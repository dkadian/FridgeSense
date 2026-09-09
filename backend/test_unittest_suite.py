import unittest
import sqlite3
import numpy as np

from app import db
from app.knowledge import get_knowledge
from app.repositories import users as users_repo, items as items_repo, events as events_repo
from app.services import risk_service, recipe_service, receipt_service, impact_service, insights_service, scratchpad_service, pantry_service
from app.ml.tfidf import TfidfVectorizer, cosine_similarity
from app.ml.matcher import FuzzyLexiconMatcher

class TestFridgeSense(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.conn.executescript(db.SCHEMA)
        self.kn = get_knowledge()

        # Create demo user
        self.user_id = users_repo.create(
            self.conn, email="test@example.com", name="Test User",
            password_hash="hash123", household_size=3
        )

    def tearDown(self):
        self.conn.close()

    # 1. Repositories Test
    def test_user_repository(self):
        user = users_repo.by_email(self.conn, "test@example.com")
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], self.user_id)
        self.assertEqual(users_repo.count(self.conn), 1)

    def test_item_repository(self):
        item_id = items_repo.create(
            self.conn, user_id=self.user_id, food_id="spinach", display_name="Spinach",
            category="leafy_greens", grams_initial=250.0, grams_remaining=250.0,
            storage="fridge", opened=0, purchase_date="2026-08-20", expiry_date="2026-08-25"
        )
        item = items_repo.get(self.conn, self.user_id, item_id)
        self.assertIsNotNone(item)
        self.assertEqual(item["food_id"], "spinach")

        active = items_repo.list_active(self.conn, self.user_id)
        self.assertEqual(len(active), 1)

    def test_event_repository(self):
        events_repo.create(
            self.conn, user_id=self.user_id, item_id=1, food_id="spinach", category="leafy_greens",
            event_type="consumed", grams=250.0, waste_reason="", co2e_kg=0.5, water_l=50.0, value_inr=35.0
        )
        evs = events_repo.since(self.conn, self.user_id, "2026-01-01")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event_type"], "consumed")

    # 2. ML Test
    def test_tfidf_vectorizer(self):
        docs = [["spinach", "paneer"], ["paneer", "atta"], ["spinach", "tomato"]]
        vec = TfidfVectorizer(sublinear_tf=True).fit(docs)
        matrix = vec.transform(docs)
        self.assertEqual(matrix.shape[0], 3)
        self.assertEqual(matrix.shape[1], 4)

        sims = cosine_similarity(matrix[0:1], matrix)
        self.assertEqual(sims.shape, (1, 3))
        self.assertAlmostEqual(sims[0, 0], 1.0, places=4)

    def test_fuzzy_matcher(self):
        matcher = FuzzyLexiconMatcher().fit([{"id": "spinach", "name": "Spinach Fresh", "keywords": "palak"}])
        res = matcher.match("spinach", top_k=1)
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0]["food_id"], "spinach")

    # 3. Impact Math & Integrity Rules Test
    def test_impact_accounting_integrity(self):
        imp = impact_service.summary(self.conn, self.user_id, days=30)
        self.assertEqual(imp["baseline_waste_rate"], 0.22)
        
        # Verify avoided_vs_baseline key exists and rescued is separate (Rule #4 in §7)
        self.assertIn("avoided_vs_baseline", imp)
        self.assertIn("rescued", imp)
        self.assertNotIn("saved", imp)  # Rule §5 shape assertion

    # 5. Storage Co-Pilot: Ethylene Conflict Detection Test
    def test_ethylene_conflict_detection(self):
        # Add Apple (ethylene producer) in fridge
        items_repo.create(
            self.conn, user_id=self.user_id, food_id="apple", display_name="Apples",
            category="fruits", grams_initial=500.0, grams_remaining=500.0,
            storage="fridge", opened=0, purchase_date="2026-09-01", expiry_date="2026-09-25"
        )
        # Add Spinach (ethylene sensitive) in the same fridge
        spinach_id = items_repo.create(
            self.conn, user_id=self.user_id, food_id="spinach", display_name="Spinach",
            category="leafy_greens", grams_initial=250.0, grams_remaining=250.0,
            storage="fridge", opened=0, purchase_date="2026-09-01", expiry_date="2026-09-06"
        )
        scored = risk_service.score_pantry(self.conn, self.user_id, self.kn)
        spinach_scored = next((s for s in scored if s["food_id"] == "spinach"), None)
        self.assertIsNotNone(spinach_scored)
        self.assertTrue(spinach_scored["ethylene_co_pilot"]["has_conflict"])
        self.assertIn("Apples", spinach_scored["ethylene_co_pilot"]["conflicting_with"])
        # Verify action recommendation mentions separating from Apples
        self.assertTrue(any("Apples" in act for act in spinach_scored["actions"]))

    # 6. Storage Location Edit & Recalculation Test
    def test_storage_location_update(self):
        from app.services import pantry_service
        item = pantry_service.add_item(
            self.conn, self.user_id, food_id="paneer", grams=200, storage="pantry", kn=self.kn
        )
        self.assertEqual(item["storage"], "pantry")
        pantry_expiry = item["expiry_date"]
        
        # User mistakenly put paneer in pantry, now edits to fridge
        updated = pantry_service.update_item(
            self.conn, self.user_id, item["item_id"], storage="fridge", kn=self.kn
        )
        self.assertEqual(updated["storage"], "fridge")
        self.assertGreaterEqual(updated["days_to_expiry"], item["days_to_expiry"])

        # Edit to freezer
        frozen = pantry_service.update_item(
            self.conn, self.user_id, item["item_id"], storage="freezer", kn=self.kn
        )
        self.assertEqual(frozen["storage"], "freezer")
        self.assertGreater(frozen["days_to_expiry"], updated["days_to_expiry"])

        # Edit back to pantry — verify 100% deterministic (no random drift or increase)
        back_to_pantry = pantry_service.update_item(
            self.conn, self.user_id, item["item_id"], storage="pantry", kn=self.kn
        )
        self.assertEqual(back_to_pantry["storage"], "pantry")
        self.assertEqual(back_to_pantry["expiry_date"], pantry_expiry)

    # 7. Container & Packaging Co-Pilot Tests
    def test_container_packaging_engine(self):
        from app.services import pantry_service
        # Add spinach in fridge with default packaging
        item = pantry_service.add_item(
            self.conn, self.user_id, food_id="spinach", grams=250, storage="fridge", container="default", kn=self.kn
        )
        default_days = item["days_to_expiry"]

        # Airtight container: extends leafy greens shelf life
        airtight = pantry_service.update_item(
            self.conn, self.user_id, item["item_id"], container="airtight", kn=self.kn
        )
        self.assertGreater(airtight["days_to_expiry"], default_days)
        self.assertEqual(airtight["packaging_insight"]["tone"], "positive")

        # Polythene bag: condensation penalty for leafy greens
        poly = pantry_service.update_item(
            self.conn, self.user_id, item["item_id"], container="polythene", kn=self.kn
        )
        self.assertLess(poly["days_to_expiry"], airtight["days_to_expiry"])
        self.assertEqual(poly["packaging_insight"]["tone"], "negative")

        # Uncovered penalty: leaving it open reduces shelf life and generates alert
        uncovered = pantry_service.update_item(
            self.conn, self.user_id, item["item_id"], container="open", is_covered=False, kn=self.kn
        )
        self.assertLessEqual(uncovered["days_to_expiry"], poly["days_to_expiry"])
        self.assertEqual(uncovered["packaging_insight"]["tone"], "negative")

    # 8. Text Scratchpad & Hinglish Parser Tests
    def test_scratchpad_service_parsing(self):
        from app.services import scratchpad_service
        
        # Test 1: Comma-separated list
        text1 = "1 kg aloo, aadha kilo tamatar, do gaddi palak, 200g paneer"
        res1 = scratchpad_service.parse_scratchpad_notes(text1, self.kn)
        self.assertEqual(len(res1["items"]), 4)
        items1 = {i["name"]: i for i in res1["items"]}
        
        self.assertIn("Potato", items1)
        self.assertEqual(items1["Potato"]["grams"], 1000.0)
        self.assertEqual(items1["Potato"]["container"], "paper_mesh")
        
        self.assertIn("Tomato", items1)
        self.assertEqual(items1["Tomato"]["grams"], 500.0)
        
        self.assertIn("Spinach", items1)
        self.assertEqual(items1["Spinach"]["grams"], 500.0)
        self.assertEqual(items1["Spinach"]["container"], "airtight")
        
        self.assertIn("Paneer", items1)
        self.assertEqual(items1["Paneer"]["grams"], 200.0)
        self.assertEqual(items1["Paneer"]["container"], "airtight")
        
        # Test 2: Multiline numbered list with colloquial units (ek pav, dozen)
        text2 = """1. ek pav hari mirch
2. 100g adrak
3. 1 dozen ande"""
        res2 = scratchpad_service.parse_scratchpad_notes(text2, self.kn)
        self.assertEqual(len(res2["items"]), 3)
        items2 = {i["name"]: i for i in res2["items"]}
        
        self.assertEqual(items2["Green Chilli"]["grams"], 250.0)
        self.assertEqual(items2["Ginger"]["grams"], 100.0)
        self.assertEqual(items2["Eggs"]["grams"], 600.0)

    def test_auto_retire_and_restock_list(self):
        # 1. Add tomato and resolve it as consumed
        item1 = pantry_service.add_item(
            self.conn, self.user_id, "tomato", grams=500.0, kn=self.kn
        )
        self.assertEqual(len(items_repo.list_active(self.conn, self.user_id)), 1)
        pantry_service.resolve_item(self.conn, self.user_id, item1["item_id"], "consumed", kn=self.kn)
        self.assertEqual(len(items_repo.list_active(self.conn, self.user_id)), 0)

        # 2. Check that tomato is now in the prebuilt restock list
        restock = pantry_service.get_restock_list(self.conn, self.user_id, self.kn)
        self.assertEqual(len(restock), 1)
        self.assertEqual(restock[0]["food_id"], "tomato")
        self.assertEqual(restock[0]["typical_grams"], 500.0)

        # 3. 1-click restock tomato
        res = pantry_service.restock_items(self.conn, self.user_id, [restock[0]], kn=self.kn)
        self.assertEqual(res["added_count"], 1)

        # Active items now has 1 tomato, and restock list is empty
        active = items_repo.list_active(self.conn, self.user_id)
        self.assertEqual(len(active), 1)
        self.assertEqual(len(pantry_service.get_restock_list(self.conn, self.user_id, self.kn)), 0)

        # 4. Now reduce active tomato stock to 20g (depleted), and add fresh 1000g tomato
        items_repo.update(self.conn, self.user_id, active[0]["id"], grams_remaining=20.0)
        pantry_service.add_item(self.conn, self.user_id, "tomato", grams=1000.0, kn=self.kn)

        # Auto-retire should have archived the 20g batch, leaving only the fresh 1000g batch
        active_after = items_repo.list_active(self.conn, self.user_id)
        self.assertEqual(len(active_after), 1)
        self.assertEqual(float(active_after[0]["grams_remaining"]), 1000.0)

    def test_shopping_list_dismissal_and_persistence(self):
        # 1. Add potato and resolve as consumed
        it = pantry_service.add_item(self.conn, self.user_id, "potato", grams=800.0, kn=self.kn)
        pantry_service.resolve_item(self.conn, self.user_id, it["item_id"], "consumed", kn=self.kn)
        restock = pantry_service.get_restock_list(self.conn, self.user_id, self.kn)
        self.assertTrue(any(x["food_id"] == "potato" for x in restock))

        # 2. Dismiss potato -> must be excluded from restock list and not reappear
        pantry_service.dismiss_restock_item(self.conn, self.user_id, "potato")
        restock_after_dismiss = pantry_service.get_restock_list(self.conn, self.user_id, self.kn)
        self.assertFalse(any(x["food_id"] == "potato" for x in restock_after_dismiss))

        # 3. Add custom shopping item
        custom = pantry_service.add_custom_shopping_item(
            self.conn, self.user_id, "Chai Patti", category="beverages", grams=250.0, unit="g", kn=self.kn
        )
        self.assertEqual(custom["name"], "Chai Patti")
        restock_with_custom = pantry_service.get_restock_list(self.conn, self.user_id, self.kn)
        self.assertTrue(any(x["name"] == "Chai Patti" for x in restock_with_custom))

        # 4. Clear restock list -> all items dismissed
        pantry_service.clear_restock_list(self.conn, self.user_id, self.kn)
        restock_cleared = pantry_service.get_restock_list(self.conn, self.user_id, self.kn)
        self.assertEqual(len(restock_cleared), 0)


if __name__ == "__main__":
    unittest.main()



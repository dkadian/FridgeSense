import unittest
import sqlite3
import numpy as np

from app import db
from app.knowledge import get_knowledge
from app.repositories import users as users_repo, items as items_repo, events as events_repo
from app.services import risk_service, recipe_service, receipt_service, impact_service, insights_service
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

if __name__ == "__main__":
    unittest.main()


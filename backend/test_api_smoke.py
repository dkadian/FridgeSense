import sys
from fastapi.testclient import TestClient
from app.main import app

def test_api():
    client = TestClient(app)
    
    # 1. Auth login
    res = client.post("/api/auth/login", json={"email": "demo@fridgesense.app", "password": "demo1234"})
    assert res.status_code == 200, f"Login failed: {res.text}"
    token_data = res.json()
    assert "access_token" in token_data
    token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✓ Auth login passed")

    # 2. Auth me
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 200
    print("✓ Auth me passed")

    # 3. Risk eat-first
    res = client.get("/api/risk/eat-first?limit=8", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data and "summary" in data
    print(f"✓ Eat-first returned {len(data['items'])} items")

    # 4. Pantry
    res = client.get("/api/pantry", headers=headers)
    assert res.status_code == 200
    pantry_data = res.json()
    assert "items" in pantry_data and "summary" in pantry_data
    print(f"✓ Pantry returned {len(pantry_data['items'])} items")

    # 5. Impact summary
    res = client.get("/api/impact/summary?days=30", headers=headers)
    assert res.status_code == 200
    imp_sum = res.json()
    assert "avoided_vs_baseline" in imp_sum
    assert "rescued" in imp_sum
    print("✓ Impact summary passed")

    # 6. Impact timeseries
    res = client.get("/api/impact/timeseries?days=30", headers=headers)
    assert res.status_code == 200
    print("✓ Impact timeseries passed")

    # 7. Impact breakdown
    res = client.get("/api/impact/breakdown?days=30", headers=headers)
    assert res.status_code == 200
    print("✓ Impact breakdown passed")

    # 8. Impact insights
    res = client.get("/api/impact/insights?days=90", headers=headers)
    assert res.status_code == 200
    print("✓ Impact insights passed")

    # 9. Recipes suggest
    res = client.get("/api/recipes/suggest?limit=6", headers=headers)
    assert res.status_code == 200
    rec_data = res.json()
    assert "recipes" in rec_data
    print(f"✓ Recipes suggest returned {len(rec_data['recipes'])} recipes")

    # 10. Recipe detail
    if rec_data["recipes"]:
        r_id = rec_data["recipes"][0]["recipe_id"]
        res = client.get(f"/api/recipes/{r_id}", headers=headers)
        assert res.status_code == 200
        print(f"✓ Recipe detail for {r_id} passed")

    # 11. Receipt parse
    res = client.post("/api/receipt/parse", json={"text": "SPINACH 250G 35.00\nPANEER 200G 90.00"}, headers=headers)
    assert res.status_code == 200
    parsed = res.json()
    assert "items" in parsed
    print("✓ Receipt parse passed")

    # 12. Catalog foods
    res = client.get("/api/catalog/foods?q=spinach", headers=headers)
    assert res.status_code == 200
    print("✓ Catalog foods passed")

    # 13. Meta model card
    res = client.get("/api/risk/model", headers=headers)
    assert res.status_code == 200
    print("✓ Meta model card passed")

    # 14. AI status
    res = client.get("/api/ai/status")
    assert res.status_code == 200
    assert "features" in res.json()
    print("✓ AI status endpoint passed")

    # 15. AI coach
    res = client.post("/api/ai/coach", json={"message": "how to store fresh coriander?"}, headers=headers)
    assert res.status_code == 200
    assert "answer" in res.json()
    print("✓ AI Food Rescue Coach passed")

    # 16. Hinglish colloquial text parser
    res = client.post("/api/receipt/parse-text", json={"text": "2 packet doodh\naadha kilo tamatar\nek pav hari mirch"}, headers=headers)
    assert res.status_code == 200
    assert len(res.json()["items"]) == 3
    print("✓ Hinglish colloquial text parser passed")

    # 17. Vision image parser
    sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    res = client.post("/api/receipt/parse-image", json={"image_base64": sample_b64, "mime_type": "image/png", "mode": "fridge"}, headers=headers)
    assert res.status_code == 200
    assert len(res.json()["items"]) > 0
    print("✓ Vision image parser passed")

    # 18. Chef Gemini AI Recipe Generation
    res = client.post("/api/recipes/ai-generate", json={"meal": "dinner", "diet": "vegetarian"}, headers=headers)
    assert res.status_code == 200
    gen_rec = res.json()
    assert "title" in gen_rec and "rescue_grams" in gen_rec
    print(f"✓ Chef Gemini AI Recipe Generator passed: {gen_rec['title']}")

    # 19. Custom Recipe Cook
    res = client.post("/api/recipes/cook-custom", json={"title": gen_rec["title"], "ingredients": [{"food_id": "spinach", "grams": 20.0}]}, headers=headers)
    assert res.status_code == 200
    assert "totals" in res.json()
    print("✓ Custom recipe cook deduction passed")

    print("\nALL 19 SMOKE ENDPOINTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_api()


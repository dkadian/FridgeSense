# FridgeSense — Project Handoff & Technical Reference

> This document provides the complete architecture, data contracts, design system specifications, model integrity constraints, and operational guidelines for **FridgeSense**.

---

## 0. Project Overview & Context

**FridgeSense** is an AI-powered household food intelligence and waste mitigation engine engineered for Indian households as part of the **1M1B Youth Leaders & IBM SkillsBuild AI Internship**.

- **Lead Developer:** **Deepak**
- **Institution:** Department of Computer Science & Engineering, **Sushant University, Gurugram, Haryana, India**
- **Mission:** Address the 68.7 million tonnes of annual household food waste in India by replacing static printed expiry dates with calibrated cold-chain decay physics, container microclimate modeling, automated staple burn-rate tracking, and generative zero-waste recipe synthesis.
- **Global Impact:** Aligned directly with **UN SDG 12 (Responsible Consumption & Production)**, **SDG 13 (Climate Action)**, and **SDG 2 (Zero Hunger)**.

---

## 1. Core Architecture & Tech Stack

- **Backend:** Python 3.10+, **FastAPI**, SQLite (`sqlite3` stdlib with ACID transactions), **PyJWT** authentication, Pydantic schemas.
- **Machine Learning Engine:** Hand-rolled, dependency-light GBDT + Logistic baseline, calibrated via `CalibratedClassifierCV` (Brier Score `0.048`, Expected Calibration Error `< 1%`, ROC-AUC `0.8359`). Pure NumPy at runtime for minimal footprint.
- **Generative AI:** **Google Gemini 2.5 Flash** integrated in `app/services/recipe_service.py` to synthesize bespoke Indian recipes targeting high-risk perishables with 1-click pantry deduction.
- **Frontend:** **React 18 + Vite + React Router 6**. Bespoke CSS custom properties & SVG visualizations (cold-chain petrol & frost aesthetic; no third-party heavyweight chart libs).
- **Packaging Microclimate Physics:** Mathematical decay multipliers:
  - 🥫 Steel Dabba: `0.90x` (thermal mass buffering)
  - 🔒 Airtight Container: `0.75x` (moisture retention & aerobic bacteria inhibition)
  - 🛍️ Polybag: `1.30x` (condensation penalty)
  - 🕸️ Open Mesh / Basket: `1.10x` (desiccation factor)

---

## 2. Implementation Status — All Milestones Complete ✅

1. **Backend & Microservices: COMPLETE & VERIFIED**
   - 36 modules, 34 endpoints across 8 routers (`auth`, `pantry`, `risk`, `recipes`, `receipts`, `impact`, `catalog`, `meta`).
   - Automated test suites passing: 9/9 unit tests (`test_unittest_suite.py`) and API smoke test suite (`test_api_smoke.py`).
   - App factory pattern in `backend/app/main.py` (`app = create_app()`).

2. **Machine Learning & Artifacts: TRAINED & CALIBRATED**
   - Stored in `ml/artifacts/`: `spoilage_model.json`, `baseline_logistic.json`, `recipe_index.json`, `lexicon_index.json`, `model_card.json`, `spoilage_dataset.csv`.
   - Honest test **ROC-AUC ≈ 0.8359** (no target leakage, scale-free quantity ratios).
   - Expected Calibration Error `< 0.01` (1%), Decile Lift `3.35x`.

3. **Frontend & Styling: 100% COMPLETE**
   - Complete CSS design system in `frontend/src/styles/` (`tokens.css`, `base.css`, `app.css`).
   - Cold-chain design identity implemented across all 8 views (Dashboard, Pantry, Add/Import, Recipes, RecipeDetail, Impact, Habits/Insights, ModelCard, Login).
   - Calibrated Freshness Gauge: 0% Cool Teal (`#12A594`) to 100% Hot Crimson (`#E11D48`).

4. **Zero-Effort Predictive Horizon: COMPLETE**
   - Automated Indian staple tracking for Aloo, Pyaz, Tamatar, and Dahi.
   - Self-calibrating daily burn rate calculations with 1-tap quick top-ups.

5. **Chef Gemini Zero-Waste AI Studio: COMPLETE**
   - Generative Indian recipe creation rescuing multi-item perishables nearing spoilage.
   - 1-Click "I Made This" auto-deducts consumed quantities from active pantry stock.

6. **Documentation & Deliverables: COMPLETE**
   - Official Capstone Project Document (`FridgeSense_Project_Document.docx` and `FridgeSense_Project_Document.pdf`).
   - Markdown specifications (`README.md`, `HANDOFF.md`, `IBM_BOB_USAGE.md`, `docs/PROJECT_DOCUMENT.md`, `docs/PROJECT_REPORT.md`).
   - High-definition 1080p demonstration video with Microsoft Neural voiceover.

---

## 3. API Contract & Response Shapes

- **`GET /api/risk/eat-first`** $\rightarrow$ `{ items: ScoredItem[], summary: PantrySummary, total_active }`
- **`GET /api/pantry`** $\rightarrow$ `{ items: ScoredItem[], summary: PantrySummary }`
- **`ScoredItem`**:
  ```typescript
  interface ScoredItem {
    item_id: number;
    food_id: string;
    name: string;
    category: string;
    storage: string;
    container_type?: string;     // steel_dabba, airtight, polybag, open_mesh
    container_multiplier?: number; // 0.75 to 1.30
    opened: boolean;
    grams_remaining: number;
    purchase_date: string;
    expiry_date: string;
    days_to_expiry: number;
    risk: number;                // 0.0 to 1.0
    risk_band: "low" | "medium" | "high" | "critical";
    risk_label: string;
    risk_color: string;
    at_risk_co2e_kg: number;
    at_risk_water_l: number;
    at_risk_value_inr: number;
    embodied_co2e_kg: number;
    embodied_value_inr: number;
    best_storage: string;
    reasons: { feature: string; text: string; direction: string; contribution: number }[];
    actions: string[];
  }
  ```
- **`PantrySummary`**:
  ```typescript
  interface PantrySummary {
    items_active: number;
    band_counts: { critical: number; high: number; medium: number; low: number };
    items_at_risk: number;
    expected_loss_kg: number;
    expected_loss_co2e_kg: number;
    expected_loss_inr: number;
    pantry_value_inr: number;
    pantry_co2e_kg: number;
  }
  ```
- **`GET /api/impact/summary`** $\rightarrow$
  ```typescript
  {
    window_days: number;
    window_start: string;
    window_end: string;
    wasted: MetricBlock;
    consumed: MetricBlock;
    donated: MetricBlock;
    rescued: MetricBlock;
    handled: MetricBlock;
    waste_rate: number;
    perishable: boolean;
    baseline_waste_rate: 0.22; // UNEP 22% benchmark
    avoided_vs_baseline: { grams: number; kg: number; co2e_kg: number; water_l: number; value_inr: number; beats_baseline: boolean };
    meals_saved: number;
    meals_lost: number;
    equivalences_avoided: { key: string; value: number; unit: string; label: string; icon: string }[];
    sources: string[];
  }
  ```
- **`POST /api/recipes/generate-bespoke`** $\rightarrow$ Bespoke recipe payload with custom culinary instructions and 1-click pantry deduction support.
- **`POST /api/recipes/{id}/cook`** $\rightarrow$ `{ recipe_id, title, servings, used: [...], short: [...], totals: { rescued_grams } }`
- **`GET /api/risk/model`** $\rightarrow$ Returns the complete `model_card.json` metrics, calibration curve, and decile lift.

---

## 4. Model Integrity & Data Science Safeguards

1. **Zero Target Leakage:** The model predicts realistic probabilistic risk ($ROC-AUC \approx 0.8359$). Absolute shelf-life completion is never used as an input feature.
2. **Scale-Free Feature Space:** Quantities are represented as unitless proportions (`grams_remaining / grams_initial`, `elapsed_days / nominal_shelf_life`) to ensure invariance across bulk and small packings.
3. **Like-for-Like Baseline Accounting:** The counterfactual comparison applies the UNEP 22% household food waste rate **strictly to perishable food categories**, preventing shelf-stable staples (atta, rice) from artificially inflating avoided waste metrics.
4. **Honest Rescue Attribution:** Items eaten while flagged at-risk are tracked distinctly as `rescued`, never conflated with counterfactual `avoided_vs_baseline`.
5. **No Metric Double-Counting:** Monthly figures across separate loss categories are treated as distinct analytical facets and never summed.

---

## 5. Quick Verification Commands

```bash
# Run unit tests
cd backend && python3 test_unittest_suite.py

# Run API smoke test
python3 test_api_smoke.py

# Launch entire platform
cd .. && ./run.sh
```

---

## 6. Future Expansion Roadmap

1. **Smart Refrigerator OEM Integration:** Firmware daemon syncing internal camera feeds and temperature sensors directly with the `/api/pantry` and `/api/risk` endpoints.
2. **Quick-Commerce Automated Restock:** Webhook and deep-link integration with Indian quick-commerce providers (Blinkit, Zepto, Instamart) when Zero-Effort Horizon countdowns reach $< 24\text{ hours}$.
3. **Kirana Cold-Chain Tier:** Extending container microclimate physics to retail milk crates, vegetable crates, and small commercial chillers.

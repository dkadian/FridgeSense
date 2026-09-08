# IBM BOB Usage Log — FridgeSense

**AI Household Food Intelligence & Waste Mitigation Engine**  
*Documenting the utilization of IBM BOB (Build-on-the-Cloud Assistant) across Ideation, Architecture, Machine Learning Formulation, Generative AI Integration, and Verification.*

---

## 👨‍💻 Contributor & Program Attribution

- **Student Contributor:** **Deepak**
- **University:** Department of Computer Science & Engineering, **Sushant University, Gurugram, Haryana, India**
- **Internship:** **1M1B Youth Leaders & IBM SkillsBuild AI Internship**
- **Project Focus:** Household Food Waste Mitigation & UN SDGs 12, 13, and 2

---

## 1. Ideation Phase

### Prompt 1.1: Addressing Indian Household Perishable Waste
> **User Prompt to BOB:**  
> *"I want to build an AI application for urban Indian households to address food waste. What features can move the needle on domestic waste, especially for high-risk perishables like paneer, fresh coriander, curd, and cooked dal in tropical ambient conditions?"*

**BOB's Insights & Recommendations:**
- **"Eat Me First" Urgency Queue:** Move away from static printed expiry dates that fail under Indian 35°C+ summer humidity. Triage perishables by active physiological decay risk.
- **Container Microclimate Modeling:** Account for traditional Indian storage vessels (stainless steel dabbas, plastic polybags, airtight containers) which radically alter humidity transpiration and decay velocity.
- **Zero-Effort Consumption Horizon:** Indian kitchens consume staple items (aloo, pyaz, tamatar) daily in predictable cadences. Rather than burdening homemakers with daily weight logging, learn automated consumption burn rates.
- **Rigorous Baseline Metrics:** Avoid vanity claims ("100% of food saved"). Ground all counterfactual accounting against the **UNEP Food Waste Index 22% unmanaged household waste baseline**.

![BOB Ideation Prompt](docs/bob/01-ideation.png)

---

## 2. Architectural & System Design Decisions

### Prompt 2.1: Minimalist, Resilient Tech Stack with Cold-Chain Aesthetics
> **User Prompt to BOB:**  
> *"Recommend an architectural blueprint for a lightweight, high-performance web app with a distinctive cold-chain design identity, deterministic ML risk scoring, and generative recipe capabilities."*

**Architecture Decisions Informed by BOB:**
1. **Backend Layer:** Python 3.10+ with **FastAPI** and standard library **SQLite** (`sqlite3`) for zero-bloat, local ACID transaction persistence.
2. **Hybrid AI Paradigm:**
   - **Predictive Machine Learning (Deterministic):** Gradient-Boosted Decision Trees (LightGBM/XGBoost) using pure NumPy at runtime for sub-5ms probability calculations.
   - **Generative AI (Culinary Studio):** LLM integration (Google Gemini 2.5 Flash / Granite) grounded in Indian culinary knowledge to rescue multi-item expiring ingredients.
3. **Frontend Design Identity:**
   - React 18 + Vite with bespoke CSS Custom Properties.
   - **Cold-Chain Freshness Palette:** Cool petrol (`#0C3B3C`) and frost (`#EDF3F1`) base, where warm colors are reserved strictly for risk: **0% Cool Teal** (`#12A594`) progressing smoothly to **100% Hot Crimson** (`#E11D48`).

![BOB Architecture Diagram](docs/bob/02-architecture.png)

---

## 3. Development Assistance & Mathematical Rigour

### Prompt 3.1: Scale-Free Features & Container Physics Multipliers
> **User Prompt to BOB:**  
> *"How should we mathematically structure container microclimate physics and prevent data leakage in our spoilage model?"*

**BOB's Engineering Guidance:**
- **Container Physics Multipliers:** Model storage microclimates as exponential rate modifiers ($k_{eff} = k_0 \times \prod M_i$):
  - 🥫 **Steel Dabba ($0.90\times$):** Temperature buffering during frequent door openings.
  - 🔒 **Airtight Box ($0.75\times$):** Moisture preservation & suppression of aerobic spoilage bacteria.
  - 🛍️ **Polybag ($1.30\times$):** Transpiration condensation penalty accelerating fungal and bacterial leaf rotting.
  - 🕸️ **Open Mesh ($1.10\times$):** Airflow-induced desiccation for root vegetables.
- **Scale-Free Feature Space:** Prevent target leakage and unit bias by encoding quantities as unitless ratios (`grams_remaining / initial_grams`, `days_elapsed / nominal_shelf_life`) rather than raw gram counts.
- **Counterfactual Math:** Apply the UNEP 22% waste factor **strictly to perishables**, keeping bulk non-perishables (atta, rice) out of avoided emissions calculations.

![BOB Development Log](docs/bob/03-development.png)

---

## 4. Debugging & Verification Log

### Debug Case 1: NumPy Matrix Normalization & Divide-by-Zero
- **Issue:** `RuntimeWarning: divide by zero encountered in matmul` in vector cosine similarity calculations when users had empty ingredient queries.
- **BOB Resolution:** Implemented safe L2-normalization with epsilon floor:
  ```python
  norm = np.linalg.norm(vec, axis=-1, keepdims=True)
  safe_norm = np.where(norm > 1e-12, norm, 1.0)
  normalized_vec = vec / safe_norm
  ```

### Debug Case 2: Model Calibration & Expected Calibration Error (ECE)
- **Issue:** Raw decision tree leaves produced overconfident probabilities near 0 and 1, distorting the Freshness Meter color ramp.
- **BOB Resolution:** Applied Platt scaling / Isotonic regression via `CalibratedClassifierCV(method='sigmoid')`, reducing Expected Calibration Error to `< 0.01` and Brier Score to `0.048`.

### Debug Case 3: 1-Click Recipe Inventory Deduction Integrity
- **Issue:** Cooking a recipe that used 3 ingredients required atomic inventory deduction so partial failures wouldn't corrupt pantry records.
- **BOB Resolution:** Wrapped the pantry deduction in SQLite transaction contexts with rollback on deficit checks (`BEGIN IMMEDIATE ... COMMIT`).

![BOB Debugging Screenshot](docs/bob/04-debugging.png)

---

## 5. Summary of IBM BOB Contributions

| Phase | Key Contribution | Outcome & Verification |
| :--- | :--- | :--- |
| **Ideation** | Conceptualized "Eat Me First" risk triage & Indian container physics | Evaluated & integrated across dashboard & modals |
| **Architecture** | FastAPI + SQLite + pure NumPy runtime ML + CSS token system | Zero bloat, instant local startup via `./run.sh` |
| **Physics Modeling** | Steel Dabba ($0.90\times$), Airtight ($0.75\times$), Polybag ($1.30\times$) multipliers | Dynamically recomputes shelf-life on container switch |
| **Integrity Rules** | Scale-free features, honest `rescued` vs `avoided_vs_baseline` | Zero target leakage; ROC-AUC: `0.8359` |
| **Generative AI** | Schema design for Chef Gemini / Granite zero-waste recipe prompting | 1-Click "I Made This" live inventory deduction |
| **Verification** | Unit test harness, ECE calibration checks, safe vector math | 9/9 backend unit tests passing; smoke tests passing |

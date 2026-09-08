import { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useToast } from "../components/Toast.jsx";
import { Loader, EmptyState, Banner } from "../components/ui.jsx";
import Icon from "../components/Icons.jsx";
import { inr, kg, grams as g } from "../lib/format.js";

const MEALS = [["any", "Any meal"], ["breakfast", "Breakfast"], ["lunch", "Lunch"], ["dinner", "Dinner"], ["snack", "Snack"]];
const DIETS = [["any", "Any diet"], ["veg", "Vegetarian"], ["vegan", "Vegan"], ["nonveg", "Non-veg"]];

export default function Recipes() {
  const nav = useNavigate();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [meal, setMeal] = useState("any");
  const [diet, setDiet] = useState("any");
  const [rescueOnly, setRescueOnly] = useState(true);

  // Chef Gemini AI Generation State
  const [aiModal, setAiModal] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiRecipe, setAiRecipe] = useState(null);
  const [cookingAi, setCookingAi] = useState(false);
  const [aiPref, setAiPref] = useState("");

  const load = useCallback(async () => {
    setErr(null); setData(null);
    try {
      const res = await api.suggestRecipes({ limit: 12, meal, diet, require_rescue: rescueOnly });
      setData(res);
    } catch (e) { setErr(e.detail || "Couldn't fetch recipes."); }
  }, [meal, diet, rescueOnly]);

  useEffect(() => { load(); }, [load]);

  async function generateAiRecipe() {
    setAiLoading(true);
    setAiRecipe(null);
    try {
      const res = await api.aiGenerateRecipe({
        meal: meal === "any" ? "dinner" : meal,
        diet: diet === "any" ? "vegetarian" : (diet === "veg" ? "vegetarian" : diet),
        preferences: aiPref,
      });
      setAiRecipe(res);
      toast.ok(`Chef Gemini created: ${res.title}!`);
    } catch (e) {
      toast.err(e.detail || "Couldn't synthesize AI recipe.");
    } finally {
      setAiLoading(false);
    }
  }

  async function cookAiRecipe() {
    if (!aiRecipe) return;
    setCookingAi(true);
    try {
      const payload = {
        title: aiRecipe.title,
        servings: Number(aiRecipe.servings || 1),
        ingredients: (aiRecipe.ingredients || []).map((i) => ({
          food_id: i.food_id,
          grams: Number(i.grams || 50),
        })),
      };
      const res = await api.cookCustomRecipe(payload);
      toast.ok(`Cooked ${aiRecipe.title}! Rescued ${Math.round(res.totals?.rescued_grams || 0)}g of food.`);
      setAiModal(false);
      nav("/pantry");
    } catch (e) {
      toast.err(e.detail || "Couldn't deduct ingredients from pantry.");
    } finally {
      setCookingAi(false);
    }
  }

  if (err) return <EmptyState icon="warn" title="Couldn't fetch recipes" body={err} action={<button className="btn" onClick={load}>Try again</button>} />;

  const recipes = data?.recipes || [];
  const atRisk = data?.at_risk_items || [];

  return (
    <div className="stack" style={{ gap: "var(--sp-5)" }}>
      {/* Chef Gemini Dynamic Zero-Waste Hero Banner */}
      {!aiRecipe && (
        <section className="chef-gemini-banner card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--sp-3)" }}>
            <div style={{ maxWidth: 620 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: "1.3rem" }}>✨</span>
                <h3 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 700 }}>Chef Gemini: Dynamic Zero-Waste AI</h3>
              </div>
              <p className="muted" style={{ fontSize: "0.88rem", margin: "4px 0 var(--sp-2) 0", lineHeight: 1.45 }}>
                Don't fit any standard catalog recipe? Chef Gemini analyzes your kitchen's specific at-risk foods
                {atRisk.length > 0 ? ` (${atRisk.slice(0, 3).map((a) => a.name).join(", ")})` : ""} and synthesizes an inventive, delicious Indian rescue dish on demand.
              </p>
            </div>
            <button
              type="button"
              className="btn btn--primary"
              disabled={aiLoading}
              onClick={generateAiRecipe}
              style={{ display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap" }}
            >
              <Icon.sparkles width={16} height={16} />
              <span>{aiLoading ? "Chef Gemini is Cooking…" : "Generate Bespoke Recipe"}</span>
            </button>
          </div>
        </section>
      )}

      {/* Inline Loading State */}
      {aiLoading && (
        <section className="card" style={{ textAlign: "center", padding: "var(--sp-6) 0" }}>
          <Loader label="Chef Gemini is studying your at-risk items and designing an Indian zero-waste recipe…" />
        </section>
      )}

      {/* Featured Chef Gemini Recipe Card */}
      {aiRecipe && (
        <section className="chef-gemini-card card">
          <div className="chef-gemini-card__head">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: "1.3rem" }}>👨‍🍳</span>
              <div>
                <strong style={{ fontSize: "1.05rem" }}>Chef Gemini's Bespoke Rescue Creation</strong>
                <div style={{ fontSize: "0.75rem", color: "var(--c-text-muted)" }}>Tailored to your current at-risk produce</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button className="btn btn--sm btn--ghost" onClick={generateAiRecipe} disabled={cookingAi}>
                ↺ Try Another
              </button>
              <button className="btn btn--sm btn--ghost" onClick={() => setAiRecipe(null)} title="Dismiss">✕</button>
            </div>
          </div>

          <div className="chef-gemini-card__body">
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
                <h2 style={{ margin: "0 0 4px 0", fontSize: "1.35rem" }}>{aiRecipe.title}</h2>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <span className="chip">⏱️ {aiRecipe.minutes} min</span>
                  <span className="chip">👥 Serves {aiRecipe.servings}</span>
                  <span className="chip chip--ok">{aiRecipe.diet}</span>
                </div>
              </div>
              <div className="recipe__meta mono" style={{ fontSize: "0.82rem", margin: "6px 0 var(--sp-2) 0" }}>
                {aiRecipe.cuisine} · {aiRecipe.meal}
              </div>
              {aiRecipe.rescue_note && (
                <div className="banner banner--ok" style={{ padding: "10px 14px", fontSize: "0.88rem", lineHeight: 1.45, margin: "var(--sp-2) 0" }}>
                  <strong>🌱 Zero-Waste Rescue Note:</strong> {aiRecipe.rescue_note}
                </div>
              )}
            </div>

            {/* Impact Badges */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, background: "var(--c-bg-subtle)", padding: 12, borderRadius: 8 }}>
              <div>
                <span className="muted" style={{ fontSize: "0.75rem", display: "block" }}>Rescued Food</span>
                <strong className="mono" style={{ color: "var(--c-ok)" }}>{g(aiRecipe.rescue_grams || 0)}</strong>
              </div>
              <div>
                <span className="muted" style={{ fontSize: "0.75rem", display: "block" }}>Value Saved</span>
                <strong className="mono" style={{ color: "var(--c-primary)" }}>{inr(aiRecipe.rescue_value_inr || 0)}</strong>
              </div>
              <div>
                <span className="muted" style={{ fontSize: "0.75rem", display: "block" }}>Carbon Avoided</span>
                <strong className="mono">{aiRecipe.rescue_co2e_kg || 0} kg CO₂e</strong>
              </div>
            </div>

            {/* Ingredients & Method */}
            <div className="grid-2" style={{ gap: "var(--sp-3)" }}>
              <div style={{ background: "var(--c-bg)", padding: 14, borderRadius: 8, border: "1px solid var(--c-border)" }}>
                <h4 style={{ margin: "0 0 10px 0", fontSize: "0.95rem" }}>Ingredients Needed</h4>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: "0.85rem", display: "flex", flexDirection: "column", gap: 6 }}>
                  {(aiRecipe.ingredients || []).map((ing, idx) => (
                    <li key={idx} style={{ color: ing.at_risk ? "var(--c-warn)" : "inherit" }}>
                      <span><strong>{ing.name}</strong> — {g(ing.grams)}</span>
                      {ing.at_risk && <span className="chip chip--warn" style={{ fontSize: "0.68rem", marginLeft: 6 }}>at risk</span>}
                    </li>
                  ))}
                </ul>
              </div>

              <div style={{ background: "var(--c-bg)", padding: 14, borderRadius: 8, border: "1px solid var(--c-border)" }}>
                <h4 style={{ margin: "0 0 10px 0", fontSize: "0.95rem" }}>Method</h4>
                <ol style={{ margin: 0, paddingLeft: 20, fontSize: "0.84rem", display: "flex", flexDirection: "column", gap: 8, lineHeight: 1.45 }}>
                  {(aiRecipe.steps || []).map((step, idx) => (
                    <li key={idx}>{step}</li>
                  ))}
                </ol>
              </div>
            </div>

            <div className="inline" style={{ justifyContent: "space-between", borderTop: "1px solid var(--c-border)", paddingTop: "var(--sp-3)" }}>
              <button type="button" className="btn btn--ghost" onClick={generateAiRecipe} disabled={cookingAi}>
                ↺ Re-roll Recipe
              </button>
              <button type="button" className="btn btn--primary" onClick={cookAiRecipe} disabled={cookingAi}>
                {cookingAi ? "Deducting from pantry…" : "🍳 Cook & Rescue This Dish"}
              </button>
            </div>
          </div>
        </section>
      )}

      <div className="toolbar">
        <div className="inline">
          <select className="select" value={meal} onChange={(e) => setMeal(e.target.value)}>{MEALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <select className="select" value={diet} onChange={(e) => setDiet(e.target.value)}>{DIETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </div>
        <label className="check"><input type="checkbox" checked={rescueOnly} onChange={(e) => setRescueOnly(e.target.checked)} /> Only recipes that rescue at-risk food</label>
      </div>

      {atRisk.length > 0 && (
        <p className="muted">Cooking to rescue: {atRisk.slice(0, 6).map((a) => a.name).join(", ")}{atRisk.length > 6 ? `, +${atRisk.length - 6} more` : ""}.</p>
      )}

      {!data ? <Loader label="Matching recipes to your fridge…" /> : recipes.length === 0 ? (
        <EmptyState icon="recipe" title="No matches right now"
          body={rescueOnly ? "Nothing at-risk maps to a catalog recipe yet. Tap 'Generate Bespoke Recipe' above to have Chef Gemini synthesize a custom dish for your items!" : "Add a few more items and we'll suggest dishes."}
          action={rescueOnly ? <button className="btn btn--primary" onClick={generateAiRecipe}>✨ Ask Chef Gemini</button> : null} />
      ) : (
        <div className="recipe-grid">
          {recipes.map((r) => <RecipeCard key={r.recipe_id} r={r} />)}
        </div>
      )}
    </div>
  );
}



function RecipeCard({ r }) {
  const cover = Math.round((r.coverage || 0) * 100);
  const rescues = r.rescues || [];
  return (
    <Link to={`/recipes/${r.recipe_id}`} className="recipe">
      <div className="recipe__top">
        <h3 className="recipe__title">{r.title}</h3>
        <span className="chip">{r.minutes} min</span>
      </div>
      <div className="recipe__meta mono">{r.cuisine} · {r.meal} · {r.diet}</div>
      {rescues.length > 0 ? (
        <div className="recipe__rescue">
          <Icon.leaf width={15} height={15} />
          <span>Rescues {rescues.slice(0, 3).join(", ")}{rescues.length > 3 ? ` +${rescues.length - 3}` : ""}</span>
        </div>
      ) : <div className="recipe__rescue muted"><Icon.plate width={15} height={15} /> Uses what you have</div>}
      <div className="recipe__stats">
        <div><span className="mono">{cover}%</span><label>you have</label></div>
        <div><span className="mono">{g(r.rescue_grams || 0)}</span><label>rescued</label></div>
        <div><span className="mono">{inr(r.rescue_value_inr || 0)}</span><label>value</label></div>
      </div>
      {r.missing_count > 0 && <div className="recipe__missing muted small">Missing {r.missing_count}: {(r.missing || []).map((m) => m.name).slice(0, 3).join(", ")}</div>}
      <div className="recipe__cta">View recipe <Icon.arrowRight width={14} height={14} /></div>
    </Link>
  );
}

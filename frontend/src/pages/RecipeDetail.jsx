import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useToast } from "../components/Toast.jsx";
import { Loader, EmptyState } from "../components/ui.jsx";
import Icon from "../components/Icons.jsx";
import { grams as g } from "../lib/format.js";

export default function RecipeDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const [recipe, setRecipe] = useState(null);
  const [err, setErr] = useState(null);
  const [servings, setServings] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setErr(null);
    try { setRecipe(await api.recipe(id)); }
    catch (e) { setErr(e.detail || "Couldn't load this recipe."); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function cook() {
    setBusy(true);
    try {
      const res = await api.cookRecipe(id, servings ? Number(servings) : undefined);
      const n = res.used?.length ?? 0;
      const rescued = res.totals?.rescued_grams ?? 0;
      toast.ok(`Cooked ${recipe.title}. Used ${n} pantry item${n === 1 ? "" : "s"}${rescued > 0 ? `, rescuing ${Math.round(rescued)} g` : ""}.`);
      nav("/pantry");
    } catch (e) { toast.err(e.detail || "Couldn't deduct ingredients — do you still have them?"); setBusy(false); }
  }

  if (err) return <EmptyState icon="warn" title="Couldn't load this recipe" body={err} action={<Link className="btn" to="/recipes">Back to recipes</Link>} />;
  if (!recipe) return <Loader label="Fetching the recipe…" />;

  const ingredients = recipe.ingredients || [];
  const steps = recipe.steps || [];

  return (
    <div className="stack" style={{ gap: "var(--sp-5)" }}>
      <Link className="link" to="/recipes"><Icon.arrowRight width={14} height={14} style={{ transform: "rotate(180deg)" }} /> All recipes</Link>

      <header className="recipe-head">
        <div>
          <h2>{recipe.title}</h2>
          <div className="recipe__meta mono">{recipe.cuisine} · {recipe.meal} · {recipe.diet} · {recipe.minutes} min · serves {recipe.servings}</div>
          {recipe.rescue_note && <p className="recipe-head__note">{recipe.rescue_note}</p>}
        </div>
      </header>

      <div className="grid-2">
        <section className="card">
          <h3 className="card__title">Ingredients</h3>
          <ul className="ingredients">
            {ingredients.map((ing, i) => (
              <li key={i} className={ing.optional ? "is-optional" : ""}>
                <span>{ing.name}</span>
                <span className="muted mono">{g(ing.grams)}{ing.optional ? " · optional" : ""}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h3 className="card__title">Method</h3>
          <ol className="steps">{steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
        </section>
      </div>

      <section className="card cook-bar">
        <div>
          <h3 className="card__title">Cook it</h3>
          <p className="muted small">This deducts each ingredient from your pantry (capped at what you have) and logs the ones it rescues.</p>
        </div>
        <div className="inline">
          <input className="input" style={{ width: 120 }} type="number" min={1} placeholder={`${recipe.servings} servings`} value={servings} onChange={(e) => setServings(e.target.value)} />
          <button className="btn btn--primary" disabled={busy} onClick={cook}>{busy ? "Cooking…" : "Cook & deduct"}</button>
        </div>
      </section>
    </div>
  );
}

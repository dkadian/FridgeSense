import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api.js";
import { Loader, EmptyState } from "../components/ui.jsx";
import { RankBars } from "../components/charts.jsx";
import Icon from "../components/Icons.jsx";

const pct = (v, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
const num = (v, d = 3) => (v == null ? "—" : Number(v).toFixed(d));

export default function ModelCard() {
  const [card, setCard] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try { setCard(await api.modelCard()); }
    catch (e) { setErr(e.detail || "The model card isn't available."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (err) return <EmptyState icon="model" title="No model card yet" body={err} action={<button className="btn" onClick={load}>Try again</button>} />;
  if (!card) return <Loader label="Opening the model card…" />;

  const m = card.metrics_test || {};
  const b = card.baseline_metrics_test || {};
  const at = m.at_threshold || {};
  const td = card.training_data || {};
  const lift = (m.lift || []).slice(0, 6).map((l) => ({ label: `Decile ${l.decile}`, value: l.waste_rate, sub: `${l.lift}× lift` }));
  const imps = (card.feature_importances || []).slice(0, 8).map((f) => ({ label: prettyFeature(f.feature), value: f.importance }));
  const cats = [...(card.per_category_auc || [])].filter((c) => c.n >= 30).sort((a, b) => b.roc_auc - a.roc_auc);

  return (
    <div className="stack" style={{ gap: "var(--sp-5)" }}>
      <section className="card model-hero">
        <div className="model-hero__icon"><Icon.model width={26} height={26} /></div>
        <div>
          <h2>{card.model_name}</h2>
          <p className="muted">{card.task}</p>
          <p className="model-hero__use">{card.intended_use}</p>
        </div>
      </section>

      <section className="metric-grid">
        <BigMetric label="ROC-AUC" value={num(m.roc_auc)} note="ranking quality" />
        <BigMetric label="Avg precision" value={num(m.average_precision)} note="PR-curve area" />
        <BigMetric label="Recall @ 0.3" value={pct(at.recall)} note="of true spoilage caught" />
        <BigMetric label="Calibration err" value={pct(m.expected_calibration_error, 2)} note="lower is better" />
      </section>

      <div className="grid-2">
        <section className="card">
          <h3 className="card__title">It beats a naive baseline</h3>
          <p className="muted small">Same features, but the baseline is a single logistic regression. The gradient-boosted model earns its keep:</p>
          <table className="table compare">
            <thead><tr><th></th><th>This model</th><th>Baseline</th></tr></thead>
            <tbody>
              <tr><td>ROC-AUC</td><td className="mono">{num(m.roc_auc)}</td><td className="mono muted">{num(b.roc_auc)}</td></tr>
              <tr><td>Avg precision</td><td className="mono">{num(m.average_precision)}</td><td className="mono muted">{num(b.average_precision)}</td></tr>
              <tr><td>Brier score</td><td className="mono">{num(m.brier_score)}</td><td className="mono muted">{num(b.brier_score)}</td></tr>
              <tr><td>Log loss</td><td className="mono">{num(m.log_loss)}</td><td className="mono muted">{num(b.log_loss)}</td></tr>
            </tbody>
          </table>
        </section>
        <section className="card">
          <h3 className="card__title">Concentrates the risk</h3>
          <p className="muted small">Waste rate by predicted-risk decile — the top deciles carry far more spoilage, which is what makes the queue useful.</p>
          <RankBars rows={lift} color="var(--warm-high)" format={(v) => pct(v)} max={Math.max(...lift.map((l) => l.value), 0.01)} />
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <h3 className="card__title">What drives a score</h3>
          <RankBars rows={imps} color="var(--petrol)" format={(v) => num(v, 3)} />
        </section>
        <section className="card">
          <h3 className="card__title">Honesty about the data</h3>
          <dl className="kv">
            <dt>Training rows</dt><dd className="mono">{(td.rows || 0).toLocaleString()}</dd>
            <dt>Households</dt><dd className="mono">{td.households}</dd>
            <dt>Split</dt><dd>{td.split}</dd>
            <dt>Base waste rate</dt><dd className="mono">{pct(td.positive_rate)}</dd>
          </dl>
          <ul className="limitations">
            {(card.limitations || []).map((l, i) => <li key={i}><Icon.warn width={15} height={15} /> {l}</li>)}
          </ul>
        </section>
      </div>

      {cats.length > 0 && (
        <section className="card">
          <h3 className="card__title">Where it's strong and weak</h3>
          <p className="muted small">Per-category ROC-AUC (categories with ≥30 test items). Perishables with clear spoilage signals score highest.</p>
          <div className="cat-auc">
            {cats.map((c) => (
              <div key={c.category} className="cat-auc__row">
                <span className="cat-auc__name">{c.category}</span>
                <div className="cat-auc__bar"><div style={{ width: `${Math.max(4, ((c.roc_auc - 0.5) / 0.5) * 100)}%` }} /></div>
                <span className="mono cat-auc__val">{num(c.roc_auc, 2)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <p className="muted small footnote">
        <Icon.info width={13} height={13} /> Trained {card.trained_at ? new Date(card.trained_at).toLocaleDateString() : ""}
        {card.serving ? ` · serving ${card.serving.trees} trees over ${card.serving.features?.length} features` : ""}.
        Predictions are decision support, not certainties.
      </p>
    </div>
  );
}

function BigMetric({ label, value, note }) {
  return <div className="big-metric"><div className="big-metric__value mono">{value}</div><div className="big-metric__label">{label}</div><div className="big-metric__note">{note}</div></div>;
}
function prettyFeature(f) {
  return String(f).replace(/_/g, " ").replace(/\bg per\b/, "g/").replace(/\bco2e\b/i, "CO₂e");
}

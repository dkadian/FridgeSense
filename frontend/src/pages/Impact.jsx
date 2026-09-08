import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api.js";
import { Loader, EmptyState } from "../components/ui.jsx";
import { TrendChart, RankBars, Donut } from "../components/charts.jsx";
import Icon from "../components/Icons.jsx";
import { inr, kg, litres } from "../lib/format.js";

const WINDOWS = [[30, "30 days"], [90, "90 days"], [365, "This year"]];
const REASON_COLORS = ["var(--hot)", "var(--warm-high)", "var(--warm-med)", "var(--petrol)", "var(--fresh)", "#8B9DA8", "#B0655A", "#C9A227"];

export default function Impact() {
  const [days, setDays] = useState(90);
  const [sum, setSum] = useState(null);
  const [ts, setTs] = useState(null);
  const [bd, setBd] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null); setSum(null);
    try {
      const [s, t, b] = await Promise.all([
        api.impactSummary(days),
        api.impactTimeseries(days < 7 ? 7 : days),
        api.impactBreakdown(days < 7 ? 7 : days),
      ]);
      setSum(s); setTs(t); setBd(b);
    } catch (e) { setErr(e.detail || "Couldn't load your impact."); }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  if (err) return <EmptyState icon="warn" title="Couldn't load your impact" body={err} action={<button className="btn" onClick={load}>Try again</button>} />;
  if (!sum || !ts || !bd) return <Loader label="Adding up your impact…" />;

  const av = sum.avoided_vs_baseline || {};
  const wasted = sum.wasted || {};
  const consumed = sum.consumed || {};
  const rescued = sum.rescued || {};
  const eq = sum.equivalences_avoided || [];
  const beats = av.beats_baseline;

  const foodRows = (bd.top_wasted_foods || []).slice(0, 6).map((f) => ({ label: f.name, value: f.value_inr, sub: kg(f.kg) }));
  const reasonSlices = (bd.reasons || []).slice(0, 8).map((r, i) => ({ label: r.label, value: r.grams, color: REASON_COLORS[i % REASON_COLORS.length] }));

  return (
    <div className="stack" style={{ gap: "var(--sp-6)" }}>
      <div className="toolbar">
        <div className="seg">{WINDOWS.map(([v, l]) => <button key={v} className={days === v ? "is-on" : ""} onClick={() => setDays(v)}>{l}</button>)}</div>
        <span className="muted small">{sum.window_start} → {sum.window_end}</span>
      </div>

      <section className={`impact-headline ${beats ? "is-good" : "is-warn"}`}>
        <div className="impact-headline__lead">
          <div className="eyebrow">{beats ? "Ahead of the baseline" : "Behind the baseline — room to improve"}</div>
          <div className="impact-headline__num mono">{inr(Math.abs(av.value_inr || 0))}</div>
          <p>{beats
            ? <>You've kept about {inr(av.value_inr || 0)} of food out of the bin versus a household that wastes at the national average.</>
            : <>You're currently {inr(Math.abs(av.value_inr || 0))} worse than the baseline for this window — the queue on your dashboard is where to claw it back.</>}
          </p>
        </div>
        <div className="impact-headline__side">
          <Metric label="CO₂e avoided" value={kg(av.co2e_kg || 0, 1)} />
          <Metric label="Water avoided" value={litres(av.water_l || 0)} />
          <Metric label="Meals saved" value={sum.meals_saved ?? 0} />
        </div>
      </section>

      <section className="card">
        <div className="section-head"><h3>Consumed vs. wasted</h3><Legend /></div>
        <TrendChart series={ts.series || []} />
        <p className="muted small" style={{ marginTop: 10 }}>
          Dotted line is your 7-day waste rate against the {Math.round((sum.baseline_waste_rate || 0.22) * 100)}% baseline.
          {ts.zero_waste_streak_days > 0 ? ` Current zero-waste streak: ${ts.zero_waste_streak_days} day${ts.zero_waste_streak_days === 1 ? "" : "s"}.` : ""}
        </p>
      </section>

      {eq.length > 0 && (
        <section className="card card--muted">
          <h3 className="card__title">What {kg(av.co2e_kg || 0, 1)} of avoided CO₂e looks like</h3>
          <div className="equiv">
            {eq.map((e) => (
              <div className="equiv__chip" key={e.key}>
                <span className="mono equiv__val">{e.value.toLocaleString()}</span>
                <span className="equiv__label">{e.unit} {e.label}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid-2">
        <section className="card">
          <h3 className="card__title">Where the money leaks</h3>
          {foodRows.length ? <RankBars rows={foodRows} color="var(--warm-high)" format={inr} /> : <p className="muted">No waste recorded in this window — nothing leaking.</p>}
        </section>
        <section className="card">
          <h3 className="card__title">Why food gets wasted</h3>
          <Donut slices={reasonSlices} />
        </section>
      </div>

      <section className="ledger ledger--tight">
        <SmallStat label="Eaten" value={kg(consumed.kg || 0)} tone="fresh" />
        <SmallStat label="Rescued at-risk" value={kg(rescued.kg || 0)} tone="fresh" />
        <SmallStat label="Wasted" value={kg(wasted.kg || 0)} tone="warm" />
        <SmallStat label="Waste rate" value={`${Math.round((sum.waste_rate || 0) * 100)}%`} tone={sum.waste_rate <= sum.baseline_waste_rate ? "fresh" : "warm"} />
      </section>

      <details className="method">
        <summary>How this is calculated</summary>
        <p>{sum.baseline_basis}</p>
        {sum.sources?.length > 0 && (
          <ul className="sources">{sum.sources.map((s, i) => <li key={i}>{s.title ? `${s.title}${s.publisher ? ` — ${s.publisher}` : ""}${s.year ? ` (${s.year})` : ""}` : String(s)}</li>)}</ul>
        )}
      </details>
    </div>
  );
}

function Metric({ label, value }) { return <div className="impact-metric"><span className="mono">{value}</span><label>{label}</label></div>; }
function SmallStat({ label, value, tone }) { return <div className={`stat stat--${tone} stat--sm`}><div className="stat__body"><div className="stat__value mono">{value}</div><div className="stat__label">{label}</div></div></div>; }
function Legend() {
  return (
    <div className="legend">
      <span><i style={{ background: "var(--fresh-deep)" }} /> eaten</span>
      <span><i style={{ background: "var(--hot)" }} /> wasted</span>
      <span><i style={{ background: "var(--warm-high)" }} /> 7-day rate</span>
    </div>
  );
}

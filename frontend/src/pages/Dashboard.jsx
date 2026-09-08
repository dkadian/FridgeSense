import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useToast } from "../components/Toast.jsx";
import { Loader, EmptyState, RiskDial, FreshnessGauge, BandChip } from "../components/ui.jsx";
import ItemRow from "../components/ItemRow.jsx";
import ItemDetailModal from "../components/ItemDetailModal.jsx";
import Icon from "../components/Icons.jsx";
import { inr, kg, grams } from "../lib/format.js";
import { band } from "../lib/risk.js";

// The home screen answers one question fast: "what should I eat tonight?"
// Everything below the hero is context for that decision.
export default function Dashboard({ ctx }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [impact, setImpact] = useState(null);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [ef, sum] = await Promise.all([api.eatFirst(8), api.impactSummary(30)]);
      setData(ef); setImpact(sum);
      const bc = ef.summary?.band_counts || {};
      ctx?.setCriticalCount?.((bc.critical || 0) + (bc.high || 0));
    } catch (e) { setErr(e.detail || "Couldn't load your kitchen."); }
  }, [ctx]);

  useEffect(() => { load(); }, [load]);

  async function quickResolve(item, status) {
    setBusyId(item.item_id);
    try {
      await api.resolveItem(item.item_id, { status, waste_reason: status === "wasted" ? "forgot_about_it" : "" });
      toast.ok(status === "consumed" ? `${item.name} — logged as eaten.` : `${item.name} — logged as wasted.`);
      await load();
    } catch (e) { toast.err(e.detail || "Couldn't save that."); }
    finally { setBusyId(null); }
  }

  async function calibrateStaple(item_id, payload, itemName) {
    setBusyId(item_id);
    try {
      if (payload.action === "mark_finished") {
        await api.resolveItem(item_id, { status: "consumed", waste_reason: "" });
        toast.ok(`${itemName} logged as finished!`);
      } else {
        await api.calibrateHorizon(item_id, payload);
        toast.ok(`Calibrated ${itemName} horizon.`);
      }
      await load();
    } catch (e) {
      toast.err(e.detail || "Couldn't update stock.");
    } finally {
      setBusyId(null);
    }
  }

  if (err) return <EmptyState icon="warn" title="Something went sideways" body={err} action={<button className="btn" onClick={load}>Try again</button>} />;
  if (!data || !impact) return <Loader label="Reading your fridge…" />;

  const items = data.items || [];
  const hero = items[0];
  const rest = items.slice(1);
  const sum = data.summary || {};
  const avoided = impact.avoided_vs_baseline || {};
  const rescued = impact.rescued || {};

  return (
    <div className="stack" style={{ gap: "var(--sp-6)" }}>
      {hero ? (
        <section className={`hero ${band(hero).cls}`}>
          <div className="hero__rail" />
          <div className="hero__dial"><RiskDial item={hero} big /></div>
          <div className="hero__main">
            <div className="eyebrow">Eat me first</div>
            <h2 className="hero__name">{hero.name}</h2>
            <div className="hero__meta mono">{grams(hero.grams_remaining)} · in the {hero.storage}{hero.opened ? " · opened" : ""}</div>
            <div style={{ maxWidth: 460, margin: "10px 0 4px" }}><FreshnessGauge item={hero} /></div>
            {hero.reasons?.[0]?.text && <p className="hero__reason">{hero.reasons[0].text}</p>}
            <div className="hero__actions">
              <button className="btn btn--primary" disabled={busyId === hero.item_id} onClick={() => quickResolve(hero, "consumed")}>
                <Icon.check width={17} height={17} /> I ate this
              </button>
              <Link className="btn" to="/recipes"><Icon.recipe width={17} height={17} /> Cook something with it</Link>
              <button className="btn btn--ghost" onClick={() => setOpen(hero)}>Details</button>
            </div>
          </div>
        </section>
      ) : (
        <EmptyState icon="check" title="Nothing's about to spoil" body="Your fridge is in good shape. Add items or import a receipt to keep it that way." action={<Link className="btn btn--primary" to="/add">Add items</Link>} />
      )}

      {sum.staples_near_empty?.length > 0 && (
        <section className="horizon-banner">
          <div className="horizon-banner__header">
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="horizon-banner__badge">⚡ ZERO-EFFORT STAPLE HORIZON</span>
              <span className="small muted">Auto-paced based on daily household cooking</span>
            </div>
            <Link to="/pantry" className="small link">View all in pantry</Link>
          </div>
          <div className="horizon-banner__list">
            {sum.staples_near_empty.slice(0, 3).map((st) => (
              <div key={st.item_id} className="horizon-banner__row">
                <span className="horizon-banner__icon">{st.predictive_horizon?.icon || "🧺"}</span>
                <div className="horizon-banner__desc">
                  <div style={{ fontWeight: 600, color: "var(--ink)" }}>
                    <strong>{st.name}</strong> is predicted to run out {st.predictive_horizon?.days_remaining <= 0.5 ? "today" : "tomorrow"}
                  </div>
                  <div className="small muted">
                    Bought {st.predictive_horizon?.days_elapsed}d ago · ~{Math.round(st.grams_remaining)}g left (~{st.predictive_horizon?.daily_burn_g}g/day burn)
                  </div>
                </div>
                <div className="horizon-banner__actions">
                  <button
                    className="btn btn--xs btn--primary"
                    disabled={busyId === st.item_id}
                    onClick={() => calibrateStaple(st.item_id, { action: "mark_finished" }, st.name)}
                  >
                    ✓ Finished
                  </button>
                  <button
                    className="btn btn--xs btn--subtle"
                    disabled={busyId === st.item_id}
                    onClick={() => calibrateStaple(st.item_id, { action: "adjust_days", days_delta: 2 }, st.name)}
                  >
                    +2 days left
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="ledger">
        <Stat icon="coin" label="Saved this month" value={inr(avoided.value_inr ?? 0)}
          sub="vs. the 22% waste baseline" tone={avoided.beats_baseline ? "fresh" : "warm"} />
        <Stat icon="plate" label="Rescued" value={kg(rescued.kg ?? 0)}
          sub="eaten while flagged at-risk" tone="fresh" />
        <Stat icon="drop" label="CO₂e avoided" value={kg(avoided.co2e_kg ?? 0, 1)}
          sub="vs. baseline, perishables" tone={avoided.beats_baseline ? "fresh" : "warm"} />
        <Stat icon="fire" label="At risk right now" value={inr(sum.expected_loss_inr ?? 0)}
          sub={`${sum.items_at_risk ?? items.length} item${(sum.items_at_risk ?? items.length) === 1 ? "" : "s"} on the clock`} tone="warm" />
      </section>

      {rest.length > 0 && (
        <section>
          <div className="section-head">
            <h3>Next on the clock</h3>
            <Link className="link" to="/pantry">See full pantry <Icon.arrowRight width={14} height={14} /></Link>
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {rest.map((it, i) => (
              <ItemRow key={it.item_id} item={it} rank={i + 2}
                busy={busyId === it.item_id}
                onOpen={setOpen}
                onAte={(x) => quickResolve(x, "consumed")}
                onWasted={(x) => quickResolve(x, "wasted")} />
            ))}
          </div>
        </section>
      )}

      {open && <ItemDetailModal item={open} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  );
}

function Stat({ icon, label, value, sub, tone }) {
  const I = Icon[icon] || Icon.info;
  return (
    <div className={`stat stat--${tone}`}>
      <div className="stat__icon"><I width={20} height={20} /></div>
      <div className="stat__body">
        <div className="stat__value mono">{value}</div>
        <div className="stat__label">{label}</div>
        <div className="stat__sub">{sub}</div>
      </div>
    </div>
  );
}

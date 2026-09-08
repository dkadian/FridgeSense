import { useState, useEffect } from "react";
import { api } from "../lib/api.js";
import { useToast } from "./Toast.jsx";
import { Modal, RiskDial, FreshnessGauge } from "./ui.jsx";
import { band } from "../lib/risk.js";
import { grams, shortDate, inr, kg, daysToText, addedAgoText } from "../lib/format.js";
import Icon from "./Icons.jsx";

const REASONS = [
  ["forgot_about_it", "Forgot about it"],
  ["expired", "Passed its date"],
  ["cooked_too_much", "Cooked too much"],
  ["bought_too_much", "Bought too much"],
  ["spoiled_early", "Spoiled early"],
  ["did_not_like", "Didn't like it"],
  ["stored_wrong", "Stored it wrong"],
  ["other", "Something else"],
];

const CONTAINERS = [
  { id: "default", label: "📦 Original Pack", short: "Original" },
  { id: "airtight", label: "🫙 Airtight Container", short: "Airtight" },
  { id: "steel_dabba", label: "🍱 Steel Dabba", short: "Steel Dabba" },
  { id: "polythene", label: "🛍️ Plastic / Polybag", short: "Polythene" },
  { id: "paper_mesh", label: "🧺 Paper / Mesh Bag", short: "Paper/Mesh" },
  { id: "open", label: "🥣 Open / Uncovered", short: "Open" },
];

export default function ItemDetailModal({ item: initialItem, onClose, onChanged }) {
  const toast = useToast();
  const [item, setItem] = useState(initialItem);
  const [updatingStorage, setUpdatingStorage] = useState(false);
  const b = band(item);
  const [tab, setTab] = useState("why");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("consumed");
  const [gramsVal, setGramsVal] = useState(Math.round(initialItem.grams_remaining));
  const [reason, setReason] = useState("forgot_about_it");

  useEffect(() => {
    setItem(initialItem);
    setGramsVal(Math.round(initialItem.grams_remaining));
  }, [initialItem]);

  async function handleStorageUpdate(updates) {
    if (updatingStorage || busy) return;
    setUpdatingStorage(true);
    try {
      const updated = await api.updateItem(item.item_id, updates);
      setItem(updated);
      if (updates.storage) {
        toast.ok(`Moved ${item.name} to ${updates.storage}. Shelf life recalculated!`);
      } else if (updates.container) {
        toast.ok(`Container updated to ${updated.container_label || updates.container}.`);
      } else if (updates.is_covered !== undefined) {
        toast.ok(updates.is_covered ? "Marked as covered with lid." : "Marked as uncovered.");
      }
      onChanged?.();
    } catch (e) {
      toast.err(e.detail || "Couldn't update storage details.");
    } finally {
      setUpdatingStorage(false);
    }
  }

  const [calibrating, setCalibrating] = useState(false);

  async function handleHorizonCalibrate(action, options = {}) {
    if (calibrating || busy) return;
    setCalibrating(true);
    try {
      if (action === "mark_finished") {
        await api.resolveItem(item.item_id, { status: "consumed", waste_reason: "" });
        toast.ok(`${item.name} logged as finished!`);
        onChanged?.();
        onClose?.();
        return;
      }
      const updated = await api.calibrateHorizon(item.item_id, { action, ...options });
      setItem(updated);
      toast.ok(`Calibrated ${item.name}: ~${updated.predictive_horizon?.days_remaining || 0}d left!`);
      onChanged?.();
    } catch (e) {
      toast.err(e.detail || "Couldn't calibrate stock horizon.");
    } finally {
      setCalibrating(false);
    }
  }

  async function resolve() {
    setBusy(true);
    try {
      await api.resolveItem(item.item_id, {
        status,
        grams: Number(gramsVal) || undefined,
        waste_reason: status === "wasted" ? reason : "",
      });
      toast.ok(status === "consumed" ? "Logged as eaten. Nice." : status === "donated" ? "Logged as donated." : "Logged as wasted — we'll learn from it.");
      onChanged?.(); onClose();
    } catch (e) { toast.err(e.detail || "Couldn't save that."); setBusy(false); }
  }

  async function remove() {
    if (!confirm(`Remove ${item.name}? This just corrects a mistaken entry — it won't count as waste.`)) return;
    setBusy(true);
    try { await api.deleteItem(item.item_id); toast.ok("Removed."); onChanged?.(); onClose(); }
    catch (e) { toast.err(e.detail || "Couldn't remove it."); setBusy(false); }
  }

  const reasons = item.reasons || [];
  const actions = item.actions || [];

  return (
    <Modal title={item.name} onClose={onClose} wide
      footer={
        tab === "log" ? (
          <>
            <button className="btn btn--ghost" onClick={() => setTab("why")} disabled={busy}>Back</button>
            <button
              className={`btn ${status === "wasted" ? "btn--danger" : "btn--primary"}`}
              onClick={resolve}
              disabled={busy}
            >
              {busy ? "Saving…" : status === "consumed" ? "Log as Eaten" : status === "donated" ? "Log as Donated" : "Log as Wasted"}
            </button>
          </>
        ) : (
          <>
            <button className="btn btn--ghost btn--danger" onClick={remove} disabled={busy}>
              <Icon.trash width={16} height={16} /> Remove item
            </button>
            <button className="btn btn--primary" onClick={onClose}>
              <Icon.check width={16} height={16} /> Done
            </button>
          </>
        )
      }>
      <div className="detail">
        <div className="detail__head">
          <RiskDial item={item} />
          <div style={{ flex: 1 }}>
            <div className="detail__meta mono">
              {grams(item.grams_remaining)} · in the {item.storage}{item.opened ? " · opened" : ""}
            </div>
            <div style={{ margin: "6px 0 10px" }}><FreshnessGauge item={item} /></div>
            <dl className="kv">
              <dt>Added to pantry</dt>
              <dd>
                {shortDate(item.purchase_date || item.created_at)} ·{" "}
                <span className="muted">{addedAgoText(item.purchase_date || item.created_at, item.days_since_purchase)}</span>
              </dd>
              <dt>Use by</dt><dd>{shortDate(item.expiry_date)} · {daysToText(item.days_to_expiry)}</dd>
              <dt>Value at risk</dt><dd>{inr(item.at_risk_value_inr)}</dd>
              <dt>Carbon at risk</dt><dd>{kg(item.at_risk_co2e_kg, 2)} CO₂e</dd>
            </dl>
          </div>
        </div>

        {/* Storage & Packaging Co-Pilot */}
        <div className="storage-switcher" style={{
          marginTop: "16px",
          padding: "14px 16px",
          background: "var(--frost-2)",
          border: "1px solid var(--line)",
          borderRadius: "var(--r-md)",
          display: "flex",
          flexDirection: "column",
          gap: "10px"
        }}>
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--ink)" }}>
              Storage & Packaging Co-Pilot
            </span>
            <span className="mono small" style={{ color: updatingStorage ? "var(--muted)" : "var(--fresh-deep)" }}>
              {updatingStorage ? "Calculating shelf life…" : "✓ Changes saved automatically"}
            </span>
          </div>

          {/* 1. Storage Location */}
          <div>
            <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-soft)", fontWeight: 600, marginBottom: 4 }}>
              Storage Location
            </div>
            <div className="seg" style={{ width: "100%" }}>
              {[
                { id: "pantry", label: "🧺 Pantry / Shelf" },
                { id: "fridge", label: "❄️ Refrigerator" },
                { id: "freezer", label: "🧊 Freezer" },
              ].map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={item.storage === s.id ? "is-on" : ""}
                  disabled={updatingStorage || busy}
                  onClick={() => handleStorageUpdate({ storage: s.id })}
                  style={{ flex: 1 }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* 2. Container / Packaging Type */}
          <div>
            <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--ink-soft)", fontWeight: 600, marginBottom: 4 }}>
              Container / Packaging Type
            </div>
            <div className="seg" style={{ width: "100%", display: "flex", flexWrap: "wrap", gap: "4px" }}>
              {CONTAINERS.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={(item.container || "default") === c.id ? "is-on" : ""}
                  disabled={updatingStorage || busy}
                  onClick={() => handleStorageUpdate({ container: c.id })}
                  style={{ flex: "1 1 30%", minWidth: "115px", fontSize: "0.76rem", padding: "5px 8px" }}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          {/* 3. Covered and Opened Toggles */}
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, paddingTop: "2px" }}>
            {(item.container || "default") !== "open" && (
              <label style={{ fontSize: "0.8rem", color: "var(--ink-soft)", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={item.is_covered !== false}
                  disabled={updatingStorage || busy}
                  onChange={(e) => handleStorageUpdate({ is_covered: e.target.checked })}
                />
                <span>Lid on / Covered with lid or plate</span>
              </label>
            )}
            <label style={{ fontSize: "0.8rem", color: "var(--ink-soft)", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={Boolean(item.opened)}
                disabled={updatingStorage || busy}
                onChange={(e) => handleStorageUpdate({ opened: e.target.checked })}
              />
              <span>Pack already opened</span>
            </label>
          </div>

          {/* 4. Real-Time Scientific Packaging Co-Pilot Insight */}
          {item.packaging_insight && (
            <div
              className={`copilot-card ${
                item.packaging_insight.tone === "positive"
                  ? "copilot-card--info"
                  : item.packaging_insight.tone === "negative"
                  ? "copilot-card--alert"
                  : ""
              }`}
              style={{ margin: 0, padding: "10px 12px", borderRadius: "var(--r-sm)" }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <strong style={{ fontSize: "0.82rem" }}>
                  {item.packaging_insight.tone === "positive" ? "✨ Freshness Boost" : item.packaging_insight.tone === "negative" ? "⚠️ Packaging Alert" : "ℹ️ Storage Note"}
                </strong>
                <span className="copilot-badge" style={{ fontSize: "0.72rem" }}>
                  {item.packaging_insight.badge_text}
                </span>
              </div>
              <p style={{ margin: 0, fontSize: "0.82rem", lineHeight: 1.4 }}>
                {item.packaging_insight.advice}
              </p>
            </div>
          )}
        </div>

        {/* Zero-Effort Predictive Stock Horizon */}
        {item.predictive_horizon && (
          <div className="horizon-panel">
            <div className="horizon-panel__head">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="horizon-panel__icon">{item.predictive_horizon.icon}</span>
                <div>
                  <div style={{ fontWeight: 700, fontSize: "0.92rem", color: "var(--ink)" }}>
                    Zero-Effort Stock Horizon
                  </div>
                  <div className="small muted">
                    {item.predictive_horizon.portion_desc} · Household of {item.predictive_horizon.household_size}
                  </div>
                </div>
              </div>
              <span className={`horizon-chip horizon-chip--${item.predictive_horizon.status_tier}`}>
                {item.predictive_horizon.status_label}
              </span>
            </div>

            {/* Visual Horizon Meter */}
            <div className="horizon-meter">
              <div className="horizon-meter__track">
                <div
                  className={`horizon-meter__fill horizon-meter__fill--${item.predictive_horizon.status_tier}`}
                  style={{ width: `${item.predictive_horizon.percent_remaining}%` }}
                />
              </div>
              <div className="horizon-meter__labels">
                <span>Day {item.predictive_horizon.days_elapsed} of ~{Math.round(item.predictive_horizon.total_stock_days)}</span>
                <strong>{item.predictive_horizon.percent_remaining}% remaining (~{Math.round(item.predictive_horizon.effective_remaining_g)}g)</strong>
              </div>
            </div>

            {/* Key Metrics */}
            <div className="horizon-grid">
              <div className="horizon-metric">
                <label>Daily Burn</label>
                <span>~{item.predictive_horizon.daily_burn_g}g / day</span>
              </div>
              <div className="horizon-metric">
                <label>Stock Duration</label>
                <span>~{item.predictive_horizon.days_remaining} days left</span>
              </div>
              <div className="horizon-metric">
                <label>Expected Run-Out</label>
                <span>{shortDate(item.predictive_horizon.projected_empty_date)}</span>
              </div>
            </div>

            {/* Calibration Bar */}
            <div className="horizon-actions">
              <span className="horizon-actions__label">Quick Calibrate (Optional):</span>
              <div className="horizon-actions__btns">
                <button
                  type="button"
                  className="btn btn--xs btn--subtle"
                  disabled={calibrating}
                  onClick={() => handleHorizonCalibrate("adjust_days", { days_delta: -1 })}
                  title="Reduce stock by 1 day"
                >
                  -1 Day
                </button>
                <button
                  type="button"
                  className="btn btn--xs btn--subtle"
                  disabled={calibrating}
                  onClick={() => handleHorizonCalibrate("adjust_days", { days_delta: 1 })}
                  title="Add 1 day of buffer"
                >
                  +1 Day
                </button>
                <button
                  type="button"
                  className="btn btn--xs btn--subtle"
                  disabled={calibrating}
                  onClick={() => handleHorizonCalibrate("set_days", { days: 2 })}
                  title="Calibrate to ~2 days left"
                >
                  Set ~2 days
                </button>
                <button
                  type="button"
                  className="btn btn--xs btn--danger"
                  disabled={calibrating}
                  onClick={() => handleHorizonCalibrate("mark_finished")}
                  style={{ marginLeft: "auto" }}
                >
                  ✓ Mark Finished
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="seg" style={{ margin: "18px 0 12px" }}>
          <button className={tab === "why" ? "is-on" : ""} onClick={() => setTab("why")}>Why this score</button>
          <button className={tab === "do" ? "is-on" : ""} onClick={() => setTab("do")}>What to do</button>
          <button className={tab === "log" ? "is-on" : ""} onClick={() => setTab("log")}>Log outcome</button>
        </div>

        {tab === "why" && (
          reasons.length ? <ul className="reasons-list">{reasons.map((r, i) => (
            <li key={i} className={`reason reason--${r.direction === "reduces" ? "down" : "up"}`}>
              {r.direction === "reduces" ? <Icon.leaf width={16} height={16} /> : <Icon.warn width={16} height={16} />}
              <span>{r.text}</span>
            </li>))}</ul>
            : <p className="muted">This item is comfortably within its life — nothing notable driving the score.</p>
        )}
        {tab === "do" && (
          actions.length ? <ul className="actions-list">{actions.map((a, i) => <li key={i}><Icon.arrowRight width={16} height={16} />{a}</li>)}</ul>
            : <p className="muted">No action needed right now.</p>
        )}
        {tab === "log" && (
          <div className="stack" style={{ gap: 14 }}>
            <div className="seg">
              {[["consumed", "Ate it"], ["wasted", "Wasted it"], ["donated", "Donated it"]].map(([v, l]) => (
                <button key={v} className={status === v ? "is-on" : ""} onClick={() => setStatus(v)}>{l}</button>
              ))}
            </div>
            <div className="field">
              <label className="field__label" htmlFor="g">Grams {status === "consumed" ? "eaten" : status === "donated" ? "donated" : "wasted"}</label>
              <input id="g" className="input" type="number" min={0} max={100000} value={gramsVal} onChange={(e) => setGramsVal(e.target.value)} />
              <span className="field__hint">Defaults to everything left ({grams(item.grams_remaining)}).</span>
            </div>
            {status === "wasted" && (
              <div className="field">
                <label className="field__label" htmlFor="r">What happened?</label>
                <select id="r" className="select" value={reason} onChange={(e) => setReason(e.target.value)}>
                  {REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <span className="field__hint">Honest reasons make the habit insights useful.</span>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

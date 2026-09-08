import Icon from "./Icons.jsx";
import { band, riskPct, gaugePositionPct } from "../lib/risk.js";

export function Loader({ label = "Loading" }) {
  return (<div style={{ textAlign: "center", padding: "24px" }}><div className="spinner" /><p className="muted">{label}…</p></div>);
}

export function EmptyState({ icon = "box", title, body, children, action }) {
  const I = Icon[icon] || Icon.box;
  const text = body ?? children;
  return (
    <div className="empty">
      <I className="empty__icon" width={46} height={46} />
      <h3>{title}</h3>
      {text && <p style={{ maxWidth: "44ch", margin: "0 auto" }}>{text}</p>}
      {action && <div style={{ marginTop: 18 }}>{action}</div>}
    </div>
  );
}

export function Banner({ tone = "info", kind, icon, title, body, children }) {
  const t = kind || tone;
  const I = Icon[icon] || (t === "warn" ? Icon.warn : t === "ok" ? Icon.check : Icon.info);
  return (
    <div className={`banner banner--${t}`}>
      <I width={18} height={18} />
      <div>
        {title && <strong className="banner__title">{title}</strong>}
        {body && <div className="banner__body">{body}</div>}
        {children}
      </div>
    </div>
  );
}

export function BandChip({ item, showPct = true }) {
  const b = band(item);
  return (
    <span className={`chip chip--band ${b.cls}`}>
      <span className="chip__dot" />
      {b.label}{showPct ? ` · ${riskPct(item)}%` : ""}
    </span>
  );
}

// The signature freshness gauge: a cold->hot track showing spoilage progress.
// 0% points to fresh (cool teal), 100% points to spoiling (hot crimson).
export function FreshnessGauge({ item, showScale = true }) {
  const pos = gaugePositionPct(item);
  return (
    <div className="gauge" aria-hidden="true">
      <div className="gauge__track"><div className="gauge__mask" style={{ left: `${pos}%` }} /></div>
      {showScale && (
        <div className="gauge__scale"><span>fresh</span><span>spoiling</span></div>
      )}
    </div>
  );
}

// Radial dial for the hero - stroke ramps with the score.
export function RiskDial({ item, big = false }) {
  const b = band(item);
  const p = riskPct(item);
  const r = 54, c = 2 * Math.PI * r;
  const dash = (p / 100) * c;
  return (
    <div className={`dial ${big ? "dial--big" : ""}`} role="img" aria-label={`Spoilage risk ${p} percent, ${b.label}`}>
      <svg width="128" height="128">
        <circle cx="64" cy="64" r={r} fill="none" stroke="var(--line)" strokeWidth="12" />
        <circle cx="64" cy="64" r={r} fill="none" stroke={b.color} strokeWidth="12"
          strokeLinecap="round" strokeDasharray={`${dash} ${c}`} />
      </svg>
      <div className="dial__val">
        <div className="dial__num" style={{ color: b.color }}>{p}<span style={{ fontSize: "1rem" }}>%</span></div>
        <div className="dial__lbl">{b.label}</div>
      </div>
    </div>
  );
}

import { useEffect } from "react";

export function Modal({ title, onClose, children, footer, wide = false }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [onClose]);
  return (
    <div className="modal-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal ${wide ? "modal--wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal__head">
          <h3>{title}</h3>
          <button className="btn btn--ghost btn--sm" onClick={onClose} aria-label="Close"><Icon.x width={18} height={18} /></button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__foot">{footer}</div>}
      </div>
    </div>
  );
}

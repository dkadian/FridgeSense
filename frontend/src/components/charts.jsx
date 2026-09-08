// Hand-rolled SVG charts - no charting dependency, so they stay verifiable
// offline and match the cold-chain palette exactly. All are responsive via
// viewBox and preserveAspectRatio.

// Dual trend: wasted grams (warm) vs consumed grams (cool) over time, with a
// 7-day waste-rate line. `series` items: {date, wasted_g, consumed_g, waste_rate_7d}.
export function TrendChart({ series, height = 220 }) {
  const W = 720, H = height, pad = { t: 16, r: 44, b: 26, l: 44 };
  if (!series || series.length === 0) return <p className="muted">No activity in this window.</p>;
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const n = series.length;
  const maxG = Math.max(1, ...series.map((d) => Math.max(d.consumed_g || 0, d.wasted_g || 0)));
  const x = (i) => pad.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const yG = (g) => pad.t + ih - (g / maxG) * ih;
  const yR = (r) => pad.t + ih - Math.min(1, r || 0) * ih;

  const area = (key, y0) => {
    const top = series.map((d, i) => `${i === 0 ? "M" : "L"}${x(i)},${yG(d[key] || 0)}`).join(" ");
    return `${top} L${x(n - 1)},${y0} L${x(0)},${y0} Z`;
  };
  const line = (key, y) => series.map((d, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(d[key])}`).join(" ");
  const base = pad.t + ih;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const labelEvery = Math.ceil(n / 6);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Waste and consumption over time" style={{ display: "block" }}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={pad.l + iw} y1={yR(t)} y2={yR(t)} stroke="var(--line)" strokeDasharray="2 4" />
          <text x={pad.l + iw + 6} y={yR(t) + 3} className="mono" fontSize="9" fill="var(--muted)">{Math.round(t * 100)}%</text>
        </g>
      ))}
      <defs>
        <linearGradient id="gConsumed" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--fresh)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--fresh)" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id="gWasted" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--hot)" stopOpacity="0.30" />
          <stop offset="100%" stopColor="var(--hot)" stopOpacity="0.03" />
        </linearGradient>
      </defs>
      <path d={area("consumed_g", base)} fill="url(#gConsumed)" />
      <path d={line("consumed_g", yG)} fill="none" stroke="var(--fresh-deep)" strokeWidth="1.6" />
      <path d={area("wasted_g", base)} fill="url(#gWasted)" />
      <path d={line("wasted_g", yG)} fill="none" stroke="var(--hot)" strokeWidth="1.6" />
      <path d={line("waste_rate_7d", yR)} fill="none" stroke="var(--warm-high)" strokeWidth="2.2" strokeDasharray="1 5" strokeLinecap="round" />
      {series.map((d, i) => (i % labelEvery === 0 || i === n - 1) ? (
        <text key={i} x={x(i)} y={H - 8} className="mono" fontSize="9" fill="var(--muted)" textAnchor="middle">
          {(d.date || "").slice(5)}
        </text>
      ) : null)}
    </svg>
  );
}

// Horizontal ranked bars. rows: [{label, value, sub}]. `color` is a CSS var.
export function RankBars({ rows, color = "var(--warm-high)", format = (v) => v, max }) {
  if (!rows || rows.length === 0) return <p className="muted">Nothing to show yet.</p>;
  const top = max || Math.max(1, ...rows.map((r) => r.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {rows.map((r, i) => (
        <div key={i}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginBottom: 4 }}>
            <span style={{ fontWeight: 500 }}>{r.label}</span>
            <span className="mono" style={{ color: "var(--ink-soft)" }}>{format(r.value)}{r.sub ? <span className="muted"> · {r.sub}</span> : null}</span>
          </div>
          <div style={{ height: 9, background: "var(--frost-2)", borderRadius: 999, overflow: "hidden" }}>
            <div style={{ width: `${Math.max(2, (r.value / top) * 100)}%`, height: "100%", background: color, borderRadius: 999, transition: "width 0.6s cubic-bezier(0.22,1,0.36,1)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

// Donut for the waste-reason split. slices: [{label, value, color}].
export function Donut({ slices, size = 168, thickness = 26 }) {
  const total = slices.reduce((s, x) => s + (x.value || 0), 0);
  if (total <= 0) return <p className="muted">No waste recorded — nothing to split.</p>;
  const r = (size - thickness) / 2, c = 2 * Math.PI * r, cx = size / 2;
  let offset = 0;
  return (
    <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Waste by reason">
        <g transform={`rotate(-90 ${cx} ${cx})`}>
          {slices.map((s, i) => {
            const len = (s.value / total) * c;
            const el = (<circle key={i} cx={cx} cy={cx} r={r} fill="none" stroke={s.color} strokeWidth={thickness}
              strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} />);
            offset += len;
            return el;
          })}
        </g>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {slices.map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 9, fontSize: "0.88rem" }}>
            <span style={{ width: 11, height: 11, borderRadius: 3, background: s.color, flex: "none" }} />
            <span style={{ fontWeight: 500 }}>{s.label}</span>
            <span className="mono muted">{Math.round((s.value / total) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

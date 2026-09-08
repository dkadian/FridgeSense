import { band, riskPct } from "../lib/risk.js";
import { daysToText, grams, shortDate, addedAgoText } from "../lib/format.js";
import { FreshnessGauge } from "./ui.jsx";
import Icon from "./Icons.jsx";

// One pantry item as a row. Rail + gauge are coloured by the model's band, so
// the row reads as "how urgent" before you read a single word.
export default function ItemRow({ item, rank, onOpen, onAte, onWasted, busy }) {
  const b = band(item);
  const topReason = item.reasons?.[0]?.text;
  return (
    <div className={`item ${b.cls}`}>
      <div className="item__rail" />
      <div className="item__body">
        <div className="item__top">
          {rank != null && <span className="rank">{String(rank).padStart(2, "0")}</span>}
          <button className="item__name" onClick={() => onOpen?.(item)} style={{ background: "none", textAlign: "left" }}>
            {item.name}
          </button>
          <span className={`chip chip--band ${b.cls}`}><span className="chip__dot" />{b.label} · {riskPct(item)}%</span>
          {item.opened && <span className="chip">opened</span>}
          {item.predictive_horizon && (
            <span
              className={`horizon-chip horizon-chip--${item.predictive_horizon.status_tier}`}
              onClick={(e) => { e.stopPropagation(); onOpen?.(item); }}
              title={`Zero-Effort Auto-Pace: ~${item.predictive_horizon.daily_burn_g}g/day for household of ${item.predictive_horizon.household_size}`}
            >
              <span className="horizon-chip__icon">{item.predictive_horizon.icon}</span>
              <span>~{item.predictive_horizon.days_remaining}d left ({item.predictive_horizon.percent_remaining}%)</span>
            </span>
          )}
        </div>
        <div className="item__sub">
          <span className="mono">{grams(item.grams_remaining)}</span> in the{" "}
          <button
            type="button"
            className="item__storage-badge"
            onClick={(e) => {
              e.stopPropagation();
              onOpen?.(item);
            }}
            title="Click to edit or change storage location"
          >
            {item.storage === "fridge" ? "❄️ fridge" : item.storage === "freezer" ? "🧊 freezer" : "🧺 pantry"}
          </button>
          {item.container && item.container !== "default" && (
            <>
              {" · "}
              <span className="chip" style={{ fontSize: "0.68rem", padding: "1px 6px" }}>
                {item.container === "airtight" ? "🫙 airtight" :
                 item.container === "steel_dabba" ? "🍱 steel dabba" :
                 item.container === "polythene" ? "🛍️ polybag" :
                 item.container === "paper_mesh" ? "🧺 paper/mesh" : "🥣 open"}
              </span>
            </>
          )}
          {item.is_covered === false && item.container !== "open" && (
            <>
              {" · "}
              <span className="chip" style={{ fontSize: "0.68rem", padding: "1px 6px", color: "#b45309" }}>
                uncovered
              </span>
            </>
          )}
          {" · "}
          <span className="mono muted" title={`Added on ${shortDate(item.purchase_date || item.created_at)}`}>
            {item.predictive_horizon
              ? `Day ${item.predictive_horizon.days_elapsed} of ~${Math.round(item.predictive_horizon.total_stock_days)}`
              : addedAgoText(item.purchase_date || item.created_at, item.days_since_purchase)}
          </span>
          {" · "}<span className="mono">{daysToText(item.days_to_expiry)}</span>
          {item.expiry_date ? <span className="muted"> · use by {shortDate(item.expiry_date)}</span> : null}
        </div>
        {topReason && <div className="item__reason">{topReason}</div>}
      </div>
      <div className="item__right">
        <div style={{ width: 150 }}><FreshnessGauge item={item} showScale={false} /></div>
        <div className="item__actions">
          <button className="btn btn--sm" disabled={busy} onClick={() => onAte?.(item)} title="Mark fully eaten"><Icon.check width={15} height={15} /> Ate it</button>
          <button className="btn btn--sm btn--danger" disabled={busy} onClick={() => onWasted?.(item)} title="Log as wasted"><Icon.trash width={15} height={15} /></button>
        </div>
      </div>
    </div>
  );
}

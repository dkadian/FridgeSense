import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { Loader, EmptyState, Banner } from "../components/ui.jsx";
import Icon from "../components/Icons.jsx";
import { inr, kg } from "../lib/format.js";

const TYPE_ICON = { hotspot: "fire", repeat: "refresh", timing: "clock", storage: "snow", winning: "leaf", default: "insight" };

export default function Insights() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try { setData(await api.insights(90)); }
    catch (e) { setErr(e.detail || "Couldn't load insights."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (err) return <EmptyState icon="warn" title="Couldn't load insights" body={err} action={<button className="btn" onClick={load}>Try again</button>} />;
  if (!data) return <Loader label="Looking for patterns…" />;

  const insights = [...(data.insights || [])].sort((a, b) => (b.severity || 0) - (a.severity || 0));
  const suff = data.data_sufficiency || {};

  return (
    <div className="stack" style={{ gap: "var(--sp-5)" }}>
      {!suff.enough_for_confidence && (
        <Banner tone="info" icon="info" title="Early days" body={suff.note || "Log more items to sharpen these patterns."} />
      )}

      {insights.length === 0 ? (
        <EmptyState icon="insight" title="No clear patterns yet"
          body="Once you've resolved a couple of weeks of items, habit insights will show up here — the categories, foods and reasons behind your waste."
          action={<Link className="btn btn--primary" to="/pantry">Go to pantry</Link>} />
      ) : (
        <>
          <p className="muted">{insights.length} pattern{insights.length === 1 ? "" : "s"} from the last {data.window_days} days, most important first.</p>
          <div className="insights">
            {insights.map((ins) => {
              const I = Icon[TYPE_ICON[ins.type] || TYPE_ICON.default] || Icon.insight;
              return (
                <article key={ins.id} className={`insight sev-${ins.severity || 1}`}>
                  <div className="insight__icon"><I width={20} height={20} /></div>
                  <div className="insight__body">
                    <h3 className="insight__title">{ins.title}</h3>
                    <p className="insight__detail">{ins.detail}</p>
                    {ins.action && <div className="insight__action"><Icon.arrowRight width={15} height={15} /> {ins.action}</div>}
                    {(ins.monthly_inr > 0 || ins.monthly_co2e_kg > 0) && (
                      <div className="insight__figures mono">
                        {ins.monthly_inr > 0 && <span>~{inr(ins.monthly_inr)}/mo</span>}
                        {ins.monthly_co2e_kg > 0 && <span>~{kg(ins.monthly_co2e_kg, 1)} CO₂e/mo</span>}
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>

          {data.figures_overlap && (
            <p className="muted small footnote"><Icon.info width={13} height={13} /> {data.overlap_note}</p>
          )}
        </>
      )}
    </div>
  );
}

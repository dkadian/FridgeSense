import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useToast } from "../components/Toast.jsx";
import { Loader, EmptyState } from "../components/ui.jsx";
import ItemRow from "../components/ItemRow.jsx";
import ItemDetailModal from "../components/ItemDetailModal.jsx";
import Icon from "../components/Icons.jsx";
import { inr, kg } from "../lib/format.js";

const BANDS = [
  ["all", "Everything"],
  ["critical", "Critical"],
  ["high", "High"],
  ["medium", "Medium"],
  ["low", "Low"],
];
const SORTS = [
  ["risk", "Most urgent"],
  ["expiry", "Expiring soonest"],
  ["added_new", "Recently added"],
  ["added_old", "Oldest added"],
  ["value", "Most valuable"],
  ["name", "A–Z"],
];

export default function Pantry({ ctx }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [band, setBand] = useState("all");
  const [sort, setSort] = useState("risk");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setErr(null);
    try {
      const res = await api.pantry();
      setData(res);
      const bc = res.summary?.band_counts || {};
      ctx?.setCriticalCount?.((bc.critical || 0) + (bc.high || 0));
    } catch (e) { setErr(e.detail || "Couldn't load your pantry."); }
  }, [ctx]);

  useEffect(() => { load(); }, [load]);

  async function quickResolve(item, status) {
    setBusyId(item.item_id);
    try {
      await api.resolveItem(item.item_id, { status, waste_reason: status === "wasted" ? "forgot_about_it" : "" });
      toast.ok(status === "consumed" ? `${item.name} — eaten.` : `${item.name} — logged as wasted.`);
      await load();
    } catch (e) { toast.err(e.detail || "Couldn't save that."); }
    finally { setBusyId(null); }
  }

  const view = useMemo(() => {
    if (!data) return [];
    let rows = [...(data.items || [])];
    if (band !== "all") rows = rows.filter((r) => r.risk_band === band);
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      rows = rows.filter((r) =>
        r.name.toLowerCase().includes(needle) ||
        (r.category || "").toLowerCase().includes(needle) ||
        (r.storage || "").toLowerCase().includes(needle)
      );
    }
    const cmp = {
      risk: (a, b) => b.risk - a.risk || a.days_to_expiry - b.days_to_expiry,
      expiry: (a, b) => a.days_to_expiry - b.days_to_expiry,
      added_new: (a, b) => new Date(b.purchase_date || b.created_at || 0) - new Date(a.purchase_date || a.created_at || 0) || b.item_id - a.item_id,
      added_old: (a, b) => new Date(a.purchase_date || a.created_at || 0) - new Date(b.purchase_date || b.created_at || 0) || a.item_id - b.item_id,
      value: (a, b) => b.embodied_value_inr - a.embodied_value_inr,
      name: (a, b) => a.name.localeCompare(b.name),
    }[sort];
    return rows.sort(cmp);
  }, [data, band, sort, q]);

  if (err) return <EmptyState icon="warn" title="Couldn't load your pantry" body={err} action={<button className="btn" onClick={load}>Try again</button>} />;
  if (!data) return <Loader label="Scoring your pantry…" />;

  const s = data.summary || {};
  const bc = s.band_counts || {};
  const empty = (data.items || []).length === 0;

  return (
    <div className="stack" style={{ gap: "var(--sp-5)" }}>
      <div className="pantry-strip">
        <div><span className="mono big">{s.items_active ?? 0}</span><label>active items</label></div>
        <div><span className="mono big">{inr(s.pantry_value_inr ?? 0)}</span><label>on the shelves</label></div>
        <div><span className="mono big warm">{inr(s.expected_loss_inr ?? 0)}</span><label>expected loss</label></div>
        <div><span className="mono big">{kg(s.expected_loss_kg ?? 0)}</span><label>expected loss (mass)</label></div>
      </div>

      {empty ? (
        <EmptyState icon="fridge" title="Your pantry is empty" body="Add items by hand or paste a grocery receipt to get started."
          action={<Link className="btn btn--primary" to="/add"><Icon.add width={16} height={16} /> Add items</Link>} />
      ) : (
        <>
          <div className="toolbar">
            <div className="seg">
              {BANDS.map(([v, l]) => (
                <button key={v} className={band === v ? "is-on" : ""} onClick={() => setBand(v)}>
                  {l}{v !== "all" && bc[v] != null ? <span className="seg__count">{bc[v]}</span> : null}
                </button>
              ))}
            </div>
            <div className="toolbar__right">
              <div className="search">
                <Icon.info width={0} height={0} style={{ display: "none" }} />
                <input className="input" placeholder="Search items…" value={q} onChange={(e) => setQ(e.target.value)} />
              </div>
              <select className="select" value={sort} onChange={(e) => setSort(e.target.value)}>
                {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <Link className="btn btn--primary" to="/add"><Icon.add width={16} height={16} /> Add</Link>
            </div>
          </div>

          {view.length === 0 ? (
            <EmptyState icon="check" title="Nothing matches" body="No items in this band or search. Try a different filter." />
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              {view.map((it) => (
                <ItemRow key={it.item_id} item={it}
                  busy={busyId === it.item_id}
                  onOpen={setOpen}
                  onAte={(x) => quickResolve(x, "consumed")}
                  onWasted={(x) => quickResolve(x, "wasted")} />
              ))}
            </div>
          )}
        </>
      )}

      {open && <ItemDetailModal item={open} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  );
}

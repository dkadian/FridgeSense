import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { useToast } from "../components/Toast.jsx";
import { Loader, EmptyState, Banner } from "../components/ui.jsx";
import Icon from "../components/Icons.jsx";
import ItemDetailModal from "../components/ItemDetailModal.jsx";
import { inr, grams as g, titleCase } from "../lib/format.js";
import { QUICK_CATEGORIES, QUICK_ADD_STAPLES } from "../lib/quickStaples.js";

const SAMPLE = `SPINACH 250G       35.00
PANEER 200G        90.00
FULL CREAM MILK 1L 68.00
ATTA 5KG          255.00
TOMATO 1KG         40.00
CURD 400G          45.00
BANANA 1 DOZEN     60.00
CORIANDER BUNCH     15.00`;

export default function AddImport({ ctx }) {
  const [mode, setMode] = useState("manual");
  return (
    <div className="stack" style={{ gap: "var(--sp-5)" }}>
      <div className="seg seg--lg">
        <button className={mode === "manual" ? "is-on" : ""} onClick={() => setMode("manual")}>
          <Icon.add width={16} height={16} /> Add by hand
        </button>
        <button className={mode === "scratchpad" ? "is-on" : ""} onClick={() => setMode("scratchpad")}>
          <Icon.sparkles width={16} height={16} /> Quick Text / WhatsApp
        </button>
        <button className={mode === "receipt" ? "is-on" : ""} onClick={() => setMode("receipt")}>
          <Icon.receipt width={16} height={16} /> Paste a receipt
        </button>
      </div>
      {mode === "manual" && <ManualAdd />}
      {mode === "scratchpad" && <TextScratchpad />}
      {mode === "receipt" && <ReceiptImport />}
    </div>
  );
}




/* ------------------------------------------------------------------ manual */
function ManualAdd() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [picked, setPicked] = useState(null);
  const [unit, setUnit] = useState("grams");
  const [amount, setAmount] = useState(250);
  const [storage, setStorage] = useState("fridge");
  const [container, setContainer] = useState("default");
  const [isCovered, setIsCovered] = useState(true);
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState([]);
  const [activePantry, setActivePantry] = useState([]);
  const [openDetailItem, setOpenDetailItem] = useState(null);
  const [quickCat, setQuickCat] = useState("all");
  const [addingStapleId, setAddingStapleId] = useState(null);
  const [stapleCounts, setStapleCounts] = useState({});
  const timer = useRef(null);
  const formRef = useRef(null);

  useEffect(() => {
    api.pantry().then((r) => setActivePantry(r.items || [])).catch(() => {});
  }, []);

  // Storage Co-Pilot: Ethylene Gas Conflict & Recommendation Engine
  const copilotInsight = useMemo(() => {
    if (!picked) return null;
    const isProducer = picked.ethylene_type === "producer";
    const isSensitive = picked.ethylene_type === "sensitive";
    const antagonists = picked.ethylene_antagonists || [];
    const storageMismatch = picked.recommended_storage && picked.recommended_storage !== storage;

    const colocated = activePantry.filter((item) => item.storage === storage);
    let conflicts = [];

    if (isSensitive) {
      conflicts = colocated.filter((item) => antagonists.includes(item.food_id));
    } else if (isProducer) {
      conflicts = colocated.filter((item) => {
        const itemAntagonists = item.ethylene_antagonists || [];
        return itemAntagonists.includes(picked.id) ||
               (item.category === "leafy_greens" && (picked.id === "apple" || picked.id === "banana" || picked.id === "tomato")) ||
               (item.food_id === "potato" && picked.id === "onion");
      });
    }

    return {
      isProducer,
      isSensitive,
      tip: picked.ethylene_tip,
      conflicts,
      storageMismatch,
      recommended: picked.recommended_storage,
    };
  }, [picked, storage, activePantry]);

  useEffect(() => {
    clearTimeout(timer.current);
    if (!q.trim() || picked) {
      setResults([]);
      return;
    }
    timer.current = setTimeout(async () => {
      try {
        const r = await api.foods(q, 8);
        setResults(r.foods || []);
      } catch {
        setResults([]);
      }
    }, 160);
    return () => clearTimeout(timer.current);
  }, [q, picked]);

  function choose(food) {
    setPicked(food);
    setQ(food.name);
    setStorage(food.recommended_storage || food.storage_default || "fridge");
    setUnit(food.unit && food.unit !== "g" ? "count" : "grams");
    setAmount(food.unit && food.unit !== "g" ? 1 : Math.max(50, Math.round(food.grams_per_unit || 250)));
    setResults([]);
  }

  function handleInputChange(e) {
    const val = e.target.value;
    setQ(val);
    if (picked && val !== picked.name) {
      setPicked(null);
    }
  }

  async function submit(e) {
    if (e) e.preventDefault();
    const query = q.trim();
    if (!picked && !query) {
      toast.err("Please enter or search for a food item.");
      return;
    }
    setBusy(true);
    try {
      const foodId = picked ? picked.id : (results[0]?.id || query);
      const displayName = picked ? picked.name : query;
      const payload = { food_id: foodId, storage, container, is_covered: isCovered, opened };
      if (displayName !== foodId) {
        payload.display_name = displayName;
      }
      if (unit === "count") payload.count = Number(amount);
      else payload.grams = Number(amount);

      const res = await api.addItem(payload);
      toast.ok(`Added ${res.name || displayName} to your pantry.`);
      setAdded((a) => [{ id: res.item_id, item: res, name: res.name || displayName, grams: res.grams_remaining, storage: res.storage, container: res.container }, ...a].slice(0, 8));
      setActivePantry((p) => [res, ...p]);
      setPicked(null);
      setQ("");
      setResults([]);
      setAmount(250);
      setContainer("default");
      setIsCovered(true);
    } catch (err) {
      toast.err(err.detail || "Couldn't add that item.");
    } finally {
      setBusy(false);
    }
  }

  async function handleQuickAdd(staple) {
    if (addingStapleId || busy) return;
    setAddingStapleId(staple.id);
    try {
      const payload = {
        food_id: staple.id,
        display_name: staple.name,
        storage: staple.storage,
        container: staple.container,
        is_covered: true,
        opened: false,
      };
      if (staple.unit === "count") {
        payload.count = staple.amount;
      } else {
        payload.grams = staple.grams;
      }

      const res = await api.addItem(payload);
      toast.ok(`Added ${staple.icon} ${staple.name} (${staple.label}) to ${staple.storage}!`);
      setStapleCounts((prev) => ({
        ...prev,
        [staple.id]: (prev[staple.id] || 0) + 1,
      }));
      setAdded((a) => [
        {
          id: res.item_id,
          item: res,
          name: res.name || staple.name,
          grams: res.grams_remaining,
          storage: res.storage,
          container: res.container,
        },
        ...a,
      ].slice(0, 10));
      setActivePantry((p) => [res, ...p]);
    } catch (err) {
      toast.err(err.detail || `Couldn't add ${staple.name}.`);
    } finally {
      setAddingStapleId(null);
    }
  }

  function handleQuickPrefill(staple) {
    setQ(staple.name);
    setStorage(staple.storage);
    setContainer(staple.container);
    setUnit(staple.unit === "count" ? "count" : "grams");
    setAmount(staple.amount);
    setIsCovered(true);
    setOpened(false);
    api.foods(staple.id, 1).then((r) => {
      if (r.foods?.length > 0) {
        setPicked(r.foods[0]);
      }
    }).catch(() => {});
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const filteredStaples = useMemo(() => {
    if (quickCat === "all") return QUICK_ADD_STAPLES;
    return QUICK_ADD_STAPLES.filter((s) => s.group === quickCat);
  }, [quickCat]);

  return (
    <div className="stack" style={{ gap: "var(--sp-5)" }}>
      {/* 1-Tap Quick Add Section */}
      <section className="card quick-add-card">
        <div className="quick-add-card__head">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: "1.4rem", lineHeight: 1 }}>⚡</span>
            <div>
              <h3 style={{ margin: 0, fontSize: "1.08rem", fontWeight: 700, color: "var(--ink)" }}>
                1-Tap Quick Add
              </h3>
              <p className="muted small" style={{ margin: 0 }}>
                Common Indian kitchen essentials with authentic quantities & storage — 1 tap to add
              </p>
            </div>
          </div>
          <div className="seg quick-add-cat-seg">
            {QUICK_CATEGORIES.map((c) => (
              <button
                key={c.id}
                type="button"
                className={quickCat === c.id ? "is-on" : ""}
                onClick={() => setQuickCat(c.id)}
              >
                <span>{c.icon}</span> <span>{c.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="quick-pills-grid">
          {filteredStaples.map((st) => {
            const count = stapleCounts[st.id] || 0;
            const isAdding = addingStapleId === st.id;
            return (
              <div key={st.id} className={`quick-pill ${count > 0 ? "is-added" : ""}`}>
                <div
                  className="quick-pill__body"
                  onClick={() => handleQuickAdd(st)}
                  title={`1-tap add ${st.name} to ${st.storage}`}
                >
                  <span className="quick-pill__icon">{st.icon}</span>
                  <div className="quick-pill__info">
                    <div className="quick-pill__title">
                      <strong>{st.name}</strong>{" "}
                      <span className="quick-pill__hi">({st.name_hi})</span>
                    </div>
                    <div className="quick-pill__meta">
                      <span className="mono">{st.label}</span> · <span>{st.storage_icon} {st.storage}</span>
                    </div>
                  </div>
                </div>
                <div className="quick-pill__actions">
                  <button
                    type="button"
                    className="quick-pill__btn-add"
                    disabled={isAdding}
                    onClick={() => handleQuickAdd(st)}
                    title={`1-tap add ${st.name} to ${st.storage}`}
                  >
                    {isAdding ? "…" : count > 0 ? `✓ +${count}` : "+ Add"}
                  </button>
                  <button
                    type="button"
                    className="quick-pill__btn-edit"
                    onClick={() => handleQuickPrefill(st)}
                    title="Customize quantity or storage before adding"
                  >
                    ✏️
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid-2" ref={formRef}>
        <section className="card">
          <h3 className="card__title">Add an item by hand</h3>
        <form onSubmit={submit} className="stack" style={{ gap: 16 }}>
          <div className="field" style={{ position: "relative" }}>
            <label className="field__label">Food item</label>
            <input
              className="input"
              placeholder="e.g. spinach, paneer, atta, milk…"
              value={q}
              onChange={handleInputChange}
              onKeyDown={(e) => {
                if (e.key === "Enter" && results.length > 0 && !picked) {
                  e.preventDefault();
                  choose(results[0]);
                }
              }}
            />
            {results.length > 0 && !picked && (
              <ul className="menu">
                {results.map((f) => (
                  <li key={f.id}>
                    <button type="button" onClick={() => choose(f)}>
                      <span>{f.name}</span>
                      <span className="muted mono small">{f.category_label}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <span className="field__hint">
              {picked ? `Selected from catalog: ${picked.name}` : "Type a food name or pick from catalog suggestions."}
            </span>
          </div>

          <div className="field">
            <label className="field__label">Quantity</label>
            <div className="inline">
              <input
                className="input"
                type="number"
                min={1}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
              <div className="seg">
                <button type="button" className={unit === "grams" ? "is-on" : ""} onClick={() => setUnit("grams")}>grams</button>
                {picked && picked.unit && picked.unit !== "g" && (
                  <button type="button" className={unit === "count" ? "is-on" : ""} onClick={() => setUnit("count")}>
                    {picked.unit}{picked.grams_per_unit ? ` (${g(picked.grams_per_unit)})` : ""}
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="field">
            <label className="field__label">Where's it stored?</label>
            <div className="seg">
              {["pantry", "fridge", "freezer"].map((s) => (
                <button type="button" key={s} className={storage === s ? "is-on" : ""} onClick={() => setStorage(s)}>
                  {titleCase(s)}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label className="field__label">Container & Packaging</label>
            <div className="seg" style={{ flexWrap: "wrap", gap: "4px" }}>
              {[
                { id: "default", label: "📦 Original Pack" },
                { id: "airtight", label: "🫙 Airtight" },
                { id: "steel_dabba", label: "🍱 Steel Dabba" },
                { id: "polythene", label: "🛍️ Polybag" },
                { id: "paper_mesh", label: "🧺 Paper/Mesh" },
                { id: "open", label: "🥣 Open Plate" },
              ].map((c) => (
                <button
                  type="button"
                  key={c.id}
                  className={container === c.id ? "is-on" : ""}
                  onClick={() => setContainer(c.id)}
                  style={{ flex: "1 1 28%", minWidth: "90px", fontSize: "0.76rem", padding: "4px 8px" }}
                >
                  {c.label}
                </button>
              ))}
            </div>
            {container !== "open" && (
              <label style={{ fontSize: "0.78rem", color: "var(--ink-soft)", display: "flex", alignItems: "center", gap: 6, marginTop: 6, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={isCovered}
                  onChange={(e) => setIsCovered(e.target.checked)}
                />
                <span>Lid on / Covered</span>
              </label>
            )}

            {/* Storage Co-Pilot: Ethylene & Co-location Insights */}
            {copilotInsight && (
              <div
                className={`copilot-card ${
                  copilotInsight.conflicts.length > 0
                    ? "copilot-card--alert"
                    : "copilot-card--info"
                }`}
                style={{ marginTop: "var(--sp-2)" }}
              >
                <div className="copilot-card__header">
                  <span>
                    {copilotInsight.conflicts.length > 0
                      ? "⚠️ Storage Co-Pilot Alert: Ethylene Conflict"
                      : copilotInsight.isProducer
                      ? "🌬️ Storage Co-Pilot: Ethylene Producer"
                      : copilotInsight.isSensitive
                      ? "🥦 Storage Co-Pilot: Ethylene Sensitive"
                      : "💡 Storage Co-Pilot Tip"}
                  </span>
                </div>
                <div className="copilot-card__body">
                  {copilotInsight.conflicts.length > 0 ? (
                    <p className="copilot-card__desc">
                      <strong>Caution:</strong> Storing <strong>{picked.name}</strong> in the {storage} alongside active{" "}
                      <strong>{copilotInsight.conflicts.map((c) => c.name).join(", ")}</strong> will accelerate spoilage.{" "}
                      {copilotInsight.isSensitive
                        ? `Ethylene gas from ${copilotInsight.conflicts[0].name} accelerates rotting and yellowing of ${picked.name}.`
                        : `Ethylene gas from ${picked.name} causes nearby sensitive greens and vegetables to rot twice as fast.`}{" "}
                      <em>Action: Keep in a sealed container or separate drawer.</em>
                    </p>
                  ) : (
                    <p className="copilot-card__desc">
                      {copilotInsight.tip || `${picked.name} keeps best in the ${picked.recommended_storage || storage}.`}
                    </p>
                  )}

                  {copilotInsight.storageMismatch && (
                    <div className="copilot-card__subnote">
                      📍 Recommended: <strong>{picked.name}</strong> naturally keeps longest in the{" "}
                      <strong>{copilotInsight.recommended}</strong> (better than {storage}).
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          <label className="check">
            <input type="checkbox" checked={opened} onChange={(e) => setOpened(e.target.checked)} />
            Already opened
          </label>

          <button type="submit" className="btn btn--primary" disabled={busy || (!q.trim() && !picked)}>
            {busy ? "Adding…" : "Add to pantry"}
          </button>
        </form>
      </section>

      <section className="card card--muted">
        <h3 className="card__title">Just added</h3>
        {added.length === 0 ? (
          <p className="muted">Items you add will appear here, then show up scored on your dashboard.</p>
        ) : (
          <ul className="added-list">
            {added.map((a) => (
              <li key={a.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <div>
                  <Icon.check width={16} height={16} /> {a.name}{" "}
                  <span className="muted mono">{g(a.grams)}</span>
                  {a.storage && (
                    <>
                      {" · "}
                      <span className="chip" style={{ fontSize: "0.7rem", padding: "1px 6px" }}>
                        {a.storage === "fridge" ? "❄️ fridge" : a.storage === "freezer" ? "🧊 freezer" : "🧺 pantry"}
                      </span>
                    </>
                  )}
                  {a.container && a.container !== "default" && (
                    <>
                      {" · "}
                      <span className="chip" style={{ fontSize: "0.7rem", padding: "1px 6px" }}>
                        {a.container === "airtight" ? "🫙 airtight" :
                         a.container === "steel_dabba" ? "🍱 steel dabba" :
                         a.container === "polythene" ? "🛍️ polybag" :
                         a.container === "paper_mesh" ? "🧺 paper/mesh" : "🥣 open"}
                      </span>
                    </>
                  )}
                </div>
                <button
                  type="button"
                  className="btn btn--sm btn--ghost"
                  onClick={() => setOpenDetailItem(a.item || a)}
                  style={{ padding: "2px 8px", fontSize: "0.75rem" }}
                  title="Change storage location or edit details"
                >
                  Edit
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {openDetailItem && (
        <ItemDetailModal
          item={openDetailItem}
          onClose={() => setOpenDetailItem(null)}
          onChanged={() => {
            api.pantry().then((r) => setActivePantry(r.items || [])).catch(() => {});
          }}
        />
      )}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- receipt */
function ReceiptImport() {
  const toast = useToast();
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState(null);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);

  async function parse() {
    setBusy(true);
    try {
      const res = await api.parseReceipt(text);
      setParsed(res);
      setRows((res.items || []).map((it) => ({ ...it, include: !it.needs_review || true })));
    } catch (e) { toast.err(e.detail || "Couldn't read that receipt."); }
    finally { setBusy(false); }
  }

  function edit(i, patch) { setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row))); }

  async function confirm() {
    const chosen = rows.filter((r) => r.include).map((r) => ({
      food_id: r.food_id, grams: Number(r.grams), storage: r.storage,
      purchase_date: r.purchase_date, expiry_date: r.expiry_date,
    }));
    if (!chosen.length) { toast.err("Tick at least one row to import."); return; }
    setBusy(true);
    try {
      const res = await api.confirmReceipt(chosen);
      toast.ok(`Added ${res.added_count} item${res.added_count === 1 ? "" : "s"} to your pantry.`);
      if (res.failed_count) toast.err(`${res.failed_count} row(s) couldn't be added.`);
      nav("/pantry");
    } catch (e) { toast.err(e.detail || "Couldn't save those items."); }
    finally { setBusy(false); }
  }

  if (!parsed) {
    return (
      <div className="grid-2">
        <section className="card">
          <h3 className="card__title">Paste your receipt</h3>
          <div className="field">
            <textarea className="input textarea" rows={12} placeholder="Paste the lines from a grocery receipt…" value={text} onChange={(e) => setText(e.target.value)} />
            <span className="field__hint">Plain text — one item per line. The parser matches names to the catalog and estimates weights.</span>
          </div>
          <div className="inline">
            <button className="btn btn--primary" disabled={busy || !text.trim()} onClick={parse}>{busy ? "Reading…" : "Read receipt"}</button>
            <button className="btn btn--ghost" onClick={() => setText(SAMPLE)}>Use a sample</button>
          </div>
        </section>
        <section className="card card--muted">
          <h3 className="card__title">How it works</h3>
          <p className="muted">Nothing is saved until you confirm. We read each line, match it to a known food, and estimate the weight from the quantity. You review and correct everything on the next screen — rows we're unsure about are flagged.</p>
        </section>
      </div>
    );
  }

  const st = parsed.stats || {};
  return (
    <div className="stack" style={{ gap: "var(--sp-4)" }}>
      <Banner tone={st.needs_review ? "warn" : "ok"} icon={st.needs_review ? "warn" : "check"}
        title={`Matched ${st.matched} of ${st.matched + st.unmatched} lines`}
        body={st.needs_review ? `${st.needs_review} row(s) need a quick check before importing.` : "Everything matched with high confidence. Review and confirm."} />

      <div className="review">
        <table className="table review__table">
          <thead><tr><th></th><th>Item</th><th>Grams</th><th>Storage</th><th>Value</th><th></th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={r.needs_review ? "row--review" : ""}>
                <td><input type="checkbox" checked={r.include} onChange={(e) => edit(i, { include: e.target.checked })} /></td>
                <td>
                  <div className="cell-name">{r.name}</div>
                  <div className="muted mono cell-sub">{r.cleaned}{r.quantity_assumed ? " · weight assumed" : ""}</div>
                  {r.needs_review && r.alternatives?.length > 0 && (
                    <select className="select select--sm" value={r.food_id}
                      onChange={(e) => { const alt = r.alternatives.find((a) => a.food_id === e.target.value); edit(i, { food_id: e.target.value, name: alt ? alt.name : r.name }); }}>
                      <option value={r.food_id}>{r.name} (matched)</option>
                      {r.alternatives.map((a) => <option key={a.food_id} value={a.food_id}>{a.name}</option>)}
                    </select>
                  )}
                </td>
                <td><input className="input input--sm" type="number" min={1} value={Math.round(r.grams)} onChange={(e) => edit(i, { grams: e.target.value })} /></td>
                <td>
                  <select className="select select--sm" value={r.storage} onChange={(e) => edit(i, { storage: e.target.value })}>
                    {["pantry", "fridge", "freezer"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
                  </select>
                </td>
                <td className="mono">{inr(r.value_inr)}</td>
                <td><span className={`dot ${r.needs_review ? "dot--warn" : "dot--ok"}`} title={r.review_reason || "high confidence"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {parsed.unmatched?.length > 0 && (
        <p className="muted small">Couldn't match: {parsed.unmatched.map((u) => u.cleaned || u.text).join(", ")}. Add those by hand if you need them.</p>
      )}

      <div className="inline">
        <button className="btn btn--primary" disabled={busy} onClick={confirm}>{busy ? "Saving…" : `Import ${rows.filter((r) => r.include).length} item(s)`}</button>
        <button className="btn btn--ghost" onClick={() => { setParsed(null); setRows([]); }}>Start over</button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- scratchpad */
function TextScratchpad({ initialText, onClearInitialText }) {
  const toast = useToast();
  const nav = useNavigate();
  const [text, setText] = useState(initialText || "");
  const [parsed, setParsed] = useState(null);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (initialText) {
      setText(initialText);
      onClearInitialText?.();
    }
  }, [initialText, onClearInitialText]);

  const SAMPLES = [
    { label: "🥔 Perishables & Paneer", text: "1 kg aloo, aadha kilo tamatar, do gaddi palak, 200g paneer" },
    { label: "🥛 Daily Dairy & Eggs", text: "2 packet doodh, 1 dozen ande, 100g adrak, 500g dahi" },
    { label: "🥦 Veggies & Chillies", text: "ek pav hari mirch, 1 phool gobi, 250g matar, 500g gajar" },
  ];

  async function parse() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const res = await api.parseScratchpad(text);
      if (!res.items || res.items.length === 0) {
        toast.err("Could not recognize any grocery items. Try simpler names like '1kg aloo, 500g tamatar'.");
        return;
      }
      setParsed(res);
      setRows(
        (res.items || []).map((it) => ({
          ...it,
          include: true,
          container: it.container || "default",
        }))
      );
    } catch (e) {
      toast.err(e.detail || "Couldn't parse that grocery text.");
    } finally {
      setBusy(false);
    }
  }

  function edit(i, patch) {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }

  function remove(i) {
    setRows((r) => r.filter((_, idx) => idx !== i));
  }

  function toggleAll(checked) {
    setRows((r) => r.map((row) => ({ ...row, include: checked })));
  }

  async function confirm() {
    const chosen = rows
      .filter((r) => r.include)
      .map((r) => ({
        food_id: r.food_id,
        grams: Number(r.grams),
        storage: r.storage,
        container: r.container || "default",
        is_covered: true,
        purchase_date: r.purchase_date,
        expiry_date: r.expiry_date,
        display_name: r.name,
      }));

    if (!chosen.length) {
      toast.err("Tick at least one item to add to your pantry.");
      return;
    }

    setBusy(true);
    try {
      const res = await api.addBulk(chosen);
      toast.ok(`Added ${res.added_count} item${res.added_count === 1 ? "" : "s"} to your pantry!`);
      if (res.failed_count) {
        toast.err(`${res.failed_count} item(s) could not be saved.`);
      }
      nav("/pantry");
    } catch (e) {
      toast.err(e.detail || "Couldn't save those items to pantry.");
    } finally {
      setBusy(false);
    }
  }

  const allSelected = rows.length > 0 && rows.every((r) => r.include);

  if (!parsed) {
    return (
      <div className="grid-2">
        <section className="card">
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", marginBottom: "var(--sp-2)" }}>
            <span style={{ fontSize: "1.2rem" }}>📝</span>
            <h3 className="card__title" style={{ margin: 0 }}>Quick Text / WhatsApp Scratchpad</h3>
          </div>
          <p className="muted small" style={{ marginBottom: "var(--sp-3)" }}>
            Paste informal notes, WhatsApp grocery messages, or quick Hinglish lists.
          </p>

          <div style={{ marginBottom: "var(--sp-3)" }}>
            <span className="small muted" style={{ display: "block", marginBottom: 6 }}>Try an example note:</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {SAMPLES.map((s, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="btn btn--ghost"
                  style={{ fontSize: "0.78rem", padding: "4px 10px", borderRadius: "999px" }}
                  onClick={() => setText(s.text)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label className="field__label">Grocery Notes / WhatsApp Text</label>
            <textarea
              className="input textarea"
              rows={8}
              placeholder="Paste anything like:&#10;1 kg aloo, aadha kilo tamatar, do gaddi palak, 200g paneer&#10;Or list line-by-line:&#10;• 2 packet doodh&#10;• 1 dozen ande&#10;• ek pav hari mirch"
              value={text}
              onChange={(e) => setText(e.target.value)}
              style={{ fontFamily: "inherit", lineHeight: 1.5 }}
            />
            <span className="field__hint">
              Supports comma-separated or line-by-line lists. Recognizes Hinglish (aadha kilo, ek pav, gaddi, darjan, packet).
            </span>
          </div>

          <div className="inline" style={{ marginTop: "var(--sp-2)" }}>
            <button
              className="btn btn--primary"
              disabled={busy || !text.trim()}
              onClick={parse}
            >
              {busy ? "Parsing Groceries…" : "Parse Groceries"}
            </button>
            {text && (
              <button className="btn btn--ghost" onClick={() => setText("")}>
                Clear
              </button>
            )}
          </div>
        </section>

        <section className="card card--muted">
          <h3 className="card__title">How the Scratchpad Works</h3>
          <div className="stack" style={{ gap: "var(--sp-3)", marginTop: "var(--sp-2)" }}>
            <div style={{ display: "flex", gap: "var(--sp-2)" }}>
              <span style={{ fontSize: "1.1rem" }}>🇮🇳</span>
              <div>
                <strong>Colloquial Indian Unit Conversions</strong>
                <p className="muted small" style={{ margin: "2px 0 0" }}>
                  Automatically translates kitchen terms: <em>aadha kilo</em> (500g), <em>ek pav</em> (250g), <em>derh kilo</em> (1.5kg), <em>gaddi</em> (bunch), <em>darjan</em> (dozen).
                </p>
              </div>
            </div>

            <div style={{ display: "flex", gap: "var(--sp-2)" }}>
              <span style={{ fontSize: "1.1rem" }}>🥫</span>
              <div>
                <strong>Packaging & Storage Co-Pilot</strong>
                <p className="muted small" style={{ margin: "2px 0 0" }}>
                  Assigns optimal container preservation physics (Airtight for greens & paneer, Steel Dabba for dairy, Paper/Mesh for potatoes & onions).
                </p>
              </div>
            </div>

            <div style={{ display: "flex", gap: "var(--sp-2)" }}>
              <span style={{ fontSize: "1.1rem" }}>⚡</span>
              <div>
                <strong>1-Click Review & Pantry Sync</strong>
                <p className="muted small" style={{ margin: "2px 0 0" }}>
                  Preview all parsed items in an interactive table, adjust weights or containers if needed, and add them all with a single click.
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    );
  }

  const st = parsed.stats || {};
  const isAi = parsed.mode === "gemini_live";

  return (
    <div className="stack" style={{ gap: "var(--sp-4)" }}>
      <Banner
        tone="ok"
        icon="check"
        title={`Extracted ${rows.length} item${rows.length === 1 ? "" : "s"} from your note`}
        body={
          <span>
            {isAi ? "🤖 Powered by Google Gemini 2.5 Flash." : "⚡ Processed via Indian Colloquial Rules."}{" "}
            Total: <strong>{g(st.total_grams || 0)}</strong>
            {st.total_value_inr ? ` · Approx. ${inr(st.total_value_inr)}` : ""}
            {" · Review items below before adding to pantry."}
          </span>
        }
      />

      <div className="review">
        <table className="table review__table">
          <thead>
            <tr>
              <th style={{ width: 36 }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => toggleAll(e.target.checked)}
                  title="Select all / Deselect all"
                />
              </th>
              <th>Item</th>
              <th style={{ width: 110 }}>Grams</th>
              <th style={{ width: 110 }}>Storage</th>
              <th style={{ width: 160 }}>Container</th>
              <th>Source / Shelf-life</th>

              <th style={{ width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={r.include ? "" : "row--muted"}>
                <td>
                  <input
                    type="checkbox"
                    checked={r.include}
                    onChange={(e) => edit(i, { include: e.target.checked })}
                  />
                </td>
                <td>
                  <div className="cell-name">{r.name}</div>
                  <div className="muted mono cell-sub" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ textTransform: "capitalize" }}>{r.category.replace("_", " ")}</span>
                    <span>·</span>
                    <span>{r.raw}</span>
                  </div>
                </td>
                <td>
                  <input
                    className="input input--sm mono"
                    type="number"
                    min={1}
                    value={Math.round(r.grams)}
                    onChange={(e) => edit(i, { grams: Number(e.target.value) })}
                    style={{ width: "100%" }}
                  />
                </td>
                <td>
                  <select
                    className="select select--sm"
                    value={r.storage}
                    onChange={(e) => edit(i, { storage: e.target.value })}
                  >
                    {["fridge", "pantry", "freezer"].map((s) => (
                      <option key={s} value={s}>{titleCase(s)}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    className="select select--sm"
                    value={r.container || "default"}
                    onChange={(e) => edit(i, { container: e.target.value })}
                  >
                    <option value="default">📦 Original</option>
                    <option value="airtight">🫙 Airtight</option>
                    <option value="steel_dabba">🍱 Steel Dabba</option>
                    <option value="polythene">🛍️ Polybag</option>
                    <option value="paper_mesh">🧺 Paper/Mesh</option>
                    <option value="open">🥣 Open Plate</option>
                  </select>
                </td>
                <td>
                  <div className="small" style={{ color: "var(--ink-soft)" }}>
                    {r.grams_source}
                  </div>
                  <div className="muted small mono">
                    ~{r.shelf_life_days}d shelf life
                  </div>
                </td>
                <td>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => remove(i)}
                    title="Remove item"
                    style={{ padding: "4px 8px", color: "var(--hot)", fontSize: "0.85rem" }}
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {parsed.unmatched?.length > 0 && (
        <div style={{ background: "var(--warm-wash)", border: "1px solid var(--warm-med)", borderRadius: "var(--r-md)", padding: "var(--sp-3)" }}>
          <strong style={{ color: "var(--warm-high)", fontSize: "0.88rem" }}>⚠️ Unmatched lines ({parsed.unmatched.length}):</strong>
          <ul style={{ margin: "4px 0 0 16px", fontSize: "0.84rem", color: "var(--ink-soft)" }}>
            {parsed.unmatched.map((u, idx) => (
              <li key={idx}><code>{u.text || u.raw}</code> — {u.reason}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="inline" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <div className="inline">
          <button
            className="btn btn--primary"
            disabled={busy || rows.filter((r) => r.include).length === 0}
            onClick={confirm}
          >
            {busy
              ? "Adding to Pantry…"
              : `Add ${rows.filter((r) => r.include).length} Item${rows.filter((r) => r.include).length === 1 ? "" : "s"} to Pantry`}
          </button>
          <button
            className="btn btn--ghost"
            onClick={() => { setParsed(null); setRows([]); }}
          >
            Edit Note / Start Over
          </button>
        </div>

        <span className="muted small">
          Selected: {rows.filter((r) => r.include).length} of {rows.length}
        </span>
      </div>
    </div>
  );
}


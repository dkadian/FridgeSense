import { useEffect, useState, useMemo } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../lib/api.js";
import { useToast } from "../components/Toast.jsx";
import { Loader, EmptyState } from "../components/ui.jsx";
import Icon from "../components/Icons.jsx";
import { inr } from "../lib/format.js";

const FOOD_ICONS = {
  rice: "🍚",
  wheat_flour: "🌾",
  atta: "🌾",
  cooking_oil: "🫗",
  mustard_oil: "🫗",
  onion: "🧅",
  potato: "🥔",
  tomato: "🍅",
  garlic: "🧄",
  ginger: "🫚",
  green_chilli: "🌶️",
  milk: "🥛",
  curd: "🥣",
  paneer: "🧀",
  eggs: "🥚",
  bread: "🍞",
  banana: "🍌",
  spinach: "🥬",
  coriander: "🌿",
  fenugreek: "🌿",
  chicken: "🍗",
  mutton: "🥩",
  fish: "🐟",
  prawns: "🦐",
  poha: "🍚",
  apple: "🍎",
  orange: "🍊",
  grapes: "🍇",
  tea: "☕",
  sugar: "🧂",
  salt: "🧂",
  toor_dal: "🥣",
  moong_dal: "🥣",
  chana_dal: "🥣",
  cauliflower: "🥦",
  cabbage: "🥬",
  capsicum: "🫑",
  carrot: "🥕",
  cucumber: "🥒",
  brinjal: "🍆",
  okra: "🌱",
  bottle_gourd: "🥒",
  ridge_gourd: "🥒",
};

const HINDI_NAMES = {
  tomato: "Tamatar",
  potato: "Aloo",
  onion: "Pyaz",
  ginger: "Adrak",
  garlic: "Lehsun",
  green_chilli: "Hari Mirch",
  coriander: "Hara Dhania",
  spinach: "Palak",
  fenugreek: "Methi",
  milk: "Doodh",
  curd: "Dahi",
  paneer: "Paneer",
  butter: "Makkhan",
  ghee: "Ghee",
  eggs: "Ande",
  bread: "Bread",
  rice: "Chawal",
  wheat_flour: "Atta",
  atta: "Atta",
  cooking_oil: "Tel",
  mustard_oil: "Sarson Tel",
  tea: "Chai Patti",
  sugar: "Cheeni",
  toor_dal: "Arhar Dal",
  moong_dal: "Moong Dal",
  chana_dal: "Chana Dal",
  cauliflower: "Phool Gobi",
  cabbage: "Patta Gobi",
  capsicum: "Shimla Mirch",
  carrot: "Gajar",
  cucumber: "Kheera",
  brinjal: "Baingan",
  okra: "Bhindi",
  bottle_gourd: "Lauki",
  ridge_gourd: "Turai / Tori",
  banana: "Kela",
  apple: "Seb",
  orange: "Santra",
};

const CATEGORY_GROUPS = [
  { id: "produce", label: "🥦 Fresh Vegetables & Greens", cats: ["vegetables", "leafy_greens", "herbs"] },
  { id: "dairy_eggs", label: "🥛 Daily Dairy & Eggs", cats: ["dairy", "eggs"] },
  { id: "staples", label: "🌾 Flours, Grains & Pulses", cats: ["grains", "pulses"] },
  { id: "fruits", label: "🍎 Fresh Fruits", cats: ["fruits"] },
  { id: "oils_spices", label: "🫗 Oils, Spices & Condiments", cats: ["nuts_oils", "condiments", "beverages", "spices"] },
  { id: "meat_fish", label: "🍗 Meat & Poultry", cats: ["meat_fish"] },
  { id: "other", label: "🧺 Other Groceries", cats: [] },
];

export default function ShoppingList({ ctx }) {
  const toast = useToast();
  const nav = useNavigate();
  const [items, setItems] = useState(null);
  const [selected, setSelected] = useState({});
  const [quantities, setQuantities] = useState({});
  const [customItem, setCustomItem] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    loadList();
  }, []);

  async function loadList() {
    setErr(null);
    try {
      const res = await api.restockList();
      const list = res.items || [];
      setItems(list);
      ctx?.setRestockCount?.(list.length);

      let savedSel = {};
      try {
        savedSel = JSON.parse(localStorage.getItem("fridgesense.shopping_selected") || "{}");
      } catch (e) {}

      const sel = {};
      const qty = {};
      list.forEach((it) => {
        // Items are NOT force-checked by default so user is not pressured to buy everything.
        // If user already explicitly checked it previously or added it as a custom item, keep it checked.
        sel[it.food_id] = Boolean(savedSel[it.food_id] || it.is_custom);
        qty[it.food_id] = it.typical_grams || 500;
      });
      setSelected(sel);
      setQuantities(qty);
    } catch (e) {
      setErr(e.detail || "Couldn't load your shopping list.");
    }
  }

  function toggle(fid) {
    setSelected((prev) => {
      const next = { ...prev, [fid]: !prev[fid] };
      try {
        localStorage.setItem("fridgesense.shopping_selected", JSON.stringify(next));
      } catch (e) {}
      return next;
    });
  }

  function toggleAll(val) {
    if (!items) return;
    const next = {};
    items.forEach((it) => { next[it.food_id] = val; });
    setSelected(next);
    try {
      localStorage.setItem("fridgesense.shopping_selected", JSON.stringify(next));
    } catch (e) {}
  }

  function adjustQty(fid, delta) {
    setQuantities((prev) => {
      const cur = prev[fid] || 500;
      const next = Math.max(50, cur + delta);
      return { ...prev, [fid]: next };
    });
  }

  async function removeItem(fid, name) {
    // 1. Optimistic removal from UI state
    setItems((prev) => {
      const next = (prev || []).filter((it) => it.food_id !== fid);
      ctx?.setRestockCount?.(next.length);
      return next;
    });
    setSelected((prev) => {
      const next = { ...prev };
      delete next[fid];
      try {
        localStorage.setItem("fridgesense.shopping_selected", JSON.stringify(next));
      } catch (e) {}
      return next;
    });

    // 2. Persist deletion/dismissal to server so it never reappears on page refresh or switch
    try {
      await api.dismissRestockItem(fid);
      toast.ok(`Removed ${name || "item"} from shopping list.`);
    } catch (e) {
      console.error("Failed to dismiss restock item", e);
    }
  }

  async function handleClearAll() {
    if (!items || !items.length) return;
    if (!confirm("Clear all items from your shopping list? You can always add items back anytime.")) return;
    setItems([]);
    setSelected({});
    try {
      localStorage.removeItem("fridgesense.shopping_selected");
    } catch (e) {}
    ctx?.setRestockCount?.(0);
    try {
      await api.clearRestockList();
      toast.ok("Shopping list cleared.");
    } catch (e) {
      console.error("Failed to clear restock list", e);
    }
  }

  async function addCustom(e) {
    if (e) e.preventDefault();
    const name = customItem.trim();
    if (!name) return;
    setCustomItem("");

    try {
      const created = await api.addCustomShoppingItem({ name, grams: 500, unit: "g" });
      const newItem = {
        food_id: created.food_id,
        name: created.name,
        category: created.category || "other",
        typical_grams: created.typical_grams || 500,
        unit: created.unit || "g",
        is_staple: false,
        estimated_cost_inr: 50,
        is_custom: true,
      };
      setItems((prev) => {
        const next = [newItem, ...(prev || [])];
        ctx?.setRestockCount?.(next.length);
        return next;
      });
      setSelected((prev) => {
        const next = { ...prev, [newItem.food_id]: true };
        try {
          localStorage.setItem("fridgesense.shopping_selected", JSON.stringify(next));
        } catch (e) {}
        return next;
      });
      setQuantities((prev) => ({ ...prev, [newItem.food_id]: 500 }));
      toast.ok(`Added "${name}" to shopping list.`);
    } catch (e) {
      toast.err("Couldn't add item to shopping list.");
    }
  }

  // Selected items list
  const selectedItems = useMemo(() => {
    if (!items) return [];
    return items.filter((it) => selected[it.food_id]);
  }, [items, selected]);

  const allSelected = items && items.length > 0 && selectedItems.length === items.length;

  const totalCost = useMemo(() => {
    return selectedItems.reduce((sum, it) => {
      const qty = quantities[it.food_id] || it.typical_grams || 500;
      const baseCost = it.estimated_cost_inr || 40;
      const baseQty = it.typical_grams || 500;
      const cost = (qty / baseQty) * baseCost;
      return sum + cost;
    }, 0);
  }, [selectedItems, quantities]);

  // 1-Click Restock
  async function handleRestock() {
    if (!selectedItems.length) {
      toast.err("Tick at least one item to restock.");
      return;
    }
    setBusy(true);
    try {
      const payload = selectedItems.map((it) => ({
        food_id: it.food_id,
        name: it.name,
        typical_grams: quantities[it.food_id] || it.typical_grams,
        storage: it.storage,
        container: it.container || "default",
      }));
      const res = await api.restock(payload);
      toast.ok(`✓ Restocked ${res.added_count} items into your pantry!`);
      nav("/pantry");
    } catch (e) {
      toast.err(e.detail || "Couldn't restock items.");
    } finally {
      setBusy(false);
    }
  }

  // Copy WhatsApp List
  function handleCopyWhatsApp() {
    if (!selectedItems.length) {
      toast.err("Select items to copy.");
      return;
    }
    const grouped = {};
    selectedItems.forEach((it) => {
      const catGroup = CATEGORY_GROUPS.find((cg) => cg.cats.includes(it.category)) || CATEGORY_GROUPS[CATEGORY_GROUPS.length - 1];
      grouped[catGroup.label] = grouped[catGroup.label] || [];
      const grams = quantities[it.food_id] || it.typical_grams;
      const qtyStr = grams >= 1000 ? `${grams / 1000}kg` : `${grams}g`;
      const hindi = HINDI_NAMES[it.food_id] ? ` (${HINDI_NAMES[it.food_id]})` : "";
      grouped[catGroup.label].push(`  • ${qtyStr} ${it.name}${hindi}`);
    });

    let text = `🛒 *FridgeSense Grocery List*\n`;
    text += `_Generated from items that ran out_\n\n`;
    Object.entries(grouped).forEach(([groupName, lines]) => {
      text += `*${groupName}*\n${lines.join("\n")}\n\n`;
    });
    text += `💰 *Est. Total:* ₹${Math.round(totalCost)}\n`;

    navigator.clipboard.writeText(text);
    toast.ok("📋 Copied WhatsApp grocery list to clipboard!");
  }

  // Edit in Scratchpad
  function handleEditInScratchpad() {
    if (!selectedItems.length) {
      toast.err("Select items to populate.");
      return;
    }
    const lines = selectedItems.map((it) => {
      const grams = quantities[it.food_id] || it.typical_grams;
      const qtyStr = grams >= 1000 ? `${grams / 1000}kg` : `${grams}g`;
      return `${qtyStr} ${it.name.toLowerCase()}`;
    });
    nav("/add", { state: { text: lines.join(", "), mode: "scratchpad" } });
  }

  if (err) return <EmptyState icon="warn" title="Couldn't load shopping list" body={err} action={<button className="btn" onClick={loadList}>Try again</button>} />;
  if (items === null) return <Loader label="Checking items that ran out…" />;

  // Grouped items
  const groupedData = CATEGORY_GROUPS.map((group) => {
    const groupItems = items.filter((it) =>
      group.cats.length > 0 ? group.cats.includes(it.category) : !CATEGORY_GROUPS.slice(0, -1).some((cg) => cg.cats.includes(it.category))
    );
    return { ...group, items: groupItems };
  }).filter((g) => g.items.length > 0);

  return (
    <div className="stack" style={{ gap: "var(--sp-5)", maxWidth: 900, margin: "0 auto" }}>
      {/* Top Banner & Action Strip */}
      <div className="card" style={{ padding: "20px 24px", borderRadius: "16px", border: "1px solid var(--border)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
              <span style={{ fontSize: "1.4rem" }}>🛒</span>
              <h2 style={{ margin: 0, fontSize: "1.3rem", fontWeight: 700, color: "var(--ink)" }}>
                Shopping List
              </h2>
              {items && items.length > 0 && (
                <span className="badge" style={{ background: "rgba(31, 111, 74, 0.12)", color: "var(--fresh)", fontWeight: 700 }}>
                  {items.length} suggestions
                </span>
              )}
            </div>
            <p className="small muted" style={{ margin: 0 }}>
              Suggestions from items that ran out in your kitchen. Check items you want to buy, or delete items you don't need.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "baseline", gap: "12px" }}>
            <div style={{ textAlign: "right" }}>
              <div className="small muted">Selected Total</div>
              <div style={{ fontSize: "1.4rem", fontWeight: 700, color: selectedItems.length > 0 ? "var(--fresh)" : "var(--muted)", fontFamily: "var(--font-mono)" }}>
                {inr(totalCost)}
              </div>
            </div>
          </div>
        </div>

        {/* Global Action Bar */}
        {items && items.length > 0 && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
              marginTop: "16px",
              paddingTop: "14px",
              borderTop: "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn--xs btn--ghost"
                onClick={() => toggleAll(!allSelected)}
              >
                {allSelected ? "Deselect all" : `Select all (${items.length})`}
              </button>
              <button
                type="button"
                className="btn btn--xs btn--ghost"
                style={{ color: "var(--hot)" }}
                onClick={handleClearAll}
                title="Dismiss all items from shopping list"
              >
                <Icon.trash width={13} height={13} /> Clear all
              </button>
              <span className="small muted">
                <strong>{selectedItems.length}</strong> of {items.length} selected
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn--primary"
                disabled={busy || !selectedItems.length}
                onClick={handleRestock}
              >
                <Icon.check width={16} height={16} /> 1-Click Restock ({selectedItems.length})
              </button>
              <button
                type="button"
                className="btn btn--subtle"
                disabled={!selectedItems.length}
                onClick={handleCopyWhatsApp}
                title="Copy formatted list for WhatsApp"
              >
                📋 Copy WhatsApp List
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={!selectedItems.length}
                onClick={handleEditInScratchpad}
                title="Open in WhatsApp Scratchpad note"
              >
                ✍️ Open in Scratchpad
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Quick Add Custom Item Input */}
      <form onSubmit={addCustom} style={{ display: "flex", gap: "8px" }}>
        <input
          className="input"
          placeholder="+ Add an item to buy (e.g. eggs, dahi, biscuits, bread…)"
          value={customItem}
          onChange={(e) => setCustomItem(e.target.value)}
          style={{ flex: 1, background: "var(--surface)", border: "1.5px dashed var(--border)" }}
        />
        <button type="submit" className="btn btn--subtle" disabled={!customItem.trim()}>
          + Add to list
        </button>
      </form>

      {/* Checklist Sections */}
      {items.length === 0 ? (
        <EmptyState
          icon="cart"
          title="Your shopping list is empty"
          body="No items currently on your shopping list. Items that run out in your kitchen will appear here as suggestions, or you can add items anytime using the box above."
          action={
            <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
              <button className="btn btn--subtle" onClick={loadList}>
                <Icon.refresh width={14} height={14} /> Refresh
              </button>
              <Link to="/pantry" className="btn btn--ghost">View Pantry</Link>
            </div>
          }
        />
      ) : (
        groupedData.map((group) => (
          <div key={group.id} className="card" style={{ padding: "16px 20px", borderRadius: "14px", border: "1px solid var(--border)" }}>
            <h3
              style={{
                margin: "0 0 12px",
                fontSize: "0.98rem",
                fontWeight: 700,
                color: "var(--ink)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span>{group.label}</span>
              <span className="small muted" style={{ fontWeight: 400 }}>
                {group.items.filter((it) => selected[it.food_id]).length} of {group.items.length} to buy
              </span>
            </h3>

            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {group.items.map((it) => {
                const isChecked = Boolean(selected[it.food_id]);
                const icon = FOOD_ICONS[it.food_id] || "🧺";
                const hindi = HINDI_NAMES[it.food_id];
                const grams = quantities[it.food_id] || it.typical_grams || 500;
                const qtyDisplay = grams >= 1000 ? `${grams / 1000} kg` : `${grams} g`;
                const itemCost = it.estimated_cost_inr ? Math.round((grams / (it.typical_grams || 500)) * it.estimated_cost_inr) : 40;

                return (
                  <div
                    key={it.food_id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "10px 14px",
                      borderRadius: "10px",
                      background: isChecked ? "rgba(31, 111, 74, 0.04)" : "transparent",
                      border: `1px solid ${isChecked ? "rgba(31, 111, 74, 0.2)" : "transparent"}`,
                      transition: "all 0.15s ease",
                      gap: "12px",
                    }}
                  >
                    {/* Checkbox and Name */}
                    <div
                      style={{ display: "flex", alignItems: "center", gap: "12px", flex: 1, cursor: "pointer", minWidth: 0 }}
                      onClick={() => toggle(it.food_id)}
                    >
                      <div
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: "50%",
                          border: `2px solid ${isChecked ? "var(--fresh)" : "var(--line)"}`,
                          background: isChecked ? "var(--fresh)" : "transparent",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "#fff",
                          flexShrink: 0,
                          transition: "all 0.15s ease",
                        }}
                      >
                        {isChecked && <Icon.check width={14} height={14} />}
                      </div>

                      <span style={{ fontSize: "1.35rem", lineHeight: 1 }}>{icon}</span>

                      <div style={{ minWidth: 0 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: "0.94rem",
                            color: isChecked ? "var(--ink)" : "var(--muted)",
                            textDecoration: isChecked ? "none" : "line-through",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {it.name}
                          {hindi && (
                            <span style={{ fontWeight: 400, color: "var(--muted)", marginLeft: 6, fontSize: "0.82rem" }}>
                              ({hindi})
                            </span>
                          )}
                        </div>
                        <div className="small muted" style={{ fontSize: "0.75rem" }}>
                          {it.is_staple ? "⚡ Household staple" : "Perishable"} {it.resolved_at ? `· Ran out ${it.resolved_at}` : ""}
                        </div>
                      </div>
                    </div>

                    {/* Quantity Pill Controls & Price */}
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", flexShrink: 0 }}>
                      <div
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          background: "var(--surface)",
                          border: "1px solid var(--border)",
                          borderRadius: "20px",
                          padding: "2px 4px",
                          gap: "4px",
                        }}
                      >
                        <button
                          type="button"
                          style={{
                            border: "none",
                            background: "transparent",
                            cursor: "pointer",
                            padding: "2px 6px",
                            fontSize: "0.85rem",
                            color: "var(--ink-soft)",
                            borderRadius: "10px",
                          }}
                          onClick={() => adjustQty(it.food_id, grams > 1000 ? -500 : -100)}
                          title="Reduce quantity"
                        >
                          -
                        </button>
                        <span style={{ fontSize: "0.82rem", fontWeight: 700, minWidth: 46, textAlign: "center" }}>
                          {qtyDisplay}
                        </span>
                        <button
                          type="button"
                          style={{
                            border: "none",
                            background: "transparent",
                            cursor: "pointer",
                            padding: "2px 6px",
                            fontSize: "0.85rem",
                            color: "var(--ink-soft)",
                            borderRadius: "10px",
                          }}
                          onClick={() => adjustQty(it.food_id, grams >= 1000 ? 500 : 100)}
                          title="Increase quantity"
                        >
                          +
                        </button>
                      </div>

                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: "0.88rem",
                          color: isChecked ? "var(--ink)" : "var(--muted)",
                          minWidth: 44,
                          textAlign: "right",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        ₹{itemCost}
                      </div>

                      <button
                        type="button"
                        className="btn btn--xs btn--ghost"
                        style={{ padding: "4px 6px", color: "var(--muted)" }}
                        onClick={(e) => {
                          e.stopPropagation();
                          removeItem(it.food_id, it.name);
                        }}
                        title="Remove permanently from shopping list"
                      >
                        <Icon.trash width={14} height={14} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

import { useState, useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "./Toast.jsx";
import { api } from "../lib/api.js";
import { initials } from "../lib/format.js";
import Icon from "./Icons.jsx";


const NAV = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true, section: "Kitchen" },
  { to: "/pantry", label: "Pantry", icon: "fridge" },
  { to: "/shopping", label: "Shopping list", icon: "cart" },
  { to: "/add", label: "Add & import", icon: "add" },
  { to: "/recipes", label: "Cook & rescue", icon: "recipe", section: "Act" },
  { to: "/impact", label: "Impact", icon: "impact" },
  { to: "/insights", label: "Habits", icon: "insight" },
  { to: "/model", label: "The model", icon: "model", section: "Under the hood" },
];

const BOTTOM_NAV = [
  { to: "/", label: "Home", icon: "dashboard", end: true },
  { to: "/pantry", label: "Pantry", icon: "fridge" },
  { to: "/shopping", label: "Buy", icon: "cart" },
  { to: "/add", label: "Add", icon: "add" },
  { to: "/recipes", label: "Recipes", icon: "recipe" },
];

const TITLES = {
  "/": ["Dashboard", "What to eat first, tonight"],
  "/pantry": ["Pantry", "Everything in your kitchen, ranked by spoilage risk"],
  "/shopping": ["Shopping list", "Items that ran out in your kitchen — ready to buy"],
  "/add": ["Add & import", "Type an item or paste a shop receipt"],
  "/recipes": ["Cook & rescue", "Recipes ranked by how much at-risk food they use up"],
  "/impact": ["Impact", "Money, carbon and water — measured, not guessed"],
  "/insights": ["Habits", "Patterns worth changing, with the evidence"],
  "/model": ["The model", "How the spoilage score is made — and where it fails"],
};

export default function Layout({ criticalCount = 0, restockCount = 0 }) {
  const { user, logout } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localRestockCount, setLocalRestockCount] = useState(restockCount);

  useEffect(() => {
    setLocalRestockCount(restockCount);
  }, [restockCount]);

  useEffect(() => {
    if (user) {
      api.restockList()
        .then((res) => {
          if (res?.items) setLocalRestockCount(res.items.length);
        })
        .catch(() => {});
    }
  }, [user]);

  useEffect(() => { setOpen(false); }, [loc.pathname]);

  const [title, sub] = TITLES[loc.pathname] || [
    loc.pathname.startsWith("/recipes/") ? "Recipe" : "FridgeSense", "",
  ];

  async function resetDemo() {
    if (!confirm("Rebuild the demo kitchen? This replaces the demo account's pantry and history with a fresh sample.")) return;
    setBusy(true);
    try { await api.resetDemo(); toast.ok("Demo kitchen rebuilt. Reloading…"); setTimeout(() => location.reload(), 700); }
    catch (e) { toast.err(e.detail || "Couldn't reset the demo."); setBusy(false); }
  }

  return (
    <div className="app">
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <aside className={`sidebar ${open ? "is-open" : ""}`}>
        <div className="brand">
          <img className="brand__mark" src="/favicon.svg" alt="" width={34} height={34} />
          <div>
            <div className="brand__name">Fridge<span>Sense</span></div>
            <div className="brand__tag">cook before you spoil</div>
          </div>
        </div>

        <nav className="nav" aria-label="Primary">
          {NAV.map((n) => {
            const I = Icon[n.icon];
            return (
              <div key={n.to}>
                {n.section && <div className="nav__section">{n.section}</div>}
                <NavLink to={n.to} end={n.end} className={({ isActive }) => `nav__link ${isActive ? "is-active" : ""}`}>
                  <I className="nav__icon" width={18} height={18} />
                  <span>{n.label}</span>
                  {n.to === "/" && criticalCount > 0 && <span className="nav__badge">{criticalCount}</span>}
                  {n.to === "/shopping" && localRestockCount > 0 && (
                    <span className="nav__badge nav__badge--teal">{localRestockCount}</span>
                  )}
                </NavLink>
              </div>
            );
          })}
        </nav>

        <div className="sidebar__foot">
          <button className="ghost-on-dark" onClick={resetDemo} disabled={busy}>↺ Rebuild demo kitchen</button>
          <div className="who">
            <div className="who__avatar">{initials(user?.name, user?.email)}</div>
            <div style={{ minWidth: 0 }}>
              <div className="who__name">{user?.name || "You"}</div>
              <div className="who__meta">Household of {user?.household_size ?? "—"}</div>
            </div>
            <button className="ghost-on-dark" title="Log out" onClick={() => { logout(); nav("/login"); }} style={{ marginLeft: "auto" }}>
              <Icon.logout width={18} height={18} />
            </button>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="hamburger" aria-label="Open menu" onClick={() => setOpen(true)}><Icon.menu /></button>
          <div>
            <div className="topbar__title">{title}</div>
            {sub && <div className="topbar__sub">{sub}</div>}
          </div>
          <div className="topbar__spacer" />
        </header>
        <main className="content"><Outlet /></main>


        <nav className="bottom-nav" aria-label="Mobile Navigation">
          {BOTTOM_NAV.map((n) => {
            const I = Icon[n.icon];
            return (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) => `bottom-nav__item ${isActive ? "is-active" : ""}`}
              >
                <div className="bottom-nav__icon-wrap">
                  <I className="bottom-nav__icon" width={20} height={20} />
                  {n.to === "/" && criticalCount > 0 && (
                    <span className="bottom-nav__badge">{criticalCount}</span>
                  )}
                  {n.to === "/shopping" && localRestockCount > 0 && (
                    <span className="bottom-nav__badge bottom-nav__badge--teal">{localRestockCount}</span>
                  )}
                </div>
                <span>{n.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>
    </div>
  );
}


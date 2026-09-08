import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { useToast } from "../components/Toast.jsx";
import { ApiError } from "../lib/api.js";
import Icon from "../components/Icons.jsx";

const DEMO = { email: "demo@fridgesense.app", password: "demo1234" };

export default function Login() {
  const { login, register } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const loc = useLocation();
  const dest = loc.state?.from || "/";

  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "", household_size: 3 });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "login") await login(form.email.trim(), form.password);
      else await register({ ...form, email: form.email.trim(), household_size: Number(form.household_size) });
      nav(dest, { replace: true });
    } catch (err) {
      toast.err(err instanceof ApiError ? (typeof err.detail === "string" ? err.detail : "Check your details and try again") : "Something went wrong");
      setBusy(false);
    }
  }

  async function demoLogin() {
    setBusy(true);
    try { await login(DEMO.email, DEMO.password); nav("/", { replace: true }); }
    catch (err) { toast.err(err.detail || "Demo isn't seeded yet. Start the backend and try again."); setBusy(false); }
  }

  return (
    <div className="auth">
      <section className="auth__pitch">
        <div className="auth__pitch-inner">
          <div className="brand" style={{ marginBottom: 28 }}>
            <img className="brand__mark" src="/favicon.svg" alt="" width={40} height={40} />
            <div className="brand__name" style={{ fontSize: "1.5rem" }}>Fridge<span>Sense</span></div>
          </div>
          <p className="auth__eyebrow">The cold-chain, at home</p>
          <h1 className="auth__headline">Your kitchen wastes food on a schedule. This reads the schedule.</h1>
          <p className="auth__lede">
            FridgeSense scores every item by how likely it is to be thrown away — not just by the printed
            date, but by how much is left, how fast you actually eat it, and where it's stored. Then it tells
            you what to cook tonight.
          </p>
          <ul className="auth__points">
            <li><Icon.snow width={18} height={18} /> A spoilage model, not a countdown timer</li>
            <li><Icon.recipe width={18} height={18} /> Recipes ranked by what they rescue</li>
            <li><Icon.coin width={18} height={18} /> Rupees, CO₂e and water — measured against a real baseline</li>
          </ul>
          <div className="auth__gaugebar" aria-hidden="true"><span /></div>
          <p className="auth__foot mono">fresh → spoiling · the whole app is coloured by this one idea</p>
        </div>
      </section>

      <section className="auth__panel">
        <div className="auth__card">
          <div className="auth__tabs" role="tablist">
            <button role="tab" aria-selected={mode === "login"} className={mode === "login" ? "is-on" : ""} onClick={() => setMode("login")}>Sign in</button>
            <button role="tab" aria-selected={mode === "register"} className={mode === "register" ? "is-on" : ""} onClick={() => setMode("register")}>Create account</button>
          </div>

          <form onSubmit={submit} className="stack" style={{ gap: 16 }}>
            {mode === "register" && (
              <div className="field">
                <label className="field__label" htmlFor="name">Name</label>
                <input id="name" className="input" value={form.name} onChange={set("name")} placeholder="Priya" autoComplete="name" />
              </div>
            )}
            <div className="field">
              <label className="field__label" htmlFor="email">Email</label>
              <input id="email" className="input" type="email" required value={form.email} onChange={set("email")} placeholder="you@kitchen.in" autoComplete="email" />
            </div>
            <div className="field">
              <label className="field__label" htmlFor="password">Password</label>
              <input id="password" className="input" type="password" required minLength={mode === "register" ? 8 : undefined}
                value={form.password} onChange={set("password")} placeholder={mode === "register" ? "at least 8 characters" : "••••••••"} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </div>
            {mode === "register" && (
              <div className="field">
                <label className="field__label" htmlFor="hh">People in the household</label>
                <input id="hh" className="input" type="number" min={1} max={20} value={form.household_size} onChange={set("household_size")} />
                <span className="field__hint">Used to gauge how fast food gets eaten.</span>
              </div>
            )}
            <button className="btn btn--primary" type="submit" disabled={busy} style={{ width: "100%", padding: "12px" }}>
              {busy ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className="auth__or"><span>or</span></div>
          <button className="btn" onClick={demoLogin} disabled={busy} style={{ width: "100%" }}>
            <Icon.plate width={18} height={18} /> Explore the demo kitchen
          </button>
          <p className="auth__hint mono">demo@fridgesense.app · demo1234</p>
        </div>
      </section>
    </div>
  );
}

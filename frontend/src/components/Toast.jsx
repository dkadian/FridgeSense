import { createContext, useContext, useState, useCallback } from "react";
import Icon from "./Icons.jsx";

const ToastCtx = createContext(null);
export const useToast = () => useContext(ToastCtx);

let seq = 0;
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const remove = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback((message, kind = "ok") => {
    const id = ++seq;
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => remove(id), 4200);
  }, [remove]);
  const toast = useCallback({
    ok: (m) => push(m, "ok"),
    err: (m) => push(m, "err"),
  }, [push]);

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="toast-wrap" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind === "err" ? "toast--err" : "toast--ok"}`} onClick={() => remove(t.id)}>
            <span className="toast__i">{t.kind === "err" ? <Icon.warn width={18} height={18} /> : <Icon.check width={18} height={18} />}</span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, getToken, setToken } from "../lib/api.js";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (getToken()) {
        try { const u = await api.me(); if (alive) setUser(u); }
        catch { setToken(""); }
      }
      if (alive) setReady(true);
    })();
    return () => { alive = false; };
  }, []);

  const login = useCallback(async (email, password) => {
    const res = await api.login(email, password);
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  }, []);

  const register = useCallback(async (payload) => {
    const res = await api.register(payload);
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => { setToken(""); setUser(null); }, []);

  const refreshUser = useCallback(async () => {
    try { setUser(await api.me()); } catch { /* ignore */ }
  }, []);

  return (
    <AuthCtx.Provider value={{ user, ready, login, register, logout, refreshUser, setUser }}>
      {children}
    </AuthCtx.Provider>
  );
}

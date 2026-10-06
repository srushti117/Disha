"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken } from "./api";

export type User = { id: number; email: string; name: string; role: string; permissions?: string[] };
type Ctx = { user: User | null; loading: boolean; login: (email: string, password: string) => Promise<void>; logout: () => void; can: (perm: string) => boolean };

const AuthCtx = createContext<Ctx>({ user: null, loading: true, login: async () => {}, logout: () => {}, can: () => false });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string; user: User; permissions: string[] }>("/api/auth/login", { body: { email, password } });
    window.localStorage.setItem("disha_token", r.access_token);
    setUser({ ...r.user, permissions: r.permissions });
  }, []);

  const logout = useCallback(() => {
    try {
      window.localStorage.removeItem("disha_token");
    } catch {}
    setUser(null);
    window.location.href = "/login";
  }, []);

  const can = useCallback((p: string) => !!user?.permissions?.includes(p), [user]);
  return <AuthCtx.Provider value={{ user, loading, login, logout, can }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);

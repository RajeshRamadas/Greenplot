"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getRefreshToken, login as apiLogin, logout as apiLogout, onAuthChange } from "./api";
import type { Me, Meta } from "./types";

interface AuthState {
  me: Me | null;
  meta: Meta | null;
  loading: boolean;
  can: (permission: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);
const ME_CACHE = "gp.me";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    if (!getRefreshToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      const m = await api<Me>("/auth/me");
      setMe(m);
      try {
        localStorage.setItem(ME_CACHE, JSON.stringify(m));
      } catch {
        /* ignore */
      }
      if (m.tenant_id) setMeta(await api<Meta>("/meta"));
    } catch (e) {
      // Offline: keep working with the cached profile so field users can queue work.
      const cached = typeof navigator !== "undefined" && !navigator.onLine ? safeCached() : null;
      setMe(cached);
      if (!cached) console.warn("session check failed", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    return onAuthChange(() => {
      if (!getRefreshToken()) setMe(null);
    });
  }, [reload]);

  const value: AuthState = {
    me,
    meta,
    loading,
    can: (p) => !!me?.permissions.includes(p),
    login: async (email, password) => {
      await apiLogin(email, password);
      await reload();
    },
    logout: async () => {
      await apiLogout();
      try {
        localStorage.removeItem(ME_CACHE);
      } catch {
        /* ignore */
      }
      setMe(null);
    },
    reload,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function safeCached(): Me | null {
  try {
    const raw = localStorage.getItem(ME_CACHE);
    return raw ? (JSON.parse(raw) as Me) : null;
  } catch {
    return null;
  }
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

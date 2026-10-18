"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchMe, login, register, type UserInfo } from "@/services/api";
import { AUTH_EXPIRED_EVENT, clearTokens, getTokens, saveTokens } from "@/services/auth";

type Status = "loading" | "anonymous" | "authenticated";

interface AuthContextValue {
  status: Status;
  user: UserInfo | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (name: string, email: string, password: string) => Promise<void>;
  startDemo: () => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<UserInfo | null>(null);

  const adopt = useCallback((u: UserInfo) => { setUser(u); setStatus("authenticated"); }, []);
  const drop = useCallback(() => { setUser(null); setStatus("anonymous"); }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!getTokens()) { drop(); return; }
      try { const u = await fetchMe(); if (alive) adopt(u); }
      catch { clearTokens(); if (alive) drop(); }
    })();
    const onExpired = () => drop();
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => { alive = false; window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired); };
  }, [adopt, drop]);

  const signIn = useCallback(async (email: string, password: string) => {
    saveTokens(await login(email, password));
    adopt(await fetchMe());
  }, [adopt]);

  const signUp = useCallback(async (name: string, email: string, password: string) => {
    saveTokens(await register(email, password, name));
    adopt(await fetchMe());
  }, [adopt]);

  /** One-click demo: a throwaway account, so evaluators don't need to invent credentials. */
  const startDemo = useCallback(async () => {
    const tag = Math.random().toString(36).slice(2, 10);
    await signUp("Demo driver", `demo-${tag}@evoptigrid.dev`, `demo-${tag}-${Date.now()}`);
  }, [signUp]);

  const signOut = useCallback(() => { clearTokens(); drop(); }, [drop]);

  const value = useMemo(() => ({ status, user, signIn, signUp, startDemo, signOut }), [status, user, signIn, signUp, startDemo, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

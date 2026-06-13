"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, AUTH_INVALID_EVENT, type AuthResponse, type User, type UserUsage } from "@/lib/api";

type AuthContextValue = {
  user: User | null;
  usage: UserUsage | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, username: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<AuthResponse | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [usage, setUsage] = useState<UserUsage | null>(null);
  const [loading, setLoading] = useState(true);

  const applyAuth = (auth: AuthResponse | null) => {
    setUser(auth?.user ?? null);
    setUsage(auth?.usage ?? null);
  };

  const refresh = async () => {
    try {
      const auth = await api.me();
      applyAuth(auth);
      return auth;
    } catch {
      applyAuth(null);
      return null;
    }
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const clearInvalidSession = () => {
      applyAuth(null);
      setLoading(false);
    };
    window.addEventListener(AUTH_INVALID_EVENT, clearInvalidSession);
    return () => window.removeEventListener(AUTH_INVALID_EVENT, clearInvalidSession);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      usage,
      loading,
      login: async (email, password) => {
        applyAuth(await api.login({ email, password }));
      },
      register: async (email, password, username) => {
        applyAuth(await api.register({ email, password, username }));
      },
      logout: async () => {
        await api.logout();
        applyAuth(null);
      },
      refresh,
    }),
    [loading, usage, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

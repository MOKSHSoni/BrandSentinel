"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, setToken, getToken } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password?: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  ready: false,
  login: async () => {
    throw new Error("no provider");
  },
  logout: () => {},
});

export const DEMO_PASSWORD = "demo1234";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setReady(true));
  }, []);

  const login = useCallback(async (email: string, password = DEMO_PASSWORD) => {
    const res = await api<{ token: string; user: User }>("/api/auth/login", { method: "POST", json: { email, password } });
    setToken(res.token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, ready, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

export const ROLE_LABEL: Record<string, string> = {
  creator: "Creator",
  manager: "Manager",
  admin: "Brand admin",
};

export function roleLabel(u: User) {
  return u.is_agency ? "Agency creator" : ROLE_LABEL[u.role];
}

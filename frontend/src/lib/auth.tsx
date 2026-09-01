import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setAuthToken } from "./api";
import type { Token, User } from "./types";

const STORAGE_KEY = "emai.auth.token";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithOAuth: (provider: "google" | "microsoft", idToken: string) => Promise<void>;
  signup: (orgName: string, orgSlug: string, email: string, password: string) => Promise<void>;
  signupWithOAuth: (
    provider: "google" | "microsoft",
    idToken: string,
    orgName: string,
    orgSlug: string,
  ) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function applySession(result: Token) {
    localStorage.setItem(STORAGE_KEY, result.access_token);
    setAuthToken(result.access_token);
    setToken(result.access_token);
    setUser(result.user);
  }

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    setAuthToken(stored);
    setToken(stored);
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(STORAGE_KEY);
        setAuthToken(null);
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      loading,
      async login(email, password) {
        const form = new URLSearchParams();
        form.set("username", email);
        form.set("password", password);
        const result = await api.postForm<Token>("/auth/login", form);
        applySession(result);
      },
      async loginWithOAuth(provider, idToken) {
        const result = await api.post<Token>("/auth/oauth/login", { provider, id_token: idToken });
        applySession(result);
      },
      async signup(orgName, orgSlug, email, password) {
        const result = await api.post<Token>("/auth/signup", {
          org_name: orgName,
          org_slug: orgSlug,
          email,
          password,
        });
        applySession(result);
      },
      async signupWithOAuth(provider, idToken, orgName, orgSlug) {
        const result = await api.post<Token>("/auth/oauth/signup", {
          provider,
          id_token: idToken,
          org_name: orgName,
          org_slug: orgSlug,
        });
        applySession(result);
      },
      logout() {
        localStorage.removeItem(STORAGE_KEY);
        setAuthToken(null);
        setToken(null);
        setUser(null);
      },
      async refreshMe() {
        const me = await api.get<User>("/auth/me");
        setUser(me);
      },
    }),
    [user, token, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function isScheduler(user: User | null): boolean {
  return !!user && (user.role === "owner" || user.role === "admin" || user.role === "scheduler");
}

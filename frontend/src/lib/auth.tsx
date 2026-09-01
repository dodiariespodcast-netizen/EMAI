import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, setAuthToken } from "./api";
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
  /** Set when a stored session exists but we couldn't reach the API to
   * verify it -- distinct from "not signed in". */
  connectionError: boolean;
  retryBootstrap: () => void;
  /** Adopt a session handed back by an endpoint that authenticates on our
   * behalf (password reset / invite confirmation), rather than logging in. */
  adoptSession: (token: Token) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState(false);
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);

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
    setConnectionError(false);

    let cancelled = false;
    api
      .get<User>("/auth/me")
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch((err) => {
        if (cancelled) return;
        // Only a definitive rejection from the server means the session is
        // dead. Anything else -- the API being briefly unreachable, a request
        // aborted by navigation, a laptop waking up -- must NOT throw away a
        // valid session, or the app appears to sign people out at random.
        const rejected = err instanceof ApiError && (err.status === 401 || err.status === 403);
        if (rejected) {
          localStorage.removeItem(STORAGE_KEY);
          setAuthToken(null);
          setToken(null);
        } else {
          setConnectionError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      // A navigation away mid-flight aborts the request; don't let that
      // resolution touch state for a page that's already gone.
      cancelled = true;
    };
  }, [bootstrapAttempt]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      loading,
      async login(email, password) {
        setConnectionError(false);
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
        setConnectionError(false);
      },
      async refreshMe() {
        const me = await api.get<User>("/auth/me");
        setUser(me);
      },
      adoptSession(result) {
        applySession(result);
      },
      connectionError,
      retryBootstrap() {
        setLoading(true);
        setBootstrapAttempt((n) => n + 1);
      },
    }),
    [user, token, loading, connectionError],
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

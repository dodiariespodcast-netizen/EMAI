import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBanner, Field, Input } from "../components/ui";
import { GoogleSignInButton } from "../components/GoogleSignInButton";
import { MicrosoftSignInButton } from "../components/MicrosoftSignInButton";
import { AuthShell } from "../components/AuthShell";

export function LoginPage() {
  const { login, loginWithOAuth } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function handleOAuth(provider: "google" | "microsoft", idToken: string) {
    setError(null);
    try {
      await loginWithOAuth(provider, idToken);
      navigate("/app");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError("No account found for this identity yet. Create an organization first.");
      } else {
        setError(err instanceof ApiError ? err.friendlyMessage : "Sign-in failed");
      }
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Log in to your EMAI Scheduler account">
      <Card className="p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <ErrorBanner message={error} />}
          <Field label="Email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          </Field>
          <Field label="Password">
            <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Log in"}
          </Button>
          <p className="text-center">
            <Link to="/forgot-password" className="text-xs font-medium text-slate-500 hover:text-brand-600">
              Forgot your password?
            </Link>
          </p>
        </form>

        <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
          <div className="h-px flex-1 bg-slate-200" />
          or
          <div className="h-px flex-1 bg-slate-200" />
        </div>

        <div className="space-y-2">
          <GoogleSignInButton onIdToken={(t) => handleOAuth("google", t)} />
          <MicrosoftSignInButton onIdToken={(t) => handleOAuth("microsoft", t)} />
        </div>
      </Card>

      <p className="mt-4 text-center text-sm text-slate-500">
        New here?{" "}
        <Link to="/signup" className="font-medium text-brand-600 hover:underline">
          Create your organization
        </Link>
      </p>
    </AuthShell>
  );
}

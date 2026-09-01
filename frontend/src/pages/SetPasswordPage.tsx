import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { AuthShell } from "../components/AuthShell";
import { Button, Card, ErrorBanner, Field, Input } from "../components/ui";
import type { Token } from "../lib/types";

/** Backs both /reset-password (forgot flow) and /set-password (invite flow) --
 * same token exchange, different copy. */
export function SetPasswordPage({ mode }: { mode: "reset" | "invite" }) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { adoptSession } = useAuth();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy =
    mode === "invite"
      ? { title: "Set your password", subtitle: "Finish setting up your account", cta: "Set password and sign in" }
      : { title: "Choose a new password", subtitle: "Almost done", cta: "Save and sign in" };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Those passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<Token>("/auth/password-reset/confirm", {
        token,
        new_password: password,
      });
      // The endpoint signs the user in, so drop them straight into the app.
      adoptSession(result);
      navigate("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <AuthShell title="Link problem" subtitle="That link is missing its token">
        <Card className="p-6">
          <ErrorBanner message="This link looks incomplete. Ask for a new one and try again." />
          <Link to="/forgot-password" className="mt-4 block text-center text-sm font-medium text-brand-600 hover:underline">
            Request a new link
          </Link>
        </Card>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={copy.title} subtitle={copy.subtitle}>
      <Card className="p-6">
        <form onSubmit={submit} className="space-y-4">
          {error && <ErrorBanner message={error} />}
          <Field label="New password">
            <Input
              type="password"
              required
              minLength={8}
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Field label="Confirm password">
            <Input type="password" required minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Saving…" : copy.cta}
          </Button>
        </form>
      </Card>
      <p className="mt-4 text-center text-sm text-slate-500">
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthShell>
  );
}

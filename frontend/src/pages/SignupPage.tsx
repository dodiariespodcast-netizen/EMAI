import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBanner, Field, Input } from "../components/ui";
import { GoogleSignInButton } from "../components/GoogleSignInButton";
import { MicrosoftSignInButton } from "../components/MicrosoftSignInButton";
import { AuthShell } from "../components/AuthShell";

function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export function SignupPage() {
  const { signup, signupWithOAuth } = useAuth();
  const navigate = useNavigate();
  const [orgName, setOrgName] = useState("");
  const [orgSlug, setOrgSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const orgReady = orgName.trim().length >= 2 && orgSlug.trim().length >= 2;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signup(orgName, orgSlug, email, password);
      navigate("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function handleOAuth(provider: "google" | "microsoft", idToken: string) {
    if (!orgReady) {
      setError("Enter your organization name first, then continue with Google/Microsoft.");
      return;
    }
    setError(null);
    try {
      await signupWithOAuth(provider, idToken, orgName, orgSlug);
      navigate("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Sign-up failed");
    }
  }

  return (
    <AuthShell title="Create your organization" subtitle="Start scheduling in a few minutes">
      <Card className="p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <ErrorBanner message={error} />}
          <Field label="Organization name">
            <Input
              required
              value={orgName}
              onChange={(e) => {
                setOrgName(e.target.value);
                if (!slugTouched) setOrgSlug(slugify(e.target.value));
              }}
              placeholder="Riverside Emergency Group"
              autoFocus
            />
          </Field>
          <Field label="Organization URL slug">
            <Input
              required
              value={orgSlug}
              onChange={(e) => {
                setSlugTouched(true);
                setOrgSlug(slugify(e.target.value));
              }}
              placeholder="riverside-eg"
            />
          </Field>
          <div className="h-px bg-slate-100" />
          <Field label="Your email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password">
            <Input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Creating…" : "Create organization"}
          </Button>
        </form>

        <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
          <div className="h-px flex-1 bg-slate-200" />
          or sign up with
          <div className="h-px flex-1 bg-slate-200" />
        </div>

        <div className="space-y-2">
          <GoogleSignInButton onIdToken={(t) => handleOAuth("google", t)} />
          <MicrosoftSignInButton onIdToken={(t) => handleOAuth("microsoft", t)} />
        </div>
      </Card>

      <p className="mt-4 text-center text-sm text-slate-500">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Log in
        </Link>
      </p>
    </AuthShell>
  );
}

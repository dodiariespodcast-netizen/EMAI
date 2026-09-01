import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { AuthShell } from "../components/AuthShell";
import { Button, Card, ErrorBanner, Field, Input, SuccessBanner } from "../components/ui";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/password-reset/request", { email });
      setSent(true);
    } catch (err) {
      // A 429 is the one failure worth surfacing; everything else the server
      // deliberately reports as success so this can't be used to discover
      // which emails have accounts.
      setError(err instanceof ApiError ? err.friendlyMessage : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Reset your password" subtitle="We'll email you a link to set a new one">
      <Card className="p-6">
        {sent ? (
          <div className="space-y-4">
            <SuccessBanner message="If that email has an account, a reset link is on its way. The link expires in 2 hours." />
            <p className="text-xs text-slate-500">
              Nothing arrived? Check spam, or ask an admin to re-send you an invite link.
            </p>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            {error && <ErrorBanner message={error} />}
            <Field label="Email">
              <Input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Sending…" : "Send reset link"}
            </Button>
          </form>
        )}
      </Card>
      <p className="mt-4 text-center text-sm text-slate-500">
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthShell>
  );
}

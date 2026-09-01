import { useState } from "react";
import { useAuth } from "../lib/auth";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { OAuthIdentity } from "../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, PageHeader, SuccessBanner } from "../components/ui";
import { GoogleSignInButton } from "../components/GoogleSignInButton";
import { MicrosoftSignInButton } from "../components/MicrosoftSignInButton";
import { titleCase } from "../lib/format";

export function SettingsPage() {
  const { user } = useAuth();
  const identities = useFetch(() => api.get<OAuthIdentity[]>("/auth/oauth/identities"), []);

  return (
    <div>
      <PageHeader title="Settings" subtitle="Your account and sign-in methods." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Account" />
          <div className="space-y-1 px-5 py-4 text-sm">
            <p>
              <span className="text-slate-400">Email:</span> {user?.email}
            </p>
            <p>
              <span className="text-slate-400">Role:</span> {titleCase(user?.role ?? "")}
            </p>
          </div>
        </Card>

        <ChangePasswordCard />

        <Card className="lg:col-span-2">
          <CardHeader title="Sign-in methods" subtitle="Link Google or Microsoft so you can log in without a password." />
          <div className="px-5 py-4">
            {identities.data && identities.data.length === 0 ? (
              <EmptyState title="No linked identities" />
            ) : (
              <div className="mb-4 divide-y divide-slate-100 border-b border-slate-100">
                {(identities.data ?? []).map((id) => (
                  <div key={id.id} className="flex items-center justify-between py-2 text-sm">
                    <div>
                      <Badge tone="blue">{titleCase(id.provider)}</Badge>{" "}
                      <span className="text-slate-500">{id.email}</span>
                    </div>
                    <button
                      className="text-xs text-slate-400 hover:text-red-600"
                      onClick={async () => {
                        await api.delete(`/auth/oauth/identities/${id.id}`);
                        identities.reload();
                      }}
                    >
                      Unlink
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-col gap-2 sm:flex-row">
              <GoogleSignInButton
                onIdToken={async (t) => {
                  await api.post("/auth/oauth/link", { provider: "google", id_token: t });
                  identities.reload();
                }}
              />
              <MicrosoftSignInButton
                onIdToken={async (t) => {
                  await api.post("/auth/oauth/link", { provider: "microsoft", id_token: t });
                  identities.reload();
                }}
              />
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(false);
    try {
      await api.post("/auth/change-password", { current_password: current || undefined, new_password: next });
      setSuccess(true);
      setCurrent("");
      setNext("");
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to change password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Password" subtitle="Leave 'current password' blank if you signed up with Google/Microsoft" />
      <form onSubmit={submit} className="space-y-3 px-5 py-4">
        {error && <ErrorBanner message={error} />}
        {success && <SuccessBanner message="Password updated." />}
        <Field label="Current password (if any)">
          <Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password">
          <Input type="password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Update password"}
        </Button>
      </form>
    </Card>
  );
}

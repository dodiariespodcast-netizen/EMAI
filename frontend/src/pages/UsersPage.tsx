import { useState } from "react";
import { useAuth } from "../lib/auth";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { InviteLink, Physician, User, UserRole } from "../lib/types";
import { Badge, Button, Card, CardHeader, ErrorBanner, Field, Input, PageHeader, Select, SuccessBanner } from "../components/ui";
import { titleCase } from "../lib/format";

const ROLES: UserRole[] = ["owner", "admin", "scheduler", "physician"];

export function UsersPage() {
  const { user: me } = useAuth();
  const users = useFetch(() => api.get<User[]>("/auth/users"), []);
  const physicians = useFetch(() => api.get<Physician[]>("/physicians"), []);
  const physicianById = new Map((physicians.data ?? []).map((p) => [p.id, p]));

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("physician");
  const [physicianId, setPhysicianId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastInvite, setLastInvite] = useState<InviteLink | null>(null);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // No password: the user is emailed a link and picks their own. The link
      // comes back too, so an admin can hand it over directly when email isn't
      // configured yet.
      const result = await api.post<InviteLink>("/auth/users", {
        email,
        role,
        physician_id: physicianId || undefined,
      });
      setLastInvite(result);
      setEmail("");
      setPhysicianId("");
      users.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to invite");
    } finally {
      setBusy(false);
    }
  }

  async function resendInvite(userId: string) {
    const result = await api.post<InviteLink>(`/auth/users/${userId}/invite`);
    setLastInvite(result);
  }

  async function updateRole(userId: string, newRole: UserRole) {
    await api.patch(`/auth/users/${userId}`, { role: newRole });
    users.reload();
  }

  async function toggleActive(u: User) {
    await api.patch(`/auth/users/${u.id}`, { is_active: !u.is_active });
    users.reload();
  }

  return (
    <div>
      <PageHeader title="Users" subtitle="Login accounts. Link a user to a physician record so they see their own schedule and can submit requests." />

      <Card className="mb-6">
        <CardHeader
          title="Invite a user"
          subtitle="They get an email with a link to set their own password -- no temporary password to pass around"
        />
        <form onSubmit={invite} className="grid grid-cols-2 gap-3 px-5 py-4 md:grid-cols-3">
          {error && (
            <div className="col-span-2 md:col-span-3">
              <ErrorBanner message={error} />
            </div>
          )}
          {lastInvite && (
            <div className="col-span-2 space-y-2 md:col-span-3">
              <SuccessBanner
                message={`Invited ${lastInvite.email}${
                  lastInvite.email_sent ? " -- an invite email is on its way." : "."
                } The link expires in ${lastInvite.expires_in_hours} hours.`}
              />
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="mb-1 text-xs text-slate-500">
                  Share this link directly if their email doesn't arrive:
                </p>
                <code className="block break-all text-xs text-slate-700">{lastInvite.invite_url}</code>
              </div>
            </div>
          )}
          <Field label="Email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Role">
            <Select value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {titleCase(r)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Link to physician (optional)">
            <Select value={physicianId} onChange={(e) => setPhysicianId(e.target.value)}>
              <option value="">None</option>
              {(physicians.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.first_name} {p.last_name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="col-span-2 md:col-span-3">
            <Button type="submit" disabled={busy}>
              {busy ? "Inviting…" : "Send invite"}
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <CardHeader title="Organization users" />
        <div className="divide-y divide-slate-100">
          {(users.data ?? []).map((u) => (
            <div key={u.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium text-slate-800">{u.email}</p>
                <p className="text-xs text-slate-400">
                  {u.physician_id && physicianById.get(u.physician_id)
                    ? `Linked to ${physicianById.get(u.physician_id)!.first_name} ${physicianById.get(u.physician_id)!.last_name}`
                    : "No physician linked"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {!u.is_active && <Badge tone="red">Disabled</Badge>}
                <Select value={u.role} onChange={(e) => updateRole(u.id, e.target.value as UserRole)} className="w-32">
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {titleCase(r)}
                    </option>
                  ))}
                </Select>
                <Button size="sm" variant="ghost" onClick={() => resendInvite(u.id)}>
                  Re-send invite
                </Button>
                {u.id !== me?.id && (
                  <Button size="sm" variant="ghost" onClick={() => toggleActive(u)}>
                    {u.is_active ? "Disable" : "Enable"}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

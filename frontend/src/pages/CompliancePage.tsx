import { useState } from "react";
import { useAuth, isScheduler } from "../lib/auth";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { Credential, CredentialType, Physician } from "../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, PageHeader, Select } from "../components/ui";
import { formatShortDate, titleCase } from "../lib/format";

const CREDENTIAL_TYPES: CredentialType[] = [
  "state_license",
  "dea",
  "board_certification",
  "malpractice_insurance",
  "acls",
  "bls",
  "pals",
  "hospital_privileges",
  "other",
];

function expiryTone(expiresOn: string | null): "slate" | "green" | "amber" | "red" {
  if (!expiresOn) return "slate";
  const days = (new Date(expiresOn).getTime() - Date.now()) / 86_400_000;
  if (days < 0) return "red";
  if (days <= 60) return "amber";
  return "green";
}

export function CompliancePage() {
  const { user } = useAuth();
  const scheduler = isScheduler(user);

  return (
    <div>
      <PageHeader title="Compliance" subtitle="Licenses, certifications, and insurance -- tracked and expiring on schedule." />
      <div className="space-y-6">
        {scheduler && <OrgCompliance />}
        {user?.physician_id && !scheduler && <MyCredentials physicianId={user.physician_id} />}
      </div>
    </div>
  );
}

function MyCredentials({ physicianId }: { physicianId: string }) {
  const credentials = useFetch(() => api.get<Credential[]>("/credentials", { physician_id: physicianId }), [physicianId]);
  return (
    <Card>
      <CardHeader title="Your credentials" subtitle="Ask an admin to add or update these" />
      <CredentialTable credentials={credentials.data ?? []} />
    </Card>
  );
}

function OrgCompliance() {
  const [withinDays, setWithinDays] = useState(60);
  const expiring = useFetch(() => api.get<Credential[]>("/credentials/expiring", { within_days: withinDays }), [withinDays]);
  const physicians = useFetch(() => api.get<Physician[]>("/physicians"), []);
  const allCredentials = useFetch(() => api.get<Credential[]>("/credentials"), []);
  const physicianById = new Map((physicians.data ?? []).map((p) => [p.id, p]));

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Expiring soon"
          subtitle="The risk dashboard -- an expired license or malpractice policy is a shift that legally can't be worked."
          action={
            <Select value={withinDays} onChange={(e) => setWithinDays(Number(e.target.value))} className="w-36">
              <option value={30}>Within 30 days</option>
              <option value={60}>Within 60 days</option>
              <option value={90}>Within 90 days</option>
              <option value={180}>Within 180 days</option>
            </Select>
          }
        />
        {expiring.data && expiring.data.length === 0 ? (
          <EmptyState title="Nothing expiring in this window" />
        ) : (
          <div className="divide-y divide-slate-100">
            {(expiring.data ?? []).map((c) => {
              const p = physicianById.get(c.physician_id);
              return (
                <div key={c.id} className="flex items-center justify-between px-5 py-3 text-sm">
                  <div>
                    <p className="font-medium text-slate-800">
                      {p ? `${p.first_name} ${p.last_name}` : "Unknown"} — {titleCase(c.credential_type)}
                    </p>
                    <p className="text-xs text-slate-400">
                      {c.issuing_state && `${c.issuing_state} · `}
                      {c.identifier}
                    </p>
                  </div>
                  <Badge tone={expiryTone(c.expires_on)}>{c.expires_on ? formatShortDate(c.expires_on) : "No expiry"}</Badge>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <AddCredentialCard physicians={physicians.data ?? []} onCreated={() => { expiring.reload(); allCredentials.reload(); }} />

      <Card>
        <CardHeader title="All credentials" />
        <CredentialTable
          credentials={allCredentials.data ?? []}
          physicianById={physicianById}
          onDelete={async (id) => {
            await api.delete(`/credentials/${id}`);
            expiring.reload();
            allCredentials.reload();
          }}
        />
      </Card>
    </div>
  );
}

function CredentialTable({
  credentials,
  physicianById,
  onDelete,
}: {
  credentials: Credential[];
  physicianById?: Map<string, Physician>;
  onDelete?: (id: string) => void;
}) {
  if (credentials.length === 0) return <EmptyState title="No credentials on file" />;
  return (
    <div className="divide-y divide-slate-100">
      {credentials.map((c) => (
        <div key={c.id} className="flex items-center justify-between px-5 py-3 text-sm">
          <div>
            <p className="font-medium text-slate-800">
              {physicianById && `${physicianById.get(c.physician_id)?.first_name ?? "Unknown"} ${physicianById.get(c.physician_id)?.last_name ?? ""} — `}
              {titleCase(c.credential_type)}
            </p>
            <p className="text-xs text-slate-400">
              {c.issuing_state && `${c.issuing_state} · `}
              {c.identifier}
              {c.note && ` · ${c.note}`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={expiryTone(c.expires_on)}>{c.expires_on ? formatShortDate(c.expires_on) : "No expiry"}</Badge>
            {onDelete && (
              <button className="text-xs text-slate-400 hover:text-red-600" onClick={() => onDelete(c.id)}>
                Remove
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function AddCredentialCard({ physicians, onCreated }: { physicians: Physician[]; onCreated: () => void }) {
  const [physicianId, setPhysicianId] = useState("");
  const [type, setType] = useState<CredentialType>("state_license");
  const [state, setState] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [expiresOn, setExpiresOn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!physicianId) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/credentials", {
        physician_id: physicianId,
        credential_type: type,
        issuing_state: state || undefined,
        identifier: identifier || undefined,
        expires_on: expiresOn || undefined,
      });
      setState("");
      setIdentifier("");
      setExpiresOn("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to add");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Add a credential" />
      <form onSubmit={submit} className="grid grid-cols-2 gap-3 px-5 py-4 md:grid-cols-5">
        <Field label="Physician">
          <Select required value={physicianId} onChange={(e) => setPhysicianId(e.target.value)}>
            <option value="">Select…</option>
            {physicians.map((p) => (
              <option key={p.id} value={p.id}>
                {p.first_name} {p.last_name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Type">
          <Select value={type} onChange={(e) => setType(e.target.value as CredentialType)}>
            {CREDENTIAL_TYPES.map((t) => (
              <option key={t} value={t}>
                {titleCase(t)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="State">
          <Input maxLength={2} value={state} onChange={(e) => setState(e.target.value.toUpperCase())} placeholder="CA" />
        </Field>
        <Field label="Identifier">
          <Input value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="License #" />
        </Field>
        <Field label="Expires">
          <Input type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
        </Field>
        <div className="col-span-2 md:col-span-5">
          {error && <ErrorBanner message={error} />}
          <Button type="submit" disabled={busy || !physicianId} className="mt-2">
            {busy ? "Adding…" : "Add credential"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

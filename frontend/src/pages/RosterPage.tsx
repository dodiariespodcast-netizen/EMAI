import { useEffect, useState } from "react";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { EmploymentType, Physician, Site } from "../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, PageHeader, Select } from "../components/ui";
import { titleCase } from "../lib/format";
import { RosterImportCard } from "../components/RosterImportCard";

const EMPLOYMENT_TYPES: EmploymentType[] = ["employed", "locums", "contract", "moonlighter"];

interface FormState {
  first_name: string;
  last_name: string;
  email: string;
  fte: number;
  seniority_years: number;
  employment_type: EmploymentType;
  hourly_rate: string;
  night_preference: number;
  weekend_preference: number;
  holiday_preference: number;
  site_ids: string[];
}

const BLANK: FormState = {
  first_name: "",
  last_name: "",
  email: "",
  fte: 1,
  seniority_years: 0,
  employment_type: "employed",
  hourly_rate: "",
  night_preference: 0,
  weekend_preference: 0,
  holiday_preference: 0,
  site_ids: [],
};

export function RosterPage() {
  const physicians = useFetch(() => api.get<Physician[]>("/physicians", { active_only: false }), []);
  const sites = useFetch(() => api.get<Site[]>("/sites"), []);
  const [editing, setEditing] = useState<Physician | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showImport, setShowImport] = useState(false);

  return (
    <div>
      <PageHeader
        title="Roster"
        subtitle="Your physicians -- FTE, preferences, employment type, and site eligibility feed directly into the optimizer."
        action={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setShowImport((s) => !s)}>
              {showImport ? "Close import" : "Import CSV"}
            </Button>
            <Button
              onClick={() => {
                setEditing(null);
                setShowForm((s) => !s);
              }}
            >
              {showForm && !editing ? "Close" : "Add physician"}
            </Button>
          </div>
        }
      />

      {showImport && (
        <div className="mb-6">
          <RosterImportCard
            sites={sites.data ?? []}
            onImported={() => {
              physicians.reload();
              setShowImport(false);
            }}
          />
        </div>
      )}

      {(showForm || editing) && (
        <div className="mb-6">
          <PhysicianForm
            key={editing?.id ?? "new"}
            sites={sites.data ?? []}
            physician={editing}
            onDone={() => {
              setEditing(null);
              setShowForm(false);
              physicians.reload();
            }}
            onCancel={() => {
              setEditing(null);
              setShowForm(false);
            }}
          />
        </div>
      )}

      <Card>
        {physicians.data && physicians.data.length === 0 ? (
          <EmptyState title="No physicians yet" hint="Add your first physician to get started." />
        ) : (
          <div className="divide-y divide-slate-100">
            {(physicians.data ?? []).map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-800">
                    {p.first_name} {p.last_name}
                    {!p.is_active && <span className="ml-2 text-xs text-slate-400">(inactive)</span>}
                  </p>
                  <p className="truncate text-xs text-slate-400">
                    {p.email} · FTE {p.fte.toFixed(2)} · {p.site_ids.length} site(s)
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge tone={p.employment_type === "employed" ? "slate" : "purple"}>{titleCase(p.employment_type)}</Badge>
                  <Button size="sm" variant="secondary" onClick={() => { setEditing(p); setShowForm(true); }}>
                    Edit
                  </Button>
                  {p.is_active && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={async () => {
                        await api.delete(`/physicians/${p.id}`);
                        physicians.reload();
                      }}
                    >
                      Deactivate
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function PhysicianForm({
  sites,
  physician,
  onDone,
  onCancel,
}: {
  sites: Site[];
  physician: Physician | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<FormState>(BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (physician) {
      setForm({
        first_name: physician.first_name,
        last_name: physician.last_name,
        email: physician.email,
        fte: physician.fte,
        seniority_years: physician.seniority_years,
        employment_type: physician.employment_type,
        hourly_rate: physician.hourly_rate?.toString() ?? "",
        night_preference: physician.night_preference,
        weekend_preference: physician.weekend_preference,
        holiday_preference: physician.holiday_preference,
        site_ids: physician.site_ids,
      });
    } else {
      setForm(BLANK);
    }
  }, [physician]);

  function toggleSite(id: string) {
    setForm((f) => ({
      ...f,
      site_ids: f.site_ids.includes(id) ? f.site_ids.filter((s) => s !== id) : [...f.site_ids, id],
    }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const payload = {
      first_name: form.first_name,
      last_name: form.last_name,
      email: form.email,
      fte: form.fte,
      seniority_years: form.seniority_years,
      employment_type: form.employment_type,
      hourly_rate: form.hourly_rate ? Number(form.hourly_rate) : null,
      night_preference: form.night_preference,
      weekend_preference: form.weekend_preference,
      holiday_preference: form.holiday_preference,
      site_ids: form.site_ids,
    };
    try {
      if (physician) {
        await api.patch(`/physicians/${physician.id}`, payload);
      } else {
        await api.post("/physicians", payload);
      }
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title={physician ? `Edit ${physician.first_name} ${physician.last_name}` : "New physician"} />
      <form onSubmit={submit} className="space-y-4 px-5 py-4">
        {error && <ErrorBanner message={error} />}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Field label="First name">
            <Input required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          </Field>
          <Field label="Last name">
            <Input required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          </Field>
          <Field label="Email">
            <Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </Field>
          <Field label="FTE">
            <Input type="number" min={0} max={1} step={0.1} value={form.fte} onChange={(e) => setForm({ ...form, fte: Number(e.target.value) })} />
          </Field>
          <Field label="Seniority (years)">
            <Input type="number" min={0} value={form.seniority_years} onChange={(e) => setForm({ ...form, seniority_years: Number(e.target.value) })} />
          </Field>
          <Field label="Employment type">
            <Select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value as EmploymentType })}>
              {EMPLOYMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Hourly rate (optional)">
            <Input type="number" min={0} step={0.01} value={form.hourly_rate} onChange={(e) => setForm({ ...form, hourly_rate: e.target.value })} />
          </Field>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Night preference">
            <Select value={form.night_preference} onChange={(e) => setForm({ ...form, night_preference: Number(e.target.value) })}>
              {[-2, -1, 0, 1, 2].map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Weekend preference">
            <Select value={form.weekend_preference} onChange={(e) => setForm({ ...form, weekend_preference: Number(e.target.value) })}>
              {[-2, -1, 0, 1, 2].map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Holiday preference">
            <Select value={form.holiday_preference} onChange={(e) => setForm({ ...form, holiday_preference: Number(e.target.value) })}>
              {[-2, -1, 0, 1, 2].map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-600">Eligible sites</p>
          <div className="flex flex-wrap gap-2">
            {sites.length === 0 && <p className="text-xs text-slate-400">Add a site first.</p>}
            {sites.map((s) => (
              <label
                key={s.id}
                className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${
                  form.site_ids.includes(s.id) ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-300 text-slate-600"
                }`}
              >
                <input type="checkbox" className="hidden" checked={form.site_ids.includes(s.id)} onChange={() => toggleSite(s.id)} />
                {s.name}
              </label>
            ))}
          </div>
        </div>

        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : physician ? "Save changes" : "Add physician"}
          </Button>
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

import { useState } from "react";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { ShiftCategory, ShiftInstance, ShiftType, Site } from "../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, PageHeader, Select, SuccessBanner } from "../components/ui";
import { titleCase } from "../lib/format";

export function ShiftsPage() {
  const sites = useFetch(() => api.get<Site[]>("/sites"), []);
  const [siteId, setSiteId] = useState("");
  const activeSiteId = siteId || sites.data?.[0]?.id || "";
  const shiftTypes = useFetch(
    () => (activeSiteId ? api.get<ShiftType[]>("/shift-types", { site_id: activeSiteId }) : Promise.resolve([])),
    [activeSiteId],
  );

  return (
    <div>
      <PageHeader title="Sites & Shifts" subtitle="Define locations and recurring shift patterns, then generate a date range of coverage needs." />

      <div className="grid gap-4 lg:grid-cols-2">
        <SitesCard sites={sites.data ?? []} onCreated={sites.reload} />

        <Card>
          <CardHeader
            title="Shift types"
            action={
              sites.data && sites.data.length > 0 ? (
                <Select value={activeSiteId} onChange={(e) => setSiteId(e.target.value)} className="w-40">
                  {sites.data.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </Select>
              ) : null
            }
          />
          {!activeSiteId ? (
            <EmptyState title="Add a site first" />
          ) : (
            <>
              <div className="divide-y divide-slate-100 border-b border-slate-100">
                {(shiftTypes.data ?? []).length === 0 && <p className="px-5 py-3 text-xs text-slate-400">No shift types yet.</p>}
                {(shiftTypes.data ?? []).map((st) => (
                  <div key={st.id} className="flex items-center justify-between px-5 py-2.5 text-sm">
                    <div>
                      <p className="font-medium text-slate-800">{st.name}</p>
                      <p className="text-xs text-slate-400">
                        {st.start_time.slice(0, 5)}–{st.end_time.slice(0, 5)} · {st.duration_hours}h · needs {st.required_physicians}
                      </p>
                    </div>
                    <Badge tone="blue">{titleCase(st.category)}</Badge>
                  </div>
                ))}
              </div>
              <NewShiftTypeForm siteId={activeSiteId} onCreated={shiftTypes.reload} />
            </>
          )}
        </Card>
      </div>

      <div className="mt-4">
        <GenerateInstancesCard siteId={activeSiteId} shiftTypes={shiftTypes.data ?? []} />
      </div>
    </div>
  );
}

function SitesCard({ sites, onCreated }: { sites: Site[]; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("America/New_York");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/sites", { name, timezone });
      setName("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to add site");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Sites" subtitle="Locations/departments you staff -- one org can span many, e.g. a locums agency's client facilities" />
      <div className="divide-y divide-slate-100 border-b border-slate-100">
        {sites.length === 0 && <p className="px-5 py-3 text-xs text-slate-400">No sites yet.</p>}
        {sites.map((s) => (
          <div key={s.id} className="px-5 py-2.5 text-sm">
            <p className="font-medium text-slate-800">{s.name}</p>
            <p className="text-xs text-slate-400">{s.timezone}</p>
          </div>
        ))}
      </div>
      <form onSubmit={submit} className="flex items-end gap-2 px-5 py-4">
        {error && (
          <div className="w-full">
            <ErrorBanner message={error} />
          </div>
        )}
        <div className="flex-1">
          <Field label="Site name">
            <Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Main ED" />
          </Field>
        </div>
        <div className="w-40">
          <Field label="Timezone">
            <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          </Field>
        </div>
        <Button type="submit" disabled={busy}>
          Add
        </Button>
      </form>
    </Card>
  );
}

function NewShiftTypeForm({ siteId, onCreated }: { siteId: string; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<ShiftCategory>("day");
  const [startTime, setStartTime] = useState("07:00");
  const [endTime, setEndTime] = useState("19:00");
  const [duration, setDuration] = useState(12);
  const [required, setRequired] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/shift-types", {
        site_id: siteId,
        name,
        category,
        start_time: `${startTime}:00`,
        end_time: `${endTime}:00`,
        duration_hours: duration,
        required_physicians: required,
      });
      setName("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to add shift type");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 px-5 py-4">
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name">
          <Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Day 07-19" />
        </Field>
        <Field label="Category">
          <Select value={category} onChange={(e) => setCategory(e.target.value as ShiftCategory)}>
            <option value="day">Day</option>
            <option value="night">Night</option>
            <option value="swing">Swing</option>
            <option value="admin">Admin</option>
          </Select>
        </Field>
      </div>
      <div className="grid grid-cols-4 gap-3">
        <Field label="Start">
          <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
        </Field>
        <Field label="End">
          <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
        </Field>
        <Field label="Hours">
          <Input type="number" min={0.5} max={24} step={0.5} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
        </Field>
        <Field label="Needs">
          <Input type="number" min={1} value={required} onChange={(e) => setRequired(Number(e.target.value))} />
        </Field>
      </div>
      <Button type="submit" disabled={busy}>
        {busy ? "Adding…" : "Add shift type"}
      </Button>
    </form>
  );
}

function GenerateInstancesCard({ siteId, shiftTypes }: { siteId: string; shiftTypes: ShiftType[] }) {
  const [shiftTypeId, setShiftTypeId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const created = await api.post<ShiftInstance[]>("/shift-instances/generate", {
        shift_type_id: shiftTypeId,
        start_date: start,
        end_date: end,
      });
      setSuccess(`Generated ${created.length} shift instance(s).`);
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to generate");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Generate coverage needs" subtitle="Stamps out one shift instance per day for a shift type over a date range." />
      <form onSubmit={submit} className="grid grid-cols-2 gap-3 px-5 py-4 md:grid-cols-4">
        <Field label="Shift type">
          <Select required value={shiftTypeId} onChange={(e) => setShiftTypeId(e.target.value)} disabled={!siteId}>
            <option value="">Select…</option>
            {shiftTypes.map((st) => (
              <option key={st.id} value={st.id}>
                {st.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="From">
          <Input type="date" required value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label="To">
          <Input type="date" required value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
        <div className="flex items-end">
          <Button type="submit" disabled={busy || !shiftTypeId} className="w-full">
            {busy ? "Generating…" : "Generate"}
          </Button>
        </div>
        <div className="col-span-2 md:col-span-4">
          {error && <ErrorBanner message={error} />}
          {success && <SuccessBanner message={success} />}
        </div>
      </form>
    </Card>
  );
}

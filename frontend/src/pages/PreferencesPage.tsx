import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { Physician, ShiftCategory, ShiftPreference } from "../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, PageHeader, Select, SuccessBanner } from "../components/ui";
import { formatShortDate } from "../lib/format";

const LEVELS: { value: number; label: string }[] = [
  { value: -2, label: "Strongly avoid" },
  { value: -1, label: "Avoid" },
  { value: 0, label: "No preference" },
  { value: 1, label: "Prefer" },
  { value: 2, label: "Strongly prefer" },
];

export function PreferencesPage() {
  const { user } = useAuth();
  if (!user?.physician_id) {
    return (
      <div>
        <PageHeader title="Preferences" />
        <EmptyState title="No physician profile linked" hint="Ask an admin to link your account to a physician record." />
      </div>
    );
  }
  return <PreferencesContent physicianId={user.physician_id} />;
}

function PreferencesContent({ physicianId }: { physicianId: string }) {
  const physician = useFetch(() => api.get<Physician>(`/physicians/${physicianId}`), [physicianId]);
  const scoped = useFetch(() => api.get<ShiftPreference[]>("/shift-preferences", { physician_id: physicianId }), [physicianId]);

  const [night, setNight] = useState(0);
  const [weekend, setWeekend] = useState(0);
  const [holiday, setHoliday] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (physician.data) {
      setNight(physician.data.night_preference);
      setWeekend(physician.data.weekend_preference);
      setHoliday(physician.data.holiday_preference);
    }
  }, [physician.data]);

  async function saveStanding() {
    setSaving(true);
    setSaved(false);
    try {
      await api.patch(`/physicians/${physicianId}/preferences`, {
        night_preference: night,
        weekend_preference: weekend,
        holiday_preference: holiday,
      });
      setSaved(true);
      physician.reload();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <PageHeader title="Preferences" subtitle="Tell the scheduler what you want more or less of. These weigh directly into the optimizer." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Standing preferences" subtitle="Applies to every schedule unless overridden below" />
          <div className="space-y-4 px-5 py-4">
            <PreferenceSlider label="Night shifts" value={night} onChange={setNight} />
            <PreferenceSlider label="Weekend shifts" value={weekend} onChange={setWeekend} />
            <PreferenceSlider label="Holiday shifts" value={holiday} onChange={setHoliday} />
            {saved && <SuccessBanner message="Saved." />}
            <Button onClick={saveStanding} disabled={saving}>
              {saving ? "Saving…" : "Save preferences"}
            </Button>
          </div>
        </Card>

        <ScopedPreferences physicianId={physicianId} preferences={scoped.data ?? []} onCreated={scoped.reload} />
      </div>
    </div>
  );
}

function PreferenceSlider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <span className="text-xs text-slate-400">{LEVELS.find((l) => l.value === value)?.label}</span>
      </div>
      <input
        type="range"
        min={-2}
        max={2}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-brand-600"
      />
    </div>
  );
}

function ScopedPreferences({
  physicianId,
  preferences,
  onCreated,
}: {
  physicianId: string;
  preferences: ShiftPreference[];
  onCreated: () => void;
}) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [category, setCategory] = useState<ShiftCategory>("night");
  const [level, setLevel] = useState(-2);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/shift-preferences", {
        physician_id: physicianId,
        effective_start: start,
        effective_end: end,
        category,
        level,
        note: note || undefined,
      });
      setStart("");
      setEnd("");
      setNote("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Time-scoped preferences" subtitle='e.g. "avoid nights in December"' />
      <div className="space-y-4 px-5 py-4">
        {error && <ErrorBanner message={error} />}
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="From">
              <Input type="date" required value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
            <Field label="To">
              <Input type="date" required value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Category">
              <Select value={category} onChange={(e) => setCategory(e.target.value as ShiftCategory)}>
                <option value="night">Night</option>
                <option value="day">Day</option>
                <option value="swing">Swing</option>
              </Select>
            </Field>
            <Field label="Preference">
              <Select value={level} onChange={(e) => setLevel(Number(e.target.value))}>
                {LEVELS.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Note (optional)">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Kid's school schedule, etc." />
          </Field>
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Add"}
          </Button>
        </form>

        <div className="divide-y divide-slate-100 border-t border-slate-100">
          {preferences.length === 0 && <p className="py-3 text-xs text-slate-400">No time-scoped preferences yet.</p>}
          {preferences.map((p) => (
            <div key={p.id} className="flex items-center justify-between py-2 text-sm">
              <div>
                <p className="text-slate-700">
                  {formatShortDate(p.effective_start)} – {formatShortDate(p.effective_end)}
                </p>
                <p className="text-xs text-slate-400">
                  {p.category} · {LEVELS.find((l) => l.value === p.level)?.label}
                  {p.note && ` · ${p.note}`}
                </p>
              </div>
              <Badge tone={p.level < 0 ? "red" : p.level > 0 ? "green" : "slate"}>{p.level > 0 ? `+${p.level}` : p.level}</Badge>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

import { useEffect, useState } from "react";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { SchedulingRule } from "../lib/types";
import { Button, Card, CardHeader, ErrorBanner, Field, Input, PageHeader, SuccessBanner } from "../components/ui";

export function RulesPage() {
  const rules = useFetch(() => api.get<SchedulingRule>("/scheduling-rules"), []);
  const [form, setForm] = useState<SchedulingRule | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (rules.data) setForm(rules.data);
  }, [rules.data]);

  async function save() {
    if (!form) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api.patch("/scheduling-rules", {
        max_consecutive_shifts: form.max_consecutive_shifts,
        min_rest_hours: form.min_rest_hours,
        max_nights_in_a_row: form.max_nights_in_a_row,
        weight_unfilled_shift: form.weight_unfilled_shift,
        weight_fairness: form.weight_fairness,
        weight_preference: form.weight_preference,
        weight_preferred_time_off: form.weight_preferred_time_off,
        weight_seniority: form.weight_seniority,
      });
      setSaved(true);
      rules.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  if (!form) return null;

  return (
    <div>
      <PageHeader title="Scheduling Rules" subtitle="Hard limits the solver never breaks, and weighted dials for what it optimizes toward." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Hard limits" subtitle="Never violated, regardless of the weights below" />
          <div className="space-y-4 px-5 py-4">
            <Field label="Max consecutive working days">
              <Input
                type="number"
                min={1}
                max={14}
                value={form.max_consecutive_shifts}
                onChange={(e) => setForm({ ...form, max_consecutive_shifts: Number(e.target.value) })}
              />
            </Field>
            <Field label="Minimum rest between shifts (hours)">
              <Input
                type="number"
                min={0}
                max={48}
                value={form.min_rest_hours}
                onChange={(e) => setForm({ ...form, min_rest_hours: Number(e.target.value) })}
              />
            </Field>
            <Field label="Max consecutive nights">
              <Input
                type="number"
                min={1}
                max={14}
                value={form.max_nights_in_a_row}
                onChange={(e) => setForm({ ...form, max_nights_in_a_row: Number(e.target.value) })}
              />
            </Field>
          </div>
        </Card>

        <Card>
          <CardHeader title="Optimization weights" subtitle="Relative importance -- tune your scheduling philosophy" />
          <div className="space-y-4 px-5 py-4">
            <WeightSlider
              label="Fill every shift"
              value={form.weight_unfilled_shift}
              max={2000}
              onChange={(v) => setForm({ ...form, weight_unfilled_shift: v })}
              hint="How hard the solver fights to avoid leaving a shift unfilled"
            />
            <WeightSlider
              label="Fairness"
              value={form.weight_fairness}
              max={30}
              onChange={(v) => setForm({ ...form, weight_fairness: v })}
              hint="Even workload distribution by FTE, incl. nights & weekends"
            />
            <WeightSlider
              label="Preference satisfaction"
              value={form.weight_preference}
              max={20}
              onChange={(v) => setForm({ ...form, weight_preference: v })}
              hint="Night/day/weekend/holiday preferences"
            />
            <WeightSlider
              label="Honor preferred time off"
              value={form.weight_preferred_time_off}
              max={20}
              onChange={(v) => setForm({ ...form, weight_preferred_time_off: v })}
            />
            <WeightSlider
              label="Seniority skew"
              value={form.weight_seniority}
              max={5}
              step={0.1}
              onChange={(v) => setForm({ ...form, weight_seniority: v })}
              hint="0 disables seniority weighting entirely"
            />
          </div>
        </Card>
      </div>

      <div className="mt-4">
        {error && <ErrorBanner message={error} />}
        {saved && <SuccessBanner message="Saved. Future schedule runs will use these rules." />}
        <Button className="mt-2" onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Save rules"}
        </Button>
      </div>
    </div>
  );
}

function WeightSlider({
  label,
  value,
  max,
  step = 1,
  hint,
  onChange,
}: {
  label: string;
  value: number;
  max: number;
  step?: number;
  hint?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <span className="text-xs text-slate-400">{value}</span>
      </div>
      <input type="range" min={0} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-brand-600" />
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

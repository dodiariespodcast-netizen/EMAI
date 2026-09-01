import { useState } from "react";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { FairnessRow, ScheduleRun, ScheduleRunDetail, Site } from "../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, PageHeader, Select, Spinner, StatCard } from "../components/ui";
import { formatDate } from "../lib/format";

const RUN_STATUS_TONE: Record<string, "slate" | "green" | "amber"> = {
  draft: "amber",
  published: "green",
  archived: "slate",
};

export function GeneratePage() {
  const sites = useFetch(() => api.get<Site[]>("/sites"), []);
  const [siteId, setSiteId] = useState("");
  const activeSiteId = siteId || sites.data?.[0]?.id || "";
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScheduleRunDetail | null>(null);
  const [fairness, setFairness] = useState<FairnessRow[] | null>(null);

  const runs = useFetch(
    () => (activeSiteId ? api.get<ScheduleRun[]>("/schedule-runs", { site_id: activeSiteId }) : Promise.resolve([])),
    [activeSiteId],
  );

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    setFairness(null);
    try {
      const run = await api.post<ScheduleRunDetail>("/schedule-runs/generate", {
        site_id: activeSiteId,
        period_start: start,
        period_end: end,
        generate_ai_summary: true,
      });
      setResult(run);
      setFairness(await api.get<FairnessRow[]>(`/schedule-runs/${run.id}/fairness`));
      runs.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to generate");
    } finally {
      setBusy(false);
    }
  }

  async function publish(runId: string) {
    await api.post(`/schedule-runs/${runId}/publish`);
    runs.reload();
    if (result?.id === runId) setResult({ ...result, status: "published" });
  }

  async function viewRun(runId: string) {
    setBusy(true);
    setError(null);
    try {
      const run = await api.get<ScheduleRunDetail>(`/schedule-runs/${runId}`);
      setResult(run);
      setFairness(await api.get<FairnessRow[]>(`/schedule-runs/${runId}/fairness`));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title="Generate Schedule" subtitle="Runs the constraint solver over a date range and produces a draft you can review before publishing." />

      <Card className="mb-6">
        <CardHeader title="New run" />
        <form onSubmit={generate} className="grid grid-cols-2 gap-3 px-5 py-4 md:grid-cols-4">
          <Field label="Site">
            <Select value={activeSiteId} onChange={(e) => setSiteId(e.target.value)}>
              {(sites.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Period start">
            <Input type="date" required value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="Period end">
            <Input type="date" required value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
          <div className="flex items-end">
            <Button type="submit" disabled={busy || !activeSiteId} className="w-full">
              {busy ? (
                <>
                  <Spinner className="h-4 w-4" /> Solving…
                </>
              ) : (
                "Generate"
              )}
            </Button>
          </div>
          {error && (
            <div className="col-span-2 md:col-span-4">
              <ErrorBanner message={error} />
            </div>
          )}
        </form>
      </Card>

      {result && (
        <Card className="mb-6">
          <CardHeader
            title={`Run: ${formatDate(result.period_start)} – ${formatDate(result.period_end)}`}
            action={
              <div className="flex items-center gap-2">
                <Badge tone={RUN_STATUS_TONE[result.status]}>{result.status}</Badge>
                {result.status === "draft" && <Button size="sm" onClick={() => publish(result.id)}>Publish</Button>}
              </div>
            }
          />
          <div className="grid grid-cols-2 gap-3 px-5 py-4 md:grid-cols-4">
            <StatCard label="Solver status" value={result.solver_status ?? "—"} />
            <StatCard label="Unfilled shifts" value={result.unfilled_shift_count} tone={result.unfilled_shift_count > 0 ? "amber" : "green"} />
            <StatCard label="Solve time" value={result.solve_seconds ? `${result.solve_seconds.toFixed(1)}s` : "—"} />
            <StatCard label="Assignments" value={result.assignments.length} />
          </div>
          {result.ai_summary && (
            <div className="mx-5 mb-5 rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-900">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-brand-500">AI summary</p>
              <p className="whitespace-pre-line">{result.ai_summary}</p>
            </div>
          )}
          {fairness && (
            <div className="border-t border-slate-100 px-5 py-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Fairness</p>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-xs text-slate-400">
                      <th className="pb-2 pr-4">Physician</th>
                      <th className="pb-2 pr-4">Shifts</th>
                      <th className="pb-2 pr-4">Target</th>
                      <th className="pb-2 pr-4">Nights</th>
                      <th className="pb-2 pr-4">Weekends</th>
                      <th className="pb-2 pr-4">Requests honored</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fairness.map((row) => (
                      <tr key={row.physician_id} className="border-t border-slate-50">
                        <td className="py-1.5 pr-4 font-medium text-slate-700">{row.physician_name}</td>
                        <td className="py-1.5 pr-4">{row.total_shifts}</td>
                        <td className="py-1.5 pr-4 text-slate-400">{row.target_shifts}</td>
                        <td className="py-1.5 pr-4">{row.night_shifts}</td>
                        <td className="py-1.5 pr-4">{row.weekend_shifts}</td>
                        <td className="py-1.5 pr-4">
                          {row.preferred_requests_total > 0 ? `${row.preferred_requests_granted}/${row.preferred_requests_total}` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Card>
      )}

      <Card>
        <CardHeader title="Previous runs" />
        {runs.data && runs.data.length === 0 ? (
          <EmptyState title="No runs yet for this site" />
        ) : (
          <div className="divide-y divide-slate-100">
            {(runs.data ?? []).map((r) => (
              <div key={r.id} className="flex items-center justify-between px-5 py-2.5 text-sm">
                <div>
                  <p className="font-medium text-slate-700">
                    {formatDate(r.period_start)} – {formatDate(r.period_end)}
                  </p>
                  <p className="text-xs text-slate-400">{r.unfilled_shift_count} unfilled</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={RUN_STATUS_TONE[r.status]}>{r.status}</Badge>
                  <Button size="sm" variant="secondary" onClick={() => viewRun(r.id)}>
                    View
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

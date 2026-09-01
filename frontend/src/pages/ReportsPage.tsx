import { useState } from "react";
import { useFetch } from "../lib/hooks";
import { api, API_BASE_URL } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { CoverageReport, HoursReport, Site } from "../lib/types";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  PageHeader,
  Select,
  Spinner,
  StatCard,
} from "../components/ui";
import { formatShortDate, titleCase } from "../lib/format";

function firstOfThisMonth(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
}

function lastOfThisMonth(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
}

const currency = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function ReportsPage() {
  const { token } = useAuth();
  const sites = useFetch(() => api.get<Site[]>("/sites"), []);
  const [start, setStart] = useState(firstOfThisMonth);
  const [end, setEnd] = useState(lastOfThisMonth);
  const [siteId, setSiteId] = useState("");

  const params = { start_date: start, end_date: end, site_id: siteId || undefined };
  const hours = useFetch(() => api.get<HoursReport>("/reports/hours", params), [start, end, siteId]);
  const coverage = useFetch(() => api.get<CoverageReport>("/reports/coverage", params), [start, end, siteId]);

  async function downloadCsv() {
    // Fetched rather than linked so the Authorization header goes with it.
    const url = new URL("/reports/hours.csv", API_BASE_URL);
    url.searchParams.set("start_date", start);
    url.searchParams.set("end_date", end);
    if (siteId) url.searchParams.set("site_id", siteId);

    const res = await fetch(url.toString(), { headers: { Authorization: `Bearer ${token}` } });
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `hours-${start}-to-${end}.csv`;
    link.click();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Hours and cost for payroll or client billing, and where coverage is still short."
      />

      <Card className="mb-6">
        <CardHeader title="Period" />
        <div className="grid grid-cols-2 gap-3 px-5 py-4 md:grid-cols-4">
          <Field label="From">
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="To">
            <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
          <Field label="Site">
            <Select value={siteId} onChange={(e) => setSiteId(e.target.value)}>
              <option value="">All sites</option>
              {(sites.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex items-end">
            <button
              onClick={downloadCsv}
              className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Download CSV
            </button>
          </div>
        </div>
      </Card>

      {hours.error && <div className="mb-4"><ErrorBanner message={hours.error} /></div>}

      <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Shifts" value={hours.data?.total_shifts ?? "—"} />
        <StatCard label="Hours" value={hours.data?.total_hours ?? "—"} />
        <StatCard
          label="Est. cost"
          value={hours.data ? currency.format(hours.data.total_estimated_cost) : "—"}
          hint={
            hours.data && hours.data.physicians_missing_rate.length > 0
              ? `Excludes ${hours.data.physicians_missing_rate.length} physician(s) with no rate on file`
              : undefined
          }
        />
        <StatCard
          label="Coverage"
          value={coverage.data ? `${Math.round(coverage.data.coverage_rate * 100)}%` : "—"}
          tone={coverage.data && coverage.data.coverage_rate < 1 ? "amber" : "green"}
          hint={coverage.data ? `${coverage.data.staffed_slots}/${coverage.data.required_slots} slots` : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader title="Hours by physician" subtitle="Scheduled hours -- the basis for payroll or client invoicing" />
          {hours.loading ? (
            <div className="flex justify-center py-10">
              <Spinner className="h-5 w-5 text-brand-500" />
            </div>
          ) : (hours.data?.rows.length ?? 0) === 0 ? (
            <EmptyState title="No published shifts in this period" hint="Publish a schedule covering these dates." />
          ) : (
            <div className="overflow-x-auto px-5 py-4">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-xs text-slate-400">
                    <th className="pb-2 pr-4">Physician</th>
                    <th className="pb-2 pr-4">Type</th>
                    <th className="pb-2 pr-4 text-right">Shifts</th>
                    <th className="pb-2 pr-4 text-right">Hours</th>
                    <th className="pb-2 pr-4 text-right">Nights</th>
                    <th className="pb-2 pr-4 text-right">Wknd</th>
                    <th className="pb-2 pr-4 text-right">Rate</th>
                    <th className="pb-2 text-right">Est. cost</th>
                  </tr>
                </thead>
                <tbody>
                  {(hours.data?.rows ?? []).map((row) => (
                    <tr key={row.physician_id} className="border-t border-slate-50">
                      <td className="py-1.5 pr-4 font-medium text-slate-700">{row.physician_name}</td>
                      <td className="py-1.5 pr-4">
                        <Badge tone={row.employment_type === "employed" ? "slate" : "purple"}>
                          {titleCase(row.employment_type)}
                        </Badge>
                      </td>
                      <td className="py-1.5 pr-4 text-right">{row.shifts}</td>
                      <td className="py-1.5 pr-4 text-right">{row.hours}</td>
                      <td className="py-1.5 pr-4 text-right text-slate-500">{row.night_hours}</td>
                      <td className="py-1.5 pr-4 text-right text-slate-500">{row.weekend_hours}</td>
                      <td className="py-1.5 pr-4 text-right text-slate-500">
                        {row.hourly_rate === null ? "—" : currency.format(row.hourly_rate)}
                      </td>
                      <td className="py-1.5 text-right font-medium">
                        {row.estimated_cost === null ? (
                          <span className="text-xs font-normal text-amber-600">no rate</span>
                        ) : (
                          currency.format(row.estimated_cost)
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Coverage gaps" subtitle="Shifts still short of the required headcount" />
          {(coverage.data?.gaps.length ?? 0) === 0 ? (
            <EmptyState title="Fully covered" hint="Every shift in this period is staffed to its requirement." />
          ) : (
            <div className="divide-y divide-slate-100">
              {(coverage.data?.gaps ?? []).map((gap) => (
                <div key={gap.shift_instance_id} className="flex items-center justify-between px-5 py-2.5 text-sm">
                  <div>
                    <p className="font-medium text-slate-700">{formatShortDate(gap.date)}</p>
                    <p className="text-xs text-slate-400">{gap.shift_type}</p>
                  </div>
                  <Badge tone="red">short {gap.short_by}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

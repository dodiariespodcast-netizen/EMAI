import { useMemo, useState } from "react";
import { useAuth, isScheduler } from "../lib/auth";
import { useFetch } from "../lib/hooks";
import { api } from "../lib/api";
import type { Assignment, Physician, ScheduleRun, ShiftInstance, ShiftType, Site } from "../lib/types";
import { addMonths, buildMonthGrid, endOfMonth, monthLabel, startOfMonth, toIsoDate } from "../lib/calendar";
import { Card, PageHeader, Select, Spinner } from "../components/ui";
import { ShiftEditorPanel } from "../components/ShiftEditorPanel";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function SchedulePage() {
  const { user } = useAuth();
  const scheduler = isScheduler(user);
  const [editingShiftId, setEditingShiftId] = useState<string | null>(null);
  const sites = useFetch(() => api.get<Site[]>("/sites"), []);
  const [siteId, setSiteId] = useState<string>("");
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [onlyMine, setOnlyMine] = useState(!!user?.physician_id);

  const activeSiteId = siteId || sites.data?.[0]?.id || "";
  const monthStart = toIsoDate(startOfMonth(month));
  const monthEnd = toIsoDate(endOfMonth(month));

  const shiftTypes = useFetch(
    () => (activeSiteId ? api.get<ShiftType[]>("/shift-types", { site_id: activeSiteId }) : Promise.resolve([])),
    [activeSiteId],
  );
  const shiftInstances = useFetch(
    () =>
      activeSiteId
        ? api.get<ShiftInstance[]>("/shift-instances", { site_id: activeSiteId, start_date: monthStart, end_date: monthEnd })
        : Promise.resolve([]),
    [activeSiteId, monthStart, monthEnd],
  );
  const runs = useFetch(
    () => (activeSiteId ? api.get<ScheduleRun[]>("/schedule-runs", { site_id: activeSiteId }) : Promise.resolve([])),
    [activeSiteId],
  );
  const physicians = useFetch(() => api.get<Physician[]>("/physicians"), []);

  // Physicians only ever see published schedules; schedulers also see drafts,
  // since reviewing and fixing a draft before publishing is the job.
  const visibleRunIds = useMemo(
    () =>
      (runs.data ?? [])
        .filter(
          (r) =>
            (scheduler || r.status === "published") &&
            r.status !== "archived" &&
            r.period_start <= monthEnd &&
            r.period_end >= monthStart,
        )
        .map((r) => r.id),
    [runs.data, monthStart, monthEnd, scheduler],
  );

  const assignments = useFetch(async () => {
    if (visibleRunIds.length === 0) return [] as Assignment[];
    const details = await Promise.all(visibleRunIds.map((id) => api.get<{ assignments: Assignment[] }>(`/schedule-runs/${id}`)));
    return details.flatMap((d) => d.assignments);
  }, [visibleRunIds.join(",")]);

  const physicianById = useMemo(() => new Map((physicians.data ?? []).map((p) => [p.id, p])), [physicians.data]);
  const shiftTypeById = useMemo(() => new Map((shiftTypes.data ?? []).map((s) => [s.id, s])), [shiftTypes.data]);
  const assignmentsByShift = useMemo(() => {
    const map = new Map<string, Assignment[]>();
    for (const a of assignments.data ?? []) {
      const list = map.get(a.shift_instance_id) ?? [];
      list.push(a);
      map.set(a.shift_instance_id, list);
    }
    return map;
  }, [assignments.data]);
  const instancesByDate = useMemo(() => {
    const map = new Map<string, ShiftInstance[]>();
    for (const s of shiftInstances.data ?? []) {
      const list = map.get(s.date) ?? [];
      list.push(s);
      map.set(s.date, list);
    }
    return map;
  }, [shiftInstances.data]);

  const grid = useMemo(() => buildMonthGrid(month), [month]);
  const editingShift = (shiftInstances.data ?? []).find((s) => s.id === editingShiftId);
  const loading = shiftInstances.loading || runs.loading || assignments.loading;

  return (
    <div>
      <PageHeader
        title="Schedule"
        subtitle="Published shifts for the selected site and month."
        action={
          <div className="flex items-center gap-2">
            {user?.physician_id && (
              <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600">
                <input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} />
                My shifts only
              </label>
            )}
            {sites.data && sites.data.length > 1 && (
              <Select value={activeSiteId} onChange={(e) => setSiteId(e.target.value)} className="w-40">
                {sites.data.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            )}
          </div>
        }
      />

      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button onClick={() => setMonth((m) => addMonths(m, -1))} className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm hover:bg-slate-50">
            ←
          </button>
          <button onClick={() => setMonth((m) => addMonths(m, 1))} className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm hover:bg-slate-50">
            →
          </button>
          <button onClick={() => setMonth(startOfMonth(new Date()))} className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-500 hover:bg-slate-50">
            Today
          </button>
        </div>
        <h2 className="text-sm font-semibold text-slate-900">{monthLabel(month)}</h2>
        {loading && <Spinner className="h-4 w-4 text-brand-500" />}
      </div>

      <Card className="overflow-hidden">
        <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50 text-center text-xs font-medium text-slate-500">
          {WEEKDAYS.map((d) => (
            <div key={d} className="px-2 py-2">
              {d}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {grid.map((day) => {
            const dayInstances = instancesByDate.get(day.iso) ?? [];
            return (
              <div
                key={day.iso}
                className={`min-h-[6.5rem] border-b border-r border-slate-100 p-1.5 last:border-r-0 ${
                  day.inMonth ? "bg-white" : "bg-slate-50/60"
                }`}
              >
                <div className={`mb-1 text-xs ${day.isToday ? "font-bold text-brand-600" : "text-slate-400"}`}>
                  {day.date.getDate()}
                </div>
                <div className="space-y-1">
                  {dayInstances.map((instance) => {
                    const shiftType = shiftTypeById.get(instance.shift_type_id);
                    const shiftAssignments = assignmentsByShift.get(instance.id) ?? [];
                    const visible = onlyMine
                      ? shiftAssignments.filter((a) => a.physician_id === user?.physician_id)
                      : shiftAssignments;
                    if (onlyMine && visible.length === 0) return null;
                    const short = instance.required_physicians - shiftAssignments.length;
                    return (
                      <button
                        key={instance.id}
                        type="button"
                        disabled={!scheduler}
                        onClick={() => setEditingShiftId(instance.id)}
                        className={`w-full rounded-md px-1.5 py-1 text-left text-[11px] leading-tight ${
                          short > 0 ? "bg-red-50" : "bg-brand-50"
                        } ${scheduler ? "cursor-pointer hover:ring-1 hover:ring-brand-300" : "cursor-default"}`}
                      >
                        <p className={`font-medium ${short > 0 ? "text-red-700" : "text-brand-700"}`}>
                          {shiftType?.name ?? instance.category}
                        </p>
                        {visible.map((a) => {
                          const p = physicianById.get(a.physician_id);
                          const mine = a.physician_id === user?.physician_id;
                          return (
                            <p key={a.id} className={mine ? "font-semibold text-slate-900" : "text-slate-500"}>
                              {p ? `${p.first_name} ${p.last_name[0]}.` : "Unassigned"}
                            </p>
                          );
                        })}
                        {short > 0 && !onlyMine && <p className="text-red-500">Short {short}</p>}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded bg-brand-50 ring-1 ring-brand-200" /> staffed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded bg-red-50 ring-1 ring-red-200" /> short of its requirement
        </span>
        <span>
          {scheduler
            ? "Click any shift to assign, reassign, or remove someone. Drafts are visible to you until published."
            : "Only published schedules appear here."}
        </span>
      </div>

      {editingShift && (
        <ShiftEditorPanel
          shift={editingShift}
          shiftType={shiftTypeById.get(editingShift.shift_type_id)}
          assignments={assignmentsByShift.get(editingShift.id) ?? []}
          physicianById={physicianById}
          onClose={() => setEditingShiftId(null)}
          onChanged={() => {
            assignments.reload();
            runs.reload();
          }}
        />
      )}
    </div>
  );
}

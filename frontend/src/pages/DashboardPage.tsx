import { useAuth, isScheduler } from "../lib/auth";
import { useFetch } from "../lib/hooks";
import { api } from "../lib/api";
import type {
  Credential,
  Physician,
  ScheduleRun,
  ShiftInstance,
  ShiftSwapRequest,
  ShiftType,
  Site,
  TimeOffRequest,
} from "../lib/types";
import { Card, CardHeader, PageHeader, StatCard, Badge, EmptyState } from "../components/ui";
import { Link } from "react-router-dom";
import { SetupChecklist } from "../components/SetupChecklist";

export function DashboardPage() {
  const { user } = useAuth();
  const scheduler = isScheduler(user);

  return (
    <div>
      <PageHeader title={`Welcome back${user ? "" : ""}`} subtitle="Here's what's happening with your schedule." />
      <div className="space-y-6">
        {user?.physician_id && <PhysicianPanel physicianId={user.physician_id} />}
        {scheduler && <AdminPanel />}
      </div>
    </div>
  );
}

function PhysicianPanel({ physicianId }: { physicianId: string }) {
  const physician = useFetch(() => api.get<Physician>(`/physicians/${physicianId}`), [physicianId]);
  const pendingRequests = useFetch(
    () => api.get<TimeOffRequest[]>("/time-off-requests", { physician_id: physicianId, status_filter: "pending" }),
    [physicianId],
  );
  const mySwaps = useFetch(() => api.get<ShiftSwapRequest[]>("/shift-swaps", { physician_id: physicianId }), [physicianId]);
  const credentials = useFetch(() => api.get<Credential[]>("/credentials", { physician_id: physicianId }), [physicianId]);

  const expiring = (credentials.data ?? []).filter((c) => {
    if (!c.expires_on) return false;
    const days = (new Date(c.expires_on).getTime() - Date.now()) / 86_400_000;
    return days <= 60;
  });

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-slate-500">Your snapshot</h2>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="FTE" value={physician.data ? physician.data.fte.toFixed(2) : "—"} />
        <StatCard label="Pending requests" value={pendingRequests.data?.length ?? "—"} />
        <StatCard
          label="Open swaps"
          value={mySwaps.data?.filter((s) => s.status === "open" || s.status === "claimed").length ?? "—"}
        />
        <StatCard
          label="Credentials expiring"
          value={expiring.length}
          tone={expiring.length > 0 ? "amber" : "green"}
        />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="Subscribe to your calendar" subtitle="Add your shifts to your phone's calendar app" />
          <div className="px-5 py-4 text-sm text-slate-600">
            {physician.data ? (
              <>
                <p className="mb-2">Paste this URL into your calendar app's "subscribe by URL" option:</p>
                <code className="block break-all rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700">
                  {new URL(`/calendar/${physician.data.calendar_token}.ics`, apiBase()).toString()}
                </code>
              </>
            ) : (
              "Loading…"
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Quick links" />
          <div className="flex flex-col gap-1 px-5 py-4 text-sm">
            <Link to="/app/schedule" className="text-brand-600 hover:underline">
              View published schedule →
            </Link>
            <Link to="/app/requests" className="text-brand-600 hover:underline">
              Submit a time-off request →
            </Link>
            <Link to="/app/swaps" className="text-brand-600 hover:underline">
              Browse the shift swap marketplace →
            </Link>
          </div>
        </Card>
      </div>
    </section>
  );
}

function AdminPanel() {
  const sites = useFetch(() => api.get<Site[]>("/sites"), []);
  const physicians = useFetch(() => api.get<Physician[]>("/physicians"), []);
  const expiring = useFetch(() => api.get<Credential[]>("/credentials/expiring", { within_days: 60 }), []);
  const pending = useFetch(() => api.get<TimeOffRequest[]>("/time-off-requests", { status_filter: "pending" }), []);
  const openSwaps = useFetch(() => api.get<ShiftSwapRequest[]>("/shift-swaps", { status_filter: "open" }), []);
  const shiftTypes = useFetch(() => api.get<ShiftType[]>("/shift-types"), []);
  const shiftInstances = useFetch(() => api.get<ShiftInstance[]>("/shift-instances"), []);
  const runs = useFetch(() => api.get<ScheduleRun[]>("/schedule-runs"), []);

  // Everything the checklist keys off has to have loaded before we can say
  // whether a step is done -- otherwise it flashes "nothing set up yet" on
  // every refresh for a group that's fully configured.
  const setupLoaded =
    !sites.loading && !shiftTypes.loading && !shiftInstances.loading && !physicians.loading && !runs.loading;

  return (
    <section>
      {setupLoaded && (
        <div className="mb-6">
          <SetupChecklist
            sites={sites.data ?? []}
            shiftTypes={shiftTypes.data ?? []}
            shiftInstances={shiftInstances.data ?? []}
            physicians={physicians.data ?? []}
            runs={runs.data ?? []}
          />
        </div>
      )}
      <h2 className="mb-3 text-sm font-semibold text-slate-500">Organization overview</h2>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Active physicians" value={physicians.data?.length ?? "—"} />
        <StatCard label="Sites" value={sites.data?.length ?? "—"} />
        <StatCard label="Pending requests" value={pending.data?.length ?? "—"} />
        <StatCard
          label="Credentials expiring (60d)"
          value={expiring.data?.length ?? "—"}
          tone={(expiring.data?.length ?? 0) > 0 ? "amber" : "green"}
        />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="Needs your attention" />
          <div className="divide-y divide-slate-100">
            {(pending.data?.length ?? 0) === 0 && (openSwaps.data?.length ?? 0) === 0 && (expiring.data?.length ?? 0) === 0 ? (
              <EmptyState title="All caught up" hint="No pending requests, open swaps, or expiring credentials." />
            ) : (
              <>
                {pending.data && pending.data.length > 0 && (
                  <Link to="/app/requests" className="flex items-center justify-between px-5 py-3 text-sm hover:bg-slate-50">
                    <span>Time-off requests awaiting a decision</span>
                    <Badge tone="amber">{pending.data.length}</Badge>
                  </Link>
                )}
                {openSwaps.data && openSwaps.data.length > 0 && (
                  <Link to="/app/swaps" className="flex items-center justify-between px-5 py-3 text-sm hover:bg-slate-50">
                    <span>Shift swaps on the marketplace</span>
                    <Badge tone="blue">{openSwaps.data.length}</Badge>
                  </Link>
                )}
                {expiring.data && expiring.data.length > 0 && (
                  <Link to="/app/compliance" className="flex items-center justify-between px-5 py-3 text-sm hover:bg-slate-50">
                    <span>Credentials expiring within 60 days</span>
                    <Badge tone="red">{expiring.data.length}</Badge>
                  </Link>
                )}
              </>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Quick links" />
          <div className="flex flex-col gap-1 px-5 py-4 text-sm">
            <Link to="/app/generate" className="text-brand-600 hover:underline">
              Generate a new schedule →
            </Link>
            <Link to="/app/roster" className="text-brand-600 hover:underline">
              Manage your roster →
            </Link>
            <Link to="/app/rules" className="text-brand-600 hover:underline">
              Tune scheduling priorities →
            </Link>
          </div>
        </Card>
      </div>
    </section>
  );
}

function apiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
}

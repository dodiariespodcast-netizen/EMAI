import { useState } from "react";
import { useAuth, isScheduler } from "../lib/auth";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { Physician, RequestPriority, RequestStatus, TimeOffRequest, TimeOffType } from "../lib/types";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  PageHeader,
  Select,
  SuccessBanner,
  Textarea,
} from "../components/ui";
import { formatShortDate, titleCase } from "../lib/format";

const STATUS_TONE: Record<RequestStatus, "amber" | "green" | "red" | "slate"> = {
  pending: "amber",
  approved: "green",
  denied: "red",
  withdrawn: "slate",
};

export function RequestsPage() {
  const { user } = useAuth();
  const scheduler = isScheduler(user);

  return (
    <div>
      <PageHeader title="Time Off" subtitle="Submit requests and track their status." />
      <div className="space-y-6">
        {user?.physician_id && <MyRequests physicianId={user.physician_id} />}
        {scheduler && <AllRequests />}
      </div>
    </div>
  );
}

function MyRequests({ physicianId }: { physicianId: string }) {
  const requests = useFetch(() => api.get<TimeOffRequest[]>("/time-off-requests", { physician_id: physicianId }), [physicianId]);
  const [mode, setMode] = useState<"text" | "form">("text");
  const [text, setText] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [type, setType] = useState<TimeOffType>("vacation");
  const [priority, setPriority] = useState<RequestPriority>("preferred");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submitText(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const req = await api.post<TimeOffRequest>("/time-off-requests/from-text", { physician_id: physicianId, text });
      setSuccess(`Got it -- logged as ${req.start_date} to ${req.end_date} (${titleCase(req.request_type)}, ${req.priority}). Adjust below if that's not quite right.`);
      setText("");
      requests.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to submit");
    } finally {
      setBusy(false);
    }
  }

  async function submitForm(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await api.post<TimeOffRequest>("/time-off-requests", {
        physician_id: physicianId,
        start_date: startDate,
        end_date: endDate,
        request_type: type,
        priority,
      });
      setSuccess("Request submitted.");
      setStartDate("");
      setEndDate("");
      requests.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to submit");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
      <Card>
        <CardHeader
          title="New request"
          subtitle={mode === "text" ? "Describe it in plain English" : "Fill in the details"}
          action={
            <button className="text-xs font-medium text-brand-600 hover:underline" onClick={() => setMode(mode === "text" ? "form" : "text")}>
              {mode === "text" ? "Use a form instead" : "Use plain English instead"}
            </button>
          }
        />
        <div className="space-y-3 px-5 py-4">
          {error && <ErrorBanner message={error} />}
          {success && <SuccessBanner message={success} />}
          {mode === "text" ? (
            <form onSubmit={submitText} className="space-y-3">
              <Textarea
                rows={4}
                required
                placeholder="e.g. I need the week of Dec 22-29 off for vacation, it's important -- my in-laws are visiting."
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <Button type="submit" disabled={busy || !text.trim()}>
                {busy ? "Parsing…" : "Submit request"}
              </Button>
            </form>
          ) : (
            <form onSubmit={submitForm} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Start date">
                  <Input type="date" required value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                </Field>
                <Field label="End date">
                  <Input type="date" required value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Type">
                  <Select value={type} onChange={(e) => setType(e.target.value as TimeOffType)}>
                    {(["vacation", "cme", "personal", "sick", "other"] as TimeOffType[]).map((t) => (
                      <option key={t} value={t}>
                        {titleCase(t)}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Priority">
                  <Select value={priority} onChange={(e) => setPriority(e.target.value as RequestPriority)}>
                    <option value="preferred">Preferred (soft ask)</option>
                    <option value="must">Must have off (hard constraint)</option>
                  </Select>
                </Field>
              </div>
              <Button type="submit" disabled={busy}>
                {busy ? "Submitting…" : "Submit request"}
              </Button>
            </form>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader title="Your requests" />
        {requests.data && requests.data.length === 0 ? (
          <EmptyState title="No requests yet" />
        ) : (
          <div className="divide-y divide-slate-100">
            {(requests.data ?? []).map((r) => (
              <div key={r.id} className="flex items-center justify-between px-5 py-3 text-sm">
                <div>
                  <p className="font-medium text-slate-800">
                    {formatShortDate(r.start_date)} – {formatShortDate(r.end_date)}
                  </p>
                  <p className="text-xs text-slate-400">
                    {titleCase(r.request_type)} · {r.priority === "must" ? "Must have off" : "Preferred"}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[r.status]}>{titleCase(r.status)}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </section>
  );
}

function AllRequests() {
  const [statusFilter, setStatusFilter] = useState<RequestStatus | "">("pending");
  const requests = useFetch(
    () => api.get<TimeOffRequest[]>("/time-off-requests", statusFilter ? { status_filter: statusFilter } : undefined),
    [statusFilter],
  );
  const physicians = useFetch(() => api.get<Physician[]>("/physicians"), []);
  const physicianById = new Map((physicians.data ?? []).map((p) => [p.id, p]));
  const [busyId, setBusyId] = useState<string | null>(null);

  async function decide(id: string, status: RequestStatus) {
    setBusyId(id);
    try {
      await api.patch(`/time-off-requests/${id}`, { status });
      requests.reload();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section>
      <Card>
        <CardHeader
          title="All organization requests"
          action={
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as RequestStatus | "")} className="w-36">
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="denied">Denied</option>
              <option value="withdrawn">Withdrawn</option>
            </Select>
          }
        />
        {requests.data && requests.data.length === 0 ? (
          <EmptyState title="Nothing here" />
        ) : (
          <div className="divide-y divide-slate-100">
            {(requests.data ?? []).map((r) => {
              const p = physicianById.get(r.physician_id);
              return (
                <div key={r.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-800">
                      {p ? `${p.first_name} ${p.last_name}` : "Unknown"} — {formatShortDate(r.start_date)} to {formatShortDate(r.end_date)}
                    </p>
                    <p className="text-xs text-slate-400">
                      {titleCase(r.request_type)} · {r.priority === "must" ? "Must have off" : "Preferred"}
                      {r.reason && ` · "${r.reason}"`}
                    </p>
                  </div>
                  {r.status === "pending" ? (
                    <div className="flex shrink-0 gap-2">
                      <Button size="sm" variant="secondary" disabled={busyId === r.id} onClick={() => decide(r.id, "approved")}>
                        Approve
                      </Button>
                      <Button size="sm" variant="danger" disabled={busyId === r.id} onClick={() => decide(r.id, "denied")}>
                        Deny
                      </Button>
                    </div>
                  ) : (
                    <Badge tone={STATUS_TONE[r.status]}>{titleCase(r.status)}</Badge>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </section>
  );
}

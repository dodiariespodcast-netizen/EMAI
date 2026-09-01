import { useMemo, useState } from "react";
import { useAuth, isScheduler } from "../lib/auth";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { AssignmentDetail, Physician, ShiftSwapRequest, SwapStatus } from "../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBanner, PageHeader, Select, Textarea } from "../components/ui";
import { formatDate } from "../lib/format";

const STATUS_TONE: Record<SwapStatus, "blue" | "amber" | "green" | "red" | "slate"> = {
  open: "blue",
  claimed: "amber",
  approved: "green",
  rejected: "red",
  cancelled: "slate",
};

export function SwapsPage() {
  const { user } = useAuth();
  const scheduler = isScheduler(user);
  const [statusFilter, setStatusFilter] = useState<SwapStatus | "">("");

  const swaps = useFetch(
    () => api.get<ShiftSwapRequest[]>("/shift-swaps", statusFilter ? { status_filter: statusFilter } : undefined),
    [statusFilter],
  );
  const physicians = useFetch(() => api.get<Physician[]>("/physicians"), []);
  const myAssignments = useFetch(
    () => (user?.physician_id ? api.get<AssignmentDetail[]>("/assignments", { physician_id: user.physician_id }) : Promise.resolve([])),
    [user?.physician_id],
  );

  const physicianById = useMemo(() => new Map((physicians.data ?? []).map((p) => [p.id, p])), [physicians.data]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function claim(swapId: string) {
    if (!user?.physician_id) return;
    setBusyId(swapId);
    setError(null);
    try {
      await api.post(`/shift-swaps/${swapId}/claim`, { physician_id: user.physician_id });
      swaps.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to claim");
    } finally {
      setBusyId(null);
    }
  }

  async function cancel(swapId: string) {
    setBusyId(swapId);
    try {
      await api.post(`/shift-swaps/${swapId}/cancel`);
      swaps.reload();
    } finally {
      setBusyId(null);
    }
  }

  async function approve(swapId: string) {
    setBusyId(swapId);
    setError(null);
    try {
      await api.post(`/shift-swaps/${swapId}/approve`);
      swaps.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to approve");
    } finally {
      setBusyId(null);
    }
  }

  async function reject(swapId: string) {
    setBusyId(swapId);
    try {
      await api.post(`/shift-swaps/${swapId}/reject`, {});
      swaps.reload();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Shift Swaps"
        subtitle="Offer a shift, claim someone else's, and schedulers approve the reassignment."
        action={
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as SwapStatus | "")} className="w-36">
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="claimed">Claimed</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="cancelled">Cancelled</option>
          </Select>
        }
      />

      {error && <div className="mb-4"><ErrorBanner message={error} /></div>}

      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader title="Marketplace" />
          {swaps.data && swaps.data.length === 0 ? (
            <EmptyState title="No swaps match this filter" />
          ) : (
            <div className="divide-y divide-slate-100">
              {(swaps.data ?? []).map((s) => {
                const offering = physicianById.get(s.offering_physician_id);
                const claimant = s.claimed_by_physician_id ? physicianById.get(s.claimed_by_physician_id) : null;
                const isMine = s.offering_physician_id === user?.physician_id;
                const isClaimant = s.claimed_by_physician_id === user?.physician_id;
                return (
                  <div key={s.id} className="px-5 py-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-800">
                          {offering ? `${offering.first_name} ${offering.last_name}` : "Unknown"} offering a shift
                        </p>
                        {s.note && <p className="text-xs text-slate-400">"{s.note}"</p>}
                        {claimant && (
                          <p className="text-xs text-slate-400">
                            Claimed by {claimant.first_name} {claimant.last_name}
                          </p>
                        )}
                      </div>
                      <Badge tone={STATUS_TONE[s.status]}>{s.status}</Badge>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {s.status === "open" && user?.physician_id && !isMine && (
                        <Button size="sm" disabled={busyId === s.id} onClick={() => claim(s.id)}>
                          Claim
                        </Button>
                      )}
                      {s.status === "open" && isMine && (
                        <Button size="sm" variant="secondary" disabled={busyId === s.id} onClick={() => cancel(s.id)}>
                          Cancel offer
                        </Button>
                      )}
                      {s.status === "claimed" && scheduler && (
                        <>
                          <Button size="sm" disabled={busyId === s.id} onClick={() => approve(s.id)}>
                            Approve
                          </Button>
                          <Button size="sm" variant="danger" disabled={busyId === s.id} onClick={() => reject(s.id)}>
                            Reject
                          </Button>
                        </>
                      )}
                      {s.status === "claimed" && !scheduler && (isMine || isClaimant) && (
                        <p className="text-xs text-slate-400">Waiting on a scheduler to approve.</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {user?.physician_id && <OfferShiftCard assignments={myAssignments.data ?? []} onOffered={swaps.reload} />}
      </div>
    </div>
  );
}

function OfferShiftCard({ assignments, onOffered }: { assignments: AssignmentDetail[]; onOffered: () => void }) {
  const upcoming = assignments
    .filter((a) => a.date >= new Date().toISOString().slice(0, 10))
    .sort((a, b) => a.date.localeCompare(b.date));

  const [selected, setSelected] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/shift-swaps", { assignment_id: selected, note: note || undefined });
      setSelected("");
      setNote("");
      onOffered();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Failed to offer shift");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Offer one of your shifts" />
      <div className="space-y-3 px-5 py-4">
        {error && <ErrorBanner message={error} />}
        {upcoming.length === 0 ? (
          <p className="text-xs text-slate-400">No upcoming published shifts to offer.</p>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <Select required value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">Select a shift…</option>
              {upcoming.map((a) => (
                <option key={a.id} value={a.id}>
                  {formatDate(a.date)} · {a.shift_type_name} @ {a.site_name}
                </option>
              ))}
            </Select>
            <Textarea rows={2} placeholder="Why are you offering this? (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
            <Button type="submit" disabled={busy || !selected} className="w-full">
              {busy ? "Posting…" : "Post to marketplace"}
            </Button>
          </form>
        )}
      </div>
    </Card>
  );
}

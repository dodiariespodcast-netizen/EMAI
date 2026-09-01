import { useState } from "react";
import { useFetch } from "../lib/hooks";
import { api, ApiError } from "../lib/api";
import type { Assignment, EligiblePhysician, Physician, ShiftInstance, ShiftType } from "../lib/types";
import { Badge, Button, ErrorBanner, Spinner } from "./ui";
import { formatDate, titleCase } from "../lib/format";

/**
 * Side panel for hand-editing one shift: who's on it, who else could take it
 * (and why anyone can't), and remove/reassign/assign actions. The conflict
 * reasons come from the server running the same hard-rule check the solver
 * does, so this can't quietly produce an illegal schedule -- but a scheduler
 * can still force an exception when reality demands it.
 */
export function ShiftEditorPanel({
  shift,
  shiftType,
  assignments,
  physicianById,
  onClose,
  onChanged,
}: {
  shift: ShiftInstance;
  shiftType: ShiftType | undefined;
  assignments: Assignment[];
  physicianById: Map<string, Physician>;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingForce, setPendingForce] = useState<{ physicianId: string; reason: string } | null>(null);

  const eligible = useFetch(
    () => api.get<EligiblePhysician[]>(`/shift-instances/${shift.id}/eligible-physicians`),
    [shift.id, assignments.length],
  );

  const short = shift.required_physicians - assignments.length;

  async function assign(physicianId: string, force = false, overrideReason?: string) {
    setBusy(true);
    setError(null);
    try {
      await api.post("/assignments", {
        shift_instance_id: shift.id,
        physician_id: physicianId,
        force,
        override_reason: overrideReason,
      });
      setPendingForce(null);
      onChanged();
      eligible.reload();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setPendingForce({ physicianId, reason: err.friendlyMessage });
      } else {
        setError(err instanceof ApiError ? err.friendlyMessage : "Couldn't assign that shift");
      }
    } finally {
      setBusy(false);
    }
  }

  async function unassign(assignmentId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.delete(`/assignments/${assignmentId}`);
      onChanged();
      eligible.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Couldn't remove that assignment");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm flex-col border-l border-slate-200 bg-white shadow-xl">
      <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{shiftType?.name ?? titleCase(shift.category)}</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {formatDate(shift.date)}
            {shift.is_holiday && " · holiday"} · needs {shift.required_physicians}
          </p>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="Close">
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="px-5 pt-4">
            <ErrorBanner message={error} />
          </div>
        )}

        <div className="px-5 py-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Assigned {short > 0 && <span className="ml-1 font-medium normal-case text-red-500">short {short}</span>}
          </p>
          {assignments.length === 0 ? (
            <p className="text-sm text-slate-400">Nobody on this shift yet.</p>
          ) : (
            <div className="space-y-1.5">
              {assignments.map((a) => {
                const p = physicianById.get(a.physician_id);
                return (
                  <div key={a.id} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                    <span className="text-sm text-slate-800">
                      {p ? `${p.first_name} ${p.last_name}` : "Unknown"}
                    </span>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => unassign(a.id)}>
                      Remove
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {pendingForce && (
          <div className="mx-5 mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
            <p className="text-sm font-medium text-amber-900">That breaks a rule</p>
            <p className="mt-1 text-xs text-amber-800">{pendingForce.reason}</p>
            <p className="mt-2 text-xs text-amber-700">
              You can override it -- the exception and this reason get recorded in the audit log.
            </p>
            <div className="mt-2 flex gap-2">
              <Button
                size="sm"
                variant="danger"
                disabled={busy}
                onClick={() => assign(pendingForce.physicianId, true, pendingForce.reason)}
              >
                Assign anyway
              </Button>
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => setPendingForce(null)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        <div className="border-t border-slate-100 px-5 py-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Assign someone</p>
          {eligible.loading ? (
            <div className="flex justify-center py-6">
              <Spinner className="h-4 w-4 text-brand-500" />
            </div>
          ) : (
            <div className="space-y-1">
              {(eligible.data ?? []).map((candidate) => (
                <button
                  key={candidate.physician_id}
                  disabled={busy}
                  onClick={() => assign(candidate.physician_id)}
                  className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left hover:bg-slate-50 disabled:opacity-50"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-slate-800">{candidate.name}</span>
                    <span className="block truncate text-xs text-slate-400">
                      {candidate.conflict ?? `${candidate.assigned_shifts_in_period} shifts this period`}
                    </span>
                  </span>
                  {candidate.conflict ? (
                    <Badge tone="red">conflict</Badge>
                  ) : (
                    <Badge tone="green">free</Badge>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

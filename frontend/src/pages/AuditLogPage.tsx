import { useFetch } from "../lib/hooks";
import { api } from "../lib/api";
import type { AuditLogEntry } from "../lib/types";
import { Badge, Card, EmptyState, PageHeader } from "../components/ui";
import { formatDateTime, titleCase } from "../lib/format";

export function AuditLogPage() {
  const log = useFetch(() => api.get<AuditLogEntry[]>("/audit-log", { limit: 300 }), []);

  return (
    <div>
      <PageHeader title="Audit Log" subtitle="Every schedule generation, publish, request decision, and swap decision, with who did it and when." />
      <Card>
        {log.data && log.data.length === 0 ? (
          <EmptyState title="Nothing recorded yet" />
        ) : (
          <div className="divide-y divide-slate-100">
            {(log.data ?? []).map((entry) => (
              <div key={entry.id} className="flex items-start justify-between gap-3 px-5 py-3 text-sm">
                <div className="min-w-0">
                  <p className="font-medium text-slate-800">{titleCase(entry.action.replace(/\./g, " "))}</p>
                  <p className="truncate text-xs text-slate-400">
                    {entry.entity_type}
                    {entry.entity_id && ` · ${entry.entity_id.slice(0, 8)}…`}
                    {Object.keys(entry.details).length > 0 && ` · ${JSON.stringify(entry.details)}`}
                  </p>
                </div>
                <Badge tone="slate">{formatDateTime(entry.created_at)}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

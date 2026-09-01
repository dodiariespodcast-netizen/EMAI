import { useRef, useState } from "react";
import { API_BASE_URL, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { PhysicianImportResult, Site } from "../lib/types";
import { Button, Card, CardHeader, ErrorBanner, Field, Select, SuccessBanner } from "./ui";

/** Bulk roster onboarding. Validates first (dry run) so an admin sees exactly
 * what a file will do before it touches the roster. */
export function RosterImportCard({ sites, onImported }: { sites: Site[]; onImported: () => void }) {
  const { token } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [siteId, setSiteId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PhysicianImportResult | null>(null);

  async function upload(dryRun: boolean) {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Choose a CSV file first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("dry_run", String(dryRun));
      if (siteId) form.append("site_ids", siteId);

      // Multipart, so this goes through fetch directly rather than the JSON client.
      const res = await fetch(new URL("/physicians/import", API_BASE_URL).toString(), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const payload = await res.json();
      if (!res.ok) throw new ApiError(res.status, payload);

      setResult(payload as PhysicianImportResult);
      if (!dryRun) {
        onImported();
        if (fileRef.current) fileRef.current.value = "";
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.friendlyMessage : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Import a roster from CSV"
        subtitle="Onboard a whole group at once instead of typing everyone in"
        action={
          <a
            href={new URL("/physicians/import/template.csv", API_BASE_URL).toString()}
            className="text-xs font-medium text-brand-600 hover:underline"
            onClick={async (e) => {
              // The template endpoint needs auth, so fetch and save it manually.
              e.preventDefault();
              const res = await fetch(new URL("/physicians/import/template.csv", API_BASE_URL).toString(), {
                headers: { Authorization: `Bearer ${token}` },
              });
              const blob = await res.blob();
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = "physician-import-template.csv";
              link.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download template
          </a>
        }
      />
      <div className="space-y-3 px-5 py-4">
        {error && <ErrorBanner message={error} />}

        <div className="grid gap-3 md:grid-cols-2">
          <Field label="CSV file">
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              onChange={() => setResult(null)}
              className="w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-700"
            />
          </Field>
          <Field label="Give everyone access to (optional)">
            <Select value={siteId} onChange={(e) => setSiteId(e.target.value)}>
              <option value="">No site assigned yet</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="flex gap-2">
          <Button variant="secondary" disabled={busy} onClick={() => upload(true)}>
            {busy ? "Checking…" : "Validate first"}
          </Button>
          <Button disabled={busy} onClick={() => upload(false)}>
            Import
          </Button>
        </div>

        {result && (
          <div className="space-y-2">
            {result.dry_run ? (
              <SuccessBanner
                message={`Looks good: ${result.created_count} physician(s) would be added${
                  result.error_count ? `, ${result.error_count} row(s) would be skipped` : ""
                }.`}
              />
            ) : (
              <SuccessBanner message={`Imported ${result.created_count} physician(s).`} />
            )}
            {result.errors.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <p className="text-xs font-semibold text-amber-900">Rows that couldn't be used</p>
                <ul className="mt-1 space-y-0.5 text-xs text-amber-800">
                  {result.errors.map((e) => (
                    <li key={`${e.line}-${e.error}`}>
                      Line {e.line}: {e.error}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

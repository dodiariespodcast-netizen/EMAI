import { Link } from "react-router-dom";
import type { Physician, ScheduleRun, ShiftInstance, ShiftType, Site } from "../lib/types";
import { Card, CardHeader } from "./ui";

interface Step {
  label: string;
  detail: string;
  to: string;
  done: boolean;
}

/**
 * A brand-new organization lands on empty screens with no idea what to do
 * first. This walks through the actual dependency order -- you can't generate
 * a schedule without shifts, and you can't have shifts without a site -- and
 * disappears once the group is set up.
 */
export function SetupChecklist({
  sites,
  shiftTypes,
  shiftInstances,
  physicians,
  runs,
}: {
  sites: Site[];
  shiftTypes: ShiftType[];
  shiftInstances: ShiftInstance[];
  physicians: Physician[];
  runs: ScheduleRun[];
}) {
  const steps: Step[] = [
    {
      label: "Add a site",
      detail: "The ED or facility you staff. Agencies add one per client hospital.",
      to: "/app/shifts",
      done: sites.length > 0,
    },
    {
      label: "Define your shift types",
      detail: "Your recurring patterns, e.g. Day 07-19 and Night 19-07, and how many people each needs.",
      to: "/app/shifts",
      done: shiftTypes.length > 0,
    },
    {
      label: "Build your roster",
      detail: "Add physicians one at a time, or import a CSV if you have more than a handful.",
      to: "/app/roster",
      done: physicians.length > 0,
    },
    {
      label: "Generate coverage needs",
      detail: "Stamp your shift types across the dates you're scheduling.",
      to: "/app/shifts",
      done: shiftInstances.length > 0,
    },
    {
      label: "Generate and publish a schedule",
      detail: "Run the optimizer, review the fairness table, then publish it to the group.",
      to: "/app/generate",
      done: runs.some((r) => r.status === "published"),
    },
  ];

  const remaining = steps.filter((s) => !s.done).length;
  if (remaining === 0) return null;

  const nextStep = steps.find((s) => !s.done);

  return (
    <Card className="border-brand-200 bg-brand-50/40">
      <CardHeader
        title="Finish setting up your group"
        subtitle={`${steps.length - remaining} of ${steps.length} done -- next: ${nextStep?.label.toLowerCase()}`}
      />
      <ol className="divide-y divide-brand-100/70">
        {steps.map((step, index) => (
          <li key={step.label}>
            <Link
              to={step.to}
              className={`flex items-start gap-3 px-5 py-3 transition-colors hover:bg-white/60 ${
                step.done ? "opacity-55" : ""
              }`}
            >
              <span
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                  step.done ? "bg-emerald-500 text-white" : "border border-brand-300 bg-white text-brand-600"
                }`}
                aria-hidden
              >
                {step.done ? "✓" : index + 1}
              </span>
              <span className="min-w-0">
                <span className={`block text-sm font-medium ${step.done ? "text-slate-500 line-through" : "text-slate-800"}`}>
                  {step.label}
                </span>
                <span className="block text-xs text-slate-500">{step.detail}</span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </Card>
  );
}

"""Generates a plain-English summary of a completed schedule run: what got
filled, what didn't, whose preferences were honored, and why -- the thing
that turns a wall of assignment rows into something a medical director can
skim before publishing. Falls back to a templated summary built from solver
stats when no LLM key is configured."""

from __future__ import annotations

from app.models.schedule import ScheduleRun
from app.schemas.schedule import FairnessRow
from app.services.ai.client import get_client


def summarize_schedule_run(run: ScheduleRun, fairness: list[FairnessRow]) -> str:
    client = get_client()
    if client is not None:
        try:
            return _summarize_with_claude(client, run, fairness)
        except Exception:
            pass
    return _summarize_fallback(run, fairness)


def _summarize_with_claude(client, run: ScheduleRun, fairness: list[FairnessRow]) -> str:
    from app.config import get_settings

    settings = get_settings()
    fairness_lines = "\n".join(
        f"- {r.physician_name}: {r.total_shifts} shifts (target {r.target_shifts}), "
        f"{r.night_shifts} nights, {r.weekend_shifts} weekends, "
        f"{r.preferred_requests_granted}/{r.preferred_requests_total} preferred requests honored"
        for r in fairness
    )
    prompt = (
        f"You generated an emergency department schedule for {run.period_start} to {run.period_end}.\n"
        f"Solver status: {run.solver_status}. Unfilled shifts: {run.unfilled_shift_count}.\n"
        f"Per-physician outcomes:\n{fairness_lines}\n\n"
        "Write a concise (under 200 words) plain-English summary for the medical director "
        "reviewing this draft before publishing it: call out any unfilled shifts and why that "
        "matters operationally, flag any physician meaningfully over/under their target, and "
        "note overall fairness/preference satisfaction. No preamble, no markdown headers."
    )
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text").strip()


def _summarize_fallback(run: ScheduleRun, fairness: list[FairnessRow]) -> str:
    lines = [
        f"Schedule for {run.period_start} to {run.period_end}: solver status {run.solver_status}, "
        f"{run.unfilled_shift_count} shift(s) unfilled."
    ]
    outliers = [r for r in fairness if abs(r.total_shifts - r.target_shifts) >= 2]
    if outliers:
        lines.append("Notably off target:")
        for r in outliers:
            lines.append(f"  - {r.physician_name}: {r.total_shifts} shifts vs target {r.target_shifts}")
    total_granted = sum(r.preferred_requests_granted for r in fairness)
    total_requested = sum(r.preferred_requests_total for r in fairness)
    if total_requested:
        lines.append(
            f"Preferred time-off requests honored: {total_granted}/{total_requested} "
            f"({round(100 * total_granted / total_requested)}%)."
        )
    return "\n".join(lines)

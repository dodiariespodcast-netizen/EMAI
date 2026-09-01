"""Per-physician .ics calendar feed: a stable, unauthenticated (token-
secured) URL a physician can paste into their phone's calendar app to see
their published shifts show up automatically -- no login flow calendar
apps could drive anyway. This is a small feature with outsized perceived
value; it's one of the first things physicians ask for from any
scheduling product."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import ScheduleRunStatus
from app.models.physician import Physician
from app.models.schedule import Assignment, ScheduleRun
from app.models.shift import ShiftInstance
from app.models.tenancy import Site

router = APIRouter(tags=["calendar"])


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


@router.get("/calendar/{calendar_token}.ics")
def physician_calendar_feed(calendar_token: str, db: Session = Depends(get_db)) -> Response:
    physician = db.query(Physician).filter(Physician.calendar_token == calendar_token).first()
    if physician is None:
        raise HTTPException(status_code=404, detail="Unknown calendar feed")

    rows = (
        db.query(Assignment, ShiftInstance, Site)
        .join(ShiftInstance, Assignment.shift_instance_id == ShiftInstance.id)
        .join(ScheduleRun, Assignment.schedule_run_id == ScheduleRun.id)
        .join(Site, ShiftInstance.site_id == Site.id)
        .filter(Assignment.physician_id == physician.id, ScheduleRun.status == ScheduleRunStatus.PUBLISHED)
        .all()
    )

    now = _fmt(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//EMAI Scheduler//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:EMAI Schedule - {physician.first_name} {physician.last_name}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT4H",
    ]
    for assignment, shift, site in rows:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{assignment.id}@emai-scheduler",
            f"DTSTAMP:{now}",
            f"DTSTART:{_fmt(shift.start_datetime)}",
            f"DTEND:{_fmt(shift.end_datetime)}",
            f"SUMMARY:{shift.category.value.title()} shift @ {site.name}",
            f"LOCATION:{site.name}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    return Response(content="\r\n".join(lines), media_type="text/calendar; charset=utf-8")

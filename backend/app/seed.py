"""Loads a realistic demo organization so the product is usable the moment
it's installed, instead of presenting an empty screen.

    python -m app.seed              # create the demo org
    python -m app.seed --reset      # wipe it first, then recreate
    python -m app.seed --slug my-em --email me@example.com

Builds a 14-physician emergency group across two sites with day/swing/night
coverage, a spread of preferences and FTEs, employed and locums physicians,
credentials (some expiring soon), pending and approved time-off requests,
then runs the optimizer over the next 28 days and publishes the result --
i.e. everything needed for every screen in the app to have something real on
it, and for a demo to a prospect to be a login rather than a setup session.
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app import database
from app.models.enums import (
    CredentialType,
    EmploymentType,
    RequestPriority,
    RequestStatus,
    ScheduleRunStatus,
    ShiftCategory,
    TimeOffType,
    UserRole,
)
from app.models.physician import Credential, Physician, PhysicianSite
from app.models.requests import ShiftPreference, TimeOffRequest
from app.models.schedule import ScheduleRun
from app.models.shift import ShiftInstance, ShiftType
from app.models.tenancy import Organization, Site, User
from app.services.scheduling.service import generate_schedule

DEFAULT_SLUG = "demo-em"
DEFAULT_PASSWORD = "demo1234"

# (first, last, fte, seniority, night_pref, weekend_pref, holiday_pref, employment, rate)
ROSTER = [
    ("Dana",    "Whitfield", 1.0, 18, -2,  0, -1, EmploymentType.EMPLOYED,    None),
    ("Marcus",  "Oyelaran",  1.0, 12,  2,  1,  0, EmploymentType.EMPLOYED,    None),
    ("Priya",   "Raghavan",  1.0,  9, -1,  0,  0, EmploymentType.EMPLOYED,    None),
    ("Tomas",   "Iverson",   1.0,  7,  1, -1,  1, EmploymentType.EMPLOYED,    None),
    ("Grace",   "Lindqvist", 0.8,  6, -2, -1, -2, EmploymentType.EMPLOYED,    None),
    ("Ahmed",   "Barakat",   1.0,  5,  1,  0,  0, EmploymentType.EMPLOYED,    None),
    ("Renee",   "Castellan", 0.6,  4, -1,  1,  0, EmploymentType.EMPLOYED,    None),
    ("Jonah",   "Pfeiffer",  1.0,  3,  2,  2,  1, EmploymentType.EMPLOYED,    None),
    ("Ivy",     "Sandoval",  1.0,  2,  0,  0,  0, EmploymentType.EMPLOYED,    None),
    ("Nate",    "Kowalczyk", 0.5,  1,  1, -1,  0, EmploymentType.MOONLIGHTER, 185.0),
    ("Simone",  "Achebe",    1.0,  8, -1,  0,  0, EmploymentType.LOCUMS,      235.0),
    ("Wes",     "Fontaine",  0.8,  4,  2,  1,  2, EmploymentType.LOCUMS,      245.0),
    ("Lena",    "Vartanian", 0.6, 11, -2,  0, -1, EmploymentType.CONTRACT,    210.0),
    ("Owen",    "Bright",    1.0,  1,  0,  1,  0, EmploymentType.EMPLOYED,    None),
]

SHIFT_TEMPLATES = [
    # (name, category, start, end, hours, required)
    ("Day 07-19",   ShiftCategory.DAY,   time(7, 0),  time(19, 0), 12.0, 2),
    ("Swing 11-23", ShiftCategory.SWING, time(11, 0), time(23, 0), 12.0, 1),
    ("Night 19-07", ShiftCategory.NIGHT, time(19, 0), time(7, 0),  12.0, 1),
]

# Fixed-date US holidays are enough for a demo; a real deployment would pull
# these from the customer's own calendar.
HOLIDAYS = {(1, 1), (7, 4), (12, 24), (12, 25), (12, 31)}


def _shift_instance(org_id: str, shift_type: ShiftType, day: date) -> ShiftInstance:
    start_dt = datetime.combine(day, shift_type.start_time)
    end_dt = datetime.combine(day, shift_type.end_time)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return ShiftInstance(
        org_id=org_id,
        site_id=shift_type.site_id,
        shift_type_id=shift_type.id,
        date=day,
        start_datetime=start_dt,
        end_datetime=end_dt,
        category=shift_type.category,
        required_physicians=shift_type.required_physicians,
        is_holiday=(day.month, day.day) in HOLIDAYS,
    )


def wipe(db: Session, slug: str) -> None:
    """Removes a previously seeded org and everything under it."""
    org = db.query(Organization).filter(Organization.slug == slug).first()
    if org is None:
        return

    from app.models.schedule import Assignment, SchedulingRule, ShiftSwapRequest
    from app.models.tenancy import AuditLog, OAuthIdentity, PasswordResetToken

    physician_ids = [p.id for p in db.query(Physician).filter(Physician.org_id == org.id).all()]
    user_ids = [u.id for u in db.query(User).filter(User.org_id == org.id).all()]

    # Children first, so foreign keys stay satisfied the whole way down.
    for model in (Assignment, ShiftSwapRequest, ShiftInstance, ScheduleRun, ShiftType):
        db.query(model).filter(model.org_id == org.id).delete(synchronize_session=False)
    for model in (TimeOffRequest, ShiftPreference, Credential):
        db.query(model).filter(model.org_id == org.id).delete(synchronize_session=False)
    if physician_ids:
        db.query(PhysicianSite).filter(PhysicianSite.physician_id.in_(physician_ids)).delete(
            synchronize_session=False
        )
    if user_ids:
        db.query(PasswordResetToken).filter(PasswordResetToken.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
        db.query(OAuthIdentity).filter(OAuthIdentity.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.org_id == org.id).delete(synchronize_session=False)
    db.query(SchedulingRule).filter(SchedulingRule.org_id == org.id).delete(synchronize_session=False)
    db.query(User).filter(User.org_id == org.id).delete(synchronize_session=False)
    db.query(Physician).filter(Physician.org_id == org.id).delete(synchronize_session=False)
    db.query(Site).filter(Site.org_id == org.id).delete(synchronize_session=False)
    db.delete(org)
    db.commit()


def seed(slug: str = DEFAULT_SLUG, admin_email: str | None = None, password: str = DEFAULT_PASSWORD) -> dict:
    rng = random.Random(20260101)  # deterministic, so demos look the same every time
    database.init_db()
    db: Session = database.SessionLocal()
    try:
        if db.query(Organization).filter(Organization.slug == slug).first():
            raise SystemExit(
                f"An organization with slug '{slug}' already exists. "
                f"Re-run with --reset to replace it, or --slug to pick another name."
            )

        admin_email = admin_email or f"admin@{slug}.example.com"
        org = Organization(name="Riverbend Emergency Physicians", slug=slug, plan_tier="demo")
        db.add(org)
        db.flush()

        main = Site(org_id=org.id, name="Riverbend Main ED", timezone="America/New_York")
        north = Site(org_id=org.id, name="Northside Freestanding ED", timezone="America/New_York")
        db.add_all([main, north])
        db.flush()

        admin = User(
            org_id=org.id, email=admin_email, hashed_password=hash_password(password), role=UserRole.OWNER
        )
        db.add(admin)

        # Roster. Everyone can work Main; about half also cover Northside, so
        # site eligibility actually constrains something.
        physicians: list[Physician] = []
        for index, (first, last, fte, seniority, night, weekend, holiday, employment, rate) in enumerate(ROSTER):
            physician = Physician(
                org_id=org.id,
                first_name=first,
                last_name=last,
                email=f"{first.lower()}.{last.lower()}@{slug}.example.com",
                credentials="DO" if index % 5 == 4 else "MD",
                fte=fte,
                seniority_years=seniority,
                night_preference=night,
                weekend_preference=weekend,
                holiday_preference=holiday,
                employment_type=employment,
                hourly_rate=rate,
            )
            db.add(physician)
            db.flush()
            physicians.append(physician)

            db.add(PhysicianSite(physician_id=physician.id, site_id=main.id))
            if index % 2 == 0:
                db.add(PhysicianSite(physician_id=physician.id, site_id=north.id))

            # Logins for the first few, so the demo can be viewed from a
            # physician's seat as well as an admin's.
            if index < 3:
                db.add(
                    User(
                        org_id=org.id,
                        email=physician.email,
                        hashed_password=hash_password(password),
                        role=UserRole.PHYSICIAN,
                        physician_id=physician.id,
                    )
                )

        # Credentials, including a couple expiring inside the 60-day window so
        # the compliance dashboard has something to flag on day one.
        today = date.today()
        states = ["NY", "NJ", "CT", "PA"]
        for index, physician in enumerate(physicians):
            db.add(
                Credential(
                    org_id=org.id,
                    physician_id=physician.id,
                    credential_type=CredentialType.STATE_LICENSE,
                    identifier=f"{states[index % len(states)]}-{100000 + index * 137}",
                    issuing_state=states[index % len(states)],
                    issued_date=today - timedelta(days=400 + index * 11),
                    expires_on=today + timedelta(days=[21, 45, 380, 500, 620][index % 5]),
                )
            )
            db.add(
                Credential(
                    org_id=org.id,
                    physician_id=physician.id,
                    credential_type=CredentialType.ACLS,
                    issued_date=today - timedelta(days=300),
                    expires_on=today + timedelta(days=[33, 200, 430][index % 3]),
                )
            )
            if physician.employment_type in (EmploymentType.LOCUMS, EmploymentType.CONTRACT):
                db.add(
                    Credential(
                        org_id=org.id,
                        physician_id=physician.id,
                        credential_type=CredentialType.MALPRACTICE_INSURANCE,
                        identifier=f"POL-{4400 + index}",
                        expires_on=today + timedelta(days=[52, 240][index % 2]),
                    )
                )

        # Shift types + a month of coverage needs at both sites.
        period_start = today
        period_end = today + timedelta(days=27)
        shift_types: list[ShiftType] = []
        for site, templates in ((main, SHIFT_TEMPLATES), (north, SHIFT_TEMPLATES[:1])):
            for name, category, start_t, end_t, hours, required in templates:
                shift_type = ShiftType(
                    org_id=org.id,
                    site_id=site.id,
                    name=name,
                    category=category,
                    start_time=start_t,
                    end_time=end_t,
                    duration_hours=hours,
                    required_physicians=required if site is main else 1,
                )
                db.add(shift_type)
                db.flush()
                shift_types.append(shift_type)

                day = period_start
                while day <= period_end:
                    db.add(_shift_instance(org.id, shift_type, day))
                    day += timedelta(days=1)

        # Time-off requests: a mix of approved-hard, approved-soft and pending,
        # so approvals, the solver's hard constraints, and the fairness report
        # all have real inputs.
        request_specs = [
            (0, 6, 3, TimeOffType.VACATION, RequestPriority.MUST, RequestStatus.APPROVED),
            (3, 12, 2, TimeOffType.CME, RequestPriority.MUST, RequestStatus.APPROVED),
            (5, 9, 1, TimeOffType.PERSONAL, RequestPriority.PREFERRED, RequestStatus.APPROVED),
            (7, 18, 4, TimeOffType.VACATION, RequestPriority.PREFERRED, RequestStatus.PENDING),
            (9, 15, 2, TimeOffType.PERSONAL, RequestPriority.PREFERRED, RequestStatus.PENDING),
            (11, 21, 3, TimeOffType.CME, RequestPriority.MUST, RequestStatus.PENDING),
        ]
        for physician_index, offset, length, kind, priority, status in request_specs:
            start = period_start + timedelta(days=offset)
            db.add(
                TimeOffRequest(
                    org_id=org.id,
                    physician_id=physicians[physician_index].id,
                    start_date=start,
                    end_date=start + timedelta(days=length - 1),
                    request_type=kind,
                    priority=priority,
                    status=status,
                    reason=f"{kind.value.title()} -- seeded demo request",
                )
            )

        # A couple of period-scoped preferences on top of the standing ones.
        for physician_index, category, level, note in (
            (2, ShiftCategory.NIGHT, -2, "Nights are rough this month -- kid's school schedule"),
            (8, ShiftCategory.NIGHT, 2, "Happy to take extra nights while saving for a house"),
        ):
            db.add(
                ShiftPreference(
                    org_id=org.id,
                    physician_id=physicians[physician_index].id,
                    effective_start=period_start,
                    effective_end=period_end,
                    category=category,
                    level=level,
                    note=note,
                )
            )

        db.commit()

        # Run the optimizer for real and publish, so the calendar, fairness
        # report, hours report and swap marketplace all have live data.
        published = []
        for site in (main, north):
            run = generate_schedule(
                db=db,
                org_id=org.id,
                site_id=site.id,
                period_start=period_start,
                period_end=period_end,
                created_by_user_id=admin.id,
                time_limit_seconds=20.0,
            )
            run.status = ScheduleRunStatus.PUBLISHED
            db.commit()
            published.append(run)

        return {
            "org": org.name,
            "slug": slug,
            "admin_email": admin_email,
            "physician_logins": [p.email for p in physicians[:3]],
            "password": password,
            "sites": [main.name, north.name],
            "physicians": len(physicians),
            "period": f"{period_start} to {period_end}",
            "runs": [
                {
                    "site": site.name,
                    "status": run.solver_status,
                    "unfilled": run.unfilled_shift_count,
                    "seconds": round(run.solve_seconds or 0, 1),
                }
                for site, run in zip((main, north), published)
            ],
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a demo organization.")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="organization slug (default: %(default)s)")
    parser.add_argument("--email", default=None, help="admin login email")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="password for all seeded logins")
    parser.add_argument("--reset", action="store_true", help="delete an existing org with this slug first")
    args = parser.parse_args()

    if args.reset:
        database.init_db()
        db = database.SessionLocal()
        try:
            wipe(db, args.slug)
        finally:
            db.close()

    result = seed(slug=args.slug, admin_email=args.email, password=args.password)

    print()
    print(f"  Seeded {result['org']}")
    print(f"  {result['physicians']} physicians across {len(result['sites'])} sites, {result['period']}")
    for run in result["runs"]:
        print(f"    - {run['site']}: solver {run['status']}, {run['unfilled']} unfilled, {run['seconds']}s")
    print()
    print("  Sign in as the scheduler/admin:")
    print(f"    {result['admin_email']}  /  {result['password']}")
    print("  Or as a physician, to see the self-service side:")
    for email in result["physician_logins"]:
        print(f"    {email}  /  {result['password']}")
    print()


if __name__ == "__main__":
    main()

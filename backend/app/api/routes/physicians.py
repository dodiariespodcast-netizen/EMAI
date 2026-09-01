import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.enums import EmploymentType, UserRole
from app.models.physician import Physician, PhysicianSite
from app.models.tenancy import User
from app.schemas.physician import (
    PhysicianCreate,
    PhysicianImportResult,
    PhysicianPreferencesUpdate,
    PhysicianRead,
    PhysicianUpdate,
)
from app.services.audit import log_audit

router = APIRouter(prefix="/physicians", tags=["physicians"])


def _to_read(physician: Physician, db: Session) -> PhysicianRead:
    site_ids = [
        ps.site_id for ps in db.query(PhysicianSite).filter(PhysicianSite.physician_id == physician.id)
    ]
    data = PhysicianRead.model_validate(physician).model_dump()
    data["site_ids"] = site_ids
    return PhysicianRead(**data)


@router.post("", response_model=PhysicianRead, status_code=201)
def create_physician(
    payload: PhysicianCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> PhysicianRead:
    data = payload.model_dump(exclude={"site_ids"})
    physician = Physician(org_id=current_user.org_id, **data)
    db.add(physician)
    db.flush()
    for site_id in payload.site_ids:
        db.add(PhysicianSite(physician_id=physician.id, site_id=site_id))
    db.commit()
    db.refresh(physician)
    return _to_read(physician, db)


@router.get("", response_model=list[PhysicianRead])
def list_physicians(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PhysicianRead]:
    q = db.query(Physician).filter(Physician.org_id == current_user.org_id)
    if active_only:
        q = q.filter(Physician.is_active.is_(True))
    return [_to_read(p, db) for p in q.all()]


@router.get("/{physician_id}", response_model=PhysicianRead)
def get_physician(
    physician_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> PhysicianRead:
    physician = (
        db.query(Physician)
        .filter(Physician.id == physician_id, Physician.org_id == current_user.org_id)
        .first()
    )
    if physician is None:
        raise HTTPException(status_code=404, detail="Physician not found")
    return _to_read(physician, db)


@router.patch("/{physician_id}", response_model=PhysicianRead)
def update_physician(
    physician_id: str,
    payload: PhysicianUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> PhysicianRead:
    physician = (
        db.query(Physician)
        .filter(Physician.id == physician_id, Physician.org_id == current_user.org_id)
        .first()
    )
    if physician is None:
        raise HTTPException(status_code=404, detail="Physician not found")

    updates = payload.model_dump(exclude_unset=True, exclude={"site_ids"})
    for field, value in updates.items():
        setattr(physician, field, value)

    if payload.site_ids is not None:
        db.query(PhysicianSite).filter(PhysicianSite.physician_id == physician.id).delete()
        for site_id in payload.site_ids:
            db.add(PhysicianSite(physician_id=physician.id, site_id=site_id))

    db.commit()
    db.refresh(physician)
    return _to_read(physician, db)


@router.patch("/{physician_id}/preferences", response_model=PhysicianRead)
def update_own_preferences(
    physician_id: str,
    payload: PhysicianPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PhysicianRead:
    """Self-service preference editing: a physician can update their own
    night/weekend/holiday preference without scheduler privileges. A
    scheduler can also use this (or the full PATCH /physicians/{id})."""
    is_self = current_user.physician_id == physician_id
    is_scheduler = current_user.role in (UserRole.OWNER, UserRole.ADMIN, UserRole.SCHEDULER)
    if not is_self and not is_scheduler:
        raise HTTPException(status_code=403, detail="Not authorized to edit this physician's preferences")

    physician = (
        db.query(Physician)
        .filter(Physician.id == physician_id, Physician.org_id == current_user.org_id)
        .first()
    )
    if physician is None:
        raise HTTPException(status_code=404, detail="Physician not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(physician, field, value)
    db.commit()
    db.refresh(physician)
    return _to_read(physician, db)


@router.delete("/{physician_id}", status_code=204)
def deactivate_physician(
    physician_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> None:
    """Soft delete: physicians are never hard-deleted so historical
    schedules keep valid references."""
    physician = (
        db.query(Physician)
        .filter(Physician.id == physician_id, Physician.org_id == current_user.org_id)
        .first()
    )
    if physician is None:
        raise HTTPException(status_code=404, detail="Physician not found")
    physician.is_active = False
    db.commit()


@router.get("/import/template.csv")
def download_import_template(_current_user: User = Depends(require_scheduler)) -> Response:
    """The exact CSV shape /physicians/import expects, with one example row.
    Onboarding a 40-person group by hand is the difference between a customer
    trying the product and giving up on it."""
    header = (
        "first_name,last_name,email,credentials,fte,seniority_years,employment_type,"
        "hourly_rate,night_preference,weekend_preference,holiday_preference\n"
    )
    example = "Dana,Reyes,dana.reyes@example.com,MD,1.0,7,employed,,-1,0,0\n"
    return Response(
        content=header + example,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="physician-import-template.csv"'},
    )


@router.post("/import", response_model=PhysicianImportResult)
async def import_physicians(
    file: UploadFile = File(...),
    site_ids: str = Form(""),
    dry_run: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> PhysicianImportResult:
    """Bulk-create physicians from a CSV.

    Rows are validated independently: a bad row is reported with its line
    number and skipped rather than failing the whole file, and `dry_run`
    validates without writing so an admin can check a file first.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "email" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(
            status_code=400,
            detail="CSV needs a header row including at least first_name, last_name, email",
        )

    target_sites = [s for s in site_ids.split(",") if s.strip()]
    existing_emails = {
        p.email.lower()
        for p in db.query(Physician).filter(Physician.org_id == current_user.org_id).all()
    }

    created: list[str] = []
    errors: list[dict] = []

    for line_number, row in enumerate(reader, start=2):  # line 1 is the header
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        first, last, email = clean.get("first_name"), clean.get("last_name"), clean.get("email")

        if not any([first, last, email]):
            continue  # blank padding row
        if not (first and last and email):
            errors.append({"line": line_number, "error": "first_name, last_name and email are all required"})
            continue
        if email.lower() in existing_emails:
            errors.append({"line": line_number, "error": f"{email} is already on the roster"})
            continue

        try:
            physician = Physician(
                org_id=current_user.org_id,
                first_name=first,
                last_name=last,
                email=email,
                credentials=clean.get("credentials") or "MD",
                fte=_as_float(clean.get("fte"), 1.0, "fte", 0.0, 1.0),
                seniority_years=_as_float(clean.get("seniority_years"), 0.0, "seniority_years", 0.0, 80.0),
                employment_type=EmploymentType(clean.get("employment_type") or "employed"),
                hourly_rate=_as_optional_float(clean.get("hourly_rate"), "hourly_rate"),
                night_preference=int(_as_float(clean.get("night_preference"), 0, "night_preference", -2, 2)),
                weekend_preference=int(_as_float(clean.get("weekend_preference"), 0, "weekend_preference", -2, 2)),
                holiday_preference=int(_as_float(clean.get("holiday_preference"), 0, "holiday_preference", -2, 2)),
            )
        except ValueError as exc:
            errors.append({"line": line_number, "error": str(exc)})
            continue

        existing_emails.add(email.lower())
        created.append(email)
        if not dry_run:
            db.add(physician)
            db.flush()
            for site_id in target_sites:
                db.add(PhysicianSite(physician_id=physician.id, site_id=site_id))

    if dry_run:
        db.rollback()
    else:
        log_audit(
            db, current_user.org_id, "physician.import", "physician", None, user_id=current_user.id,
            details={"created": len(created), "errors": len(errors)},
        )
        db.commit()

    return PhysicianImportResult(
        dry_run=dry_run,
        created_count=len(created),
        created_emails=created,
        error_count=len(errors),
        errors=errors,
    )


def _as_float(value: str | None, default: float, field: str, low: float, high: float) -> float:
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(f"{field} must be a number, got {value!r}")
    if not low <= parsed <= high:
        raise ValueError(f"{field} must be between {low:g} and {high:g}, got {parsed:g}")
    return parsed


def _as_optional_float(value: str | None, field: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value.replace("$", "").replace(",", ""))
    except ValueError:
        raise ValueError(f"{field} must be a number, got {value!r}")
    if parsed < 0:
        raise ValueError(f"{field} cannot be negative")
    return parsed

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.database import get_db
from app.models.enums import AssignmentStatus, SwapStatus, UserRole
from app.models.physician import Physician
from app.models.schedule import Assignment, ShiftSwapRequest
from app.models.shift import ShiftInstance
from app.models.tenancy import User
from app.schemas.swap import ShiftSwapClaim, ShiftSwapCreate, ShiftSwapRead, ShiftSwapRejection
from app.services.audit import log_audit
from app.services.notifications.notify import notify_swap_claimed, notify_swap_decided
from app.services.scheduling.service import get_or_create_rules
from app.services.scheduling.swap_conflicts import find_swap_conflict

router = APIRouter(prefix="/shift-swaps", tags=["shift-swaps"])


def _own_physician_or_scheduler(current_user: User, physician_id: str) -> None:
    if current_user.physician_id == physician_id:
        return
    if current_user.role in (UserRole.OWNER, UserRole.ADMIN, UserRole.SCHEDULER):
        return
    raise HTTPException(status_code=403, detail="Not authorized for this physician")


def _physician_email_name(db: Session, physician_id: str) -> tuple[str | None, str]:
    physician = db.query(Physician).filter(Physician.id == physician_id).first()
    name = f"{physician.first_name} {physician.last_name}" if physician else "Unknown"
    user = db.query(User).filter(User.physician_id == physician_id).first()
    return (user.email if user else None), name


@router.post("", response_model=ShiftSwapRead, status_code=201)
def offer_swap(
    payload: ShiftSwapCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ShiftSwapRead:
    assignment = (
        db.query(Assignment)
        .filter(Assignment.id == payload.assignment_id, Assignment.org_id == current_user.org_id)
        .first()
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _own_physician_or_scheduler(current_user, assignment.physician_id)

    existing_open = (
        db.query(ShiftSwapRequest)
        .filter(
            ShiftSwapRequest.assignment_id == assignment.id,
            ShiftSwapRequest.status.in_([SwapStatus.OPEN, SwapStatus.CLAIMED]),
        )
        .first()
    )
    if existing_open is not None:
        raise HTTPException(status_code=400, detail="This shift already has an open swap request")

    swap = ShiftSwapRequest(
        org_id=current_user.org_id,
        assignment_id=assignment.id,
        offering_physician_id=assignment.physician_id,
        target_physician_id=payload.target_physician_id,
        note=payload.note,
        status=SwapStatus.OPEN,
    )
    db.add(swap)
    db.flush()
    log_audit(db, current_user.org_id, "shift_swap.offer", "shift_swap_request", swap.id, user_id=current_user.id)
    db.commit()
    db.refresh(swap)
    return ShiftSwapRead.model_validate(swap)


@router.get("", response_model=list[ShiftSwapRead])
def list_swaps(
    status_filter: SwapStatus | None = None,
    physician_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ShiftSwapRead]:
    q = db.query(ShiftSwapRequest).filter(ShiftSwapRequest.org_id == current_user.org_id)
    if status_filter:
        q = q.filter(ShiftSwapRequest.status == status_filter)
    if physician_id:
        q = q.filter(
            (ShiftSwapRequest.offering_physician_id == physician_id)
            | (ShiftSwapRequest.claimed_by_physician_id == physician_id)
        )
    return q.order_by(ShiftSwapRequest.created_at.desc()).all()


@router.post("/{swap_id}/claim", response_model=ShiftSwapRead)
def claim_swap(
    swap_id: str,
    payload: ShiftSwapClaim,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ShiftSwapRead:
    claimant_physician_id = payload.physician_id
    swap = _get_swap_or_404(db, current_user.org_id, swap_id)
    if swap.status != SwapStatus.OPEN:
        raise HTTPException(status_code=400, detail="This swap is no longer open")
    if swap.target_physician_id and swap.target_physician_id != claimant_physician_id:
        raise HTTPException(status_code=403, detail="This shift was offered to a specific physician")
    if swap.offering_physician_id == claimant_physician_id:
        raise HTTPException(status_code=400, detail="Cannot claim your own offered shift")
    _own_physician_or_scheduler(current_user, claimant_physician_id)

    swap.claimed_by_physician_id = claimant_physician_id
    swap.status = SwapStatus.CLAIMED
    log_audit(
        db, current_user.org_id, "shift_swap.claim", "shift_swap_request", swap.id, user_id=current_user.id,
        details={"claimant": claimant_physician_id},
    )
    db.commit()
    db.refresh(swap)

    email, offering_name = _physician_email_name(db, swap.offering_physician_id)
    _, claimant_name = _physician_email_name(db, claimant_physician_id)
    assignment = db.query(Assignment).filter(Assignment.id == swap.assignment_id).first()
    shift = db.query(ShiftInstance).filter(ShiftInstance.id == assignment.shift_instance_id).first()
    if email:
        notify_swap_claimed(email, offering_name, claimant_name, shift.date if shift else "the requested date")
    return ShiftSwapRead.model_validate(swap)


@router.post("/{swap_id}/approve", response_model=ShiftSwapRead)
def approve_swap(
    swap_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_scheduler)
) -> ShiftSwapRead:
    swap = _get_swap_or_404(db, current_user.org_id, swap_id)
    if swap.status != SwapStatus.CLAIMED:
        raise HTTPException(status_code=400, detail="Swap must be claimed before it can be approved")

    assignment = db.query(Assignment).filter(Assignment.id == swap.assignment_id).first()
    shift = db.query(ShiftInstance).filter(ShiftInstance.id == assignment.shift_instance_id).first()
    rules = get_or_create_rules(db, current_user.org_id)

    conflict = find_swap_conflict(db, current_user.org_id, shift, swap.claimed_by_physician_id, rules)
    if conflict:
        raise HTTPException(status_code=409, detail=f"Cannot approve: {conflict}")

    assignment.physician_id = swap.claimed_by_physician_id
    assignment.status = AssignmentStatus.SWAPPED
    swap.status = SwapStatus.APPROVED
    swap.decided_by_user_id = current_user.id
    log_audit(db, current_user.org_id, "shift_swap.approve", "shift_swap_request", swap.id, user_id=current_user.id)
    db.commit()
    db.refresh(swap)

    for physician_id in (swap.offering_physician_id, swap.claimed_by_physician_id):
        email, name = _physician_email_name(db, physician_id)
        if email:
            notify_swap_decided(email, name, shift.date, approved=True)
    return ShiftSwapRead.model_validate(swap)


@router.post("/{swap_id}/reject", response_model=ShiftSwapRead)
def reject_swap(
    swap_id: str,
    payload: ShiftSwapRejection,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> ShiftSwapRead:
    swap = _get_swap_or_404(db, current_user.org_id, swap_id)
    if swap.status not in (SwapStatus.OPEN, SwapStatus.CLAIMED):
        raise HTTPException(status_code=400, detail="Swap is already decided")
    swap.status = SwapStatus.REJECTED
    swap.decided_by_user_id = current_user.id
    log_audit(
        db, current_user.org_id, "shift_swap.reject", "shift_swap_request", swap.id, user_id=current_user.id,
        details={"reason": payload.reason},
    )
    db.commit()
    db.refresh(swap)

    assignment = db.query(Assignment).filter(Assignment.id == swap.assignment_id).first()
    shift = db.query(ShiftInstance).filter(ShiftInstance.id == assignment.shift_instance_id).first()
    physicians = [swap.offering_physician_id] + ([swap.claimed_by_physician_id] if swap.claimed_by_physician_id else [])
    for physician_id in physicians:
        email, name = _physician_email_name(db, physician_id)
        if email:
            notify_swap_decided(email, name, shift.date, approved=False)
    return ShiftSwapRead.model_validate(swap)


@router.post("/{swap_id}/cancel", response_model=ShiftSwapRead)
def cancel_swap(
    swap_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ShiftSwapRead:
    swap = _get_swap_or_404(db, current_user.org_id, swap_id)
    _own_physician_or_scheduler(current_user, swap.offering_physician_id)
    if swap.status != SwapStatus.OPEN:
        raise HTTPException(status_code=400, detail="Only an open, unclaimed swap can be cancelled")
    swap.status = SwapStatus.CANCELLED
    log_audit(db, current_user.org_id, "shift_swap.cancel", "shift_swap_request", swap.id, user_id=current_user.id)
    db.commit()
    db.refresh(swap)
    return ShiftSwapRead.model_validate(swap)


def _get_swap_or_404(db: Session, org_id: str, swap_id: str) -> ShiftSwapRequest:
    swap = (
        db.query(ShiftSwapRequest)
        .filter(ShiftSwapRequest.id == swap_id, ShiftSwapRequest.org_id == org_id)
        .first()
    )
    if swap is None:
        raise HTTPException(status_code=404, detail="Shift swap not found")
    return swap

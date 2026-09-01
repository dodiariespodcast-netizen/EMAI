from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import (
    RequestPriority,
    RequestStatus,
    ShiftCategory,
    TimeOffType,
)
from app.models.mixins import TimestampMixin, UUIDPKMixin


class TimeOffRequest(Base, UUIDPKMixin, TimestampMixin):
    """A physician's request to not be scheduled over a date range.

    MUST-priority requests are a hard constraint: the solver will never
    violate an APPROVED must-off request. PREFERRED requests are a soft
    constraint weighted into the objective alongside everyone else's asks.
    """

    __tablename__ = "time_off_requests"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    physician_id: Mapped[str] = mapped_column(ForeignKey("physicians.id"), index=True, nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    request_type: Mapped[TimeOffType] = mapped_column(default=TimeOffType.PERSONAL)
    priority: Mapped[RequestPriority] = mapped_column(default=RequestPriority.PREFERRED)
    status: Mapped[RequestStatus] = mapped_column(default=RequestStatus.PENDING, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Populated when the request originated as free text parsed by the AI layer.
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    physician: Mapped["Physician"] = relationship()  # noqa: F821


class ShiftPreference(Base, UUIDPKMixin, TimestampMixin):
    """A standing, period-scoped preference such as 'avoid nights in
    December' or 'prefer weekends this quarter', distinct from a one-off
    time-off request. Feeds the solver's soft-constraint objective."""

    __tablename__ = "shift_preferences"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    physician_id: Mapped[str] = mapped_column(ForeignKey("physicians.id"), index=True, nullable=False)

    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[ShiftCategory] = mapped_column(default=ShiftCategory.NIGHT)
    # -2 (strongly avoid) .. +2 (strongly prefer)
    level: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

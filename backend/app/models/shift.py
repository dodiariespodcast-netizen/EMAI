from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ShiftCategory
from app.models.mixins import TimestampMixin, UUIDPKMixin


class ShiftType(Base, UUIDPKMixin, TimestampMixin):
    """A reusable shift template, e.g. 'Day 07-19' or 'Night 19-07'."""

    __tablename__ = "shift_types"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[ShiftCategory] = mapped_column(default=ShiftCategory.DAY)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_hours: Mapped[float] = mapped_column(Float, nullable=False)
    required_physicians: Mapped[int] = mapped_column(Integer, default=1)

    instances: Mapped[list["ShiftInstance"]] = relationship(
        back_populates="shift_type", cascade="all, delete-orphan"
    )


class ShiftInstance(Base, UUIDPKMixin, TimestampMixin):
    """A concrete, dated slot that needs to be staffed. Generated in bulk
    from a ShiftType over a date range, or created ad hoc for one-off
    coverage needs."""

    __tablename__ = "shift_instances"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True, nullable=False)
    shift_type_id: Mapped[str] = mapped_column(ForeignKey("shift_types.id"), index=True, nullable=False)
    schedule_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("schedule_runs.id"), index=True, nullable=True
    )

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[ShiftCategory] = mapped_column(default=ShiftCategory.DAY)
    required_physicians: Mapped[int] = mapped_column(Integer, default=1)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)

    shift_type: Mapped["ShiftType"] = relationship(back_populates="instances")

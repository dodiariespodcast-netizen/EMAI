from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Physician(Base, UUIDPKMixin, TimestampMixin):
    """A schedulable clinician. Preference weights and rule overrides live
    here so the solver can read one row per physician when building its
    objective function."""

    __tablename__ = "physicians"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    credentials: Mapped[str] = mapped_column(String(50), default="MD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # FTE (full-time-equivalent), e.g. 1.0 = full time, 0.5 = half time.
    # Drives each physician's fair-share target shift count for a period.
    fte: Mapped[float] = mapped_column(Float, default=1.0)

    # Seniority in years at the group. Used as a tie-breaker weight so that
    # preference satisfaction can (optionally) skew toward tenure, mirroring
    # how most EM groups actually negotiate schedules today.
    seniority_years: Mapped[float] = mapped_column(Float, default=0.0)

    # Preference weights in [-2, 2]: negative = avoid, positive = prefer.
    night_preference: Mapped[int] = mapped_column(Integer, default=0)
    weekend_preference: Mapped[int] = mapped_column(Integer, default=0)
    holiday_preference: Mapped[int] = mapped_column(Integer, default=0)

    # Personal scheduling rules; None falls back to the org-wide SchedulingRule.
    max_consecutive_shifts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_rest_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_shifts_per_period: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Named distinctly from the PhysicianRead.site_ids API field (a plain
    # list[str]) so pydantic's from_attributes can't accidentally pick this
    # relationship (a list of PhysicianSite rows) up for that field.
    physician_sites: Mapped[list["PhysicianSite"]] = relationship(
        back_populates="physician", cascade="all, delete-orphan"
    )


class PhysicianSite(Base, UUIDPKMixin):
    """Which sites a physician is credentialed/eligible to work at."""

    __tablename__ = "physician_sites"

    physician_id: Mapped[str] = mapped_column(ForeignKey("physicians.id"), index=True, nullable=False)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True, nullable=False)

    physician: Mapped["Physician"] = relationship(back_populates="physician_sites")

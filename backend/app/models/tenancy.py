from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import UserRole
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Organization(Base, UUIDPKMixin, TimestampMixin):
    """A tenant: one emergency medicine group / hospital system subscribing
    to the product. Every other row in the system is scoped to an org_id so
    customer data never crosses tenant boundaries."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    plan_tier: Mapped[str] = mapped_column(String(50), default="trial")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    sites: Mapped[list["Site"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Site(Base, UUIDPKMixin, TimestampMixin):
    """A physical location/department (e.g. 'Main ED', 'Downtown Campus')."""

    __tablename__ = "sites"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    organization: Mapped["Organization"] = relationship(back_populates="sites")


class User(Base, UUIDPKMixin, TimestampMixin):
    """A login account. May or may not be linked to a Physician record --
    schedulers/admins often aren't clinicians themselves."""

    __tablename__ = "users"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(default=UserRole.PHYSICIAN)
    physician_id: Mapped[str | None] = mapped_column(ForeignKey("physicians.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")

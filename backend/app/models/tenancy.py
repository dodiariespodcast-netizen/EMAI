from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import UserRole
from app.models.mixins import TimestampMixin, UUIDPKMixin, utcnow


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
    # Nullable: an account created via "Sign in with Google/Microsoft" has no
    # password until the user sets one (see /auth/change-password).
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(default=UserRole.PHYSICIAN)
    physician_id: Mapped[str | None] = mapped_column(ForeignKey("physicians.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    oauth_identities: Mapped[list["OAuthIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OAuthIdentity(Base, UUIDPKMixin, TimestampMixin):
    """Links a User to a 'Sign in with ___' identity (Google, Microsoft, ...).
    A user can link several -- e.g. password + Google -- and sign in with
    any of them."""

    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject", name="uq_oauth_identity_subject"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "google" | "microsoft"
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)  # provider's stable user id
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped["User"] = relationship(back_populates="oauth_identities")


class AuditLog(Base, UUIDPKMixin):
    """Append-only trail of who changed what. A compliance requirement most
    healthcare-adjacent buyers will ask about during procurement, and a
    genuine trust signal for locums agencies whose whole business is
    defensible records."""

    __tablename__ = "audit_logs"

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

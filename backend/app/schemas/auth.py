from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole


class OrgSignup(BaseModel):
    """Creates a new tenant organization plus its first (owner) user."""

    org_name: str = Field(min_length=2, max_length=255)
    org_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    email: EmailStr
    password: str = Field(min_length=8)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole = UserRole.PHYSICIAN
    physician_id: str | None = None


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    physician_id: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: str
    org_id: str
    email: EmailStr
    role: UserRole
    physician_id: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ChangePassword(BaseModel):
    current_password: str | None = None  # omit if the account has no password yet (OAuth-only)
    new_password: str = Field(min_length=8)


class OAuthProvider(BaseModel):
    provider: str = Field(pattern=r"^(google|microsoft)$")
    id_token: str


class OAuthSignup(OAuthProvider):
    """Creates a new tenant organization whose owner authenticates via an
    OAuth identity instead of a password."""

    org_name: str = Field(min_length=2, max_length=255)
    org_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")


class OAuthIdentityRead(BaseModel):
    id: str
    provider: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}

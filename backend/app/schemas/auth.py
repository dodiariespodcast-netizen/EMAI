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

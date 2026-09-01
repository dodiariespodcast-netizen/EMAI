from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_scheduler
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.enums import UserRole
from app.models.tenancy import OAuthIdentity, Organization, User
from app.schemas.auth import (
    ChangePassword,
    OAuthIdentityRead,
    OAuthProvider,
    OAuthSignup,
    OrgSignup,
    Token,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services.audit import log_audit
from app.services.auth.oauth import OAuthVerificationError, verify_id_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(user: User) -> Token:
    token = create_access_token(subject=user.id, extra_claims={"org_id": user.org_id, "role": user.role.value})
    return Token(access_token=token, user=UserRead.model_validate(user))


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup(payload: OrgSignup, db: Session = Depends(get_db)) -> Token:
    if db.query(Organization).filter(Organization.slug == payload.org_slug).first():
        raise HTTPException(status_code=400, detail="Organization slug already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    org = Organization(name=payload.org_name, slug=payload.org_slug)
    db.add(org)
    db.flush()

    user = User(
        org_id=org.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.OWNER,
    )
    db.add(user)
    db.flush()
    log_audit(db, org.id, "org.signup", "organization", org.id, user_id=user.id)
    db.commit()
    db.refresh(user)

    return _issue_token(user)


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is disabled")
    return _issue_token(user)


@router.post("/change-password", response_model=UserRead)
def change_password(
    payload: ChangePassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    if current_user.hashed_password is not None:
        if not payload.current_password or not verify_password(
            payload.current_password, current_user.hashed_password
        ):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> UserRead:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        org_id=current_user.org_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        physician_id=payload.physician_id,
    )
    db.add(user)
    db.flush()
    log_audit(
        db, current_user.org_id, "user.invite", "user", user.id, user_id=current_user.id,
        details={"email": payload.email, "role": payload.role.value},
    )
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_scheduler)) -> list[UserRead]:
    return db.query(User).filter(User.org_id == current_user.org_id).all()


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheduler),
) -> UserRead:
    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    log_audit(
        db, current_user.org_id, "user.update", "user", user.id, user_id=current_user.id,
        details=payload.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)


# ---- OAuth ("Sign in with Google/Microsoft") ----


@router.post("/oauth/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
def oauth_signup(payload: OAuthSignup, db: Session = Depends(get_db)) -> Token:
    """Creates a brand-new organization whose owner authenticates via
    Google/Microsoft instead of a password -- the "continue with Google"
    path on the signup screen."""
    identity = _verify_or_400(payload.provider, payload.id_token)
    if not identity.email_verified:
        raise HTTPException(status_code=400, detail="Provider email is not verified")
    if db.query(Organization).filter(Organization.slug == payload.org_slug).first():
        raise HTTPException(status_code=400, detail="Organization slug already taken")
    if db.query(User).filter(User.email == identity.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    org = Organization(name=payload.org_name, slug=payload.org_slug)
    db.add(org)
    db.flush()

    user = User(org_id=org.id, email=identity.email, hashed_password=None, role=UserRole.OWNER)
    db.add(user)
    db.flush()
    db.add(OAuthIdentity(user_id=user.id, provider=identity.provider, provider_subject=identity.subject, email=identity.email))
    log_audit(db, org.id, "org.signup", "organization", org.id, user_id=user.id, details={"via": identity.provider})
    db.commit()
    db.refresh(user)

    return _issue_token(user)


@router.post("/oauth/login", response_model=Token)
def oauth_login(payload: OAuthProvider, db: Session = Depends(get_db)) -> Token:
    """Signs in an existing user via a linked OAuth identity, or -- on
    first use, if a verified-email match exists (e.g. an admin invited them
    by email and they've never logged in with a password) -- auto-links
    the identity to that account."""
    identity = _verify_or_400(payload.provider, payload.id_token)

    existing = (
        db.query(OAuthIdentity)
        .filter(OAuthIdentity.provider == identity.provider, OAuthIdentity.provider_subject == identity.subject)
        .first()
    )
    if existing is not None:
        user = db.query(User).filter(User.id == existing.user_id).first()
    elif identity.email_verified:
        user = db.query(User).filter(User.email == identity.email).first()
        if user is not None:
            db.add(
                OAuthIdentity(
                    user_id=user.id, provider=identity.provider, provider_subject=identity.subject, email=identity.email
                )
            )
            log_audit(db, user.org_id, "user.oauth_auto_link", "user", user.id, user_id=user.id, details={"provider": identity.provider})
            db.commit()
    else:
        user = None

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="No account found for this identity. Sign up first, or ask an admin to invite this email.",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is disabled")
    return _issue_token(user)


@router.post("/oauth/link", response_model=OAuthIdentityRead, status_code=status.HTTP_201_CREATED)
def oauth_link(
    payload: OAuthProvider,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OAuthIdentityRead:
    """Attaches a Google/Microsoft identity to the signed-in account, e.g.
    someone who signed up with a password adding 'Sign in with Google' as a
    second way in."""
    identity = _verify_or_400(payload.provider, payload.id_token)
    conflict = (
        db.query(OAuthIdentity)
        .filter(OAuthIdentity.provider == identity.provider, OAuthIdentity.provider_subject == identity.subject)
        .first()
    )
    if conflict is not None:
        raise HTTPException(status_code=409, detail="This identity is already linked to an account")

    record = OAuthIdentity(
        user_id=current_user.id, provider=identity.provider, provider_subject=identity.subject, email=identity.email
    )
    db.add(record)
    log_audit(db, current_user.org_id, "user.oauth_link", "user", current_user.id, user_id=current_user.id, details={"provider": identity.provider})
    db.commit()
    db.refresh(record)
    return OAuthIdentityRead.model_validate(record)


@router.get("/oauth/identities", response_model=list[OAuthIdentityRead])
def list_oauth_identities(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[OAuthIdentityRead]:
    return db.query(OAuthIdentity).filter(OAuthIdentity.user_id == current_user.id).all()


@router.delete("/oauth/identities/{identity_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_oauth_identity(
    identity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    record = (
        db.query(OAuthIdentity)
        .filter(OAuthIdentity.id == identity_id, OAuthIdentity.user_id == current_user.id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Identity not found")
    if current_user.hashed_password is None:
        remaining = db.query(OAuthIdentity).filter(OAuthIdentity.user_id == current_user.id).count()
        if remaining <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot unlink your only sign-in method. Set a password first.",
            )
    db.delete(record)
    log_audit(db, current_user.org_id, "user.oauth_unlink", "user", current_user.id, user_id=current_user.id)
    db.commit()


def _verify_or_400(provider: str, id_token: str):
    try:
        return verify_id_token(provider, id_token)
    except OAuthVerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

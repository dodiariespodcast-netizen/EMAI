from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models.enums import UserRole
from app.models.tenancy import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise credentials_exception
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_scheduler(user: User = Depends(get_current_user)) -> User:
    """Physicians can view their own data / submit requests, but only
    schedulers, admins, and owners can manage rosters, shifts, and run the
    optimizer."""
    if user.role not in (UserRole.OWNER, UserRole.ADMIN, UserRole.SCHEDULER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Scheduler privileges required")
    return user

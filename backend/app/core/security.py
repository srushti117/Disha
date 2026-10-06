"""JWT auth, password hashing (PBKDF2-SHA256, stdlib) and role-based access control."""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db

settings = get_settings()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ROLES = ("admin", "commander", "analyst", "responder", "observer")

# capability -> roles allowed. Single source of truth for RBAC (also served to the UI).
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "view": ROLES,
    "event.write": ("admin", "commander", "analyst"),
    "event.process": ("admin", "commander", "analyst"),
    "priority.configure": ("admin", "commander"),
    "resource.assign": ("admin", "commander"),
    "route.plan": ("admin", "commander", "responder"),
    "field.report": ("admin", "commander", "responder"),
    "report.generate": ("admin", "commander", "analyst"),
    "admin": ("admin",),
    "data.manage": ("admin", "analyst"),
}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"pbkdf2${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), 120_000)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def create_token(user_id: int, email: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "role": role, "exp": exp},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}") from e


def current_user(
    token: str | None = Depends(oauth2),
    access_token: str | None = Query(default=None, description="For <img>/download URLs that cannot send headers"),
    db: Session = Depends(get_db),
):
    from ..models import User

    raw = token or access_token
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    claims = _decode(raw)
    user = db.get(User, int(claims["sub"]))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")
    return user


def require(permission: str):
    allowed = PERMISSIONS[permission]

    def dep(user=Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{user.role}' lacks permission '{permission}'")
        return user

    return dep

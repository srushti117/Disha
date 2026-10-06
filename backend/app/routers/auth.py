from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import PERMISSIONS, ROLES, create_token, current_user, hash_password, require, verify_password
from ..models import User
from ..services.common import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class UserIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active, "is_demo": u.is_demo}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalars(select(User).where(User.email == body.email.lower().strip())).first()
    if not u or not u.active or not verify_password(body.password, u.hashed_password):
        audit(db, None, "auth.login_failed", body.email)
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    audit(db, u, "auth.login", u.email)
    db.commit()
    return {"access_token": create_token(u.id, u.email, u.role), "token_type": "bearer", "user": user_out(u),
            "permissions": [p for p, roles in PERMISSIONS.items() if u.role in roles]}


@router.get("/me")
def me(u: User = Depends(current_user)):
    return {**user_out(u), "permissions": [p for p, roles in PERMISSIONS.items() if u.role in roles]}


@router.post("/users", status_code=201)
def create_user(body: UserIn, admin: User = Depends(require("admin")), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    if db.scalars(select(User).where(User.email == body.email.lower())).first():
        raise HTTPException(409, "Email already registered")
    u = User(email=body.email.lower(), name=body.name, role=body.role, hashed_password=hash_password(body.password))
    db.add(u)
    audit(db, admin, "user.create", body.email, detail={"role": body.role})
    db.commit()
    return user_out(u)

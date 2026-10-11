"""Password hashing (bcrypt), JWT (HS256), the current-user dependency and role checks."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.errors import AppError
from app.logging import get_logger
from app.models import User

log = get_logger("app")

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "migrateiq"
DEMO_USERS: tuple[tuple[str, str], ...] = (("operator", "operator"), ("approver", "approver"))

# Used when the username does not exist, so a failed login costs the same as a wrong password.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12))

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password.encode("utf-8")
    if len(candidate) > 72:  # bcrypt's input limit; longer inputs are never valid here
        return False
    target = password_hash.encode("ascii") if password_hash else _DUMMY_HASH
    ok = bcrypt.checkpw(candidate, target)
    return ok and password_hash is not None


def create_access_token(user: User | CurrentUser, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iss": JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings | None = None) -> CurrentUser:
    settings = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_signing_key,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "sub", "iss"]},
        )
        return CurrentUser(id=int(claims["sub"]), username=claims["username"], role=claims["role"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AppError("UNAUTHENTICATED", "Your session is invalid or has expired.") from exc


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            "UNAUTHENTICATED", "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"}
        )
    user = decode_access_token(credentials.credentials)
    request.scope.setdefault("state", {})["user"] = user.username
    structlog.contextvars.bind_contextvars(user=user.username)
    return user


def require_role(*roles: str) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    async def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise AppError(
                "FORBIDDEN",
                f"This action needs the {' or '.join(roles)} role.",
                details={"required_roles": list(roles), "your_role": user.role},
            )
        return user

    return _dependency


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if not verify_password(password, user.password_hash if user else None):
        return None
    return user


def seed_demo_users(db: Session, settings: Settings | None = None) -> None:
    """Upsert the two demo accounts. Re-hashes only when the configured password changed."""
    settings = settings or get_settings()
    for username, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            password_hash = hash_password(settings.demo_password)
            db.add(User(username=username, role=role, password_hash=password_hash))
            log.info("auth.demo_user.created", username=username, role=role)
        else:
            changed = False
            if user.role != role:
                user.role = role
                changed = True
            if not verify_password(settings.demo_password, user.password_hash):
                user.password_hash = hash_password(settings.demo_password)
                changed = True
            if changed:
                log.info("auth.demo_user.updated", username=username, role=role)
    db.commit()

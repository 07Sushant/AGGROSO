from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.logging import get_logger
from app.schemas.api import LoginRequest, LoginResponse, UserOut
from app.security import CurrentUser, authenticate, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("app")


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = authenticate(db, body.username.strip(), body.password)
    if user is None:
        log.info("auth.login_failed", username=body.username[:80])
        raise AppError("UNAUTHENTICATED", "Invalid username or password.")
    log.info("auth.login", username=user.username, role=user.role)
    settings = get_settings()
    return LoginResponse(
        access_token=create_access_token(user, settings),
        expires_in=settings.jwt_ttl_hours * 3600,
        user=UserOut(id=user.id, username=user.username, role=user.role),  # type: ignore[arg-type]
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role)  # type: ignore[arg-type]

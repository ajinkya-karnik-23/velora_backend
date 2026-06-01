"""Auth endpoints — login, refresh, logout, me."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.schemas.token import TokenResponse
from app.schemas.user import UserOut
from app.services.auth_service import AuthService

router = APIRouter()

_COOKIE_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400


class LoginRequest:
    """Form-style dependency for login credentials."""

    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password


@router.post("/login-user", response_model=TokenResponse)
async def login(
    creds: LoginRequest = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = AuthService(db)
    token_resp, refresh_token = await service.login(creds.email, creds.password)
    response = Response(
        content=token_resp.model_dump_json(),
        media_type="application/json",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api/v1/auth",
        max_age=_COOKIE_MAX_AGE,
    )
    return response


@router.post("/refresh-token", response_model=TokenResponse)
async def refresh(
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if not refresh_token:
        from app.core.exceptions import UnauthorizedException

        raise UnauthorizedException("Refresh token missing.")
    service = AuthService(db)
    token_resp, new_refresh = await service.refresh(refresh_token)
    response = Response(
        content=token_resp.model_dump_json(),
        media_type="application/json",
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api/v1/auth",
        max_age=_COOKIE_MAX_AGE,
    )
    return response


@router.post("/logout-user")
async def logout() -> Response:
    response = Response(content='{"detail":"Logged out"}', media_type="application/json")
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")
    return response


@router.get("/get-current-user", response_model=UserOut)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    service = AuthService(db)
    return await service.get_me(int(current_user["sub"]))

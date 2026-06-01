"""Authentication service — login, refresh, logout, get_me."""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    verify_token,
)
from app.repositories.user_repo import UserRepo
from app.schemas.token import TokenResponse
from app.schemas.user import UserOut


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepo(db)

    async def login(self, email: str, password: str) -> tuple[TokenResponse, str]:
        """Authenticate user, return (token_response, refresh_token_str)."""
        user = await self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise UnauthorizedException("Invalid email or password.")
        if user.status == "Deactivated":
            raise UnauthorizedException("Account is deactivated.")

        roles, permissions = await self.user_repo.get_roles_and_permissions(user.user_id)
        token_data = {"sub": user.user_id, "roles": roles, "permissions": permissions}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # Update last_login
        user.last_login = int(time.time())
        await self.db.commit()

        return TokenResponse(access_token=access_token), refresh_token

    async def refresh(self, refresh_token: str) -> tuple[TokenResponse, str]:
        """Verify refresh token and reissue access + refresh tokens."""
        try:
            payload = verify_token(refresh_token)
        except Exception:
            raise UnauthorizedException("Invalid or expired refresh token.")
        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid token type.")

        user_id = int(payload["sub"])
        user = await self.user_repo.get_by_id(user_id)
        if not user or user.status == "Deactivated":
            raise UnauthorizedException("User not found or deactivated.")

        roles, permissions = await self.user_repo.get_roles_and_permissions(user.user_id)
        token_data = {"sub": user.user_id, "roles": roles, "permissions": permissions}
        new_access = create_access_token(token_data)
        new_refresh = create_refresh_token(token_data)

        return TokenResponse(access_token=new_access), new_refresh

    async def get_me(self, user_id: int) -> UserOut:
        """Return current user profile with roles and permissions."""
        user = await self.user_repo.get_with_roles_permissions(user_id)
        if not user:
            raise UnauthorizedException("User not found.")
        roles, permissions = await self.user_repo.get_roles_and_permissions(user.user_id)
        return UserOut(
            **{c.key: getattr(user, c.key) for c in user.__table__.columns},
            roles=roles,
            permissions=permissions,
        )

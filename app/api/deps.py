"""Shared FastAPI dependencies — DB session, auth, RBAC, repo/service factories."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import verify_token
from app.db.session import async_session_maker

# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session. The service layer owns commit/rollback."""
    async with async_session_maker() as session:
        yield session


# ---------------------------------------------------------------------------
# Role hierarchy (higher index = more privileged)
# ---------------------------------------------------------------------------

ROLE_HIERARCHY: dict[str, int] = {
    "Viewer": 0,
    "Auditor": 1,
    "Moderator": 2,
    "Admin": 3,
}


# ---------------------------------------------------------------------------
# Current user extraction
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Decode JWT and return the token payload.

    Full user-from-DB lookup will be added in Phase 2 once the User model
    exists.  For now we return the decoded JWT payload dict with keys:
    sub, roles, permissions.
    """
    if credentials is None:
        raise UnauthorizedException()
    try:
        payload = verify_token(credentials.credentials)
    except Exception:
        raise UnauthorizedException("Invalid or expired token.")
    if payload.get("type") != "access":
        raise UnauthorizedException("Invalid token type.")
    return payload


# ---------------------------------------------------------------------------
# Role-based access
# ---------------------------------------------------------------------------


def require_role(*allowed_roles: str) -> Callable[..., Any]:
    """Return a dependency that checks the user has at least one of the allowed roles.

    Uses role hierarchy — e.g. Admin implicitly satisfies any role check.
    """

    async def _check(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        user_roles: list[str] = current_user.get("roles", [])
        # Direct match
        if any(r in allowed_roles for r in user_roles):
            return current_user
        # Hierarchy check: user has a higher-ranked role
        max_user_level = max((ROLE_HIERARCHY.get(r, -1) for r in user_roles), default=-1)
        min_required_level = min(
            (ROLE_HIERARCHY.get(r, 999) for r in allowed_roles), default=999
        )
        if max_user_level >= min_required_level:
            return current_user
        raise ForbiddenException("Insufficient role.")

    return _check


# ---------------------------------------------------------------------------
# Permission-based access
# ---------------------------------------------------------------------------


def require_permission(*required_perms: str) -> Callable[..., Any]:
    """Return a dependency that checks the JWT permissions claim."""

    async def _check(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        user_perms: list[str] = current_user.get("permissions", [])
        if all(p in user_perms for p in required_perms):
            return current_user
        raise ForbiddenException("Insufficient permissions.")

    return _check


# ---------------------------------------------------------------------------
# Engagement membership
# ---------------------------------------------------------------------------


async def require_engagement_member(
    cycle_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Check the user is a member of the engagement (or Admin/Moderator bypass)."""
    user_roles: list[str] = current_user.get("roles", [])
    if any(r in ("Admin", "Moderator") for r in user_roles):
        return current_user

    from app.repositories.engagement_team_repo import EngagementTeamRepo

    repo = EngagementTeamRepo(db)
    is_mem = await repo.is_member(cycle_id, int(current_user["sub"]))
    if is_mem:
        return current_user
    raise ForbiddenException("Not a member of this engagement.")

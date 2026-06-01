"""User repository — extends BaseRepo with user-specific queries."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_role import UserRole
from app.repositories.base_repo import BaseRepo


class UserRepo(BaseRepo[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_roles_permissions(self, user_id: int) -> User | None:
        """Load user with eager-loaded roles and permissions (4-table join)."""
        stmt = (
            select(User)
            .where(User.user_id == user_id)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_roles_and_permissions(self, user_id: int) -> tuple[list[str], list[str]]:
        """Return (role_names, permission_keys) for a user via joins."""
        # Roles
        role_stmt = (
            select(Role.role_name)
            .join(UserRole, UserRole.role_id == Role.role_id)
            .where(UserRole.user_id == user_id)
        )
        role_result = await self.session.execute(role_stmt)
        roles = list(role_result.scalars().all())

        # Permissions via role_permissions
        perm_stmt = (
            select(Permission.permission_key)
            .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
        perm_result = await self.session.execute(perm_stmt)
        permissions = list(perm_result.scalars().all())

        return roles, permissions

    async def get_stats(self) -> dict:
        """Return user counts grouped by status + 2FA enabled count."""
        status_stmt = (
            select(User.status, func.count(User.user_id)).group_by(User.status)
        )
        status_result = await self.session.execute(status_stmt)
        by_status = {row[0]: row[1] for row in status_result.all()}

        tfa_stmt = select(func.count(User.user_id)).where(User.two_factor_enabled.is_(True))
        tfa_result = await self.session.execute(tfa_stmt)
        two_factor_count = tfa_result.scalar() or 0

        return {"by_status": by_status, "two_factor_enabled_count": two_factor_count}

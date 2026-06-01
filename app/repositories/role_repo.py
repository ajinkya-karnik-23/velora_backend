"""Role repository."""

from __future__ import annotations

from sqlalchemy import select

from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.repositories.base_repo import BaseRepo


class RoleRepo(BaseRepo[Role]):
    model = Role

    async def get_by_name(self, role_name: str) -> Role | None:
        stmt = select(Role).where(Role.role_name == role_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_permissions_for_roles(self, role_ids: list[int]) -> list[str]:
        """Return distinct permission keys for a set of role IDs."""
        stmt = (
            select(Permission.permission_key)
            .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
            .where(RolePermission.role_id.in_(role_ids))
            .distinct()
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

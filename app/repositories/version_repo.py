"""Version repository."""

from __future__ import annotations

from sqlalchemy import select

from app.models.version import Version
from app.repositories.base_repo import BaseRepo


class VersionRepo(BaseRepo[Version]):
    model = Version

    async def get_current(self) -> Version | None:
        stmt = select(Version).where(Version.is_current.is_(True)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def clear_current(self) -> None:
        """Unset is_current on all versions (before setting a new current)."""
        from sqlalchemy import update

        stmt = update(Version).where(Version.is_current.is_(True)).values(is_current=False)
        await self.session.execute(stmt)
        await self.session.flush()

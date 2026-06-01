"""Version service — CRUD with is_current management."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.version import Version
from app.repositories.version_repo import VersionRepo
from app.schemas.version import VersionCreate, VersionOut, VersionUpdate


class VersionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.version_repo = VersionRepo(db)

    async def create_version(self, data: VersionCreate) -> VersionOut:
        if data.is_current:
            await self.version_repo.clear_current()
        version = Version(**data.model_dump())
        await self.version_repo.create(version)
        await self.db.commit()
        return VersionOut.model_validate(version)

    async def get_version(self, version_id: int) -> VersionOut:
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise NotFoundException("Version not found.")
        return VersionOut.model_validate(version)

    async def get_current(self) -> VersionOut:
        version = await self.version_repo.get_current()
        if not version:
            raise NotFoundException("No current version set.")
        return VersionOut.model_validate(version)

    async def list_versions(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[VersionOut], int]:
        count_stmt = select(func.count(Version.version_id))
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(Version)
            .order_by(Version.version_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        versions = [VersionOut.model_validate(v) for v in result.scalars().all()]
        return versions, total

    async def update_version(self, version_id: int, data: VersionUpdate) -> VersionOut:
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            raise NotFoundException("Version not found.")
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        if update_data.get("is_current"):
            await self.version_repo.clear_current()
        await self.version_repo.update(version, update_data)
        await self.db.commit()
        return VersionOut.model_validate(version)

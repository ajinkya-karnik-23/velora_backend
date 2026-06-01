"""Version endpoints — CRUD."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.schemas.common import PaginatedResponse
from app.schemas.version import VersionCreate, VersionOut, VersionUpdate
from app.services.version_service import VersionService

router = APIRouter()


@router.get("/list-versions", response_model=PaginatedResponse[VersionOut])
async def list_versions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = VersionService(db)
    versions, total = await service.list_versions(page, page_size)
    return {"data": versions, "total": total, "page": page, "page_size": page_size}


@router.get("/get-current-version", response_model=VersionOut)
async def get_current_version(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VersionOut:
    service = VersionService(db)
    return await service.get_current()


@router.post("/create-version", response_model=VersionOut, status_code=201)
async def create_version(
    data: VersionCreate,
    current_user: dict = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
) -> VersionOut:
    service = VersionService(db)
    return await service.create_version(data)


@router.put("/update-version", response_model=VersionOut)
async def update_version(
    version_id: int = Query(...),
    data: VersionUpdate = Body(...),
    current_user: dict = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
) -> VersionOut:
    service = VersionService(db)
    return await service.update_version(version_id, data)


@router.get("/get-version", response_model=VersionOut)
async def get_version(
    version_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VersionOut:
    service = VersionService(db)
    return await service.get_version(version_id)

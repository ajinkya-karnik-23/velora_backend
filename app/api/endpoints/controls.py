"""Control catalog endpoints — browse, detail, changelog. Read-only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.common import PaginatedResponse
from app.schemas.control import ChangeLogOut, ControlOut
from app.services.control_service import ControlService

router = APIRouter()


@router.get("/list-controls", response_model=PaginatedResponse[ControlOut])
async def browse_controls(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    domain: str | None = None,
    risk_level: str | None = None,
    frequency: str | None = None,
    framework: str | None = None,
    status: str | None = None,
    search: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ControlService(db)
    filters: dict[str, Any] = {}
    if domain:
        filters["domain"] = domain
    if risk_level:
        filters["risk_level"] = risk_level
    if frequency:
        filters["frequency"] = frequency
    if framework:
        filters["framework"] = framework
    if status:
        filters["status"] = status
    if search:
        filters["search"] = search
    controls, total = await service.browse(filters, page, page_size)
    return {"data": controls, "total": total, "page": page, "page_size": page_size}


@router.get("/get-control", response_model=ControlOut)
async def get_control(
    control_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ControlOut:
    service = ControlService(db)
    return await service.get_detail(control_id)


@router.get("/get-control-changelog", response_model=list[ChangeLogOut])
async def get_control_changelog(
    control_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChangeLogOut]:
    service = ControlService(db)
    return await service.get_changelog(control_id)

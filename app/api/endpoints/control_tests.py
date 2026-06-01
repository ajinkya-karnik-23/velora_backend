"""Control test endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.control_test import ControlTestOut, ControlTestUpdate
from app.services.control_test_service import ControlTestService

router = APIRouter()


@router.get("/get-test", response_model=ControlTestOut)
async def get_control_test(
    test_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ControlTestOut:
    service = ControlTestService(db)
    return await service.get_test(test_id)


@router.get("/list-tests", response_model=list[ControlTestOut])
async def list_control_tests(
    config_control_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ControlTestOut]:
    service = ControlTestService(db)
    return await service.list_tests(config_control_id)


@router.put("/update-test", response_model=ControlTestOut)
async def update_control_test(
    test_id: int = Query(...),
    data: ControlTestUpdate = Body(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ControlTestOut:
    service = ControlTestService(db)
    return await service.update_test(test_id, data)

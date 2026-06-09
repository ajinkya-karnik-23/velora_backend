"""Test log endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.test_log import TestLogCreate, TestLogOut
from app.services.test_log_service import TestLogService

router = APIRouter()


@router.get("/list", response_model=list[TestLogOut])
async def list_test_logs(
    current_user: dict = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> list[TestLogOut]:
    """Return the 200 most recent test log entries across all cycles."""
    service = TestLogService(db)
    return await service.list_all()


@router.post("/create-test-log", response_model=TestLogOut, status_code=201)
async def create_test_log(
    data: TestLogCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TestLogOut:
    service = TestLogService(db)
    return await service.create_log(data, current_user)

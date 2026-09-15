"""Manual test step endpoints — auditor-defined procedures on a control's testing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_permission
from app.schemas.manual_test_step import (
    CycleManualStepOut,
    ManualTestStepCreate,
    ManualTestStepOut,
    ManualTestStepUpdate,
    RecordResultRequest,
    StepResultOut,
)
from app.services.manual_test_step_service import ManualTestStepService

router = APIRouter()


@router.get("/list-for-cycle", response_model=list[CycleManualStepOut])
async def list_for_cycle(
    cycle_id: int = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CycleManualStepOut]:
    """Steps applying to every control attached to a cycle, with current results."""
    return await ManualTestStepService(db).list_for_cycle(cycle_id, current_user)


@router.get("/list-for-control", response_model=list[ManualTestStepOut])
async def list_for_control(
    control_id: int = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> list[ManualTestStepOut]:
    """Every step defined for a control across cycles — the repository view."""
    return await ManualTestStepService(db).list_for_control(control_id)


@router.post("/create-step", response_model=ManualTestStepOut, status_code=201)
async def create_step(
    data: ManualTestStepCreate = Body(...),
    current_user: dict[str, Any] = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ManualTestStepOut:
    return await ManualTestStepService(db).create(data, current_user)


@router.put("/update-step", response_model=ManualTestStepOut)
async def update_step(
    step_id: int = Query(...),
    data: ManualTestStepUpdate = Body(...),
    current_user: dict[str, Any] = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ManualTestStepOut:
    return await ManualTestStepService(db).update(step_id, data, current_user)


@router.delete("/delete-step", status_code=204, response_model=None)
async def delete_step(
    step_id: int = Query(...),
    current_user: dict[str, Any] = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> None:
    await ManualTestStepService(db).delete(step_id, current_user)


@router.put("/record-result", response_model=StepResultOut)
async def record_result(
    step_id: int = Query(...),
    data: RecordResultRequest = Body(...),
    current_user: dict[str, Any] = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> StepResultOut:
    """Record the auditor's verdict for a step under one attached control."""
    return await ManualTestStepService(db).record_result(step_id, data, current_user)

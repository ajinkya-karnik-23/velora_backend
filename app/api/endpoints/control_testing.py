from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.schemas.control_test import ClearRunDataResponse, TestRunHistoryOut
from app.schemas.test_log import TestLogCreate, TestLogOut
from app.services.control_test_service import ControlTestService
from app.services.control_testing_module.run_module import (
    execute_module_pipeline
)
from app.services.control_testing_module.sse_pipeline import stream_full_pipeline, stream_g01_pipeline
from app.services.test_log_service import TestLogService

router = APIRouter()


@router.post("/execute")
async def execute_control_testing(
    payload: dict
):

    result = await execute_module_pipeline(
        incoming_trigger=payload,
        task_id=str(uuid.uuid4())
    )

    return result


@router.post("/stream")
async def stream_control_testing(
    payload: dict
):
    task_id = str(uuid.uuid4())
    return StreamingResponse(
        stream_full_pipeline(payload, task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class SaveResultRequest(BaseModel):
    test_id: int | None = None
    control_id: int | None = None
    cycle_id: int | None = None
    verdict: str
    remarks: str | None = None
    execution_time_ms: int | None = None


@router.get("/results", response_model=list[TestRunHistoryOut])
async def list_run_results(
    cycle_id: int = Query(...),
    control_id: str | None = Query(default=None),
    test_id: int | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TestRunHistoryOut]:
    """Return persisted AI run results (newest first) for a cycle.

    Optionally narrow by control_id and/or test_id. The first item is the latest
    run; the remainder are past runs.
    """
    service = ControlTestService(db)
    return await service.get_run_history(cycle_id, control_id, test_id)


@router.delete("/cycle/{cycle_id}/run-data", response_model=ClearRunDataResponse)
async def clear_cycle_run_data(
    cycle_id: int,
    current_user: dict = Depends(require_role("Moderator")),
    db: AsyncSession = Depends(get_db),
) -> ClearRunDataResponse:
    """Delete all AI run results and test logs for a review cycle.

    Destructive and irreversible. Uploaded evidence files are not affected.
    Requires Moderator or higher.
    """
    service = ControlTestService(db)
    return await service.clear_cycle_run_data(cycle_id)


@router.post("/save-result", response_model=TestLogOut, status_code=201)
async def save_test_result(
    data: SaveResultRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TestLogOut:
    """Persist the outcome of a completed SSE test run to test_logs."""
    service = TestLogService(db)
    return await service.create_log(
        TestLogCreate(
            test_id=data.test_id,
            control_id=data.control_id,
            cycle_id=data.cycle_id,
            status=data.verdict,
            notes=data.remarks,
            execution_time_seconds=(
                data.execution_time_ms // 1000 if data.execution_time_ms else None
            ),
        ),
        current_user,
    )
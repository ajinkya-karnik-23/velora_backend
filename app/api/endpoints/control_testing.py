from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.test_log import TestLogCreate, TestLogOut
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
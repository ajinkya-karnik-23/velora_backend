from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import uuid

from app.services.control_testing_module.run_module import (
    execute_module_pipeline
)
from app.services.control_testing_module.sse_pipeline import stream_full_pipeline, stream_g01_pipeline

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
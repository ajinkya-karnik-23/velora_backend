"""Report generation endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_current_user, get_db
from app.models.evidence_file import EvidenceFile
from app.models.user import User
from app.services.report_generation_module.generate_report import generate_test_report

router = APIRouter()


def _fmt_size(b: int | None) -> str:
    if b is None:
        return "—"
    if b < 1_024:
        return f"{b} B"
    if b < 1_024 ** 2:
        return f"{b / 1_024:.1f} KB"
    return f"{b / 1_024 ** 2:.1f} MB"


@router.get("/test-report")
async def download_test_report(
    test_id: int = Query(...),
    control_number: str = Query(...),
    test_description: str = Query(default=""),
    result_string: str = Query(default=""),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    # Resolve the name of the user who ran the test (current user)
    user_row = (
        await db.execute(select(User).where(User.user_id == int(_current_user["sub"])))
    ).scalar_one_or_none()
    tested_by = user_row.user_name if user_row else "—"

    stmt = (
        select(EvidenceFile)
        .where(EvidenceFile.test_id == test_id)
        .options(joinedload(EvidenceFile.uploader))
        .order_by(EvidenceFile.upload_date)
    )
    rows = (await db.execute(stmt)).scalars().all()

    if rows:
        evidence_list = [
            {
                "idx": i + 1,
                "file_name": ev.file_name,
                "file_type": ev.file_type or "—",
                "file_size": _fmt_size(ev.file_size),
                "status": ev.status,
                "uploader": ev.uploader.user_name if ev.uploader else "—",
                "upload_date": datetime.fromtimestamp(
                    ev.upload_date, tz=timezone.utc
                ).strftime("%d %b %Y"),
            }
            for i, ev in enumerate(rows)
        ]
    else:
        evidence_list = [
            {
                "idx": "—",
                "file_name": "No evidence attached to this test.",
                "file_type": "—",
                "file_size": "—",
                "status": "—",
                "uploader": "—",
                "upload_date": "—",
            }
        ]

    docx_bytes = generate_test_report(
        control_number=control_number,
        test_id=test_id,
        test_description=test_description,
        result_string=result_string,
        evidence_list=evidence_list,
        tested_by=tested_by,
    )
    filename = f"test_report_{control_number}_{test_id}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

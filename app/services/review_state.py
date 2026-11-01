"""Whether a control is genuinely with the reviewer.

A hand-over only holds while the testing it handed over does. Once a sample
has run again after the submission, the stored "submitted" row describes
results that no longer exist: the tester is working on the control again and
must be able to change it and submit it afresh. The screens apply the same
rule (`isReviewStale` in the frontend's reviewStatus.ts), using the same run
log, so the server never refuses an action the tester was rightly offered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.control_review import SUBMITTED, ControlReviewStatus
from app.models.test_log import TestLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.config_control import ConfigControl


async def last_run_time(db: AsyncSession, cc: ConfigControl) -> int | None:
    """When any of the control's samples or steps last ran in this cycle."""
    return (
        await db.execute(
            select(func.max(TestLog.log_date)).where(
                TestLog.cycle_id == cc.cycle_id, TestLog.control_id == cc.control_id
            )
        )
    ).scalar_one_or_none()


def superseded(row: ControlReviewStatus, last_run: int | None) -> bool:
    """Testing has run since the row was recorded."""
    recorded = row.reviewed_time or row.submitted_time
    return last_run is not None and recorded is not None and last_run > recorded


async def with_reviewer(db: AsyncSession, cc: ConfigControl) -> bool:
    """The control is submitted and nothing has run since the hand-over."""
    row = (
        await db.execute(
            select(ControlReviewStatus).where(
                ControlReviewStatus.config_control_id == cc.config_control_id
            )
        )
    ).scalar_one_or_none()
    if row is None or row.status != SUBMITTED:
        return False
    return not superseded(row, await last_run_time(db, cc))

"""Review workflow: hand a control from tester to reviewer, and record verdicts.

Only the hand-over and the reviewer's decision are stored. Everything before
submission — pending, in progress, processed — is testing progress, which the
UI derives from the samples themselves rather than duplicating here.

Submitting is a tester action, verdicts are reviewer actions, and both append
to the event trail so a later verdict never erases how the control got there.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.config_control import ConfigControl
from app.models.control_review import (
    RETURNED,
    REVIEWER_VERDICTS,
    SUBMITTED,
    ControlReviewEvent,
    ControlReviewStatus,
)
from app.schemas.control_review import (
    ControlReviewEventOut,
    ControlReviewStatusOut,
    SubmitForReviewResult,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

TESTER = "tester"
REVIEWER = "reviewer"


def _to_out(row: ControlReviewStatus) -> ControlReviewStatusOut:
    return ControlReviewStatusOut(
        config_control_id=row.config_control_id,
        status=row.status,
        note=row.note,
        submitted_by_name=row.submitter.user_name if row.submitter else None,
        submitted_time=row.submitted_time,
        reviewed_by_name=row.reviewer.user_name if row.reviewer else None,
        reviewed_time=row.reviewed_time,
        updated_time=row.updated_time,
    )


class ControlReviewService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------ helpers

    async def _require_member(self, cycle_id: int, current_user: dict[str, Any]) -> None:
        roles = current_user.get("roles", [])
        if any(r in ("Admin", "Moderator") for r in roles):
            return
        from app.repositories.engagement_team_repo import EngagementTeamRepo

        if not await EngagementTeamRepo(self.db).is_member(cycle_id, int(current_user["sub"])):
            raise ForbiddenException("Not a member of this engagement.")

    async def _config_control(self, cycle_id: int, config_control_id: int) -> ConfigControl:
        cc = await self.db.get(ConfigControl, config_control_id)
        if cc is None or cc.cycle_id != cycle_id:
            raise NotFoundException("Attached control not found in this cycle.")
        return cc

    async def _row(self, config_control_id: int) -> ControlReviewStatus | None:
        return (
            await self.db.execute(
                select(ControlReviewStatus)
                .where(ControlReviewStatus.config_control_id == config_control_id)
                .options(
                    selectinload(ControlReviewStatus.submitter),
                    selectinload(ControlReviewStatus.reviewer),
                )
                # The row is usually already in the session from the write just
                # made; without this its names come back stale.
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    def _record_event(
        self,
        config_control_id: int,
        from_status: str | None,
        to_status: str,
        note: str | None,
        actor_id: int,
        persona: str,
        now: int,
    ) -> None:
        self.db.add(
            ControlReviewEvent(
                config_control_id=config_control_id,
                from_status=from_status,
                to_status=to_status,
                note=note,
                actor_id=actor_id,
                actor_persona=persona,
                event_time=now,
            )
        )

    # ------------------------------------------------------------ reads

    async def list_for_cycle(
        self, cycle_id: int, current_user: dict[str, Any]
    ) -> list[ControlReviewStatusOut]:
        """Stored review status for every attached control that has one."""
        await self._require_member(cycle_id, current_user)
        cc_ids = select(ConfigControl.config_control_id).where(ConfigControl.cycle_id == cycle_id)
        rows = (
            (
                await self.db.execute(
                    select(ControlReviewStatus)
                    .where(ControlReviewStatus.config_control_id.in_(cc_ids))
                    .options(
                        selectinload(ControlReviewStatus.submitter),
                        selectinload(ControlReviewStatus.reviewer),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_to_out(r) for r in rows]

    async def list_events(
        self, cycle_id: int, config_control_id: int, current_user: dict[str, Any]
    ) -> list[ControlReviewEventOut]:
        """The control's review trail, newest first."""
        await self._require_member(cycle_id, current_user)
        await self._config_control(cycle_id, config_control_id)
        rows = (
            (
                await self.db.execute(
                    select(ControlReviewEvent)
                    .where(ControlReviewEvent.config_control_id == config_control_id)
                    .options(selectinload(ControlReviewEvent.actor))
                    .order_by(
                        ControlReviewEvent.event_time.desc(), ControlReviewEvent.event_id.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            ControlReviewEventOut(
                config_control_id=e.config_control_id,
                from_status=e.from_status,
                to_status=e.to_status,
                note=e.note,
                actor_name=e.actor.user_name if e.actor else None,
                actor_persona=e.actor_persona,
                event_time=e.event_time,
            )
            for e in rows
        ]

    # ------------------------------------------------------------ writes

    async def submit(
        self,
        cycle_id: int,
        config_control_id: int,
        note: str | None,
        current_user: dict[str, Any],
    ) -> ControlReviewStatusOut:
        """Hand one control to the reviewer. Re-submitting a returned control is
        the normal way back, so only an in-flight review blocks it."""
        await self._require_member(cycle_id, current_user)
        await self._config_control(cycle_id, config_control_id)

        row = await self._row(config_control_id)
        if row is not None and row.status in (SUBMITTED,):
            raise AppException(
                code="ALREADY_SUBMITTED",
                message="This control is already with the reviewer.",
                status_code=409,
            )

        now = int(time.time())
        user_id = int(current_user["sub"])
        previous = row.status if row else None
        if row is None:
            row = ControlReviewStatus(config_control_id=config_control_id, status=SUBMITTED)
            self.db.add(row)
        row.status = SUBMITTED
        row.note = note
        row.submitted_by = user_id
        row.submitted_time = now
        # A fresh submission supersedes the previous verdict.
        row.reviewed_by = None
        row.reviewed_time = None
        self._record_event(config_control_id, previous, SUBMITTED, note, user_id, TESTER, now)

        await self.db.commit()
        return _to_out(await self._row(config_control_id))  # type: ignore[arg-type]

    async def submit_many(
        self,
        cycle_id: int,
        config_control_ids: list[int],
        current_user: dict[str, Any],
    ) -> SubmitForReviewResult:
        """Submit several controls in one go. Controls already with the reviewer
        are skipped rather than failing the batch."""
        await self._require_member(cycle_id, current_user)
        submitted: list[int] = []
        skipped: list[int] = []
        for cc_id in config_control_ids:
            try:
                await self.submit(cycle_id, cc_id, None, current_user)
                submitted.append(cc_id)
            except AppException:
                skipped.append(cc_id)
        return SubmitForReviewResult(submitted=submitted, skipped=skipped)

    async def record_verdict(
        self,
        cycle_id: int,
        config_control_id: int,
        verdict: str,
        note: str | None,
        current_user: dict[str, Any],
    ) -> ControlReviewStatusOut:
        """Record the reviewer's decision on a submitted control."""
        await self._require_member(cycle_id, current_user)
        await self._config_control(cycle_id, config_control_id)

        if verdict not in REVIEWER_VERDICTS:
            raise AppException(
                code="INVALID_VERDICT",
                message="That is not a reviewer verdict.",
                status_code=422,
            )

        row = await self._row(config_control_id)
        if row is None:
            raise AppException(
                code="NOT_SUBMITTED",
                message="This control has not been submitted for review yet.",
                status_code=409,
            )
        if verdict == RETURNED and not (note or "").strip():
            raise AppException(
                code="NOTE_REQUIRED",
                message="Say what the tester needs to do before returning the control.",
                status_code=422,
            )

        now = int(time.time())
        user_id = int(current_user["sub"])
        previous = row.status
        row.status = verdict
        row.note = (note or "").strip() or None
        row.reviewed_by = user_id
        row.reviewed_time = now
        self._record_event(config_control_id, previous, verdict, row.note, user_id, REVIEWER, now)

        await self.db.commit()
        return _to_out(await self._row(config_control_id))  # type: ignore[arg-type]

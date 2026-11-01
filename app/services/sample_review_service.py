"""The reviewer's word on tested samples, and what the tester is told of it.

A save may carry an edit (outcome, conclusion), a comment, people involved
and a verdict; each part that changes is recorded as its own event. Those
events, with the reviewer's control-level verdicts, are the tester's
notifications.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.config_control import ConfigControl
from app.models.control_review import ControlReviewEvent
from app.models.review_cycle import ReviewCycle
from app.models.sample_review import SampleReview, SampleReviewEvent
from app.schemas.sample_review import (
    Involved,
    NotificationOut,
    SampleReviewEventOut,
    SampleReviewIn,
    SampleReviewOut,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_out(row: SampleReview) -> SampleReviewOut:
    return SampleReviewOut(
        config_control_id=row.config_control_id,
        sample_no=row.sample_no,
        result=row.result,
        conclusion=row.conclusion,
        comment=row.comment,
        involved=[Involved(**p) for p in (row.involved or [])],
        verdict=row.verdict,
        verdict_time=row.verdict_time,
        reviewed_by_name=row.reviewer.user_name if row.reviewer else None,
        updated_time=row.updated_time,
    )


class SampleReviewService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _require_member(self, cycle_id: int, current_user: dict[str, Any]) -> None:
        if any(r in ("Admin", "Moderator") for r in current_user.get("roles", [])):
            return
        from app.repositories.engagement_team_repo import EngagementTeamRepo

        if not await EngagementTeamRepo(self.db).is_member(cycle_id, int(current_user["sub"])):
            raise ForbiddenException("Not a member of this engagement.")

    async def _row(self, config_control_id: int, sample_no: int) -> SampleReview | None:
        return (
            await self.db.execute(
                select(SampleReview)
                .where(
                    SampleReview.config_control_id == config_control_id,
                    SampleReview.sample_no == sample_no,
                )
                .options(selectinload(SampleReview.reviewer))
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    # ------------------------------------------------------------ reads

    async def for_control(self, config_control_id: int) -> dict[int, dict[str, Any]]:
        """Sample number → the reviewer's word, ready to ride on a testing output."""
        rows = (
            (
                await self.db.execute(
                    select(SampleReview)
                    .where(SampleReview.config_control_id == config_control_id)
                    .options(selectinload(SampleReview.reviewer))
                )
            )
            .scalars()
            .all()
        )
        return {r.sample_no: _to_out(r).model_dump() for r in rows}

    async def results_for(self, config_control_id: int) -> dict[int, str]:
        """Sample number → the reviewer's outcome, where they changed it."""
        rows = (
            await self.db.execute(
                select(SampleReview.sample_no, SampleReview.result).where(
                    SampleReview.config_control_id == config_control_id,
                    SampleReview.result.is_not(None),
                )
            )
        ).all()
        return {int(no): str(result) for no, result in rows if result}

    async def list_for_cycle(self, cycle_id: int) -> list[SampleReviewOut]:
        rows = (
            (
                await self.db.execute(
                    select(SampleReview)
                    .join(
                        ConfigControl,
                        ConfigControl.config_control_id == SampleReview.config_control_id,
                    )
                    .where(ConfigControl.cycle_id == cycle_id)
                    .options(selectinload(SampleReview.reviewer))
                )
            )
            .scalars()
            .all()
        )
        return [_to_out(r) for r in rows]

    async def events_for_cycle(self, cycle_id: int) -> list[SampleReviewEventOut]:
        rows = (
            (
                await self.db.execute(
                    select(SampleReviewEvent)
                    .join(
                        ConfigControl,
                        ConfigControl.config_control_id == SampleReviewEvent.config_control_id,
                    )
                    .where(ConfigControl.cycle_id == cycle_id)
                    .options(selectinload(SampleReviewEvent.actor))
                    .order_by(
                        SampleReviewEvent.event_time.desc(), SampleReviewEvent.event_id.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            SampleReviewEventOut(
                config_control_id=e.config_control_id,
                sample_no=e.sample_no,
                kind=e.kind,
                detail=e.detail,
                note=e.note,
                actor_name=e.actor.user_name if e.actor else None,
                event_time=e.event_time,
            )
            for e in rows
        ]

    # ------------------------------------------------------------ writes

    async def save(
        self,
        cycle_id: int,
        config_control_id: int,
        sample_no: int,
        data: SampleReviewIn,
        current_user: dict[str, Any],
    ) -> SampleReviewOut:
        await self._require_member(cycle_id, current_user)
        cc = await self.db.get(ConfigControl, config_control_id)
        if cc is None or cc.cycle_id != cycle_id:
            raise NotFoundException("Attached control not found in this cycle.")
        fields = data.model_fields_set
        if not fields:
            raise AppException(code="NOTHING_TO_SAVE", message="Nothing to save.", status_code=422)

        now = int(time.time())
        user_id = int(current_user["sub"])
        row = await self._row(config_control_id, sample_no)
        if row is None:
            row = SampleReview(config_control_id=config_control_id, sample_no=sample_no)
            self.db.add(row)

        def event(kind: str, note: str | None = None, detail: dict | None = None) -> None:
            self.db.add(
                SampleReviewEvent(
                    config_control_id=config_control_id,
                    sample_no=sample_no,
                    kind=kind,
                    note=note,
                    detail=detail,
                    actor_id=user_id,
                    event_time=now,
                )
            )

        edited: dict[str, Any] = {}
        if "result" in fields and data.result != row.result:
            edited["result"] = {"from": row.result, "to": data.result}
            row.result = data.result
        if "conclusion" in fields and (data.conclusion or None) != row.conclusion:
            edited["conclusion"] = True
            row.conclusion = (data.conclusion or "").strip() or None
        if edited:
            event("edited", row.conclusion, edited)
        if "comment" in fields and (data.comment or "").strip():
            row.comment = data.comment.strip()  # type: ignore[union-attr]
            event("commented", row.comment)
        if "involved" in fields and data.involved is not None:
            before = {p.get("email") or p.get("name") for p in (row.involved or [])}
            people = [p.model_dump() for p in data.involved]
            added = [p for p in people if (p.get("email") or p.get("name")) not in before]
            row.involved = people
            if added:
                event("involved", None, {"people": added})
        if "verdict" in fields and data.verdict:
            row.verdict = data.verdict
            row.verdict_time = now
            event("verdict", None, {"verdict": data.verdict})
        row.reviewed_by = user_id
        row.updated_time = now
        await self.db.commit()
        return _to_out(await self._row(config_control_id, sample_no))  # type: ignore[arg-type]

    async def clear_for_cycle(self, cycle_id: int) -> None:
        """Drop the cycle's sample reviews and their trail. Caller commits."""
        cc_ids = select(ConfigControl.config_control_id).where(ConfigControl.cycle_id == cycle_id)
        await self.db.execute(
            delete(SampleReview).where(SampleReview.config_control_id.in_(cc_ids))
        )
        await self.db.execute(
            delete(SampleReviewEvent).where(SampleReviewEvent.config_control_id.in_(cc_ids))
        )

    # ------------------------------------------------------------ notifications

    async def notifications(self, client_id: int) -> list[NotificationOut]:
        """Review activity across the client's cycles, newest first: the
        reviewer's control verdicts and every action on a sample (the
        tester's notifications), and the tester's hand-overs (the reviewer's)."""
        ccs = (
            await self.db.execute(
                select(ConfigControl, ReviewCycle)
                .join(ReviewCycle, ReviewCycle.cycle_id == ConfigControl.cycle_id)
                .where(ReviewCycle.client_id == client_id)
                .options(selectinload(ConfigControl.control))
            )
        ).all()
        by_cc = {cc.config_control_id: (cc, cycle) for cc, cycle in ccs}
        if not by_cc:
            return []
        out: list[NotificationOut] = []

        def base(cc_id: int) -> dict[str, Any]:
            cc, cycle = by_cc[cc_id]
            return {
                "cycle_id": cycle.cycle_id,
                "cycle_name": cycle.name,
                "config_control_id": cc_id,
                "control_number": cc.control.control_number if cc.control else None,
                "control_name": cc.control.control_name if cc.control else None,
            }

        control_events = (
            (
                await self.db.execute(
                    select(ControlReviewEvent)
                    .where(ControlReviewEvent.config_control_id.in_(by_cc.keys()))
                    .options(selectinload(ControlReviewEvent.actor))
                )
            )
            .scalars()
            .all()
        )
        for e in control_events:
            out.append(
                NotificationOut(
                    key=f"c{e.event_id}",
                    # A tester's hand-over is the reviewer's notification;
                    # a reviewer's verdict is the tester's.
                    kind="control_verdict" if e.actor_persona == "reviewer" else "submitted",
                    status=e.to_status,
                    note=e.note,
                    actor_name=e.actor.user_name if e.actor else None,
                    event_time=e.event_time,
                    **base(e.config_control_id),
                )
            )
        sample_events = (
            (
                await self.db.execute(
                    select(SampleReviewEvent)
                    .where(SampleReviewEvent.config_control_id.in_(by_cc.keys()))
                    .options(selectinload(SampleReviewEvent.actor))
                )
            )
            .scalars()
            .all()
        )
        for e in sample_events:
            out.append(
                NotificationOut(
                    key=f"s{e.event_id}",
                    kind="sample_verdict" if e.kind == "verdict" else e.kind,
                    sample_no=e.sample_no,
                    status=(e.detail or {}).get("verdict") if e.kind == "verdict" else None,
                    note=e.note,
                    actor_name=e.actor.user_name if e.actor else None,
                    event_time=e.event_time,
                    **base(e.config_control_id),
                )
            )
        out.sort(key=lambda n: n.event_time, reverse=True)
        return out

"""Manual test steps: define, list, edit, delete, and record results.

Scope rules
-----------
A step is either a *cycle step* (``config_control_id`` set — a customisation
of one cycle's testing) or a *control step* (``config_control_id`` null — kept
on the control, so every cycle that attaches the control picks it up).

Results
-------
Verdicts are recorded by the auditor, one per step per attached control. Each
result is pinned to the evidence present when it was recorded; once that
evidence changes the result no longer describes what is attached and is
reported as absent, exactly as a sample's run is voided by a re-upload.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.config_control import ConfigControl
from app.models.evidence_file import EvidenceFile
from app.models.manual_test_step import ManualTestStep, ManualTestStepResult
from app.schemas.manual_test_step import (
    CycleManualStepOut,
    ManualTestStepOut,
    StepParameter,
    StepResultOut,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.manual_test_step import (
        ManualTestStepCreate,
        ManualTestStepUpdate,
        RecordResultRequest,
    )


def _step_out(step: ManualTestStep) -> dict[str, Any]:
    cc = step.config_control
    return {
        "step_id": step.step_id,
        "control_id": step.control_id,
        "control_number": step.control.control_number if step.control else None,
        "config_control_id": step.config_control_id,
        "scope": "cycle" if step.config_control_id is not None else "control",
        "cycle_id": cc.cycle_id if cc else None,
        "cycle_name": cc.review_cycle.name if cc and cc.review_cycle else None,
        "serial": step.serial,
        "title": step.title,
        "summary": step.summary,
        "test_type": step.test_type,
        "evidence_name": step.evidence_name,
        "evidence_description": step.evidence_description,
        "parameters": [StepParameter.model_validate(p) for p in step.parameters or []],
        "created_by_name": step.creator.user_name if step.creator else None,
        "created_time": step.created_time,
        "updated_time": step.updated_time,
    }


def evidence_token(evidence_ids: list[int]) -> str:
    """The fingerprint a result is pinned to — matches the UI's sample token."""
    return ",".join(str(i) for i in sorted(evidence_ids))


class ManualTestStepService:
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

    async def _config_control(self, config_control_id: int) -> ConfigControl:
        cc = await self.db.get(ConfigControl, config_control_id)
        if cc is None:
            raise NotFoundException("Attached control not found.")
        return cc

    async def _step(self, step_id: int) -> ManualTestStep:
        stmt = (
            select(ManualTestStep)
            .where(ManualTestStep.step_id == step_id)
            .options(
                selectinload(ManualTestStep.control),
                selectinload(ManualTestStep.creator),
                selectinload(ManualTestStep.config_control).selectinload(
                    ConfigControl.review_cycle
                ),
            )
        )
        step = (await self.db.execute(stmt)).scalar_one_or_none()
        if step is None:
            raise NotFoundException("Test step not found.")
        return step

    async def _step_evidence_token(self, step_id: int, cycle_id: int) -> str:
        ids = (
            (
                await self.db.execute(
                    select(EvidenceFile.evidence_id).where(
                        EvidenceFile.manual_step_id == step_id,
                        EvidenceFile.cycle_id == cycle_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return evidence_token(list(ids))

    # ------------------------------------------------------------ reads

    async def list_for_cycle(
        self, cycle_id: int, current_user: dict[str, Any]
    ) -> list[CycleManualStepOut]:
        """Every step that applies to the cycle's attached controls, with results."""
        await self._require_member(cycle_id, current_user)

        ccs = (
            (await self.db.execute(select(ConfigControl).where(ConfigControl.cycle_id == cycle_id)))
            .scalars()
            .all()
        )
        if not ccs:
            return []
        cc_by_id = {cc.config_control_id: cc for cc in ccs}
        cc_by_control = {cc.control_id: cc for cc in ccs}

        steps = (
            (
                await self.db.execute(
                    select(ManualTestStep)
                    .where(
                        or_(
                            ManualTestStep.config_control_id.in_(cc_by_id),
                            ManualTestStep.config_control_id.is_(None)
                            & ManualTestStep.control_id.in_(cc_by_control),
                        )
                    )
                    .options(
                        selectinload(ManualTestStep.control),
                        selectinload(ManualTestStep.creator),
                        selectinload(ManualTestStep.config_control).selectinload(
                            ConfigControl.review_cycle
                        ),
                    )
                    .order_by(ManualTestStep.created_time, ManualTestStep.step_id)
                )
            )
            .scalars()
            .all()
        )

        results = (
            (
                await self.db.execute(
                    select(ManualTestStepResult)
                    .where(ManualTestStepResult.config_control_id.in_(cc_by_id))
                    .options(selectinload(ManualTestStepResult.recorder))
                )
            )
            .scalars()
            .all()
        )
        result_by_key = {(r.step_id, r.config_control_id): r for r in results}

        evidence_rows = (
            await self.db.execute(
                select(EvidenceFile.manual_step_id, EvidenceFile.evidence_id).where(
                    EvidenceFile.cycle_id == cycle_id,
                    EvidenceFile.manual_step_id.is_not(None),
                )
            )
        ).all()
        ids_by_step: dict[int, list[int]] = {}
        for step_id, evidence_id in evidence_rows:
            ids_by_step.setdefault(step_id, []).append(evidence_id)

        out: list[CycleManualStepOut] = []
        for step in steps:
            cc = (
                cc_by_id.get(step.config_control_id)
                if step.config_control_id is not None
                else cc_by_control.get(step.control_id)
            )
            if cc is None:
                continue
            result = result_by_key.get((step.step_id, cc.config_control_id))
            token = evidence_token(ids_by_step.get(step.step_id, []))
            # A result recorded against different evidence is void.
            current = result if result and result.evidence_token == token else None
            out.append(
                CycleManualStepOut(
                    **_step_out(step),
                    applies_to_config_control_id=cc.config_control_id,
                    result=(
                        StepResultOut(
                            verdict=current.verdict,  # type: ignore[arg-type]
                            remark=current.remark,
                            evidence_token=current.evidence_token,
                            recorded_by_name=(
                                current.recorder.user_name if current.recorder else None
                            ),
                            recorded_time=current.updated_time,
                        )
                        if current
                        else None
                    ),
                )
            )
        return out

    async def list_for_control(self, control_id: int) -> list[ManualTestStepOut]:
        """Every step defined for a control, across cycles — the repository view."""
        steps = (
            (
                await self.db.execute(
                    select(ManualTestStep)
                    .where(ManualTestStep.control_id == control_id)
                    .options(
                        selectinload(ManualTestStep.control),
                        selectinload(ManualTestStep.creator),
                        selectinload(ManualTestStep.config_control).selectinload(
                            ConfigControl.review_cycle
                        ),
                    )
                    .order_by(ManualTestStep.created_time, ManualTestStep.step_id)
                )
            )
            .scalars()
            .all()
        )
        return [ManualTestStepOut(**_step_out(s)) for s in steps]

    # ------------------------------------------------------------ writes

    async def create(
        self, data: ManualTestStepCreate, current_user: dict[str, Any]
    ) -> ManualTestStepOut:
        cc = await self._config_control(data.config_control_id)
        await self._require_member(cc.cycle_id, current_user)

        step = ManualTestStep(
            control_id=cc.control_id,
            config_control_id=None if data.keep_for_future_cycles else cc.config_control_id,
            serial=data.serial,
            title=data.title,
            summary=data.summary,
            test_type=data.test_type,
            evidence_name=data.evidence_name,
            evidence_description=(data.evidence_description or "").strip() or None,
            parameters=[p.model_dump() for p in data.parameters],
            created_by=int(current_user["sub"]),
        )
        self.db.add(step)
        await self.db.commit()
        return ManualTestStepOut(**_step_out(await self._step(step.step_id)))

    async def update(
        self, step_id: int, data: ManualTestStepUpdate, current_user: dict[str, Any]
    ) -> ManualTestStepOut:
        step = await self._step(step_id)
        if step.config_control is not None:
            await self._require_member(step.config_control.cycle_id, current_user)

        step.serial = data.serial
        step.title = data.title
        step.summary = data.summary
        step.test_type = data.test_type
        step.evidence_name = data.evidence_name
        step.evidence_description = (data.evidence_description or "").strip() or None
        step.parameters = [p.model_dump() for p in data.parameters]

        if data.keep_for_future_cycles is True:
            step.config_control_id = None
        elif data.keep_for_future_cycles is False and step.config_control_id is None:
            # Narrowing a control step back to one cycle needs that cycle's
            # attachment of the same control.
            if data.config_control_id is None:
                raise AppException(
                    code="SCOPE_REQUIRED",
                    message="Choose the review cycle this step should be limited to.",
                    status_code=422,
                )
            cc = await self._config_control(data.config_control_id)
            if cc.control_id != step.control_id:
                raise AppException(
                    code="SCOPE_MISMATCH",
                    message="That review cycle does not test this control.",
                    status_code=422,
                )
            await self._require_member(cc.cycle_id, current_user)
            step.config_control_id = cc.config_control_id

        await self.db.commit()
        self.db.expire_all()
        return ManualTestStepOut(**_step_out(await self._step(step_id)))

    async def delete(self, step_id: int, current_user: dict[str, Any]) -> None:
        step = await self._step(step_id)
        if step.config_control is not None:
            await self._require_member(step.config_control.cycle_id, current_user)
        # Evidence uploaded for the step stays in the vault, unlinked; results
        # go with the step.
        await self.db.execute(
            EvidenceFile.__table__.update()
            .where(EvidenceFile.manual_step_id == step_id)
            .values(manual_step_id=None)
        )
        await self.db.delete(step)
        await self.db.commit()

    async def record_result(
        self, step_id: int, data: RecordResultRequest, current_user: dict[str, Any]
    ) -> StepResultOut:
        step = await self._step(step_id)
        cc = await self._config_control(data.config_control_id)
        applies = (
            step.config_control_id == cc.config_control_id
            if step.config_control_id is not None
            else step.control_id == cc.control_id
        )
        if not applies:
            raise AppException(
                code="STEP_NOT_IN_CONTROL",
                message="This test step does not belong to that control.",
                status_code=422,
            )
        await self._require_member(cc.cycle_id, current_user)

        token = await self._step_evidence_token(step_id, cc.cycle_id)
        if not token:
            raise AppException(
                code="EVIDENCE_REQUIRED",
                message="Upload evidence for this test step before recording a result.",
                status_code=422,
            )
        if data.verdict != "PASS" and not data.remark:
            raise AppException(
                code="REMARK_REQUIRED",
                message="Add a remark explaining why the step did not pass.",
                status_code=422,
            )

        result = (
            await self.db.execute(
                select(ManualTestStepResult).where(
                    ManualTestStepResult.step_id == step_id,
                    ManualTestStepResult.config_control_id == cc.config_control_id,
                )
            )
        ).scalar_one_or_none()
        if result is None:
            result = ManualTestStepResult(step_id=step_id, config_control_id=cc.config_control_id)
            self.db.add(result)
        result.verdict = data.verdict
        result.remark = data.remark
        result.evidence_token = token
        result.recorded_by = int(current_user["sub"])

        # Every recorded result is also an audit-log entry, so the trail keeps
        # each re-run even though the step holds only its latest result.
        import time

        from app.models.test_log import TestLog

        self.db.add(
            TestLog(
                control_id=cc.control_id,
                cycle_id=cc.cycle_id,
                log_date=int(time.time()),
                changed_by=int(current_user["sub"]),
                status=data.verdict,
                notes=data.remark,
                source="manual_step",
                manual_step_id=step_id,
            )
        )
        await self.db.commit()

        fresh = (
            await self.db.execute(
                select(ManualTestStepResult)
                .where(ManualTestStepResult.result_id == result.result_id)
                .options(selectinload(ManualTestStepResult.recorder))
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        return StepResultOut(
            verdict=fresh.verdict,  # type: ignore[arg-type]
            remark=fresh.remark,
            evidence_token=fresh.evidence_token,
            recorded_by_name=fresh.recorder.user_name if fresh.recorder else None,
            recorded_time=fresh.updated_time,
        )

    async def clear_results_for_cycle(self, cycle_id: int) -> int:
        """Drop every recorded step result in a cycle. Caller commits."""
        cc_ids = select(ConfigControl.config_control_id).where(ConfigControl.cycle_id == cycle_id)
        res = await self.db.execute(
            delete(ManualTestStepResult).where(ManualTestStepResult.config_control_id.in_(cc_ids))
        )
        return res.rowcount or 0  # type: ignore[attr-defined]

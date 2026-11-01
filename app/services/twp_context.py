"""What a review cycle contributes to a control's TWP work paper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.control_review import ControlReviewStatus
from app.models.evidence_file import EvidenceFile
from app.models.review_cycle import ReviewCycle
from app.services.config_control_service import ConfigControlService
from app.services.twp_builder import TwpContext

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.config_control import ConfigControl

REVIEW_LABELS = {
    "submitted_for_review": "Submitted to reviewer",
    "under_review": "Under review",
    "reviewed": "Reviewed",
    "approved": "Approved",
    "returned_to_tester": "Returned to tester",
}


def apply_judgement(sample: dict) -> dict:
    """The work paper reports the tester's result where one was recorded.

    The tool's own result is kept beside it (`tool_result`) so the paper can
    show what the tool concluded and that the tester changed it.
    """
    judgement = sample.get("judgement")
    sample["tool_result"] = sample.get("result")
    if judgement:
        sample["result"] = judgement["result"]
    # A reviewer's changed outcome overrides both.
    review = sample.get("review")
    if review and review.get("result"):
        sample["result"] = review["result"]
    return sample


async def twp_context(
    db: AsyncSession, cc: ConfigControl, phase_run_id: int | None = None
) -> TwpContext:
    """The cycle's tested samples, their documents, gaps and sign-off.

    On a phased cycle the paper covers one phase run — the current one, or the
    run asked for — with that run's samples and its own sign-off.
    """
    output = await ConfigControlService(db).get_test_output(cc.config_control_id, phase_run_id)
    samples = [apply_judgement(s.model_dump()) for s in output.samples]

    documents: dict[int, list[tuple[str, str]]] = {}
    if output.test_id is not None:
        rows = (
            await db.execute(
                select(EvidenceFile)
                .where(EvidenceFile.test_id == output.test_id)
                .order_by(EvidenceFile.evidence_id)
            )
        ).scalars()
        for ev in rows:
            if ev.sample_no is None:
                continue
            documents.setdefault(ev.sample_no, []).append(
                (ev.doc_ref or f"#{ev.evidence_id}", ev.file_name)
            )

    review = (
        await db.execute(
            select(ControlReviewStatus)
            .where(ControlReviewStatus.config_control_id == cc.config_control_id)
            .options(
                selectinload(ControlReviewStatus.submitter),
                selectinload(ControlReviewStatus.reviewer),
            )
        )
    ).scalar_one_or_none()
    cycle = await db.get(ReviewCycle, cc.cycle_id)

    phase = output.phase
    signoff: dict = {}
    if phase is not None and phase.status == "active":
        # The testing output holds every sample's verdict up front; a round
        # still in progress shows only what has been run, the rest pending.
        from app.services.phase_service import PhaseService

        service = PhaseService(db)
        ran = (await service.results(cc, await service.runs(cc.config_control_id))).get(
            phase.phase_run_id, {}
        )
        for sample in samples:
            if sample.get("sample_no") not in ran:
                sample.update(
                    result="PENDING", tool_result=None, validation=None, judgement=None, review=None
                )
    if phase is not None:
        signoff = await _phase_signoff(db, cc, phase.phase_run_id)
        # The review row only ever describes the current run; a concluded run
        # signs off from its own trail.
        if phase.status != "active":
            review = None

    context = TwpContext(
        samples=samples,
        population_count=output.population_count,
        documents=documents,
        not_tested_reason=output.not_tested_reason,
        untested_types=[t.model_dump() for t in output.untested_types],
        cycle_name=cycle.name if cycle else None,
        review_status=(
            "Not tested"
            if output.not_tested_reason
            else REVIEW_LABELS.get(review.status, review.status) if review else "Not submitted"
        ),
        tester=review.submitter.user_name if review and review.submitter else None,
        submitted_time=review.submitted_time if review else None,
        reviewer=review.reviewer.user_name if review and review.reviewer else None,
        reviewed_time=review.reviewed_time if review else None,
        review_note=review.note if review else None,
    )
    if phase is not None:
        context.phase_label = phase.label
        context.phase_name = phase.name
        context.evidence_window = f"{_day(phase.window_start)} to {_day(phase.window_end)}"
        context.size_basis = _size_basis(phase)
        context.phase_outcome = PHASE_OUTCOMES.get(phase.status, phase.status)
        context.failure_reason = phase.failure_reason
        context.phase_concluded_time = signoff.get("concluded_time")
        if not review:
            context.review_status = PHASE_OUTCOMES.get(phase.status, phase.status)
            context.tester = signoff.get("tester")
            context.submitted_time = signoff.get("submitted_time")
            context.reviewer = signoff.get("reviewer")
            context.reviewed_time = signoff.get("reviewed_time")
            context.review_note = signoff.get("note")
    return context


PHASE_OUTCOMES = {
    "active": "In progress",
    "approved": "Passed — approved by reviewer",
    "failed": "Failed — remediation raised",
}


def _day(iso: str | None) -> str:
    if not iso:
        return "—"
    from datetime import date

    return date.fromisoformat(iso).strftime("%d %b %Y")


def _size_basis(phase) -> str:  # noqa: ANN001 — PhaseInfo
    if phase.phase == "DE":
        return "Design effectiveness always tests one sample."
    if phase.override_size:
        return (
            f"Sample count set to {phase.override_size} by the tester "
            f"(matrix: {phase.matrix_value or 'no value'}). Reason: {phase.override_reason}"
        )
    if phase.phase == "OE":
        return f"Sampling matrix, frequency x risk: {phase.matrix_value}."
    return f"Sampling matrix, {phase.phase} column by frequency: {phase.matrix_value}."


async def _phase_signoff(db: AsyncSession, cc: ConfigControl, phase_run_id: int) -> dict:
    """Who submitted and who concluded one phase run, from its trail."""
    from app.models.control_phase import ControlPhaseEvent

    events = (
        (
            await db.execute(
                select(ControlPhaseEvent)
                .where(ControlPhaseEvent.phase_run_id == phase_run_id)
                .options(selectinload(ControlPhaseEvent.actor))
                .order_by(ControlPhaseEvent.event_time, ControlPhaseEvent.event_id)
            )
        )
        .scalars()
        .all()
    )
    out: dict = {}
    for e in events:
        name = e.actor.user_name if e.actor else None
        if e.kind in ("submitted", "failed"):
            out["tester"], out["submitted_time"] = name, e.event_time
        if e.kind in ("approved", "returned_to_tester", "reviewed", "under_review"):
            out["reviewer"], out["reviewed_time"], out["note"] = name, e.event_time, e.note
        if e.kind in ("approved", "failed"):
            out["concluded_time"] = e.event_time
    return out

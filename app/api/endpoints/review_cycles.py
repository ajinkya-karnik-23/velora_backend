"""Review cycle endpoints — CRUD, stats, team management."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_engagement_member, require_permission
from app.schemas.common import PaginatedResponse
from app.schemas.config_control import (
    DefaultEvidenceAttachOut,
    DefaultEvidenceFileOut,
    DefaultEvidenceStatusOut,
    ConfigControlBulkCreate,
    ConfigControlBulkRemove,
    ConfigControlCreate,
    ConfigControlOut,
    ControlTestOutputOut,
    EvidenceCheckOut,
    SampleSizeResultOut,
    SamplingCheckOut,
)
from app.schemas.control_review import (
    ControlReviewEventOut,
    ControlReviewStatusOut,
    ReviewVerdictRequest,
    SubmitForReviewRequest,
    SubmitForReviewResult,
    SubmitManyRequest,
)
from app.schemas.control_phase import (
    ControlPhasesOut,
    CyclePhasesOut,
    PhaseFailIn,
    PhaseSampleSizeIn,
    PhaseSampleSizeResetIn,
    PhaseSizeComputedIn,
)
from app.schemas.control_test import CycleTestObjectiveOut
from app.schemas.engagement_team import (
    TeamMemberAdd,
    TeamMemberBulkAdd,
    TeamMemberOut,
    TeamMemberUpdate,
)
from app.schemas.evidence import EvidenceOut
from app.schemas.review_cycle import (
    ReviewCycleCreate,
    ReviewCycleOut,
    ReviewCycleUpdate,
    SamplingModeUpdate,
)
from app.schemas.cycle_overview import CycleOverviewOut
from app.schemas.sample_review import (
    NotificationOut,
    SampleReviewEventOut,
    SampleReviewIn,
    SampleReviewOut,
)
from app.schemas.sample_judgement import SampleJudgementIn, SampleJudgementOut
from app.schemas.test_log import TestLogOut
from app.services.config_control_service import ConfigControlService
from app.services.control_review_service import ControlReviewService
from app.services.control_test_service import ControlTestService
from app.services.engagement_team_service import EngagementTeamService
from app.services.evidence_service import EvidenceService
from app.services.review_cycle_service import ReviewCycleService
from app.services.test_log_service import TestLogService

router = APIRouter()


# ---------------------------------------------------------------------------
# Review Cycle CRUD
# ---------------------------------------------------------------------------


@router.get("/list-cycles", response_model=PaginatedResponse[ReviewCycleOut])
async def list_review_cycles(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    client_id: int | None = None,
    status: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ReviewCycleService(db)
    filters = {}
    if client_id:
        filters["client_id"] = client_id
    if status:
        filters["status"] = status
    cycles, total = await service.list_cycles(
        filters, int(current_user["sub"]), current_user.get("roles", []), page, page_size
    )
    return {"data": cycles, "total": total, "page": page, "page_size": page_size}


@router.post("/create-cycle", response_model=ReviewCycleOut, status_code=201)
async def create_review_cycle(
    data: ReviewCycleCreate,
    current_user: dict = Depends(require_permission("can_manage_cycles")),
    db: AsyncSession = Depends(get_db),
) -> ReviewCycleOut:
    service = ReviewCycleService(db)
    return await service.create_cycle(data)


@router.get("/get-cycle", response_model=ReviewCycleOut)
async def get_review_cycle(
    cycle_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewCycleOut:
    service = ReviewCycleService(db)
    return await service.get_cycle(cycle_id)


@router.put("/update-cycle", response_model=ReviewCycleOut)
async def update_review_cycle(
    cycle_id: int = Query(...),
    data: ReviewCycleUpdate = Body(...),
    current_user: dict = Depends(require_permission("can_manage_cycles")),
    db: AsyncSession = Depends(get_db),
) -> ReviewCycleOut:
    service = ReviewCycleService(db)
    return await service.update_cycle(cycle_id, data)


@router.put("/{cycle_id}/sampling-mode", response_model=ReviewCycleOut)
async def set_sampling_mode(
    cycle_id: int,
    data: SamplingModeUpdate = Body(...),
    current_user: dict = Depends(require_permission("can_manage_cycles")),
    db: AsyncSession = Depends(get_db),
) -> ReviewCycleOut:
    """Switch the cycle between full-population and matrix sampling.

    Every attached control is re-sampled for the new mode. Refused for a
    locked cycle.
    """
    service = ReviewCycleService(db)
    return await service.set_sampling_mode(cycle_id, data.sampling_mode)


@router.get("/{cycle_id}/sample-judgements", response_model=list[SampleJudgementOut])
async def list_sample_judgements(
    cycle_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SampleJudgementOut]:
    """Every tester judgement recorded in the cycle (results, root causes)."""
    from app.services.sample_judgement_service import SampleJudgementService

    return await SampleJudgementService(db).list_for_cycle(cycle_id)


@router.put("/{cycle_id}/sample-judgement", response_model=SampleJudgementOut)
async def record_sample_judgement(
    cycle_id: int,
    data: SampleJudgementIn,
    config_control_id: int = Query(...),
    sample_no: int = Query(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> SampleJudgementOut:
    """Accept or change the tool's result for one sample.

    The tool's result is kept as it is; the judgement is stored beside it and
    logged to the audit trail. A failure needs a root-cause category, and a
    change needs a conclusion.
    """
    from app.services.sample_judgement_service import SampleJudgementService

    return await SampleJudgementService(db).record(
        cycle_id, config_control_id, sample_no, data, current_user
    )


@router.delete("/{cycle_id}/sample-judgement", status_code=204, response_model=None)
async def revert_sample_judgement(
    cycle_id: int,
    config_control_id: int = Query(...),
    sample_no: int = Query(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Withdraw the tester's judgement, so the tool's result stands again."""
    from app.services.sample_judgement_service import SampleJudgementService

    await SampleJudgementService(db).revert(cycle_id, config_control_id, sample_no, current_user)


@router.get("/{cycle_id}/evidence-map")
async def get_evidence_map(
    cycle_id: int,
    current_user: dict = Depends(require_engagement_member),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Every supporting document in the attached controls' populations, dated,
    with the phase window it falls in, the run that drew it and the files
    attached — read-only, for the Evidence tab."""
    from app.services.evidence_map_service import evidence_map

    return await evidence_map(db, cycle_id)


@router.get("/{cycle_id}/sample-reviews", response_model=list[SampleReviewOut])
async def list_sample_reviews(
    cycle_id: int,
    current_user: dict = Depends(require_engagement_member),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> list[SampleReviewOut]:
    """The reviewer's word on every reviewed sample in the cycle."""
    from app.services.sample_review_service import SampleReviewService

    return await SampleReviewService(db).list_for_cycle(cycle_id)


@router.get("/{cycle_id}/sample-review-events", response_model=list[SampleReviewEventOut])
async def list_sample_review_events(
    cycle_id: int,
    current_user: dict = Depends(require_engagement_member),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> list[SampleReviewEventOut]:
    """Every reviewer action on a sample in the cycle, newest first."""
    from app.services.sample_review_service import SampleReviewService

    return await SampleReviewService(db).events_for_cycle(cycle_id)


@router.put("/{cycle_id}/sample-review", response_model=SampleReviewOut)
async def save_sample_review(
    cycle_id: int,
    data: SampleReviewIn,
    config_control_id: int = Query(...),
    sample_no: int = Query(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> SampleReviewOut:
    """Record the reviewer's edit, comment, people involved and/or verdict on
    one sample. A changed outcome becomes the sample's effective result."""
    from app.services.sample_review_service import SampleReviewService

    return await SampleReviewService(db).save(
        cycle_id, config_control_id, sample_no, data, current_user
    )


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    client_id: int = Query(...),
    current_user: dict = Depends(get_current_user),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> list[NotificationOut]:
    """The reviewer's actions across the client's cycles, newest first — what a
    tester is notified of."""
    from app.services.sample_review_service import SampleReviewService

    return await SampleReviewService(db).notifications(client_id)


@router.get("/{cycle_id}/sampling-check", response_model=SamplingCheckOut)
async def sampling_check(
    cycle_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SamplingCheckOut:
    """Each control's sample count checked against its population.

    Flags controls whose population is smaller than the matrix asks for, and
    controls that cannot be tested (no population, or no matrix size).
    """
    service = ConfigControlService(db)
    return await service.sampling_check(cycle_id)


@router.delete("/delete-cycle", status_code=204, response_model=None)
async def delete_review_cycle(
    cycle_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_manage_cycles")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ReviewCycleService(db)
    await service.delete_cycle(cycle_id, current_user)


@router.get("/cycles-overview", response_model=list[CycleOverviewOut])
async def cycles_overview(
    client_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CycleOverviewOut]:
    """Per-cycle summary for the Review Cycles screen: controls, recorded
    testing results by control, review state, evidence and team."""
    from app.services.cycle_overview_service import client_overview

    return await client_overview(db, client_id)


@router.get("/get-cycle-stats")
async def get_review_cycle_stats(
    cycle_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ReviewCycleService(db)
    return await service.get_stats(cycle_id)


# ---------------------------------------------------------------------------
# Engagement Team
# ---------------------------------------------------------------------------


@router.get("/{cycle_id}/list-team-members", response_model=list[TeamMemberOut])
async def get_team(
    cycle_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamMemberOut]:
    service = EngagementTeamService(db)
    return await service.get_team(cycle_id)


@router.post("/{cycle_id}/add-team-member", response_model=TeamMemberOut, status_code=201)
async def add_team_member(
    cycle_id: int,
    data: TeamMemberAdd,
    current_user: dict = Depends(require_permission("can_assign_team")),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberOut:
    service = EngagementTeamService(db)
    return await service.add_member(cycle_id, data)


@router.post(
    "/{cycle_id}/add-team-members-bulk", response_model=list[TeamMemberOut], status_code=201
)
async def bulk_add_team_members(
    cycle_id: int,
    data: TeamMemberBulkAdd,
    current_user: dict = Depends(require_permission("can_assign_team")),
    db: AsyncSession = Depends(get_db),
) -> list[TeamMemberOut]:
    service = EngagementTeamService(db)
    return await service.bulk_add(cycle_id, data.members)


@router.put("/{cycle_id}/update-team-member", response_model=TeamMemberOut)
async def update_team_member_role(
    cycle_id: int,
    user_id: int = Query(...),
    data: TeamMemberUpdate = Body(...),
    current_user: dict = Depends(require_permission("can_assign_team")),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberOut:
    service = EngagementTeamService(db)
    return await service.update_role(cycle_id, user_id, data.team_role)


@router.delete("/{cycle_id}/remove-team-member", status_code=204, response_model=None)
async def remove_team_member(
    cycle_id: int,
    user_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_assign_team")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = EngagementTeamService(db)
    await service.remove_member(cycle_id, user_id)


# ---------------------------------------------------------------------------
# Cycle Controls (Phase 4)
# ---------------------------------------------------------------------------


@router.get("/{cycle_id}/list-controls", response_model=list[ConfigControlOut])
async def get_cycle_controls(
    cycle_id: int,
    current_user: dict = Depends(require_engagement_member),
    db: AsyncSession = Depends(get_db),
) -> list[ConfigControlOut]:
    service = ConfigControlService(db)
    return await service.get_cycle_controls(cycle_id)


@router.post("/{cycle_id}/add-control", response_model=ConfigControlOut, status_code=201)
async def attach_control(
    cycle_id: int,
    data: ConfigControlCreate,
    current_user: dict = Depends(require_permission("can_manage_controls")),
    db: AsyncSession = Depends(get_db),
) -> ConfigControlOut:
    service = ConfigControlService(db)
    return await service.attach_control(cycle_id, data.control_id)


@router.post(
    "/{cycle_id}/add-controls-bulk", response_model=list[ConfigControlOut], status_code=201
)
async def bulk_attach_controls(
    cycle_id: int,
    data: ConfigControlBulkCreate,
    current_user: dict = Depends(require_permission("can_manage_controls")),
    db: AsyncSession = Depends(get_db),
) -> list[ConfigControlOut]:
    service = ConfigControlService(db)
    return await service.bulk_attach(cycle_id, data.control_ids)


async def _cycle_control(db: AsyncSession, cycle_id: int, config_control_id: int) -> Any:
    from app.core.exceptions import NotFoundException
    from app.models.config_control import ConfigControl

    cc = await db.get(ConfigControl, config_control_id)
    if cc is None or cc.cycle_id != cycle_id:
        raise NotFoundException("Attached control not found in this cycle.")
    return cc


# ---------------------------------------------------------------------------
# Testing phases (matrix-sampled cycles)
# ---------------------------------------------------------------------------


@router.get("/{cycle_id}/phases", response_model=CyclePhasesOut)
async def list_cycle_phases(
    cycle_id: int,
    current_user: dict = Depends(require_engagement_member),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> CyclePhasesOut:
    """Every control's phase path, runs, results and history. Empty for a
    full-population cycle, which is tested in a single round."""
    from app.services.phase_service import PhaseService, period_under_review

    service = PhaseService(db)
    controls = await service.cycle_phases(cycle_id)
    return CyclePhasesOut(
        cycle_id=cycle_id,
        period_under_review=period_under_review(),
        cycle_phase=await service.cycle_phase(cycle_id) if controls else None,
        controls=controls,
    )


@router.put("/{cycle_id}/phase-sample-size", response_model=ControlPhasesOut)
async def override_phase_sample_size(
    cycle_id: int,
    config_control_id: int = Query(...),
    data: PhaseSampleSizeIn = Body(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ControlPhasesOut:
    """Change the sample count of the control's current phase (not DE)."""
    from app.models.review_cycle import ReviewCycle
    from app.services.phase_service import PhaseService

    cc = await _cycle_control(db, cycle_id, config_control_id)
    service = PhaseService(db)
    await service.override_size(
        cc, data.phase_run_id, data.size, data.reason, int(current_user["sub"])
    )
    await db.commit()
    return ControlPhasesOut(**await service.control_phases(cc, await db.get(ReviewCycle, cycle_id)))


@router.post("/{cycle_id}/phase-sample-size/reset", response_model=ControlPhasesOut)
async def reset_phase_sample_size(
    cycle_id: int,
    config_control_id: int = Query(...),
    data: PhaseSampleSizeResetIn = Body(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ControlPhasesOut:
    """Return the current phase's sample count to the sampling matrix's."""
    from app.models.review_cycle import ReviewCycle
    from app.services.phase_service import PhaseService

    cc = await _cycle_control(db, cycle_id, config_control_id)
    service = PhaseService(db)
    await service.reset_size(cc, data.phase_run_id, int(current_user["sub"]))
    await db.commit()
    return ControlPhasesOut(**await service.control_phases(cc, await db.get(ReviewCycle, cycle_id)))


@router.put("/{cycle_id}/phase-size-computed", response_model=ControlPhasesOut)
async def mark_phase_size_computed(
    cycle_id: int,
    config_control_id: int = Query(...),
    data: PhaseSizeComputedIn = Body(...),
    current_user: dict = Depends(require_engagement_member),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> ControlPhasesOut:
    """Keep (or clear) a phase run's computed sample count on the Controls table."""
    from app.models.review_cycle import ReviewCycle
    from app.services.phase_service import PhaseService

    cc = await _cycle_control(db, cycle_id, config_control_id)
    service = PhaseService(db)
    await service.mark_computed(cc, data.phase_run_id, data.computed)
    await db.commit()
    return ControlPhasesOut(**await service.control_phases(cc, await db.get(ReviewCycle, cycle_id)))


@router.get("/{cycle_id}/selectable-samples")
async def list_selectable_samples(
    cycle_id: int,
    config_control_id: int = Query(...),
    current_user: dict = Depends(require_engagement_member),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The current phase run's sample collections — each sample's evidence
    documents under a vault collection ID — and which can be chosen."""
    from app.services.manual_selection import selectable_samples

    return await selectable_samples(db, await _cycle_control(db, cycle_id, config_control_id))


@router.put("/{cycle_id}/select-samples", response_model=ControlPhasesOut)
async def select_phase_samples(
    cycle_id: int,
    config_control_id: int = Query(...),
    data: dict = Body(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ControlPhasesOut:
    """Set the current phase run's samples to the collections the tester chose."""
    from app.models.review_cycle import ReviewCycle
    from app.services.manual_selection import select_samples
    from app.services.phase_service import PhaseService

    cc = await _cycle_control(db, cycle_id, config_control_id)
    await select_samples(
        db, cc, [int(n) for n in data.get("sample_nos") or []], int(current_user["sub"])
    )
    await db.commit()
    return ControlPhasesOut(
        **await PhaseService(db).control_phases(cc, await db.get(ReviewCycle, cycle_id))
    )


@router.post("/{cycle_id}/redraw-samples", response_model=ControlPhasesOut)
async def redraw_phase_samples(
    cycle_id: int,
    config_control_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ControlPhasesOut:
    """Re-run the testing configuration: draw the current phase run's samples
    again, the same count, other samples from the same evidence window."""
    from app.models.review_cycle import ReviewCycle
    from app.services.phase_service import PhaseService

    cc = await _cycle_control(db, cycle_id, config_control_id)
    service = PhaseService(db)
    await service.redraw(cc, int(current_user["sub"]))
    await db.commit()
    return ControlPhasesOut(**await service.control_phases(cc, await db.get(ReviewCycle, cycle_id)))


@router.post("/{cycle_id}/phase-fail", response_model=ControlPhasesOut)
async def conclude_phase_failed(
    cycle_id: int,
    config_control_id: int = Query(...),
    data: PhaseFailIn = Body(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ControlPhasesOut:
    """Conclude the current phase as failed and open its remediation round."""
    from app.models.review_cycle import ReviewCycle
    from app.services.phase_service import PhaseService

    cc = await _cycle_control(db, cycle_id, config_control_id)
    service = PhaseService(db)
    await service.conclude_failed(cc, data.reason, int(current_user["sub"]))
    await db.commit()
    return ControlPhasesOut(**await service.control_phases(cc, await db.get(ReviewCycle, cycle_id)))


@router.post("/{cycle_id}/start-testing", response_model=ConfigControlOut)
async def start_testing(
    cycle_id: int,
    config_control_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ConfigControlOut:
    """The tester starts testing a control (its current phase, when phased)."""
    return await ConfigControlService(db).start_testing(cycle_id, config_control_id, current_user)


@router.get("/{cycle_id}/review-status", response_model=list[ControlReviewStatusOut])
async def list_review_status(
    cycle_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ControlReviewStatusOut]:
    """Stored review state for the cycle's controls (none until submitted)."""
    return await ControlReviewService(db).list_for_cycle(cycle_id, current_user)


@router.get("/{cycle_id}/review-events", response_model=list[ControlReviewEventOut])
async def list_review_events(
    cycle_id: int,
    config_control_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ControlReviewEventOut]:
    """The control's review trail, newest first."""
    return await ControlReviewService(db).list_events(cycle_id, config_control_id, current_user)


@router.post("/{cycle_id}/submit-for-review", response_model=ControlReviewStatusOut)
async def submit_for_review(
    cycle_id: int,
    config_control_id: int = Query(...),
    data: SubmitForReviewRequest = Body(default=SubmitForReviewRequest()),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ControlReviewStatusOut:
    """Tester hands one control to the reviewer."""
    return await ControlReviewService(db).submit(
        cycle_id, config_control_id, data.note, current_user
    )


@router.post("/{cycle_id}/submit-many-for-review", response_model=SubmitForReviewResult)
async def submit_many_for_review(
    cycle_id: int,
    data: SubmitManyRequest = Body(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> SubmitForReviewResult:
    """Tester hands several finished controls over in one action."""
    return await ControlReviewService(db).submit_many(
        cycle_id, data.config_control_ids, current_user
    )


@router.post("/{cycle_id}/review-verdict", response_model=ControlReviewStatusOut)
async def record_review_verdict(
    cycle_id: int,
    config_control_id: int = Query(...),
    data: ReviewVerdictRequest = Body(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> ControlReviewStatusOut:
    """Reviewer records their decision on a submitted control."""
    return await ControlReviewService(db).record_verdict(
        cycle_id, config_control_id, data.verdict, data.note, current_user
    )


@router.get("/{cycle_id}/default-evidence", response_model=DefaultEvidenceStatusOut)
async def get_default_evidence_status(
    cycle_id: int,
    config_control_id: int = Query(...),
    current_user: dict = Depends(require_engagement_member),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
) -> DefaultEvidenceStatusOut:
    """How much of this control's default evidence is still to attach."""
    from app.services.default_evidence import plan_default_evidence

    plan = await plan_default_evidence(db, await _cycle_control(db, cycle_id, config_control_id))
    return DefaultEvidenceStatusOut(
        configured=plan.configured,
        planned=plan.planned,
        missing=len(plan.missing),
        unavailable=plan.unavailable,
        missing_files=[
            DefaultEvidenceFileOut(sample_no=n, file_name=p.name) for n, p in plan.missing
        ],
    )


@router.post("/{cycle_id}/attach-default-evidence", response_model=DefaultEvidenceAttachOut)
async def attach_default_evidence(
    cycle_id: int,
    config_control_id: int = Query(...),
    sample_no: int | None = Query(default=None),
    file_name: str | None = Query(default=None),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> DefaultEvidenceAttachOut:
    """Attach missing default evidence to this control's samples.

    With `sample_no` and `file_name`, attaches only that one file (the Testing
    tab attaches file by file); without them, attaches everything missing.
    """
    from app.core.exceptions import ForbiddenException
    from app.services.default_evidence import attach_default_evidence as attach
    from app.services.default_evidence import attach_one_default_evidence, plan_default_evidence

    roles = current_user.get("roles", [])
    if not any(r in ("Admin", "Moderator") for r in roles):
        from app.repositories.engagement_team_repo import EngagementTeamRepo

        if not await EngagementTeamRepo(db).is_member(cycle_id, int(current_user["sub"])):
            raise ForbiddenException("Not a member of this engagement.")

    cc = await _cycle_control(db, cycle_id, config_control_id)
    if sample_no is not None and file_name:
        done = await attach_one_default_evidence(
            db, cc, int(current_user["sub"]), sample_no, file_name
        )
        after = await plan_default_evidence(db, cc)
        return DefaultEvidenceAttachOut(
            configured=after.configured,
            planned=after.planned,
            missing=len(after.missing),
            unavailable=after.unavailable,
            attached=1 if done else 0,
        )
    plan = await attach(db, cc, int(current_user["sub"]))
    return DefaultEvidenceAttachOut(
        configured=plan.configured,
        planned=plan.planned,
        missing=0,
        unavailable=plan.unavailable,
        attached=len(plan.missing),
    )


@router.post("/{cycle_id}/calculate-sample-size", response_model=SampleSizeResultOut)
async def calculate_sample_size(
    cycle_id: int,  # noqa: ARG001 — path scoping only; lookup is by config_control_id
    config_control_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_manage_controls")),
    db: AsyncSession = Depends(get_db),
) -> SampleSizeResultOut:
    """Determine this attached control's sample size.

    Resolves the control's attributes against the sampling methodology
    matrix, falling back to the size defined on the control itself when no
    mapping applies.
    """
    service = ConfigControlService(db)
    return await service.calculate_sample_size(config_control_id)


@router.get("/{cycle_id}/check-evidence", response_model=EvidenceCheckOut)
async def check_evidence(
    cycle_id: int,  # noqa: ARG001 — path scoping only
    config_control_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceCheckOut:
    """Whether this control's evidence permits test execution."""
    service = ConfigControlService(db)
    return await service.check_evidence(config_control_id)


@router.get("/{cycle_id}/evidence-pages")
async def get_evidence_pages(
    cycle_id: int,  # noqa: ARG001 — path scoping only
    config_control_id: int = Query(...),
    sample_no: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Evidence for one sample, trimmed to the pages it was validated on."""
    service = ConfigControlService(db)
    content, media_type, filename = await service.get_evidence_pages(config_control_id, sample_no)
    safe_name = filename.replace('"', "")
    return Response(
        content=content,
        media_type=media_type,
        # inline so the browser renders it in the new tab rather than downloading
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.delete("/{cycle_id}/clear-evidence")
async def clear_cycle_evidence(
    cycle_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Remove every evidence file attached to this cycle. Admin-only."""
    service = EvidenceService(db)
    deleted = await service.delete_all_for_cycle(cycle_id, current_user)
    return {"deleted": deleted}


@router.get("/{cycle_id}/test-output", response_model=ControlTestOutputOut)
async def get_test_output(
    cycle_id: int,  # noqa: ARG001 — path scoping only; lookup is by config_control_id
    config_control_id: int = Query(...),
    phase_run_id: int | None = Query(
        None, description="Phased cycles: an earlier phase run instead of the current one."
    ),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ControlTestOutputOut:
    """Testing output for an attached control — drives the Testing table."""
    service = ConfigControlService(db)
    return await service.get_test_output(config_control_id, phase_run_id)


@router.get("/{cycle_id}/test-outputs", response_model=list[ControlTestOutputOut])
async def list_test_outputs(
    cycle_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ControlTestOutputOut]:
    """Testing output for every control attached to this cycle.

    Backs the cycle-wide progress dashboards, which need the sample rows of
    all attached controls rather than one control at a time.
    """
    service = ConfigControlService(db)
    return await service.get_cycle_test_outputs(cycle_id)


@router.delete("/{cycle_id}/remove-control", status_code=204, response_model=None)
async def detach_control(
    cycle_id: int,
    control_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_manage_controls")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ConfigControlService(db)
    await service.detach_control(cycle_id, control_id)


@router.delete("/{cycle_id}/bulk-remove-controls", status_code=204, response_model=None)
async def bulk_detach_controls(
    cycle_id: int,
    data: ConfigControlBulkRemove,
    current_user: dict = Depends(require_permission("can_manage_controls")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ConfigControlService(db)
    await service.bulk_detach(cycle_id, data.config_control_ids)


@router.delete("/{cycle_id}/reset-controls", status_code=204, response_model=None)
async def reset_cycle_controls(
    cycle_id: int,
    current_user: dict = Depends(require_permission("can_manage_controls")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ConfigControlService(db)
    await service.reset_cycle_controls(cycle_id)


# ---------------------------------------------------------------------------
# Cycle Test Logs & Evidence (Phase 5)
# ---------------------------------------------------------------------------


@router.get("/{cycle_id}/list-test-logs", response_model=list[TestLogOut])
async def list_cycle_test_logs(
    cycle_id: int,
    current_user: dict = Depends(require_engagement_member),
    db: AsyncSession = Depends(get_db),
) -> list[TestLogOut]:
    service = TestLogService(db)
    return await service.list_by_cycle(cycle_id)


@router.get("/{cycle_id}/list-evidence", response_model=list[EvidenceOut])
async def list_cycle_evidence(
    cycle_id: int,
    current_user: dict = Depends(require_engagement_member),
    db: AsyncSession = Depends(get_db),
) -> list[EvidenceOut]:
    service = EvidenceService(db)
    items, _ = await service.list_evidence(
        {"cycle_id": cycle_id},
        int(current_user["sub"]),
        current_user.get("roles", []),
        page=1,
        # Every file in the cycle: the Testing tab derives per-sample evidence
        # from this list, and a demo cycle alone holds a few hundred.
        page_size=5000,
    )
    return items


@router.get("/{cycle_id}/list-test-objectives", response_model=list[CycleTestObjectiveOut])
async def list_cycle_test_objectives(
    cycle_id: int,
    current_user: dict = Depends(require_engagement_member),
    db: AsyncSession = Depends(get_db),
) -> list[CycleTestObjectiveOut]:
    service = ControlTestService(db)
    return await service.list_cycle_test_objectives(cycle_id)

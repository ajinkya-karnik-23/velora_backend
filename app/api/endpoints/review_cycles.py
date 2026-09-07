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
    ConfigControlBulkCreate,
    ConfigControlBulkRemove,
    ConfigControlCreate,
    ConfigControlOut,
    ControlTestOutputOut,
    EvidenceCheckOut,
    SampleSizeResultOut,
)
from app.schemas.control_test import CycleTestObjectiveOut
from app.schemas.engagement_team import (
    TeamMemberAdd,
    TeamMemberBulkAdd,
    TeamMemberOut,
    TeamMemberUpdate,
)
from app.schemas.evidence import EvidenceOut
from app.schemas.review_cycle import ReviewCycleCreate, ReviewCycleOut, ReviewCycleUpdate
from app.schemas.test_log import TestLogOut
from app.services.config_control_service import ConfigControlService
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


@router.delete("/delete-cycle", status_code=204, response_model=None)
async def delete_review_cycle(
    cycle_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_manage_cycles")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ReviewCycleService(db)
    await service.delete_cycle(cycle_id, current_user)


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


@router.post("/{cycle_id}/add-team-members-bulk", response_model=list[TeamMemberOut], status_code=201)
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


@router.post(
    "/{cycle_id}/calculate-sample-size", response_model=SampleSizeResultOut
)
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
    content, media_type, filename = await service.get_evidence_pages(
        config_control_id, sample_no
    )
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
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ControlTestOutputOut:
    """Testing output for an attached control — drives the Testing table."""
    service = ConfigControlService(db)
    return await service.get_test_output(config_control_id)


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
        page_size=100,
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

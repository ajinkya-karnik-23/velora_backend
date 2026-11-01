"""Report generation endpoint."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.models.config_control import ConfigControl
from app.models.control_repository import ControlRepository
from app.models.evidence_file import EvidenceFile
from app.models.user import User
from app.services.report_generation_module.generate_report import generate_test_report
from app.services.twp_templates import load_twp_templates

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


@router.get("/twp-template")
async def download_twp_template(
    config_control_id: int = Query(...),
    tests_completed: bool = Query(
        False,
        description=(
            "Whether every sample for this control has been tested. Selects the "
            "completed work paper over the empty template."
        ),
    ),
    phase_run_id: int | None = Query(
        None, description="Phased cycles: the phase run the paper covers (default: current)."
    ),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the Test Work Paper (TWP) report for an attached control.

    Two workbooks are configured per control: an empty template while testing
    is outstanding, and the completed report once every sample has been
    tested. Which one applies is decided by `tests_completed`; which file
    backs each is configured in the TWP template map, so controls can be
    added without code changes.
    """
    cc = await db.get(ConfigControl, config_control_id)
    if cc is None:
        raise NotFoundException("Attached control not found.")

    control = await db.get(ControlRepository, cc.control_id)
    control_number = control.control_number if control else ""

    suffix = "Completed" if tests_completed else "Template"
    stem = control_number or str(config_control_id)
    entity = f".{cc.entity_code}" if cc.entity_code else ""

    # A phased cycle's paper covers one phase run and is always built live,
    # named for the phase: TWP_IA4.CA14.19A1_OE_Completed.xlsm.
    phase = await _phase_for(db, cc, phase_run_id)
    if phase is not None and cc.entity_code and control_number:
        from app.services.twp_builder import TwpBuildError, build_twp_workbook
        from app.services.twp_context import twp_context

        try:
            wb = build_twp_workbook(
                control_number, cc.entity_code, await twp_context(db, cc, phase.phase_run_id)
            )
        except TwpBuildError as exc:
            raise NotFoundException("The TWP for this phase could not be built.") from exc
        buffer = io.BytesIO()
        wb.save(buffer)
        state = "Completed" if tests_completed or phase.status != "active" else "In_Progress"
        return Response(
            content=buffer.getvalue(),
            media_type="application/vnd.ms-excel.sheet.macroEnabled.12",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="TWP_{stem}{entity}_{_phase_tag(phase)}_{state}.xlsm"'
                ),
                "X-TWP-Variant": "phase",
                "Access-Control-Expose-Headers": "X-TWP-Variant, Content-Disposition",
            },
        )

    # The completed work paper — and the record of a control that could not be
    # tested — is built for this cycle: its own samples, their document
    # references, anything left untested, and who prepared and reviewed it.
    if (tests_completed or cc.not_tested_reason) and cc.entity_code and control_number:
        from app.services.twp_builder import TwpBuildError, build_twp_workbook
        from app.services.twp_context import twp_context

        try:
            wb = build_twp_workbook(
                control_number, cc.entity_code, await twp_context(db, cc)
            )
        except TwpBuildError:
            wb = None  # fall back to the configured static workbook
        if wb is not None:
            buffer = io.BytesIO()
            wb.save(buffer)
            variant = "completed" if tests_completed else "not_tested"
            return Response(
                content=buffer.getvalue(),
                media_type="application/vnd.ms-excel.sheet.macroEnabled.12",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="TWP_{stem}{entity}_'
                        f'{"Completed" if tests_completed else "Not_Tested"}.xlsm"'
                    ),
                    "X-TWP-Variant": variant,
                    "Access-Control-Expose-Headers": "X-TWP-Variant, Content-Disposition",
                },
            )

    mapped = load_twp_templates(
        Path(settings.TWP_TEMPLATE_MAP_PATH), control_number, cc.entity_code
    )
    configured = mapped.for_state(tests_completed)

    # Controls with no mapping fall back to the generic template, so a control
    # that has not been configured yet still returns a usable work paper.
    template_path = Path(configured) if configured else Path(settings.TWP_TEMPLATE_PATH)
    if not template_path.exists():
        variant = "completed" if tests_completed else "empty"
        raise NotFoundException(
            f"The {variant} TWP template for this control is not available. "
            "Check the TWP template map configuration."
        )

    filename = f"TWP_{stem}{entity}_{suffix}{template_path.suffix}"

    return Response(
        content=template_path.read_bytes(),
        media_type="application/vnd.ms-excel.sheet.macroEnabled.12",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Lets the caller confirm which variant it actually received.
            "X-TWP-Variant": "completed" if tests_completed else "empty",
            "Access-Control-Expose-Headers": "X-TWP-Variant, Content-Disposition",
        },
    )


def _phase_tag(phase: Any) -> str:
    """OE, RF … or RM1-DE for a remediation round, as used in file names."""
    if phase.phase == "RM":
        return f"RM{phase.attempt}-{phase.base_phase}"
    return phase.phase


async def _phase_for(db: AsyncSession, cc: ConfigControl, phase_run_id: int | None) -> Any:
    """The phase run a download covers, or None for an unphased cycle."""
    from app.services.config_control_service import ConfigControlService

    output = await ConfigControlService(db).get_test_output(cc.config_control_id, phase_run_id)
    return output.phase


@router.get("/crp")
async def download_crp(
    config_control_id: int = Query(...),
    phase_run_id: int | None = Query(None),
    tests_completed: bool = Query(False),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the Continuous Reviewable Process (CRP) workbook for a phase.

    A placeholder until the client's CRP format is defined: a cover sheet for
    the phase and one row per sample tested in it. Named like the TWP:
    CRP_IA4.CA14.19A1_OE_Completed.xlsx.
    """
    from app.services.crp_builder import build_crp_workbook
    from app.services.twp_context import twp_context

    cc = await db.get(ConfigControl, config_control_id)
    if cc is None:
        raise NotFoundException("Attached control not found.")
    control = await db.get(ControlRepository, cc.control_id)
    control_number = control.control_number if control else str(config_control_id)
    phase = await _phase_for(db, cc, phase_run_id)
    context = await twp_context(db, cc, phase.phase_run_id if phase else None)

    wb = build_crp_workbook(
        control_number=control_number,
        control_name=control.control_name if control else None,
        entity_code=cc.entity_code,
        context=context,
    )
    buffer = io.BytesIO()
    wb.save(buffer)
    entity = f".{cc.entity_code}" if cc.entity_code else ""
    tag = f"_{_phase_tag(phase)}" if phase else ""
    state = (
        "Completed"
        if tests_completed or (phase is not None and phase.status != "active")
        else "In_Progress"
    )
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="CRP_{control_number}{entity}{tag}_{state}.xlsx"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


async def _cycle_reports(db: AsyncSession, cycle_id: int) -> tuple[Any, list[dict[str, Any]]]:
    from app.models.review_cycle import ReviewCycle
    from app.services.phase_service import PhaseService, phased

    cycle = await db.get(ReviewCycle, cycle_id)
    if cycle is None or not phased(cycle):
        raise NotFoundException("No phased cycle to report on.")
    return cycle, await PhaseService(db).cycle_phases(cycle_id)


def _not_ready(message: str) -> Exception:
    from app.core.exceptions import AppException

    return AppException(code="PHASE_NOT_COMPLETE", message=message, status_code=409)


def _file_stem(cycle: Any) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9-]+", "_", cycle.name.replace("–", "-")).strip("_")


async def _filled_crp(
    db: AsyncSession, cycle: Any, controls: list[dict[str, Any]], phases: list[str]
) -> bytes:
    """The client's CRP workbook with each given phase's sheet filled."""
    from collections import Counter

    from app.services.crp_report import crp_rows, identity_rows, scope_notes
    from app.services.crp_template import PHASE_SHEETS
    from app.services.crp_template import fill_crp

    template = Path(settings.CRP_TEMPLATE_PATH)
    if not template.exists():
        raise NotFoundException("The CRP template is not available. Check CRP_TEMPLATE_PATH.")
    # Every phase sheet lists only the cycle's controls: filled where the
    # phase is complete, by name and attributes where it is still to come.
    rows = {
        p: await crp_rows(db, controls, p) if p in phases else await identity_rows(db, controls, p)
        for p in PHASE_SHEETS
        if any(p in c["path"] for c in controls)
    }
    approvers = Counter(
        r["concluded_by_name"]
        for c in controls
        for r in c["runs"]
        if r["base_phase"] in phases and r["status"] == "approved" and r["concluded_by_name"]
    )
    intro = {
        "F14": cycle.entity_code or "",
        "F16": approvers.most_common(1)[0][0] if approvers else "",
    }
    notes = {p: scope_notes(controls, p, cycle.name) for p in rows}
    return fill_crp(template.read_bytes(), rows, intro, notes)


def _xlsx(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/crp-phase")
async def download_cycle_crp(
    cycle_id: int = Query(...),
    phase: str = Query(..., description="DE, OE, RF or YE."),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the cycle's CRP once a phase is complete.

    The client's Concurrent Review Process workbook (CRP_TEMPLATE_PATH),
    structure untouched, with the phase's sheet — and every earlier phase's —
    filled from the platform. Issued only once every control on the phase has
    its final round (the phase, or its last remediation round) approved.
    """
    from app.services.crp_report import phase_complete
    from app.services.crp_template import PHASE_SHEETS

    code = phase.strip().upper()
    cycle, controls = await _cycle_reports(db, cycle_id)
    if code not in PHASE_SHEETS:
        raise NotFoundException(f"The CRP template has no sheet for {code}.")
    if not controls or not all(phase_complete(c, code) for c in controls):
        raise _not_ready(f"The {code} CRP is issued once {code} is approved for every control.")
    order = list(PHASE_SHEETS)
    phases = [
        p
        for p in order[: order.index(code) + 1]
        if all(phase_complete(c, p) for c in controls)
        and any(p in c["path"] for c in controls)
    ]
    content = await _filled_crp(db, cycle, controls, phases)
    return _xlsx(content, f"CRP_{_file_stem(cycle)}_{code}_Completed.xlsx")


@router.get("/crp-final")
async def download_final_crp(
    cycle_id: int = Query(...),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The cycle's final CRP: every phase sheet filled, once every phase of
    every control is approved."""
    from app.services.crp_template import PHASE_SHEETS
    from app.services.phase_service import first_needed

    cycle, controls = await _cycle_reports(db, cycle_id)
    if not controls or any(first_needed(c["path"], _runs(c)) for c in controls):
        raise _not_ready("The final CRP is issued once every phase is approved for every control.")
    phases = [p for p in PHASE_SHEETS if any(p in c["path"] for c in controls)]
    content = await _filled_crp(db, cycle, controls, phases)
    return _xlsx(content, f"CRP_{_file_stem(cycle)}_Final.xlsx")


@router.get("/twp-final")
async def download_final_twps(
    cycle_id: int = Query(...),
    _current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Every control's TWP for every phase (its final round), in one zip,
    once every phase of every control is approved."""
    import zipfile

    from app.services.phase_service import first_needed
    from app.services.twp_builder import TwpBuildError, build_twp_workbook
    from app.services.twp_context import twp_context

    cycle, controls = await _cycle_reports(db, cycle_id)
    if not controls or any(first_needed(c["path"], _runs(c)) for c in controls):
        raise _not_ready("The final TWPs are issued once every phase is approved for every control.")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for c in controls:
            cc = await db.get(ConfigControl, c["config_control_id"])
            if cc is None or not cc.entity_code or not c["control_number"]:
                continue
            for p in c["path"]:
                rounds = [r for r in c["runs"] if r["base_phase"] == p]
                if not rounds:
                    continue
                final = rounds[-1]
                tag = (
                    f"RM{final['attempt']}-{p}" if final["phase"] == "RM" else final["phase"]
                )
                try:
                    wb = build_twp_workbook(
                        c["control_number"],
                        cc.entity_code,
                        await twp_context(db, cc, final["phase_run_id"]),
                    )
                except TwpBuildError:
                    continue
                buffer = io.BytesIO()
                wb.save(buffer)
                z.writestr(
                    f"{c['control_number']}.{cc.entity_code}/"
                    f"TWP_{c['control_number']}.{cc.entity_code}_{tag}_Completed.xlsm",
                    buffer.getvalue(),
                )
    return Response(
        content=out.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="TWP_{_file_stem(cycle)}_Final.zip"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


def _runs(control: dict[str, Any]) -> list[Any]:
    """A cycle_phases control's runs in the shape first_needed reads."""
    from types import SimpleNamespace

    return [
        SimpleNamespace(
            phase_run_id=r["phase_run_id"],
            phase=r["phase"],
            remediates_run_id=r["remediates_run_id"],
            status=r["status"],
        )
        for r in control["runs"]
    ]

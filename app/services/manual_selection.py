"""Choosing a phase run's samples by hand ("manual selection of samples").

A sample in the testing output is one test row; the evidence for it is a
collection of documents (the files the control's default-evidence map plans
for it, else the files the output lists as used). Choosing any document of a
collection chooses the whole collection, so a test never runs on part of its
evidence. Each collection carries a stable vault collection ID.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from app.core.exceptions import AppException
from app.models.control_repository import ControlRepository
from app.services.default_evidence import _entry_for, planned_files
from app.services.matrix_sampling import sample_no_of
from app.services.phase_demo import sample_date
from app.services.phase_service import (
    PhaseService,
    base_phase,
    effective_size,
    load_phased_output,
    run_label,
)
from app.services.review_state import with_reviewer
from app.services.test_output_matching import build_samples

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.config_control import ConfigControl


def collection_id(control_number: str, sample_no: int) -> str:
    return f"VC-{control_number}-{sample_no:03d}"


async def selectable_samples(db: AsyncSession, cc: ConfigControl) -> dict[str, Any]:
    """The current run's choosable collections: in its window, unused by any
    other run, with each sample's documents — and which are chosen now."""
    phases = PhaseService(db)
    run = await phases._active(cc)  # noqa: SLF001
    runs = await phases.runs(cc.config_control_id)
    by_id = {r.phase_run_id: r for r in runs}
    ctrl = await db.get(ControlRepository, cc.control_id)
    payload = load_phased_output(ctrl.control_number, cc.entity_code)
    population = build_samples(payload) if payload else []
    eligible, _ = phases._eligible(run, runs, ctrl, cc, population)  # noqa: SLF001
    allowed = {no for no, _ in eligible}
    used = {
        n for r in runs if r.phase_run_id != run.phase_run_id for n in (r.selected_samples or [])
    }
    entry = _entry_for(ctrl.control_number, cc.entity_code)
    collections = []
    for i, s in enumerate(population):
        no = sample_no_of(s, i)
        files = [p.name for p in planned_files(entry, s)] if entry else []
        if not files:
            files = [str(f) for f in (s.get("evidences_used") or [])]
        when = sample_date(s)
        collections.append(
            {
                "sample_no": no,
                "collection_id": collection_id(ctrl.control_number, no),
                "document_no": s.get("document_no"),
                "date": when.isoformat() if when else None,
                "documents": files,
                "parameters": [
                    {"label": p.get("label"), "value": p.get("value")}
                    for p in (s.get("parameters") or [])[:4]
                    if isinstance(p, dict)
                ],
                "selectable": no in allowed,
                "reason": (
                    None
                    if no in allowed
                    else (
                        "Tested in an earlier round"
                        if no in used
                        else "Outside the evidence window"
                    )
                ),
            }
        )
    return {
        "phase_run_id": run.phase_run_id,
        "label": run_label(run, by_id),
        "base_phase": base_phase(run, by_id),
        "size": effective_size(run),
        "selected": list(run.selected_samples or []),
        "collections": collections,
    }


async def select_samples(
    db: AsyncSession, cc: ConfigControl, sample_nos: list[int], actor_id: int
) -> None:
    """Set the current run's samples to the chosen collections."""
    phases = PhaseService(db)
    run = await phases._active(cc)  # noqa: SLF001
    if await with_reviewer(db, cc):
        raise AppException(
            code="WITH_REVIEWER",
            message="This phase is with the reviewer, so its samples cannot change.",
            status_code=409,
        )
    info = await selectable_samples(db, cc)
    allowed = {c["sample_no"] for c in info["collections"] if c["selectable"]}
    chosen = sorted(set(sample_nos))
    size = info["size"] or 0
    if not chosen or any(n not in allowed for n in chosen):
        raise AppException(
            code="SAMPLES_NOT_SELECTABLE",
            message=(
                "Choose collections from this phase's evidence window "
                "that no earlier round used."
            ),
            status_code=422,
        )
    if len(chosen) != size:
        raise AppException(
            code="SAMPLE_COUNT_MISMATCH",
            message=(
                f"This phase tests {size} sample{'s' if size != 1 else ''}; "
                "choose exactly that many collections."
            ),
            status_code=422,
        )
    before = list(run.selected_samples or [])
    now = int(time.time())
    phases._event(  # noqa: SLF001
        cc.config_control_id,
        run,
        "redrawn",
        "Samples chosen by hand.",
        actor_id,
        now,
        {"from": before},
    )
    run.selected_samples = chosen
    await db.flush()
    await phases._store(cc)  # noqa: SLF001
    phases._event(  # noqa: SLF001
        cc.config_control_id,
        run,
        "redrawn_to",
        None,
        actor_id,
        now,
        {"from": before, "to": chosen, "manual": True},
    )
    await db.flush()

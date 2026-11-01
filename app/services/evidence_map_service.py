"""Which supporting documents a cycle has, by date — for the Evidence tab.

Read-only. Every sample in a control's population (its testing output) is a
supporting document on a date; that date decides which phase's evidence
window it falls in. Beside each: the phase run that drew it (if any), its
recorded result, and how many files are attached to it in this cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.phase_rules import EVIDENCE_WINDOWS, PERIOD_UNDER_REVIEW
from app.models.config_control import ConfigControl
from app.models.evidence_file import EvidenceFile
from app.services.phase_demo import sample_date
from app.services.phase_service import PhaseService, base_phase, load_phased_output, run_label
from app.services.test_output_matching import build_samples

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def evidence_map(db: AsyncSession, cycle_id: int) -> dict[str, Any]:
    ccs = (
        (
            await db.execute(
                select(ConfigControl)
                .where(ConfigControl.cycle_id == cycle_id)
                .options(selectinload(ConfigControl.control))
                .order_by(ConfigControl.config_control_id)
            )
        )
        .scalars()
        .all()
    )
    attached = {
        (control_id, sample_no): n
        for control_id, sample_no, n in (
            await db.execute(
                select(EvidenceFile.control_id, EvidenceFile.sample_no, func.count())
                .where(EvidenceFile.cycle_id == cycle_id, EvidenceFile.sample_no.is_not(None))
                .group_by(EvidenceFile.control_id, EvidenceFile.sample_no)
            )
        ).all()
    }
    phases = PhaseService(db)
    controls: list[dict[str, Any]] = []
    for cc in ccs:
        ctrl = cc.control
        payload = load_phased_output(ctrl.control_number, cc.entity_code) if ctrl else None
        population = build_samples(payload) if payload else []
        runs = await phases.runs(cc.config_control_id)
        by_id = {r.phase_run_id: r for r in runs}
        results = await phases.results(cc, runs) if runs else {}
        drawn: dict[int, tuple[str, str, str | None]] = {}
        for r in runs:
            for no in r.selected_samples or []:
                drawn[no] = (
                    run_label(r, by_id),
                    base_phase(r, by_id),
                    results.get(r.phase_run_id, {}).get(no),
                )
        samples = []
        for i, s in enumerate(population):
            no = s["sample_no"] if isinstance(s.get("sample_no"), int) else i + 1
            when = sample_date(s)
            label, phase, result = drawn.get(no, (None, None, None))
            samples.append(
                {
                    "sample_no": no,
                    "date": when.isoformat() if when else None,
                    "document_no": s.get("document_no"),
                    "evidences": [str(e) for e in (s.get("evidences_used") or [])],
                    "drawn_by": label,
                    "drawn_phase": phase,
                    "result": result,
                    "attached": attached.get((cc.control_id, no), 0),
                }
            )
        controls.append(
            {
                "config_control_id": cc.config_control_id,
                "control_number": ctrl.control_number if ctrl else None,
                "control_name": ctrl.control_name if ctrl else None,
                "entity_code": cc.entity_code,
                "samples": samples,
            }
        )
    return {
        "cycle_id": cycle_id,
        "period": {
            "start": PERIOD_UNDER_REVIEW[0].isoformat(),
            "end": PERIOD_UNDER_REVIEW[1].isoformat(),
        },
        "windows": {
            p: {"start": w[0].isoformat(), "end": w[1].isoformat()}
            for p, w in EVIDENCE_WINDOWS.items()
        },
        "controls": controls,
    }

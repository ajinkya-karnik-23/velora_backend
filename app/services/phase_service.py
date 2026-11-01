"""A control's progress through its testing phases on a matrix-sampled cycle.

The lifecycle (rules in app/core/phase_rules.py):

    DE ──approved──▶ OE ──approved──▶ RF          (annual: DE ──▶ YE)
     │failed         │failed          │failed
     ▼               ▼                ▼
     RM 1 … n ──approved──▶ the phase after the one remediated

Each phase run draws its own samples: from that phase's evidence window,
never one an earlier run of the control has used. Sizing is DE = 1 always,
OE from frequency × risk, RF / RM / YE from their matrix column by frequency
only, with the population-band table for frequencies the matrix has no row
for. A tester may override any size except DE's.

The run's selection is what the Testing screen shows: it is written to
config_controls.selected_samples, which the testing output already filters
on. Sample numbers are unique within a control and never reused across runs,
so evidence, run logs and judgements — all keyed by sample — fall into the
right run without carrying a run id of their own.

Hand-over and verdict stay with the review workflow (control_review_status).
Approval of the current run advances the control and clears that row, so the
next phase starts fresh; a failure opens a remediation round the same way.
"""

from __future__ import annotations

import random
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import AppException, NotFoundException
from app.core.phase_rules import (
    CYCLE_ORDER,
    DE,
    DE_SAMPLE_SIZE,
    EVIDENCE_WINDOWS,
    PERIOD_UNDER_REVIEW,
    PHASE_NAMES,
    RM,
    YE,
    phase_path,
    planned_window,
)
from app.models.config_control import ConfigControl
from app.models.control_phase import (
    ACTIVE,
    APPROVED,
    FAILED,
    ControlPhaseEvent,
    ControlPhaseRun,
)
from app.models.control_repository import ControlRepository
from app.models.control_review import RETURNED, ControlReviewEvent, ControlReviewStatus
from app.models.review_cycle import ReviewCycle
from app.models.sample_judgement import SampleJudgement
from app.models.test_log import TestLog
from app.services.matrix_sampling import (
    NO_POPULATION_REASON,
    matrix_size,
    proportional_quotas,
    sample_no_of,
    sample_types,
    size_from_matrix_value,
)
from app.services.phase_demo import (
    apply_overlay,
    demo_changes_for,
    excluded_for,
    pins_for,
    sample_date,
)
from app.services.review_state import with_reviewer
from app.services.sampling_matrix import extract_control_parameters, load_sampling_matrix
from app.services.test_output_matching import build_samples, find_test_output

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# A logged run status, or a tester's judgement, that counts as an exception.
EXCEPTION_STATUSES = {"FAIL", "FAILED", "EVIDENCE_EXCEPTION"}

TOO_LARGE_MESSAGE = "That is more samples than this phase can draw. Please reduce the sample count."


def phased(cycle: ReviewCycle | None) -> bool:
    """Phases apply to matrix-sampled cycles; the full-population baseline keeps
    its single round of testing."""
    return cycle is not None and cycle.sampling_mode == "matrix"


def base_phase(run: ControlPhaseRun, runs_by_id: dict[int, ControlPhaseRun]) -> str:
    """The phase a run belongs to — for a remediation round, the remediated one."""
    if run.phase == RM and run.remediates_run_id in runs_by_id:
        return runs_by_id[run.remediates_run_id].phase
    return run.phase


def run_label(run: ControlPhaseRun, runs_by_id: dict[int, ControlPhaseRun]) -> str:
    if run.phase == RM:
        return f"RM {run.attempt} · {base_phase(run, runs_by_id)}"
    return run.phase


def effective_size(run: ControlPhaseRun) -> int | None:
    if run.phase == DE:
        return DE_SAMPLE_SIZE
    if run.override_size:
        return run.override_size
    return size_from_matrix_value(run.matrix_value)


def first_needed(path: list[str], runs: list[ControlPhaseRun]) -> str | None:
    """The first phase on the control's path it has not yet cleared — a phase is
    cleared once its last run (the phase itself or its final RM round) is
    approved. None once every phase is approved."""
    by_id = {r.phase_run_id: r for r in runs}
    last: dict[str, ControlPhaseRun] = {}
    for r in runs:
        last[base_phase(r, by_id)] = r
    for p in path:
        if p not in last or last[p].status != APPROVED:
            return p
    return None


def load_phased_output(control_number: str, entity_code: str | None) -> dict[str, Any] | None:
    """The control's testing output as a phased cycle reads it: the demo
    overlay applied, and its dates on the demo's testing calendar."""
    from app.services.demo_calendar import shift_payload

    payload = find_test_output(Path(settings.TEST_OUTPUTS_PATH), control_number, entity_code)
    return shift_payload(apply_overlay(payload, control_number, entity_code))


def _in_window(sample: dict[str, Any], window: tuple[date, date]) -> bool:
    when = sample_date(sample)
    return when is None or window[0] <= when <= window[1]


class PhaseService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------ reads

    async def runs(self, config_control_id: int) -> list[ControlPhaseRun]:
        return list(
            (
                await self.db.execute(
                    select(ControlPhaseRun)
                    .where(ControlPhaseRun.config_control_id == config_control_id)
                    .options(
                        selectinload(ControlPhaseRun.overrider),
                        selectinload(ControlPhaseRun.concluder),
                    )
                    .order_by(ControlPhaseRun.phase_run_id)
                )
            )
            .scalars()
            .all()
        )

    async def current_run(self, config_control_id: int) -> ControlPhaseRun | None:
        """The run being tested now, or — once the lifecycle is complete — the last."""
        runs = await self.runs(config_control_id)
        active = [r for r in runs if r.status == ACTIVE]
        return active[-1] if active else (runs[-1] if runs else None)

    async def run(self, config_control_id: int, phase_run_id: int) -> ControlPhaseRun:
        row = await self.db.get(ControlPhaseRun, phase_run_id)
        if row is None or row.config_control_id != config_control_id:
            raise NotFoundException("Phase run not found for this control.")
        return row

    # ------------------------------------------------------------ sampling

    async def plan(self, cc: ConfigControl, ctrl: ControlRepository) -> dict[str, Any]:
        """The control's sampling for its current phase run, starting DE if needed.

        Same shape as the full-population plan in ConfigControlService, plus the
        run and whether the run is still waiting for the tester to give a size.
        """
        params = extract_control_parameters(cc.entity_detail_json or ctrl.source_json or {})
        payload = load_phased_output(ctrl.control_number, cc.entity_code)
        population = build_samples(payload) if payload else []
        plan: dict[str, Any] = {
            "params": params,
            "available": len(population),
            "matrix_value": None,
            "source": None,
            "required": None,
            "selection": None,
            "not_tested_reason": None,
            "run": None,
            "awaiting_size": False,
        }
        if not population:
            plan["not_tested_reason"] = NO_POPULATION_REASON
            return plan

        run = await self.current_run(cc.config_control_id)
        if run is None:
            run = await self._start(cc, DE, None, 1, actor_id=None)
        runs = await self.runs(cc.config_control_id)
        if run.selected_samples is None:
            self._size(run, self.sizing_params(params, run, runs, ctrl, cc))
            if effective_size(run):
                run.selected_samples = self._select(
                    run,
                    runs,
                    ctrl,
                    cc,
                    population,
                    payload,
                    effective_size(run) or 0,
                    await self._redraws(run),
                )["selected"]
                await self.db.flush()

        required = effective_size(run)
        plan.update(
            run=run,
            matrix_value=run.matrix_value,
            source="override" if run.override_size else run.size_source,
            required=required,
        )
        if not required:
            plan["awaiting_size"] = True
            return plan
        plan["selection"] = self._describe(run, runs, ctrl, cc, population, payload)
        return plan

    @staticmethod
    def sizing_params(
        params: dict[str, Any],
        run: ControlPhaseRun,
        runs: list[ControlPhaseRun],
        ctrl: ControlRepository,
        cc: ConfigControl,
    ) -> dict[str, Any]:
        """The sizing inputs for a run. A control whose frequency was changed
        for the demo (to annual, to show year end) keeps the frequency it was
        sized under for every phase but YE, which reads the new one."""
        if base_phase(run, {r.phase_run_id: r for r in runs}) == YE:
            return params
        change = demo_changes_for(ctrl.control_number, cc.entity_code).get("frequency") or {}
        return {**params, "frequency": change["from"]} if change.get("from") else params

    def _size(self, run: ControlPhaseRun, params: dict[str, Any]) -> None:
        """Record what the rules and the matrix say this run should test."""
        if run.phase == DE:
            run.matrix_value, run.size_source = str(DE_SAMPLE_SIZE), "rule"
            return
        matrix = load_sampling_matrix(Path(settings.SAMPLING_MATRIX_PATH))
        raw, source = matrix_size(matrix, {**params, "phase": run.phase})
        run.matrix_value, run.size_source = raw, source or "none"

    def _eligible(
        self,
        run: ControlPhaseRun,
        runs: list[ControlPhaseRun],
        ctrl: ControlRepository,
        cc: ConfigControl,
        population: list[dict[str, Any]],
    ) -> tuple[list[tuple[int, dict[str, Any]]], list[int]]:
        """(samples this run may draw, the run's pinned samples).

        In the run's evidence window, unused by any other run of the control,
        and not held back for another phase's pinned demo sample.
        """
        by_id = {r.phase_run_id: r for r in runs}
        window = EVIDENCE_WINDOWS[base_phase(run, by_id)]
        used = {
            n
            for r in runs
            if r.phase_run_id != run.phase_run_id
            for n in (r.selected_samples or [])
        }
        pins = pins_for(ctrl.control_number, cc.entity_code)
        own_pins = pins.get(run.phase, []) if run.phase != RM else []
        reserved = {n for phase, nos in pins.items() if phase != run.phase for n in nos}
        if run.phase == RM:
            reserved |= {n for nos in pins.values() for n in nos}
        reserved |= excluded_for(ctrl.control_number, cc.entity_code)
        eligible = [
            (sample_no_of(s, i), s)
            for i, s in enumerate(population)
            if sample_no_of(s, i) not in used
            and sample_no_of(s, i) not in reserved
            and _in_window(s, window)
        ]
        allowed = {no for no, _ in eligible}
        return eligible, [n for n in own_pins if n in allowed]

    def _select(
        self,
        run: ControlPhaseRun,
        runs: list[ControlPhaseRun],
        ctrl: ControlRepository,
        cc: ConfigControl,
        population: list[dict[str, Any]],
        payload: dict[str, Any] | None,
        size: int,
        redraw: tuple[int, set[int]] = (0, set()),
    ) -> dict[str, Any]:
        """Draw the run's samples: pinned first, then a seeded random pick per
        sample type, the count shared across types in proportion to what the
        window holds. Seeded by control and run, so a reload never reshuffles."""
        eligible, pinned = self._eligible(run, runs, ctrl, cc, population)
        # A redraw ("re-run testing config") takes other samples: the ones drawn
        # before are set aside while enough remain, pins no longer apply, and
        # the seed moves on so the pick differs.
        redraws, drawn_before = redraw
        if redraws:
            fresh = [(no, smp) for no, smp in eligible if no not in drawn_before]
            if len(fresh) >= min(size, len(eligible)):
                eligible = fresh
            pinned = []
        header = (payload or {}).get("control_test_output")
        labels = sample_types([s for _, s in eligible], header)
        groups: dict[str, list[int]] = {}
        for (no, _), label in zip(eligible, labels, strict=True):
            groups.setdefault(label, []).append(no)

        size = min(size, len(eligible))
        chosen = set(pinned[:size])
        remaining = {label: [n for n in nos if n not in chosen] for label, nos in groups.items()}
        quotas = proportional_quotas(
            {label: len(nos) for label, nos in remaining.items()}, size - len(chosen)
        )
        by_id = {r.phase_run_id: r for r in runs}
        rng = random.Random(  # noqa: S311 — reproducible sample draw, not security
            f"{ctrl.control_number}|{cc.entity_code}|{run.phase}|"
            f"{base_phase(run, by_id)}|{run.attempt}" + (f"|redraw{redraws}" if redraws else "")
        )
        for label, nos in remaining.items():
            chosen.update(rng.sample(nos, min(quotas.get(label, 0), len(nos))))
        order = [no for no, _ in eligible]
        return {"selected": [n for n in order if n in chosen], "eligible": len(eligible)}

    def _describe(
        self,
        run: ControlPhaseRun,
        runs: list[ControlPhaseRun],
        ctrl: ControlRepository,
        cc: ConfigControl,
        population: list[dict[str, Any]],
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """The stored selection in the shape the sampling check reports."""
        selected = list(run.selected_samples or [])
        eligible, _ = self._eligible(run, runs, ctrl, cc, population)
        pool = eligible + [
            (sample_no_of(s, i), s)
            for i, s in enumerate(population)
            if sample_no_of(s, i) in selected and sample_no_of(s, i) not in dict(eligible)
        ]
        labels = sample_types([s for _, s in pool], (payload or {}).get("control_test_output"))
        types: dict[str, dict[str, Any]] = {}
        for (no, _), label in zip(pool, labels, strict=True):
            line = types.setdefault(label, {"label": label, "available": 0, "selected": 0})
            line["available"] += 1
            line["selected"] += int(no in selected)
        required = effective_size(run) or 0
        return {
            "selected": selected,
            "types": list(types.values()),
            "shortfall": max(0, required - len(selected)),
        }

    # ------------------------------------------------------------ writes

    async def _start(
        self,
        cc: ConfigControl,
        phase: str,
        remediates: ControlPhaseRun | None,
        attempt: int,
        actor_id: int | None,
    ) -> ControlPhaseRun:
        now = int(time.time())
        run = ControlPhaseRun(
            config_control_id=cc.config_control_id,
            phase=phase,
            remediates_run_id=remediates.phase_run_id if remediates else None,
            attempt=attempt,
            status=ACTIVE,
            started_time=now,
        )
        self.db.add(run)
        # A new phase or remediation round is started afresh by the tester.
        cc.testing_started_time = None
        cc.testing_started_by = None
        cc.testing_started_by_name = None
        await self.db.flush()
        self._event(cc.config_control_id, run, "started", None, actor_id, now)
        return run

    def _event(
        self,
        config_control_id: int,
        run: ControlPhaseRun | None,
        kind: str,
        note: str | None,
        actor_id: int | None,
        now: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            ControlPhaseEvent(
                config_control_id=config_control_id,
                phase_run_id=run.phase_run_id if run else None,
                kind=kind,
                note=note,
                detail=detail,
                actor_id=actor_id,
                event_time=now or int(time.time()),
            )
        )

    async def _store(self, cc: ConfigControl) -> None:
        """Re-plan the control and write its current selection to config_controls."""
        from app.services.config_control_service import ConfigControlService

        await ConfigControlService(self.db).apply_sampling(cc, "matrix")

    async def _clear_review(self, config_control_id: int) -> None:
        await self.db.execute(
            delete(ControlReviewStatus).where(
                ControlReviewStatus.config_control_id == config_control_id
            )
        )

    async def _active(self, cc: ConfigControl) -> ControlPhaseRun:
        runs = await self.runs(cc.config_control_id)
        active = [r for r in runs if r.status == ACTIVE]
        if not active:
            raise AppException(
                code="PHASES_COMPLETE",
                message="Every phase of this control has already been concluded.",
                status_code=409,
            )
        return active[-1]

    def _next_phase(
        self, run: ControlPhaseRun, runs: list[ControlPhaseRun], frequency: str | None
    ) -> str | None:
        path = phase_path(frequency)
        current = base_phase(run, {r.phase_run_id: r for r in runs})
        index = path.index(current) if current in path else len(path)
        return path[index + 1] if index + 1 < len(path) else None

    async def reopen_approval(self, cc: ConfigControl, actor_id: int) -> bool:
        """Reopen the control's last approved run so the reviewer can change the
        verdict. Only while the cycle is still in that phase: once any control
        has a run in a later phase, the approval stands (reopening it would
        put the cycle out of step). Returns False when there is nothing to
        reopen (a run is still active)."""
        runs = await self.runs(cc.config_control_id)
        if any(r.status == ACTIVE for r in runs):
            return False
        approved = [r for r in runs if r.status == APPROVED]
        if not approved:
            return False
        last = approved[-1]
        phase = base_phase(last, {r.phase_run_id: r for r in runs})
        for other in await self._cycle_controls(cc.cycle_id):
            other_runs = await self.runs(other.config_control_id)
            other_by_id = {r.phase_run_id: r for r in other_runs}
            if any(
                CYCLE_ORDER.index(base_phase(r, other_by_id)) > CYCLE_ORDER.index(phase)
                for r in other_runs
                if base_phase(r, other_by_id) in CYCLE_ORDER
            ):
                raise AppException(
                    code="PHASE_MOVED_ON",
                    message=f"The cycle has moved past {phase}, so this approval can no longer be changed.",
                    status_code=409,
                )
        last.status = ACTIVE
        last.concluded_time = None
        last.concluded_by = None
        self._event(
            cc.config_control_id, last, "reopened", "Approval reopened to change the verdict.", actor_id
        )
        await self.db.flush()
        return True

    async def on_submitted(self, cc: ConfigControl, actor_id: int, note: str | None) -> None:
        run = await self.current_run(cc.config_control_id)
        if run is not None and run.status == ACTIVE:
            self._event(cc.config_control_id, run, "submitted", note, actor_id)

    async def on_verdict(
        self, cc: ConfigControl, verdict: str, actor_id: int, note: str | None
    ) -> bool:
        """Log the reviewer's verdict on the current run; on approval, move the
        control on. Returns True when the review row was cleared for a new run."""
        run = await self.current_run(cc.config_control_id)
        if run is None or run.status != ACTIVE:
            return False
        self._event(cc.config_control_id, run, verdict, note, actor_id)
        if verdict != APPROVED:
            return False

        now = int(time.time())
        run.status = APPROVED
        run.concluded_time = now
        run.concluded_by = actor_id
        runs = await self.runs(cc.config_control_id)
        ctrl = await self.db.get(ControlRepository, cc.control_id)
        upcoming = self._next_phase(run, runs, ctrl.frequency if ctrl else None)
        if upcoming is None:
            self._event(cc.config_control_id, None, "completed", None, actor_id, now)
            await self.db.flush()
            await self._release(cc.cycle_id, actor_id)
            return False
        # The cycle moves in step: the next phase opens for this control only
        # once every control has cleared the phase the cycle is in.
        opened = await self._release(cc.cycle_id, actor_id)
        if cc.config_control_id in opened:
            return True
        cycle_now = await self.cycle_phase(cc.cycle_id)
        self._event(
            cc.config_control_id,
            None,
            "waiting",
            f"{upcoming} opens once every control has cleared {cycle_now}.",
            actor_id,
            now,
            {"next": upcoming, "cycle_phase": cycle_now},
        )
        await self.db.flush()
        return False

    async def conclude_failed(
        self, cc: ConfigControl, reason: str, actor_id: int
    ) -> ControlPhaseRun:
        """Close the current run as failed and open its remediation round."""
        reason = (reason or "").strip()
        if not reason:
            raise AppException(
                code="REASON_REQUIRED",
                message="Say why this phase failed before starting remediation.",
                status_code=422,
            )
        run = await self._active(cc)
        if await with_reviewer(self.db, cc):
            raise AppException(
                code="WITH_REVIEWER",
                message="This phase is with the reviewer. Wait for the verdict first.",
                status_code=409,
            )
        if not await self.has_exception(cc, run):
            raise AppException(
                code="NO_EXCEPTION",
                message="No exception has been recorded in this phase's testing.",
                status_code=409,
            )

        now = int(time.time())
        run.status = FAILED
        run.failure_reason = reason
        run.concluded_time = now
        run.concluded_by = actor_id
        self._event(cc.config_control_id, run, "failed", reason, actor_id, now)

        runs = await self.runs(cc.config_control_id)
        original = (
            next((r for r in runs if r.phase_run_id == run.remediates_run_id), run)
            if run.phase == RM
            else run
        )
        rounds = sum(
            1 for r in runs if r.phase == RM and r.remediates_run_id == original.phase_run_id
        )
        remediation = await self._start(cc, RM, original, rounds + 1, actor_id)
        await self._clear_review(cc.config_control_id)
        await self._store(cc)
        return remediation

    async def override_size(
        self,
        cc: ConfigControl,
        phase_run_id: int,
        size: int,
        reason: str,
        actor_id: int,
    ) -> ControlPhaseRun:
        """Set the current run's sample count by hand, and redraw its samples.

        Not for DE, which always tests one. A count larger than the run can
        draw is refused without saying what the limit is.
        """
        run = await self.run(cc.config_control_id, phase_run_id)
        if run.status != ACTIVE:
            raise AppException(
                code="PHASE_CONCLUDED",
                message="This phase has been concluded, so its sample count is fixed.",
                status_code=409,
            )
        if run.phase == DE:
            raise AppException(
                code="DE_FIXED",
                message="Design effectiveness always tests one sample.",
                status_code=422,
            )
        reason = (reason or "").strip()
        if not reason:
            raise AppException(
                code="REASON_REQUIRED",
                message="Give a reason for changing the sample count.",
                status_code=422,
            )
        if size < 1:
            raise AppException(
                code="SAMPLE_SIZE_INVALID",
                message="The sample count must be at least 1.",
                status_code=422,
            )
        if await with_reviewer(self.db, cc):
            raise AppException(
                code="WITH_REVIEWER",
                message="This phase is with the reviewer, so its sample count cannot change.",
                status_code=409,
            )

        ctrl = await self.db.get(ControlRepository, cc.control_id)
        payload = load_phased_output(ctrl.control_number, cc.entity_code)
        population = build_samples(payload) if payload else []
        runs = await self.runs(cc.config_control_id)
        eligible, _ = self._eligible(run, runs, ctrl, cc, population)
        if size > len(eligible):
            raise AppException(
                code="SAMPLE_SIZE_TOO_LARGE", message=TOO_LARGE_MESSAGE, status_code=422
            )

        previous = effective_size(run)
        now = int(time.time())
        run.override_size = size
        run.override_reason = reason
        run.override_by = actor_id
        run.override_time = now
        run.selected_samples = None
        self._event(
            cc.config_control_id,
            run,
            "overridden",
            reason,
            actor_id,
            now,
            {"from": previous, "to": size, "matrix_value": run.matrix_value},
        )
        await self.db.flush()
        await self._store(cc)
        return run

    async def _redraws(self, run: ControlPhaseRun) -> tuple[int, set[int]]:
        """How often the run's samples were redrawn, and every sample it held."""
        events = (
            (
                await self.db.execute(
                    select(ControlPhaseEvent).where(
                        ControlPhaseEvent.phase_run_id == run.phase_run_id,
                        ControlPhaseEvent.kind == "redrawn",
                    )
                )
            )
            .scalars()
            .all()
        )
        held = {int(n) for e in events for n in ((e.detail or {}).get("from") or [])}
        return len(events), held

    async def redraw(self, cc: ConfigControl, actor_id: int) -> ControlPhaseRun:
        """Draw the current run's samples again — the same count (the phase's
        matrix size, or the tester's override), other samples from the same
        window, never one an earlier run used."""
        run = await self._active(cc)
        if await with_reviewer(self.db, cc):
            raise AppException(
                code="WITH_REVIEWER",
                message="This phase is with the reviewer, so its samples cannot change.",
                status_code=409,
            )
        before = list(run.selected_samples or [])
        now = int(time.time())
        self._event(
            cc.config_control_id,
            run,
            "redrawn",
            "Testing configuration re-run.",
            actor_id,
            now,
            {"from": before},
        )
        await self.db.flush()
        run.selected_samples = None
        await self.db.flush()
        await self._store(cc)
        await self.db.refresh(run)
        self._event(
            cc.config_control_id,
            run,
            "redrawn_to",
            None,
            actor_id,
            now,
            {"from": before, "to": list(run.selected_samples or [])},
        )
        await self.db.flush()
        return run

    async def mark_computed(self, cc: ConfigControl, phase_run_id: int, computed: bool) -> None:
        """Record (or clear) that the tester has computed this run's count."""
        run = await self.run(cc.config_control_id, phase_run_id)
        run.size_computed_time = int(time.time()) if computed else None
        await self.db.flush()

    async def reset_size(
        self, cc: ConfigControl, phase_run_id: int, actor_id: int
    ) -> ControlPhaseRun:
        """Drop the tester's count and go back to the sampling matrix's.

        The run's samples are redrawn at the matrix size. Refused on the same
        grounds as an override: DE, a concluded phase, or one with the reviewer.
        """
        run = await self.run(cc.config_control_id, phase_run_id)
        if run.status != ACTIVE:
            raise AppException(
                code="PHASE_CONCLUDED",
                message="This phase has been concluded, so its sample count is fixed.",
                status_code=409,
            )
        if run.phase == DE:
            raise AppException(
                code="DE_FIXED",
                message="Design effectiveness always tests one sample.",
                status_code=422,
            )
        if await with_reviewer(self.db, cc):
            raise AppException(
                code="WITH_REVIEWER",
                message="This phase is with the reviewer, so its sample count cannot change.",
                status_code=409,
            )
        if not run.override_size:
            return run

        previous = effective_size(run)
        now = int(time.time())
        run.override_size = None
        run.override_reason = None
        run.override_by = None
        run.override_time = None
        run.selected_samples = None
        self._event(
            cc.config_control_id,
            run,
            "reset_to_matrix",
            "Sample count reset to the sampling matrix.",
            actor_id,
            now,
            {"from": previous, "to": effective_size(run), "matrix_value": run.matrix_value},
        )
        await self.db.flush()
        await self._store(cc)
        return run

    async def has_exception(self, cc: ConfigControl, run: ControlPhaseRun) -> bool:
        results = await self.results(cc, [run])
        return any(v in EXCEPTION_STATUSES for v in results.get(run.phase_run_id, {}).values())

    async def results(
        self, cc: ConfigControl, runs: list[ControlPhaseRun]
    ) -> dict[int, dict[int, str]]:
        """Each run's sample results: the latest logged run, overridden by a
        tester's judgement, then by a reviewer's changed outcome."""
        wanted = {n for r in runs for n in (r.selected_samples or [])}
        if not wanted:
            return {}
        logs = (
            await self.db.execute(
                select(TestLog.sample_no, TestLog.status, TestLog.log_date)
                .where(
                    TestLog.cycle_id == cc.cycle_id,
                    TestLog.control_id == cc.control_id,
                    TestLog.source == "sample",
                    TestLog.sample_no.in_(wanted),
                )
                .order_by(TestLog.log_date, TestLog.log_id)
            )
        ).all()
        # Logs outlive an attachment (they are keyed by control and cycle), so
        # a run counts only what was run after it started — a control detached
        # and attached again starts untested.
        opened = min((r.started_time for r in runs if r.selected_samples), default=0)
        # A control returned by the reviewer is tested afresh: its round counts
        # only runs made after the return.
        returned_at = (
            await self.db.execute(
                select(func.max(ControlReviewEvent.event_time)).where(
                    ControlReviewEvent.config_control_id == cc.config_control_id,
                    ControlReviewEvent.to_status == RETURNED,
                )
            )
        ).scalar_one_or_none() or 0
        latest: dict[int, str] = {}
        when: dict[int, int] = {}
        for no, status, at in logs:
            if at >= opened:
                latest[no] = (status or "").upper()
                when[no] = at
        judged = (
            await self.db.execute(
                select(SampleJudgement.sample_no, SampleJudgement.result).where(
                    SampleJudgement.config_control_id == cc.config_control_id,
                    SampleJudgement.sample_no.in_(wanted),
                )
            )
        ).all()
        for no, result in judged:
            if no in latest:
                latest[no] = (result or "").upper()
        # The reviewer's outcome, where they changed it, is the last word.
        from app.services.sample_review_service import SampleReviewService

        for no, result in (
            await SampleReviewService(self.db).results_for(cc.config_control_id)
        ).items():
            if no in latest:
                latest[no] = (result or "").upper()
        return {
            r.phase_run_id: {
                n: latest[n]
                for n in (r.selected_samples or [])
                if n in latest
                and when.get(n, 0)
                >= max(r.started_time, returned_at if returned_at >= r.started_time else 0)
            }
            for r in runs
        }

    async def _cycle_controls(self, cycle_id: int) -> list[ConfigControl]:
        return list(
            (
                await self.db.execute(
                    select(ConfigControl)
                    .where(ConfigControl.cycle_id == cycle_id)
                    .order_by(ConfigControl.config_control_id)
                )
            )
            .scalars()
            .all()
        )

    async def cycle_phase(self, cycle_id: int) -> str | None:
        """The phase the cycle is in: the earliest phase any attached control
        still has to clear. None once every control has cleared every phase."""
        needed: list[str] = []
        for cc in await self._cycle_controls(cycle_id):
            runs = await self.runs(cc.config_control_id)
            if not runs:
                continue
            ctrl = await self.db.get(ControlRepository, cc.control_id)
            nxt = first_needed(phase_path(ctrl.frequency if ctrl else None), runs)
            if nxt:
                needed.append(nxt)
        return min(needed, key=CYCLE_ORDER.index) if needed else None

    async def _release(self, cycle_id: int, actor_id: int | None) -> set[int]:
        """Open the cycle's phase for every control waiting on it. Returns the
        controls whose phase was opened."""
        await self.db.flush()
        current = await self.cycle_phase(cycle_id)
        opened: set[int] = set()
        if current is None:
            return opened
        for cc in await self._cycle_controls(cycle_id):
            runs = await self.runs(cc.config_control_id)
            if not runs or any(r.status == ACTIVE for r in runs):
                continue
            ctrl = await self.db.get(ControlRepository, cc.control_id)
            if first_needed(phase_path(ctrl.frequency if ctrl else None), runs) != current:
                continue
            await self._start(cc, current, None, 1, actor_id)
            await self._clear_review(cc.config_control_id)
            await self._store(cc)
            opened.add(cc.config_control_id)
        return opened

    async def reset_cycle(self, cycle_id: int) -> None:
        """Start every control of a phased cycle again from DE."""
        cycle = await self.db.get(ReviewCycle, cycle_id)
        if not phased(cycle):
            return
        ccs = (
            (await self.db.execute(select(ConfigControl).where(ConfigControl.cycle_id == cycle_id)))
            .scalars()
            .all()
        )
        ids = [cc.config_control_id for cc in ccs]
        if not ids:
            return
        await self.db.execute(
            delete(ControlPhaseEvent).where(ControlPhaseEvent.config_control_id.in_(ids))
        )
        await self.db.execute(
            delete(ControlPhaseRun).where(ControlPhaseRun.config_control_id.in_(ids))
        )
        await self.db.execute(
            delete(ControlReviewStatus).where(ControlReviewStatus.config_control_id.in_(ids))
        )
        await self.db.flush()
        for cc in ccs:
            await self._store(cc)

    # ------------------------------------------------------------ overview

    async def cycle_phases(self, cycle_id: int) -> list[dict[str, Any]]:
        """Every attached control's phase path, runs, results and history."""
        cycle = await self.db.get(ReviewCycle, cycle_id)
        if not phased(cycle):
            return []
        ccs = (
            (
                await self.db.execute(
                    select(ConfigControl)
                    .where(ConfigControl.cycle_id == cycle_id)
                    .options(selectinload(ConfigControl.control))
                    .order_by(ConfigControl.config_control_id)
                )
            )
            .scalars()
            .all()
        )
        out = []
        for cc in ccs:
            out.append(await self.control_phases(cc, cycle))
        return out

    async def control_phases(self, cc: ConfigControl, cycle: ReviewCycle) -> dict[str, Any]:
        ctrl = await self.db.get(ControlRepository, cc.control_id)
        runs = await self.runs(cc.config_control_id)
        by_id = {r.phase_run_id: r for r in runs}
        results = await self.results(cc, runs)
        events = (
            (
                await self.db.execute(
                    select(ControlPhaseEvent)
                    .where(ControlPhaseEvent.config_control_id == cc.config_control_id)
                    .options(selectinload(ControlPhaseEvent.actor))
                    .order_by(ControlPhaseEvent.event_time, ControlPhaseEvent.event_id)
                )
            )
            .scalars()
            .all()
        )
        frequency = ctrl.frequency if ctrl else None
        path = phase_path(frequency)
        active = [r for r in runs if r.status == ACTIVE]
        current = active[-1] if active else None
        needed = first_needed(path, runs) if runs else None
        complete = bool(runs) and needed is None
        # Cleared its phase and waiting for the rest of the cycle to catch up.
        waiting_for = needed if runs and current is None and needed else None
        due = cycle.due_date or cycle.end_date or cycle.start_date

        def run_out(r: ControlPhaseRun) -> dict[str, Any]:
            phase = base_phase(r, by_id)
            window = EVIDENCE_WINDOWS.get(phase)
            return {
                "phase_run_id": r.phase_run_id,
                "phase": r.phase,
                "base_phase": phase,
                "label": run_label(r, by_id),
                "name": PHASE_NAMES.get(r.phase, r.phase),
                "remediates_run_id": r.remediates_run_id,
                "attempt": r.attempt,
                "status": r.status,
                "matrix_value": r.matrix_value,
                "size_source": r.size_source,
                "sample_size": effective_size(r),
                "override_size": r.override_size,
                "override_reason": r.override_reason,
                "override_by_name": r.overrider.user_name if r.overrider else None,
                "override_time": r.override_time,
                "size_computed_time": r.size_computed_time,
                "selected_samples": r.selected_samples or [],
                "results": {str(k): v for k, v in results.get(r.phase_run_id, {}).items()},
                "failure_reason": r.failure_reason,
                "started_time": r.started_time,
                "concluded_time": r.concluded_time,
                "concluded_by_name": r.concluder.user_name if r.concluder else None,
                "window_start": window[0].isoformat() if window else None,
                "window_end": window[1].isoformat() if window else None,
            }

        return {
            "config_control_id": cc.config_control_id,
            "control_number": ctrl.control_number if ctrl else None,
            "frequency": frequency,
            "demo_changes": demo_changes_for(ctrl.control_number, cc.entity_code) if ctrl else {},
            "risk_level": ctrl.risk_level if ctrl else None,
            "path": path,
            "current_run_id": current.phase_run_id if current else None,
            "current_phase": base_phase(current, by_id) if current else None,
            "in_remediation": bool(current and current.phase == RM),
            "complete": complete,
            "waiting_for": waiting_for,
            "runs": [run_out(r) for r in runs],
            "planned": {
                p: dict(
                    zip(("start", "end"), planned_window(p, cycle.start_date, due), strict=True)
                )
                for p in path
            },
            "windows": {
                p: {
                    "start": EVIDENCE_WINDOWS[p][0].isoformat(),
                    "end": EVIDENCE_WINDOWS[p][1].isoformat(),
                }
                for p in path
            },
            "events": [
                {
                    "phase_run_id": e.phase_run_id,
                    "label": (
                        run_label(by_id[e.phase_run_id], by_id) if e.phase_run_id in by_id else None
                    ),
                    "kind": e.kind,
                    "note": e.note,
                    "detail": e.detail,
                    "actor_name": e.actor.user_name if e.actor else None,
                    "event_time": e.event_time,
                }
                for e in events
            ],
        }


def period_under_review() -> dict[str, str]:
    return {"start": PERIOD_UNDER_REVIEW[0].isoformat(), "end": PERIOD_UNDER_REVIEW[1].isoformat()}

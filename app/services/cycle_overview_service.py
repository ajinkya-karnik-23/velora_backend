"""Summary of every review cycle of a client, for the Review Cycles screen.

Results are read from what was recorded, not from client-side run state: a
sample counts as executed once its run is in the audit trail (test_logs,
source "sample"), and its result is the tester's judgement where one exists,
else the result logged for that run. Samples are the cycle's own — a
matrix-sampled cycle counts only its selection.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.control_review import ControlReviewEvent, ControlReviewStatus
from app.models.engagement_team import EngagementTeam
from app.models.evidence_file import EvidenceFile
from app.models.review_cycle import ReviewCycle
from app.models.test_log import TestLog
from app.repositories.config_control_repo import ConfigControlRepo
from app.schemas.cycle_overview import (
    ActivityDayOut,
    ControlProfileOut,
    ControlResultOut,
    CycleOverviewOut,
    PersonOut,
    StakeholderOut,
    TesterOut,
)
from app.services.config_control_service import ConfigControlService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

REVIEWER_STATES = {"submitted_for_review", "under_review", "reviewed"}


def _bucket(result: str | None) -> str:
    value = (result or "").strip().upper()
    if value in ("PASS", "PASSED"):
        return "passed"
    if value in ("FAIL", "FAILED", "EVIDENCE_EXCEPTION"):
        return "exceptions"
    return "not_concluded"


def _day(epoch: int) -> str:
    # The engagement's working day, in the server's local time — a UTC day
    # would fold an evening's runs into the next morning's.
    return datetime.fromtimestamp(epoch).astimezone().date().isoformat()


def load_demo_activity(path: Path, cycle: ReviewCycle) -> dict[str, Any] | None:
    """The demo team/activity entry matching this cycle, if one is configured."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    for entry in payload.get("cycles") or []:
        match = entry.get("match") or {}
        if all(str(getattr(cycle, k, None)) == str(v) for k, v in match.items()):
            return entry
    return None


def load_directory(path: Path) -> dict[str, dict[str, Any]]:
    """Contact details by name, from the activity file's 'directory'."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    directory = payload.get("directory")
    return directory if isinstance(directory, dict) else {}


def _contact(directory: dict[str, dict[str, Any]], name: str, role: str | None = None) -> PersonOut:
    entry = directory.get(name) or {}
    return PersonOut(
        name=name,
        role=role,
        email=entry.get("email"),
        title=entry.get("title"),
        organisation=entry.get("organisation"),
        location=entry.get("location"),
    )


# Who a control definition names, and as what — in the order shown.
_STAKEHOLDER_FIELDS = (
    ("Business Process Owner (BPO)", "Business process owner"),
    ("Entity CFO", "Entity CFO"),
    ("Control Owner", "Control owner"),
    ("PBC Owners", "PBC owner"),
    ("Control Executor", "Control executor"),
)


def _stakeholders(
    definitions: list[dict[str, Any]], directory: dict[str, dict[str, Any]]
) -> list[StakeholderOut]:
    """Client-side people named across the cycle's controls, with their roles."""
    people: dict[str, StakeholderOut] = {}

    def add(name: Any, role: str, control: str) -> None:
        name = str(name or "").strip()
        if not name:
            return
        person = people.get(name)
        if person is None:
            person = StakeholderOut(**_contact(directory, name).model_dump())
            people[name] = person
        if role not in person.roles:
            person.roles.append(role)
        if control and control not in person.controls:
            person.controls.append(control)

    for d in definitions:
        rcm = d.get("rcm_details") or {}
        control = str((d.get("control_details") or {}).get("Control No") or "").strip()
        for field, role in _STAKEHOLDER_FIELDS:
            add(rcm.get(field), role, control)
        for name in rcm.get("Additional Owners") or []:
            add(name, "Additional owner", control)
    # The most involved first.
    return sorted(people.values(), key=lambda p: (-len(p.roles), -len(p.controls), p.name))


def _profile(definitions: list[dict[str, Any]]) -> ControlProfileOut:
    process: Counter[str] = Counter()
    nature: Counter[str] = Counter()
    risk: Counter[str] = Counter()
    frequency: Counter[str] = Counter()
    key = ipe = 0
    for d in definitions:
        rcm = d.get("rcm_details") or {}
        details = d.get("control_details") or {}
        process[str(rcm.get("Process Name") or "Unspecified")] += 1
        nature[str(rcm.get("Control Nature") or "Unspecified")] += 1
        risk[str(rcm.get("Risk Level") or "Unspecified")] += 1
        frequency[str(rcm.get("Frequency") or "Unspecified")] += 1
        key += 1 if str(rcm.get("Significance") or "").strip().lower() == "key" else 0
        ipe += 1 if str(details.get("IPE control") or "").strip().lower() == "yes" else 0
    return ControlProfileOut(
        process=dict(process.most_common()),
        nature=dict(nature.most_common()),
        risk=dict(risk.most_common()),
        frequency=dict(frequency.most_common()),
        key_controls=key,
        ipe_controls=ipe,
    )


async def _count(db: AsyncSession, stmt) -> int:  # noqa: ANN001
    return (await db.execute(stmt)).scalar() or 0


async def cycle_overview(db: AsyncSession, cycle: ReviewCycle) -> CycleOverviewOut:
    service = ConfigControlService(db)
    ccs = await ConfigControlRepo(db).get_cycle_controls(cycle.cycle_id)

    # Latest recorded run per (control, sample).
    runs: dict[tuple[int | None, int], tuple[int, str]] = {}
    logs = (
        (
            await db.execute(
                select(TestLog)
                .where(
                    TestLog.cycle_id == cycle.cycle_id,
                    TestLog.source == "sample",
                    TestLog.sample_no.is_not(None),
                )
                .options(selectinload(TestLog.changer))
            )
        )
        .scalars()
        .all()
    )
    # A run counts for a control only once it is attached: logs outlive a
    # detach, and a re-attached control starts with a clean record.
    attached_at = {cc.control_id: cc.created_time or 0 for cc in ccs}
    logs = [log for log in logs if log.log_date >= attached_at.get(log.control_id, 0)]
    day_runs: Counter[str] = Counter()
    actor_runs: Counter[str] = Counter()
    for log in logs:
        day_runs[_day(log.log_date)] += 1
        actor_runs[log.changer.user_name if log.changer else "Unknown"] += 1
    for control_id, sample_no, status, log_date in (
        (log.control_id, log.sample_no, log.status, log.log_date) for log in logs
    ):
        key = (control_id, sample_no)
        if key not in runs or log_date >= runs[key][0]:
            runs[key] = (log_date, status)

    reviews = (
        {
            row.config_control_id: row.status
            for row in (
                await db.execute(
                    select(ControlReviewStatus).where(
                        ControlReviewStatus.config_control_id.in_(
                            [cc.config_control_id for cc in ccs]
                        )
                    )
                )
            ).scalars()
        }
        if ccs
        else {}
    )

    # A returned control is tested afresh: only runs after the return count.
    returned_at: dict[int, int] = {}
    if ccs:
        rows = await db.execute(
            select(ControlReviewEvent.config_control_id, func.max(ControlReviewEvent.event_time))
            .where(
                ControlReviewEvent.config_control_id.in_([cc.config_control_id for cc in ccs]),
                ControlReviewEvent.to_status == "returned_to_tester",
            )
            .group_by(ControlReviewEvent.config_control_id)
        )
        returned_at = {int(cc_id): int(t) for cc_id, t in rows.all()}
    out = CycleOverviewOut(cycle_id=cycle.cycle_id, controls=len(ccs), tests_run=len(logs))
    root_causes: dict[str, int] = {}
    for cc in ccs:
        output = await service.get_test_output(cc.config_control_id)
        row = ControlResultOut(
            config_control_id=cc.config_control_id,
            control_number=cc.control.control_number if cc.control else None,
            control_name=cc.control.control_name if cc.control else None,
            samples=len(output.samples),
            not_tested_reason=output.not_tested_reason,
            untested_types=len(output.untested_types),
            review_status=reviews.get(cc.config_control_id),
        )
        # Run logs outlive an attachment; only runs made since this control was
        # attached describe it (a detached and re-attached control starts afresh).
        since = max(cc.created_time or 0, returned_at.get(cc.config_control_id, 0))
        for i, sample in enumerate(output.samples):
            no = sample.sample_no if isinstance(sample.sample_no, int) else i + 1
            run = runs.get((cc.control_id, no))
            if run is None or run[0] < since:
                continue
            row.executed += 1
            judgement = sample.judgement
            review = sample.review
            bucket = _bucket(
                review.result
                if review and review.result
                else judgement.result if judgement else run[1]
            )
            setattr(row, bucket, getattr(row, bucket) + 1)
            if bucket != "passed" and judgement and judgement.root_cause_label:
                label = judgement.root_cause_label
                root_causes[label] = root_causes.get(label, 0) + 1
            out.last_run_time = max(out.last_run_time or 0, run[0])

        out.samples += row.samples
        out.population += output.population_count or row.samples
        out.controls_tested += 1 if row.executed else 0
        out.executed += row.executed
        out.passed += row.passed
        out.exceptions += row.exceptions
        out.not_concluded += row.not_concluded
        out.controls_not_tested += 1 if row.not_tested_reason else 0
        out.sample_types_not_tested += row.untested_types
        out.approved += 1 if row.review_status == "approved" else 0
        out.with_reviewer += 1 if row.review_status in REVIEWER_STATES else 0
        out.control_results.append(row)

    out.root_causes = root_causes
    definitions = [
        cc.entity_detail_json or (cc.control.source_json if cc.control else None) or {}
        for cc in ccs
    ]
    out.profile = _profile(definitions)

    # People and activity: recorded by default; the demo file, when it has an
    # entry for this cycle, supplies the team and testers (and, optionally,
    # the days) instead.
    members = (
        (
            await db.execute(
                select(EngagementTeam)
                .where(EngagementTeam.cycle_id == cycle.cycle_id)
                .options(selectinload(EngagementTeam.user))
            )
        )
        .scalars()
        .all()
    )
    out.team = [
        PersonOut(name=m.user.user_name if m.user else "Unknown", role=m.team_role) for m in members
    ]
    out.testers = [TesterOut(name=name, runs=n) for name, n in actor_runs.most_common()]
    reviewers = (
        (
            await db.execute(
                select(ControlReviewStatus)
                .where(
                    ControlReviewStatus.config_control_id.in_([cc.config_control_id for cc in ccs])
                )
                .options(selectinload(ControlReviewStatus.reviewer))
            )
        )
        .scalars()
        .all()
        if ccs
        else []
    )
    for r in reviewers:
        if r.status == "returned_to_tester":
            out.returned += 1
        else:
            out.submitted += 1
        if r.submitted_time:
            out.last_submitted_time = max(out.last_submitted_time or 0, r.submitted_time)
        if r.reviewed_time:
            out.last_reviewed_time = max(out.last_reviewed_time or 0, r.reviewed_time)
    out.lead = cycle.lead.user_name if cycle.lead else None
    reviewer_names = Counter(r.reviewer.user_name for r in reviewers if r.reviewer)
    out.reviewer = reviewer_names.most_common(1)[0][0] if reviewer_names else None
    out.activity = [ActivityDayOut(date=d, runs=n) for d, n in sorted(day_runs.items())]

    demo = load_demo_activity(Path(settings.CYCLE_ACTIVITY_PATH), cycle)
    if demo:
        out.demo_activity = True
        out.team = [PersonOut(**p) for p in demo.get("team") or []] or out.team
        out.reviewer = demo.get("reviewer") or out.reviewer
        out.lead = demo.get("lead") or out.lead
        # Illustrative run activity only for the locked demo cycle; a working
        # cycle shows the runs it actually recorded, so its figures move with
        # testing (and read zero after a reset).
        if demo.get("activity") and cycle.is_locked:
            out.activity = [
                ActivityDayOut(date=d, runs=int(n)) for d, n in sorted(demo["activity"].items())
            ]
            out.tests_run = sum(a.runs for a in out.activity)
        shares = demo.get("testers") or []
        if shares:
            # Split the samples actually executed by the configured shares;
            # rounding drift lands on the primary tester.
            split = [int(out.executed * float(t.get("share", 0))) for t in shares]
            split[0] += out.executed - sum(split)
            out.testers = [
                TesterOut(name=t["name"], runs=n) for t, n in zip(shares, split, strict=True)
            ]
    out.evidence_files = await _count(
        db,
        select(func.count(EvidenceFile.evidence_id)).where(EvidenceFile.cycle_id == cycle.cycle_id),
    )
    out.team_members = await _count(
        db,
        select(func.count(EngagementTeam.engagement_team_id)).where(
            EngagementTeam.cycle_id == cycle.cycle_id
        ),
    )
    # Contact details for everyone the overview names.
    directory = load_directory(Path(settings.CYCLE_ACTIVITY_PATH))
    out.team = [
        PersonOut(
            **{
                **_contact(directory, p.name, p.role).model_dump(),
                **{k: v for k, v in p.model_dump().items() if v},
            }
        )
        for p in out.team
    ]
    out.lead_contact = _contact(directory, out.lead, "Cycle lead") if out.lead else None
    out.reviewer_contact = _contact(directory, out.reviewer, "Reviewer") if out.reviewer else None
    out.stakeholders = _stakeholders(definitions, directory)
    return out


async def client_overview(db: AsyncSession, client_id: int) -> list[CycleOverviewOut]:
    cycles = (
        (
            await db.execute(
                select(ReviewCycle)
                .where(ReviewCycle.client_id == client_id)
                .options(selectinload(ReviewCycle.lead))
                .order_by(ReviewCycle.cycle_id)
            )
        )
        .scalars()
        .all()
    )
    return [await cycle_overview(db, cycle) for cycle in cycles]

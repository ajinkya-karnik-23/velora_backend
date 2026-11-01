"""The CRP rows for a cycle's phases, read from the platform.

Each control's row in a phase sheet describes the phase's final round — the
phase itself, or its last remediation round — and checks the TWP the platform
builds for it against the template's review checklist (Introductory Page):

- Documents downloaded: every sample of the round has evidence attached.
- Test performed: the round was handed to the reviewer (it is approved).
- Test result: Effective, Ineffective (the phase found exceptions, even if
  remediation later passed) or No population.
- All mandatory fields completed (checklist 2, 4, 8, 9): control number,
  frequency, population period, sample count and basis, samples with document
  references, tester.
- IPE section (checklist 5): Not applicable without an IPE; otherwise the
  TWP's IPE fields are filled.
- Preparer identified (checklist 10): the TWP's sign-off names the tester and
  the hand-over date.
- Appropriate testing method and number of samples (checklist 3, 6): every
  sample the matrix (or the override) called for was tested, no sample type
  was left out in OE (DE, RF and YE take fixed small counts), and RF reads its
  own matrix column.
- Needs Action follow-up: "Addressed and corrected" where the reviewer
  returned the round and it was then approved.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.models.config_control import ConfigControl
from app.models.control_repository import ControlRepository
from app.services.crp_template import (
    ADDRESSED,
    DOCS_COMPLETE,
    DOCS_INCOMPLETE,
    DOCS_NOT_PROVIDED,
    EFFECTIVE,
    INEFFECTIVE,
    NEEDS_ACTION,
    NO_POPULATION,
    NOT_APPLICABLE,
    PASS,
    PHASE_SHEETS,
    READY_FOR_REVIEW,
    SELECT_SPACED,
    CrpRow,
    template_frequency,
)
from app.services.twp_builder import has_ipe
from app.services.twp_context import twp_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# How the run's trail reads in the notes.
EVENT_WORDS = {
    "started": "Round opened",
    "testing_started": "Testing started",
    "redrawn_to": "Samples redrawn",
    "overridden": "Sample count changed",
    "reset_to_matrix": "Sample count reset to the matrix",
    "submitted": "Submitted for review",
    "under_review": "Review started",
    "reviewed": "Reviewed",
    "returned_to_tester": "Returned to the tester",
    "approved": "Approved",
    "failed": "Failed — remediation raised",
}
VALIDATION_CHARS = 420


def _comments_file() -> dict[str, Any]:
    path = Path(settings.CRP_COMMENTS_PATH)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload.get("controls") or {} if isinstance(payload, dict) else {}


def comment_for(control_number: str, phase: str, remediated: bool) -> dict[str, str]:
    """The tester's and reviewer's comment on a control's phase, as written in
    misc/crp_comments.json (CRP_COMMENTS_PATH); its "remediated" variant when
    the phase failed and was remediated. Empty when none is written."""
    entry = (_comments_file().get(control_number.strip()) or {}).get(phase) or {}
    if remediated and isinstance(entry.get("remediated"), dict):
        entry = entry["remediated"]
    return {k: str(v) for k, v in entry.items() if k in ("tester", "reviewer") and v}


def _when(epoch: int | None, time: bool = False) -> str:
    if not epoch:
        return "—"
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%d %b %Y %H:%M" if time else "%d %b %Y")


def _trail(events: list[dict[str, Any]], run_ids: set[int]) -> list[str]:
    lines = []
    for e in events:
        if e.get("phase_run_id") not in run_ids or e["kind"] not in EVENT_WORDS:
            continue
        line = f"{_when(e['event_time'], True)} · {EVENT_WORDS[e['kind']]}"
        if e.get("label") and e["kind"] in ("started", "failed", "approved"):
            line += f" ({e['label']})"
        if e.get("actor_name"):
            line += f" — {e['actor_name']}"
        if e.get("note") and e["kind"] not in ("started",):
            line += f': "{e["note"]}"'
        lines.append(line)
    return lines


def _sample_lines(ctx: Any, label: str, results: dict[str, str]) -> list[str]:
    """Each sample's outcome, the tool's validation, and any tester or
    reviewer word on it."""
    lines = [f"{label}:"]
    for smp in ctx.samples or []:
        no = smp.get("sample_no")
        ran = str(no) in results
        result = str(smp.get("result") or "").upper() if ran else "NOT RUN YET"
        docs = ", ".join(ref for ref, _ in ctx.documents.get(no, [])) if isinstance(no, int) else ""
        head = f"• Sample #{no} — {result}" + (f" [{docs}]" if docs else "")
        lines.append(head)
        validation = (smp.get("validation") or "").strip().replace("\n", " ") if ran else ""
        if validation:
            cut = validation[:VALIDATION_CHARS]
            lines.append("  " + cut + ("…" if len(validation) > VALIDATION_CHARS else ""))
        judgement = smp.get("judgement") or {}
        if judgement:
            verb = "confirmed" if judgement.get("action") == "accepted" else "changed to"
            lines.append(
                f"  Tester {verb} {judgement.get('result') or result}"
                + (f": {judgement['conclusion']}" if judgement.get("conclusion") else "")
                + (
                    f" (root cause: {judgement['root_cause_category']})"
                    if judgement.get("root_cause_category")
                    else ""
                )
            )
        review = smp.get("review") or {}
        if review and (review.get("comment") or review.get("result") or review.get("conclusion")):
            parts = []
            if review.get("result"):
                parts.append(f"outcome {review['result']}")
            if review.get("conclusion"):
                parts.append(review["conclusion"])
            if review.get("comment"):
                parts.append(f'"{review["comment"]}"')
            lines.append("  Reviewer: " + "; ".join(parts))
    return lines


def scope_notes(controls: list[dict[str, Any]], phase: str, cycle_name: str) -> list[str]:
    """What replaces the template's notes on the client's full control list."""
    on = [c for c in controls if phase in c["path"]]
    annual = [c["control_number"] for c in controls if "YE" in c["path"]]
    lines = [
        f"Note:\nThis CRP is prepared by Velora for the review cycle {cycle_name}. "
        f"{len(on)} control{'s' if len(on) != 1 else ''} "
        f"{'are' if len(on) != 1 else 'is'} in scope for this phase: "
        + ", ".join(c["control_number"] for c in on)
        + ". "
        "Each row is filled from the platform's testing, evidence and review records; "
        "hover a cell with a red corner for the detail behind it."
    ]
    if annual and phase != "YE":
        lines.append(
            f"{len(annual)} control{'s' if len(annual) != 1 else ''} "
            f"({', '.join(annual)}) {'are' if len(annual) != 1 else 'is'} annual and "
            "will also be tested in the year end phase."
        )
    return lines


def phase_complete(control: dict[str, Any], phase: str) -> bool:
    """The phase's final round is approved (or the phase is not on the path)."""
    if phase not in control["path"]:
        return True
    rounds = [r for r in control["runs"] if r["base_phase"] == phase]
    return bool(rounds) and rounds[-1]["status"] == "approved"


async def crp_rows(db: AsyncSession, controls: list[dict[str, Any]], phase: str) -> list[CrpRow]:
    """One row per control whose path includes the phase."""
    rows: list[CrpRow] = []
    for c in controls:
        if phase not in c["path"]:
            continue
        rounds = [r for r in c["runs"] if r["base_phase"] == phase]
        if not rounds:
            continue
        final, first = rounds[-1], rounds[0]
        cc = await db.get(ConfigControl, c["config_control_id"])
        ctrl = await db.get(ControlRepository, cc.control_id) if cc else None
        if cc is None or ctrl is None:
            continue
        ctx = await twp_context(db, cc, final["phase_run_id"])
        first_ctx = await twp_context(db, cc, first["phase_run_id"]) if first is not final else None
        definition = cc.entity_detail_json or ctrl.source_json or {}
        rcm = definition.get("rcm_details") or {}
        ipe = has_ipe(rcm)
        samples = ctx.samples or []
        numbers = [s.get("sample_no") for s in samples]
        with_docs = [n for n in numbers if isinstance(n, int) and ctx.documents.get(n)]
        tested = len(final["results"])
        required = final["sample_size"] or 0

        # Short issue lines, each one a reason for a Needs Action.
        issues: list[str] = []
        missing = [
            label
            for label, present in (
                ("frequency", ctrl.frequency),
                ("population period", ctx.evidence_window),
                ("sample count basis", ctx.size_basis),
                ("samples", samples),
                ("tester", ctx.tester),
            )
            if not present
        ]
        unreferenced = [n for n in numbers if n not in with_docs]
        if unreferenced:
            missing.append("doc refs for " + ", ".join(f"#{n}" for n in unreferenced))
        mandatory = PASS if not missing else NEEDS_ACTION
        if missing:
            issues.append("TWP missing " + "; ".join(missing) + ".")

        preparer = PASS if ctx.tester and ctx.submitted_time else NEEDS_ACTION
        if preparer == NEEDS_ACTION:
            issues.append("Preparer sign-off missing.")

        shortfall = tested < required or len(final["selected_samples"]) < required
        # Only OE is sized to cover the population's types. DE tests one
        # sample by rule and RF/YE take their column's small fixed count, so a
        # type they leave out is the methodology, not a gap.
        gaps = phase == "OE" and bool(ctx.untested_types)
        samples_ok = PASS if required and not shortfall and not gaps else NEEDS_ACTION
        if shortfall:
            issues.append(f"{tested}/{required} samples tested.")

        remediated = first["status"] == "failed"
        said = comment_for(ctrl.control_number, phase, remediated)
        if gaps and not said:
            issues.append("Not sampled: " + ", ".join(t["label"] for t in ctx.untested_types) + ".")

        run_ids = {r["phase_run_id"] for r in rounds}
        returns = [
            e
            for e in c["events"]
            if e["kind"] == "returned_to_tester" and e.get("phase_run_id") in run_ids
        ]
        returned = bool(returns)
        exceptions = sum(
            1
            for v in final["results"].values()
            if str(v).upper() in ("FAIL", "FAILED", "EVIDENCE_EXCEPTION")
        )

        # The comment column: the tester's and reviewer's word, then any issue.
        comments: list[str] = []
        if said.get("tester"):
            comments.append(f"Tester: {said['tester']}")
        if said.get("reviewer"):
            comments.append(f"Reviewer: {said['reviewer']}")
        for e in returns:
            comments.append(
                f"Returned {_when(e['event_time'])}"
                + (f': "{e["note"]}"' if e.get("note") else "")
                + " — corrected."
            )
        if remediated and not said:
            comments.append(f"Remediated in {final['label']}; approved.")
        for smp in samples:
            remark = (smp.get("review") or {}).get("comment")
            if remark:
                comments.append(f"Reviewer on #{smp.get('sample_no')}: {remark}")
        comments += [f"Needs Action: {i}" for i in issues]
        if not comments:
            comments.append("No action needed.")

        # Cell notes: the detail a reviewer would otherwise open the TWP for.
        doc_lines = [f"Evidence window {ctx.evidence_window or '—'}."]
        for no in numbers:
            docs = ctx.documents.get(no, []) if isinstance(no, int) else []
            doc_lines.append(
                f"• Sample #{no}: "
                + (
                    "; ".join(f"{ref} · {name}" for ref, name in docs)
                    if docs
                    else "no document attached"
                )
            )
        performed = [
            *([f"Tester: {said['tester']}"] if said.get("tester") else []),
            *([f"Reviewer: {said['reviewer']}", ""] if said.get("reviewer") else []),
            f"Round: {final['label']} · {final['name']}",
            f"Prepared by {ctx.tester or '—'} · submitted {_when(ctx.submitted_time, True)}",
            f"Reviewed by {ctx.reviewer or '—'} · concluded "
            f"{_when(ctx.phase_concluded_time or ctx.reviewed_time, True)}",
            f"Sample count: {ctx.size_basis or '—'}",
            "",
            "Trail:",
            *_trail(c["events"], run_ids),
        ]
        outcome = []
        if first_ctx is not None:
            outcome += _sample_lines(first_ctx, f"{first['label']} (failed)", first["results"])
            if first.get("failure_reason"):
                outcome.append(f"  Failure reason: {first['failure_reason']}")
            outcome.append("")
        outcome += _sample_lines(
            ctx,
            f"{final['label']} — {tested} tested, "
            f"{exceptions} exception{'s' if exceptions != 1 else ''}",
            final["results"],
        )
        notes = {"L": "\n".join(doc_lines), "N": "\n".join(performed), "P": "\n".join(outcome)}
        result = NO_POPULATION if cc.not_tested_reason else INEFFECTIVE if remediated else EFFECTIVE
        process = (definition.get("control_details") or {}).get("Business Process") or "ACIS"
        rows.append(
            CrpRow(
                control_number=ctrl.control_number,
                entity_code=cc.entity_code,
                # The template's naming, used only where no sheet lists it.
                short_name=(
                    f"BP-{process}."
                    f"{cc.entity_code}..{ctrl.control_number.split('.')[0]}..."
                    f"{ctrl.control_number}.{cc.entity_code}. {ctrl.control_name}"
                ),
                frequency=template_frequency(ctrl.frequency),
                control_type=rcm.get("Control Type") or "Manual",
                ipe="Yes" if ipe else "No",
                documents=(
                    DOCS_COMPLETE
                    if numbers and len(with_docs) == len(numbers)
                    else DOCS_INCOMPLETE if with_docs else DOCS_NOT_PROVIDED
                ),
                test_performed=READY_FOR_REVIEW if final["status"] == "approved" else SELECT_SPACED,
                test_result=result,
                tester=ctx.tester or "Please complete the section…",
                mandatory_fields=mandatory,
                ipe_section=PASS if ipe else NOT_APPLICABLE,
                preparer_identified=preparer,
                samples_appropriate=samples_ok,
                comments=comments,
                follow_up=ADDRESSED if returned else NOT_APPLICABLE,
                notes=notes,
            )
        )
    return rows


async def identity_rows(
    db: AsyncSession, controls: list[dict[str, Any]], phase: str
) -> list[CrpRow]:
    """Rows for a phase not yet complete: each control on it, by name and
    attributes only."""
    rows: list[CrpRow] = []
    for c in controls:
        if phase not in c["path"]:
            continue
        cc = await db.get(ConfigControl, c["config_control_id"])
        ctrl = await db.get(ControlRepository, cc.control_id) if cc else None
        if cc is None or ctrl is None:
            continue
        definition = cc.entity_detail_json or ctrl.source_json or {}
        rcm = definition.get("rcm_details") or {}
        process = (definition.get("control_details") or {}).get("Business Process") or "ACIS"
        rows.append(
            CrpRow(
                control_number=ctrl.control_number,
                entity_code=cc.entity_code,
                short_name=(
                    f"BP-{process}.{cc.entity_code}..{ctrl.control_number.split('.')[0]}..."
                    f"{ctrl.control_number}.{cc.entity_code}. {ctrl.control_name}"
                ),
                frequency=template_frequency(ctrl.frequency),
                control_type=rcm.get("Control Type") or "Manual",
                ipe="Yes" if has_ipe(rcm) else "No",
                documents="",
                test_performed="",
                test_result="",
                tester="",
                mandatory_fields="",
                ipe_section="",
                preparer_identified="",
                samples_appropriate="",
                identity_only=True,
            )
        )
    return rows


def sheet_phases() -> list[str]:
    """The phases the template has a sheet for, in cycle order."""
    return list(PHASE_SHEETS)

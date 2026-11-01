"""Reference numbers for supporting documents.

Every evidence file gets a reference that says where it sits in the testing:

    IA5.CA01-S03-D01   control IA5.CA01, sample 3, first document
    IA5.CA01-T12-D02   control IA5.CA01, manual test step 12, second document
    IA5.CA01-D01       evidence attached to the control as a whole

References are unique within a review cycle — the scope of a work paper —
and never reused: the document number continues from the highest one issued
for that sample, so deleting a file does not hand its reference to the next.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from app.models.control_repository import ControlRepository
from app.models.evidence_file import EvidenceFile

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_DOC_NUMBER = re.compile(r"-D(\d+)$")


def ref_prefix(
    control_number: str | None, sample_no: int | None, manual_step_id: int | None
) -> str:
    base = (control_number or "DOC").strip()
    if sample_no is not None:
        return f"{base}-S{sample_no:02d}"
    if manual_step_id is not None:
        return f"{base}-T{manual_step_id:02d}"
    return base


def next_ref(prefix: str, existing: list[str]) -> str:
    """The next reference under `prefix`, given the references already issued."""
    highest = 0
    for ref in existing:
        if not ref.startswith(f"{prefix}-D"):
            continue
        match = _DOC_NUMBER.search(ref)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-D{highest + 1:02d}"


async def assign_doc_ref(db: AsyncSession, evidence: EvidenceFile) -> str:
    """Give a newly created evidence row its reference (idempotent)."""
    if evidence.doc_ref:
        return evidence.doc_ref
    control_number = None
    if evidence.control_id is not None:
        control = await db.get(ControlRepository, evidence.control_id)
        control_number = control.control_number if control else None
    prefix = ref_prefix(control_number, evidence.sample_no, evidence.manual_step_id)
    # Auto-attach sends several files for one sample at once; without this,
    # two requests can both read "D01" as next and one fails on the unique
    # constraint. A transaction-scoped advisory lock per cycle+prefix makes
    # them take numbers one at a time (Postgres only; tests run on SQLite).
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"doc_ref:{evidence.cycle_id}:{prefix}"},
        )
    stmt = select(EvidenceFile.doc_ref).where(EvidenceFile.doc_ref.like(f"{prefix}-D%"))
    stmt = (
        stmt.where(EvidenceFile.cycle_id == evidence.cycle_id)
        if evidence.cycle_id is not None
        else stmt.where(EvidenceFile.cycle_id.is_(None))
    )
    existing = [r for r in (await db.execute(stmt)).scalars().all() if r]
    evidence.doc_ref = next_ref(prefix, existing)
    await db.flush()
    return evidence.doc_ref

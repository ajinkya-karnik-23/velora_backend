"""supporting-document reference numbers, and per-type untested samples

Revision ID: a3c5e7f9b1d2
Revises: f2b4d6e8a0c1
Create Date: 2026-10-21

Adds evidence_files.doc_ref (unique per cycle) and backfills it for existing
rows in upload order, and config_controls.untested_types for sample types a
matrix selection left without any sample.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a3c5e7f9b1d2"
down_revision = "f2b4d6e8a0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence_files", sa.Column("doc_ref", sa.String(80), nullable=True))
    op.add_column("config_controls", sa.Column("untested_types", sa.JSON(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT e.evidence_id, e.cycle_id, e.sample_no, e.manual_step_id, c.control_number "
            "FROM evidence_files e "
            "LEFT JOIN control_repository c ON c.control_id = e.control_id "
            "ORDER BY e.evidence_id"
        )
    ).fetchall()
    counters: dict[tuple, int] = {}
    for evidence_id, cycle_id, sample_no, step_id, control_number in rows:
        base = (control_number or "DOC").strip()
        if sample_no is not None:
            prefix = f"{base}-S{sample_no:02d}"
        elif step_id is not None:
            prefix = f"{base}-T{step_id:02d}"
        else:
            prefix = base
        key = (cycle_id, prefix)
        counters[key] = counters.get(key, 0) + 1
        conn.execute(
            sa.text("UPDATE evidence_files SET doc_ref = :ref WHERE evidence_id = :id"),
            {"ref": f"{prefix}-D{counters[key]:02d}", "id": evidence_id},
        )

    op.create_unique_constraint(
        "uq_evidence_files_cycle_doc_ref", "evidence_files", ["cycle_id", "doc_ref"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_evidence_files_cycle_doc_ref", "evidence_files", type_="unique")
    op.drop_column("config_controls", "untested_types")
    op.drop_column("evidence_files", "doc_ref")

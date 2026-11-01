"""Lock the reference review cycle and create its matrix-sampled counterpart.

Usage:
    python -m scripts.setup_matrix_sampling_cycle [REFERENCE_CYCLE_ID]

The reference cycle (default 16, "Q1 Sox review") keeps full-population
sampling and is locked, so it cannot be deleted or have controls removed.
A second cycle is created alongside it with the same client, entity and
dates, sampled from the sampling matrix, and every control in the client's
repository is attached to it. Prints the sampling check for the new cycle.

Idempotent — re-running finds the existing matrix cycle and only attaches
controls it is missing.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.base import *  # noqa: F401,F403 — register all models for relationship resolution
from app.db.session import async_session_maker, engine
from app.models.control_repository import ControlRepository
from app.models.review_cycle import ReviewCycle
from app.services.config_control_service import ConfigControlService

# Name given to a newly created matrix cycle; an existing one is found by its
# sampling mode, so it can be renamed freely.
DEFAULT_NAME = "SOX Review · FY2026"


async def main(reference_id: int) -> None:
    async with async_session_maker() as db:
        reference = await db.get(ReviewCycle, reference_id)
        if reference is None:
            raise SystemExit(f"Review cycle {reference_id} not found.")
        reference.is_locked = True
        reference.sampling_mode = "full_population"

        cycle = (
            (
                await db.execute(
                    select(ReviewCycle)
                    .where(
                        ReviewCycle.client_id == reference.client_id,
                        ReviewCycle.sampling_mode == "matrix",
                        ReviewCycle.cycle_id != reference_id,
                    )
                    .order_by(ReviewCycle.cycle_id)
                )
            )
            .scalars()
            .first()
        )
        name = cycle.name if cycle else DEFAULT_NAME
        if cycle is None:
            cycle = ReviewCycle(
                client_id=reference.client_id,
                project_lead=reference.project_lead,
                review_period=reference.review_period,
                name=name,
                audit_type=reference.audit_type,
                priority=reference.priority,
                framework=reference.framework,
                start_date=reference.start_date,
                due_date=reference.due_date,
                status="Draft",
                overview=reference.overview,
                description=(
                    f"{reference.description or ''}\n\nSamples are selected from the "
                    "sampling methodology matrix rather than the full testing population."
                ).strip(),
                entity_code=reference.entity_code,
                sampling_mode="matrix",
            )
            db.add(cycle)
        await db.commit()
        cycle_id = cycle.cycle_id

        control_ids = (
            await db.execute(
                select(ControlRepository.control_id)
                .where(ControlRepository.client_id == reference.client_id)
                .order_by(ControlRepository.control_id)
            )
        ).scalars().all()

        service = ConfigControlService(db)
        await service.bulk_attach(cycle_id, list(control_ids))
        # Re-apply in case controls were attached before the mode was set.
        await service.apply_cycle_sampling(cycle_id)
        await db.commit()

        print(f"Locked cycle {reference_id} ({reference.name}).")
        print(f"Matrix cycle {cycle_id} ({name}) — {len(control_ids)} controls attached.\n")
        check = await service.sampling_check(cycle_id)
        for row in check.controls:
            types = ", ".join(f"{t.label} {t.selected}/{t.available}" for t in row.types)
            print(
                f"  {row.control_number:<12} {row.frequency or '-':<16} {row.risk_level or '-':<7}"
                f" matrix={row.matrix_value or '-':<7} selected {row.selected}/{row.available}"
                f"  [{row.status}]"
            )
            if types:
                print(f"      by type: {types}")
            if row.message:
                print(f"      {row.message}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 16))

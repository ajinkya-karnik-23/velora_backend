"""Start the matrix-sampled cycle's controls on the phased lifecycle.

Usage:
    python -m scripts.setup_phased_cycle [CYCLE_ID]

Every control on the cycle (default: the client's matrix-sampled cycle, 17)
is put back at design effectiveness with its first sample drawn — the same
reset "Clear Run Data" performs, without touching uploaded evidence. Also
renames the demo sign-in account to Anshu Sharma, so runs are recorded under
the tester the demo follows. Prints each control's current phase and samples.

The full-population baseline is refused: it is never phased.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.base import *  # noqa: F401,F403 — register all models for relationship resolution
from app.db.session import async_session_maker, engine
from app.models.review_cycle import ReviewCycle
from app.models.user import User
from app.services.phase_service import PhaseService, phased

DEMO_TESTER = "Anshu Sharma"


async def main(cycle_id: int | None) -> None:
    async with async_session_maker() as db:
        if cycle_id is None:
            cycle = (
                (
                    await db.execute(
                        select(ReviewCycle)
                        .where(ReviewCycle.sampling_mode == "matrix")
                        .order_by(ReviewCycle.cycle_id)
                    )
                )
                .scalars()
                .first()
            )
        else:
            cycle = await db.get(ReviewCycle, cycle_id)
        if cycle is None or not phased(cycle):
            raise SystemExit("No matrix-sampled cycle to phase; the baseline is never phased.")

        admin = (
            await db.execute(select(User).order_by(User.user_id).limit(1))
        ).scalar_one_or_none()
        if admin is not None and admin.user_name != DEMO_TESTER:
            print(f"Renaming account {admin.email}: {admin.user_name} -> {DEMO_TESTER}")
            admin.user_name = DEMO_TESTER

        service = PhaseService(db)
        await service.reset_cycle(cycle.cycle_id)
        await db.commit()

        print(f"\nCycle {cycle.cycle_id} · {cycle.name}")
        for control in await service.cycle_phases(cycle.cycle_id):
            run = next(
                (r for r in control["runs"] if r["phase_run_id"] == control["current_run_id"]),
                None,
            )
            print(
                f"  {control['control_number']:<12} path {'→'.join(control['path']):<10} "
                f"now {run['label'] if run else '—':<6} samples {run['selected_samples'] if run else []}"
            )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else None))

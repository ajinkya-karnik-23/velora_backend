"""Write the demo's field changes (misc/phase_demo.json "demo_changes") to the database.

Usage:
    python -m scripts.apply_demo_changes            # apply each change's "to"
    python -m scripts.apply_demo_changes --revert   # put each "from" back

Only `frequency` is supported. It is set on the control's repository record
(the column and the imported JSON's rcm_details) and on the control's
entity snapshot in every matrix-sampled cycle, where sizing reads it. The
locked full-population baseline keeps its snapshot. The client's control JSON
files are never modified. Safe to run repeatedly.
"""

from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.base import *  # noqa: F401,F403 — register all models for relationship resolution
from app.db.session import async_session_maker, engine
from app.models.config_control import ConfigControl
from app.models.control_repository import ControlRepository
from app.models.review_cycle import ReviewCycle
from app.services.phase_demo import _load, demo_changes_for


def _with_frequency(payload: dict[str, Any] | None, value: str) -> dict[str, Any] | None:
    if not payload:
        return payload
    out = copy.deepcopy(payload)
    out.setdefault("rcm_details", {})["Frequency"] = value
    return out


async def main(revert: bool) -> None:
    async with async_session_maker() as db:
        for entry in _load():
            number = str(entry.get("control_number", "")).strip()
            entity = entry.get("entity_code")
            change = demo_changes_for(number, entity).get("frequency")
            if not change:
                continue
            value = change["from"] if revert else change["to"]
            controls = (
                (
                    await db.execute(
                        select(ControlRepository).where(ControlRepository.control_number == number)
                    )
                )
                .scalars()
                .all()
            )
            for ctrl in controls:
                print(
                    f"{number}: frequency {ctrl.frequency} -> {value} (control {ctrl.control_id})"
                )
                ctrl.frequency = value
                ctrl.source_json = _with_frequency(ctrl.source_json, value)
                attached = (
                    await db.execute(
                        select(ConfigControl)
                        .join(ReviewCycle, ReviewCycle.cycle_id == ConfigControl.cycle_id)
                        .where(
                            ConfigControl.control_id == ctrl.control_id,
                            ReviewCycle.sampling_mode == "matrix",
                        )
                    )
                ).scalars()
                for cc in attached:
                    cc.entity_detail_json = _with_frequency(cc.entity_detail_json, value)
                    print(f"  cycle {cc.cycle_id}: attached control {cc.config_control_id} updated")
        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main("--revert" in sys.argv[1:]))

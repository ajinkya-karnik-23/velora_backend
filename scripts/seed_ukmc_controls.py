"""Seed UKMC master controls and canonical test templates from JSON.

Usage:
    python -m scripts.seed_ukmc_controls

Prerequisites:
    Run `python -m scripts.seed` first to ensure admin user and version exist.

What this does:
    1. Upserts ControlRepository rows from ukmc_master_controls.json.
    2. Upserts ControlTestTemplate rows with the canonical test_id values
       from data/detailed_jsons/<CTRL>.json.  These IDs are reused verbatim
       when a control is attached to any review cycle (_seed_tests).
    3. Repairs any existing ConfigControl that has zero ControlTest rows by
       seeding it from the templates right now — no Reset+Reattach needed.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import *  # noqa: F401,F403 — register all models for relationship resolution
from app.db.session import async_session_maker, engine
from app.models.client import Client
from app.models.config_control import ConfigControl
from app.models.control_repository import ControlRepository
from app.models.control_test import ControlTest
from app.models.control_test_template import ControlTestTemplate
from app.models.review_cycle import ReviewCycle
from app.models.user import User
from app.models.version import Version

SEED_CLIENT_CODE = "SIGNORA-SEED"
SEED_CLIENT_NAME = "Signora Seed Client"
SEED_CYCLE_NAME = "Signora Seed Cycle Q4 FY24"

JSON_PATH = Path(__file__).resolve().parent / "ukmc_master_controls.json"
DETAILED_JSONS_PATH = Path(__file__).resolve().parent.parent / "data" / "detailed_jsons"


def _load_detailed(control_number: str) -> list[dict]:
    """Return the ordered validations list from the control's detailed JSON."""
    json_file = DETAILED_JSONS_PATH / f"{control_number}.json"
    if not json_file.exists():
        return []
    try:
        data = json.loads(json_file.read_text(encoding="utf-8", errors="ignore"))
        return data.get("validations", [])
    except Exception:
        return []


async def _get_admin_user(session: AsyncSession) -> User:
    result = await session.execute(
        select(User).where(User.status == "Active").order_by(User.user_id).limit(1)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise RuntimeError("No active user found. Run `python -m scripts.seed` first.")
    return user


async def _get_current_version(session: AsyncSession) -> Version:
    result = await session.execute(select(Version).where(Version.is_current.is_(True)))
    version = result.scalar_one_or_none()
    if not version:
        raise RuntimeError("No current version found. Run `python -m scripts.seed` first.")
    return version


async def _get_or_create_client(session: AsyncSession) -> Client:
    _OLD_CODES = ["AZ-SEED", "VELORA-SEED"]
    result = await session.execute(
        select(Client).where(
            Client.client_code.in_([SEED_CLIENT_CODE] + _OLD_CODES)
        )
    )
    client = result.scalar_one_or_none()
    if client:
        updated = False
        if client.client_code != SEED_CLIENT_CODE:
            client.client_code = SEED_CLIENT_CODE
            updated = True
        if client.client_name != SEED_CLIENT_NAME:
            client.client_name = SEED_CLIENT_NAME
            updated = True
        if updated:
            await session.flush()
            print(f"  Renamed existing seed client → {SEED_CLIENT_NAME}")
        return client
    client = Client(
        client_code=SEED_CLIENT_CODE,
        client_name=SEED_CLIENT_NAME,
        definition_scope="Seeded from ukmc_master_controls.json",
        reference_documents="ukmc_master_controls.json",
    )
    session.add(client)
    await session.flush()
    print(f"  Created seed client: {SEED_CLIENT_CODE}")
    return client


async def _get_or_create_cycle(
    session: AsyncSession, client_id: int, admin_id: int
) -> ReviewCycle:
    _OLD_NAMES = [
        "AZ Seed Cycle",
        "Velora Seed Cycle",
        "V.E.L.O.R.A Seed Cycle",
    ]
    result = await session.execute(
        select(ReviewCycle).where(
            ReviewCycle.name.in_([SEED_CYCLE_NAME] + _OLD_NAMES)
        )
    )
    cycles = result.scalars().all()

    # Keep the first cycle (preferring an already-correctly-named one); delete the rest.
    primary = next((c for c in cycles if c.name == SEED_CYCLE_NAME), None)
    if primary is None and cycles:
        primary = cycles[0]

    for cycle in cycles:
        if cycle is primary:
            continue
        # Must delete child config_controls before the cycle (RESTRICT FK).
        cc_result = await session.execute(
            select(ConfigControl).where(ConfigControl.cycle_id == cycle.cycle_id)
        )
        for cc in cc_result.scalars().all():
            await session.delete(cc)
        await session.flush()
        await session.delete(cycle)
        await session.flush()
        print(f"  Deleted stale seed cycle: {cycle.name!r}")

    if primary:
        if primary.name != SEED_CYCLE_NAME:
            primary.name = SEED_CYCLE_NAME
            await session.flush()
            print(f"  Renamed seed cycle → {SEED_CYCLE_NAME}")
        return primary

    now = int(time.time())
    cycle = ReviewCycle(
        client_id=client_id,
        review_period="Q4 FY2024",
        name=SEED_CYCLE_NAME,
        audit_type="Internal",
        priority="High",
        start_date=now,
        due_date=now + 90 * 86400,
        status="Draft",
        project_lead=admin_id,
    )
    session.add(cycle)
    await session.flush()
    print(f"  Created seed review cycle: {SEED_CYCLE_NAME}")
    return cycle


async def _repair_missing_tests(session: AsyncSession) -> int:
    """For every ConfigControl that has no ControlTest rows, seed from templates.

    This handles the case where controls were attached before templates existed,
    or where a seed script run previously deleted test rows.
    Returns the number of ControlTest rows created.
    """
    # Find config_control_ids that have zero ControlTest rows
    subq = (
        select(ControlTest.config_control_id)
        .group_by(ControlTest.config_control_id)
        .having(func.count() > 0)
        .scalar_subquery()
    )
    result = await session.execute(
        select(ConfigControl).where(ConfigControl.config_control_id.not_in(subq))
    )
    bare_ccs = result.scalars().all()

    if not bare_ccs:
        return 0

    rows_created = 0
    for cc in bare_ccs:
        templates = (
            await session.execute(
                select(ControlTestTemplate)
                .where(
                    ControlTestTemplate.control_id == cc.control_id,
                    ControlTestTemplate.tests.is_not(None),
                )
                .order_by(ControlTestTemplate.template_id)
            )
        ).scalars().all()

        if templates:
            for tmpl in templates:
                kwargs: dict = {
                    "config_control_id": cc.config_control_id,
                    "tests": tmpl.tests,
                    "note": tmpl.note,
                    "comments": tmpl.comments,
                }
                if tmpl.source_test_id is not None:
                    kwargs["test_id"] = tmpl.source_test_id
                session.add(ControlTest(**kwargs))
                rows_created += 1
        else:
            # No templates yet — create one blank placeholder
            session.add(ControlTest(config_control_id=cc.config_control_id))
            rows_created += 1

        await session.flush()

    return rows_created


async def seed_ukmc_controls() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(data)} entries from JSON")

    async with async_session_maker() as session:
        async with session.begin():
            admin = await _get_admin_user(session)
            version = await _get_current_version(session)
            client = await _get_or_create_client(session)
            await _get_or_create_cycle(session, client.client_id, admin.user_id)

            admin_id = admin.user_id
            version_id = version.version_id

            controls_created = 0
            controls_skipped = 0
            templates_created = 0
            templates_updated = 0
            templates_skipped = 0

            for entry in data:
                control_number = entry["control_number"]
                frequency = entry["frequency"]

                # ── ControlRepository row ────────────────────────────────────
                result = await session.execute(
                    select(ControlRepository).where(
                        ControlRepository.control_number == control_number,
                        ControlRepository.frequency == frequency,
                    )
                )
                ctrl = result.scalar_one_or_none()

                if not ctrl:
                    entity = entry["entity"] or "Signora"
                    ctrl = ControlRepository(
                        control_number=control_number,
                        version_id=version_id,
                        control_name=entry["control_name"],
                        reference_number=entry.get("reference_number"),
                        entity=entity,
                        control_desc=entry["control_desc"],
                        frequency=frequency,
                        risk_level=entry["risk_level"],
                        pwc_reliance=entry.get("pwc_reliance"),
                        control_owner=admin_id,
                        units_fccg_contact=admin_id,
                    )
                    session.add(ctrl)
                    await session.flush()
                    controls_created += 1
                else:
                    controls_skipped += 1

                # ── ControlTestTemplate rows (canonical, cycle-independent) ──
                validations = _load_detailed(control_number)
                source_ids: list[int | None] = [v.get("test_id") for v in validations]

                for idx, test_entry in enumerate(entry.get("control_tests_and_evidences", [])):
                    tests_label = test_entry["tests"]
                    source_id: int | None = source_ids[idx] if idx < len(source_ids) else None

                    tmpl_result = await session.execute(
                        select(ControlTestTemplate).where(
                            ControlTestTemplate.control_id == ctrl.control_id,
                            ControlTestTemplate.tests == tests_label,
                        )
                    )
                    existing_tmpl = tmpl_result.scalar_one_or_none()

                    if existing_tmpl is None:
                        session.add(ControlTestTemplate(
                            control_id=ctrl.control_id,
                            source_test_id=source_id,
                            tests=tests_label,
                            note=test_entry.get("note"),
                            comments=test_entry.get("comments"),
                        ))
                        await session.flush()
                        templates_created += 1
                    elif existing_tmpl.source_test_id is None and source_id is not None:
                        existing_tmpl.source_test_id = source_id
                        await session.flush()
                        templates_updated += 1
                    else:
                        templates_skipped += 1

            # ── Repair any ConfigControls that have no ControlTest rows ──────
            repaired = await _repair_missing_tests(session)

            print(f"\n  Controls:   {controls_created} created, {controls_skipped} skipped")
            print(
                f"  Templates:  {templates_created} created, "
                f"{templates_updated} backfilled, {templates_skipped} skipped"
            )
            if repaired:
                print(f"  Repaired:   {repaired} ControlTest rows seeded for bare ConfigControls")

    print("UKMC seed complete.")



if __name__ == "__main__":

    async def _run() -> None:
        await seed_ukmc_controls()
        await engine.dispose()

    asyncio.run(_run())

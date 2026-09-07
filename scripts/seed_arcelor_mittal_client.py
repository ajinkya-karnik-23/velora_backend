"""Seed the Arcelor Mittal SOC POC client and its control catalog.

Usage:
    python -m scripts.seed_arcelor_mittal_client

Idempotent — safe to run on every startup (matches the pattern used by
scripts/seed_ukmc_controls.py).

Controls are materialized from the client's own control_jsons directory
using the same field mapping as the upload-control flow
(ControlService.upload_from_control_json), so a seeded row is
indistinguishable from one created by uploading the matching Excel. Without
this the Control Repository screen is empty for this client, since uploading
is otherwise the only path that writes a control_repository row.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import *  # noqa: F401,F403 — register all models for relationship resolution
from app.db.session import async_session_maker, engine
from app.models.client import Client
from app.models.control_repository import ControlRepository
from app.models.user import User
from app.models.version import Version
from app.services.control_matching import iter_control_jsons

CLIENT_CODE = "ARCELOR-MITTAL"
CLIENT_NAME = "ArcelorMittal"
# Shown as the subtitle/tag beneath the client name across the app.
DEFINITION_SCOPE = "Control Automation"
COMPLIANCE_FRAMEWORK = "SOX 404"
# Taken from configuration so the seeded client points at wherever the client
# data actually lives on this machine (see CLIENT_DATA_PATH).
EVIDENCE_VAULT_PATH = settings.SUPPORTING_DOCS_PATH
CONTROL_JSONS_PATH = settings.CONTROL_JSONS_PATH


async def _get_or_create_client(session: AsyncSession) -> Client:
    result = await session.execute(select(Client).where(Client.client_code == CLIENT_CODE))
    client = result.scalar_one_or_none()
    if client:
        updated = False
        if client.client_name != CLIENT_NAME:
            client.client_name = CLIENT_NAME
            updated = True
        if client.definition_scope != DEFINITION_SCOPE:
            client.definition_scope = DEFINITION_SCOPE
            updated = True
        if client.evidence_vault_path != EVIDENCE_VAULT_PATH:
            client.evidence_vault_path = EVIDENCE_VAULT_PATH
            updated = True
        if client.control_jsons_path != CONTROL_JSONS_PATH:
            client.control_jsons_path = CONTROL_JSONS_PATH
            updated = True
        if client.compliance_framework != COMPLIANCE_FRAMEWORK:
            client.compliance_framework = COMPLIANCE_FRAMEWORK
            updated = True
        if updated:
            await session.flush()
            print(f"  Updated {CLIENT_CODE} client record")
        return client

    client = Client(
        client_code=CLIENT_CODE,
        client_name=CLIENT_NAME,
        definition_scope=DEFINITION_SCOPE,
        reference_documents="Provided by Arcelor Mittal (POC).",
        compliance_framework=COMPLIANCE_FRAMEWORK,
        evidence_vault_path=EVIDENCE_VAULT_PATH,
        control_jsons_path=CONTROL_JSONS_PATH,
    )
    session.add(client)
    await session.flush()
    print(f"  Created client: {CLIENT_CODE} ({CLIENT_NAME})")
    return client


async def _get_admin_user(session: AsyncSession) -> User:
    """The bootstrap admin — stands in as control owner / FCCG contact, the
    way the uploading user does in the upload flow."""
    result = await session.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
    admin = result.scalar_one_or_none()
    if admin is None:
        raise RuntimeError(f"Admin user {settings.ADMIN_EMAIL} not found — run scripts.seed first.")
    return admin


async def _seed_controls(session: AsyncSession, client: Client) -> None:
    """Upsert one ControlRepository row per control JSON in the client's
    control_jsons directory.

    Field mapping is kept in lockstep with
    ControlService.upload_from_control_json — change both together.
    """
    control_jsons_dir = Path(client.control_jsons_path or settings.CONTROL_JSONS_PATH)
    payloads = iter_control_jsons(control_jsons_dir)
    if not payloads:
        # Client data is optional — the app runs without it, the screen is
        # simply empty. Say so rather than failing the seed.
        print(f"  No control JSONs under {control_jsons_dir} — skipping controls")
        return

    admin = await _get_admin_user(session)
    version = (
        await session.execute(select(Version).where(Version.is_current.is_(True)))
    ).scalar_one_or_none()

    created = updated = 0
    for _path, payload in payloads:
        details = payload.get("control_details", {}) or {}
        rcm = payload.get("rcm_details", {}) or {}
        control_number = str(details.get("Control No", "")).strip()
        if not control_number:
            continue

        fields = {
            "control_number": control_number,
            "client_id": client.client_id,
            "version_id": version.version_id if version else None,
            "control_name": details.get("Control Name") or control_number,
            "reference_number": details.get("Control Reference") or None,
            "entity": details.get("Entity Code") or details.get("Region Name") or "Unknown",
            "control_desc": details.get("Control Description") or "",
            "domain": details.get("Category of the Process") or None,
            "frequency": rcm.get("Frequency") or "Unknown",
            "risk_level": rcm.get("Risk Level") or "Unknown",
            "pwc_reliance": rcm.get("Ext. Auditor Reliance") or None,
            "control_owner": admin.user_id,
            "units_fccg_contact": admin.user_id,
            "source_json": payload,
        }

        existing = (
            await session.execute(
                select(ControlRepository).where(
                    ControlRepository.client_id == client.client_id,
                    ControlRepository.control_number == control_number,
                )
            )
        ).scalar_one_or_none()

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            updated += 1
        else:
            session.add(ControlRepository(**fields))
            created += 1

    await session.flush()
    print(f"  Controls: {created} created, {updated} updated")


async def seed_arcelor_mittal_client() -> None:
    async with async_session_maker() as session:
        async with session.begin():
            client = await _get_or_create_client(session)
            await _seed_controls(session, client)

    print("Arcelor Mittal client seed complete.")


if __name__ == "__main__":

    async def _run() -> None:
        await seed_arcelor_mittal_client()
        await engine.dispose()

    asyncio.run(_run())

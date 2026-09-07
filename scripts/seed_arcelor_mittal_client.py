"""Seed the Arcelor Mittal SOC POC client.

Usage:
    python -m scripts.seed_arcelor_mittal_client

Idempotent — safe to run on every startup (matches the pattern used by
scripts/seed_ukmc_controls.py).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_maker, engine
from app.models.client import Client

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


async def seed_arcelor_mittal_client() -> None:
    async with async_session_maker() as session:
        async with session.begin():
            await _get_or_create_client(session)

    print("Arcelor Mittal client seed complete.")


if __name__ == "__main__":

    async def _run() -> None:
        await seed_arcelor_mittal_client()
        await engine.dispose()

    asyncio.run(_run())

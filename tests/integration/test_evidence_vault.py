"""Integration tests for the per-client evidence vault (supporting-documents-dump).

Each client has its own isolated vault directory (Client.evidence_vault_path),
one folder per control number — see <CLIENT_DATA_PATH>/
supporting_documents_dump for the Arcelor Mittal client. Tests build a
throwaway vault dir and point the seeded test client's evidence_vault_path
at it, so nothing here touches real client data.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


def _build_fake_vault(tmp_path: Path) -> Path:
    """Create a vault dir with two control folders, mirroring the real layout."""
    vault = tmp_path / "supporting_documents_dump"

    ctrl_a = vault / "CTRL0001"
    ctrl_a.mkdir(parents=True)
    (ctrl_a / "evidence1.xlsx").write_bytes(b"fake xlsx content")
    (ctrl_a / "evidence2.png").write_bytes(b"fake png content")

    ctrl_b = vault / "CTRL0002"
    ctrl_b.mkdir(parents=True)
    (ctrl_b / "screenshot.jpg").write_bytes(b"fake jpg content")

    # Junk that must be ignored: loose file at vault root, dotfiles.
    (vault / ".DS_Store").write_bytes(b"")
    (vault / "loose_file.txt").write_bytes(b"should be ignored, not in a control folder")
    (ctrl_a / ".DS_Store").write_bytes(b"")

    return vault


async def _point_client_at_vault(
    db_session: AsyncSession, client_id: int, vault: Path
) -> None:
    """Assign a client's evidence_vault_path, simulating its own POD."""
    from app.models.client import Client

    client = await db_session.get(Client, client_id)
    client.evidence_vault_path = str(vault)
    await db_session.commit()


@pytest.mark.asyncio
async def test_demo_vault_lists_files_grouped_by_control(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    vault = _build_fake_vault(tmp_path)
    await _point_client_at_vault(db_session, cid, vault)

    resp = await client.get(
        "/api/v1/evidence/demo-vault",
        params={"client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 200
    data = resp.json()

    control_numbers = {f["control_number"] for f in data}
    assert control_numbers == {"CTRL0001", "CTRL0002"}

    # Loose root file and dotfiles must not appear.
    file_names = {f["file_name"] for f in data}
    assert "loose_file.txt" not in file_names
    assert ".DS_Store" not in file_names

    ctrl_a_files = {f["file_name"] for f in data if f["control_number"] == "CTRL0001"}
    assert ctrl_a_files == {"evidence1.xlsx", "evidence2.png"}


@pytest.mark.asyncio
async def test_demo_vault_is_isolated_per_client(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    """A second client with its own vault must never see another client's files."""
    from app.models.client import Client

    cid_a = seeded_engagement["client"].client_id
    vault_a = _build_fake_vault(tmp_path / "client_a")
    await _point_client_at_vault(db_session, cid_a, vault_a)

    vault_b = tmp_path / "client_b" / "supporting_documents_dump"
    (vault_b / "CTRL9999").mkdir(parents=True)
    (vault_b / "CTRL9999" / "other_client_file.pdf").write_bytes(b"belongs to client B only")

    client_b = Client(
        client_code="OTHER-CLIENT",
        client_name="Other Client",
        definition_scope="Other client scope",
        reference_documents="Other client docs",
        evidence_vault_path=str(vault_b),
    )
    db_session.add(client_b)
    await db_session.commit()

    resp_a = await client.get(
        "/api/v1/evidence/demo-vault",
        params={"client_id": cid_a},
        headers=seeded_users["Admin"]["headers"],
    )
    resp_b = await client.get(
        "/api/v1/evidence/demo-vault",
        params={"client_id": client_b.client_id},
        headers=seeded_users["Admin"]["headers"],
    )

    assert {f["control_number"] for f in resp_a.json()} == {"CTRL0001", "CTRL0002"}
    assert {f["control_number"] for f in resp_b.json()} == {"CTRL9999"}
    assert "other_client_file.pdf" not in {f["file_name"] for f in resp_a.json()}


@pytest.mark.asyncio
async def test_demo_vault_unknown_client_404s(client, seeded_users):
    resp = await client.get(
        "/api/v1/evidence/demo-vault",
        params={"client_id": 999999},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_demo_vault_empty_when_dir_missing(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    missing = tmp_path / "does_not_exist_yet"
    await _point_client_at_vault(db_session, cid, missing)

    resp = await client.get(
        "/api/v1/evidence/demo-vault",
        params={"client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_demo_vault_download_file(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    vault = _build_fake_vault(tmp_path)
    await _point_client_at_vault(db_session, cid, vault)

    resp = await client.get(
        "/api/v1/evidence/demo-vault/download",
        params={"control_number": "CTRL0001", "filename": "evidence1.xlsx", "client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 200
    assert resp.content == b"fake xlsx content"


@pytest.mark.asyncio
async def test_demo_vault_download_rejects_path_traversal(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    vault = _build_fake_vault(tmp_path)
    await _point_client_at_vault(db_session, cid, vault)
    # A real secret file living just outside the vault directory.
    (tmp_path / "secret.txt").write_bytes(b"outside the vault")

    resp = await client.get(
        "/api/v1/evidence/demo-vault/download",
        params={"control_number": "..", "filename": "secret.txt", "client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_demo_vault_download_404_for_missing_file(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    vault = _build_fake_vault(tmp_path)
    await _point_client_at_vault(db_session, cid, vault)

    resp = await client.get(
        "/api/v1/evidence/demo-vault/download",
        params={"control_number": "CTRL0001", "filename": "nope.xlsx", "client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
@patch("app.services.evidence_service.azure_storage")
async def test_import_demo_file_links_into_real_evidence(
    mock_azure, client, seeded_users, seeded_engagement, db_session, tmp_path
):
    mock_azure.upload_blob = AsyncMock(return_value="1/1/evidence1.xlsx")
    cid = seeded_engagement["client"].client_id
    vault = _build_fake_vault(tmp_path)
    await _point_client_at_vault(db_session, cid, vault)

    cycle_id = seeded_engagement["cycle"].cycle_id
    resp = await client.post(
        "/api/v1/evidence/import-demo-file",
        json={
            "control_number": "CTRL0001",
            "filename": "evidence1.xlsx",
            "client_id": cid,
            "cycle_id": cycle_id,
        },
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["file_name"] == "evidence1.xlsx"
    assert data["status"] == "Pending"

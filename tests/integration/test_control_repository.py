"""Integration tests for the control-JSON-matched control repository upload.

An uploaded control Excel is never parsed — only its filename's leading
"<code>.<code>" prefix is used as a search key, matched against each
control JSON's own control_details["Control No"] (not the JSON's filename —
real client exports use a ".txt" extension and don't reliably have a fixed
segment count, see test_control_matching.py). The matched JSON's
control_details/rcm_details become one ControlRepository row for that
client. Also covers that the control repository listing is properly
client-scoped (each client is its own POD, per the evidence vault work).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

CONTROL_JSON_PAYLOAD = {
    "control_details": {
        "Business Process": "Journal Entries",
        "Region Name": "Europe",
        "Entity Code": "19A1",
        "Category of the Process": "IA8",
        "Control No": "IA8.CA02",
        "Control Reference": "IA8.CA02.19A1.",
        "Phase of control": "Design",
        "Control Name": "Non-Recurring and Manual JV Review",
        "IPE control": "No",
        "Control Description": "Review of non-recurring and manual journal entries.",
        "Sample Size": "25",
    },
    "rcm_details": {
        "Frequency": "Monthly",
        "Risk Level": "High",
        "Ext. Auditor Reliance": "Yes",
        "Control Owner": "Jane Doe",
    },
}


def _write_control_json(control_jsons_dir: Path, filename: str, payload: dict) -> Path:
    control_jsons_dir.mkdir(parents=True, exist_ok=True)
    f = control_jsons_dir / filename
    f.write_text(json.dumps(payload))
    return f


async def _point_client_at_control_jsons(
    db_session: AsyncSession, client_id: int, control_jsons_dir: Path
) -> None:
    from app.models.client import Client

    client = await db_session.get(Client, client_id)
    client.control_jsons_path = str(control_jsons_dir)
    await db_session.commit()


@pytest.mark.asyncio
async def test_upload_control_matches_by_content_and_creates_row(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    control_jsons_dir = tmp_path / "control_jsons"
    # Real client exports use ".txt" and a sub-index segment ("1") before the
    # entity — the filename must not need to be parsed to work.
    _write_control_json(
        control_jsons_dir, "IA8.CA02.1.19A1.DE.Control.txt", CONTROL_JSON_PAYLOAD
    )
    await _point_client_at_control_jsons(db_session, cid, control_jsons_dir)

    resp = await client.post(
        "/api/v1/controls/upload-control",
        data={"client_id": str(cid)},
        files={
            "file": (
                "IA8.CA02.19A1.DE.2026 NR and Manual JV.xlsm",
                b"pretend this is xlsm binary content",
                "application/vnd.ms-excel.sheet.macroEnabled.12",
            )
        },
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 201
    data = resp.json()
    # Control Repository groups by the 2-segment code — entity ("19A1") is
    # resolved later, per review cycle, not baked into the repo row.
    assert data["control_number"] == "IA8.CA02"
    assert data["client_id"] == cid
    assert data["control_name"] == "Non-Recurring and Manual JV Review"
    assert data["entity"] == "19A1"
    assert data["frequency"] == "Monthly"
    assert data["risk_level"] == "High"
    assert data["source_json"]["control_details"]["Control No"] == "IA8.CA02"


@pytest.mark.asyncio
async def test_upload_control_no_match_returns_404(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    control_jsons_dir = tmp_path / "control_jsons"
    decoy = {**CONTROL_JSON_PAYLOAD, "control_details": {**CONTROL_JSON_PAYLOAD["control_details"], "Control No": "ZZ9.ZZ99"}}
    _write_control_json(control_jsons_dir, "ZZ9.ZZ99.ZZZZ.DE.Control.txt", decoy)
    await _point_client_at_control_jsons(db_session, cid, control_jsons_dir)

    resp = await client.post(
        "/api/v1/controls/upload-control",
        data={"client_id": str(cid)},
        files={"file": ("IA8.CA02.19A1.DE.Whatever.xlsm", b"content", "application/octet-stream")},
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_control_invalid_filename_returns_422(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    await _point_client_at_control_jsons(db_session, cid, tmp_path / "control_jsons")

    resp = await client.post(
        "/api/v1/controls/upload-control",
        data={"client_id": str(cid)},
        files={"file": ("TooShort.xlsm", b"content", "application/octet-stream")},
        headers=seeded_users["Admin"]["headers"],
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reupload_same_control_updates_instead_of_duplicating(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    control_jsons_dir = tmp_path / "control_jsons"
    _write_control_json(
        control_jsons_dir, "IA8.CA02.1.19A1.DE.Control.txt", CONTROL_JSON_PAYLOAD
    )
    await _point_client_at_control_jsons(db_session, cid, control_jsons_dir)

    async def _upload():
        return await client.post(
            "/api/v1/controls/upload-control",
            data={"client_id": str(cid)},
            files={
                "file": (
                    "IA8.CA02.19A1.DE.2026 NR and Manual JV.xlsm",
                    b"content",
                    "application/octet-stream",
                )
            },
            headers=seeded_users["Admin"]["headers"],
        )

    first = await _upload()
    second = await _upload()
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["control_id"] == second.json()["control_id"]

    list_resp = await client.get(
        "/api/v1/controls/list-controls",
        params={"client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )
    matching = [c for c in list_resp.json()["data"] if c["control_number"] == "IA8.CA02"]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_list_controls_is_isolated_per_client(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    """Uploading a control for client A must never appear for client B."""
    from app.models.client import Client

    cid_a = seeded_engagement["client"].client_id
    control_jsons_dir = tmp_path / "control_jsons"
    _write_control_json(
        control_jsons_dir, "IA8.CA02.1.19A1.DE.Control.txt", CONTROL_JSON_PAYLOAD
    )
    await _point_client_at_control_jsons(db_session, cid_a, control_jsons_dir)

    await client.post(
        "/api/v1/controls/upload-control",
        data={"client_id": str(cid_a)},
        files={
            "file": (
                "IA8.CA02.19A1.DE.2026 NR and Manual JV.xlsm",
                b"content",
                "application/octet-stream",
            )
        },
        headers=seeded_users["Admin"]["headers"],
    )

    client_b = Client(
        client_code="OTHER-CLIENT-CTRL",
        client_name="Other Client",
        definition_scope="scope",
        reference_documents="docs",
    )
    db_session.add(client_b)
    await db_session.commit()

    resp_a = await client.get(
        "/api/v1/controls/list-controls",
        params={"client_id": cid_a},
        headers=seeded_users["Admin"]["headers"],
    )
    resp_b = await client.get(
        "/api/v1/controls/list-controls",
        params={"client_id": client_b.client_id},
        headers=seeded_users["Admin"]["headers"],
    )

    numbers_a = {c["control_number"] for c in resp_a.json()["data"]}
    numbers_b = {c["control_number"] for c in resp_b.json()["data"]}
    assert "IA8.CA02" in numbers_a
    assert "IA8.CA02" not in numbers_b

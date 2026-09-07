"""Integration tests for entity-scoped control attachment.

The Control Repository groups controls by their 2-segment code (e.g.
"IA8.CA02"). A review cycle can carry an entity_code (e.g. "19A1") — the
site it covers. Attaching a control to such a cycle resolves
control_number + entity_code against each control JSON's own CONTENT
(control_details["Control No"] / ["Entity Code"]) in the client's
control_jsons directory, and snapshots that entity's rcm_details onto the
ConfigControl row. The fixture JSON here uses the real-world filename shape
(a sub-index segment before the entity, ".txt" extension) to prove
resolution doesn't depend on filename position parsing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

ENTITY_JSON_PAYLOAD = {
    "control_details": {
        "Control No": "IA8.CA02",
        "Entity Code": "19A1",
        "Control Name": "Non-Recurring and Manual JV Review",
    },
    "rcm_details": {"Frequency": "Monthly", "Risk Level": "High"},
}


async def _make_control(
    db_session: AsyncSession,
    client_id: int,
    version_id: int,
    admin_id: int,
    control_number: str,
):
    from app.models.control_repository import ControlRepository

    now = int(time.time())
    ctrl = ControlRepository(
        control_number=control_number,
        client_id=client_id,
        version_id=version_id,
        control_name="Group Control",
        entity="Group Entity",
        control_desc="desc",
        frequency="Monthly",
        risk_level="High",
        control_owner=admin_id,
        units_fccg_contact=admin_id,
        created_time=now,
        updated_time=now,
    )
    db_session.add(ctrl)
    await db_session.commit()
    return ctrl


async def _point_client_control_jsons(
    db_session: AsyncSession, client_id: int, dir_path: Path
) -> None:
    from app.models.client import Client

    c = await db_session.get(Client, client_id)
    c.control_jsons_path = str(dir_path)
    await db_session.commit()


async def _create_cycle(client, headers, client_id, extra: dict | None = None):
    now = int(time.time())
    body = {
        "client_id": client_id,
        "review_period": "Q1 2026",
        "name": "Entity Test Cycle",
        "start_date": now,
        "due_date": now + 86400 * 30,
        **(extra or {}),
    }
    return await client.post("/api/v1/review-cycles/create-cycle", json=body, headers=headers)


@pytest.mark.asyncio
async def test_attach_control_with_entity_resolves_detail_json(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    version_id = seeded_engagement["version"].version_id
    admin_id = seeded_users["Admin"]["user_id"]

    control_jsons_dir = tmp_path / "control_jsons"
    control_jsons_dir.mkdir()
    # Real-world shape: sub-index segment ("1") before the entity, .txt extension.
    (control_jsons_dir / "IA8.CA02.1.19A1.DE.Control.txt").write_text(
        json.dumps(ENTITY_JSON_PAYLOAD)
    )
    await _point_client_control_jsons(db_session, cid, control_jsons_dir)
    ctrl = await _make_control(db_session, cid, version_id, admin_id, "IA8.CA02")

    cycle_resp = await _create_cycle(
        client, seeded_users["Admin"]["headers"], cid, {"entity_code": "19A1"}
    )
    assert cycle_resp.status_code == 201
    assert cycle_resp.json()["entity_code"] == "19A1"
    cycle_id = cycle_resp.json()["cycle_id"]

    attach_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/add-control",
        json={"control_id": ctrl.control_id},
        headers=seeded_users["Admin"]["headers"],
    )
    assert attach_resp.status_code == 201
    data = attach_resp.json()
    assert data["entity_code"] == "19A1"
    assert data["entity_detail_json"]["control_details"]["Control No"] == "IA8.CA02"
    assert data["entity_detail_json"]["rcm_details"]["Frequency"] == "Monthly"


@pytest.mark.asyncio
async def test_attach_control_without_entity_leaves_detail_null(
    client, seeded_users, seeded_engagement, db_session
):
    cid = seeded_engagement["client"].client_id
    version_id = seeded_engagement["version"].version_id
    admin_id = seeded_users["Admin"]["user_id"]
    ctrl = await _make_control(db_session, cid, version_id, admin_id, "IA8.CA03")

    cycle_resp = await _create_cycle(client, seeded_users["Admin"]["headers"], cid)
    assert cycle_resp.json()["entity_code"] is None
    cycle_id = cycle_resp.json()["cycle_id"]

    attach_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/add-control",
        json={"control_id": ctrl.control_id},
        headers=seeded_users["Admin"]["headers"],
    )
    assert attach_resp.status_code == 201
    data = attach_resp.json()
    assert data["entity_code"] is None
    assert data["entity_detail_json"] is None


@pytest.mark.asyncio
async def test_attach_control_entity_no_matching_json_is_non_fatal(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    version_id = seeded_engagement["version"].version_id
    admin_id = seeded_users["Admin"]["user_id"]

    await _point_client_control_jsons(db_session, cid, tmp_path / "control_jsons")
    ctrl = await _make_control(db_session, cid, version_id, admin_id, "IA8.CA04")

    cycle_resp = await _create_cycle(
        client, seeded_users["Admin"]["headers"], cid, {"entity_code": "ZZZZ"}
    )
    cycle_id = cycle_resp.json()["cycle_id"]

    attach_resp = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/add-control",
        json={"control_id": ctrl.control_id},
        headers=seeded_users["Admin"]["headers"],
    )
    assert attach_resp.status_code == 201
    data = attach_resp.json()
    assert data["entity_code"] == "ZZZZ"
    assert data["entity_detail_json"] is None


@pytest.mark.asyncio
async def test_list_entities_endpoint(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    cid = seeded_engagement["client"].client_id
    control_jsons_dir = tmp_path / "control_jsons"
    control_jsons_dir.mkdir()
    entity_b_payload = {
        **ENTITY_JSON_PAYLOAD,
        "control_details": {**ENTITY_JSON_PAYLOAD["control_details"], "Entity Code": "20B2"},
    }
    # Entities are read from content, not filename position — these use the
    # real-world ".txt" + sub-index shape to prove that.
    (control_jsons_dir / "IA8.CA02.1.19A1.DE.Control.txt").write_text(
        json.dumps(ENTITY_JSON_PAYLOAD)
    )
    (control_jsons_dir / "IA8.CA02.1.20B2.DE.Control.txt").write_text(
        json.dumps(entity_b_payload)
    )
    await _point_client_control_jsons(db_session, cid, control_jsons_dir)

    resp = await client.get(
        "/api/v1/controls/list-entities",
        params={"client_id": cid},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 200
    assert resp.json() == ["19A1", "20B2"]


# ─── Sample size calculation ──────────────────────────────────────────────────

SAMPLING_MATRIX = {
    "Sampling Methodology": {
        "Operating Effectiveness Testing": {
            "Monthly": {
                "Risk Rating conclusion Low": None,
                "Risk Rating Conclusion Medium": "2 to 5",
                "Risk Rating Conclusion High": None,
                "RF (Full test)": 1,
                "RM": 2,
                "YE": None,
            }
        }
    }
}


async def _attach(client, headers, cycle_id, control_id):
    return await client.post(
        f"/api/v1/review-cycles/{cycle_id}/add-control",
        json={"control_id": control_id},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_calculate_sample_size_from_matrix(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    """Matrix hit: Medium + Monthly resolves to the '2 to 5' range cell."""
    cid = seeded_engagement["client"].client_id
    version_id = seeded_engagement["version"].version_id
    admin_id = seeded_users["Admin"]["user_id"]
    headers = seeded_users["Admin"]["headers"]

    payload = {
        "control_details": {
            "Control No": "IA5.CA03",
            "Entity Code": "19A1",
            "Phase of control": "DE",
            "Sample Size": 12,
        },
        "rcm_details": {"Risk Level": "Medium", "Frequency": "Monthly"},
    }
    control_jsons_dir = tmp_path / "control_jsons"
    control_jsons_dir.mkdir()
    (control_jsons_dir / "IA5.CA03.1.19A1.DE.Control.json").write_text(json.dumps(payload))
    await _point_client_control_jsons(db_session, cid, control_jsons_dir)
    ctrl = await _make_control(db_session, cid, version_id, admin_id, "IA5.CA03")

    cycle_id = (await _create_cycle(client, headers, cid, {"entity_code": "19A1"})).json()[
        "cycle_id"
    ]
    cc_id = (await _attach(client, headers, cycle_id, ctrl.control_id)).json()[
        "config_control_id"
    ]

    matrix_file = tmp_path / "sampling_matrix.json"
    matrix_file.write_text(json.dumps(SAMPLING_MATRIX))
    with patch("app.core.config.settings.SAMPLING_MATRIX_PATH", str(matrix_file)):
        resp = await client.post(
            f"/api/v1/review-cycles/{cycle_id}/calculate-sample-size",
            params={"config_control_id": cc_id},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sample_size"] == "2 to 5"
    assert data["sample_size_source"] == "matrix"
    assert data["frequency"] == "Monthly"
    assert data["risk_level"] == "Medium"
    assert data["phase"] == "DE"


@pytest.mark.asyncio
async def test_calculate_sample_size_falls_back_to_control_json(
    client, seeded_users, seeded_engagement, db_session, tmp_path
):
    """No matrix row for 'Upon Occurrence' -> fall back to JSON Sample Size."""
    cid = seeded_engagement["client"].client_id
    version_id = seeded_engagement["version"].version_id
    admin_id = seeded_users["Admin"]["user_id"]
    headers = seeded_users["Admin"]["headers"]

    payload = {
        "control_details": {
            "Control No": "IA8.CA02",
            "Entity Code": "19A1",
            "Phase of control": "DE",
            "Sample Size": 2,
        },
        "rcm_details": {"Risk Level": "Low", "Frequency": "Upon Occurrence"},
    }
    control_jsons_dir = tmp_path / "control_jsons"
    control_jsons_dir.mkdir()
    (control_jsons_dir / "IA8.CA02.19A1.DE.Control.json").write_text(json.dumps(payload))
    await _point_client_control_jsons(db_session, cid, control_jsons_dir)
    ctrl = await _make_control(db_session, cid, version_id, admin_id, "IA8.CA02")

    cycle_id = (await _create_cycle(client, headers, cid, {"entity_code": "19A1"})).json()[
        "cycle_id"
    ]
    cc_id = (await _attach(client, headers, cycle_id, ctrl.control_id)).json()[
        "config_control_id"
    ]

    matrix_file = tmp_path / "sampling_matrix.json"
    matrix_file.write_text(json.dumps(SAMPLING_MATRIX))
    with patch("app.core.config.settings.SAMPLING_MATRIX_PATH", str(matrix_file)):
        resp = await client.post(
            f"/api/v1/review-cycles/{cycle_id}/calculate-sample-size",
            params={"config_control_id": cc_id},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sample_size"] == "2"
    assert data["sample_size_source"] == "control_definition"
    # The attributes the determination used are returned for the UI to show.
    assert data["frequency"] == "Upon Occurrence"
    assert data["risk_level"] == "Low"
    assert data["phase"] == "DE"


@pytest.mark.asyncio
async def test_calculate_sample_size_unknown_config_control_404s(client, seeded_users):
    resp = await client.post(
        "/api/v1/review-cycles/1/calculate-sample-size",
        params={"config_control_id": 999999},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sampling_matrix_endpoint_returns_matrix(client, seeded_users, tmp_path):
    matrix_file = tmp_path / "sampling_matrix.json"
    matrix_file.write_text(json.dumps(SAMPLING_MATRIX))
    with patch("app.core.config.settings.SAMPLING_MATRIX_PATH", str(matrix_file)):
        resp = await client.get(
            "/api/v1/controls/sampling-matrix",
            headers=seeded_users["Admin"]["headers"],
        )
    assert resp.status_code == 200
    assert resp.json() == SAMPLING_MATRIX

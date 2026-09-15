"""Integration tests for manual test steps: lifecycle, scope, results, evidence pinning."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

BASE = "/api/v1/manual-test-steps"


def _payload(cc_id: int, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "config_control_id": cc_id,
        "serial": "MS-01",
        "title": "Invoice total ties to ledger",
        "summary": "Reconcile the invoice total with the posted ledger amount.",
        "test_type": "total_reconciliation",
        "evidence_name": "Ledger extract",
        "evidence_description": "SAP FBL3N export",
        "parameters": [
            {
                "name": "Invoice total",
                "data_type": "currency",
                "expected": {"currency": "USD", "operator": "eq", "value": "83514.51"},
            },
            {"name": "Approved", "data_type": "boolean", "expected": {"value": True}},
        ],
    }
    body.update(overrides)
    return body


async def _add_evidence(
    db: AsyncSession, engagement: dict[str, Any], step_id: int, name: str = "ledger.pdf"
) -> int:
    from app.models.evidence_file import EvidenceFile

    now = int(time.time())
    ev = EvidenceFile(
        file_name=name,
        upload_date=now,
        uploaded_by=engagement["admin"]["user_id"],
        cycle_id=engagement["cycle"].cycle_id,
        control_id=engagement["control"].control_id,
        manual_step_id=step_id,
        status="Pending",
        file_version=1,
        created_time=now,
        updated_time=now,
    )
    db.add(ev)
    await db.commit()
    return ev.evidence_id


async def _create(client: AsyncClient, engagement: dict[str, Any], **overrides: Any) -> dict:
    res = await client.post(
        f"{BASE}/create-step",
        json=_payload(engagement["config_control"].config_control_id, **overrides),
        headers=engagement["admin"]["headers"],
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _cycle_steps(client: AsyncClient, engagement: dict[str, Any]) -> list[dict]:
    res = await client.get(
        f"{BASE}/list-for-cycle",
        params={"cycle_id": engagement["cycle"].cycle_id},
        headers=engagement["admin"]["headers"],
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_create_cycle_step_lists_under_cycle_and_control(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    step = await _create(client, seeded_engagement)

    assert step["scope"] == "cycle"
    assert step["cycle_name"] == "Test Engagement"
    assert step["parameters"][0]["expected"]["currency"] == "USD"

    listed = await _cycle_steps(client, seeded_engagement)
    assert [s["step_id"] for s in listed] == [step["step_id"]]
    assert listed[0]["applies_to_config_control_id"] == (
        seeded_engagement["config_control"].config_control_id
    )
    assert listed[0]["result"] is None

    repo = await client.get(
        f"{BASE}/list-for-control",
        params={"control_id": seeded_engagement["control"].control_id},
        headers=seeded_engagement["admin"]["headers"],
    )
    assert [s["step_id"] for s in repo.json()] == [step["step_id"]]


@pytest.mark.asyncio
async def test_kept_step_is_scoped_to_control(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    step = await _create(client, seeded_engagement, keep_for_future_cycles=True)

    assert step["scope"] == "control"
    assert step["config_control_id"] is None
    # Still applies to this cycle's attachment of the control.
    listed = await _cycle_steps(client, seeded_engagement)
    assert listed[0]["applies_to_config_control_id"] == (
        seeded_engagement["config_control"].config_control_id
    )


@pytest.mark.asyncio
async def test_update_changes_fields_and_scope(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    step = await _create(client, seeded_engagement)
    cc_id = seeded_engagement["config_control"].config_control_id

    body = _payload(cc_id, title="Renamed", parameters=[])
    body.pop("config_control_id")
    res = await client.put(
        f"{BASE}/update-step",
        params={"step_id": step["step_id"]},
        json={**body, "keep_for_future_cycles": True},
        headers=seeded_engagement["admin"]["headers"],
    )
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "Renamed"
    assert res.json()["scope"] == "control"
    assert res.json()["parameters"] == []

    # Narrowing back to one cycle needs the cycle's attachment.
    res = await client.put(
        f"{BASE}/update-step",
        params={"step_id": step["step_id"]},
        json={**body, "keep_for_future_cycles": False},
        headers=seeded_engagement["admin"]["headers"],
    )
    assert res.status_code == 422
    res = await client.put(
        f"{BASE}/update-step",
        params={"step_id": step["step_id"]},
        json={**body, "keep_for_future_cycles": False, "config_control_id": cc_id},
        headers=seeded_engagement["admin"]["headers"],
    )
    assert res.json()["scope"] == "cycle"


@pytest.mark.asyncio
async def test_rejects_unknown_test_type(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    res = await client.post(
        f"{BASE}/create-step",
        json=_payload(seeded_engagement["config_control"].config_control_id, test_type="guess"),
        headers=seeded_engagement["admin"]["headers"],
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_result_needs_evidence_and_remark_for_non_pass(
    client: AsyncClient, seeded_engagement: dict[str, Any], db_session: AsyncSession
) -> None:
    step = await _create(client, seeded_engagement)
    cc_id = seeded_engagement["config_control"].config_control_id
    headers = seeded_engagement["admin"]["headers"]
    url = f"{BASE}/record-result"

    res = await client.put(
        url,
        params={"step_id": step["step_id"]},
        json={"config_control_id": cc_id, "verdict": "PASS"},
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "EVIDENCE_REQUIRED"

    await _add_evidence(db_session, seeded_engagement, step["step_id"])

    res = await client.put(
        url,
        params={"step_id": step["step_id"]},
        json={"config_control_id": cc_id, "verdict": "FAIL"},
        headers=headers,
    )
    assert res.json()["error"]["code"] == "REMARK_REQUIRED"

    res = await client.put(
        url,
        params={"step_id": step["step_id"]},
        json={"config_control_id": cc_id, "verdict": "FAIL", "remark": "Totals differ."},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["verdict"] == "FAIL"

    listed = await _cycle_steps(client, seeded_engagement)
    assert listed[0]["result"]["remark"] == "Totals differ."


@pytest.mark.asyncio
async def test_new_evidence_voids_recorded_result(
    client: AsyncClient, seeded_engagement: dict[str, Any], db_session: AsyncSession
) -> None:
    step = await _create(client, seeded_engagement)
    cc_id = seeded_engagement["config_control"].config_control_id
    await _add_evidence(db_session, seeded_engagement, step["step_id"])
    await client.put(
        f"{BASE}/record-result",
        params={"step_id": step["step_id"]},
        json={"config_control_id": cc_id, "verdict": "PASS"},
        headers=seeded_engagement["admin"]["headers"],
    )
    assert (await _cycle_steps(client, seeded_engagement))[0]["result"]["verdict"] == "PASS"

    await _add_evidence(db_session, seeded_engagement, step["step_id"], name="second.pdf")

    assert (await _cycle_steps(client, seeded_engagement))[0]["result"] is None


@pytest.mark.asyncio
async def test_delete_removes_step_and_unlinks_evidence(
    client: AsyncClient, seeded_engagement: dict[str, Any], db_session: AsyncSession
) -> None:
    from app.models.evidence_file import EvidenceFile

    step = await _create(client, seeded_engagement)
    evidence_id = await _add_evidence(db_session, seeded_engagement, step["step_id"])

    res = await client.delete(
        f"{BASE}/delete-step",
        params={"step_id": step["step_id"]},
        headers=seeded_engagement["admin"]["headers"],
    )
    assert res.status_code == 204

    assert await _cycle_steps(client, seeded_engagement) == []
    db_session.expire_all()
    ev = (
        await db_session.execute(
            select(EvidenceFile).where(EvidenceFile.evidence_id == evidence_id)
        )
    ).scalar_one()
    assert ev.manual_step_id is None


@pytest.mark.asyncio
async def test_clear_run_data_drops_step_results(
    client: AsyncClient, seeded_engagement: dict[str, Any], db_session: AsyncSession
) -> None:
    step = await _create(client, seeded_engagement)
    cc_id = seeded_engagement["config_control"].config_control_id
    await _add_evidence(db_session, seeded_engagement, step["step_id"])
    await client.put(
        f"{BASE}/record-result",
        params={"step_id": step["step_id"]},
        json={"config_control_id": cc_id, "verdict": "PASS"},
        headers=seeded_engagement["admin"]["headers"],
    )

    res = await client.delete(
        f"/api/v1/control-testing/cycle/{seeded_engagement['cycle'].cycle_id}/run-data",
        headers=seeded_engagement["admin"]["headers"],
    )
    assert res.status_code == 200, res.text
    assert (await _cycle_steps(client, seeded_engagement))[0]["result"] is None


@pytest.mark.asyncio
async def test_viewer_cannot_create(
    client: AsyncClient, seeded_engagement: dict[str, Any], seeded_users: dict[str, Any]
) -> None:
    res = await client.post(
        f"{BASE}/create-step",
        json=_payload(seeded_engagement["config_control"].config_control_id),
        headers=seeded_users["Viewer"]["headers"],
    )
    assert res.status_code == 403

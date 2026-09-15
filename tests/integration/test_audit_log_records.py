"""Audit log entries written by sample runs and manual step results."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from app.schemas.config_control import ControlTestOutputOut, TestSampleOut

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


def _output(cc_id: int, test_id: int) -> ControlTestOutputOut:
    return ControlTestOutputOut(
        config_control_id=cc_id,
        control_number="CTRL-001",
        test_id=test_id,
        samples=[
            TestSampleOut(sample_no=1, result="PASS", validation="Matched.", evidence_status="ok"),
            TestSampleOut(
                sample_no=2, result="PASS", validation="Secret detail.", evidence_status="invalid"
            ),
            TestSampleOut(
                sample_no=3, result="PENDING", validation="Awaiting.", evidence_status="missing"
            ),
        ],
    )


async def _logs(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    res = await client.get("/api/v1/test-logs/list", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_sample_run_is_logged_with_server_verdict(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    cc = seeded_engagement["config_control"]
    headers = seeded_engagement["admin"]["headers"]
    output = _output(cc.config_control_id, seeded_engagement["control_test"].test_id)

    with patch(
        "app.services.config_control_service.ConfigControlService.get_test_output",
        return_value=output,
    ):
        ok = await client.post(
            "/api/v1/test-logs/record-sample-run",
            json={
                "config_control_id": cc.config_control_id,
                "sample_no": 1,
                "execution_time_ms": 1200,
            },
            headers=headers,
        )
        bad = await client.post(
            "/api/v1/test-logs/record-sample-run",
            json={"config_control_id": cc.config_control_id, "sample_no": 2},
            headers=headers,
        )
        missing = await client.post(
            "/api/v1/test-logs/record-sample-run",
            json={"config_control_id": cc.config_control_id, "sample_no": 3},
            headers=headers,
        )

    assert ok.status_code == 201, ok.text
    assert ok.json()["status"] == "PASS"
    assert ok.json()["source"] == "sample"
    assert ok.json()["sample_no"] == 1
    assert ok.json()["execution_time_seconds"] == 2
    assert ok.json()["cycle_name"] == "Test Engagement"

    # Failed evidence is logged generically; the stored narrative is not leaked.
    assert bad.json()["status"] == "EVIDENCE_EXCEPTION"
    assert "Secret" not in (bad.json()["notes"] or "")

    assert missing.status_code == 422

    logs = await _logs(client, headers)
    assert [entry["sample_no"] for entry in logs] == [2, 1]


@pytest.mark.asyncio
async def test_manual_step_result_is_logged(
    client: AsyncClient, seeded_engagement: dict[str, Any], db_session: AsyncSession
) -> None:
    from app.models.evidence_file import EvidenceFile

    cc = seeded_engagement["config_control"]
    headers = seeded_engagement["admin"]["headers"]
    step = (
        await client.post(
            "/api/v1/manual-test-steps/create-step",
            json={
                "config_control_id": cc.config_control_id,
                "serial": "MS-01",
                "title": "Ties out",
                "summary": "s",
                "test_type": "custom",
                "evidence_name": "e",
                "parameters": [],
            },
            headers=headers,
        )
    ).json()
    now = int(time.time())
    db_session.add(
        EvidenceFile(
            file_name="e.pdf",
            upload_date=now,
            uploaded_by=seeded_engagement["admin"]["user_id"],
            cycle_id=seeded_engagement["cycle"].cycle_id,
            control_id=seeded_engagement["control"].control_id,
            manual_step_id=step["step_id"],
            status="Pending",
            file_version=1,
            created_time=now,
            updated_time=now,
        )
    )
    await db_session.commit()

    for verdict, remark in (("FAIL", "Totals differ."), ("PASS", None)):
        res = await client.put(
            f"/api/v1/manual-test-steps/record-result?step_id={step['step_id']}",
            json={"config_control_id": cc.config_control_id, "verdict": verdict, "remark": remark},
            headers=headers,
        )
        assert res.status_code == 200, res.text

    logs = await _logs(client, headers)
    # Each recording is its own entry, newest first.
    assert [(entry["status"], entry["source"]) for entry in logs] == [
        ("PASS", "manual_step"),
        ("FAIL", "manual_step"),
    ]
    assert logs[0]["step_label"] == "MS-01 · Ties out"


@pytest.mark.asyncio
async def test_list_is_scoped_to_the_selected_client(
    client: AsyncClient, seeded_engagement: dict[str, Any], db_session: AsyncSession
) -> None:
    from app.models.test_log import TestLog

    headers = seeded_engagement["admin"]["headers"]
    now = int(time.time())
    db_session.add(
        TestLog(
            cycle_id=seeded_engagement["cycle"].cycle_id,
            control_id=seeded_engagement["control"].control_id,
            log_date=now,
            changed_by=seeded_engagement["admin"]["user_id"],
            status="PASS",
            created_time=now,
            updated_time=now,
        )
    )
    await db_session.commit()
    own = seeded_engagement["client"].client_id

    mine = await client.get(f"/api/v1/test-logs/list?client_id={own}", headers=headers)
    other = await client.get(f"/api/v1/test-logs/list?client_id={own + 999}", headers=headers)

    assert len(mine.json()) == 1
    assert other.json() == []

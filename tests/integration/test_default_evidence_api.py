"""Attaching a control's default evidence from its Testing card."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient

OUTPUT = {
    "control_test_output": {"control_number": "CTRL-001"},
    "test_details": {"1": {"sample_no": 1}, "2": {"sample_no": 2}},
}


@pytest.mark.asyncio
async def test_status_then_attach_is_idempotent(
    client: AsyncClient, seeded_engagement: dict[str, Any], tmp_path: Path
) -> None:
    evidence_dir = tmp_path / "ev"
    evidence_dir.mkdir()
    (evidence_dir / "proof.pdf").write_bytes(b"%PDF-1.4")
    map_path = tmp_path / "map.json"
    map_path.write_text(
        json.dumps(
            {
                "controls": [
                    {
                        "control_number": "CTRL-001",
                        "source_dir": str(evidence_dir),
                        "files_from": "fixed",
                        "file": "proof.pdf",
                    }
                ]
            }
        )
    )

    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    headers = seeded_engagement["admin"]["headers"]
    base = f"/api/v1/review-cycles/{cycle_id}"

    with (
        patch("app.services.default_evidence.settings.DEFAULT_EVIDENCE_MAP_PATH", str(map_path)),
        patch("app.services.default_evidence.find_test_output", return_value=OUTPUT),
        patch(
            "app.services.default_evidence.storage.upload_blob",
            new=AsyncMock(return_value="blob/proof.pdf"),
        ),
    ):
        status = await client.get(
            f"{base}/default-evidence?config_control_id={cc_id}", headers=headers
        )
        assert status.json() == {
            "configured": True,
            "planned": 2,
            "missing": 2,
            "unavailable": 0,
            "missing_files": [
                {"sample_no": 1, "file_name": "proof.pdf"},
                {"sample_no": 2, "file_name": "proof.pdf"},
            ],
        }

        single = f"{base}/attach-default-evidence?config_control_id={cc_id}&sample_no=1&file_name=proof.pdf"
        one = await client.post(single, headers=headers)
        assert (one.json()["attached"], one.json()["missing"]) == (1, 1)
        assert (await client.post(single, headers=headers)).json()["attached"] == 0

        rest = await client.post(
            f"{base}/attach-default-evidence?config_control_id={cc_id}", headers=headers
        )
        assert rest.status_code == 200, rest.text
        assert rest.json()["attached"] == 1

        again = await client.post(
            f"{base}/attach-default-evidence?config_control_id={cc_id}", headers=headers
        )
        assert again.json()["attached"] == 0

    evidence = (await client.get(f"{base}/list-evidence", headers=headers)).json()
    assert sorted(e["sample_no"] for e in evidence if e["file_name"] == "proof.pdf") == [1, 2]


@pytest.mark.asyncio
async def test_unmapped_control_is_not_configured(
    client: AsyncClient, seeded_engagement: dict[str, Any], tmp_path: Path
) -> None:
    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    with patch(
        "app.services.default_evidence.settings.DEFAULT_EVIDENCE_MAP_PATH",
        str(tmp_path / "none.json"),
    ):
        res = await client.get(
            f"/api/v1/review-cycles/{cycle_id}/default-evidence?config_control_id={cc_id}",
            headers=seeded_engagement["admin"]["headers"],
        )
    assert res.json()["configured"] is False


@pytest.mark.asyncio
async def test_viewer_cannot_attach(
    client: AsyncClient, seeded_engagement: dict[str, Any], seeded_users: dict[str, Any]
) -> None:
    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    res = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/attach-default-evidence?config_control_id={cc_id}",
        headers=seeded_users["Viewer"]["headers"],
    )
    assert res.status_code == 403

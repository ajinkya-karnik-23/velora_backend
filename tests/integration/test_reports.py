"""Integration tests for report downloads.

TWP (Test Work Paper) download is state-aware: an empty template while the
control still has samples to test, the completed work paper once they have all
been tested. Which file backs each variant comes from the TWP template map;
controls with no mapping fall back to settings.TWP_TEMPLATE_PATH.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

XLSM_MEDIA_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.12"


@pytest.mark.asyncio
async def test_download_twp_template_success(client, seeded_users, seeded_engagement, tmp_path):
    cc_id = seeded_engagement["config_control"].config_control_id

    # Supply the fallback template rather than relying on client data, which
    # lives outside the repository and may not be present.
    fallback = tmp_path / "dummy_template.xlsm"
    fallback.write_bytes(b"FALLBACK-TEMPLATE")

    with patch("app.core.config.settings.TWP_TEMPLATE_PATH", str(fallback)):
        resp = await client.get(
            "/api/v1/reports/twp-template",
            params={"config_control_id": cc_id},
            headers=seeded_users["Admin"]["headers"],
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == XLSM_MEDIA_TYPE
    # Unmapped control → the fallback template, named for the empty variant.
    assert resp.headers["x-twp-variant"] == "empty"
    assert "_Template.xlsm" in resp.headers["content-disposition"]
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_download_twp_template_unknown_config_control_404s(client, seeded_users):
    resp = await client.get(
        "/api/v1/reports/twp-template",
        params={"config_control_id": 999999},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_twp_template_missing_file_404s(client, seeded_users, seeded_engagement):
    cc_id = seeded_engagement["config_control"].config_control_id

    with patch("app.core.config.settings.TWP_TEMPLATE_PATH", "does/not/exist.xlsm"):
        resp = await client.get(
            "/api/v1/reports/twp-template",
            params={"config_control_id": cc_id},
            headers=seeded_users["Admin"]["headers"],
        )
    assert resp.status_code == 404


# ── State-aware variant selection ─────────────────────────────────────────────


@pytest.fixture
def mapped_templates(tmp_path, seeded_engagement):
    """Map the seeded control to two distinguishable workbooks."""
    control = seeded_engagement["config_control"]
    empty = tmp_path / "empty.xlsm"
    completed = tmp_path / "completed.xlsm"
    empty.write_bytes(b"EMPTY-WORKBOOK")
    completed.write_bytes(b"COMPLETED-WORKBOOK")

    mapping = tmp_path / "twp_template_map.json"
    mapping.write_text(
        json.dumps(
            {
                "controls": [
                    {
                        "control_number": seeded_engagement["control"].control_number,
                        "entity_code": control.entity_code,
                        "empty_template": str(empty),
                        "completed_template": str(completed),
                    }
                ]
            }
        )
    )
    return mapping


@pytest.mark.asyncio
async def test_serves_empty_template_before_testing(
    client, seeded_users, seeded_engagement, mapped_templates
):
    cc_id = seeded_engagement["config_control"].config_control_id

    with patch("app.core.config.settings.TWP_TEMPLATE_MAP_PATH", str(mapped_templates)):
        resp = await client.get(
            "/api/v1/reports/twp-template",
            params={"config_control_id": cc_id, "tests_completed": False},
            headers=seeded_users["Admin"]["headers"],
        )

    assert resp.status_code == 200
    assert resp.content == b"EMPTY-WORKBOOK"
    assert resp.headers["x-twp-variant"] == "empty"


@pytest.mark.asyncio
async def test_serves_completed_report_once_tested(
    client, seeded_users, seeded_engagement, mapped_templates
):
    cc_id = seeded_engagement["config_control"].config_control_id

    with patch("app.core.config.settings.TWP_TEMPLATE_MAP_PATH", str(mapped_templates)):
        resp = await client.get(
            "/api/v1/reports/twp-template",
            params={"config_control_id": cc_id, "tests_completed": True},
            headers=seeded_users["Admin"]["headers"],
        )

    assert resp.status_code == 200
    assert resp.content == b"COMPLETED-WORKBOOK"
    assert resp.headers["x-twp-variant"] == "completed"


@pytest.mark.asyncio
async def test_defaults_to_the_empty_template(
    client, seeded_users, seeded_engagement, mapped_templates
):
    """Omitting the flag must never hand back a completed report."""
    cc_id = seeded_engagement["config_control"].config_control_id

    with patch("app.core.config.settings.TWP_TEMPLATE_MAP_PATH", str(mapped_templates)):
        resp = await client.get(
            "/api/v1/reports/twp-template",
            params={"config_control_id": cc_id},
            headers=seeded_users["Admin"]["headers"],
        )

    assert resp.content == b"EMPTY-WORKBOOK"


@pytest.mark.asyncio
async def test_missing_completed_report_404s_rather_than_serving_the_empty_one(
    client, seeded_users, seeded_engagement, tmp_path
):
    """A missing completed report must not silently degrade to a blank one."""
    control = seeded_engagement["config_control"]
    empty = tmp_path / "empty.xlsm"
    empty.write_bytes(b"EMPTY-WORKBOOK")
    mapping = tmp_path / "map.json"
    mapping.write_text(
        json.dumps(
            {
                "controls": [
                    {
                        "control_number": seeded_engagement["control"].control_number,
                        "entity_code": control.entity_code,
                        "empty_template": str(empty),
                        "completed_template": str(tmp_path / "absent.xlsm"),
                    }
                ]
            }
        )
    )

    with patch("app.core.config.settings.TWP_TEMPLATE_MAP_PATH", str(mapping)):
        resp = await client.get(
            "/api/v1/reports/twp-template",
            params={"config_control_id": control.config_control_id, "tests_completed": True},
            headers=seeded_users["Admin"]["headers"],
        )

    assert resp.status_code == 404
    assert "completed" in resp.json()["error"]["message"].lower()

"""The reviewer's word on a sample: saved, traced, and notified to the tester."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_edit_then_verdict_is_kept_with_its_trail_and_notified(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    cycle = seeded_engagement["cycle"]
    cc_id = seeded_engagement["config_control"].config_control_id
    headers = seeded_engagement["admin"]["headers"]
    base = f"/api/v1/review-cycles/{cycle.cycle_id}"
    url = f"{base}/sample-review?config_control_id={cc_id}&sample_no=3"

    edited = await client.put(
        url,
        json={
            "result": "FAIL",
            "conclusion": "The approval post-dates the posting.",
            "comment": "Please check the approver's delegation.",
            "involved": [{"name": "Joe Joseph", "email": "joe@example.com"}],
        },
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["result"] == "FAIL"
    assert edited.json()["verdict"] is None

    verdict = await client.put(url, json={"verdict": "returned_to_tester"}, headers=headers)
    assert verdict.status_code == 200, verdict.text
    assert verdict.json()["verdict"] == "returned_to_tester"
    # The edit is kept when only the verdict is sent.
    assert verdict.json()["result"] == "FAIL"
    assert verdict.json()["involved"][0]["name"] == "Joe Joseph"

    listed = (await client.get(f"{base}/sample-reviews", headers=headers)).json()
    assert [(r["sample_no"], r["verdict"]) for r in listed] == [(3, "returned_to_tester")]

    kinds = [e["kind"] for e in (await client.get(f"{base}/sample-review-events", headers=headers)).json()]
    assert sorted(kinds) == ["commented", "edited", "involved", "verdict"]

    notes = (
        await client.get(
            f"/api/v1/review-cycles/notifications?client_id={cycle.client_id}", headers=headers
        )
    ).json()
    assert {n["kind"] for n in notes} >= {"sample_verdict", "edited"}
    assert all(n["sample_no"] == 3 for n in notes)


@pytest.mark.asyncio
async def test_an_empty_save_is_refused(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    res = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/sample-review?config_control_id={cc_id}&sample_no=1",
        json={},
        headers=seeded_engagement["admin"]["headers"],
    )
    assert res.status_code == 422

"""Review workflow: tester hands over, reviewer decides, trail is kept."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_submit_then_verdicts_follow_the_lifecycle(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    headers = seeded_engagement["admin"]["headers"]
    base = f"/api/v1/review-cycles/{cycle_id}"

    # Nothing stored until a control is submitted: its state is testing progress.
    assert (await client.get(f"{base}/review-status", headers=headers)).json() == []

    submitted = await client.post(
        f"{base}/submit-for-review?config_control_id={cc_id}",
        json={"note": "All samples tested."},
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted_for_review"
    assert submitted.json()["submitted_by_name"] == "test_admin"

    # Submitting again while it sits with the reviewer is refused.
    again = await client.post(
        f"{base}/submit-for-review?config_control_id={cc_id}", json={}, headers=headers
    )
    assert again.status_code == 409

    for verdict in ("under_review", "reviewed", "approved"):
        res = await client.post(
            f"{base}/review-verdict?config_control_id={cc_id}",
            json={"verdict": verdict, "note": f"moved to {verdict}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == verdict
        assert res.json()["reviewed_by_name"] == "test_admin"

    listed = (await client.get(f"{base}/review-status", headers=headers)).json()
    assert [r["status"] for r in listed] == ["approved"]

    events = (
        await client.get(f"{base}/review-events?config_control_id={cc_id}", headers=headers)
    ).json()
    # Newest first, and the whole path is kept.
    assert [e["to_status"] for e in events] == [
        "approved",
        "reviewed",
        "under_review",
        "submitted_for_review",
    ]
    assert events[-1]["actor_persona"] == "tester"
    assert events[0]["actor_persona"] == "reviewer"


@pytest.mark.asyncio
async def test_return_needs_a_note_and_allows_resubmission(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    headers = seeded_engagement["admin"]["headers"]
    base = f"/api/v1/review-cycles/{cycle_id}"

    await client.post(
        f"{base}/submit-for-review?config_control_id={cc_id}", json={}, headers=headers
    )

    bare = await client.post(
        f"{base}/review-verdict?config_control_id={cc_id}",
        json={"verdict": "returned_to_tester"},
        headers=headers,
    )
    assert bare.status_code == 422
    assert bare.json()["error"]["code"] == "NOTE_REQUIRED"

    returned = await client.post(
        f"{base}/review-verdict?config_control_id={cc_id}",
        json={"verdict": "returned_to_tester", "note": "Sample 4 evidence is illegible."},
        headers=headers,
    )
    assert returned.json()["status"] == "returned_to_tester"

    # The tester can send it back once addressed, and the new submission
    # supersedes the previous verdict.
    resubmitted = await client.post(
        f"{base}/submit-for-review?config_control_id={cc_id}", json={}, headers=headers
    )
    assert resubmitted.json()["status"] == "submitted_for_review"
    assert resubmitted.json()["reviewed_by_name"] is None


@pytest.mark.asyncio
async def test_verdict_before_submission_is_refused(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    res = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/review-verdict?config_control_id={cc_id}",
        json={"verdict": "approved"},
        headers=seeded_engagement["admin"]["headers"],
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "NOT_SUBMITTED"


@pytest.mark.asyncio
async def test_submit_many_skips_controls_already_with_the_reviewer(
    client: AsyncClient, seeded_engagement: dict[str, Any]
) -> None:
    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    headers = seeded_engagement["admin"]["headers"]
    base = f"/api/v1/review-cycles/{cycle_id}"

    await client.post(
        f"{base}/submit-for-review?config_control_id={cc_id}", json={}, headers=headers
    )
    res = await client.post(
        f"{base}/submit-many-for-review",
        json={"config_control_ids": [cc_id]},
        headers=headers,
    )
    assert res.json() == {"submitted": [], "skipped": [cc_id]}


@pytest.mark.asyncio
async def test_viewer_cannot_submit_or_decide(
    client: AsyncClient, seeded_engagement: dict[str, Any], seeded_users: dict[str, Any]
) -> None:
    cycle_id = seeded_engagement["cycle"].cycle_id
    cc_id = seeded_engagement["config_control"].config_control_id
    res = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/submit-for-review?config_control_id={cc_id}",
        json={},
        headers=seeded_users["Viewer"]["headers"],
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_resubmit_after_testing_ran_again_replaces_the_hand_over(
    client: AsyncClient, seeded_engagement: dict[str, Any], db_session: Any
) -> None:
    """A submission that testing has since overtaken no longer holds, so the
    tester's fresh submission is accepted rather than refused as a duplicate."""
    from app.models.test_log import TestLog

    cycle_id = seeded_engagement["cycle"].cycle_id
    cc = seeded_engagement["config_control"]
    headers = seeded_engagement["admin"]["headers"]
    base = f"/api/v1/review-cycles/{cycle_id}"

    url = f"{base}/submit-for-review?config_control_id={cc.config_control_id}"
    first = await client.post(url, json={}, headers=headers)
    assert first.status_code == 200, first.text
    submitted_at = first.json()["submitted_time"]

    # A sample runs again after the hand-over.
    ran_at = submitted_at + 60
    db_session.add(
        TestLog(
            control_id=cc.control_id, cycle_id=cycle_id, log_date=ran_at,
            changed_by=seeded_engagement["admin"]["user_id"], status="PASS",
            created_time=ran_at, updated_time=ran_at,
        )
    )
    await db_session.commit()

    again = await client.post(url, json={"note": "Re-run and re-submitted."}, headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "submitted_for_review"

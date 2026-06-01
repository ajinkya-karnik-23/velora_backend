"""Unit tests for EngagementTeamService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.schemas.engagement_team import TeamMemberAdd
from app.services.engagement_team_service import EngagementTeamService


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def service(db):
    return EngagementTeamService(db)


TEAM_MEMBER_DICT = {
    "user_id": 2,
    "user_name": "auditor",
    "email": "auditor@test.com",
    "profile_picture": None,
    "job_title": None,
    "team_role": "Reviewer",
    "role_name": "Auditor",
}


@pytest.mark.asyncio
async def test_add_member_success(service):
    service.repo.is_member = AsyncMock(return_value=False)
    service.repo.add_member = AsyncMock()
    service.repo.get_team = AsyncMock(return_value=[TEAM_MEMBER_DICT])

    data = TeamMemberAdd(user_id=2, team_role="Reviewer")
    result = await service.add_member(1, data)
    assert result.user_id == 2
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_member_duplicate(service):
    service.repo.is_member = AsyncMock(return_value=True)

    data = TeamMemberAdd(user_id=2, team_role="Reviewer")
    with pytest.raises(ConflictException, match="already a member"):
        await service.add_member(1, data)


@pytest.mark.asyncio
async def test_bulk_add_skips_duplicates(service):
    # First call: not member, second call: already member
    service.repo.is_member = AsyncMock(side_effect=[False, True])
    service.repo.add_member = AsyncMock()
    service.repo.get_team = AsyncMock(return_value=[TEAM_MEMBER_DICT])

    members = [
        TeamMemberAdd(user_id=2, team_role="Reviewer"),
        TeamMemberAdd(user_id=3, team_role="Lead"),
    ]
    result = await service.bulk_add(1, members)
    # Only one add_member call (second skipped)
    assert service.repo.add_member.call_count == 1


@pytest.mark.asyncio
async def test_update_role_success(service):
    service.repo.update_role = AsyncMock(return_value=MagicMock())
    service.repo.get_team = AsyncMock(return_value=[TEAM_MEMBER_DICT])

    result = await service.update_role(1, 2, "Lead")
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_role_not_found(service):
    service.repo.update_role = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="Team member not found"):
        await service.update_role(1, 999, "Lead")


@pytest.mark.asyncio
async def test_remove_member_success(service):
    service.repo.remove_member = AsyncMock(return_value=True)

    await service.remove_member(1, 2)
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_member_not_found(service):
    service.repo.remove_member = AsyncMock(return_value=False)

    with pytest.raises(NotFoundException, match="Team member not found"):
        await service.remove_member(1, 999)

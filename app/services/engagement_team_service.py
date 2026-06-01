"""Engagement team service — add/remove/update team members."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.repositories.engagement_team_repo import EngagementTeamRepo
from app.schemas.engagement_team import TeamMemberAdd, TeamMemberOut


class EngagementTeamService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = EngagementTeamRepo(db)

    async def get_team(self, cycle_id: int) -> list[TeamMemberOut]:
        team = await self.repo.get_team(cycle_id)
        return [TeamMemberOut(**m) for m in team]

    async def add_member(self, cycle_id: int, data: TeamMemberAdd) -> TeamMemberOut:
        if await self.repo.is_member(cycle_id, data.user_id):
            raise ConflictException("User is already a member of this engagement.")
        await self.repo.add_member(cycle_id, data.user_id, data.team_role)
        await self.db.commit()
        # Re-fetch to get full details
        team = await self.repo.get_team(cycle_id)
        for m in team:
            if m["user_id"] == data.user_id:
                return TeamMemberOut(**m)
        raise NotFoundException("Member not found after add.")

    async def bulk_add(self, cycle_id: int, members: list[TeamMemberAdd]) -> list[TeamMemberOut]:
        for m in members:
            if not await self.repo.is_member(cycle_id, m.user_id):
                await self.repo.add_member(cycle_id, m.user_id, m.team_role)
        await self.db.commit()
        return await self.get_team(cycle_id)

    async def update_role(self, cycle_id: int, user_id: int, team_role: str) -> TeamMemberOut:
        member = await self.repo.update_role(cycle_id, user_id, team_role)
        if not member:
            raise NotFoundException("Team member not found.")
        await self.db.commit()
        team = await self.repo.get_team(cycle_id)
        for m in team:
            if m["user_id"] == user_id:
                return TeamMemberOut(**m)
        raise NotFoundException("Member not found after update.")

    async def remove_member(self, cycle_id: int, user_id: int) -> None:
        removed = await self.repo.remove_member(cycle_id, user_id)
        if not removed:
            raise NotFoundException("Team member not found.")
        await self.db.commit()

"""Engagement team repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.engagement_team import EngagementTeam
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.repositories.base_repo import BaseRepo


class EngagementTeamRepo(BaseRepo[EngagementTeam]):
    model = EngagementTeam

    async def get_team(self, cycle_id: int) -> list[dict]:
        """Get team members with user details and role names."""
        stmt = (
            select(
                EngagementTeam.user_id,
                User.user_name,
                User.email,
                User.profile_picture,
                User.job_title,
                EngagementTeam.team_role,
                Role.role_name,
            )
            .join(User, User.user_id == EngagementTeam.user_id)
            .outerjoin(UserRole, UserRole.user_id == User.user_id)
            .outerjoin(Role, Role.role_id == UserRole.role_id)
            .where(EngagementTeam.cycle_id == cycle_id)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        # Deduplicate (user may have multiple roles — pick first)
        seen: set[int] = set()
        team = []
        for row in rows:
            if row.user_id not in seen:
                seen.add(row.user_id)
                team.append(
                    {
                        "user_id": row.user_id,
                        "user_name": row.user_name,
                        "email": row.email,
                        "profile_picture": row.profile_picture,
                        "job_title": row.job_title,
                        "team_role": row.team_role,
                        "role_name": row.role_name,
                    }
                )
        return team

    async def is_member(self, cycle_id: int, user_id: int) -> bool:
        stmt = select(EngagementTeam).where(
            EngagementTeam.cycle_id == cycle_id,
            EngagementTeam.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_member(self, cycle_id: int, user_id: int) -> EngagementTeam | None:
        stmt = select(EngagementTeam).where(
            EngagementTeam.cycle_id == cycle_id,
            EngagementTeam.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_member(
        self, cycle_id: int, user_id: int, team_role: str
    ) -> EngagementTeam:
        member = EngagementTeam(cycle_id=cycle_id, user_id=user_id, team_role=team_role)
        self.session.add(member)
        await self.session.flush()
        return member

    async def update_role(
        self, cycle_id: int, user_id: int, team_role: str
    ) -> EngagementTeam | None:
        member = await self.get_member(cycle_id, user_id)
        if member:
            member.team_role = team_role
            await self.session.flush()
        return member

    async def remove_member(self, cycle_id: int, user_id: int) -> bool:
        member = await self.get_member(cycle_id, user_id)
        if member:
            await self.session.delete(member)
            await self.session.flush()
            return True
        return False

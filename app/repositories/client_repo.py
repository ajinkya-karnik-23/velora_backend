"""Client repository."""

from __future__ import annotations

from sqlalchemy import exists, select

from app.models.client import Client
from app.models.review_cycle import ReviewCycle
from app.repositories.base_repo import BaseRepo


class ClientRepo(BaseRepo[Client]):
    model = Client

    async def has_review_cycles(self, client_id: int) -> bool:
        """Check if any review_cycles reference this client (deletion guard)."""
        stmt = select(exists().where(ReviewCycle.client_id == client_id))
        result = await self.session.execute(stmt)
        return bool(result.scalar())

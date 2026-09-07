"""Client service — CRUD with deletion guard."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.client import Client
from app.models.control_repository import ControlRepository
from app.models.review_cycle import ReviewCycle
from app.repositories.client_repo import ClientRepo
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate


class ClientService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.client_repo = ClientRepo(db)

    async def create_client(self, data: ClientCreate) -> ClientOut:
        client = Client(**data.model_dump())
        await self.client_repo.create(client)
        await self.db.commit()
        return ClientOut.model_validate(client)

    async def get_client(self, client_id: int) -> ClientOut:
        client = await self.client_repo.get_by_id(client_id)
        if not client:
            raise NotFoundException("Client not found.")
        return ClientOut.model_validate(client)

    async def list_clients(self, page: int = 1, page_size: int = 20) -> tuple[list[ClientOut], int]:
        count_stmt = select(func.count(Client.client_id))
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(Client)
            .order_by(Client.client_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())

        # Two grouped queries for the whole page rather than a pair per client.
        ids = [c.client_id for c in rows]
        cycles: dict[int, int] = {}
        controls: dict[int, int] = {}
        if ids:
            cycles = dict(
                (
                    await self.db.execute(
                        select(ReviewCycle.client_id, func.count(ReviewCycle.cycle_id))
                        .where(ReviewCycle.client_id.in_(ids))
                        .group_by(ReviewCycle.client_id)
                    )
                ).all()
            )
            controls = dict(
                (
                    await self.db.execute(
                        select(ControlRepository.client_id, func.count())
                        .where(ControlRepository.client_id.in_(ids))
                        .group_by(ControlRepository.client_id)
                    )
                ).all()
            )

        clients = []
        for c in rows:
            out = ClientOut.model_validate(c)
            out.review_cycle_count = cycles.get(c.client_id, 0)
            out.control_count = controls.get(c.client_id, 0)
            clients.append(out)
        return clients, total

    async def update_client(self, client_id: int, data: ClientUpdate) -> ClientOut:
        client = await self.client_repo.get_by_id(client_id)
        if not client:
            raise NotFoundException("Client not found.")
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        await self.client_repo.update(client, update_data)
        await self.db.commit()
        return ClientOut.model_validate(client)

    async def delete_client(self, client_id: int) -> None:
        client = await self.client_repo.get_by_id(client_id)
        if not client:
            raise NotFoundException("Client not found.")
        if await self.client_repo.has_review_cycles(client_id):
            raise ConflictException("Cannot delete client with existing review cycles.")
        await self.client_repo.delete(client)
        await self.db.commit()

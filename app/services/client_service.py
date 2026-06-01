"""Client service — CRUD with deletion guard."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.client import Client
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

    async def list_clients(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[ClientOut], int]:
        count_stmt = select(func.count(Client.client_id))
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(Client)
            .order_by(Client.client_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        clients = [ClientOut.model_validate(c) for c in result.scalars().all()]
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

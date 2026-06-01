"""Client endpoints — CRUD."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_permission
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate
from app.schemas.common import PaginatedResponse
from app.services.client_service import ClientService

router = APIRouter()


@router.get("/list-clients", response_model=PaginatedResponse[ClientOut])
async def list_clients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = ClientService(db)
    clients, total = await service.list_clients(page, page_size)
    return {"data": clients, "total": total, "page": page, "page_size": page_size}


@router.post("/create-client", response_model=ClientOut, status_code=201)
async def create_client(
    data: ClientCreate,
    current_user: dict = Depends(require_permission("can_manage_clients")),
    db: AsyncSession = Depends(get_db),
) -> ClientOut:
    service = ClientService(db)
    return await service.create_client(data)


@router.get("/get-client", response_model=ClientOut)
async def get_client(
    client_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClientOut:
    service = ClientService(db)
    return await service.get_client(client_id)


@router.put("/update-client", response_model=ClientOut)
async def update_client(
    client_id: int = Query(...),
    data: ClientUpdate = Body(...),
    current_user: dict = Depends(require_permission("can_manage_clients")),
    db: AsyncSession = Depends(get_db),
) -> ClientOut:
    service = ClientService(db)
    return await service.update_client(client_id, data)


@router.delete("/delete-client", status_code=204, response_model=None)
async def delete_client(
    client_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_manage_clients")),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ClientService(db)
    await service.delete_client(client_id)


# Phase 3 stubs — will be implemented when review_cycles exist
# GET /{client_id}/review-cycles
# GET /{client_id}/ref-docs
# GET /{client_id}/scope

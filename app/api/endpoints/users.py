"""User endpoints — CRUD, role assignment, stats."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_permission
from app.schemas.common import PaginatedResponse
from app.schemas.role import RoleAssignment
from app.schemas.user import UserAdminUpdate, UserCreate, UserOut, UserUpdate
from app.services.user_service import UserService

router = APIRouter()


def _is_admin(current_user: dict) -> bool:
    return "Admin" in current_user.get("roles", [])


@router.get("/list-users", response_model=PaginatedResponse[UserOut])
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    department: str | None = None,
    search: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = UserService(db)
    users, total = await service.list_users(page, page_size, status, department, search)
    return {"data": users, "total": total, "page": page, "page_size": page_size}


@router.post("/create-user", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate,
    current_user: dict = Depends(require_permission("can_manage_users")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    service = UserService(db)
    return await service.create_user(data)


@router.get("/get-user-stats")
async def get_user_stats(
    current_user: dict = Depends(require_permission("can_manage_users")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = UserService(db)
    return await service.get_stats()


@router.get("/get-user", response_model=UserOut)
async def get_user(
    user_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    service = UserService(db)
    return await service.get_user(user_id)


@router.put("/update-user", response_model=UserOut)
async def update_user(
    user_id: int = Query(...),
    data: UserAdminUpdate = Body(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    is_admin = _is_admin(current_user)
    if is_admin:
        update_dict = data.model_dump(exclude_unset=True)
    else:
        # Non-admins: strip admin-only fields
        safe = UserUpdate(**data.model_dump(include=set(UserUpdate.model_fields.keys())))
        update_dict = safe.model_dump(exclude_unset=True)

    service = UserService(db)
    return await service.update_user(user_id, update_dict, int(current_user["sub"]), is_admin)


@router.put("/{user_id}/update-user-roles", response_model=UserOut)
async def update_user_roles(
    user_id: int,
    data: RoleAssignment,
    current_user: dict = Depends(require_permission("can_manage_users")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    service = UserService(db)
    return await service.update_roles(user_id, data.role_ids)


@router.delete("/delete-user", response_model=UserOut)
async def delete_user(
    user_id: int = Query(...),
    current_user: dict = Depends(require_permission("can_manage_users")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    service = UserService(db)
    return await service.soft_delete(user_id)

"""User service — CRUD, role assignment, soft-delete, stats."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.security import hash_password
from app.models.user import User
from app.models.user_role import UserRole
from app.repositories.user_repo import UserRepo
from app.schemas.user import UserCreate, UserOut


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepo(db)

    async def create_user(self, data: UserCreate) -> UserOut:
        """Create user + assign roles atomically."""
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise ConflictException("Email already registered.", field="email")

        user = User(
            user_name=data.user_name,
            email=data.email,
            password_hash=hash_password(data.password),
            phone=data.phone,
            department=data.department,
            job_title=data.job_title,
            location=data.location,
            profile_picture=data.profile_picture,
            status="Active",
        )
        self.db.add(user)
        await self.db.flush()  # materialise user_id

        # Assign roles
        for role_id in data.role_ids:
            self.db.add(UserRole(user_id=user.user_id, role_id=role_id))
        await self.db.flush()

        await self.db.commit()

        roles, permissions = await self.user_repo.get_roles_and_permissions(user.user_id)
        return UserOut(
            **{c.key: getattr(user, c.key) for c in user.__table__.columns},
            roles=roles,
            permissions=permissions,
        )

    async def get_user(self, user_id: int) -> UserOut:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found.")
        roles, permissions = await self.user_repo.get_roles_and_permissions(user.user_id)
        return UserOut(
            **{c.key: getattr(user, c.key) for c in user.__table__.columns},
            roles=roles,
            permissions=permissions,
        )

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        department: str | None = None,
        search: str | None = None,
    ) -> tuple[list[UserOut], int]:
        """Return paginated user list with filters."""
        stmt = select(User)
        count_stmt = select(func.count(User.user_id))

        if status:
            stmt = stmt.where(User.status == status)
            count_stmt = count_stmt.where(User.status == status)
        if department:
            stmt = stmt.where(User.department == department)
            count_stmt = count_stmt.where(User.department == department)
        if search:
            pattern = f"%{search}%"
            search_filter = User.user_name.ilike(pattern) | User.email.ilike(pattern)
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(User.user_id).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        users = list(result.scalars().all())

        user_outs = []
        for u in users:
            roles, permissions = await self.user_repo.get_roles_and_permissions(u.user_id)
            user_outs.append(
                UserOut(
                    **{c.key: getattr(u, c.key) for c in u.__table__.columns},
                    roles=roles,
                    permissions=permissions,
                )
            )
        return user_outs, total

    async def update_user(
        self,
        user_id: int,
        data: dict[str, Any],
        current_user_id: int,
        is_admin: bool,
    ) -> UserOut:
        """Update user fields. Self-service vs admin rules enforced by caller."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found.")

        # Non-admins can only update their own profile
        if not is_admin and user_id != current_user_id:
            raise ForbiddenException("Cannot update another user's profile.")

        # Check email uniqueness if changing email
        if "email" in data and data["email"] and data["email"] != user.email:
            existing = await self.user_repo.get_by_email(data["email"])
            if existing:
                raise ConflictException("Email already registered.", field="email")

        update_data = {k: v for k, v in data.items() if v is not None}
        await self.user_repo.update(user, update_data)
        await self.db.commit()

        return await self.get_user(user_id)

    async def update_roles(self, user_id: int, role_ids: list[int]) -> UserOut:
        """Replace all user roles (DELETE + INSERT)."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found.")

        # Delete existing roles
        existing_stmt = select(UserRole).where(UserRole.user_id == user_id)
        result = await self.db.execute(existing_stmt)
        for ur in result.scalars().all():
            await self.db.delete(ur)
        await self.db.flush()

        # Insert new roles
        for role_id in role_ids:
            self.db.add(UserRole(user_id=user_id, role_id=role_id))
        await self.db.flush()
        await self.db.commit()

        return await self.get_user(user_id)

    async def soft_delete(self, user_id: int) -> UserOut:
        """Soft-delete: set status to 'Deactivated'."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found.")
        await self.user_repo.update(user, {"status": "Deactivated"})
        await self.db.commit()
        return await self.get_user(user_id)

    async def get_stats(self) -> dict:
        return await self.user_repo.get_stats()

"""Idempotent seed script — roles, permissions, role-permission mappings, admin user.

Usage:
    python -m scripts.seed
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import async_session_maker, engine
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_role import UserRole
from app.models.version import Version

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

ROLES = ["Admin", "Moderator", "Auditor", "Viewer"]

PERMISSIONS = [
    ("can_manage_users", "Manage Users", "Create, update, delete, and assign roles to users"),
    ("can_manage_clients", "Manage Clients", "Create, update, and delete clients"),
    ("can_manage_cycles", "Manage Cycles", "Create, update, and delete review cycles"),
    ("can_manage_controls", "Manage Controls", "Attach/detach controls to cycles"),
    ("can_assign_team", "Assign Team", "Add/remove engagement team members"),
    ("can_upload", "Upload Evidence", "Upload evidence files"),
    ("can_approve", "Approve Evidence", "Approve evidence files"),
    ("can_reject", "Reject Evidence", "Reject evidence files"),
    ("can_export", "Export Data", "Export reports and data"),
]

# Permission matrix per §6
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Admin": [p[0] for p in PERMISSIONS],  # All 9
    "Moderator": [
        "can_manage_clients",
        "can_manage_cycles",
        "can_manage_controls",
        "can_assign_team",
        "can_upload",
        "can_approve",
        "can_reject",
    ],
    "Auditor": ["can_upload", "can_export"],
    "Viewer": [],
}


async def _get_or_create_role(session: AsyncSession, role_name: str) -> Role:
    stmt = select(Role).where(Role.role_name == role_name)
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()
    if role:
        return role
    role = Role(role_name=role_name)
    session.add(role)
    await session.flush()
    return role


async def _get_or_create_permission(
    session: AsyncSession, key: str, label: str, description: str
) -> Permission:
    stmt = select(Permission).where(Permission.permission_key == key)
    result = await session.execute(stmt)
    perm = result.scalar_one_or_none()
    if perm:
        return perm
    perm = Permission(permission_key=key, permission_label=label, permission_description=description)
    session.add(perm)
    await session.flush()
    return perm


async def _ensure_role_permission(
    session: AsyncSession, role_id: int, permission_id: int
) -> None:
    stmt = select(RolePermission).where(
        RolePermission.role_id == role_id,
        RolePermission.permission_id == permission_id,
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        return
    session.add(RolePermission(role_id=role_id, permission_id=permission_id))
    await session.flush()


async def seed() -> None:
    async with async_session_maker() as session:
        async with session.begin():
            # 1. Roles
            roles: dict[str, Role] = {}
            for name in ROLES:
                roles[name] = await _get_or_create_role(session, name)
            print(f"  Roles: {list(roles.keys())}")

            # 2. Permissions
            perms: dict[str, Permission] = {}
            for key, label, desc in PERMISSIONS:
                perms[key] = await _get_or_create_permission(session, key, label, desc)
            print(f"  Permissions: {list(perms.keys())}")

            # 3. Role-permission mappings
            for role_name, perm_keys in ROLE_PERMISSIONS.items():
                for perm_key in perm_keys:
                    await _ensure_role_permission(
                        session, roles[role_name].role_id, perms[perm_key].permission_id
                    )
            print("  Role-permission mappings set")

            # 4. Admin user
            stmt = select(User).where(User.email == settings.ADMIN_EMAIL)
            result = await session.execute(stmt)
            admin = result.scalar_one_or_none()
            if not admin:
                admin = User(
                    user_name="Admin",
                    email=settings.ADMIN_EMAIL,
                    password_hash=hash_password(settings.ADMIN_PASSWORD),
                    status="Active",
                )
                session.add(admin)
                await session.flush()
                # Assign Admin role
                session.add(UserRole(user_id=admin.user_id, role_id=roles["Admin"].role_id))
                await session.flush()
                print(f"  Admin user created: {settings.ADMIN_EMAIL}")
            else:
                print(f"  Admin user already exists: {settings.ADMIN_EMAIL}")

            # 5. Version (Phase 4)
            stmt = select(Version).where(Version.is_current.is_(True))
            result = await session.execute(stmt)
            version = result.scalar_one_or_none()
            if not version:
                version = Version(version_name="v1.0", is_current=True)
                session.add(version)
                await session.flush()
                print(f"  Version seeded: {version.version_name}")
            else:
                print(f"  Version already exists: {version.version_name}")


    print("Seed complete.")


if __name__ == "__main__":

    async def _run() -> None:
        await seed()
        await engine.dispose()

    asyncio.run(_run())

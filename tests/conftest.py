"""Shared test fixtures — async DB session, test client, seeded data."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sqlalchemy import BigInteger, Integer, event as sa_event
from sqlalchemy.engine import Engine

from app.core.security import create_access_token, hash_password
from app.db.base import Base  # imports all models so metadata is populated

# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# In-memory SQLite async engine (aiosqlite)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# SQLite requires INTEGER (not BIGINT) for autoincrement primary keys.
# Override BigInteger to render as INTEGER on SQLite.
from sqlalchemy.dialects import sqlite as sqlite_dialect

@sa_event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# Patch all BigInteger columns in metadata to use Integer on SQLite
@sa_event.listens_for(Base.metadata, "before_create")
def _patch_bigint_for_sqlite(target, connection, **kw):
    if connection.dialect.name == "sqlite":
        for table in target.sorted_tables:
            for column in table.columns:
                if isinstance(column.type, BigInteger):
                    column.type = Integer()

_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
_testing_session = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create all tables, yield a session, then drop everything."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with _testing_session() as session:
        yield session

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# FastAPI test client with DB override
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Yield an httpx AsyncClient wired to the test DB session."""
    from app.api.deps import get_db
    from app.main import create_app

    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

_ALL_PERMS = [
    "can_manage_users",
    "can_manage_clients",
    "can_manage_cycles",
    "can_manage_controls",
    "can_assign_team",
    "can_upload",
    "can_approve",
    "can_reject",
    "can_export",
]


def make_token(
    user_id: int = 1,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> str:
    """Create a valid JWT access token for testing."""
    return create_access_token(
        {
            "sub": user_id,
            "roles": roles if roles is not None else ["Admin"],
            "permissions": permissions if permissions is not None else _ALL_PERMS,
        }
    )


def auth_header(
    user_id: int = 1,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> dict[str, str]:
    """Return an Authorization header dict."""
    token = make_token(user_id, roles, permissions)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Seeded users fixture (one per role)
# ---------------------------------------------------------------------------

ADMIN_ALL_PERMS = [
    "can_manage_users", "can_manage_clients", "can_manage_cycles",
    "can_manage_controls", "can_assign_team", "can_upload",
    "can_approve", "can_reject", "can_export",
]
MODERATOR_PERMS = [
    "can_manage_clients", "can_manage_cycles", "can_manage_controls",
    "can_assign_team", "can_upload", "can_approve", "can_reject",
]
AUDITOR_PERMS = ["can_upload", "can_export"]
VIEWER_PERMS: list[str] = []


@pytest_asyncio.fixture
async def seeded_users(db_session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Insert one user per role and return their info (with tokens)."""
    from app.models.role import Role
    from app.models.user import User
    from app.models.user_role import UserRole

    now = int(time.time())
    users_info: dict[str, dict[str, Any]] = {}

    # Create roles
    roles_map: dict[str, Role] = {}
    for role_name in ("Admin", "Moderator", "Auditor", "Viewer"):
        role = Role(role_name=role_name, created_time=now, updated_time=now)
        db_session.add(role)
    await db_session.flush()

    result = await db_session.execute(
        __import__("sqlalchemy").select(Role)
    )
    for r in result.scalars().all():
        roles_map[r.role_name] = r

    role_perms = {
        "Admin": ADMIN_ALL_PERMS,
        "Moderator": MODERATOR_PERMS,
        "Auditor": AUDITOR_PERMS,
        "Viewer": VIEWER_PERMS,
    }

    for role_name in ("Admin", "Moderator", "Auditor", "Viewer"):
        user = User(
            user_name=f"test_{role_name.lower()}",
            email=f"{role_name.lower()}@test.com",
            password_hash=hash_password("Test@12345678"),
            status="Active",
            two_factor_enabled=False,
            api_access_enabled=False,
            created_time=now,
            updated_time=now,
        )
        db_session.add(user)
        await db_session.flush()

        ur = UserRole(
            user_id=user.user_id,
            role_id=roles_map[role_name].role_id,
            created_time=now,
            updated_time=now,
        )
        db_session.add(ur)
        await db_session.flush()

        token = make_token(user.user_id, [role_name], role_perms[role_name])
        users_info[role_name] = {
            "user": user,
            "user_id": user.user_id,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
            "roles": [role_name],
            "permissions": role_perms[role_name],
        }

    await db_session.commit()
    return users_info


# ---------------------------------------------------------------------------
# Seeded engagement fixture (client + cycle + team + control + evidence)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded_engagement(
    db_session: AsyncSession, seeded_users: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Create a full engagement setup for integration testing."""
    from app.models.client import Client
    from app.models.config_control import ConfigControl
    from app.models.control_repository import ControlRepository
    from app.models.control_test import ControlTest
    from app.models.engagement_team import EngagementTeam
    from app.models.review_cycle import ReviewCycle
    from app.models.version import Version

    now = int(time.time())
    admin = seeded_users["Admin"]
    auditor = seeded_users["Auditor"]

    # Client
    client_obj = Client(
        client_code="TEST-001",
        client_name="Test Client",
        definition_scope="Test scope",
        reference_documents="Test docs",
        compliance_framework="SOX",
        created_time=now,
        updated_time=now,
    )
    db_session.add(client_obj)
    await db_session.flush()

    # Version
    version = Version(
        version_name="v1.0",
        is_current=True,
        released_at=now,
        created_time=now,
        updated_time=now,
    )
    db_session.add(version)
    await db_session.flush()

    # Review cycle
    cycle = ReviewCycle(
        client_id=client_obj.client_id,
        project_lead=admin["user_id"],
        review_period="Q1 2026",
        name="Test Engagement",
        audit_type="Internal",
        priority="High",
        start_date=now,
        due_date=now + 86400 * 30,
        status="Active",
        created_time=now,
        updated_time=now,
    )
    db_session.add(cycle)
    await db_session.flush()

    # Engagement team — add Admin and Auditor
    for user_key, team_role in [("Admin", "Lead"), ("Auditor", "Reviewer")]:
        et = EngagementTeam(
            cycle_id=cycle.cycle_id,
            user_id=seeded_users[user_key]["user_id"],
            team_role=team_role,
            created_time=now,
            updated_time=now,
        )
        db_session.add(et)
    await db_session.flush()

    # Control repository entry
    control = ControlRepository(
        control_number="CTRL-001",
        version_id=version.version_id,
        control_name="Test Control",
        entity="Test Entity",
        control_desc="A test control description",
        domain="IT",
        status="Active",
        frequency="Annual",
        risk_level="High",
        control_owner=admin["user_id"],
        units_fccg_contact=admin["user_id"],
        created_time=now,
        updated_time=now,
    )
    db_session.add(control)
    await db_session.flush()

    # Config control (attach to cycle)
    cc = ConfigControl(
        cycle_id=cycle.cycle_id,
        control_id=control.control_id,
        created_time=now,
        updated_time=now,
    )
    db_session.add(cc)
    await db_session.flush()

    # Control test
    ct = ControlTest(
        config_control_id=cc.config_control_id,
        created_time=now,
        updated_time=now,
    )
    db_session.add(ct)
    await db_session.flush()

    await db_session.commit()

    return {
        "client": client_obj,
        "version": version,
        "cycle": cycle,
        "control": control,
        "config_control": cc,
        "control_test": ct,
        "admin": admin,
        "auditor": auditor,
    }

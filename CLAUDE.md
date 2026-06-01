# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CIQ (Controls Internal Quality) Backend — an audit management API built with FastAPI, async SQLAlchemy, and PostgreSQL. All 5 phases are implemented: auth/users, clients/versions, review cycles/engagement teams, controls/config controls, and evidence/test logs.

## Commands

```bash
# Run dev server
poetry run uvicorn app.main:app --reload --port 8000

# Run with Docker (includes Postgres + Azurite)
docker-compose up

# Database migrations
poetry run alembic upgrade head          # apply all
poetry run alembic revision --autogenerate -m "description"  # generate new

# Seed data (roles, permissions, admin user)
poetry run python -m scripts.seed

# Linting & formatting
poetry run black --check .
poetry run ruff check .
poetry run mypy .

# Tests
poetry run pytest
poetry run pytest tests/unit/
poetry run pytest tests/integration/
poetry run pytest -k "test_name"
```

## Architecture

**Layered pattern**: Endpoint -> Service -> Repository -> Model

- `app/api/endpoints/` — FastAPI routers. Each file is a resource (auth, users, clients, versions, review_cycles, controls, control_tests, evidence, test_logs).
- `app/services/` — Business logic. Services own transaction boundaries (commit/rollback). Named `{resource}_service.py`.
- `app/repositories/` — Data access. All extend `BaseRepo[ModelT]` which provides generic CRUD. Repositories **never call `session.commit()`** — only flush.
- `app/models/` — SQLAlchemy 2.0 declarative models. All use `BigIntTimestampMixin` for `created_time`/`updated_time` as Unix epoch integers.
- `app/schemas/` — Pydantic v2 request/response schemas.

**Key cross-cutting modules:**

- `app/api/deps.py` — FastAPI dependencies: `get_db()`, `get_current_user()`, `require_role()`, `require_permission()`, `require_engagement_member()`. Role hierarchy: Viewer(0) < Auditor(1) < Moderator(2) < Admin(3).
- `app/core/config.py` — `Settings` (pydantic-settings), loaded from `.env`. Singleton `settings` used throughout.
- `app/core/security.py` — bcrypt password hashing (cost 12), JWT access/refresh token creation and verification.
- `app/core/exceptions.py` — `AppException` base with subclasses (`NotFoundException`, `ConflictException`, `ForbiddenException`, `UnauthorizedException`). All return structured JSON `{"error": {"code", "message", "field"}}`.
- `app/db/base.py` — Model import hub. All models must be imported here for Alembic autogenerate to detect them.
- `app/db/session.py` — Async engine and session factory (`asyncpg`).
- `app/middleware/rate_limit.py` — Rate limiting middleware.
- `app/middleware/request_logging.py` — Request/response logging middleware.

**Infrastructure:**

- PostgreSQL 16 (via asyncpg), Azure Blob Storage (Azurite for local dev)
- Alembic for async migrations — `env.py` reads `DATABASE_URL` from app config, not `alembic.ini`
- Pre-commit hooks: black, ruff (with `--fix`), mypy
- Prometheus metrics exposed at `/metrics`, health check at `/health`

## Code Style

- Python 3.12, line length 100 (black + ruff)
- mypy strict mode with pydantic plugin
- ruff rules: E, F, W, I, N, UP, S, B, A, C4, SIM, TCH (S101 allowed in tests)
- All API routes prefixed `/api/v1/`

## Testing

- `tests/unit/` — Unit tests for services (auth, user, client, config_control, engagement_team, evidence, review_cycle, test_log).
- `tests/integration/` — Integration tests for API endpoints (auth, clients, users, evidence, review_cycles, rbac, pagination, engagement_scope, hardening, negative cases).
- `tests/conftest.py` — Shared fixtures.

## Environment

Copy `.env.example` to `.env`. Required vars: `DATABASE_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `AZURE_STORAGE_CONNECTION_STRING`.

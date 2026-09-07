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
poetry run python -m scripts.seed_arcelor_mittal_client   # POC client + its data paths

# Regenerate the completed TWP work paper from the client data
poetry run python -m scripts.build_twp_completed IA8.CA02 19A1

# Linting & formatting
poetry run black --check .
poetry run ruff check .
poetry run mypy .

# Tests
poetry run pytest
poetry run pytest tests/unit/
poetry run pytest tests/integration/
poetry run pytest -k "test_name"

# Prove the app still runs with no client data present
CLIENT_DATA_PATH=/nonexistent poetry run pytest
```

**Baseline:** the suite has 13 pre-existing failures unrelated to current work (evidence/test-log service mocks, cycle stats). Compare against that set rather than expecting green.

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

Copy `.env.example` to `.env` — it lists every setting the app reads, with the required ones marked. Required vars: `DATABASE_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, the agent-pipeline block (`DETAILED_JSONS_PATH`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `MODEL1`, `LITELLM_MODEL`, `LANGSMITH_*`), and `AZURE_STORAGE_CONNECTION_STRING` when `STORAGE_BACKEND=azure`.

### Client data

Control definitions, the evidence vault, testing outputs and report templates are **client-supplied**: they are not part of the application, and `CLIENT_DATA_PATH` is the single variable that locates them.

```
<CLIENT_DATA_PATH>/
  control_jsons/              control definitions, one JSON per control
  supporting_documents_dump/  evidence vault, one folder per control number
  test_outputs/               per-control testing output JSONs
  misc/                       report templates + config JSONs
    dummy_template.xlsm             empty TWP work paper
    twp_template_map.json           empty/completed TWP per control
    sampling_matrix.json            frequency x risk/round -> sample size
    sampling_metadata.json          per-control sampling reasoning
    evidence_filename_map.json      expected evidence filename per control
```

On the **`poc-2` branch this folder is committed as `poc-2-data/`** so the POC can be cloned and run as-is. That is a branch-specific choice — a real deployment points `CLIENT_DATA_PATH` at its own copy and leaves the folder untracked.

Each path (`CONTROL_JSONS_PATH`, `SUPPORTING_DOCS_PATH`, …) can be set individually to override the value derived from the root — see `app/core/config.py`. An explicit environment value always wins.

The app starts and runs without this data: every loader degrades to an empty result, the demo-vault static mount is skipped rather than aborting startup, and the affected screens come up blank. Tests that read the real files skip when it is absent (`tests/client_data.py`).

> Two files store paths **in their own contents** — `twp_template_map.json` and the seeded `clients.evidence_vault_path` / `control_jsons_path` columns. Renaming or relocating the folder means updating those too, not just the environment.

## POC-specific behaviour (Arcelor Mittal / `poc-2`)

This branch carries a client demo layered on the generic platform. The pieces worth knowing before changing anything here:

- **The testing-output JSON is the source of truth for verdicts.** `Run` in the Testing UI is a presentation-only reveal — it plays an executing state and then shows the result already stored in `test_outputs/`. Nothing is computed, and nothing is written back.
- **Per-sample evidence gating.** `check_evidence` judges each sample on *its own* uploads against `evidence_filename_map.json`; a valid file on a sibling sample never vouches for another. Messages are deliberately generic and must never reveal the expected filename. `get_evidence_pages` applies the same gate.
- **Matching is on content, not filenames.** `control_matching.py`, `test_output_matching.py` and `twp_templates.py` all resolve by control number + entity code read from the file, accept any extension, and degrade quietly when a file is missing or malformed. Follow that pattern for new client-data loaders.
- **Per-client isolation.** `Client.evidence_vault_path` / `control_jsons_path` scope each client to its own data, so the Signora seed client keeps working alongside the POC client.
- **`scripts/build_twp_completed.py`** regenerates the completed TWP work paper from the control JSON, sampling matrix and testing output. Re-run it after editing any of those.

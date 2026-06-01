"""Integration tests for hardening — security headers, rate limiting, health check."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_present(client):
    resp = await client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "max-age=" in resp.headers.get("Strict-Transport-Security", "")


@pytest.mark.asyncio
async def test_request_id_header(client):
    resp = await client.get("/health")
    assert resp.headers.get("X-Request-ID") is not None


@pytest.mark.asyncio
async def test_custom_request_id_echoed(client):
    resp = await client.get("/health", headers={"X-Request-ID": "test-req-123"})
    assert resp.headers.get("X-Request-ID") == "test-req-123"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "db" in data
    assert "azure" in data


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "http_request" in body or "http_requests" in body


# ---------------------------------------------------------------------------
# Validation error format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_error_format(client, seeded_users):
    """422 errors should return structured JSON per spec."""
    resp = await client.post(
        "/api/v1/users/create-user",
        json={},
        headers=seeded_users["Admin"]["headers"],
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
    assert data["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_has_required_routes(client):
    """Verify all expected routers are mounted."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    paths = list(spec.get("paths", {}).keys())
    assert any("/api/v1/auth/login-user" in p for p in paths)
    assert any("/api/v1/users" in p for p in paths)
    assert any("/api/v1/clients" in p for p in paths)
    assert any("/api/v1/review-cycles" in p for p in paths)
    assert any("/api/v1/controls" in p for p in paths)
    assert any("/api/v1/evidence" in p for p in paths)
    assert any("/api/v1/test-logs" in p for p in paths)

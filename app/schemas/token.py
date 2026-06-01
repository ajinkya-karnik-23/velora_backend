"""Token schemas for auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: int
    roles: list[str] = []
    permissions: list[str] = []

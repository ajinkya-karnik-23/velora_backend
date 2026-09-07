"""Client schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClientCreate(BaseModel):
    client_code: str = Field(..., max_length=255)
    client_name: str = Field(..., max_length=255)
    definition_scope: str
    reference_documents: str
    compliance_framework: str | None = Field(default=None, max_length=255)


class ClientUpdate(BaseModel):
    client_code: str | None = Field(default=None, max_length=255)
    client_name: str | None = Field(default=None, max_length=255)
    definition_scope: str | None = None
    reference_documents: str | None = None
    compliance_framework: str | None = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_id: int
    client_code: str
    client_name: str
    definition_scope: str
    reference_documents: str
    compliance_framework: str | None = None
    # Engagement size, so a client can be picked on substance rather than name
    # alone. Populated by the list endpoint; absent on single-client reads.
    review_cycle_count: int = 0
    control_count: int = 0
    created_time: int
    updated_time: int

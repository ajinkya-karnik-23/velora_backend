"""Evidence file schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceUpload(BaseModel):
    """Multipart upload metadata (file is supplied separately via UploadFile)."""

    cycle_id: int | None = None
    control_id: int | None = None
    test_id: int | None = None
    comments: str | None = None

    @model_validator(mode="after")
    def _at_least_one_linkage(self) -> "EvidenceUpload":
        if self.cycle_id is None and self.control_id is None and self.test_id is None:
            raise ValueError(
                "At least one of cycle_id, control_id, test_id must be provided."
            )
        return self


class EvidenceUpdate(BaseModel):
    comments: str | None = None
    cycle_id: int | None = None
    control_id: int | None = None
    test_id: int | None = None


class EvidenceStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(Approved|Rejected)$")
    comments: str | None = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: int
    file_name: str
    file_type: str | None = None
    file_size: int | None = None
    file_path: str | None = None
    upload_date: int
    uploaded_by: int
    uploader_name: str | None = None
    cycle_id: int | None = None
    engagement_name: str | None = None
    control_id: int | None = None
    control_number: str | None = None
    control_name: str | None = None
    test_id: int | None = None
    status: str
    comments: str | None = None
    file_version: int
    created_time: int
    updated_time: int


class EvidenceFilter(BaseModel):
    cycle_id: int | None = None
    control_id: int | None = None
    uploaded_by: int | None = None
    file_type: str | None = None
    status: str | None = None
    search: str | None = None


class EvidenceStats(BaseModel):
    total_count: int = 0
    total_size: int = 0
    by_file_type: dict[str, dict[str, int]] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)


class DemoVaultFile(BaseModel):
    control_number: str
    file_name: str
    file_size: int
    file_type: str
    uploader_name: str | None = None


class WorkflowStepOut(BaseModel):
    step: int
    name: str
    status: str


class WorkflowStatusOut(BaseModel):
    evidence_id: int
    current_step: int
    status: str
    result: str | None = None
    steps: list[WorkflowStepOut]

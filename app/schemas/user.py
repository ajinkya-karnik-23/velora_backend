"""User schemas for API request/response validation."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=10, max_length=128)
    phone: str | None = Field(default=None, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    job_title: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=255)
    profile_picture: str | None = Field(default=None, max_length=500)
    role_ids: list[int] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str, info) -> str:  # noqa: ANN001
        errors: list[str] = []
        if not re.search(r"[A-Z]", v):
            errors.append("at least 1 uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("at least 1 lowercase letter")
        if not re.search(r"\d", v):
            errors.append("at least 1 digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", v):
            errors.append("at least 1 special character")
        if errors:
            raise ValueError("Password must contain: " + ", ".join(errors))
        # Cannot match email or user_name
        data = info.data
        if data.get("email") and v.lower() == data["email"].lower():
            raise ValueError("Password cannot match email")
        if data.get("user_name") and v.lower() == data["user_name"].lower():
            raise ValueError("Password cannot match user name")
        return v


class UserUpdate(BaseModel):
    """Self-service fields. Admin-only fields (email, status) handled separately."""

    user_name: str | None = Field(default=None, max_length=255)
    phone: str | None = None
    department: str | None = None
    job_title: str | None = None
    location: str | None = None
    profile_picture: str | None = None


class UserAdminUpdate(UserUpdate):
    """Admin-only update — extends self-service fields with email and status."""

    email: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=50)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    user_name: str
    email: str
    phone: str | None = None
    department: str | None = None
    job_title: str | None = None
    location: str | None = None
    profile_picture: str | None = None
    status: str
    two_factor_enabled: bool
    api_access_enabled: bool
    last_login: int | None = None
    created_time: int
    updated_time: int
    roles: list[str] = []
    permissions: list[str] = []


class UserFilter(BaseModel):
    status: str | None = None
    department: str | None = None
    search: str | None = None

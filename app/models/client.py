"""Client model — maps to the ``clients`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntTimestampMixin


class Client(BigIntTimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (Index("ix_clients_client_name", "client_name"),)

    client_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_code: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition_scope: Mapped[str] = mapped_column(Text, nullable=False)
    reference_documents: Mapped[str] = mapped_column(Text, nullable=False)
    compliance_framework: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Filesystem root for this client's evidence vault — one folder per
    # control number underneath it. Falls back to settings.SUPPORTING_DOCS_PATH
    # when unset. Each client gets its own POD-style, isolated vault.
    evidence_vault_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Filesystem root for this client's control JSON definitions — one JSON
    # file per control, matched against uploaded control Excel filenames by
    # their shared "<code>.<code>.<code>" prefix. Falls back to
    # settings.CONTROL_JSONS_PATH when unset.
    control_jsons_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

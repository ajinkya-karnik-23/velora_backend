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

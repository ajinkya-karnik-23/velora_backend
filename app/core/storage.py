"""Storage dispatcher — routes to azure or local backend based on config."""

from __future__ import annotations

from typing import BinaryIO

from app.core.config import settings


def _backend():  # noqa: ANN202
    if settings.STORAGE_BACKEND == "local":
        from app.core import local_storage

        return local_storage
    from app.core import azure_storage

    return azure_storage


async def upload_blob(
    cycle_id: int,
    control_number: str,
    filename: str,
    stream: BinaryIO,
    content_type: str | None = None,
) -> str:
    return await _backend().upload_blob(cycle_id, control_number, filename, stream, content_type)


async def download_blob_content(
    cycle_id: int,
    control_number: str,
    filename: str,
) -> tuple[bytes, str]:
    return await _backend().download_blob_content(cycle_id, control_number, filename)


async def delete_blob(cycle_id: int, control_number: str, filename: str) -> None:
    await _backend().delete_blob(cycle_id, control_number, filename)


async def rename_blob(
    cycle_id: int,
    control_number: str,
    old_filename: str,
    new_filename: str,
) -> str:
    return await _backend().rename_blob(cycle_id, control_number, old_filename, new_filename)

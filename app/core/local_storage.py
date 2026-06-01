"""Local filesystem storage backend for evidence file management."""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _container_name() -> str:
    """Container name scoped by environment: ciq-evidence-{env}."""
    return f"{settings.AZURE_BLOB_CONTAINER}-{settings.APP_ENV}"


def _blob_path(cycle_id: int, control_number: str, filename: str) -> Path:
    """Build full filesystem path for a blob."""
    root = Path(settings.LOCAL_STORAGE_PATH)
    return root / _container_name() / str(cycle_id) / control_number / filename


async def upload_blob(
    cycle_id: int,
    control_number: str,
    filename: str,
    stream: BinaryIO,
    content_type: str | None = None,
) -> str:
    """Write a file stream to local disk. Returns the logical blob path."""
    dest = _blob_path(cycle_id, control_number, filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(stream.read())
    blob_name = f"{cycle_id}/{control_number}/{filename}"
    logger.info("local_blob_upload", operation="upload", blob_name=blob_name)
    return blob_name


async def download_blob_content(
    cycle_id: int,
    control_number: str,
    filename: str,
) -> tuple[bytes, str]:
    """Read a file from local disk. Returns (bytes, content_type)."""
    path = _blob_path(cycle_id, control_number, filename)
    content = path.read_bytes()
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    blob_name = f"{cycle_id}/{control_number}/{filename}"
    logger.info("local_blob_download", operation="download", blob_name=blob_name)
    return content, content_type


async def delete_blob(cycle_id: int, control_number: str, filename: str) -> None:
    """Delete a file from local disk."""
    path = _blob_path(cycle_id, control_number, filename)
    path.unlink(missing_ok=True)
    blob_name = f"{cycle_id}/{control_number}/{filename}"
    logger.info("local_blob_delete", operation="delete", blob_name=blob_name)


async def rename_blob(
    cycle_id: int,
    control_number: str,
    old_filename: str,
    new_filename: str,
) -> str:
    """Move a file on local disk. Used for archiving old evidence versions."""
    src = _blob_path(cycle_id, control_number, old_filename)
    dest = _blob_path(cycle_id, control_number, new_filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    new_name = f"{cycle_id}/{control_number}/{new_filename}"
    logger.info(
        "local_blob_rename",
        operation="rename",
        blob_name=f"{cycle_id}/{control_number}/{old_filename}",
        new_blob_name=new_name,
    )
    return new_name

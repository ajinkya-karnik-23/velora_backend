"""Azure Blob Storage wrapper for evidence file management."""

from __future__ import annotations

from typing import BinaryIO

from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    ExponentialRetry,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _container_name() -> str:
    """Container name scoped by environment: ciq-evidence-{env}."""
    return f"{settings.AZURE_BLOB_CONTAINER}-{settings.APP_ENV}"


def _get_blob_service_client() -> BlobServiceClient:
    """Create a BlobServiceClient with exponential backoff retry."""
    return BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING,
        retry_policy=ExponentialRetry(initial_backoff=1, increment_base=2, retry_total=3),
    )


def _blob_path(cycle_id: int, control_number: str, filename: str) -> str:
    """Build blob path: {cycle_id}/{control_number}/{filename}."""
    return f"{cycle_id}/{control_number}/{filename}"


async def upload_blob(
    cycle_id: int,
    control_number: str,
    filename: str,
    stream: BinaryIO,
    content_type: str | None = None,
) -> str:
    """Upload a file stream to Azure Blob Storage.

    Returns the blob path (not a full URL).
    """
    blob_name = _blob_path(cycle_id, control_number, filename)
    client = _get_blob_service_client()
    container_client = client.get_container_client(_container_name())

    # Ensure container exists
    try:
        container_client.create_container()
    except Exception:  # noqa: BLE001 — container may already exist
        pass

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        stream,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type) if content_type else None,
    )
    logger.info("azure_blob_upload", operation="upload", blob_name=blob_name)
    return blob_name


async def download_blob_content(
    cycle_id: int,
    control_number: str,
    filename: str,
) -> tuple[bytes, str]:
    """Download a blob and return its raw bytes and content-type.

    Replaces the previous SAS-URL approach which failed against Azurite's
    path-style emulator URLs due to canonical-resource signing differences.
    """
    blob_name = _blob_path(cycle_id, control_number, filename)
    client = _get_blob_service_client()
    blob_client = client.get_blob_client(_container_name(), blob_name)
    downloader = blob_client.download_blob()
    content: bytes = downloader.readall()
    properties = blob_client.get_blob_properties()
    content_type: str = (
        properties.content_settings.content_type or "application/octet-stream"
    )
    logger.info("azure_blob_download", operation="download", blob_name=blob_name)
    return content, content_type


async def delete_blob(cycle_id: int, control_number: str, filename: str) -> None:
    """Delete a blob from storage."""
    blob_name = _blob_path(cycle_id, control_number, filename)
    client = _get_blob_service_client()
    blob_client = client.get_blob_client(_container_name(), blob_name)
    blob_client.delete_blob()
    logger.info("azure_blob_delete", operation="delete", blob_name=blob_name)


async def rename_blob(
    cycle_id: int,
    control_number: str,
    old_filename: str,
    new_filename: str,
) -> str:
    """Rename (copy + delete) a blob. Used for archiving old evidence versions.

    Archive path: {cycle_id}/{control_number}/_archive/{timestamp}_{filename}
    """
    old_name = _blob_path(cycle_id, control_number, old_filename)
    new_name = _blob_path(cycle_id, control_number, new_filename)

    client = _get_blob_service_client()
    container_client = client.get_container_client(_container_name())

    source_blob = container_client.get_blob_client(old_name)
    dest_blob = container_client.get_blob_client(new_name)

    dest_blob.start_copy_from_url(source_blob.url)
    source_blob.delete_blob()

    logger.info(
        "azure_blob_rename",
        operation="rename",
        blob_name=old_name,
        new_blob_name=new_name,
    )
    return new_name

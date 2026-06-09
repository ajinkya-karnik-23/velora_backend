"""Evidence service — upload/approve/reject/download, Azure Blob integration."""

from __future__ import annotations

import time
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage as azure_storage
from app.core.exceptions import (
    AppException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.core.logging import get_logger
from app.models.evidence_file import EvidenceFile
from app.models.test_log import TestLog
from app.repositories.evidence_repo import EvidenceRepo
from app.schemas.evidence import EvidenceOut, EvidenceUpdate

logger = get_logger(__name__)

# File validation
ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/msword",  # doc
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "application/vnd.ms-excel",  # xls
    "image/png",
    "image/jpeg",
    "text/csv",
    "application/zip",
    "application/x-zip-compressed",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def _to_out(ev: EvidenceFile) -> EvidenceOut:
    return EvidenceOut(
        evidence_id=ev.evidence_id,
        file_name=ev.file_name,
        file_type=ev.file_type,
        file_size=ev.file_size,
        file_path=ev.file_path,
        upload_date=ev.upload_date,
        uploaded_by=ev.uploaded_by,
        uploader_name=ev.uploader.user_name if ev.uploader else None,
        cycle_id=ev.cycle_id,
        engagement_name=ev.review_cycle.name if ev.review_cycle else None,
        control_id=ev.control_id,
        control_number=ev.control.control_number if ev.control else None,
        control_name=ev.control.control_name if ev.control else None,
        test_id=ev.test_id,
        status=ev.status,
        comments=ev.comments,
        file_version=ev.file_version,
        created_time=ev.created_time,
        updated_time=ev.updated_time,
    )


class EvidenceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = EvidenceRepo(db)

    # ------------------------------------------------------------------ list

    async def list_evidence(
        self,
        filters: dict[str, Any],
        user_id: int,
        user_roles: list[str],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[EvidenceOut], int]:
        items, total = await self.repo.list_with_joins(
            filters, user_id, user_roles, page, page_size
        )
        return [_to_out(e) for e in items], total

    async def get_evidence(
        self, evidence_id: int, user_id: int, user_roles: list[str]
    ) -> EvidenceOut:
        ev = await self.repo.get_detail(evidence_id)
        if not ev:
            raise NotFoundException("Evidence not found.")
        await self._assert_scope(ev, user_id, user_roles)
        return _to_out(ev)

    async def get_stats(
        self, user_id: int, user_roles: list[str]
    ) -> dict[str, Any]:
        return await self.repo.get_stats(user_id, user_roles)

    async def get_vault(
        self, user_id: int, user_roles: list[str]
    ) -> list[dict[str, Any]]:
        return await self.repo.get_vault(user_id, user_roles)

    # ------------------------------------------------------------------ helpers (private)

    async def _control_number(self, control_id: int | None) -> str:
        """Resolve control_id → control_number for blob path construction."""
        if not control_id:
            return "uncategorized"
        from sqlalchemy import select
        from app.models.control_repository import ControlRepository
        result = await self.db.execute(
            select(ControlRepository.control_number).where(
                ControlRepository.control_id == control_id
            )
        )
        number = result.scalar_one_or_none()
        return number or str(control_id)

    # ------------------------------------------------------------------ upload

    async def upload(
        self,
        file: UploadFile,
        cycle_id: int | None,
        control_id: int | None,
        test_id: int | None,
        comments: str | None,
        current_user: dict[str, Any],
    ) -> EvidenceOut:
        # Validate MIME type
        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
            raise AppException(
                code="INVALID_FILE_TYPE",
                message=f"File type '{file.content_type}' is not allowed.",
                status_code=422,
            )

        # Read into memory and validate size
        content = await file.read()
        file_size = len(content)
        if file_size > MAX_FILE_SIZE:
            raise AppException(
                code="FILE_TOO_LARGE",
                message=f"File exceeds maximum size of {MAX_FILE_SIZE} bytes.",
                status_code=413,
            )

        now = int(time.time())
        user_id = int(current_user["sub"])

        # Step 1: INSERT evidence_files row (get PK for blob path)
        evidence = EvidenceFile(
            file_name=file.filename or "unnamed",
            file_type=file.content_type,
            file_size=file_size,
            upload_date=now,
            uploaded_by=user_id,
            cycle_id=cycle_id,
            control_id=control_id,
            test_id=test_id,
            status="Pending",
            comments=comments,
            file_version=1,
        )
        await self.repo.create(evidence)  # flush → materialise evidence_id

        # Step 2: Upload blob. On failure, rollback DB row.
        try:
            import io

            ctrl_number = await self._control_number(control_id)
            blob_path = await azure_storage.upload_blob(
                cycle_id=cycle_id or 0,
                control_number=ctrl_number,
                filename=evidence.file_name,
                stream=io.BytesIO(content),
                content_type=file.content_type,
            )
            evidence.file_path = blob_path
            await self.db.flush()
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            logger.error("evidence_upload_failed", error=str(exc))
            raise AppException(
                code="UPLOAD_FAILED",
                message="Failed to upload evidence file.",
                status_code=500,
            ) from exc

        # Re-fetch with joins
        fresh = await self.repo.get_detail(evidence.evidence_id)
        return _to_out(fresh) if fresh else _to_out(evidence)

    # ------------------------------------------------------------------ update

    async def update_metadata(
        self,
        evidence_id: int,
        data: EvidenceUpdate,
        current_user: dict[str, Any],
    ) -> EvidenceOut:
        ev = await self.repo.get_detail(evidence_id)
        if not ev:
            raise NotFoundException("Evidence not found.")
        self._assert_owner_or_privileged(ev, current_user)

        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if updates:
            await self.repo.update(ev, updates)
            await self.db.commit()
        fresh = await self.repo.get_detail(evidence_id)
        return _to_out(fresh) if fresh else _to_out(ev)

    async def approve_reject(
        self,
        evidence_id: int,
        status: str,
        comments: str | None,
        current_user: dict[str, Any],
    ) -> EvidenceOut:
        if status not in ("Approved", "Rejected"):
            raise AppException(
                code="INVALID_STATUS",
                message="Status must be 'Approved' or 'Rejected'.",
                status_code=400,
            )
        ev = await self.repo.get_detail(evidence_id)
        if not ev:
            raise NotFoundException("Evidence not found.")

        # Atomic: UPDATE evidence_files status → INSERT test_log
        ev.status = status
        if comments is not None:
            ev.comments = comments
        await self.db.flush()

        log = TestLog(
            test_id=ev.test_id,
            control_id=ev.control_id,
            cycle_id=ev.cycle_id,
            log_date=int(time.time()),
            changed_by=int(current_user["sub"]),
            status=status,
            notes=f"Evidence {evidence_id} {status.lower()}",
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.commit()

        fresh = await self.repo.get_detail(evidence_id)
        return _to_out(fresh) if fresh else _to_out(ev)

    # ------------------------------------------------------------------ re-upload

    async def reupload(
        self,
        evidence_id: int,
        file: UploadFile,
        current_user: dict[str, Any],
    ) -> EvidenceOut:
        ev = await self.repo.get_detail(evidence_id)
        if not ev:
            raise NotFoundException("Evidence not found.")
        self._assert_owner_or_privileged(ev, current_user)

        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
            raise AppException(
                code="INVALID_FILE_TYPE",
                message=f"File type '{file.content_type}' is not allowed.",
                status_code=422,
            )
        content = await file.read()
        file_size = len(content)
        if file_size > MAX_FILE_SIZE:
            raise AppException(
                code="FILE_TOO_LARGE",
                message="File exceeds maximum size.",
                status_code=413,
            )

        ctrl_number = ev.control.control_number if ev.control else "uncategorized"

        # Archive old blob
        if ev.file_path:
            archive_name = f"_archive/{int(time.time())}_{ev.file_name}"
            try:
                await azure_storage.rename_blob(
                    cycle_id=ev.cycle_id or 0,
                    control_number=ctrl_number,
                    old_filename=ev.file_name,
                    new_filename=archive_name,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("evidence_archive_failed", error=str(exc))

        # Upload new blob
        try:
            import io

            new_filename = file.filename or ev.file_name
            blob_path = await azure_storage.upload_blob(
                cycle_id=ev.cycle_id or 0,
                control_number=ctrl_number,
                filename=new_filename,
                stream=io.BytesIO(content),
                content_type=file.content_type,
            )
            ev.file_name = new_filename
            ev.file_type = file.content_type
            ev.file_size = file_size
            ev.file_path = blob_path
            ev.file_version = (ev.file_version or 1) + 1
            ev.upload_date = int(time.time())
            ev.status = "Pending"
            await self.db.flush()
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            raise AppException(
                code="UPLOAD_FAILED",
                message="Failed to re-upload evidence file.",
                status_code=500,
            ) from exc

        fresh = await self.repo.get_detail(evidence_id)
        return _to_out(fresh) if fresh else _to_out(ev)

    # ------------------------------------------------------------------ import demo file

    async def import_demo(
        self,
        control_number: str,
        filename: str,
        cycle_id: int | None,
        control_id: int | None,
        test_id: int | None,
        current_user: dict[str, Any],
    ) -> EvidenceOut:
        from pathlib import Path
        import mimetypes, io

        demo_vault = (
            Path(__file__).parent / "evidence_vault" / "demo_data"
        )
        safe_path = (demo_vault / control_number / filename).resolve()
        if not str(safe_path).startswith(str(demo_vault.resolve())):
            raise AppException(code="INVALID_PATH", message="Invalid path.", status_code=400)
        if not safe_path.exists() or not safe_path.is_file():
            raise AppException(code="NOT_FOUND", message="Demo file not found.", status_code=404)

        content = safe_path.read_bytes()
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        now = int(time.time())
        user_id = int(current_user["sub"])

        evidence = EvidenceFile(
            file_name=filename,
            file_type=mime,
            file_size=len(content),
            upload_date=now,
            uploaded_by=user_id,
            cycle_id=cycle_id,
            control_id=control_id,
            test_id=test_id,
            status="Pending",
            comments=None,
            file_version=1,
        )
        await self.repo.create(evidence)

        try:
            ctrl_number = await self._control_number(control_id) if control_id else control_number
            blob_path = await azure_storage.upload_blob(
                cycle_id=cycle_id or 0,
                control_number=ctrl_number,
                filename=filename,
                stream=io.BytesIO(content),
                content_type=mime,
            )
            evidence.file_path = blob_path
            await self.db.flush()
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            logger.error("demo_import_failed", error=str(exc))
            raise AppException(
                code="UPLOAD_FAILED",
                message="Failed to import demo file.",
                status_code=500,
            ) from exc

        fresh = await self.repo.get_detail(evidence.evidence_id)
        return _to_out(fresh) if fresh else _to_out(evidence)

    # ------------------------------------------------------------------ delete

    async def delete(self, evidence_id: int, current_user: dict[str, Any]) -> None:
        roles = current_user.get("roles", [])
        if "Admin" not in roles:
            raise ForbiddenException("Only Admin can delete evidence.")
        ev = await self.repo.get_detail(evidence_id)
        if not ev:
            raise NotFoundException("Evidence not found.")

        ctrl_number = ev.control.control_number if ev.control else "uncategorized"

        # Delete blob first (best-effort)
        if ev.file_path:
            try:
                await azure_storage.delete_blob(
                    cycle_id=ev.cycle_id or 0,
                    control_number=ctrl_number,
                    filename=ev.file_name,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("evidence_blob_delete_failed", error=str(exc))

        await self.repo.delete(ev)
        await self.db.commit()

    # ------------------------------------------------------------------ download

    async def download_stream(
        self, evidence_id: int, user_id: int, user_roles: list[str]
    ) -> tuple[bytes, str, str]:
        """Return (file_bytes, content_type, file_name) for streaming to client."""
        ev = await self.repo.get_detail(evidence_id)
        if not ev:
            raise NotFoundException("Evidence not found.")
        await self._assert_scope(ev, user_id, user_roles)
        if not ev.file_path:
            raise ConflictException("Evidence has no associated file.")
        ctrl_number = ev.control.control_number if ev.control else "uncategorized"
        content, content_type = await azure_storage.download_blob_content(
            cycle_id=ev.cycle_id or 0,
            control_number=ctrl_number,
            filename=ev.file_name,
        )
        return content, content_type, ev.file_name

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _assert_owner_or_privileged(
        ev: EvidenceFile, current_user: dict[str, Any]
    ) -> None:
        roles = current_user.get("roles", [])
        if "Admin" in roles or "Moderator" in roles:
            return
        if ev.uploaded_by == int(current_user["sub"]):
            return
        raise ForbiddenException("Not the owner of this evidence.")

    async def _assert_scope(
        self, ev: EvidenceFile, user_id: int, user_roles: list[str]
    ) -> None:
        """Auditor/Viewer may only access evidence for cycles they are members of."""
        if any(r in ("Admin", "Moderator") for r in user_roles):
            return
        if ev.cycle_id is None:
            if ev.uploaded_by != user_id:
                raise ForbiddenException("Not authorised for this evidence.")
            return
        from app.repositories.engagement_team_repo import EngagementTeamRepo

        team_repo = EngagementTeamRepo(self.db)
        if not await team_repo.is_member(ev.cycle_id, user_id):
            raise ForbiddenException("Not a member of this engagement.")

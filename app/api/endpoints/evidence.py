"""Evidence endpoints — upload, list, approve/reject, download SAS."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_db,
    require_engagement_member,
    require_permission,
)
from app.core.exceptions import ForbiddenException
from app.schemas.common import PaginatedResponse
from app.schemas.evidence import (
    DemoFileImport,
    DemoVaultFile,
    EvidenceOut,
    EvidenceStatusUpdate,
    EvidenceUpdate,
    WorkflowStatusOut,
    WorkflowStepOut,
)

# Absolute path to the static demo_data folder
_DEMO_VAULT = Path(__file__).parent.parent.parent / "services" / "evidence_vault" / "demo_data"
from app.services.evidence_service import EvidenceService

router = APIRouter()


# ---------------------------------------------------------------------------
# Listing & stats
# ---------------------------------------------------------------------------


@router.get("/list-evidence", response_model=PaginatedResponse[EvidenceOut])
async def list_evidence(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    cycle_id: int | None = None,
    control_id: int | None = None,
    test_id: int | None = None,
    uploaded_by: int | None = None,
    file_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = EvidenceService(db)
    filters: dict[str, Any] = {}
    for k, v in {
        "cycle_id": cycle_id,
        "control_id": control_id,
        "test_id": test_id,
        "uploaded_by": uploaded_by,
        "file_type": file_type,
        "status": status,
        "search": search,
    }.items():
        if v is not None:
            filters[k] = v
    items, total = await service.list_evidence(
        filters,
        int(current_user["sub"]),
        current_user.get("roles", []),
        page,
        page_size,
    )
    return {"data": items, "total": total, "page": page, "page_size": page_size}


@router.get("/get-evidence-stats")
async def get_evidence_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    service = EvidenceService(db)
    return await service.get_stats(
        int(current_user["sub"]), current_user.get("roles", [])
    )


@router.get("/get-evidence-vault")
async def get_evidence_vault(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    service = EvidenceService(db)
    return await service.get_vault(
        int(current_user["sub"]), current_user.get("roles", [])
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload-evidence", response_model=EvidenceOut, status_code=201)
async def upload_evidence(
    file: UploadFile = File(...),
    cycle_id: int | None = Form(default=None),
    control_id: int | None = Form(default=None),
    test_id: int | None = Form(default=None),
    comments: str | None = Form(default=None),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> EvidenceOut:
    if cycle_id is None and control_id is None and test_id is None:
        from app.core.exceptions import AppException

        raise AppException(
            code="MISSING_LINKAGE",
            message="At least one of cycle_id, control_id, test_id must be provided.",
            status_code=422,
        )
    # Engagement membership enforcement when cycle_id present
    if cycle_id is not None:
        roles = current_user.get("roles", [])
        if not any(r in ("Admin", "Moderator") for r in roles):
            from app.repositories.engagement_team_repo import EngagementTeamRepo

            team_repo = EngagementTeamRepo(db)
            if not await team_repo.is_member(cycle_id, int(current_user["sub"])):
                raise ForbiddenException("Not a member of this engagement.")

    service = EvidenceService(db)
    return await service.upload(
        file=file,
        cycle_id=cycle_id,
        control_id=control_id,
        test_id=test_id,
        comments=comments,
        current_user=current_user,
    )


# ---------------------------------------------------------------------------
# Single-evidence operations
# ---------------------------------------------------------------------------


@router.get("/get-evidence", response_model=EvidenceOut)
async def get_evidence(
    evidence_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceOut:
    service = EvidenceService(db)
    return await service.get_evidence(
        evidence_id, int(current_user["sub"]), current_user.get("roles", [])
    )


@router.put("/update-evidence", response_model=EvidenceOut)
async def update_evidence(
    evidence_id: int = Query(...),
    data: EvidenceUpdate = Body(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceOut:
    service = EvidenceService(db)
    return await service.update_metadata(evidence_id, data, current_user)


@router.put("/reupload-evidence", response_model=EvidenceOut)
async def reupload_evidence(
    evidence_id: int = Query(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> EvidenceOut:
    service = EvidenceService(db)
    return await service.reupload(evidence_id, file, current_user)


@router.put("/update-evidence-status", response_model=EvidenceOut)
async def approve_reject_evidence(
    evidence_id: int = Query(...),
    data: EvidenceStatusUpdate = Body(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvidenceOut:
    # Permission: can_approve or can_reject depending on status
    perms = current_user.get("permissions", [])
    needed = "can_approve" if data.status == "Approved" else "can_reject"
    if needed not in perms:
        raise ForbiddenException(f"Missing permission: {needed}.")
    service = EvidenceService(db)
    return await service.approve_reject(
        evidence_id, data.status, data.comments, current_user
    )


@router.delete("/delete-evidence", status_code=204, response_model=None)
async def delete_evidence(
    evidence_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = EvidenceService(db)
    await service.delete(evidence_id, current_user)


@router.get("/download-evidence")
async def download_evidence(
    evidence_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = EvidenceService(db)
    content, content_type, file_name = await service.download_stream(
        evidence_id, int(current_user["sub"]), current_user.get("roles", [])
    )
    safe_name = file_name.replace('"', "")
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# ---------------------------------------------------------------------------
# Workflow status (dummy)
# ---------------------------------------------------------------------------

WORKFLOW_STEPS = [
    "Uploading Evidence File",
    "Linking to Control Record",
    "Running Compliance Checks",
    "Cross-referencing Frameworks",
    "Generating Test Report",
    "Evidence Processing Complete",
]


# ---------------------------------------------------------------------------
# Demo Vault — static file browser of evidence_vault/demo_data
# ---------------------------------------------------------------------------


_DEMO_UPLOADERS = [
    "Sarah Mitchell",
    "James Chen",
    "Priya Sharma",
    "Tom O'Brien",
    "Lisa Kowalski",
    "Arun Nair",
    "Emma Walsh",
]


@router.get("/demo-vault", response_model=list[DemoVaultFile])
async def list_demo_vault(
    current_user: dict = Depends(get_current_user),  # noqa: ARG001
) -> list[DemoVaultFile]:
    """Return all files in the demo_data folder, organised by control number."""
    files: list[DemoVaultFile] = []
    if not _DEMO_VAULT.exists():
        return files
    for control_dir in sorted(_DEMO_VAULT.iterdir()):
        if not control_dir.is_dir() or control_dir.name.startswith("."):
            continue
        uploader = _DEMO_UPLOADERS[abs(hash(control_dir.name)) % len(_DEMO_UPLOADERS)]
        for file in sorted(control_dir.iterdir()):
            if not file.is_file() or file.name.startswith("."):
                continue
            mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            files.append(DemoVaultFile(
                control_number=control_dir.name,
                file_name=file.name,
                file_size=file.stat().st_size,
                file_type=mime,
                uploader_name=uploader,
            ))
    return files


@router.post("/import-demo-file", response_model=EvidenceOut, status_code=201)
async def import_demo_file(
    data: DemoFileImport,
    current_user: dict = Depends(require_permission("can_upload")),
    db: AsyncSession = Depends(get_db),
) -> EvidenceOut:
    """Copy a demo vault file into real evidence storage and link it."""
    service = EvidenceService(db)
    return await service.import_demo(
        control_number=data.control_number,
        filename=data.filename,
        cycle_id=data.cycle_id,
        control_id=data.control_id,
        test_id=data.test_id,
        current_user=current_user,
    )


@router.get("/demo-vault/download")
async def download_demo_vault_file(
    control_number: str = Query(...),
    filename: str = Query(...),
    current_user: dict = Depends(get_current_user),  # noqa: ARG001
) -> FileResponse:
    """Stream a file from the demo_data folder."""
    # Prevent path traversal
    safe_path = (_DEMO_VAULT / control_number / filename).resolve()
    if not str(safe_path).startswith(str(_DEMO_VAULT.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path.")
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path=str(safe_path), filename=filename)


@router.get("/{evidence_id}/workflow-status", response_model=WorkflowStatusOut)
async def get_workflow_status(
    evidence_id: int,
    current_user: dict = Depends(get_current_user),  # noqa: ARG001
) -> WorkflowStatusOut:
    """Return dummy workflow status for the given evidence (all steps completed)."""
    return WorkflowStatusOut(
        evidence_id=evidence_id,
        current_step=6,
        status="completed",
        result="approved",
        steps=[
            WorkflowStepOut(step=i + 1, name=name, status="completed")
            for i, name in enumerate(WORKFLOW_STEPS)
        ],
    )

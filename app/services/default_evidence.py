"""Attach a control's known evidence on request, so demo testing is ready to run.

Configured in the client's `default_evidence_map.json`, per control number and
entity. From the Testing tab an auditor attaches, for one attached control,
every mapped file its samples do not yet hold, one row per sample. Nothing is
removed or replaced: a file counts as present when the same test and sample
already hold a file of that name, whoever uploaded it.

The files go through the same storage path as a normal upload, so they
download, gate and run exactly like hand-uploaded evidence.
"""

from __future__ import annotations

import asyncio
import io
import json
import mimetypes
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core import storage
from app.core.config import settings
from app.core.logging import get_logger
from app.models.control_repository import ControlRepository
from app.models.control_test import ControlTest
from app.models.evidence_file import EvidenceFile
from app.services.evidence_verification import expected_filename_for_sample, load_filename_rule
from app.services.test_output_matching import build_samples, find_test_output

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.config_control import ConfigControl

logger = get_logger(__name__)

AUTO_COMMENT = "Attached from default evidence"

# One run at a time: a double click must not attach the same files twice.
_lock = asyncio.Lock()


def load_map(map_path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [c for c in payload.get("controls") or [] if isinstance(c, dict)]


def _sample_fields(sample: dict[str, Any]) -> dict[str, Any]:
    fields = {k: v for k, v in sample.items() if k != "parameters"}
    for param in sample.get("parameters") or []:
        if param.get("label"):
            fields[param["label"]] = param.get("value")
    return fields


def planned_files(entry: dict[str, Any], sample: dict[str, Any]) -> list[Path]:
    """The source files one sample should hold, per the map entry."""
    source = Path(str(entry.get("source_dir") or ""))
    mode = entry.get("files_from")
    if mode == "fixed":
        name = str(entry.get("file") or "").strip()
        return [source / name] if name else []
    if mode == "filename_rule":
        rule = load_filename_rule(
            Path(settings.EVIDENCE_FILENAME_MAP_PATH),
            str(entry.get("control_number")),
            entry.get("entity_code"),
        )
        name = expected_filename_for_sample(rule, _sample_fields(sample)) if rule else None
        return [source / name] if name else []
    if mode == "evidences_used":
        folder = source
        field = entry.get("folder_field")
        if field:
            value = _sample_fields(sample).get(field)
            if not value:
                return []
            folder = source / str(value).strip()
        names = [str(n).strip() for n in sample.get("evidences_used") or []]
        return [folder / n for n in dict.fromkeys(names) if n]
    return []


class DefaultEvidencePlan:
    """What default evidence one attached control has, and what it lacks."""

    def __init__(self) -> None:
        self.configured = False
        self.planned = 0
        # (sample_no, source path) not yet attached and present on disk.
        self.missing: list[tuple[int, Path]] = []
        # Mapped but absent from disk, so they cannot be attached.
        self.unavailable = 0


def _entry_for(control_number: str, entity_code: str | None) -> dict[str, Any] | None:
    for entry in load_map(Path(settings.DEFAULT_EVIDENCE_MAP_PATH)):
        if str(entry.get("control_number") or "").strip() != control_number.strip():
            continue
        mapped_entity = str(entry.get("entity_code") or "").strip()
        if mapped_entity and mapped_entity != (entity_code or "").strip():
            continue
        return entry
    return None


async def _test_id(db: AsyncSession, config_control_id: int) -> int | None:
    return (
        await db.execute(
            select(ControlTest.test_id)
            .where(ControlTest.config_control_id == config_control_id)
            .order_by(ControlTest.test_id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def plan_default_evidence(db: AsyncSession, cc: ConfigControl) -> DefaultEvidencePlan:
    plan = DefaultEvidencePlan()
    control = await db.get(ControlRepository, cc.control_id)
    if control is None:
        return plan
    entry = _entry_for(control.control_number, cc.entity_code)
    test_id = await _test_id(db, cc.config_control_id)
    payload = find_test_output(
        Path(settings.TEST_OUTPUTS_PATH), control.control_number, cc.entity_code
    )
    if entry is None or test_id is None or payload is None:
        return plan
    plan.configured = True

    present = {
        (row.sample_no, row.file_name.strip().lower())
        for row in (
            await db.execute(
                select(EvidenceFile.sample_no, EvidenceFile.file_name).where(
                    EvidenceFile.test_id == test_id
                )
            )
        ).all()
    }
    for i, sample in enumerate(build_samples(payload)):
        raw = sample.get("sample_no")
        sample_no = raw if isinstance(raw, int) else i + 1
        for path in planned_files(entry, sample):
            plan.planned += 1
            if (sample_no, path.name.strip().lower()) in present:
                continue
            if not path.is_file():
                plan.unavailable += 1
                continue
            plan.missing.append((sample_no, path))
    return plan


async def attach_one_default_evidence(
    db: AsyncSession, cc: ConfigControl, user_id: int, sample_no: int, file_name: str
) -> bool:
    """Attach a single missing mapped file. False when it is not missing
    (already attached, unmapped, or absent from disk), so a repeated call is
    harmless."""
    async with _lock:
        plan = await plan_default_evidence(db, cc)
        wanted = (sample_no, file_name.strip().lower())
        match = next(
            (item for item in plan.missing if (item[0], item[1].name.strip().lower()) == wanted),
            None,
        )
        if match is None:
            return False
        control = await db.get(ControlRepository, cc.control_id)
        test_id = await _test_id(db, cc.config_control_id)
        if control is None or test_id is None:
            return False
        await _attach(db, cc, control.control_number, test_id, match[0], match[1], user_id)
        return True


async def attach_default_evidence(
    db: AsyncSession, cc: ConfigControl, user_id: int
) -> DefaultEvidencePlan:
    """Attach every missing mapped file for one attached control.

    Returns the plan as it stood before attaching; `len(plan.missing)` files
    were attached. Serialised so a double click cannot attach twice.
    """
    async with _lock:
        plan = await plan_default_evidence(db, cc)
        if not plan.missing:
            return plan
        control = await db.get(ControlRepository, cc.control_id)
        test_id = await _test_id(db, cc.config_control_id)
        if control is None or test_id is None:
            return plan
        for sample_no, path in plan.missing:
            await _attach(db, cc, control.control_number, test_id, sample_no, path, user_id)
        logger.info(
            "default_evidence_attached",
            config_control_id=cc.config_control_id,
            count=len(plan.missing),
        )
        return plan


async def _attach(
    db: AsyncSession,
    cc: ConfigControl,
    control_number: str,
    test_id: int,
    sample_no: int,
    path: Path,
    user_id: int,
) -> None:
    content = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    now = int(time.time())
    evidence = EvidenceFile(
        file_name=path.name,
        file_type=mime,
        file_size=len(content),
        upload_date=now,
        uploaded_by=user_id,
        cycle_id=cc.cycle_id,
        control_id=cc.control_id,
        test_id=test_id,
        sample_no=sample_no,
        status="Pending",
        comments=AUTO_COMMENT,
        file_version=1,
    )
    db.add(evidence)
    await db.flush()
    evidence.file_path = await storage.upload_blob(
        cycle_id=cc.cycle_id,
        control_number=control_number,
        filename=path.name,
        stream=io.BytesIO(content),
        content_type=mime,
    )
    await db.commit()

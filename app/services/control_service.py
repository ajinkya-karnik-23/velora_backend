"""Control service — browse catalog, get detail, get changelog. Read-only in V1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, NotFoundException
from app.models.client import Client
from app.models.control_repository import ControlRepository
from app.models.version import Version
from app.repositories.control_change_log_repo import ControlChangeLogRepo
from app.repositories.control_repo import ControlRepo
from app.schemas.control import ChangeLogOut, ControlOut
from app.services.control_matching import (
    GROUP_CODE_SEGMENTS,
    extract_control_code,
    find_control_json_by_control_no,
    list_available_entities,
    load_control_json,
)


def _to_out(ctrl: ControlRepository) -> ControlOut:
    return ControlOut(
        **{c.key: getattr(ctrl, c.key) for c in ctrl.__table__.columns},
        owner_name=ctrl.owner.user_name if ctrl.owner else None,
        fccg_contact_name=ctrl.fccg_contact.user_name if ctrl.fccg_contact else None,
        frameworks=[fw.framework_name for fw in ctrl.frameworks],
    )


class ControlService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ControlRepo(db)
        self.changelog_repo = ControlChangeLogRepo(db)

    async def browse(
        self,
        filters: dict[str, Any],
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ControlOut], int]:
        controls, total = await self.repo.browse_with_frameworks(filters, page, page_size)
        return [_to_out(c) for c in controls], total

    async def get_detail(self, control_id: int) -> ControlOut:
        ctrl = await self.repo.get_detail(control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")
        return _to_out(ctrl)

    async def get_changelog(self, control_id: int) -> list[ChangeLogOut]:
        # Verify control exists
        ctrl = await self.repo.get_by_id(control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")
        logs = await self.changelog_repo.get_by_control(control_id)
        return [
            ChangeLogOut(
                **{c.key: getattr(log, c.key) for c in log.__table__.columns},
                changer_name=log.changer.user_name if log.changer else None,
                from_version_name=(
                    log.version_from.version_name if log.version_from else None
                ),
                to_version_name=(
                    log.version_to.version_name if log.version_to else None
                ),
            )
            for log in logs
        ]

    # ------------------------------------------------------------------ upload from control JSON

    async def upload_from_control_json(
        self,
        filename: str,
        client_id: int,
        current_user: dict[str, Any],
    ) -> ControlOut:
        """Match an uploaded control Excel's filename to its definition JSON.

        The Excel content itself is never parsed — only its filename's
        leading "<code>.<code>" group prefix is used as a search key. That
        key is matched against each control JSON's own
        control_details["Control No"] (not the JSON's filename, which isn't
        reliably 3-segment or even ".json" in real client exports). The
        matched JSON becomes (or updates) one ControlRepository row for this
        client — entity-specific detail is resolved later, per review
        cycle, at attach time.
        """
        client = await self.db.get(Client, client_id)
        if client is None:
            raise NotFoundException("Client not found.")

        search_code = extract_control_code(filename, num_segments=GROUP_CODE_SEGMENTS)
        if search_code is None:
            raise AppException(
                code="INVALID_FILENAME",
                message=(
                    "Uploaded filename must start with a "
                    "'<code>.<code>' prefix, e.g. 'IA8.CA02...'."
                ),
                status_code=422,
            )

        control_jsons_dir = Path(client.control_jsons_path or settings.CONTROL_JSONS_PATH)
        json_path = find_control_json_by_control_no(control_jsons_dir, search_code)
        if json_path is None:
            raise NotFoundException(
                f"No control definition found matching code '{search_code}'."
            )

        payload = load_control_json(json_path)
        details = payload.get("control_details", {}) or {}
        rcm = payload.get("rcm_details", {}) or {}
        # Authoritative control number comes from the JSON's own field, not
        # the search key — they're equal by construction of the match above.
        control_number = str(details.get("Control No", "")).strip() or search_code

        version_result = await self.db.execute(
            select(Version).where(Version.is_current.is_(True))
        )
        version = version_result.scalar_one_or_none()
        user_id = int(current_user["sub"])

        fields: dict[str, Any] = {
            "control_number": control_number,
            "client_id": client_id,
            "version_id": version.version_id if version else None,
            "control_name": details.get("Control Name") or control_number,
            "reference_number": details.get("Control Reference") or None,
            "entity": (
                details.get("Entity Code") or details.get("Region Name") or "Unknown"
            ),
            "control_desc": details.get("Control Description") or "",
            "domain": details.get("Category of the Process") or None,
            "frequency": rcm.get("Frequency") or "Unknown",
            "risk_level": rcm.get("Risk Level") or "Unknown",
            "pwc_reliance": rcm.get("Ext. Auditor Reliance") or None,
            "control_owner": user_id,
            "units_fccg_contact": user_id,
            "source_json": payload,
        }

        existing = await self.repo.get(
            {"client_id": client_id, "control_number": control_number}
        )
        if existing:
            ctrl = await self.repo.update(existing[0], fields)
        else:
            ctrl = await self.repo.create(ControlRepository(**fields))

        await self.db.commit()
        fresh = await self.repo.get_detail(ctrl.control_id)
        return _to_out(fresh) if fresh else _to_out(ctrl)

    async def list_entities(self, client_id: int) -> list[str]:
        """Entities (site codes) available in this client's control_jsons."""
        client = await self.db.get(Client, client_id)
        if client is None:
            raise NotFoundException("Client not found.")
        control_jsons_dir = Path(client.control_jsons_path or settings.CONTROL_JSONS_PATH)
        return list_available_entities(control_jsons_dir)

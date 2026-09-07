"""Config control service — attach/detach controls to cycles (atomic)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.client import Client
from app.models.config_control import ConfigControl
from app.models.control_repository import ControlRepository
from app.models.control_test import ControlTest
from app.models.evidence_file import EvidenceFile
from app.models.review_cycle import ReviewCycle
from app.repositories.config_control_repo import ConfigControlRepo
from app.repositories.control_repo import ControlRepo
from app.repositories.control_test_repo import ControlTestRepo
from app.schemas.config_control import (
    ConfigControlOut,
    ControlTestOutputOut,
    EvidenceCheckOut,
    SampleSizeResultOut,
    TestMethodology,
)
from app.services.control_matching import (
    find_control_json_by_control_and_entity,
    load_control_json,
)
from app.services.sampling_matrix import (
    calculate_sample_size,
    extract_control_parameters,
    load_sampling_matrix,
    load_sampling_notes,
)
from app.services.evidence_verification import (
    build_methodology,
    extract_pages,
    filename_matches,
    load_expected_filename,
)
from app.services.test_output_matching import build_samples, find_test_output


logger = get_logger(__name__)

# Deliberately generic — never reveals the expected filename.
EVIDENCE_NOT_UPLOADED_MESSAGE = (
    "No evidence has been uploaded for this control yet. "
    "Upload the supporting evidence to begin testing."
)

EVIDENCE_MISMATCH_MESSAGE = (
    "The appropriate evidence for this control was not found. "
    "Please review the evidence uploaded and try again."
)


def _to_out(cc: ConfigControl) -> ConfigControlOut:
    ctrl = cc.control
    test = cc.test
    return ConfigControlOut(
        config_control_id=cc.config_control_id,
        cycle_id=cc.cycle_id,
        control_id=cc.control_id,
        control_number=ctrl.control_number if ctrl else None,
        control_name=ctrl.control_name if ctrl else None,
        domain=ctrl.domain if ctrl else None,
        risk_level=ctrl.risk_level if ctrl else None,
        frequency=ctrl.frequency if ctrl else None,
        status=ctrl.status if ctrl else None,
        test_id=test.test_id if test else None,
        tests=test.tests if test else None,
        note=test.note if test else None,
        comments=test.comments if test else None,
        entity_code=cc.entity_code,
        entity_detail_json=cc.entity_detail_json,
        sample_size=cc.sample_size,
        sample_size_source=cc.sample_size_source,
        created_time=cc.created_time,
        updated_time=cc.updated_time,
    )


class ConfigControlService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ConfigControlRepo(db)
        self.control_repo = ControlRepo(db)
        self.test_repo = ControlTestRepo(db)
        from app.services.evidence_service import EvidenceService

        self.evidence_service = EvidenceService(db)

    async def _seed_tests(self, config_control_id: int, control_id: int) -> None:
        """Populate ControlTest rows from the cycle-independent ControlTestTemplate table.
        Uses source_test_id from the template so IDs always match the detailed JSONs.
        Falls back to one blank row (auto-increment) only if no templates exist."""
        templates = await self.test_repo.get_templates_for_control(control_id)
        if templates:
            for tmpl in templates:
                kwargs: dict = {
                    "config_control_id": config_control_id,
                    "tests": tmpl.tests,
                    "note": tmpl.note,
                    "comments": tmpl.comments,
                }
                if tmpl.source_test_id is not None:
                    kwargs["test_id"] = tmpl.source_test_id
                self.db.add(ControlTest(**kwargs))
        else:
            self.db.add(ControlTest(config_control_id=config_control_id))
        await self.db.flush()

    async def _resolve_entity_detail(
        self, cycle_id: int, ctrl: ControlRepository
    ) -> tuple[str | None, dict | None]:
        """If the cycle has an entity_code, resolve control_number + entity
        against the client's control_jsons to pull that entity's rcm_details.

        Returns (entity_code, detail_json) — detail_json is None if the
        cycle has no entity, or if no matching JSON is found on disk (not
        fatal — attaching still proceeds without the entity snapshot).
        """
        cycle = await self.db.get(ReviewCycle, cycle_id)
        if cycle is None or not cycle.entity_code:
            return None, None

        client = await self.db.get(Client, cycle.client_id)
        if client is None:
            return cycle.entity_code, None

        control_jsons_dir = Path(client.control_jsons_path or settings.CONTROL_JSONS_PATH)
        json_path = find_control_json_by_control_and_entity(
            control_jsons_dir, ctrl.control_number, cycle.entity_code
        )
        if json_path is None:
            return cycle.entity_code, None
        return cycle.entity_code, load_control_json(json_path)

    async def get_cycle_controls(self, cycle_id: int) -> list[ConfigControlOut]:
        ccs = await self.repo.get_cycle_controls(cycle_id)
        return [_to_out(cc) for cc in ccs]

    async def attach_control(self, cycle_id: int, control_id: int) -> ConfigControlOut:
        # Verify control exists
        ctrl = await self.control_repo.get_by_id(control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")
        # Check duplicate
        existing = await self.repo.get_by_cycle_and_control(cycle_id, control_id)
        if existing:
            raise ConflictException("Control is already attached to this cycle.")
        entity_code, entity_detail = await self._resolve_entity_detail(cycle_id, ctrl)
        cc = ConfigControl(
            cycle_id=cycle_id,
            control_id=control_id,
            entity_code=entity_code,
            entity_detail_json=entity_detail,
        )
        await self.repo.create(cc)  # flush materialises config_control_id
        await self._seed_tests(cc.config_control_id, control_id)
        await self.db.commit()
        # Re-fetch with joins
        ccs = await self.repo.get_cycle_controls(cycle_id)
        for item in ccs:
            if item.control_id == control_id:
                return _to_out(item)
        return _to_out(cc)  # fallback

    async def bulk_attach(self, cycle_id: int, control_ids: list[int]) -> list[ConfigControlOut]:
        for control_id in control_ids:
            ctrl = await self.control_repo.get_by_id(control_id)
            if not ctrl:
                raise NotFoundException(f"Control {control_id} not found.")
            existing = await self.repo.get_by_cycle_and_control(cycle_id, control_id)
            if existing:
                continue  # skip duplicates in bulk
            entity_code, entity_detail = await self._resolve_entity_detail(cycle_id, ctrl)
            cc = ConfigControl(
                cycle_id=cycle_id,
                control_id=control_id,
                entity_code=entity_code,
                entity_detail_json=entity_detail,
            )
            await self.repo.create(cc)
            await self._seed_tests(cc.config_control_id, control_id)
        await self.db.commit()
        return await self.get_cycle_controls(cycle_id)

    async def calculate_sample_size(self, config_control_id: int) -> SampleSizeResultOut:
        """Determine an attached control's sample size.

        Reads the control's Risk Level, Frequency and Phase of control (from
        the entity-specific attributes when present, else the repository
        record), resolves them against the sampling methodology matrix, and
        falls back to the sample size defined on the control itself when the
        matrix has no applicable mapping.

        Returns the attributes alongside the result so the UI can show what
        the determination was based on.
        """
        cc = await self.repo.get_by_id(config_control_id)
        if not cc:
            raise NotFoundException("Attached control not found.")

        ctrl = await self.control_repo.get_by_id(cc.control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")

        # Re-read the control's definition from disk so an edited definition
        # is picked up on re-determination. The stored snapshot is only a
        # fallback for when the definition can no longer be found on disk.
        _entity, live_detail = await self._resolve_entity_detail(cc.cycle_id, ctrl)
        if live_detail is not None and live_detail != cc.entity_detail_json:
            cc.entity_detail_json = live_detail

        attributes = live_detail or cc.entity_detail_json or ctrl.source_json or {}
        params = extract_control_parameters(attributes)

        matrix = load_sampling_matrix(Path(settings.SAMPLING_MATRIX_PATH))
        value = calculate_sample_size(
            matrix,
            risk_level=params["risk_level"],
            frequency=params["frequency"],
            phase=params["phase"],
        )
        source = "matrix"
        if value is None:
            value = params["fallback_sample_size"]
            source = "control_definition"
        if value is None:
            raise AppException(
                code="SAMPLE_SIZE_UNAVAILABLE",
                message=(
                    "Could not determine a sample size: the control's attributes "
                    "have no applicable mapping in the sampling methodology matrix, "
                    "and no sample size is defined on the control."
                ),
                status_code=422,
            )

        cc.sample_size = value
        cc.sample_size_source = source
        await self.db.flush()
        await self.db.commit()

        notes = load_sampling_notes(
            Path(settings.SAMPLING_METADATA_PATH), ctrl.control_number, cc.entity_code
        )

        return SampleSizeResultOut(
            config_control_id=cc.config_control_id,
            control_number=ctrl.control_number,
            entity_code=cc.entity_code,
            frequency=params["frequency"],
            risk_level=params["risk_level"],
            phase=params["phase"],
            frequency_note=notes["frequency"],
            risk_level_note=notes["risk_level"],
            phase_note=notes["phase"],
            sample_size=value,
            sample_size_source=source,
        )

    async def get_test_output(self, config_control_id: int) -> ControlTestOutputOut:
        """The control's testing output — header, IPE name, and sample rows.

        Samples are generated from the output JSON's test_details, so the
        row count always follows the data rather than any fixed number.
        Returns an empty sample list when no output file exists yet.
        """
        cc = await self.repo.get_by_id(config_control_id)
        if not cc:
            raise NotFoundException("Attached control not found.")

        ctrl = await self.control_repo.get_by_id(cc.control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")

        source_json = cc.entity_detail_json or ctrl.source_json or {}
        rcm = source_json.get("rcm_details") or {}
        # "IPE Name of Report" is often a descriptive report name; when it is
        # just a Yes/No flag fall back to the generic "IPE" label.
        raw_ipe = str(rcm.get("IPE Name of Report") or "").strip()
        ipe_name = raw_ipe if raw_ipe.lower() not in ("", "yes", "no") else "IPE"

        tests = await self.test_repo.get_by_config_control(cc.config_control_id)
        test_id = tests[0].test_id if tests else None

        payload = find_test_output(
            Path(settings.TEST_OUTPUTS_PATH), ctrl.control_number, cc.entity_code
        )
        if payload is None:
            return ControlTestOutputOut(
                config_control_id=cc.config_control_id,
                control_number=ctrl.control_number,
                entity_code=cc.entity_code,
                ipe_name=ipe_name,
                test_id=test_id,
                samples=[],
            )

        header = payload.get("control_test_output") or {}
        samples = build_samples(payload)
        await self._annotate_evidence_status(cc, ctrl, test_id, samples)
        return ControlTestOutputOut(
            config_control_id=cc.config_control_id,
            control_number=header.get("control_number") or ctrl.control_number,
            entity_code=header.get("entity_code") or cc.entity_code,
            phase_of_control=header.get("phase_of_control"),
            summary=header.get("summary"),
            ipe_name=ipe_name,
            test_id=test_id,
            methodology=TestMethodology(**build_methodology(samples)),
            samples=samples,
        )

    async def get_cycle_test_outputs(self, cycle_id: int) -> list[ControlTestOutputOut]:
        """Testing output for every control attached to a cycle.

        One request instead of one per control, so the dashboards that
        aggregate across the whole cycle (Overview, Controls) read exactly
        the same sample data the Testing table works from.
        """
        ccs = await self.repo.get_cycle_controls(cycle_id)
        return [await self.get_test_output(cc.config_control_id) for cc in ccs]

    # ------------------------------------------------------------ evidence gating

    async def _evidence_by_sample(self, test_id: int | None) -> dict[int, list[EvidenceFile]]:
        """This test's uploads, grouped by the sample row they belong to."""
        if test_id is None:
            return {}
        rows = (
            (await self.db.execute(select(EvidenceFile).where(EvidenceFile.test_id == test_id)))
            .scalars()
            .all()
        )
        grouped: dict[int, list[EvidenceFile]] = {}
        for ev in rows:
            if ev.sample_no is not None:
                grouped.setdefault(ev.sample_no, []).append(ev)
        return grouped

    async def _annotate_evidence_status(
        self,
        cc: ConfigControl,
        ctrl: ControlRepository,
        test_id: int | None,
        samples: list[dict],
    ) -> None:
        """Stamp each sample with the standing of its own evidence.

        Judged per sample, so a correct upload on one row never vouches for
        another. Mutates `samples` in place.
        """
        expected = load_expected_filename(
            Path(settings.EVIDENCE_FILENAME_MAP_PATH),
            ctrl.control_number,
            cc.entity_code,
        )
        grouped = await self._evidence_by_sample(test_id)

        for i, sample in enumerate(samples):
            raw = sample.get("sample_no")
            sample_no = raw if isinstance(raw, int) else i + 1
            files = grouped.get(sample_no, [])
            if not files:
                sample["evidence_status"] = "missing"
            elif not expected:
                # Control isn't filename-gated — any upload satisfies it.
                sample["evidence_status"] = "ok"
            elif any(filename_matches(f.file_name, expected) for f in files):
                sample["evidence_status"] = "ok"
            else:
                sample["evidence_status"] = "invalid"

    async def check_evidence(self, config_control_id: int) -> EvidenceCheckOut:
        """Whether this control's uploaded evidence permits test execution.

        Validation is per sample: a sample passes only when evidence attached
        to *that sample* matches the filename mapped for the control. Evidence
        sitting on a sibling sample never vouches for it — otherwise one
        correct upload would clear the whole control.

        `ok` reports the control as a whole (false only when nothing valid was
        uploaded anywhere); `invalid_samples` names the individual rows that
        have evidence which fails the check. Controls with no mapping are not
        gated. The response never names the expected file.
        """
        cc = await self.repo.get_by_id(config_control_id)
        if not cc:
            raise NotFoundException("Attached control not found.")
        ctrl = await self.control_repo.get_by_id(cc.control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")

        expected = load_expected_filename(
            Path(settings.EVIDENCE_FILENAME_MAP_PATH),
            ctrl.control_number,
            cc.entity_code,
        )
        if not expected:
            return EvidenceCheckOut(ok=True)

        tests = await self.test_repo.get_by_config_control(cc.config_control_id)
        test_id = tests[0].test_id if tests else None
        if test_id is None:
            return EvidenceCheckOut(
                ok=False, message=EVIDENCE_NOT_UPLOADED_MESSAGE, reason="no_evidence"
            )

        rows = (
            (await self.db.execute(select(EvidenceFile).where(EvidenceFile.test_id == test_id)))
            .scalars()
            .all()
        )

        # Group each sample's uploads, then judge each sample on its own files.
        by_sample: dict[int, list[EvidenceFile]] = {}
        for ev in rows:
            if ev.sample_no is not None:
                by_sample.setdefault(ev.sample_no, []).append(ev)

        invalid = sorted(
            sample_no
            for sample_no, files in by_sample.items()
            if not any(filename_matches(f.file_name, expected) for f in files)
        )
        any_valid = any(filename_matches(ev.file_name, expected) for ev in rows)

        if any_valid:
            return EvidenceCheckOut(ok=True, invalid_samples=invalid)

        # Nothing uploaded at all is the normal starting state, not a failure —
        # saying "the appropriate evidence was not found" there reads as though
        # the wrong file was supplied.
        if not rows:
            return EvidenceCheckOut(
                ok=False, message=EVIDENCE_NOT_UPLOADED_MESSAGE, reason="no_evidence"
            )
        return EvidenceCheckOut(
            ok=False,
            message=EVIDENCE_MISMATCH_MESSAGE,
            reason="mismatch",
            invalid_samples=invalid,
        )

    async def get_evidence_pages(
        self, config_control_id: int, sample_no: int
    ) -> tuple[bytes, str, str]:
        """Evidence for one sample, trimmed to the pages it was validated on.

        Returns (content, media_type, filename). Non-PDF evidence is returned
        as-is, since page extraction only applies to PDFs.
        """
        cc = await self.repo.get_by_id(config_control_id)
        if not cc:
            raise NotFoundException("Attached control not found.")
        ctrl = await self.control_repo.get_by_id(cc.control_id)
        if not ctrl:
            raise NotFoundException("Control not found.")

        payload = find_test_output(
            Path(settings.TEST_OUTPUTS_PATH), ctrl.control_number, cc.entity_code
        )
        pages: list[int] = []
        if payload:
            for sample in build_samples(payload):
                if str(sample.get("sample_no")) == str(sample_no):
                    pages = [p for p in sample.get("pages", []) if isinstance(p, int)]
                    break

        tests = await self.test_repo.get_by_config_control(cc.config_control_id)
        test_id = tests[0].test_id if tests else None
        rows = (
            (
                await self.db.execute(
                    select(EvidenceFile)
                    .where(EvidenceFile.test_id == test_id)
                    .order_by(EvidenceFile.upload_date)
                )
            )
            .scalars()
            .all()
            if test_id is not None
            else []
        )

        # Only this sample's own evidence may be served for it. Falling back to
        # a sibling's file would show pages the sample was never tested against.
        own = [e for e in rows if e.sample_no == sample_no]

        # The same filename gate that governs execution also governs viewing —
        # unverified evidence is never served, whichever route asks for it.
        expected = load_expected_filename(
            Path(settings.EVIDENCE_FILENAME_MAP_PATH),
            ctrl.control_number,
            cc.entity_code,
        )
        if expected:
            own = [e for e in own if filename_matches(e.file_name, expected)]
            if not own:
                raise AppException(
                    code="EVIDENCE_NOT_VERIFIED",
                    message=EVIDENCE_MISMATCH_MESSAGE,
                    status_code=422,
                )

        source = own[0] if own else None
        if source is None:
            raise NotFoundException("No evidence uploaded for this sample.")

        try:
            content, content_type, file_name = await self.evidence_service.download_stream(
                source.evidence_id, 0, ["Admin"]
            )
        except FileNotFoundError as exc:
            # The record survives but its stored file does not — most often
            # because storage was cleared out from under the uploads. Say so
            # plainly rather than surfacing a 500.
            logger.warning(
                "evidence_blob_missing",
                evidence_id=source.evidence_id,
                sample_no=sample_no,
            )
            raise AppException(
                code="EVIDENCE_FILE_MISSING",
                message=(
                    "The stored evidence for this sample is no longer available. "
                    "Please re-upload the evidence and try again."
                ),
                status_code=422,
            ) from exc

        is_pdf = (content_type or "").lower() == "application/pdf" or file_name.lower().endswith(
            ".pdf"
        )
        if not is_pdf:
            # Page-level review only means something for a PDF; returning the
            # raw bytes here would silently show the wrong thing.
            raise AppException(
                code="EVIDENCE_NOT_PDF",
                message=(
                    "The evidence for this control is not a PDF, so specific pages "
                    "cannot be displayed. Please upload the PDF evidence and try again."
                ),
                status_code=422,
            )

        if pages:
            try:
                content = extract_pages(content, pages)
                file_name = f"{Path(file_name).stem}_pages_{'-'.join(map(str, pages))}.pdf"
            except Exception as exc:  # noqa: BLE001
                # A malformed PDF shouldn't block viewing the original.
                logger.warning("evidence_page_extract_failed", error=str(exc))

        return content, content_type or "application/pdf", file_name

    async def detach_control(self, cycle_id: int, control_id: int) -> None:
        cc = await self.repo.get_by_cycle_and_control(cycle_id, control_id)
        if not cc:
            raise NotFoundException("Control is not attached to this cycle.")
        await self.repo.delete(cc)
        await self.db.commit()

    async def bulk_detach(self, cycle_id: int, config_control_ids: list[int]) -> None:
        for cc_id in config_control_ids:
            cc = await self.repo.get_by_id(cc_id)
            if cc and cc.cycle_id == cycle_id:
                await self.repo.delete(cc)
        await self.db.commit()

    async def reset_cycle_controls(self, cycle_id: int) -> None:
        ccs = await self.repo.get_cycle_controls(cycle_id)
        for cc in ccs:
            await self.repo.delete(cc)
        await self.db.commit()

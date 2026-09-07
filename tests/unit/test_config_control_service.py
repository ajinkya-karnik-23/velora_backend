"""Unit tests for ConfigControlService."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.services.config_control_service import ConfigControlService


@pytest.fixture
def db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service(db):
    return ConfigControlService(db)


def _mock_config_control():
    cc = MagicMock()
    cc.config_control_id = 1
    cc.cycle_id = 1
    cc.control_id = 10
    cc.created_time = int(time.time())
    cc.updated_time = int(time.time())
    cc.control = MagicMock(
        control_number="CTRL-001",
        control_name="Test Control",
        domain="IT",
        risk_level="High",
        frequency="Annual",
        status="Active",
    )
    cc.test = MagicMock(test_id=1, tests=None, note=None, comments=None)
    return cc


@pytest.mark.asyncio
async def test_attach_control_success(service):
    service.control_repo.get_by_id = AsyncMock(return_value=MagicMock())
    service.repo.get_by_cycle_and_control = AsyncMock(return_value=None)
    service.repo.create = AsyncMock(return_value=MagicMock(config_control_id=1))

    cc = _mock_config_control()
    service.repo.get_cycle_controls = AsyncMock(return_value=[cc])

    result = await service.attach_control(1, 10)
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_attach_control_not_found(service):
    service.control_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="Control not found"):
        await service.attach_control(1, 999)


@pytest.mark.asyncio
async def test_attach_control_duplicate(service):
    service.control_repo.get_by_id = AsyncMock(return_value=MagicMock())
    service.repo.get_by_cycle_and_control = AsyncMock(return_value=MagicMock())

    with pytest.raises(ConflictException, match="already attached"):
        await service.attach_control(1, 10)


@pytest.mark.asyncio
async def test_detach_control_success(service):
    service.repo.get_by_cycle_and_control = AsyncMock(return_value=MagicMock())
    service.repo.delete = AsyncMock()

    await service.detach_control(1, 10)
    service.repo.delete.assert_awaited_once()
    service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_detach_control_not_found(service):
    service.repo.get_by_cycle_and_control = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="not attached"):
        await service.detach_control(1, 999)


@pytest.mark.asyncio
async def test_bulk_attach_skips_duplicates(service):
    service.control_repo.get_by_id = AsyncMock(return_value=MagicMock())
    # First not attached, second already attached
    service.repo.get_by_cycle_and_control = AsyncMock(
        side_effect=[None, MagicMock()]
    )
    service.repo.create = AsyncMock(return_value=MagicMock(config_control_id=1))
    service.repo.get_cycle_controls = AsyncMock(return_value=[_mock_config_control()])

    result = await service.bulk_attach(1, [10, 20])
    # Only one create call (second skipped)
    assert service.repo.create.call_count == 1


@pytest.mark.asyncio
async def test_bulk_attach_control_not_found(service):
    service.control_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(NotFoundException, match="Control 999 not found"):
        await service.bulk_attach(1, [999])


# ── Per-sample evidence validation ────────────────────────────────────────────


class TestPerSampleEvidenceValidation:
    """A correct upload on one sample must never vouch for another.

    This is the rule that stops a control-wide check from passing every sample
    just because a single valid file exists somewhere under the test.
    """

    EXPECTED = "Correct.pdf"

    def _evidence(self, sample_no: int, file_name: str):
        return MagicMock(sample_no=sample_no, file_name=file_name)

    def _wire(self, service, rows, monkeypatch, expected=EXPECTED):
        cc = MagicMock(config_control_id=1, control_id=10, cycle_id=1, entity_code="19A1")
        ctrl = MagicMock(control_number="IA8.CA02")
        service.repo.get_by_id = AsyncMock(return_value=cc)
        service.control_repo.get_by_id = AsyncMock(return_value=ctrl)
        service.test_repo.get_by_config_control = AsyncMock(
            return_value=[MagicMock(test_id=18)]
        )

        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        service.db.execute = AsyncMock(return_value=result)

        monkeypatch.setattr(
            "app.services.config_control_service.load_expected_filename",
            lambda *_a, **_k: expected,
        )
        return cc, ctrl

    @pytest.mark.asyncio
    async def test_sibling_evidence_does_not_vouch_for_a_bad_sample(
        self, service, monkeypatch
    ):
        # Sample 1 holds the wrong file; samples 2 and 3 hold the right one.
        rows = [
            self._evidence(1, "holiday-photo.jpg"),
            self._evidence(2, self.EXPECTED),
            self._evidence(3, self.EXPECTED),
        ]
        self._wire(service, rows, monkeypatch)

        out = await service.check_evidence(1)

        # The control as a whole is workable, but sample 1 is called out.
        assert out.ok is True
        assert out.invalid_samples == [1]

    @pytest.mark.asyncio
    async def test_all_samples_wrong_fails_the_control(self, service, monkeypatch):
        rows = [self._evidence(1, "a.jpg"), self._evidence(2, "b.txt")]
        self._wire(service, rows, monkeypatch)

        out = await service.check_evidence(1)

        assert out.ok is False
        assert out.invalid_samples == [1, 2]
        # The generic message must never name the expected file.
        assert self.EXPECTED not in (out.message or "")

    @pytest.mark.asyncio
    async def test_sample_with_a_valid_file_alongside_junk_passes(
        self, service, monkeypatch
    ):
        rows = [self._evidence(1, "notes.txt"), self._evidence(1, self.EXPECTED)]
        self._wire(service, rows, monkeypatch)

        out = await service.check_evidence(1)

        assert out.ok is True
        assert out.invalid_samples == []

    @pytest.mark.asyncio
    async def test_ungated_control_accepts_anything(self, service, monkeypatch):
        rows = [self._evidence(1, "whatever.bin")]
        self._wire(service, rows, monkeypatch, expected=None)

        out = await service.check_evidence(1)

        assert out.ok is True
        assert out.invalid_samples == []

    @pytest.mark.asyncio
    async def test_annotate_marks_each_sample_independently(self, service, monkeypatch):
        rows = [
            self._evidence(1, "wrong.jpg"),
            self._evidence(2, self.EXPECTED),
        ]
        cc, ctrl = self._wire(service, rows, monkeypatch)

        # Sample 3 has no upload at all.
        samples = [{"sample_no": 1}, {"sample_no": 2}, {"sample_no": 3}]
        await service._annotate_evidence_status(cc, ctrl, 18, samples)

        assert [s["evidence_status"] for s in samples] == ["invalid", "ok", "missing"]

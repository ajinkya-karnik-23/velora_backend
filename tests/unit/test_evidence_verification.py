"""Unit tests for evidence gating, page extraction, and methodology counts."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from app.core.config import settings
from app.services.evidence_verification import (
    build_methodology,
    extract_pages,
    filename_matches,
    load_expected_filename,
)
from tests.client_data import requires_client_data

MAP_PAYLOAD = {
    "controls": [
        {
            "control_number": "IA8.CA02",
            "entity_code": "19A1",
            "expected_evidence_filename": "IA8.CA02.19A1.Evidence.pdf",
        }
    ]
}


def _pdf(pages: int) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


class TestLoadExpectedFilename:
    def _write(self, tmp_path: Path, payload: dict) -> Path:
        f = tmp_path / "evidence_filename_map.json"
        f.write_text(json.dumps(payload))
        return f

    def test_returns_mapped_filename(self, tmp_path: Path):
        f = self._write(tmp_path, MAP_PAYLOAD)
        assert load_expected_filename(f, "IA8.CA02", "19A1") == "IA8.CA02.19A1.Evidence.pdf"

    def test_unmapped_control_returns_none(self, tmp_path: Path):
        f = self._write(tmp_path, MAP_PAYLOAD)
        assert load_expected_filename(f, "NO.SUCH", "19A1") is None

    def test_wrong_entity_returns_none(self, tmp_path: Path):
        f = self._write(tmp_path, MAP_PAYLOAD)
        assert load_expected_filename(f, "IA8.CA02", "20B2") is None

    def test_missing_or_malformed_file_returns_none(self, tmp_path: Path):
        assert load_expected_filename(tmp_path / "nope.json", "IA8.CA02", "19A1") is None
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert load_expected_filename(bad, "IA8.CA02", "19A1") is None


class TestFilenameMatches:
    def test_exact_match(self):
        assert filename_matches("Evidence.pdf", "Evidence.pdf")

    def test_case_insensitive(self):
        assert filename_matches("EVIDENCE.PDF", "evidence.pdf")

    def test_folder_path_is_ignored(self):
        assert filename_matches("/tmp/uploads/Evidence.pdf", "Evidence.pdf")

    def test_mismatch_rejected(self):
        assert not filename_matches("Other.pdf", "Evidence.pdf")

    def test_unmapped_control_passes(self):
        # No expectation means the control isn't gated on filename.
        assert filename_matches("anything.pdf", None)

    def test_missing_upload_fails_when_expected(self):
        assert not filename_matches(None, "Evidence.pdf")


class TestExtractPages:
    def test_extracts_only_requested_pages(self):
        out = extract_pages(_pdf(30), [18, 20, 23, 25])
        assert len(PdfReader(io.BytesIO(out)).pages) == 4

    def test_out_of_range_pages_are_skipped(self):
        out = extract_pages(_pdf(30), [29, 30, 999])
        assert len(PdfReader(io.BytesIO(out)).pages) == 2

    def test_empty_page_list_returns_original(self):
        src = _pdf(5)
        assert extract_pages(src, []) == src

    def test_all_pages_out_of_range_returns_original(self):
        src = _pdf(3)
        assert extract_pages(src, [50, 60]) == src


class TestBuildMethodology:
    def _sample(self, type_value: str) -> dict:
        return {"parameters": [{"label": "Type", "value": type_value}]}

    def test_counts_nr_versus_manual(self):
        samples = [self._sample("KR")] * 24 + [self._sample("SA")] + [self._sample("NR")] * 2
        m = build_methodology(samples)
        assert m["total_samples"] == 27
        assert m["manual_entries"] == 25
        assert m["nr_entries"] == 2
        assert m["methodology"] == "NR & Manual Journal Entry testing"

    def test_type_match_is_case_insensitive(self):
        m = build_methodology([self._sample("nr"), self._sample(" NR ")])
        assert m["nr_entries"] == 2

    def test_samples_without_a_type_count_as_manual(self):
        m = build_methodology([{"parameters": []}])
        assert m["manual_entries"] == 1
        assert m["nr_entries"] == 0

    def test_empty_sample_set(self):
        m = build_methodology([])
        assert m["total_samples"] == 0


@requires_client_data
class TestRealClientData:
    """The shipped testing output should yield the documented figures."""

    def test_real_output_yields_27_25_2(self):
        from app.services.test_output_matching import build_samples, find_test_output

        payload = find_test_output(Path(settings.TEST_OUTPUTS_PATH), "IA8.CA02", "19A1")
        assert payload is not None
        m = build_methodology(build_samples(payload))
        assert (m["total_samples"], m["manual_entries"], m["nr_entries"]) == (27, 25, 2)

    def test_real_mapping_file_parses(self):
        expected = load_expected_filename(
            Path(settings.EVIDENCE_FILENAME_MAP_PATH), "IA8.CA02", "19A1"
        )
        assert expected is not None

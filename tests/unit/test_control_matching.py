"""Unit tests for control-JSON content matching.

An uploaded control Excel's filename supplies a "<code>.<code>" search key
(we never parse the Excel itself). That key — and later, a review cycle's
entity_code — is matched against each control JSON's own CONTENT
(control_details["Control No"] / ["Entity Code"]), not the JSON's filename.

Real client exports are not reliably 3-segment or even ".json"
(e.g. "IA5.CA03.1.19A1.DE.Control.txt" has an extra sub-index segment before
the entity, and a ".txt" extension) — these tests cover exactly that shape
alongside the cleaner "IA8.CA02.19A1.DE.Control.json" case.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.control_matching import (
    extract_control_code,
    find_control_json_by_control_and_entity,
    find_control_json_by_control_no,
    iter_control_jsons,
    list_available_entities,
    load_control_json,
)

IA8_PAYLOAD = {
    "control_details": {
        "Control No": "IA8.CA02",
        "Entity Code": "19A1",
        "Control Name": "NR and Manual JV",
    },
    "rcm_details": {"Frequency": "Upon Occurrence", "Risk Level": "Low"},
}

# Real-world shape: filename has a sub-index ("1") between control and
# entity segments, and a .txt extension — Control No is still clean.
IA5_PAYLOAD = {
    "control_details": {
        "Control No": "IA5.CA03",
        "Entity Code": "19A1",
        "Control Name": "Review of Credit Limits",
    },
    "rcm_details": {"Frequency": "Monthly", "Risk Level": "Medium"},
}


class TestExtractControlCode:
    def test_extracts_two_segment_code_from_excel_filename(self):
        assert (
            extract_control_code("IA8.CA02.19A1.DE.2026 NR and Manual JV.xlsm")
            == "IA8.CA02"
        )

    def test_two_segment_code_unaffected_by_extra_segments_after_it(self):
        # The sub-index ("1") and entity ("19A1") come after the group code —
        # extracting only the first 2 segments is unaffected by them.
        assert extract_control_code("IA5.CA03.1.19A1.DE.Control.xlsm") == "IA5.CA03"

    def test_returns_none_when_fewer_than_two_segments(self):
        assert extract_control_code("TooFewSegments.xlsx") is None

    def test_custom_segment_count(self):
        assert extract_control_code("A.B.C.D.Control.json", num_segments=4) == "A.B.C.D"


class TestIterControlJsons:
    def test_finds_files_regardless_of_extension(self, tmp_path: Path):
        d = tmp_path / "control_jsons"
        d.mkdir()
        (d / "IA8.CA02.19A1.DE.Control.txt").write_text(json.dumps(IA8_PAYLOAD))
        (d / "IA5.CA03.1.19A1.DE.Control.json").write_text(json.dumps(IA5_PAYLOAD))
        found = iter_control_jsons(d)
        assert len(found) == 2

    def test_skips_files_that_are_not_valid_json(self, tmp_path: Path):
        d = tmp_path / "control_jsons"
        d.mkdir()
        (d / "IA8.CA02.19A1.DE.Control.txt").write_text(json.dumps(IA8_PAYLOAD))
        (d / "README.txt").write_text("this is not json at all")
        (d / "empty.json").write_text("{}")  # valid JSON, but no control_details
        found = iter_control_jsons(d)
        assert len(found) == 1
        assert found[0][1] == IA8_PAYLOAD

    def test_skips_dotfiles(self, tmp_path: Path):
        d = tmp_path / "control_jsons"
        d.mkdir()
        (d / ".DS_Store").write_bytes(b"")
        (d / "IA8.CA02.19A1.DE.Control.txt").write_text(json.dumps(IA8_PAYLOAD))
        found = iter_control_jsons(d)
        assert len(found) == 1

    def test_empty_when_directory_missing(self, tmp_path: Path):
        assert iter_control_jsons(tmp_path / "does_not_exist") == []


class TestFindControlJsonByControlNo:
    @pytest.fixture
    def control_jsons_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "control_jsons"
        d.mkdir()
        (d / "IA8.CA02.19A1.DE.Control.txt").write_text(json.dumps(IA8_PAYLOAD))
        (d / "IA5.CA03.1.19A1.DE.Control.txt").write_text(json.dumps(IA5_PAYLOAD))
        return d

    def test_matches_by_content_not_filename(self, control_jsons_dir: Path):
        match = find_control_json_by_control_no(control_jsons_dir, "IA5.CA03")
        assert match is not None
        assert match.name == "IA5.CA03.1.19A1.DE.Control.txt"

    def test_txt_extension_is_matched(self, control_jsons_dir: Path):
        match = find_control_json_by_control_no(control_jsons_dir, "IA8.CA02")
        assert match is not None

    def test_end_to_end_upload_filename_resolves_by_content(
        self, control_jsons_dir: Path
    ):
        uploaded_filename = "IA5.CA03.1.19A1.DE.2026 Credit Limits.xlsm"
        code = extract_control_code(uploaded_filename)
        assert code == "IA5.CA03"
        match = find_control_json_by_control_no(control_jsons_dir, code)
        assert match is not None
        assert match.name == "IA5.CA03.1.19A1.DE.Control.txt"

    def test_returns_none_when_no_control_no_matches(self, control_jsons_dir: Path):
        assert find_control_json_by_control_no(control_jsons_dir, "NO.SUCH") is None


class TestFindControlJsonByControlAndEntity:
    @pytest.fixture
    def control_jsons_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "control_jsons"
        d.mkdir()
        (d / "IA5.CA03.1.19A1.DE.Control.txt").write_text(json.dumps(IA5_PAYLOAD))
        other_entity = {**IA5_PAYLOAD, "control_details": {**IA5_PAYLOAD["control_details"], "Entity Code": "20B2"}}
        (d / "IA5.CA03.1.20B2.DE.Control.txt").write_text(json.dumps(other_entity))
        return d

    def test_resolves_the_right_entity_despite_sub_index_in_filename(
        self, control_jsons_dir: Path
    ):
        # This is exactly the case filename-position parsing got wrong: the
        # entity is "19A1", not the sub-index "1" that sits before it.
        match = find_control_json_by_control_and_entity(
            control_jsons_dir, "IA5.CA03", "19A1"
        )
        assert match is not None
        assert match.name == "IA5.CA03.1.19A1.DE.Control.txt"

    def test_different_entity_resolves_to_different_file(self, control_jsons_dir: Path):
        match = find_control_json_by_control_and_entity(
            control_jsons_dir, "IA5.CA03", "20B2"
        )
        assert match is not None
        assert match.name == "IA5.CA03.1.20B2.DE.Control.txt"

    def test_wrong_entity_does_not_match(self, control_jsons_dir: Path):
        assert (
            find_control_json_by_control_and_entity(control_jsons_dir, "IA5.CA03", "ZZZZ")
            is None
        )


class TestListAvailableEntities:
    def test_lists_unique_sorted_entities_from_content(self, tmp_path: Path):
        d = tmp_path / "control_jsons"
        d.mkdir()
        (d / "IA8.CA02.19A1.DE.Control.txt").write_text(json.dumps(IA8_PAYLOAD))
        (d / "IA5.CA03.1.19A1.DE.Control.txt").write_text(json.dumps(IA5_PAYLOAD))
        other_entity = {**IA5_PAYLOAD, "control_details": {**IA5_PAYLOAD["control_details"], "Entity Code": "20B2"}}
        (d / "IA5.CA03.1.20B2.DE.Control.txt").write_text(json.dumps(other_entity))
        # The sub-index "1" must NOT leak into the entity list.
        assert list_available_entities(d) == ["19A1", "20B2"]

    def test_empty_when_directory_missing(self, tmp_path: Path):
        assert list_available_entities(tmp_path / "does_not_exist") == []


class TestLoadControlJson:
    def test_loads_and_parses_json_content(self, tmp_path: Path):
        f = tmp_path / "CTRL.json"
        f.write_text(json.dumps(IA8_PAYLOAD))
        assert load_control_json(f) == IA8_PAYLOAD

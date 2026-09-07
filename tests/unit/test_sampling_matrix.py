"""Unit tests for sampling-size calculation from the sampling matrix.

Frequency picks the matrix row; the column is picked by the control's phase
when that phase names a testing round (RF/RM/YE), otherwise by risk level.
Any miss returns None so the caller can fall back to the control JSON's own
"Sample Size".
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.sampling_matrix import (
    calculate_sample_size,
    extract_control_parameters,
    load_sampling_matrix,
    load_sampling_notes,
    resolve_column,
)

from app.core.config import settings
from tests.client_data import requires_client_data

MATRIX = {
    "Sampling Methodology": {
        "Operating Effectiveness Testing": {
            "Annual": {
                "Risk Rating conclusion Low": None,
                "Risk Rating Conclusion Medium": None,
                "Risk Rating Conclusion High": None,
                "RF (Full test)": None,
                "RM": 1,
                "YE": 1,
            },
            "Monthly": {
                "Risk Rating conclusion Low": None,
                "Risk Rating Conclusion Medium": "2 to 5",
                "Risk Rating Conclusion High": None,
                "RF (Full test)": 1,
                "RM": 2,
                "YE": None,
            },
            "Daily": {
                "Risk Rating conclusion Low": 20,
                "Risk Rating Conclusion Medium": 30,
                "Risk Rating Conclusion High": 40,
                "RF (Full test)": 5,
                "RM": 10,
                "YE": None,
            },
        }
    }
}


class TestResolveColumn:
    def test_testing_round_phase_selects_its_own_column(self):
        assert resolve_column("Low", "RM") == "RM"
        assert resolve_column("Low", "YE") == "YE"
        assert resolve_column("High", "RF") == "RF (Full test)"

    def test_non_round_phase_falls_through_to_risk_level(self):
        # DE / OE are design & operating effectiveness, not testing rounds.
        assert resolve_column("Low", "DE") == "Risk Rating conclusion Low"
        assert resolve_column("Medium", "OE") == "Risk Rating Conclusion Medium"
        assert resolve_column("High", None) == "Risk Rating Conclusion High"

    def test_case_and_whitespace_insensitive(self):
        assert resolve_column("  medium ", " de ") == "Risk Rating Conclusion Medium"
        assert resolve_column("low", "rm") == "RM"

    def test_unknown_risk_level_yields_no_column(self):
        assert resolve_column("Catastrophic", "DE") is None
        assert resolve_column(None, None) is None


class TestCalculateSampleSize:
    def test_numeric_lookup(self):
        assert calculate_sample_size(MATRIX, "High", "Daily", "DE") == "40"
        assert calculate_sample_size(MATRIX, "Low", "Daily", "DE") == "20"

    def test_range_values_are_preserved_as_text(self):
        assert calculate_sample_size(MATRIX, "Medium", "Monthly", "DE") == "2 to 5"

    def test_testing_round_phase_overrides_risk_column(self):
        # Daily/RM is 10 regardless of the Low risk rating.
        assert calculate_sample_size(MATRIX, "Low", "Daily", "RM") == "10"

    def test_null_cell_yields_none(self):
        # Monthly + Low is null in the matrix.
        assert calculate_sample_size(MATRIX, "Low", "Monthly", "DE") is None

    def test_unknown_frequency_yields_none(self):
        # "Upon Occurrence" is a real control frequency with no matrix row.
        assert calculate_sample_size(MATRIX, "Low", "Upon Occurrence", "DE") is None

    def test_frequency_match_is_case_insensitive(self):
        assert calculate_sample_size(MATRIX, "High", "  daily ", "DE") == "40"

    def test_empty_matrix_yields_none(self):
        assert calculate_sample_size({}, "High", "Daily", "DE") is None


class TestExtractControlParameters:
    def test_pulls_all_three_inputs_and_fallback(self):
        source = {
            "control_details": {"Phase of control": "DE", "Sample Size": 2},
            "rcm_details": {"Risk Level": "Low", "Frequency": "Upon Occurrence"},
        }
        params = extract_control_parameters(source)
        assert params == {
            "risk_level": "Low",
            "frequency": "Upon Occurrence",
            "phase": "DE",
            "fallback_sample_size": "2",
        }

    def test_missing_sections_are_tolerated(self):
        params = extract_control_parameters({})
        assert params["risk_level"] is None
        assert params["fallback_sample_size"] is None


class TestLoadSamplingMatrix:
    def test_loads_from_disk(self, tmp_path: Path):
        f = tmp_path / "sampling_matrix.json"
        f.write_text(json.dumps(MATRIX))
        assert load_sampling_matrix(f) == MATRIX

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_sampling_matrix(tmp_path / "nope.json") == {}

    def test_malformed_file_returns_empty(self, tmp_path: Path):
        f = tmp_path / "bad.json"
        f.write_text("{not json")
        assert load_sampling_matrix(f) == {}


@requires_client_data
class TestRealClientMatrix:
    """Sanity checks against the actual shipped matrix + real control values."""

    @property
    def matrix(self) -> dict:
        return load_sampling_matrix(Path(settings.SAMPLING_MATRIX_PATH))

    def test_real_matrix_parses(self):
        assert "Sampling Methodology" in self.matrix

    def test_ia8_ca02_falls_back(self):
        # Low / "Upon Occurrence" / DE — no matrix row for that frequency.
        assert calculate_sample_size(self.matrix, "Low", "Upon Occurrence", "DE") is None

    def test_ia5_ca03_resolves_from_matrix(self):
        # Medium / Monthly / DE -> the "2 to 5" range cell.
        assert calculate_sample_size(self.matrix, "Medium", "Monthly", "DE") == "2 to 5"


class TestLoadSamplingNotes:
    """Per-control sampling reasoning shown beside each attribute."""

    PAYLOAD = {
        "controls": [
            {
                "control_number": "IA8.CA02",
                "entity_code": "19A1",
                "notes": {
                    "frequency": {
                        "text": "For manual entries... 25 + 2 = 27",
                        "source": "RCM",
                    },
                    "risk_level": {"text": "As observed from the RCM.", "source": "RCM"},
                    "phase": None,
                },
            },
            {
                "control_number": "IA8.CA02",
                "entity_code": "20B2",
                # Bare-string form — supported for quick, untagged notes.
                "notes": {"frequency": "Different entity reasoning"},
            },
        ]
    }

    def _write(self, tmp_path: Path, payload: dict) -> Path:
        f = tmp_path / "sampling_metadata.json"
        f.write_text(json.dumps(payload))
        return f

    def test_matches_on_control_and_entity_with_source_tag(self, tmp_path: Path):
        f = self._write(tmp_path, self.PAYLOAD)
        notes = load_sampling_notes(f, "IA8.CA02", "19A1")
        assert notes["frequency"] == {
            "text": "For manual entries... 25 + 2 = 27",
            "source": "RCM",
        }

    def test_risk_level_note_carries_its_tag(self, tmp_path: Path):
        f = self._write(tmp_path, self.PAYLOAD)
        notes = load_sampling_notes(f, "IA8.CA02", "19A1")
        assert notes["risk_level"]["text"] == "As observed from the RCM."
        assert notes["risk_level"]["source"] == "RCM"

    def test_bare_string_note_is_accepted_without_a_source(self, tmp_path: Path):
        f = self._write(tmp_path, self.PAYLOAD)
        notes = load_sampling_notes(f, "IA8.CA02", "20B2")
        assert notes["frequency"] == {"text": "Different entity reasoning", "source": None}

    def test_null_and_absent_notes_are_none(self, tmp_path: Path):
        f = self._write(tmp_path, self.PAYLOAD)
        assert load_sampling_notes(f, "IA8.CA02", "19A1")["phase"] is None
        assert load_sampling_notes(f, "IA8.CA02", "20B2")["risk_level"] is None

    def test_unmatched_control_yields_empty_notes(self, tmp_path: Path):
        f = self._write(tmp_path, self.PAYLOAD)
        assert load_sampling_notes(f, "NO.SUCH", "19A1") == {
            "frequency": None,
            "risk_level": None,
            "phase": None,
        }

    def test_missing_file_is_not_fatal(self, tmp_path: Path):
        notes = load_sampling_notes(tmp_path / "nope.json", "IA8.CA02", "19A1")
        assert notes == {"frequency": None, "risk_level": None, "phase": None}

    def test_malformed_file_is_not_fatal(self, tmp_path: Path):
        f = tmp_path / "bad.json"
        f.write_text("{not json")
        notes = load_sampling_notes(f, "IA8.CA02", "19A1")
        assert notes == {"frequency": None, "risk_level": None, "phase": None}

    @requires_client_data
    def test_real_metadata_file_carries_tagged_reasoning(self):
        notes = load_sampling_notes(Path(settings.SAMPLING_METADATA_PATH), "IA8.CA02", "19A1")
        assert "25 + 2 = 27" in notes["frequency"]["text"]
        assert notes["frequency"]["source"] == "RCM"
        assert notes["risk_level"]["text"] == "As observed from the RCM."
        assert notes["risk_level"]["source"] == "RCM"

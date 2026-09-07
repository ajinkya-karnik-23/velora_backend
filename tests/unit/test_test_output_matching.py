"""Unit tests for testing-output lookup and sample normalisation.

Output files are matched on their content header (control_number +
entity_code), not their filename, and sample rows are normalised from the
client's own column names onto stable API fields with the remaining keys
grouped as displayable parameters.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.test_output_matching import (
    build_samples,
    find_test_output,
    iter_test_outputs,
    normalise_sample,
)

from app.core.config import settings
from tests.client_data import requires_client_data

RAW_SAMPLE = {
    "sample_no": 1,
    "Document No": "1900006431",
    "Type": "KR",
    "Document description": "Vendor invoice",
    "Posting date": "2025-01-10",
    "Amount in local cur.": 83514.51,
    "LCurr": "USD",
    "Text": "WAR RISK INSU MV CAPE HAIZHOU",
    "result": "PASS",
    "pages": [1, 2, 3],
    "validation": "Traced to SAP posting without exception.",
}

PAYLOAD = {
    "control_test_output": {
        "control_number": "IA8.CA02",
        "entity_code": "19A1",
        "phase_of_control": "DE",
        "summary": "A sample-based review...",
    },
    "test_details": {
        "1": RAW_SAMPLE,
        "2": {**RAW_SAMPLE, "sample_no": 2, "result": "NOT_VALIDATED"},
    },
}


class TestNormaliseSample:
    def test_core_fields_are_mapped(self):
        out = normalise_sample("1", RAW_SAMPLE)
        assert out["sample_no"] == 1
        assert out["document_no"] == "1900006431"
        assert out["result"] == "PASS"
        assert out["validation"] == "Traced to SAP posting without exception."
        assert out["pages"] == [1, 2, 3]

    def test_the_six_documented_parameters_are_grouped_in_order(self):
        out = normalise_sample("1", RAW_SAMPLE)
        assert [p["label"] for p in out["parameters"]] == [
            "Type",
            "Document description",
            "Posting date",
            "Amount in local cur.",
            "LCurr",
            "Text",
        ]
        assert out["parameters"][3]["value"] == 83514.51

    def test_core_fields_never_leak_into_parameters(self):
        out = normalise_sample("1", RAW_SAMPLE)
        labels = {p["label"] for p in out["parameters"]}
        assert not labels & {"sample_no", "Document No", "result", "validation", "pages"}

    def test_unknown_columns_still_surface_as_parameters(self):
        out = normalise_sample("1", {**RAW_SAMPLE, "Reviewer": "J. Doe"})
        assert {"label": "Reviewer", "value": "J. Doe"} in out["parameters"]

    def test_sample_no_falls_back_to_the_dict_key(self):
        raw = {k: v for k, v in RAW_SAMPLE.items() if k != "sample_no"}
        assert normalise_sample("7", raw)["sample_no"] == 7


class TestBuildSamples:
    def test_row_count_follows_the_data(self):
        assert len(build_samples(PAYLOAD)) == 2

    def test_rows_are_numerically_ordered_not_lexically(self):
        details = {str(i): {**RAW_SAMPLE, "sample_no": i} for i in (1, 2, 10, 27)}
        samples = build_samples({"test_details": details})
        assert [s["sample_no"] for s in samples] == [1, 2, 10, 27]

    def test_missing_details_yields_no_rows(self):
        assert build_samples({}) == []


class TestFindTestOutput:
    @pytest.fixture
    def outputs_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "test_outputs"
        d.mkdir()
        (d / "IA8.CA02.19A1.TestOutput.json").write_text(json.dumps(PAYLOAD))
        other = {
            **PAYLOAD,
            "control_test_output": {**PAYLOAD["control_test_output"], "entity_code": "20B2"},
        }
        (d / "IA8.CA02.20B2.TestOutput.json").write_text(json.dumps(other))
        (d / "README.txt").write_text("not json")
        return d

    def test_matches_on_control_and_entity(self, outputs_dir: Path):
        found = find_test_output(outputs_dir, "IA8.CA02", "20B2")
        assert found is not None
        assert found["control_test_output"]["entity_code"] == "20B2"

    def test_entity_none_matches_first_for_that_control(self, outputs_dir: Path):
        found = find_test_output(outputs_dir, "IA8.CA02", None)
        assert found is not None

    def test_wrong_entity_returns_none(self, outputs_dir: Path):
        assert find_test_output(outputs_dir, "IA8.CA02", "ZZZZ") is None

    def test_wrong_control_returns_none(self, outputs_dir: Path):
        assert find_test_output(outputs_dir, "NO.SUCH", "19A1") is None

    def test_non_json_files_are_skipped(self, outputs_dir: Path):
        assert len(iter_test_outputs(outputs_dir)) == 2

    def test_missing_directory_returns_none(self, tmp_path: Path):
        assert find_test_output(tmp_path / "nope", "IA8.CA02", "19A1") is None


@requires_client_data
class TestRealClientOutput:
    """Sanity check against the actual shipped testing output."""

    def test_real_output_has_all_27_samples(self):
        payload = find_test_output(Path(settings.TEST_OUTPUTS_PATH), "IA8.CA02", "19A1")
        assert payload is not None
        samples = build_samples(payload)
        assert len(samples) == 27
        assert samples[0]["sample_no"] == 1
        assert samples[-1]["sample_no"] == 27
        # 25 PASS + 2 NOT_VALIDATED, matching the output's own summary.
        results = [s["result"] for s in samples]
        assert results.count("PASS") == 25
        assert results.count("NOT_VALIDATED") == 2
        # Every sample groups the six documented parameters.
        assert all(len(s["parameters"]) == 6 for s in samples)

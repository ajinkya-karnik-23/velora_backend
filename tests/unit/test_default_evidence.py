"""Which files the default evidence map plans for each sample."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.services.default_evidence import load_map, planned_files


def test_fixed_file_for_every_sample() -> None:
    entry = {"source_dir": "src", "files_from": "fixed", "file": "JV's TOE.pdf"}
    assert planned_files(entry, {"sample_no": 7}) == [Path("src/JV's TOE.pdf")]


def test_evidences_used_from_a_per_sample_folder_without_duplicates() -> None:
    entry = {"source_dir": "src", "files_from": "evidences_used", "folder_field": "Customer Name"}
    sample = {
        "evidences_used": ["DBapps.pdf", "DBapps.pdf", " Evaluation.pdf "],
        "parameters": [{"label": "Customer Name", "value": "UAB Vikant"}],
    }
    assert planned_files(entry, sample) == [
        Path("src/UAB Vikant/DBapps.pdf"),
        Path("src/UAB Vikant/Evaluation.pdf"),
    ]
    # A sample without the folder field has no folder to read from.
    assert planned_files(entry, {"evidences_used": ["a.pdf"], "parameters": []}) == []


def test_filename_rule_follows_the_evidence_map(tmp_path: Path) -> None:
    rule_map = tmp_path / "rules.json"
    rule_map.write_text(
        json.dumps(
            {
                "controls": [
                    {
                        "control_number": "IA5.CA03.1",
                        "entity_code": "19A1",
                        "expected_evidence_filename_fields": ["Customer name", "Month"],
                        "expected_evidence_extension": ".pdf",
                    }
                ]
            }
        )
    )
    entry = {
        "control_number": "IA5.CA03.1",
        "entity_code": "19A1",
        "source_dir": "src",
        "files_from": "filename_rule",
    }
    with patch("app.services.default_evidence.settings.EVIDENCE_FILENAME_MAP_PATH", str(rule_map)):
        amendment = {"parameters": [{"label": "Customer name", "value": "PSBT sp./Rawa"}]}
        review = {"parameters": [{"label": "Month", "value": "Apr-25"}]}
        assert planned_files(entry, amendment) == [Path("src/PSBT sp.-Rawa.pdf")]
        assert planned_files(entry, review) == [Path("src/Apr-25.pdf")]


def test_missing_map_disables_attachment(tmp_path: Path) -> None:
    assert load_map(tmp_path / "absent.json") == []

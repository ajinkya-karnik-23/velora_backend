"""Unit tests for TWP template selection."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.twp_templates import TwpTemplates, load_twp_templates

from app.core.config import settings
from tests.client_data import requires_client_data

MAP_PAYLOAD = {
    "controls": [
        {
            "control_number": "IA8.CA02",
            "entity_code": "19A1",
            "empty_template": "misc/empty.xlsm",
            "completed_template": "misc/completed.xlsm",
        },
        {
            # No entity — applies to every entity of this control.
            "control_number": "IA5.CA03",
            "empty_template": "misc/any-empty.xlsm",
            "completed_template": "misc/any-done.xlsm",
        },
    ]
}


def _write(tmp_path: Path, payload: object) -> Path:
    f = tmp_path / "twp_template_map.json"
    f.write_text(json.dumps(payload))
    return f


class TestLoadTwpTemplates:
    def test_returns_both_variants(self, tmp_path: Path):
        t = load_twp_templates(_write(tmp_path, MAP_PAYLOAD), "IA8.CA02", "19A1")
        assert t.empty == "misc/empty.xlsm"
        assert t.completed == "misc/completed.xlsm"

    def test_entity_must_match_when_mapped(self, tmp_path: Path):
        t = load_twp_templates(_write(tmp_path, MAP_PAYLOAD), "IA8.CA02", "20B2")
        assert t == TwpTemplates()

    def test_entry_without_entity_applies_to_any(self, tmp_path: Path):
        t = load_twp_templates(_write(tmp_path, MAP_PAYLOAD), "IA5.CA03", "99Z9")
        assert t.completed == "misc/any-done.xlsm"

    def test_unmapped_control_returns_nothing(self, tmp_path: Path):
        assert (
            load_twp_templates(_write(tmp_path, MAP_PAYLOAD), "NO.SUCH", "19A1") == TwpTemplates()
        )

    def test_missing_or_malformed_map_degrades_quietly(self, tmp_path: Path):
        assert load_twp_templates(tmp_path / "nope.json", "IA8.CA02", "19A1") == TwpTemplates()
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert load_twp_templates(bad, "IA8.CA02", "19A1") == TwpTemplates()

    def test_non_dict_entries_are_skipped(self, tmp_path: Path):
        f = _write(tmp_path, {"controls": ["nonsense", None, MAP_PAYLOAD["controls"][0]]})
        assert load_twp_templates(f, "IA8.CA02", "19A1").empty == "misc/empty.xlsm"


class TestForState:
    def test_picks_by_testing_state(self):
        t = TwpTemplates(empty="e.xlsm", completed="c.xlsm")
        assert t.for_state(tests_completed=False) == "e.xlsm"
        assert t.for_state(tests_completed=True) == "c.xlsm"

    def test_unmapped_state_is_none(self):
        assert TwpTemplates(empty="e.xlsm").for_state(tests_completed=True) is None


@requires_client_data
class TestShippedConfiguration:
    """The mapping shipped for the client must resolve to files on disk."""

    def test_both_variants_exist(self):
        t = load_twp_templates(Path(settings.TWP_TEMPLATE_MAP_PATH), "IA8.CA02", "19A1")
        assert t.empty and Path(t.empty).exists(), "empty template missing"
        assert t.completed and Path(t.completed).exists(), "completed report missing"

    def test_the_two_variants_are_different_files(self):
        t = load_twp_templates(Path(settings.TWP_TEMPLATE_MAP_PATH), "IA8.CA02", "19A1")
        assert Path(t.empty).read_bytes() != Path(t.completed).read_bytes()

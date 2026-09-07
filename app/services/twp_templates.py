"""TWP report template selection.

A control has two work-paper workbooks: an empty one, served while testing is
still outstanding, and the completed report, served once every sample has been
tested. Which file backs each is configured in a JSON map so new controls can
be added without touching code.

Follows the same conventions as the other client-config loaders: matched on
content (control number + entity) rather than filename, and degrading quietly
when the map is missing or malformed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TwpTemplates:
    """The workbooks configured for one control+entity."""

    empty: str | None = None
    completed: str | None = None

    def for_state(self, tests_completed: bool) -> str | None:
        """The path to serve for the control's current testing state."""
        return self.completed if tests_completed else self.empty


def _matches(entry: dict, control_number: str, entity_code: str | None) -> bool:
    if str(entry.get("control_number") or "").strip() != (control_number or "").strip():
        return False
    mapped_entity = entry.get("entity_code")
    # An entry without an entity applies to every entity of that control.
    if mapped_entity in (None, ""):
        return True
    return str(mapped_entity).strip() == str(entity_code or "").strip()


def load_twp_templates(
    map_path: Path, control_number: str, entity_code: str | None
) -> TwpTemplates:
    """Templates configured for a control, or empty when none are mapped."""
    try:
        payload = json.loads(map_path.read_text())
    except (OSError, json.JSONDecodeError):
        return TwpTemplates()

    for entry in payload.get("controls") or []:
        if not isinstance(entry, dict) or not _matches(entry, control_number, entity_code):
            continue
        return TwpTemplates(
            empty=(entry.get("empty_template") or None),
            completed=(entry.get("completed_template") or None),
        )
    return TwpTemplates()

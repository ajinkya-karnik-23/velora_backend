"""Match an uploaded control Excel filename to its control-definition JSON.

We never parse the Excel itself — only its filename's leading dot-separated
code prefix is used as a search key, e.g.:

    uploaded:  "IA8.CA02.19A1.DE.2026 NR and Manual JV.xlsm"
    code:      "IA8.CA02"   (first 2 segments — the control group code)

That search key is then matched against each control JSON's own CONTENT —
specifically control_details["Control No"] and control_details["Entity
Code"] — rather than the JSON filename. Real client filenames are not
reliably 3-segment (e.g. "IA5.CA03.1.19A1.DE.Control.txt" has an extra
sub-index segment before the entity, and files may be saved with a ".txt"
extension instead of ".json"), so filename position parsing on the JSON
side is not trustworthy. The JSON's own fields are.

Segment breakdown of the search key (derived from the uploaded filename
only, since that's the one thing with no structured content to read):
  - the first 2 segments ("IA8.CA02") identify the control itself — this is
    what the Control Repository groups/displays by, and what
    control_details["Control No"] is expected to equal.
  - the entity (site), e.g. "19A1", lives in control_details["Entity Code"]
    and in the Review Cycle's entity_code — never parsed from a filename.
"""

from __future__ import annotations

import json
from pathlib import Path

GROUP_CODE_SEGMENTS = 2


def extract_control_code(filename: str, num_segments: int = GROUP_CODE_SEGMENTS) -> str | None:
    """Return the leading "<code>.<code>..." prefix of a filename's stem.

    Only ever applied to the uploaded Excel's filename — control JSONs are
    matched by their own content, not by parsing their filename.

    Returns None if the filename doesn't have at least `num_segments`
    dot-separated parts before its extension.
    """
    stem = Path(filename).stem
    parts = stem.split(".")
    if len(parts) < num_segments:
        return None
    return ".".join(parts[:num_segments])


def iter_control_jsons(control_jsons_dir: Path) -> list[tuple[Path, dict]]:
    """Return (path, payload) for every file in the directory that parses as
    a control definition JSON (valid JSON, containing "control_details").

    File extension is ignored — client exports have been seen with ".txt"
    as well as ".json". Files that aren't valid JSON, or don't look like a
    control definition, are silently skipped rather than erroring, since
    stray files (.DS_Store, README, etc.) commonly share the directory.
    """
    if not control_jsons_dir.exists():
        return []
    results: list[tuple[Path, dict]] = []
    for candidate in sorted(control_jsons_dir.iterdir()):
        if not candidate.is_file() or candidate.name.startswith("."):
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and "control_details" in payload:
            results.append((candidate, payload))
    return results


def find_control_json_by_control_no(control_jsons_dir: Path, control_no: str) -> Path | None:
    """Return the first control JSON whose control_details["Control No"]
    equals `control_no` exactly."""
    for path, payload in iter_control_jsons(control_jsons_dir):
        details = payload.get("control_details") or {}
        if str(details.get("Control No", "")).strip() == control_no.strip():
            return path
    return None


def find_control_json_by_control_and_entity(
    control_jsons_dir: Path, control_no: str, entity_code: str
) -> Path | None:
    """Return the first control JSON matching both control_no and entity_code."""
    for path, payload in iter_control_jsons(control_jsons_dir):
        details = payload.get("control_details") or {}
        if (
            str(details.get("Control No", "")).strip() == control_no.strip()
            and str(details.get("Entity Code", "")).strip() == entity_code.strip()
        ):
            return path
    return None


def list_available_entities(control_jsons_dir: Path) -> list[str]:
    """Sorted, deduplicated entity codes found across a client's control JSONs."""
    entities: set[str] = set()
    for _path, payload in iter_control_jsons(control_jsons_dir):
        details = payload.get("control_details") or {}
        entity = str(details.get("Entity Code", "")).strip()
        if entity:
            entities.add(entity)
    return sorted(entities)


def load_control_json(json_path: Path) -> dict:
    """Parse a control definition JSON file."""
    return json.loads(json_path.read_text(encoding="utf-8"))

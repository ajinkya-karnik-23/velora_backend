"""Demo control owners for the Control Repository.

`misc/control_owners.json` (CONTROL_OWNERS_PATH) names an owner and role per
control number; a control it does not list takes one from its roster, picked
by a hash of the control number so the same control always shows the same
person. A missing or malformed file means no demo owners, and the repository
falls back to the account recorded on the control.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Any

from app.core.config import settings


def _load() -> dict[str, Any]:
    path = Path(settings.CONTROL_OWNERS_PATH)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def owner_for(control_number: str) -> tuple[str, str | None] | None:
    """(name, role) for a control, or None when no demo owners are configured."""
    data = _load()
    listed = (data.get("controls") or {}).get(control_number.strip())
    if isinstance(listed, dict) and listed.get("name"):
        return str(listed["name"]), listed.get("role")
    roster = [r for r in data.get("roster") or [] if isinstance(r, dict) and r.get("name")]
    if not roster:
        return None
    pick = roster[zlib.crc32(control_number.strip().encode()) % len(roster)]
    return str(pick["name"]), pick.get("role")

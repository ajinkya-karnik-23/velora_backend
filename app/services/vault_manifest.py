"""The client's evidence-vault listing, from a manifest in the vault folder.

`<vault>/vault_manifest.json` lists the files shown per control. Only an entry
with a `path` (relative to the backend working directory) is a real document
that can be opened, downloaded or linked to a test; the rest are listed by
name, size and upload time only. Without a manifest the vault is read from its
folders as before.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

MANIFEST_NAME = "vault_manifest.json"


def load_manifest(vault_dir: Path) -> dict[str, Any] | None:
    path = vault_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def manifest_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Flat list of listed files: control_number, file_name, size, type, viewable."""
    out = []
    for control in manifest.get("controls") or []:
        number = str(control.get("control_number") or "").strip()
        for f in control.get("files") or []:
            name = str(f.get("name") or "").strip()
            if not number or not name:
                continue
            real = _real_path(f)
            out.append(
                {
                    "control_number": number,
                    "file_name": name,
                    "file_size": int(f.get("size") or (real.stat().st_size if real else 0)),
                    "file_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
                    "viewable": real is not None,
                    "uploaded_time": f.get("uploaded"),
                }
            )
    return out


def _real_path(entry: dict[str, Any]) -> Path | None:
    raw = entry.get("path")
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.is_file() else None


def viewable_path(manifest: dict[str, Any], control_number: str, filename: str) -> Path | None:
    """The real document behind a listed file, or None if it is listing-only."""
    for control in manifest.get("controls") or []:
        if str(control.get("control_number") or "").strip() != control_number.strip():
            continue
        for f in control.get("files") or []:
            if str(f.get("name") or "").strip() == filename.strip():
                return _real_path(f)
    return None

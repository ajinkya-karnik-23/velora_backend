"""Helpers for tests that read the client's own data files.

That data is not part of the repository — it is supplied per deployment and
located via CLIENT_DATA_PATH. Tests covering it are skipped wherever the
folder is absent, so a checkout without it still runs green.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings


def client_data_present() -> bool:
    """Whether the configured client-data folder exists on this machine."""
    return Path(settings.CLIENT_DATA_PATH).is_dir()


requires_client_data = pytest.mark.skipif(
    not client_data_present(),
    reason=(
        f"client data not found at {settings.CLIENT_DATA_PATH!r} — "
        "set CLIENT_DATA_PATH to run the tests that read it"
    ),
)

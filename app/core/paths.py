"""Filesystem path constants for the app."""

import contextlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"

# Ensure directories exist on import. Failure is non-fatal so import-time
# usage (e.g. tests, read-only filesystems) doesn't blow up — the first
# real write will surface a clearer error.
for _dir in (DATA_DIR, STATIC_DIR):
    with contextlib.suppress(PermissionError, OSError):
        _dir.mkdir(exist_ok=True)

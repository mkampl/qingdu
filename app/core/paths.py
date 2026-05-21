"""Filesystem path constants for the app."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"

# Ensure directories exist on import.
for _dir in (DATA_DIR, BACKUP_DIR, STATIC_DIR, TEMPLATES_DIR):
    _dir.mkdir(exist_ok=True)

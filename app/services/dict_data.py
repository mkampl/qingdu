"""
Pinned dictionary data (HSK list + CC-CEDICT).

Both upstream sources ship inside the repo under `app/data/dict/`, gzip
compressed, with `VERSION.json` recording where each file came from and
the sha256 of its uncompressed content. Startup reads these files and
never goes to the network for them; `tools/refresh_dictionaries.py` is the
only thing that replaces them, and it is run by hand after reviewing the
gloss diff.

`dict_version()` combines the hashes of everything that shapes a word's
gloss (both source files, the bundled sense and reading overrides, the
learner glosses and `GLOSS_RULES_VERSION`). It is stored in `system_settings` after the
user-word snapshot backfill ran, so the backfill only rewrites user rows
when that combination actually changed.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.constants import GLOSS_RULES_VERSION

logger = logging.getLogger(__name__)

APP_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DICT_DIR: Path = APP_DATA_DIR / "dict"
VERSION_FILE_NAME = "VERSION.json"

# Bundled files that change how a gloss is picked. Hashed into the
# dictionary version so editing them also triggers a backfill.
_RULE_FILES = (
    "cedict_primary_overrides.json",
    "learner_glosses.json",
    "reading_overrides.json",
    "subtlex_char_pinyin_freq.json",
)

DICT_VERSION_SETTING = "dictionary.version"

# sha256 of the source text each loader actually used ("hsk", "cedict").
# None means that source was not loaded (missing, failed, or skipped in
# tests); the version is then incomplete and the backfill does not run.
loaded_sources: dict[str, str | None] = {"hsk": None, "cedict": None}


class ChecksumError(ValueError):
    """A vendored dictionary file does not match VERSION.json."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_version_info(dict_dir: Path | None = None) -> dict:
    """Parsed VERSION.json, or {} if it is missing or unreadable."""
    path = (dict_dir or DICT_DIR) / VERSION_FILE_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logger.error("Unreadable %s: %s", path, e)
        return {}


def read_vendored(source: str, dict_dir: Path | None = None) -> tuple[bytes, str] | None:
    """Return (uncompressed bytes, sha256) of the vendored file for
    `source` ("hsk" or "cedict"), or None if it is not there.

    Raises ChecksumError when the content does not match VERSION.json, so a
    damaged or hand-edited file is never loaded silently."""
    dict_dir = dict_dir or DICT_DIR
    info = read_version_info(dict_dir).get(source)
    if not info or not info.get("file"):
        return None
    path = dict_dir / info["file"]
    if not path.exists():
        return None
    raw = path.read_bytes()
    data = gzip.decompress(raw) if path.suffix == ".gz" else raw
    digest = sha256_bytes(data)
    expected = info.get("sha256")
    if expected and digest != expected:
        raise ChecksumError(f"{path.name}: sha256 {digest} does not match VERSION.json {expected}")
    return data, digest


def load_pinned_dictionaries() -> None:
    """Fill `hsk_vocab` and `cedict_vocab` from the vendored files the way
    startup does, without touching the network or the data directory.
    For tools and tests that run outside the app."""
    from app import state
    from app.services import cedict_loader, hsk_loader

    hsk = read_vendored("hsk")
    cedict = read_vendored("cedict")
    if hsk is None or cedict is None:
        raise FileNotFoundError(f"vendored dictionaries missing in {DICT_DIR}")
    hsk_loader.process_raw_hsk(json.loads(hsk[0]))
    state.cedict_vocab.clear()
    state.cedict_vocab.update(cedict_loader._parse_text(cedict[0].decode("utf-8")))
    cedict_loader._merge_into_hsk_vocab()


def _rule_files_digest() -> str:
    h = hashlib.sha256()
    for name in _RULE_FILES:
        path = APP_DATA_DIR / name
        h.update(name.encode())
        h.update(path.read_bytes() if path.exists() else b"-")
    return h.hexdigest()


def dict_version() -> str | None:
    """Identifier of the gloss data currently loaded, or None when a
    source is missing (then nothing should be written to user rows)."""
    hsk, cedict = loaded_sources.get("hsk"), loaded_sources.get("cedict")
    if not hsk or not cedict:
        return None
    combined = sha256_bytes(f"{hsk}:{cedict}:{_rule_files_digest()}".encode())
    return f"r{GLOSS_RULES_VERSION}-{hsk[:8]}-{cedict[:8]}-{combined[:12]}"


def get_stored_version(db: Session) -> str | None:
    from app.database import SystemSetting

    row = db.query(SystemSetting).filter(SystemSetting.key == DICT_VERSION_SETTING).first()
    if not row:
        return None
    try:
        return json.loads(row.value)
    except ValueError:
        return None


def set_stored_version(db: Session, version: str) -> None:
    from app.database import SystemSetting

    row = db.query(SystemSetting).filter(SystemSetting.key == DICT_VERSION_SETTING).first()
    if row:
        row.value = json.dumps(version)
    else:
        db.add(SystemSetting(key=DICT_VERSION_SETTING, value=json.dumps(version)))
    db.commit()


__all__ = [
    "DICT_DIR",
    "ChecksumError",
    "dict_version",
    "get_stored_version",
    "load_pinned_dictionaries",
    "loaded_sources",
    "read_vendored",
    "read_version_info",
    "set_stored_version",
]

"""Reader and review preferences kept on the account.

The SPA used to keep these on the device only, so a phone and a laptop
showed different pinyin, colours and review modes. They live in
`users.ui_settings` as JSON now. Only the keys below are stored, each
checked; device matters (theme, reminder time, haptics) stay local.
"""

from __future__ import annotations

import json

# key -> allowed values (a set) or a validator
_CHOICES: dict[str, set] = {
    "pinyinMode": {"auto", "on", "off"},
    "hskVersion": {"new", "old"},
    "colorMode": {"progress", "hsk", "off"},
}
_BOOLS = {
    "showLegend",
    "writingShowOutline",
    "autoLearnOnClick",
    "reviewSingleMode",
    # The welcome / placement flow has been seen (shown once per account).
    "onboarded",
}
_INTS = {"autoGradeDelayMs": (0, 10_000)}
KEYS = frozenset(_CHOICES) | _BOOLS | frozenset(_INTS)


def clean(raw: dict) -> dict:
    """The known keys with valid values; anything else is dropped."""
    out: dict = {}
    for key, value in (raw or {}).items():
        choice = key in _CHOICES and isinstance(value, str) and value in _CHOICES[key]
        if choice or (key in _BOOLS and isinstance(value, bool)):
            out[key] = value
        elif key in _INTS and isinstance(value, int) and not isinstance(value, bool):
            lo, hi = _INTS[key]
            if lo <= value <= hi:
                out[key] = value
    return out


def load(stored: str | None) -> dict | None:
    if not stored:
        return None
    try:
        data = json.loads(stored)
    except (TypeError, ValueError):
        return None
    return clean(data) if isinstance(data, dict) else None


def merge(stored: str | None, update: dict) -> str:
    """Stored settings with the valid keys of `update` on top."""
    return json.dumps({**(load(stored) or {}), **clean(update)}, sort_keys=True)


__all__ = ["KEYS", "clean", "load", "merge"]

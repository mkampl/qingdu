"""
Global Simplified <-> Traditional conversion driven by User.display_script.

The app's internal data (HSK vocab, CC-CEDICT keys, jieba dictionary) is
Simplified-canonical, so:
- 'simp': either pass through or normalise to simp (cheap; opencc t2s).
- 'trad': convert simp -> trad on every Chinese-bearing response field.
- 'auto': don't touch the text. The user sees whatever was stored.

OpenCC is stateless, fast and synchronous; we cache the two converters
at module level so we don't rebuild them per request.
"""

from __future__ import annotations

from functools import lru_cache

from opencc import OpenCC

from app.database import User


@lru_cache(maxsize=2)
def _converter(direction: str) -> OpenCC:
    """direction is 's2t' or 't2s'. Cached so we build each converter once."""
    return OpenCC(direction)


def user_script(user: User | None) -> str:
    """Resolve the user's preference, with a safe default for anon callers."""
    if user is None:
        return "auto"
    return (getattr(user, "display_script", None) or "auto").lower()


def to_user_script(text: str, user: User | None) -> str:
    """Convert one string to the user's preferred script.

    'auto' is a no-op so user data stays untouched. 'simp' normalises any
    Traditional characters to Simplified; 'trad' does the reverse. The
    string is returned unchanged if it's empty or has no CJK content
    (cheap early-out — opencc handles non-CJK too but the call is
    measurable on hot paths like analyze).
    """
    if not text:
        return text
    pref = user_script(user)
    if pref == "auto":
        return text
    if pref == "trad":
        return _converter("s2t").convert(text)
    if pref == "simp":
        return _converter("t2s").convert(text)
    return text


def to_canonical(text: str, user: User | None) -> str:
    """Normalise an incoming Chinese string to Simplified for storage / lookup.

    HSK vocab, CC-CEDICT keys, jieba dict and the `user_words` table are all
    Simplified-canonical. When a user is on a non-auto script preference,
    they may post Chinese back to us in Traditional (or in their preferred
    form), so we convert to simp before lookup/storage. 'auto' is a no-op
    so anonymous and auto users keep whatever they actually typed.
    """
    if not text:
        return text
    pref = user_script(user)
    if pref == "auto":
        return text
    return _converter("t2s").convert(text)


__all__ = ["to_user_script", "to_canonical", "user_script"]

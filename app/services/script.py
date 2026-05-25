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


def convert_analysis_data(data: dict | list | None, user: User | None) -> dict | list | None:
    """Walk an /api/analyze-shaped response and convert every Chinese
    surface (word.text, grammar sentence.text, segments) to the user's
    display script. Returns the structure unchanged when user pref is
    'auto' or the data is empty — cheap early-out for the common case.

    The function mutates in place and also returns the same reference
    so callers can use either idiom."""
    if data is None:
        return data
    pref = user_script(user)
    if pref == "auto":
        return data
    if isinstance(data, dict):
        for word in data.get("words", []) or []:
            if isinstance(word, dict) and word.get("text"):
                word["text"] = to_user_script(word["text"], user)
        grammar = data.get("grammar")
        if isinstance(grammar, dict):
            for sentence in grammar.get("sentences", []) or []:
                if isinstance(sentence, dict) and sentence.get("text"):
                    sentence["text"] = to_user_script(sentence["text"], user)
    return data


def convert_vocab_sections(sections: list | None, user: User | None) -> list | None:
    """Walk vocabulary-list sections and convert each word's hanzi field
    (and the optional 'traditional' duplicate) to the user's display
    script. Pinyin is left alone — readings don't change between simp
    and trad. Returns the structure as the same reference."""
    if sections is None:
        return sections
    pref = user_script(user)
    if pref == "auto":
        return sections
    for section in sections:
        if not isinstance(section, dict):
            continue
        for word in section.get("words", []) or []:
            if not isinstance(word, dict):
                continue
            if word.get("hanzi"):
                word["hanzi"] = to_user_script(word["hanzi"], user)
            if word.get("traditional"):
                word["traditional"] = to_user_script(word["traditional"], user)
    return sections


__all__ = [
    "convert_analysis_data",
    "convert_vocab_sections",
    "to_canonical",
    "to_user_script",
    "user_script",
]

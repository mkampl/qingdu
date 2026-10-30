import re

from app.core.constants import TEXT_LEVEL_THRESHOLD

_BAND = re.compile(r"[1-9]|7\+|7-9")


def level_number(level: object, prefixes: tuple[str, ...] = ("new-",)) -> int | None:
    """Band number of an HSK level string; None for anything else.

    The level is one of `prefixes` followed by the band: "new-3" -> 3;
    "new-7", "new-7+" and "new-7-9" -> 7 (7 = HSK 7-9, "+" is an older
    suffix of that band). Pass ("new-", "old-") to also read "old-6", or
    ("",) for a bare "3" or "7-9".
    """
    if not isinstance(level, str):
        return None
    for prefix in prefixes:
        if level.startswith(prefix):
            band = level[len(prefix) :]
            if _BAND.fullmatch(band):
                return int(band[0])
    return None


def estimate_text_level(hsk_stats: dict, total_hsk_words: int) -> str:
    """
    Estimate text difficulty based on HSK word distribution.

    The text level is the lowest HSK level whose cumulative word coverage
    crosses TEXT_LEVEL_THRESHOLD percent — i.e. the level at which a
    reader would understand "most" of the text.

    Args:
        hsk_stats: Dictionary keyed `hskN` (N = 1..9) with word counts at each level.
        total_hsk_words: Total number of HSK-tagged words in the text.

    Returns:
        Estimated HSK level as a string (e.g. "HSK 3", "HSK 9+", or "Unknown").
    """
    if total_hsk_words == 0:
        return "Unknown"

    cumulative_words = 0
    for level in range(1, 10):
        cumulative_words += hsk_stats.get(f"hsk{level}", 0)
        percentage = (cumulative_words / total_hsk_words) * 100
        if percentage >= TEXT_LEVEL_THRESHOLD:
            return f"HSK {level}"

    return "HSK 9+"

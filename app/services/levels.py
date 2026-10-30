import re
from collections.abc import Iterable

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


def _count(stats: dict, level: str | None, prefix: str) -> int:
    n = level_number(level, (prefix, ""))
    if n is None:
        return 0
    if f"hsk{n}" in stats:
        stats[f"hsk{n}"] += 1
    return 1


def hsk_statistics(levels: Iterable[tuple[str | None, str | None]]) -> dict:
    """Word counts per band in both HSK systems for (level_new, level_old)
    pairs, with totals and the estimated text level. A level outside the
    system's buckets ("old-7") counts in the total only."""
    new = {f"hsk{i}": 0 for i in range(1, 10)}
    old = {f"hsk{i}": 0 for i in range(1, 7)}  # Old HSK has 6 levels
    total_new = total_old = 0
    for level_new, level_old in levels:
        total_new += _count(new, level_new, "new-")
        total_old += _count(old, level_old, "old-")
    estimated_new = estimate_text_level(new, total_new)
    return {
        "hsk_words_new": total_new,
        "hsk_distribution_new": new,
        "estimated_level_new": estimated_new,
        "hsk_words_old": total_old,
        "hsk_distribution_old": old,
        "estimated_level_old": estimate_text_level(old, total_old),
        # Aliases of the new-HSK fields.
        "hsk_words": total_new,
        "hsk_distribution": new,
        "estimated_level": estimated_new,
    }


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

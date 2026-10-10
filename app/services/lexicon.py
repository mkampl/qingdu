"""
What counts as a word.

A token is a word when the dictionaries know it: the HSK list, CC-CEDICT,
or a list the user curated themselves (vocabulary lists, glossaries,
package glosses). jieba also produces frequent phrases such as 很多, 三个
or 洗衣服 that no dictionary lists. Those are split into the dictionary
words they are made of instead of being glued together into a fake
"very + many" entry, and they are never stored as a user word.

Single CJK characters always count as words, so splitting can always
fall back to them.
"""

from __future__ import annotations

import json
from collections.abc import Collection

from app.state import cedict_vocab, hsk_vocab


def is_cjk_char(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2FFFF
    )


def is_cjk_word(word: str) -> bool:
    return bool(word) and all(is_cjk_char(c) for c in word)


def dictionaries_loaded() -> bool:
    """Both HSK and CC-CEDICT are in memory. Without CC-CEDICT there is no
    way to tell a real word from a phrase, so callers then keep tokens as
    they are and accept any word."""
    return bool(hsk_vocab) and bool(cedict_vocab)


def in_dictionary(word: str) -> bool:
    return word in hsk_vocab or word in cedict_vocab


def _hsk_weight(part: str) -> int:
    entry = hsk_vocab.get(part)
    return len(part) if entry and entry.get("is_original_hsk") else 0


def split_into_known(word: str, extra: Collection[str] = ()) -> list[str]:
    """Split `word` into the fewest dictionary words (HSK, CC-CEDICT or
    `extra`), falling back to single characters.

    Ties go to the split that covers more characters with HSK headwords
    (洗衣服 -> 洗 / 衣服 rather than 洗衣 / 服, 第一个 -> 第一 / 个), and
    after that to the one with the longer word at the end."""
    n = len(word)
    if n <= 1:
        return [word] if word else []

    def known(piece: str) -> bool:
        return len(piece) == 1 or piece in extra or in_dictionary(piece)

    # best[i]: best split of word[i:] as (cost, parts). Cost is compared
    # as a tuple: fewer parts, more HSK coverage, shorter first part.
    best: list[tuple[tuple[int, int, int], list[str]] | None] = [None] * (n + 1)
    best[n] = ((0, 0, 0), [])
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, n + 1):
            piece = word[i:j]
            rest = best[j]
            if rest is None or not known(piece):
                continue
            (count, neg_cov, _), parts = rest
            cost = (count + 1, neg_cov - _hsk_weight(piece), len(piece))
            if best[i] is None or cost < best[i][0]:
                best[i] = (cost, [piece, *parts])
    result = best[0]
    return result[1] if result else list(word)


def user_word_sources(db, user_id: int) -> set[str]:
    """Words the user brought in themselves: every entry of their vocabulary
    lists (glossaries included) and every word that carries a package
    gloss. These count as words even when no dictionary lists them."""
    from app.database import UserWord, UserWordGloss, VocabularyList

    words: set[str] = set()
    for (sections,) in db.query(VocabularyList.sections).filter(VocabularyList.user_id == user_id):
        try:
            parsed = json.loads(sections) if sections else []
        except (TypeError, ValueError):
            continue
        for section in parsed or []:
            for entry in (section or {}).get("words") or []:
                hanzi = (entry.get("hanzi") or "").strip() if isinstance(entry, dict) else ""
                if hanzi:
                    words.add(hanzi)
    rows = (
        db.query(UserWord.word)
        .outerjoin(UserWordGloss, UserWordGloss.user_word_id == UserWord.id)
        .filter(UserWord.user_id == user_id)
        .filter((UserWordGloss.source == "package") | (UserWord.meaning_source == "package"))
        .distinct()
    )
    words.update(w for (w,) in rows)
    return words


def is_lexical_word(
    word: str,
    *,
    db=None,
    user_id: int | None = None,
    extra: Collection[str] | None = None,
) -> bool:
    """True when `word` may become a user word: it is a single CJK
    character, a dictionary word, one of `extra`, or (when `db` and
    `user_id` are given) one of the user's own list or package words.

    Accepts everything while the dictionaries are not loaded, so a failed
    CC-CEDICT load never locks users out of saving words."""
    word = (word or "").strip()
    if not word:
        return False
    if not dictionaries_loaded():
        return True
    if len(word) == 1 and is_cjk_char(word):
        return True
    if in_dictionary(word):
        return True
    if extra is not None and word in extra:
        return True
    if db is not None and user_id is not None:
        return word in user_word_sources(db, user_id)
    return False


__all__ = [
    "dictionaries_loaded",
    "in_dictionary",
    "is_cjk_char",
    "is_cjk_word",
    "is_lexical_word",
    "split_into_known",
    "user_word_sources",
]

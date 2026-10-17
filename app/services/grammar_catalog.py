"""The grammar catalog: the points of the HSK 3.0 grammar syllabus with
English titles, explanations, examples and exercise words
(app/data/grammar/catalog.json, built by tools/build_grammar_catalog.py).

The reader's 30 fast regex patterns (services/grammar) each stand for one
catalog point; `REGEX_POINT` maps them, so a sentence the regex finds and
a sentence the LLM tags land on the same point.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "grammar" / "catalog.json"

LEVELS = ("1", "2", "3", "4", "5", "6", "7-9")

# Regex pattern id (services/grammar) -> catalog point id: the syllabus
# point each of the reader's fast patterns stands for.
REGEX_POINT: dict[str, str] = {
    pid: f"hsk30-{no:03d}"
    for pid, no in {
        "shi-de": 108,  # “是……的”句1
        "ba": 184,  # “把”字句1
        "bei": 185,  # 被动句1
        "yue-yue": 172,  # 越……越……
        "yibian-yibian": 39,  # 并列复句: 一边……，一边……
        "yinwei-suoyi": 116,  # 因果复句: 因为……，所以……
        "suiran-danshi": 113,  # 转折复句: 虽然……，但是……
        "budan-erqie": 111,  # 递进复句: 不但……，而且……
        "ruguo-jiu": 114,  # 假设复句: 如果……，就……
        "le-aspect": 41,  # 完成态: 了1
        "cong-dao": 15,  # 介词 从1
        "gen-yiqi": 10,  # 一起
        "guo-experiential": 119,  # 经历态: 过
        "bi-comparison": 38,  # 比较句1
        "zhe-durative": 118,  # 持续态: 着
        "de-resultative": 99,  # 状态补语1: 动词+得+形容词性词语
        "you-you": 94,  # 又……又……
        "rang-jiao": 187,  # 兼语句1: 叫/让 (使令)
        "gei-benefactive": 74,  # 介词 给
        "jiuyao-le": 130,  # 要/快要/就要……了
        "yi-jiu": 117,  # 紧缩复句: 一……就……
        "gang-jiu": 63,  # 时间副词 刚
        "chule-yiwai": 168,  # 除了……（以外）
        "lian-ye": 277,  # 用“连……也/都……”表示强调
        "zhiyao-jiu": 115,  # 只要……，就……
        "zhiyou-cai": 200,  # 只有……，才……
        "bushi-ershi": 254,  # 不是……，而是……
        "yaome-yaome": 406,  # 要么……，要么……
        "dehua-jiu": 114,  # 假设复句: ……的话
        "kenenghui": 49,  # 能愿动词 可能
    }.items()
}


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 0, "entries": []}
    return data if isinstance(data, dict) else {"version": 0, "entries": []}


def version() -> int:
    return int(_load().get("version") or 0)


def entries() -> list[dict]:
    return _load().get("entries") or []


@lru_cache(maxsize=1)
def by_id() -> dict[str, dict]:
    return {e["id"]: e for e in entries()}


def get(point_id: str) -> dict | None:
    """A point by catalog id, or by one of the regex pattern ids."""
    return by_id().get(REGEX_POINT.get(point_id, point_id))


def level_rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else len(LEVELS)


# Kinds of points offered first: sentence patterns say more about a
# sentence than the word-class lists (pronouns, adverbs …) that match
# almost every sentence.
_PATTERN_GROUPS = ("句子的类型", "固定格式", "口语格式", "动作的态", "强调的方法", "特殊表达法")


def candidates(sentence: str, limit: int = 32) -> list[dict]:
    """Points whose words occur in the sentence: what the LLM may choose
    from, sentence patterns first, then by level. Points without words
    (sentence structures) are never candidates."""
    out = [e for e in entries() if any(m in sentence for m in e.get("markers") or [])]
    out.sort(key=lambda e: (e["group"] not in _PATTERN_GROUPS, level_rank(e["level"]), e["no"]))
    return out[:limit]


def summary(e: dict) -> dict:
    """What lists show for a point (no examples)."""
    return {
        "id": e["id"],
        "level": e["level"],
        "group": e["group"],
        "forms": e["forms"],
        "title": e["title_en"],
        "structure": e["structure"],
        "explanation": e["explanation"],
    }


__all__ = ["LEVELS", "REGEX_POINT", "by_id", "candidates", "entries", "get", "summary", "version"]

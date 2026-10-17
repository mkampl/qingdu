"""Topic series: texts the LLM writes one after another on one topic.

Each text builds on the ones before (their short summaries go into the
prompt), uses the previous text's new words again, and brings about
`new_words` words the user doesn't know yet, each at least twice. The
server counts what is really new for the user and writes the text once
more when that is far off. Every sentence comes with its English
translation. The text is analysed like a pasted one and saved into the
series' folder, where it reads like any saved text (pre-learn, review,
grammar).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SavedText, SessionLocal, TextFolder, TextSeries, User, UserWord
from app.services import llm, readability, text_folders
from app.services.segmentation import analyze_chinese_text, segment_text
from app.state import hsk_vocab

logger = logging.getLogger(__name__)

FEATURE = "series"
PARENT_FOLDER = "Topic series"
LENGTHS = {"short": 300, "medium": 600, "long": 900}
MIN_NEW, MAX_NEW = 5, 50
# A generation older than this is taken as lost (server restart).
STALE = timedelta(minutes=10)
CJK = re.compile(r"[㐀-鿿]")

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"zh": {"type": "string"}, "en": {"type": "string"}},
                "required": ["zh", "en"],
            },
        },
        "new_words": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "sentences", "new_words"],
}

PROMPT = """You write graded reading texts in Chinese (simplified characters) for a learner.
Series topic: {topic}
Level: HSK {level}. Length: about {chars} Chinese characters, in short paragraphs.
{story}
The learner knows these words; build the text mostly from them: {known}
Bring in about {new} new words that fit the topic and the level (words not in the list above),
and use each new word at least twice. {reuse}{feedback}
Plain text only: no markdown, no asterisks or other marks around the new words.
Return: a short Chinese title; a one-sentence English summary of what happens in this text
(for writing the next one); the text as sentences, each with an English translation; and the
list of the new words you brought in.
"""


_MARKUP = re.compile(r"[*_#`~]+")


def plain(text: str) -> str:
    """Text without markdown marks (models like to bold the new words)."""
    return _MARKUP.sub("", text).strip()


def _level_of(word: str) -> int:
    raw = str((hsk_vocab.get(word) or {}).get("level_new") or "")
    m = re.match(r"new-(\d)", raw)
    return int(m.group(1)) if m else 99


def _known_words(db: Session, user_id: int, level: int, limit: int = 250) -> list[str]:
    known = [
        w
        for (w,) in db.query(UserWord.word).filter(
            UserWord.user_id == user_id, UserWord.state.in_(("known", "learning"))
        )
        if _level_of(w) <= max(level, 2)
    ]
    known.sort(key=lambda w: -int((hsk_vocab.get(w) or {}).get("frequency") or 0))
    return known[:limit]


def _series_texts(db: Session, series: TextSeries) -> list[SavedText]:
    return text_folders.siblings(db, series.user_id, series.folder_id)


def _meta(text: SavedText) -> dict:
    try:
        data = json.loads(text.analysis_data or "{}")
    except ValueError:
        return {}
    return (data.get("series") or {}) if isinstance(data, dict) else {}


def payload(db: Session, series: TextSeries) -> dict:
    texts = _series_texts(db, series)
    generating = bool(
        series.generating_since and datetime.utcnow() - series.generating_since < STALE
    )
    return {
        "id": series.id,
        "folder_id": series.folder_id,
        "topic": series.topic,
        "level": series.level,
        "new_words": series.new_words,
        "length": series.length,
        "texts": len(texts),
        "generating": generating,
        "last_error": series.last_error,
    }


def create(
    db: Session, user: User, topic: str, level: int, new_words: int, length: str
) -> TextSeries:
    """The series and its folder (inside "Topic series")."""
    parent = (
        db.query(TextFolder)
        .filter(
            TextFolder.user_id == user.id,
            TextFolder.name == PARENT_FOLDER,
            TextFolder.parent_id.is_(None),
        )
        .first()
    )
    if parent is None:
        parent = TextFolder(user_id=user.id, name=PARENT_FOLDER)
        db.add(parent)
        db.flush()
    folder = TextFolder(user_id=user.id, name=topic[:120], parent_id=parent.id)
    db.add(folder)
    db.flush()
    series = TextSeries(
        user_id=user.id,
        folder_id=folder.id,
        topic=topic,
        level=level,
        new_words=new_words,
        length=length,
    )
    db.add(series)
    db.commit()
    return series


def _key(sentence: str) -> str:
    return "".join(CJK.findall(sentence))


async def _write(db: Session, series: TextSeries) -> dict:
    """Ask the LLM for the next text; checked, at most twice."""
    texts = _series_texts(db, series)
    earlier = [m for m in (_meta(t) for t in texts[-3:]) if m.get("summary")]
    story = (
        "This continues a series; so far:\n"
        + "\n".join(f"- {m['summary']}" for m in earlier)
        + "\nWrite the next part: new events or a new aspect of the topic, building on these."
        if earlier
        else "This is the first text of the series."
    )
    last_new = (_meta(texts[-1]).get("new_words") or []) if texts else []
    reuse = (
        f"Use these words from the previous text again: {'、'.join(last_new[:20])}. "
        if last_new
        else ""
    )
    known = _known_words(db, series.user_id, series.level)
    target = series.new_words
    best = None
    feedback = ""
    for _attempt in range(2):
        reply = await llm.chat(
            [
                {
                    "role": "user",
                    "content": PROMPT.format(
                        topic=series.topic,
                        level="7-9" if series.level == 7 else series.level,
                        chars=LENGTHS.get(series.length, 600),
                        story=story,
                        known="、".join(known) or "(only the most basic HSK 1 words)",
                        new=target,
                        reuse=reuse,
                        feedback=feedback,
                    ),
                }
            ],
            schema=SCHEMA,
            max_tokens=4000,
            temperature=0.7,
            timeout=240,
        )
        sentences = [
            {"zh": plain(str(s.get("zh") or "")), "en": plain(str(s.get("en") or ""))}
            for s in reply.get("sentences") or []
            if CJK.search(str(s.get("zh") or ""))
        ]
        if len(sentences) < 3:
            feedback = "\nThe last answer had no usable text; write the full text."
            continue
        text = _paragraphs([s["zh"] for s in sentences])
        summary = readability.for_user(db, series.user_id, segment_text(text))
        new = [w for w, _c in summary.missing]
        candidate = {
            "title": plain(str(reply.get("title") or ""))[:80] or series.topic,
            "summary": str(reply.get("summary") or "").strip()[:300],
            "sentences": sentences,
            "text": text,
            "new": new,
            "off": abs(len(new) - target),
        }
        if best is None or candidate["off"] < best["off"]:
            best = candidate
        if target * 0.5 - 2 <= len(new) <= target * 1.6 + 3:
            break
        feedback = (
            f"\nThe last text had {len(new)} words the learner doesn't know instead of about "
            f"{target}: {'fewer' if len(new) > target else 'more'} new words, please."
        )
    if best is None:
        raise llm.LlmError("The model wrote no usable text")
    return best


def _paragraphs(sentences: list[str], size: int = 4) -> str:
    lines = ["".join(sentences[i : i + size]) for i in range(0, len(sentences), size)]
    return "\n".join(lines)


async def _save(db: Session, series: TextSeries, written: dict) -> SavedText:
    title = written["title"]
    content = f"{title}\n{written['text']}"
    analysis = await analyze_chinese_text(content)
    by_key = {_key(s["zh"]): s["en"] for s in written["sentences"]}
    translations = {}
    for line in content.split("\n"):
        for part in re.split(r"(?<=[。！？!?…])", line):
            part = part.strip()
            if part and _key(part) in by_key:
                translations[part] = by_key[_key(part)]
    analysis["sentence_translations"] = translations
    analysis["series"] = {
        "summary": written["summary"],
        "new_words": written["new"],
        "topic": series.topic,
    }
    text = SavedText(
        user_id=series.user_id,
        title=title,
        content=content,
        analysis_data=json.dumps(analysis, ensure_ascii=False),
        tags=json.dumps(["Series", series.topic], ensure_ascii=False),
        folder_id=series.folder_id,
        position=text_folders.next_position(db, series.user_id, series.folder_id),
    )
    db.add(text)
    db.commit()
    return text


async def generate(series_id: int) -> None:
    """Write and save the next text (runs in the background)."""
    db = SessionLocal()
    try:
        series = db.get(TextSeries, series_id)
        if series is None:
            return
        try:
            written = await _write(db, series)
            await _save(db, series, written)
            series.last_error = None
        except llm.LlmError as e:
            series.last_error = str(e)[:300]
        except Exception:
            logger.exception("Series %s: generation failed", series_id)
            series.last_error = "Something went wrong writing the text"
        series.generating_since = None
        db.commit()
    finally:
        db.close()


_tasks: set[asyncio.Task] = set()


def start(db: Session, series: TextSeries) -> bool:
    """Start writing the next text unless one is on its way."""
    if series.generating_since and datetime.utcnow() - series.generating_since < STALE:
        return False
    series.generating_since = datetime.utcnow()
    series.last_error = None
    db.commit()
    task = asyncio.create_task(generate(series.id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


__all__ = ["FEATURE", "LENGTHS", "MAX_NEW", "MIN_NEW", "create", "generate", "payload", "start"]

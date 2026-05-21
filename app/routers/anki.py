import json
import logging
import os
import shutil
import tempfile
import time

import genanki
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from gtts import gTTS
from sqlalchemy.orm import Session

from app.auth import require_auth, require_auth_flexible
from app.core.paths import DATA_DIR
from app.database import User, VocabularyList, get_db

router = APIRouter(tags=["Anki Export"])
logger = logging.getLogger(__name__)


def _owned_list(db: Session, user: User, list_id: int) -> VocabularyList:
    vocab_list = (
        db.query(VocabularyList)
        .filter(VocabularyList.id == list_id, VocabularyList.user_id == user.id)
        .first()
    )
    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")
    return vocab_list


def _cache_path_for(hanzi: str):
    """Return the on-disk cache path for the TTS clip of `hanzi`."""
    audio_cache_dir = DATA_DIR / "audio_cache"
    audio_cache_dir.mkdir(exist_ok=True)
    unicode_ids = "_".join(str(ord(char)) for char in hanzi)
    return audio_cache_dir / f"{unicode_ids}_zh.mp3"


@router.get("/api/vocabulary-lists/{list_id}/check-audio")
async def check_audio_status(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Fast non-generating audit of which TTS clips are already cached."""
    vocab_list = _owned_list(db, user, list_id)
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []

    total_words = 0
    cached_count = 0
    missing_words: list = []

    for section in sections:
        for word_data in section.get("words", []):
            hanzi = word_data.get("hanzi", "")
            if not hanzi:
                continue
            total_words += 1
            cache_path = _cache_path_for(hanzi)
            if cache_path.exists() and cache_path.stat().st_size > 0:
                cached_count += 1
            else:
                missing_words.append(hanzi)

    missing_count = len(missing_words)
    estimated_seconds = missing_count * 0.5
    return {
        "total": total_words,
        "cached": cached_count,
        "missing": missing_count,
        "estimated_time": (
            f"~{int(estimated_seconds)}s" if missing_count > 0 else "0s"
        ),
        "ready": missing_count == 0,
    }


@router.post("/api/vocabulary-lists/{list_id}/prepare-export")
async def prepare_export_audio(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Generate missing TTS clips before the actual Anki export."""
    vocab_list = _owned_list(db, user, list_id)
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []

    total_words = 0
    generated_count = 0
    failed_count = 0
    consecutive_failures = 0
    rate_limited = False

    for section in sections:
        for word_data in section.get("words", []):
            hanzi = word_data.get("hanzi", "")
            if not hanzi:
                continue
            total_words += 1
            cache_path = _cache_path_for(hanzi)
            if cache_path.exists() and cache_path.stat().st_size > 0:
                continue
            if consecutive_failures >= 5:
                rate_limited = True
                failed_count += 1
                continue
            try:
                tts = gTTS(hanzi, lang="zh")
                tts.save(str(cache_path))
                generated_count += 1
                consecutive_failures = 0
                logger.info(f"Generated audio for: {hanzi}")
            except Exception as e:
                failed_count += 1
                consecutive_failures += 1
                logger.warning(f"Failed to generate audio for {hanzi}: {e}")
                if consecutive_failures >= 5:
                    rate_limited = True
                    logger.error("Rate limit reached during audio preparation")

    cached_count = total_words - generated_count - failed_count
    return {
        "total": total_words,
        "cached": cached_count,
        "generated": generated_count,
        "failed": failed_count,
        "rate_limited": rate_limited,
        "ready": failed_count == 0,
    }


@router.get("/api/vocabulary-lists/{list_id}/export-anki")
async def export_vocabulary_list_anki(
    list_id: int,
    user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db),
):
    """Export a vocabulary list as an Anki .apkg file with stroke animations + subdecks."""
    vocab_list = _owned_list(db, user, list_id)
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []

    audio_cache_dir = DATA_DIR / "audio_cache"
    audio_cache_dir.mkdir(exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="qingdu_anki_")
    media_files: list = []

    total_words = sum(len(s.get("words", [])) for s in sections)  # noqa: F841
    words_processed = 0
    audio_generated = 0
    audio_cached = 0
    audio_failed = 0
    failed_words: list = []
    rate_limited = False
    consecutive_failures = 0

    try:
        template_path = DATA_DIR / "hanzi_template.json"
        if not template_path.exists():
            raise HTTPException(status_code=500, detail="Template file not found")
        with open(template_path, "r", encoding="utf-8") as f:
            template_data = json.load(f)

        qfmt = template_data["qfmt"].replace("__HANZI_WRITER_VERSION__", "2.2")
        qfmt = qfmt.replace("__CHARACTER_WIDTH__", "250").replace(
            "__CHARACTER_HEIGHT__", "250"
        )
        afmt = template_data["afmt"].replace("__HANZI_WRITER_VERSION__", "2.2")
        afmt = afmt.replace("__STROKE_ANIMATION_SPEED__", "1")
        afmt = afmt.replace("__DELAY_BETWEEN_STROKES__", "150")

        model = genanki.Model(
            1607392319,
            "Hanzi Stroke Order QingDu",
            fields=[
                {"name": "Translation"},
                {"name": "Hanzi"},
                {"name": "Pinyin"},
                {"name": "Mp3"},
                {"name": "DeckIdentifier"},
            ],
            templates=[{"name": "Hanzi Card", "qfmt": qfmt, "afmt": afmt}],
        )

        decks: list = []
        deck_id_base = vocab_list.anki_deck_id or (2000000 + list_id)

        for section in sections:
            section_name = section.get("name", "Main")
            words = section.get("words", [])
            if not words:
                continue
            subdeck_name = f"{vocab_list.name}::{section_name}"
            subdeck_id = deck_id_base + hash(section_name) % 100000
            subdeck = genanki.Deck(subdeck_id, subdeck_name)
            deck_identifier = f"[{subdeck_name}]"

            for word_data in words:
                hanzi = word_data.get("hanzi", "")
                pinyin = word_data.get("pinyin", "")
                meaning = word_data.get("meaning", "")
                if not hanzi:
                    continue

                words_processed += 1
                mp3_field = ""

                try:
                    unicode_ids = "_".join(str(ord(char)) for char in hanzi)
                    cache_filename = f"{unicode_ids}_zh.mp3"
                    cache_path = audio_cache_dir / cache_filename
                    mp3_filename = os.path.join(
                        temp_dir, f"{unicode_ids}_pronunciation.mp3"
                    )

                    if cache_path.exists() and cache_path.stat().st_size > 0:
                        shutil.copy2(cache_path, mp3_filename)
                        media_files.append(mp3_filename)
                        mp3_field = f"[sound:{os.path.basename(mp3_filename)}]"
                        audio_cached += 1
                        consecutive_failures = 0
                    elif not rate_limited and consecutive_failures < 5:
                        try:
                            tts = gTTS(hanzi, lang="zh")
                            tts.save(mp3_filename)
                            shutil.copy2(mp3_filename, cache_path)
                            media_files.append(mp3_filename)
                            mp3_field = f"[sound:{os.path.basename(mp3_filename)}]"
                            audio_generated += 1
                            consecutive_failures = 0
                            time.sleep(0.1)
                        except Exception as tts_error:
                            error_msg = str(tts_error)
                            if "429" in error_msg or "Too Many Requests" in error_msg:
                                logger.warning(f"Rate limit hit at word '{hanzi}'")
                                rate_limited = True
                            else:
                                logger.debug(f"TTS failed for '{hanzi}': {tts_error}")
                                consecutive_failures += 1
                            audio_failed += 1
                            failed_words.append(hanzi)
                    else:
                        audio_failed += 1
                except Exception as e:
                    audio_failed += 1
                    failed_words.append(hanzi)
                    logger.debug(f"Audio processing failed for '{hanzi}': {e}")

                note = genanki.Note(
                    model=model,
                    fields=[meaning, hanzi, pinyin, mp3_field, deck_identifier],
                )
                subdeck.add_note(note)

            if subdeck.notes:
                decks.append(subdeck)

        if not decks:
            raise HTTPException(status_code=400, detail="No words found to export")

        package = genanki.Package(decks)
        package.media_files = media_files

        output_filename = f"{vocab_list.name.replace(' ', '_')}.apkg"
        output_path = os.path.join(temp_dir, output_filename)
        package.write_to_file(output_path)

        with open(output_path, "rb") as f:
            apkg_content = f.read()

        shutil.rmtree(temp_dir)

        logger.info(
            f"Export complete: {words_processed} words, {audio_cached} cached, "
            f"{audio_generated} generated, {audio_failed} failed"
        )
        if rate_limited:
            logger.warning(
                f"Rate limit reached. {audio_failed} cards created without audio."
            )

        return Response(
            content=apkg_content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={output_filename}",
                "Content-Length": str(len(apkg_content)),
                "X-Export-Stats": (
                    f"{words_processed}|{audio_cached}|{audio_generated}|{audio_failed}"
                ),
                "X-Rate-Limited": "true" if rate_limited else "false",
            },
        )
    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        logger.error(f"Export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/api/vocabulary-lists/{list_id}/export")
async def export_vocabulary_list_csv(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Export a vocabulary list as CSV (`hanzi;pinyin;meaning;level`)."""
    vocab_list = _owned_list(db, user, list_id)
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    csv_lines = [
        f"{w.get('hanzi','')};{w.get('pinyin','')};{w.get('meaning','')};{w.get('level','')}"
        for section in sections
        for w in section.get("words", [])
    ]
    csv_content = "\n".join(csv_lines)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename={vocab_list.name.replace(' ', '_')}.csv"
            )
        },
    )

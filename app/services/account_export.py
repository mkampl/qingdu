"""Everything the server knows about one account, as one JSON document
(GET /api/auth/export)."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.database import SavedText, TextFolder, User, UserWord, UserWordEvent, VocabularyList
from app.services.timestamps import iso_utc


def export_account(db: Session, user: User) -> dict:
    words = db.query(UserWord).filter(UserWord.user_id == user.id).all()
    return {
        "format": "qingdu-export",
        "version": 1,
        "exported_at": iso_utc(datetime.utcnow()),
        "profile": {
            "username": user.username,
            "created_at": iso_utc(user.created_at),
            "settings": {
                "daily_new_words": user.daily_new_words,
                "hsk_focus_version": user.hsk_focus_version,
                "display_script": user.display_script,
                "review_retention": user.review_retention,
                "review_window": user.review_window,
                "review_focus": user.review_focus,
                "timezone": user.timezone,
            },
        },
        "texts": [
            {
                "title": t.title,
                "content": t.content,
                "tags": t.tags,
                "reading_progress": t.reading_progress,
                "created_at": iso_utc(t.created_at),
                "folder_id": t.folder_id,
                "position": t.position,
            }
            for t in db.query(SavedText).filter(SavedText.user_id == user.id).all()
        ],
        "text_folders": [
            {"id": f.id, "name": f.name, "parent_id": f.parent_id, "position": f.position}
            for f in db.query(TextFolder).filter(TextFolder.user_id == user.id).all()
        ],
        "vocabulary_lists": [
            {
                "name": vl.name,
                "list_type": vl.list_type,
                "sections": vl.sections,
                "apply_as_glossary": vl.apply_as_glossary,
                "created_at": iso_utc(vl.created_at),
            }
            for vl in db.query(VocabularyList).filter(VocabularyList.user_id == user.id).all()
        ],
        "words": [
            {
                "word": w.word,
                "state": w.state,
                "seen_count": w.seen_count,
                "pinyin": w.pinyin,
                "meaning": w.meaning,
                "ease": w.ease,
                "stability": w.stability,
                "difficulty": w.difficulty,
                "due_at": iso_utc(w.due_at),
                "last_reviewed_at": iso_utc(w.last_reviewed_at),
                "glosses": [
                    {
                        "meaning": g.meaning,
                        "pinyin": g.pinyin,
                        "source": g.source,
                        "source_tag": g.source_tag,
                    }
                    for g in w.glosses
                ],
            }
            for w in words
        ],
        "review_events": [
            {
                "word": e.word,
                "event_type": e.event_type,
                "new_state": e.new_state,
                "grade": e.grade,
                "mode": e.mode,
                "created_at": iso_utc(e.created_at),
            }
            for e in db.query(UserWordEvent)
            .filter(UserWordEvent.user_id == user.id)
            .order_by(UserWordEvent.created_at)
            .all()
        ],
    }

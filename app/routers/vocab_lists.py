import json
import logging
import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints
from pypinyin import Style, lazy_pinyin
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, VocabularyList, get_db
from app.services import dict_data
from app.services.gloss_refresh import is_user_meaning, refresh_vocab_list
from app.services.migrations import migrate_vocabulary_sections
from app.services.script import convert_vocab_sections, to_user_script

router = APIRouter(tags=["Vocabulary Lists"])
logger = logging.getLogger(__name__)


# Request bodies. Words and sections allow extra keys because the SPA
# round-trips whatever GET returned (migrated level fields, 'traditional').
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ListWord(BaseModel):
    model_config = ConfigDict(extra="allow")

    hanzi: NonEmpty
    pinyin: str | None = None
    meaning: str | None = None
    level: str | None = None


class ListSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: NonEmpty
    words: list[ListWord] = []


class CreateListRequest(BaseModel):
    name: NonEmpty
    type: str = "custom"
    sections: list[ListSection] = []


class UpdateListRequest(BaseModel):
    name: NonEmpty | None = None
    sections: list[ListSection] | None = None
    apply_as_glossary: bool | None = None


class AddWordRequest(BaseModel):
    section_name: NonEmpty
    hanzi: NonEmpty
    meaning: str = ""


class AddSectionRequest(BaseModel):
    name: NonEmpty


class RenameSectionRequest(BaseModel):
    old_name: NonEmpty
    new_name: NonEmpty


class WordPatch(BaseModel):
    hanzi: NonEmpty | None = None
    meaning: str | None = None


class UpdateWordRequest(BaseModel):
    section_name: NonEmpty
    old_hanzi: NonEmpty
    word: WordPatch


class DeleteWordRequest(BaseModel):
    section_name: NonEmpty
    hanzi: NonEmpty


def _dump_sections(sections: list[ListSection]) -> str:
    return json.dumps([s.model_dump(exclude_none=True) for s in sections])


def _load_sections(vocab_list: VocabularyList) -> list[dict]:
    """Stored sections, defensively: lists saved before request validation
    can hold sections without a name or words, which used to KeyError
    every later mutation."""
    try:
        raw = json.loads(vocab_list.sections) if vocab_list.sections else []
    except (TypeError, ValueError):
        logger.warning("vocab list %s has unreadable sections; treating as empty", vocab_list.id)
        return []
    sections = []
    for section in raw if isinstance(raw, list) else []:
        if not isinstance(section, dict):
            continue
        section.setdefault("name", "")
        words = section.get("words")
        section["words"] = [
            w for w in (words if isinstance(words, list) else []) if isinstance(w, dict)
        ]
        for w in section["words"]:
            w.setdefault("hanzi", "")
        sections.append(section)
    return sections


def _owned_list(db: Session, user: User, list_id: int) -> VocabularyList:
    """Return the list if it belongs to `user`, else 404."""
    vocab_list = (
        db.query(VocabularyList)
        .filter(VocabularyList.id == list_id, VocabularyList.user_id == user.id)
        .first()
    )
    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")
    return vocab_list


@router.post("/api/vocabulary-lists")
async def create_vocabulary_list(
    list_data: CreateListRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Create a vocabulary list (auto-generates a unique Anki deck ID)."""
    anki_deck_id = 2000000 + random.randint(1, 999999)
    vocab_list = VocabularyList(
        user_id=user.id,
        name=list_data.name,
        list_type=list_data.type,
        sections=_dump_sections(list_data.sections),
        anki_deck_id=anki_deck_id,
    )
    db.add(vocab_list)
    db.commit()
    return {"id": vocab_list.id, "message": "List created"}


def _serialize_list(vocab_list: VocabularyList, user: User) -> dict:
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    migrated_sections = migrate_vocabulary_sections(sections)
    # Display-script conversion: each word's hanzi (and the
    # 'traditional' duplicate, when present) goes to the user's
    # preferred script. Pinyin / meanings / list name pass through.
    convert_vocab_sections(migrated_sections, user)
    return {
        "id": vocab_list.id,
        "name": to_user_script(vocab_list.name or "", user),
        "type": vocab_list.list_type,
        "sections": migrated_sections,
        "apply_as_glossary": bool(vocab_list.apply_as_glossary),
    }


@router.get("/api/vocabulary-lists")
async def get_vocabulary_lists(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Return all vocabulary lists for the current user, with auto-migration."""
    lists = db.query(VocabularyList).filter(VocabularyList.user_id == user.id).all()
    version = dict_data.dict_version()
    for vocab_list in lists:
        refresh_vocab_list(db, vocab_list, version)
    return [_serialize_list(vocab_list, user) for vocab_list in lists]


@router.get("/api/vocabulary-lists/{list_id}")
async def get_vocabulary_list(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """One list, same shape as an entry of the list endpoint."""
    vocab_list = _owned_list(db, user, list_id)
    refresh_vocab_list(db, vocab_list)
    return _serialize_list(vocab_list, user)


@router.put("/api/vocabulary-lists/{list_id}")
async def update_vocabulary_list(
    list_id: int,
    list_data: UpdateListRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    # PATCH-style: only update fields the caller sent. Previously this
    # wiped `sections` to [] when a caller omitted the key — a footgun
    # that Phase #99's glossary toggle would have triggered on every flip.
    if list_data.name is not None:
        vocab_list.name = list_data.name
    if list_data.sections is not None:
        vocab_list.sections = _dump_sections(list_data.sections)
    if list_data.apply_as_glossary is not None:
        vocab_list.apply_as_glossary = list_data.apply_as_glossary
    db.commit()
    return {"message": "List updated"}


@router.delete("/api/vocabulary-lists/{list_id}")
async def delete_vocabulary_list(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    db.delete(vocab_list)
    db.commit()
    return {"message": "List deleted"}


@router.post("/api/vocabulary-lists/{list_id}/words")
async def add_word_to_list(
    list_id: int,
    word_data: AddWordRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Add a word to a section (creating the section if missing).

    A word that is already anywhere in the list is a 409 naming the
    section it sits in, so the client can say so instead of "Added".
    """
    vocab_list = _owned_list(db, user, list_id)
    sections = _load_sections(vocab_list)
    hanzi = word_data.hanzi
    for existing in sections:
        if any(w["hanzi"] == hanzi for w in existing["words"]):
            raise HTTPException(
                status_code=409,
                detail=f"「{hanzi}」 is already in this list (section “{existing['name']}”).",
            )

    section_name = word_data.section_name
    section = next((s for s in sections if s["name"] == section_name), None)
    if not section:
        section = {"name": section_name, "words": []}
        sections.append(section)

    pinyin = " ".join(lazy_pinyin(hanzi, style=Style.TONE))
    entry = {
        "hanzi": hanzi,
        "pinyin": pinyin,
        "meaning": word_data.meaning,
        "level": "Custom",
    }
    # A meaning other than the dictionary's (typed by hand, or a glossary
    # or package gloss picked up in the reader) is kept through later
    # dictionary refreshes.
    if is_user_meaning(hanzi, word_data.meaning):
        entry["edited"] = True
    section["words"].append(entry)
    vocab_list.sections = json.dumps(sections)
    db.commit()
    return {"message": "Word added", "added": True, "pinyin": pinyin}


@router.post("/api/vocabulary-lists/{list_id}/sections")
async def add_section_to_list(
    list_id: int,
    section_data: AddSectionRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    sections = _load_sections(vocab_list)
    logger.info(
        f"Before adding: list {list_id} has {len(sections)} sections: "
        f"{[s['name'] for s in sections]}"
    )
    section_name = section_data.name
    if any(s["name"] == section_name for s in sections):
        raise HTTPException(status_code=409, detail="Section already exists")

    sections.append({"name": section_name, "words": []})
    vocab_list.sections = json.dumps(sections)
    db.commit()
    db.refresh(vocab_list)

    updated_sections = _load_sections(vocab_list)
    logger.info(
        f"After commit: list {list_id} has {len(updated_sections)} sections: "
        f"{[s['name'] for s in updated_sections]}"
    )
    return {
        "message": "Section added",
        "name": section_name,
        "total_sections": len(updated_sections),
    }


@router.put("/api/vocabulary-lists/{list_id}/sections")
async def rename_section(
    list_id: int,
    section_data: RenameSectionRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    old_name = section_data.old_name
    new_name = section_data.new_name

    sections = _load_sections(vocab_list)
    section = next((s for s in sections if s["name"] == old_name), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if any(s["name"] == new_name for s in sections if s["name"] != old_name):
        raise HTTPException(status_code=409, detail="Section name already exists")

    section["name"] = new_name
    vocab_list.sections = json.dumps(sections)
    db.commit()
    return {"message": "Section renamed"}


@router.delete("/api/vocabulary-lists/{list_id}/sections/{section_name}")
async def delete_section(
    list_id: int,
    section_name: str,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    sections = _load_sections(vocab_list)
    section = next((s for s in sections if s["name"] == section_name), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    sections = [s for s in sections if s["name"] != section_name]
    vocab_list.sections = json.dumps(sections)
    db.commit()
    return {
        "message": "Section deleted",
        "word_count": len(section.get("words", [])),
    }


@router.put("/api/vocabulary-lists/{list_id}/words")
async def update_word_in_list(
    list_id: int,
    word_data: UpdateWordRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Update one word in a section. Forces level back to 'Custom' on edit."""
    vocab_list = _owned_list(db, user, list_id)
    section_name = word_data.section_name
    old_hanzi = word_data.old_hanzi
    new_word = word_data.word

    sections = _load_sections(vocab_list)
    section = next((s for s in sections if s["name"] == section_name), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    word = next((w for w in section["words"] if w["hanzi"] == old_hanzi), None)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    new_hanzi = new_word.hanzi or word["hanzi"]
    if new_hanzi != old_hanzi and any(w["hanzi"] == new_hanzi for w in section["words"]):
        # Two rows with the same hanzi break the list view (keyed by hanzi)
        # and make every later edit/delete ambiguous.
        raise HTTPException(
            status_code=409,
            detail=f"「{new_hanzi}」 is already in section “{section_name}”.",
        )
    if new_word.meaning is not None and (
        new_hanzi != old_hanzi or new_word.meaning != word.get("meaning")
    ):
        # Edited meanings survive dictionary refreshes; one that matches
        # the dictionary (or is cleared) keeps following it.
        if is_user_meaning(new_hanzi, new_word.meaning):
            word["edited"] = True
        else:
            word.pop("edited", None)
    word["hanzi"] = new_hanzi
    word["pinyin"] = " ".join(lazy_pinyin(new_hanzi, style=Style.TONE))
    if new_word.meaning is not None:
        word["meaning"] = new_word.meaning
    word["level"] = "Custom"

    vocab_list.sections = json.dumps(sections)
    db.commit()
    return {"message": "Word updated", "pinyin": word["pinyin"]}


@router.delete("/api/vocabulary-lists/{list_id}/words")
async def delete_word_from_list(
    list_id: int,
    word_data: DeleteWordRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    section_name = word_data.section_name
    hanzi = word_data.hanzi

    sections = _load_sections(vocab_list)
    section = next((s for s in sections if s["name"] == section_name), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    original_count = len(section["words"])
    section["words"] = [w for w in section["words"] if w["hanzi"] != hanzi]
    if len(section["words"]) == original_count:
        raise HTTPException(status_code=404, detail="Word not found")

    vocab_list.sections = json.dumps(sections)
    db.commit()
    return {"message": "Word deleted"}

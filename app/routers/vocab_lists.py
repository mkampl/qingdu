import json
import logging
import random

from fastapi import APIRouter, Depends, HTTPException
from pypinyin import Style, lazy_pinyin
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, VocabularyList, get_db
from app.services.migrations import migrate_vocabulary_sections
from app.services.script import convert_vocab_sections, to_user_script

router = APIRouter(tags=["Vocabulary Lists"])
logger = logging.getLogger(__name__)


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
    list_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Create a vocabulary list (auto-generates a unique Anki deck ID)."""
    anki_deck_id = 2000000 + random.randint(1, 999999)
    vocab_list = VocabularyList(
        user_id=user.id,
        name=list_data.get("name"),
        list_type=list_data.get("type", "custom"),
        sections=json.dumps(list_data.get("sections", [])),
        anki_deck_id=anki_deck_id,
    )
    db.add(vocab_list)
    db.commit()
    return {"id": vocab_list.id, "message": "List created"}


@router.get("/api/vocabulary-lists")
async def get_vocabulary_lists(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Return all vocabulary lists for the current user, with auto-migration."""
    lists = db.query(VocabularyList).filter(VocabularyList.user_id == user.id).all()
    result = []
    for vocab_list in lists:
        sections = json.loads(vocab_list.sections) if vocab_list.sections else []
        migrated_sections = migrate_vocabulary_sections(sections)
        # Display-script conversion: each word's hanzi (and the
        # 'traditional' duplicate, when present) goes to the user's
        # preferred script. Pinyin / meanings / list name pass through.
        convert_vocab_sections(migrated_sections, user)
        result.append(
            {
                "id": vocab_list.id,
                "name": to_user_script(vocab_list.name or "", user),
                "type": vocab_list.list_type,
                "sections": migrated_sections,
                "apply_as_glossary": bool(vocab_list.apply_as_glossary),
            }
        )
    return result


@router.put("/api/vocabulary-lists/{list_id}")
async def update_vocabulary_list(
    list_id: int,
    list_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    # PATCH-style: only update fields the caller sent. Previously this
    # wiped `sections` to [] when a caller omitted the key — a footgun
    # that Phase #99's glossary toggle would have triggered on every flip.
    if "name" in list_data:
        vocab_list.name = list_data["name"]
    if "sections" in list_data:
        vocab_list.sections = json.dumps(list_data["sections"])
    if "apply_as_glossary" in list_data:
        vocab_list.apply_as_glossary = bool(list_data["apply_as_glossary"])
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
    word_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Add a word to a section (creating the section if missing)."""
    vocab_list = _owned_list(db, user, list_id)
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    section_name = word_data.get("section_name")
    section = next((s for s in sections if s["name"] == section_name), None)
    if not section:
        section = {"name": section_name, "words": []}
        sections.append(section)

    hanzi = word_data.get("hanzi")
    pinyin = " ".join(lazy_pinyin(hanzi, style=Style.TONE))
    word = {
        "hanzi": hanzi,
        "pinyin": pinyin,
        "meaning": word_data.get("meaning"),
        "level": "Custom",
    }
    if any(w["hanzi"] == word["hanzi"] for w in section["words"]):
        return {"message": "Word already in list"}

    section["words"].append(word)
    vocab_list.sections = json.dumps(sections)
    db.commit()
    return {"message": "Word added", "pinyin": pinyin}


@router.post("/api/vocabulary-lists/{list_id}/sections")
async def add_section_to_list(
    list_id: int,
    section_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    logger.info(
        f"Before adding: list {list_id} has {len(sections)} sections: "
        f"{[s['name'] for s in sections]}"
    )
    section_name = section_data.get("name", "").strip()
    if not section_name:
        raise HTTPException(status_code=400, detail="Section name required")
    if any(s["name"] == section_name for s in sections):
        raise HTTPException(status_code=400, detail="Section already exists")

    sections.append({"name": section_name, "words": []})
    vocab_list.sections = json.dumps(sections)
    db.commit()
    db.refresh(vocab_list)

    updated_sections = json.loads(vocab_list.sections) if vocab_list.sections else []
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
    section_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    old_name = section_data.get("old_name")
    new_name = section_data.get("new_name", "").strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="Both old_name and new_name required")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    section = next((s for s in sections if s["name"] == old_name), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if any(s["name"] == new_name for s in sections if s["name"] != old_name):
        raise HTTPException(status_code=400, detail="Section name already exists")

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
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
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
    word_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Update one word in a section. Forces level back to 'Custom' on edit."""
    vocab_list = _owned_list(db, user, list_id)
    section_name = word_data.get("section_name")
    old_hanzi = word_data.get("old_hanzi")
    new_word = word_data.get("word")
    if not section_name or not old_hanzi or not new_word:
        raise HTTPException(status_code=400, detail="section_name, old_hanzi, and word required")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    section = next((s for s in sections if s["name"] == section_name), None)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    word = next((w for w in section["words"] if w["hanzi"] == old_hanzi), None)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    new_hanzi = new_word.get("hanzi", word["hanzi"])
    word["hanzi"] = new_hanzi
    word["pinyin"] = " ".join(lazy_pinyin(new_hanzi, style=Style.TONE))
    word["meaning"] = new_word.get("meaning", word["meaning"])
    word["level"] = "Custom"

    vocab_list.sections = json.dumps(sections)
    db.commit()
    return {"message": "Word updated", "pinyin": word["pinyin"]}


@router.delete("/api/vocabulary-lists/{list_id}/words")
async def delete_word_from_list(
    list_id: int,
    word_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    vocab_list = _owned_list(db, user, list_id)
    section_name = word_data.get("section_name")
    hanzi = word_data.get("hanzi")
    if not section_name or not hanzi:
        raise HTTPException(status_code=400, detail="section_name and hanzi required")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
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

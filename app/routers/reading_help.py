"""LLM help while reading: comprehension questions for a saved text
(services/text_quiz) and what a word means in its sentence
(services/word_sense)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import SavedText, User, get_db
from app.services import llm, text_quiz, word_sense
from app.services.reading_progress import READ_THROUGH, progress_fraction
from app.services.streak import record_activity

router = APIRouter(tags=["Reading help"])


class QuizAnswers(BaseModel):
    answers: list[int]


class SenseRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=20)
    sentence: str = Field(..., min_length=1, max_length=400)
    # Meanings the user's lists give the word (WordInfo.user_glosses).
    glosses: list[str] = Field(default_factory=list, max_length=5)


def _text(db: Session, user: User, text_id: int) -> SavedText:
    text = db.query(SavedText).filter(SavedText.id == text_id, SavedText.user_id == user.id).first()
    if text is None:
        raise HTTPException(status_code=404, detail="Text not found")
    return text


@router.get("/api/texts/{text_id}/quiz")
def get_quiz(
    text_id: int, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    """The text's questions without the answers; none until written."""
    quiz = text_quiz.stored(_text(db, user, text_id))
    return text_quiz.client(quiz) if quiz else {"questions": []}


@router.post("/api/texts/{text_id}/quiz/write")
async def write_quiz(
    text_id: int, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    """Have the LLM write the questions (again, when there are some)."""
    text = _text(db, user, text_id)
    llm.require(text_quiz.FEATURE)
    llm.charge(db, user.id)
    try:
        quiz = await text_quiz.write(db, text)
    except llm.LlmError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return text_quiz.client(quiz)


@router.post("/api/texts/{text_id}/quiz")
def grade_quiz(
    text_id: int,
    body: QuizAnswers,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Grade the answers; all right = the text counts as read."""
    text = _text(db, user, text_id)
    quiz = text_quiz.stored(text)
    if quiz is None:
        raise HTTPException(status_code=404, detail="No questions for this text yet")
    if len(body.answers) != len(quiz["questions"]):
        raise HTTPException(status_code=400, detail="Expected an answer for every question")
    results = text_quiz.grade(quiz, body.answers)
    all_correct = all(results)
    if all_correct and progress_fraction(text.reading_progress) < READ_THROUGH:
        text.reading_progress = 1.0
        record_activity(user, db)
        db.commit()
    return {"results": results, "all_correct": all_correct}


@router.post("/api/words/sense")
async def sense(
    body: SenseRequest, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    """What the word means in this sentence."""
    if body.word not in body.sentence:
        raise HTTPException(status_code=422, detail="The word is not in the sentence")
    llm.require(word_sense.FEATURE)
    llm.charge(db, user.id)
    try:
        return await word_sense.sense_in(body.word, body.sentence, body.glosses)
    except llm.LlmError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

"""How readable a text is for the signed-in user ("make this text readable").

The reader posts the tokens of the text it shows; the response says what
share of the running words the user knows, how much more counts once the
words in review are learned, and which words are still missing. See
services/readability for the counting rules.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, get_db
from app.services import readability
from app.services.script import to_canonical, to_user_script

router = APIRouter(tags=["Readability"])


class ReadabilityRequest(BaseModel):
    # The text's tokens in reading order, as the analysis split them.
    tokens: list[str] = Field(default_factory=list, max_length=60000)
    # Words with a meaning of their own in this text (package or glossary
    # terms) that count as words although no dictionary has them.
    extra: list[str] = Field(default_factory=list, max_length=5000)


def summary_payload(summary: readability.Summary, user: User) -> dict:
    return {
        "threshold": summary.threshold,
        "total": summary.total,
        "unique": summary.unique,
        "known": summary.known,
        "in_progress": summary.in_progress,
        "known_pct": round(summary.known_pct, 4),
        "with_progress_pct": round(summary.with_progress_pct, 4),
        "to_unlock": summary.to_unlock,
        "unlocked": summary.unlocked,
        "missing_count": len(summary.missing),
        "missing": [
            {**readability.missing_payload(w, c), "word": to_user_script(w, user)}
            for w, c in summary.missing[: readability.MAX_MISSING_LISTED]
        ],
        "in_progress_words": [to_user_script(w, user) for w in summary.in_progress_words],
    }


@router.post("/api/readability")
def text_readability(
    payload: ReadabilityRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Readability of the posted tokens for the signed-in user."""
    tokens = [to_canonical(t, user) for t in payload.tokens]
    extra = {to_canonical(w.strip(), user) for w in payload.extra if w.strip()}
    summary = readability.for_user(db, user.id, tokens, extra=extra)
    return summary_payload(summary, user)

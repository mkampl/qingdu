"""Comprehension questions for a saved text, written by the LLM.

Five multiple-choice questions in English on what the text says, like the
library's quizzes. The model gives the right answer and three wrong ones;
the options are shuffled here, so the answer is not always in the same
place. The questions are stored on the text (`saved_texts.quiz`) with a
hash of its content, so an edited text gets new ones, and they are graded
on the server: the answer key never goes to the browser. All right means
the text counts as read to the end.
"""

from __future__ import annotations

import hashlib
import json
import random

from app.database import SavedText
from app.services import llm
from app.services.text_series import plain

FEATURE = "quiz"
QUESTIONS = 5
MIN_QUESTIONS = 3
# A long text is asked about from its start.
MAX_CHARS = 4000

SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "correct": {"type": "string"},
                    "wrong": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question", "correct", "wrong"],
            },
        }
    },
    "required": ["questions"],
}

PROMPT = """Write {n} multiple-choice questions in English that check whether a learner understood
this Chinese text{part}. Ask about what happens and what is said, in the order of the text, not
about single words or grammar. For each question give the right answer and three wrong answers
that sound possible but are clearly wrong for someone who read the text. Keep the answers short
(at most 12 words) and in English.

Text:
{text}
"""


def content_hash(content: str) -> str:
    return hashlib.sha1((content or "").encode("utf-8")).hexdigest()


def stored(text: SavedText) -> dict | None:
    """The text's questions with their answers, if they fit its content."""
    try:
        quiz = json.loads(text.quiz or "null")
    except ValueError:
        return None
    if not isinstance(quiz, dict) or quiz.get("hash") != content_hash(text.content or ""):
        return None
    return quiz if quiz.get("questions") else None


def client(quiz: dict) -> dict:
    """What the browser gets: questions and options, no answer key."""
    return {
        "questions": [{"prompt": q["prompt"], "options": q["options"]} for q in quiz["questions"]]
    }


def _question(raw: dict, rng: random.Random) -> dict | None:
    prompt = plain(str(raw.get("question") or ""))
    correct = plain(str(raw.get("correct") or ""))
    wrong = []
    for w in raw.get("wrong") or []:
        w = plain(str(w))
        if w and w.lower() != correct.lower() and w.lower() not in {x.lower() for x in wrong}:
            wrong.append(w)
    if not prompt or not correct or len(wrong) < 3:
        return None
    options = [correct, *wrong[:3]]
    rng.shuffle(options)
    return {"prompt": prompt, "options": options, "answer_index": options.index(correct)}


async def write(db, text: SavedText) -> dict:
    """Ask the LLM for the questions and store them on the text."""
    content = text.content or ""
    part = " (its beginning)" if len(content) > MAX_CHARS else ""
    reply = await llm.chat(
        [
            {
                "role": "user",
                "content": PROMPT.format(n=QUESTIONS, part=part, text=content[:MAX_CHARS]),
            }
        ],
        schema=SCHEMA,
        max_tokens=1800,
        temperature=0.4,
        timeout=120,
    )
    digest = content_hash(content)
    rng = random.Random(digest)
    questions = [
        q
        for q in (_question(r, rng) for r in (reply.get("questions") or [])[:QUESTIONS])
        if q is not None
    ]
    if len(questions) < MIN_QUESTIONS:
        raise llm.LlmError("The model wrote no usable questions")
    quiz = {"hash": digest, "questions": questions}
    text.quiz = json.dumps(quiz, ensure_ascii=False)
    db.commit()
    return quiz


def grade(quiz: dict, answers: list[int]) -> list[bool]:
    return [a == q["answer_index"] for a, q in zip(answers, quiz["questions"], strict=True)]


__all__ = ["FEATURE", "client", "content_hash", "grade", "stored", "write"]

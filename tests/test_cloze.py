"""
Cloze-mode review: sentence extraction + blanking + lazy population.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, SavedText, User, UserWord
from app.services import cloze


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()
    s.add(User(id=1, username="alice", password_hash="x", invite_quota=0))
    s.commit()
    yield s
    s.close()


def test_split_sentences_on_chinese_punctuation():
    text = "我喜欢学中文。她也喜欢！你呢？"
    parts = cloze.split_sentences(text)
    assert parts == ["我喜欢学中文。", "她也喜欢！", "你呢？"]


def test_find_sentence_prefers_shortest_match():
    # Two sentences contain 学 — the shorter one wins.
    text = "他每天都很认真地学习中文，特别喜欢看古文。我也学。"
    s = cloze.find_sentence_for_word(text, "学")
    assert s == "我也学。"


def test_find_sentence_returns_none_when_word_absent():
    assert cloze.find_sentence_for_word("我吃饭。", "中文") is None


def test_find_sentence_truncates_runaway_sentence():
    # Build a sentence longer than _MAX_SENTENCE_CHARS so we exercise the
    # truncation branch. The target word is buried in the middle.
    target = "目标"
    long = ("一" * 60) + target + ("二" * 60) + "。"
    s = cloze.find_sentence_for_word(long, target)
    assert s is not None
    assert target in s
    assert "…" in s  # truncation marker
    assert len(s) <= 82  # _MAX_SENTENCE_CHARS + ellipses


def test_make_cloze_template_blanks_first_occurrence_only():
    sentence = "我喜欢学中文，他也喜欢学中文。"
    template = cloze.make_cloze_template(sentence, "中文")
    # Only the first occurrence becomes ___; the second remains visible.
    assert template == "我喜欢学___，他也喜欢学中文。"


def test_make_cloze_template_handles_word_not_in_sentence():
    # Defensive — caller shouldn't pass mismatched data, but if it does
    # we return the sentence unchanged rather than blowing up.
    assert cloze.make_cloze_template("我吃饭。", "中文") == "我吃饭。"


def test_populate_sample_sentence_pulls_from_users_saved_text(db_session):
    db_session.add(
        SavedText(
            user_id=1,
            title="Lesson 1",
            content="我喜欢学中文。她也喜欢学中文。",
            analysis_data="{}",
        )
    )
    row = UserWord(user_id=1, word="中文", state="learning")
    db_session.add(row)
    db_session.commit()

    chosen = cloze.populate_sample_sentence(row, db_session)
    db_session.commit()
    assert chosen == "我喜欢学中文。"
    assert row.sample_sentence == "我喜欢学中文。"


def test_populate_sample_sentence_returns_none_when_no_match(db_session):
    db_session.add(SavedText(user_id=1, title="t", content="我吃饭。", analysis_data="{}"))
    row = UserWord(user_id=1, word="奇怪", state="learning")
    db_session.add(row)
    db_session.commit()

    chosen = cloze.populate_sample_sentence(row, db_session)
    assert chosen is None
    assert row.sample_sentence is None


def test_populate_sample_sentence_is_idempotent(db_session):
    row = UserWord(user_id=1, word="中文", state="learning", sample_sentence="cached one.")
    db_session.add(row)
    db_session.commit()
    # No saved texts at all — but cached value wins, no scan needed.
    chosen = cloze.populate_sample_sentence(row, db_session)
    assert chosen == "cached one."

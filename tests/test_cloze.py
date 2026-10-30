"""
Cloze-mode review: sentence extraction + blanking + lazy population.
"""

import pytest

from app.database import SavedText, User, UserWord
from app.services import cloze


@pytest.fixture
def db_session(memory_db):
    s = memory_db()
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
    # In no saved text and in no library text either.
    row = UserWord(user_id=1, word="鸭嘴兽", state="learning")
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


def test_populate_caches_misses_until_forgotten(db_session):
    row = UserWord(user_id=1, word="鸭嘴兽", state="learning")
    db_session.add(row)
    db_session.commit()
    assert cloze.populate_sample_sentence(row, db_session) is None

    # A text arriving behind the cache's back stays invisible: the miss is
    # remembered, so the review queue doesn't rescan every session.
    db_session.add(SavedText(user_id=1, title="t", content="我看鸭嘴兽。", analysis_data="{}"))
    db_session.commit()
    assert cloze.populate_sample_sentence(row, db_session) is None

    # Saving / editing a text forgets the user's misses.
    cloze.forget_misses(1)
    assert cloze.populate_sample_sentence(row, db_session) == "我看鸭嘴兽。"


def test_populate_only_loads_matching_text(db_session):
    """The lookup asks the database for a text containing the word instead
    of pulling every saved text into Python."""
    from sqlalchemy import event

    for i in range(5):
        db_session.add(
            SavedText(user_id=1, title=f"t{i}", content="我吃饭。" * 50, analysis_data="{}")
        )
    db_session.add(SavedText(user_id=1, title="hit", content="我学中文。", analysis_data="{}"))
    row = UserWord(user_id=1, word="中文", state="learning")
    db_session.add(row)
    db_session.commit()

    statements: list[str] = []
    engine = db_session.get_bind()

    def _capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        assert cloze.populate_sample_sentence(row, db_session) == "我学中文。"
    finally:
        event.remove(engine, "before_cursor_execute", _capture)
    text_queries = [s for s in statements if "saved_texts" in s]
    assert len(text_queries) == 1
    assert "LIKE" in text_queries[0] and "LIMIT" in text_queries[0]


def test_populate_names_the_saved_text(db_session):
    db_session.add(SavedText(user_id=1, title="Lesson 1", content="我学中文。", analysis_data="{}"))
    row = UserWord(user_id=1, word="中文", state="learning")
    db_session.add(row)
    db_session.commit()
    cloze.populate_sample_sentence(row, db_session)
    assert row.sample_source == "Lesson 1"


def test_populate_falls_back_to_a_library_sentence(db_session):
    row = UserWord(user_id=1, word="感冒", state="learning")
    db_session.add(row)
    db_session.commit()
    sentence = cloze.populate_sample_sentence(row, db_session)
    assert sentence and "感冒" in sentence
    assert row.sample_source  # the library text's title


def test_library_sentences_match_whole_words_only():
    from app.services import library

    sentence, _ = library.example_sentence("会")
    # The stored segmentation decides: 会 inside 社会 does not count.
    assert "会" in sentence.replace("社会", "")


def test_adopt_sentence_keeps_the_first_context():
    row = UserWord(user_id=1, word="中文", state="learning")
    assert cloze.adopt_sentence(row, "我在学中文。", "Lesson 1")
    assert (row.sample_sentence, row.sample_source) == ("我在学中文。", "Lesson 1")
    assert not cloze.adopt_sentence(row, "她也学中文。", "Lesson 2")
    assert row.sample_sentence == "我在学中文。"


def test_adopt_sentence_ignores_a_sentence_without_the_word():
    row = UserWord(user_id=1, word="中文", state="learning")
    assert not cloze.adopt_sentence(row, "我吃饭。", None)
    assert row.sample_sentence is None

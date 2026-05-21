"""Tests for migrate_word_data idempotency and basic shape preservation."""

from app.services.migrations import migrate_word_data


def test_idempotent_when_already_migrated():
    word = {"text": "你好", "level_new": "new-1", "hsk_level": "new-1"}
    assert migrate_word_data(dict(word)) == word


def test_returns_input_when_no_level():
    word = {"text": "?"}
    assert migrate_word_data(dict(word)) == word


def test_legacy_new_level_assigns_level_new():
    word = {"text": "?somethingnotinhsk?", "hsk_level": "new-3"}
    out = migrate_word_data(word)
    assert out["level_new"] == "new-3"
    assert out["level_old"] is None


def test_legacy_old_level_assigns_level_old():
    word = {"text": "?somethingnotinhsk?", "hsk_level": "old-2"}
    out = migrate_word_data(word)
    assert out["level_old"] == "old-2"
    assert out["level_new"] is None

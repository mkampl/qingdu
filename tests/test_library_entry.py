"""GET /api/library/{slug}: the bundled analyses are brought up to the
current dictionary on open, and the quiz answer key never reaches the
client."""

import json

import pytest

from app.services import dict_data, library

SLUG = "hsk3_13_online-shopping"


def _tokens(body, text):
    return [w for w in body["analyzed"]["words"] if w.get("text") == text]


def test_entry_strips_answer_key_and_flags_quiz(client):
    body = client.get(f"/api/library/{SLUG}").json()
    assert "questions" not in body
    assert "answer_index" not in json.dumps(body)
    assert body["has_quiz"] is True
    # The bundled entry itself keeps its questions for grading.
    assert library.questions(SLUG)


@pytest.fixture
def fresh_library(monkeypatch):
    """Refreshing stamps the cached entries; start and end with clean ones."""
    monkeypatch.setattr(dict_data, "dict_version", lambda: "test-version")
    library._all_entries.cache_clear()
    yield
    library._all_entries.cache_clear()


def test_entry_glosses_follow_the_current_dictionary(client, pinned_dictionaries, fresh_library):
    body = client.get(f"/api/library/{SLUG}").json()
    toks = _tokens(body, "社会")
    assert toks, "fixture text should contain 社会"
    # The stored file was built with the old -ui tone placement (hùi).
    assert all(t["pinyin"] == "shè huì" for t in toks)
    assert body["analyzed"]["dict_version"] == "test-version"


def test_unknown_slug_is_404(client):
    assert client.get("/api/library/nope").status_code == 404

"""Anki ids of the word-state export stay the same across server runs."""

from app.routers.export import _stable_id


def test_stable_id_does_not_depend_on_the_process():
    # A fixed value: Python's salted hash() would differ per process.
    assert _stable_id("alice") == 2147484401
    assert _stable_id("alice") != _stable_id("alice-words")

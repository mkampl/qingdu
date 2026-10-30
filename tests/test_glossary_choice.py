"""Each text picks its glossaries; a list's glossary flag only offers it."""

import json

from app.database import User, VocabularyList
from app.services.word_lists import build_glossary


def _list(s, list_id, flagged, words):
    s.add(
        VocabularyList(
            id=list_id,
            user_id=1,
            name=f"L{list_id}",
            sections=json.dumps([{"name": "A", "words": words}]),
            apply_as_glossary=flagged,
        )
    )


def test_only_the_texts_chosen_lists_apply(words_client):
    s = words_client.session_factory()
    _list(s, 1, True, [{"hanzi": "自然", "meaning": "Zì Rán, the so-of-itself"}])
    _list(s, 2, False, [{"hanzi": "守窍", "meaning": "guarding an aperture"}])
    s.commit()
    user = s.get(User, 1)
    # No choice = no glossary, even with a flagged list.
    assert build_glossary(s, user, None) == {}
    assert build_glossary(s, user, []) == {}
    # A chosen list applies whether it is flagged or not.
    assert set(build_glossary(s, user, [2])) == {"守窍"}
    assert set(build_glossary(s, user, [1, 2])) == {"自然", "守窍"}
    # Without an account there is none.
    assert build_glossary(s, None, [1]) == {}
    s.close()

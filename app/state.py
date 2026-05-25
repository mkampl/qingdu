"""
Shared mutable application state.

These dicts/caches are populated at startup (`app.main.startup_event` ->
`app.services.hsk_loader.download_hsk_vocabulary`) and read by services
and routers thereafter. Importing services should always read/mutate the
dicts *in place* — never rebind the names (use `.clear()` + `.update()`
if you need to swap contents).
"""

from cachetools import TTLCache

from app.core.constants import (
    UNKNOWN_WORD_CACHE_SIZE,
    UNKNOWN_WORD_CACHE_TTL,
)

# For text analysis — includes supplementation and character components.
hsk_vocab: dict = {}

# For list generation — only original HSK words without supplementation.
hsk_lists_original: dict = {}

# CC-CEDICT — richer Chinese-English glosses than the upstream HSK list
# carries. Keyed by simplified form; each value carries traditional form,
# pinyin (tone-marked) and a meanings list. Populated by
# `app.services.cedict_loader` on startup.
cedict_vocab: dict = {}

# Online lookup cache for words missing from HSK vocabulary.
unknown_word_cache: TTLCache = TTLCache(maxsize=UNKNOWN_WORD_CACHE_SIZE, ttl=UNKNOWN_WORD_CACHE_TTL)

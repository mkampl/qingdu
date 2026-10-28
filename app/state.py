"""
Shared mutable application state.

These dicts/caches are populated at startup (`app.main.startup_event` ->
`app.services.hsk_loader.load_hsk_vocabulary`) and read by services
and routers thereafter. Importing services should always read/mutate the
dicts *in place* — never rebind the names (use `.clear()` + `.update()`
if you need to swap contents).
"""

# For text analysis — includes supplementation and character components.
hsk_vocab: dict = {}

# For list generation — only original HSK words without supplementation.
hsk_lists_original: dict = {}

# CC-CEDICT — richer Chinese-English glosses than the upstream HSK list
# carries. Keyed by simplified form; each value carries traditional form,
# pinyin (tone-marked) and a meanings list. Populated by
# `app.services.cedict_loader` on startup.
cedict_vocab: dict = {}

# Variant and traditional forms CC-CEDICT lists only in its traditional
# column (玅 for 妙): {form: simplified headword}. Forms that are a
# simplified headword themselves are left out.
cedict_variants: dict = {}

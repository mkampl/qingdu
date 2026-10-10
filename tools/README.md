# tools/

Maintainer scripts. None of them run in the app; run them from the repo root
with the app's Python environment.

| Script | What it does |
|---|---|
| `gloss_audit.py` | Snapshot every HSK word's reading and headline through the app's loaders, and diff two snapshots |
| `refresh_dictionaries.py` | Replace the vendored HSK list / CC-CEDICT in `app/data/dict/` (by hand, after reviewing the gloss diff) |
| `export_gloss_candidates.py` | Input for writing learner glosses (below) |
| `check_learner_glosses.py` | Automatic checks for learner glosses (below) |
| `split_glue_words.py` | One-off migration for glued user words |
| `fetch_prod_db.sh` | Copy the production database for local analysis |
| `generate_favicon.py` | Rebuild the favicon set |

## Learner glosses

`app/data/learner_glosses.json` gives HSK words a short learner headline in
place of CC-CEDICT's first usable sense (太 "too; very" instead of
"highest"). Each gloss is tied to the main reading it was written for and
replaces only the headline; the CC-CEDICT senses and the other readings stay
visible under it (`app/services/learner_glosses.py`). Changing the file
changes the dictionary version, so user-word snapshots refresh on the next
start.

Work one batch of levels at a time (HSK 1-2 first, then 3-4):

1. **Export** the input for each word: every CC-CEDICT reading with all its
   senses, the HSK list's English, the current headline and up to two
   library example sentences.

   ```bash
   python tools/export_gloss_candidates.py --levels 1-2 -o hsk1-2.json
   ```

2. **Write** one gloss per word from that file: `[{word, pinyin, gloss,
   confidence, note}]`. `pinyin` is the word's `main_pinyin` (tone marks,
   syllables space-separated); `gloss` is at most 40 characters, the sense a
   beginner meets first, and must paraphrase one of that reading's
   CC-CEDICT senses. No register tags, no leading parentheticals, no
   Chinese except in quotes.

3. **Check, twice.** A second, independent pass reviews every entry against
   the same export (right reading, gloss backed by a CC-CEDICT sense of it,
   the beginner sense). Entries where both passes agree are accepted. Then
   the automatic checks:

   ```bash
   python tools/check_learner_glosses.py written-hsk1-2.json --json check-hsk1-2.json
   ```

   Hard failures (exit status 1) must be fixed. Entries flagged "no sense
   support" or "low confidence" go to the hand review.

4. **Review by hand**: the disagreements between the two passes, everything
   flagged in step 3, and a random 5% of the accepted entries. If the
   sample shows more than about 2% errors, rerun step 3 with a stricter
   review.

5. **Merge** the accepted entries into `app/data/learner_glosses.json`
   (`"glosses": {word: {"pinyin", "gloss", "source": "reviewed"}}`) and run
   the checker on the merged file; it must pass.

6. **Diff and test.** Snapshot before and after the merge and review the
   headline changes, then run the golden set (it resolves headlines after
   the learner-gloss layer):

   ```bash
   python tools/gloss_audit.py snapshot -o /tmp/before.json   # on main, before the merge
   python tools/gloss_audit.py snapshot -o /tmp/after.json    # on the branch, after it
   python tools/gloss_audit.py diff /tmp/before.json /tmp/after.json --level 1 --level 2
   pytest -q tests/test_golden_glosses.py
   ```

A gloss whose pinyin no longer matches the main reading (after a dictionary
refresh or a reading-override change) is skipped at startup with a warning;
`check_learner_glosses.py app/data/learner_glosses.json` lists them as
failures, so run it after every `refresh_dictionaries.py`.

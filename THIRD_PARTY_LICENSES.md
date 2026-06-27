# Third-Party Licenses

Libraries, data, and services used by QingDu, grouped by licence.

Last reconciled: 2026-06-27 against `requirements.txt`, `frontend/package.json`, bundled `app/data/`, and Google-Fonts CDN imports in `frontend/index.html` + `frontend/src/styles/global.css`.

## Backend (Python)

### Apache 2.0 — <https://www.apache.org/licenses/LICENSE-2.0>

- **aiofiles** — Tin Tvrtkovic — <https://github.com/Tinche/aiofiles>
- **bcrypt** — Python Cryptographic Authority — <https://github.com/pyca/bcrypt>
- **opencc-python-reimplemented** — <https://github.com/yichen0831/opencc-python>
- **python-multipart** — Andrew Dunham — <https://github.com/andrew-d/python-multipart>
- **tenacity** — Julien Danjou — <https://github.com/jd/tenacity>
- **trafilatura** — Adrien Barbaresi — <https://github.com/adbar/trafilatura>

### MIT License — <https://opensource.org/licenses/MIT>

- **beautifulsoup4** — Leonard Richardson — <https://www.crummy.com/software/BeautifulSoup/>
- **cachetools** — Thomas Kemmer — <https://github.com/tkem/cachetools>
- **faster-whisper** — Guillaume Klein — <https://github.com/SYSTRAN/faster-whisper>
- **FastAPI** — Sebastián Ramírez — <https://github.com/tiangolo/fastapi>
- **fsrs** — Open Spaced Repetition — <https://github.com/open-spaced-repetition/py-fsrs>
- **genanki** — Kerrick Staley — <https://github.com/kerrickstaley/genanki>
- **gTTS** — Pierre Nicolas Durette — <https://github.com/pndurette/gTTS>
- **jieba** — Sun Junyi — <https://github.com/fxsjy/jieba>
- **pydantic** — Samuel Colvin — <https://github.com/pydantic/pydantic>
- **pypinyin** — mozillazg — <https://github.com/mozillazg/python-pinyin>
- **python-jose** — Michael Davis — <https://github.com/mpdavis/python-jose>
- **slowapi** — Laurent Savaete — <https://github.com/laurentS/slowapi>
- **SQLAlchemy** — Michael Bayer — <https://github.com/sqlalchemy/sqlalchemy>

### BSD 3-Clause — <https://opensource.org/licenses/BSD-3-Clause>

- **httpx** — Encode OSS — <https://github.com/encode/httpx>
- **Jinja2** — Armin Ronacher — <https://github.com/pallets/jinja>
- **passlib** — Eli Collins — <https://foss.heptapod.net/python-libs/passlib>
- **pypdf** — Mathieu Fenniak and contributors — <https://github.com/py-pdf/pypdf>
- **python-dotenv** — Saurabh Kumar — <https://github.com/theskumar/python-dotenv>
- **uvicorn** — Encode OSS — <https://github.com/encode/uvicorn>

### ISC — <https://opensource.org/licenses/ISC>

- **librosa** — librosa development team — <https://github.com/librosa/librosa>

### AGPL-3.0 — <https://www.gnu.org/licenses/agpl-3.0.en.html>

- **EbookLib** — Aleksandar Erkalović — <https://github.com/aerkalov/ebooklib>
  Used at import time only (parses EPUB into plain text). No EbookLib code is shipped to clients.

## Frontend (JavaScript / TypeScript)

### MIT License

- **Vue** — Evan You — <https://github.com/vuejs/core>
- **Vite** — Evan You — <https://github.com/vitejs/vite>
- **Pinia** — Eduardo San Martin Morote — <https://github.com/vuejs/pinia>
- **Vue Router** — Eduardo San Martin Morote — <https://github.com/vuejs/router>
- **Tailwind CSS** — Tailwind Labs — <https://github.com/tailwindlabs/tailwindcss>
- **@tailwindcss/vite** — Tailwind Labs — <https://github.com/tailwindlabs/tailwindcss>
- **hanzi-writer** — Chris Nicholas — <https://github.com/chanind/hanzi-writer>
- **@vitejs/plugin-vue** — Vite team — <https://github.com/vitejs/vite-plugin-vue>
- **Capacitor (core, android, cli)** — Ionic — <https://github.com/ionic-team/capacitor>
- **@capacitor/haptics** — Ionic — <https://github.com/ionic-team/capacitor-plugins>
- **@capacitor/local-notifications** — Ionic — <https://github.com/ionic-team/capacitor-plugins>
- **@capacitor/share** — Ionic — <https://github.com/ionic-team/capacitor-plugins>
- **@capacitor/splash-screen** — Ionic — <https://github.com/ionic-team/capacitor-plugins>
- **@capacitor/status-bar** — Ionic — <https://github.com/ionic-team/capacitor-plugins>
- **happy-dom**, **vitest**, **@vue/test-utils**, **@vue/tsconfig**, **vue-tsc** — dev-time only — MIT

### Apache 2.0

- **TypeScript** — Microsoft — <https://github.com/microsoft/TypeScript>
- **tesseract.js** — Naptha — <https://github.com/naptha/tesseract.js>
- **tessdata `chi_sim` model** — <https://github.com/naptha/tessdata>

## Fonts

QingDu uses self-hosted Latin display fonts via `@fontsource-variable` and CJK fonts via Google Fonts CDN. The font files themselves are SIL OFL 1.1; the npm wrappers are MIT.

### SIL Open Font License 1.1 — <https://scripts.sil.org/OFL>

- **Inter** (`@fontsource-variable/inter`) — Rasmus Andersson — <https://rsms.me/inter/>
- **Newsreader** (`@fontsource-variable/newsreader`) — Production Type — <https://github.com/productiontype/Newsreader>
- **Noto Serif SC**, **Noto Sans SC** — Google / Adobe — loaded at runtime from `fonts.googleapis.com` (CDN). Self-hosters who want to avoid Google Fonts can replace the two `@import url(...)` lines in `frontend/src/styles/global.css` with a self-hosted fallback (`Source Han Serif SC` is already listed as a fallback). See [[fonts-self-host]] if you ship an air-gapped build.

## Data

### HSK Vocabulary
- **Source**: [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary)
- **License**: MIT
- **Description**: HSK 1–9 vocabulary with pinyin and English glosses.

### CC-CEDICT
- **Source**: [mdbg.net](https://www.mdbg.net/chinese/dictionary?page=cc-cedict)
- **License**: [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **Description**: Chinese-to-English dictionary used as the primary meaning source. Downloaded as `cedict_1_0_ts_utf-8_mdbg.txt.gz` on first start, cached locally, refreshed weekly. Attribution: <https://www.mdbg.net/chinese/dictionary>.

### SUBTLEX-CH per-reading frequencies
- **Source**: SUBTLEX-CH-WF, Cai & Brysbaert (2010). <http://crr.ugent.be/programs-data/subtitle-frequencies>
- **Original licence**: CC-BY-NC-ND 4.0 (academic redistribution; non-commercial; no derivatives).
- **Bundled file**: `app/data/subtlex_char_pinyin_freq.json` — an aggregated per-(character, pinyin) sum derived from SUBTLEX-CH-WF. No transcript material is bundled.
- **Compatibility caveat**: the NC clause is the gating concern. QingDu the OSS app is MIT and free; the F-Droid build is non-commercial distribution; the planned `qingdu-premium` private fork (see [[project-qingdu-llm-features]]) would be commercial and **must not** bundle this file. The maintainer's downstream-use position (derived aggregate, not transcript material) is reasonable but has not been independently reviewed. Removing the file is a clean exit; pinyin disambiguation falls back to a lower-quality heuristic (already implemented as the absent-data path in `_per_reading_frequency`).
- **Decision before Phase 2 (F-Droid)**: keep as-is for the OSS APK with the note above; remove cleanly before any commercial distribution.

### tesseract.js OCR model
- **Source**: [tessdata `chi_sim`](https://github.com/naptha/tessdata)
- **License**: Apache 2.0
- **Description**: Simplified Chinese OCR model loaded in the browser when the user opens the Scan import tab.

### Bundled sample packages (`app/data/packages/`)
- `dao_de_jing_ch1.json` — Daodejing (道德经) chapter 1 by Laozi — public domain (~600 BCE classical Chinese text).

### HSK Library v1 (180 short reading texts)
- **Source**: Generated locally with the Gemma 4 31B model (Apache-2.0) on the maintainer's machine, then human-curated. All 180 texts are original short pieces written to demonstrate the vocabulary and grammar of a specific HSK level.
- **License**: CC0 1.0 (waived by the QingDu maintainer to the public domain). Bundled at `app/data/packages/`.

## Visual assets

- **App icon (印章 chop seal "读")** — Custom design by the QingDu maintainer using FLUX.1-dev (Apache-2.0 model weights, see [[project-qingdu-icon]]). Final raster + ICO + manifest under `static/`. Original work — no third-party rights involved.

## External runtime services

QingDu calls out to these networked services. None require API keys for the OSS build except DeepL (optional):

- **Translation chain** — DeepL (commercial T&C, opt-in via env var; the public demo holds a free key) → Google Translate → MyMemory (MyMemory free tier, attribution preserved in the chip UI).
- **Google Fonts CDN** (`fonts.googleapis.com`, `fonts.gstatic.com`) — loaded at runtime for CJK glyphs. Self-hosters should be aware this is the only third-party request the frontend makes by default.
- **gTTS** (`translate.google.com`) — server-side TTS for sentence and word readings.

## Licence Compatibility

All bundled code is under permissive licences (MIT, BSD-3-Clause, Apache-2.0, ISC) compatible with QingDu's MIT licence. Bundled data falls under (a) MIT / Apache-2.0 / CC-BY-SA / CC0 — compatible; or (b) CC-BY-NC-ND for the SUBTLEX-CH derivative file, with the caveat documented above. Fonts are SIL OFL 1.1 and CC0 (Google Fonts CDN).

EbookLib (AGPL-3.0) is used only in the server-side import pipeline and is not redistributed to clients.

For a complete list with pinned versions, see `requirements.txt` and `frontend/package.json`.

# Third-Party Licenses

Libraries, data, and services used by QingDu, grouped by licence.

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
- **TypeScript** — Microsoft — <https://github.com/microsoft/TypeScript>
- **Pinia** — Eduardo San Martin Morote — <https://github.com/vuejs/pinia>
- **Vue Router** — Eduardo San Martin Morote — <https://github.com/vuejs/router>
- **Tailwind CSS** — Tailwind Labs — <https://github.com/tailwindlabs/tailwindcss>
- **hanzi-writer** — Nick Winter — <https://github.com/chanind/hanzi-writer>
- **tesseract.js** — Naptha — <https://github.com/naptha/tesseract.js>

## Data

### HSK Vocabulary
- **Source**: [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary)
- **License**: MIT
- **Description**: HSK 1–9 vocabulary with pinyin and English glosses.

### CC-CEDICT
- **Source**: [mdbg.net](https://www.mdbg.net/chinese/dictionary?page=cc-cedict)
- **License**: [CC-BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **Description**: Chinese-to-English dictionary used as the primary meaning source. Downloaded as `cedict_1_0_ts_utf-8_mdbg.txt.gz` on first start, cached locally, refreshed weekly.

### tesseract.js OCR model
- **Source**: [tesseract.js-data](https://github.com/naptha/tessdata) (`chi_sim`)
- **License**: Apache 2.0
- **Description**: Simplified Chinese OCR model loaded in the browser when the user opens the Scan import tab.

## Licence Compatibility

All Python and JavaScript dependencies are under permissive licences (MIT, BSD-3-Clause, Apache-2.0, ISC) compatible with QingDu's MIT licence. EbookLib (AGPL-3.0) is used only in the server-side import pipeline and is not redistributed to clients.

For a complete list with pinned versions, see `requirements.txt` and `frontend/package.json`.

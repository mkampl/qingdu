# 轻读 QingDu — HSK Chinese Text Analyzer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A web app for reading Chinese text against HSK 1–9 vocabulary. Paste or import any text and get per-word difficulty colours, pinyin, and definitions; save texts and review them with built-in spaced repetition.

## Features

- HSK 1–9 analysis with colour-coded difficulty and optional pinyin overlay
- Click for word definitions; click sentences for translation (DeepL → Google → MyMemory)
- Text-to-speech for words and full passages
- Spaced-repetition review with four modes: Recognition, Dictation, Writing, Cloze
- Pronunciation check with per-syllable tone scoring
- Import from URL, EPUB, PDF, or scanned image (browser OCR)
- Personal glossaries and vocabulary lists with Anki / CSV export
- Simplified ↔ Traditional toggle across the whole app
- Public share links for saved texts

## Quick Start

```bash
git clone https://github.com/mkampl/qingdu.git
cd qingdu
docker compose up -d --build
```

App is at http://localhost:8000. First boot writes a random admin password to `./data/admin_bootstrap.txt` and prints it to the logs; you'll be forced to change it on first login.

For hot-reload + the Vite dev server on `:5173`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

See [README_SETUP.md](README_SETUP.md) for optional API-key configuration (DeepL, Google Translate).

## Self-hosting + mobile app

Run your own backend; point the official Android APK at it via **Settings → Server** (or the first-launch prompt). Two environment variables matter for cross-origin access:

- `ALLOWED_ORIGINS` — comma-separated list of origins allowed by CORS. Set this if the SPA / Capacitor wrapper talks to your server from a different host. Example: `ALLOWED_ORIGINS=https://qingdu.example.com,capacitor://localhost,http://localhost`.
- `SECRET_KEY` — JWT signing key; rotate per deployment.

The web build at `/` is same-origin so CORS isn't needed for browser users. The Capacitor build hits the server cross-origin (its WebView loads from `capacitor://localhost`), so the wrapper origin must appear in `ALLOWED_ORIGINS` on the server.

## Technology

Backend: FastAPI, jieba, pypinyin, FSRS, faster-whisper, librosa, SQLite.
Frontend: Vue 3, Vite, TypeScript, Pinia, Tailwind 4.

## License

MIT — see [LICENSE](LICENSE). Third-party attributions: [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

Dictionary data:
- HSK vocabulary: [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) (MIT)
- CC-CEDICT: [mdbg.net](https://www.mdbg.net/chinese/dictionary?page=cc-cedict) (CC-BY-SA 4.0)

## Support

[Open an issue](https://github.com/mkampl/qingdu/issues) for bugs or feature requests · [Ko-fi](https://ko-fi.com/mkampl)

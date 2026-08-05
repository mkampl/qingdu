# Features

A reading-and-study tool for Chinese learners, organised around the HSK vocabulary list and a built-in spaced-repetition loop.

## Reading

- **HSK-coloured analysis** — paste or import any Chinese text and every word is coloured by its HSK level. Mode can be set to colour by HSK level, by your personal progress (new / learning / known), or off.
- **Pinyin overlay** — three modes: auto (only above your estimated reading level), always-on, off.
- **Word definitions** — click any word for pinyin, primary meaning, full sense list, HSK level, and the radical breakdown. CC-CEDICT is the primary dictionary; HSK-only words fall back to the HSK list.
- **Sentence translation** — click any sentence for an English gloss, with provider attribution (DeepL → Google → MyMemory fallback chain).
- **Audio narration** — per-word TTS or a continuous play-bar across the whole passage with speed control.
- **Grammar patterns** — common HSK 1–4 patterns (是…的, 把, 被, 越…越…, 一边…一边…, etc.) are detected and underlined; click for a popover explanation.
- **Stroke order** — accordion in the word popover renders a hanzi-writer animation for each character.
- **Pronunciation check** — record yourself saying a word; per-syllable tone score (Whisper transcribes + librosa.pyin extracts F0; we compare contour shape to the canonical Chao-scale tone template).

## Importing

- **Paste** — the textarea handles arbitrarily long passages.
- **From URL** — server-side article extraction strips ads and chrome.
- **EPUB / PDF** — chunked by chapter; scanned PDFs are flagged.
- **Scan tab** — browser-side OCR via tesseract.js (chi_sim) for photos or screenshots.
- **Pre-analysed packages** — drop-in JSON produced upstream (e.g. by an LLM) to skip segmentation entirely. A bundled Dao De Jing chapter ships as the reference sample.

## Studying

- **Per-user word states** — each word is `new` / `learning` / `known` / `ignored`, tracked across all texts. Clicking a word in the reader promotes it to `learning`.
- **Bulk shortcuts** — mark whole pages or whole HSK levels at once (the "I already know HSK 1–N" onboarding shortcut).
- **Personal glossaries** — any vocabulary list can be flagged as a glossary; its entries override CC-CEDICT/HSK lookups during analysis. Useful for specialised corpora (classical Chinese, technical jargon).
- **Public sharing** — mint a share token for any saved text; the public URL is read-only.
- **Anki & CSV export** — vocabulary lists export to Anki `.apkg` (with TTS audio baked in) or CSV. Whole-history exports for your learning + known words too.

## Spaced repetition

`/review` runs FSRS-4.5 across four modes:

- **Recognition** — see the character, recall meaning, grade Again / Hard / Good / Easy.
- **Dictation** — listen to the TTS, type what you heard.
- **Writing** — draw each character on a 米字格 practice grid; hanzi-writer grades per-stroke accuracy.
- **Cloze** — fill in a blanked word in a real sentence from one of your saved texts.

Optional **daily auto-enrolment** seeds new HSK words into the learning pool at a configurable rate (default off; user picks 1–30 / day in Settings). Mastered words (stability ≥ 90 days) drop from "learning" colour to "known" colour automatically; a wrong answer pushes them back.

## Settings

- **Script** — auto / Simplified / Traditional. Applies to every Chinese surface (reader, saved texts, vocabulary lists, review cards). Internal data stays simp-canonical, conversion happens at the I/O boundary.
- **HSK version** — new (9-level) or old (6-level); affects both colouring and bulk-mark shortcuts.
- **Pinyin mode** — auto / on / off.
- **Word colouring** — by HSK level / by your progress / off.
- **Daily learning** — enable + target count.

## Accounts

- **Invitation-only signup** — each user can mint a limited number of invites (admin-configurable quota).
- **Admin panel** — at `/admin` for users with the flag set.
- **Daily streak** — counted from any of: word-state change, bulk mark, review grade. Visible as a flame badge in the nav. Earns a streak freeze every 7 days (capped at 2 banked) that automatically covers a missed day instead of resetting the count.
- **Weekly sparkline** — at the top of `/review`, stacked bars show reviews + words-marked over the last 7 days.
- **API tokens** — Settings → API tokens lets you mint a scoped, revocable personal access token (`read:words` / `write:words`) so another app of yours (e.g. a speaking-companion with its own whisper/LLM/TTS) can read your known/learning words and report newly-encountered ones back, without sharing your password.

## Stack

Backend: FastAPI, jieba, pypinyin, FSRS, faster-whisper, librosa, SQLite.
Frontend: Vue 3, Vite, TypeScript, Pinia, Tailwind 4, hanzi-writer, tesseract.js.
Data: HSK 1–9 from [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary); CC-CEDICT from [mdbg.net](https://www.mdbg.net/chinese/dictionary?page=cc-cedict).

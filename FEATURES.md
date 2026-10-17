# Features

A reading-and-study tool for Chinese learners, organised around the HSK vocabulary list and a built-in spaced-repetition loop.

## Getting started

- **Welcome and placement test** — a new account starts with a three-minute word test: the meaning of six words per level, moving up a level after a good round and stopping after a poor one. The words of the levels you passed can be marked as known in one step; you choose how many new words a day, and get texts that fit your level. Settings can open the test again.

## Reading

- **HSK-coloured analysis** — paste or import any Chinese text and every word is coloured by its HSK level. Mode can be set to colour by HSK level, by your personal progress (new / learning / known), or off.
- **Pinyin overlay** — three modes: auto (only above your estimated reading level), always-on, off.
- **Word definitions** — click any word for pinyin, primary meaning, full sense list, HSK level, and the radical breakdown. CC-CEDICT is the primary dictionary; HSK-only words fall back to the HSK list.
- **Sentence translation** — click any sentence for an English gloss, with provider attribution (DeepL → Google → MyMemory fallback chain).
- **Audio narration** — per-word TTS or a continuous play-bar across the whole passage with speed control.
- **Grammar patterns** — common HSK 1–4 patterns (是…的, 把, 被, 越…越…, 一边…一边…, etc.) are detected and underlined; click for a popover explanation.
- **Grammar section** — all 573 points of the HSK 3.0 grammar syllabus, by level and kind, each with an English title, explanation, structure and examples. For every point: how often you met it in texts you read to the end, your own sentences that show it (then sentences from your other texts and the library), and practice: fill the gap and put the pieces in order. A good round moves the next practice further out; practice counts for the streak. With an LLM configured, the server finds the points in your sentences in the background (it only confirms points whose words occur, and checks every match); without one, 30 common patterns are found by rule.
- **Explain grammar & practice texts** (servers with an LLM) — under any sentence's translation, "Explain grammar" breaks the sentence down, glosses it word by word and links the grammar points it uses. On a grammar point's page, "Practice text" writes a short text at your level that uses the point several times, built from words you know and checked before it opens in the reader.
- **Stroke order** — accordion in the word popover renders a hanzi-writer animation for each character.
- **Characters & measure word** — the word popover and review cards show the word's measure words (一本书, 一张桌子) and what each character is made of, with the parts' meanings and how it is built (好 = 女 woman + 子 son).
- **Make this text readable** — above every text: the share of its running words you know (every occurrence counts; words you ignore count as covered), the share once the words in review are learned, and how many missing words stand between you and 95 %, the point where a text reads without a dictionary. **Pre-learn missing words** lists them most frequent first; pick as many as you like and they go into review with their sentence from this text and, in a package or glossary text, the text's own meaning. The text remembers them, so you can add the rest another day, and **Review these words** runs a session on just that text.

## Importing

- **Paste** — the textarea handles arbitrarily long passages.
- **From URL** — server-side article extraction strips ads and chrome.
- **EPUB / PDF** — chunked by chapter; scanned PDFs are flagged.
- **Subtitles** — .srt, .vtt and .ass files of a series or film come in as one line per subtitle; only the Chinese lines are kept (bilingual subtitles lose their English half) and repeats are dropped. Saved into a folder, the episodes read in order.
- **Scan tab** — browser-side OCR via tesseract.js (chi_sim) for photos or screenshots.
- **Pre-analysed packages** — drop-in JSON produced upstream (e.g. by an LLM) to skip segmentation entirely. A bundled Dao De Jing chapter ships as the reference sample.

## Saved texts

- **Topic series** (servers with an LLM) — pick a topic, a level, how many new words each text should bring (5–50, default 10) and a length; a folder fills with texts written one after another for your words. Each text continues the ones before, uses the last text's new words again and brings new ones, each at least twice; every sentence comes with its translation. The server counts what is really new for you and writes a text again when it is far off. With many new words, pre-learn them before reading.

- **Folders** — keep saved texts in nested folders (a book, a course, a teacher). Texts without a folder stay at the top level; move a text or a folder anywhere, and deleting a folder keeps its texts. Each folder says how many of its texts are readable. Search looks through every folder.
- **Series** — inside a folder texts have an order you can change; each shows its number (2 / 6), and the reader leads from one to the next. A text saved from the reader goes into the folder you have open.

## Library

- **Graded texts** — 180 bundled texts across HSK 1–9, each with a short comprehension quiz. Passing the quiz or marking a text as read records your progress and counts for your streak, as does reading a saved text to the end.
- **For you** — texts where you already know most of the words (the 85–98 % band) are suggested on Discover and on the reader's Today panel.
- **Readable** — every library card, For-you pick and saved text shows whether it is readable for you yet or how many words are left; the library can sort by *almost readable*.

## Studying

- **Per-user word states** — each word is `new` / `learning` / `known` / `ignored`, tracked across all texts. Set from the word popover; Settings can make a click in the reader promote a new word to `learning` automatically (off by default).
- **Bulk shortcuts** — mark whole pages or whole HSK levels at once (the "I already know HSK 1–N" onboarding shortcut).
- **Personal glossaries** — any vocabulary list can be flagged as a glossary; its entries override CC-CEDICT/HSK lookups during analysis. Useful for specialised corpora (classical Chinese, technical jargon).
- **Learn a list** — *Learn this list* takes a vocabulary list into review; meanings you gave its words are kept next to the dictionary's, tagged with the list name. *Review this list* runs a session on just its words.
- **Public sharing** — mint a share token for any saved text; the public URL is read-only.
- **Anki & CSV export** — vocabulary lists export to Anki `.apkg` (with TTS audio baked in) or CSV. Whole-history exports for your learning + known words too.
- **Tone practice** — hear a word, pick its tones from choices that differ only in tone. Real minimal pairs come with their hanzi and can be played to compare (买 mǎi / 卖 mài). Uses your learning and known words, topped up with everyday ones; words whose spoken tones differ from the dictionary's (一, 不, two third tones) are left out. Practice only, nothing is graded.

## Spaced repetition

`/review` runs FSRS (the `fsrs` 6 library). The default mixed session:

- **Intro** — a new word with its pinyin, meaning, audio and stroke animation, then one traced pass. That pass is copying, so it never grades Easy: the word comes back about ten minutes later in the same session to be written from memory.
- **Read** — the hanzi alone; recall sound, tone and meaning (optionally type the pinyin), reveal, grade yourself.
- **Produce** — once a word is established, write it from pinyin and meaning.
- **Review focus** (Settings): *reading and writing* (default: read while a word is young, write once it is established), *reading* only, or *writing* only.
- **Context** — every card shows the sentence you met the word in (else one from your saved texts or the library), with its source and sentence audio.
- **Your own meanings** — meanings from packages (e.g. the Dao De Jing) and from your lists show on every card next to the dictionary's, each tagged with where it came from. A session focused on one text or list leads with that text's or list's meaning.

Single modes are available too:

- **Recognition** — see the character, recall meaning, grade Again / Hard / Good / Easy.
- **Dictation** — listen to the TTS, type the hanzi or the pinyin with tones (marks or numbers, e.g. `ma3`).
- **Writing** — draw each character on a 米字格 practice grid; hanzi-writer grades per-stroke accuracy.
- **Cloze** — fill in a blanked word in a real sentence from one of your saved texts.

Optional **daily auto-enrolment** seeds new HSK words into the learning pool at a configurable rate (default off; user picks 1–30 / day in Settings). Mastered words (stability ≥ 90 days) drop from "learning" colour to "known" colour automatically; a wrong answer pushes them back.

## Settings

- **Settings follow your account** — pinyin, colouring, HSK version, review modes and the writing options are stored on your account, so phone and browser show the same; theme, reminders and vibration stay per device.
- **Script** — auto / Simplified / Traditional. Applies to every Chinese surface (reader, saved texts, vocabulary lists, review cards). Internal data stays simp-canonical, conversion happens at the I/O boundary.
- **HSK version** — new (9-level) or old (6-level); affects colouring, bulk-mark shortcuts and which list daily auto-enrolment draws from.
- **Pinyin mode** — auto / on / off.
- **Word colouring** — by HSK level / by your progress / off.
- **Daily learning** — enable + target count.

## Accounts

- **Signup** — open registration with captcha and rate limits, or invitation-only; the admin panel switches between them. Each user can mint a limited number of invites (admin-configurable quota).
- **Admin panel** — at `/admin` for users with the flag set.
- **Daily streak** — counted from any of: word-state change, bulk mark, review grade. Visible as a flame badge in the nav. Earns a streak freeze every 7 days (capped at 2 banked) that automatically covers a missed day instead of resetting the count.
- **Weekly sparkline** — at the top of `/review`, stacked bars show reviews + words-marked over the last 7 days.
- **API tokens** — Settings → API tokens lets you mint a scoped, revocable personal access token (`read:words` / `write:words`) so another app of yours (e.g. a speaking-companion with its own whisper/LLM/TTS) can read your known/learning words and report newly-encountered ones back, without sharing your password.

## Stack

Backend: FastAPI, jieba, pypinyin, FSRS, SQLite.
Frontend: Vue 3, Vite, TypeScript, Pinia, Tailwind 4, hanzi-writer, tesseract.js.
Data: HSK 1–9 from [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary); CC-CEDICT from [mdbg.net](https://www.mdbg.net/chinese/dictionary?page=cc-cedict).

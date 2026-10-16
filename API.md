# API

QingDu's HTTP API is documented automatically at runtime — point your browser at the live instance for the complete, always-current reference:

- **Swagger UI**: `<base>/docs`
- **ReDoc**: `<base>/redoc`
- **OpenAPI JSON**: `<base>/openapi.json`

This page is a short tour of the surface; the schemas under `/docs` are the source of truth.

## Authentication

Most endpoints require a JWT. Obtain one from `POST /api/auth/login`, then send it on every subsequent call:

```
Authorization: Bearer <token>
```

Anonymous callers can still hit `GET /api/vocabulary-stats`, `GET /health`, `POST /api/analyze` (with reduced enrichment), and the public share endpoint `GET /api/share/{token}`.

## Endpoint groups

| Group | Prefix | Purpose |
|---|---|---|
| Authentication | `/api/auth/*` | Login, signup-with-invite, current-user, change-password, settings update |
| Analysis | `/api/analyze`, `/api/translate`, `/api/tts/*` | Segment a text, translate a sentence, synthesise speech |
| Saved texts | `/api/texts/*` | List, save, update, delete, share; move a text with `folder_id`; `POST /api/texts/order` sets a folder's reading order |
| Text folders | `/api/folders/*` | Nested folders for saved texts: list, create, rename, move, delete (texts move up one level) |
| Readability | `/api/readability`, `/api/readability/prelearn` | How much of a text the user can read and which words are missing; take missing words into review |
| Vocabulary lists | `/api/vocabulary-lists/*`, `/api/vocabulary-stats` | CRUD on user lists; take a list into review; Anki / CSV exports |
| Words | `/api/words/*` | Per-user word states (new / learning / known / ignored), bulk operations, stats, exports |
| Review | `/api/review/*` | FSRS queue + grading; recognition / dictation / writing / cloze modes; `text_key` / `list_id` focus a session on one text or list |
| Library | `/api/library/*` | Bundled graded texts, level-matched picks, how readable each is, reading progress, quizzes |
| Import | `/api/extract/file`, `/api/import/package/*` | EPUB / PDF / scan import; pre-analysed JSON package import |
| Convert | `/api/convert`, `/api/convert/detect` | Trad ⇄ Simp conversion, script detection |
| Stats | `/api/stats/weekly`, `/api/review/stats` | Activity sparkline + review queue counters |
| Admin | `/api/admin/users/*` | User management, invite quotas (admin only) |
| Invitations | `/api/invitations/*` | Mint + claim signup invitations |
| Health | `/health` | Liveness probe — also reports `vocab_count` + `cedict_count` |

## Rate limits

Applied per source IP via `slowapi`:

- `POST /api/auth/login` — 5 / minute
- `POST /api/analyze` — 30 / minute
- `POST /api/translate` — 20 / minute
- `GET /api/share/{token}` — 60 / minute

Everything else is unlimited at the application layer (reverse proxies in front may impose their own).

## Errors

All errors return JSON in FastAPI's default shape:

```json
{ "detail": "Human-readable description" }
```

Common status codes:

- `400` invalid input (empty text, bad enum value, etc.)
- `401` missing, expired or revoked token (a password change or admin reset signs out every
  existing session; `change-password` returns a fresh `access_token` for the caller)
- `403` authorised but not permitted (admin-only endpoint, or a wrong password on a
  re-check such as change-password / account deletion — the session stays valid)
- `404` resource not found
- `409` conflict (duplicate vocabulary list, invitation already claimed)
- `413` payload too large (audio uploads cap at 5 MB)
- `422` Pydantic validation failure
- `429` rate-limit exceeded
- `503` vocabulary not yet loaded (early in startup)

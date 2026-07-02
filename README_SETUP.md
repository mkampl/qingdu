# Setup Guide

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up -d --build
```

App is at <http://localhost:8000>.

On first boot a random admin password is written to `data/admin_bootstrap.txt` (mode 0600) and printed to the logs. You'll be forced to change it on first login.

## Production checklist

Generate a real `SECRET_KEY` before deploying:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the output into `SECRET_KEY=` in your `.env`. The app refuses to start if `SECRET_KEY` is missing.

## Local development (without Docker)

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

For the Vue frontend with hot-reload at `:5173`, run the dev compose layer instead:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Environment variables

### Required

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key. Generate with `secrets.token_urlsafe(32)`. |

### Optional

| Variable | Default | Purpose |
|---|---|---|
| `DEEPL_API_KEY` | — | DeepL translation. Highest-quality provider; falls back to Google / MyMemory when missing. |
| `GOOGLE_TRANSLATE_API_KEY` | — | Google Translate fallback. |
| `PORT` | `8000` | Server port. |
| `LOG_LEVEL` | `INFO` | Python logging level. |
| `ALLOWED_ORIGINS` | `*` | CORS allow-list, comma-separated. |
| `QINGDU_SKIP_CEDICT_LOAD` | `0` | Set to `1` to skip the ~4 MB CC-CEDICT download at startup (used by the test suite; not recommended in production — disables CC-CEDICT meaning overlay). |

## Troubleshooting

**`"SECRET_KEY must be set"` at startup.**  Missing `.env` or empty key. Run `./setup.sh` (generates one), or copy `.env.example` to `.env` and fill `SECRET_KEY=` with the output of `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Every installation needs its own key — a shared key lets anyone forge login tokens.

**Container won't start.**  `docker compose logs web` — most failures are a missing required env var.

**Port already in use.**  Set `PORT=8001` (or any free port) in `.env` and restart.

**Pronunciation check returns 500.**  Check that the container has `ffmpeg` available — the default image ships with it, but custom builds need it installed.

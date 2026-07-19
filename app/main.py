"""
Qingdu — application entry point.

Builds the FastAPI app, wires middleware, and includes the routers.
All endpoint logic lives in `app.routers.*`; business logic in
`app.services.*`; shared mutable state in `app.state`.
"""

import logging
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.core.paths import STATIC_DIR
from app.core.rate_limit import limiter
from app.database import init_db
from app.routers import (
    admin,
    analyze,
    anki,
    auth,
    convert,
    export,
    extract,
    health,
    invitations,
    legal,
    library,
    package,
    pronounce,
    review,
    spa,
    stats,
    texts,
    translate,
    tts,
    vocab,
    vocab_lists,
    words,
)
from app.services.cedict_loader import load_cedict
from app.services.hsk_loader import download_hsk_vocabulary
from app.state import hsk_vocab

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="轻读 QingDu - Chinese Text Analyzer",
    description="""
    A modern Chinese language learning tool that analyzes text difficulty based on HSK vocabulary levels.

    ## Features

    * **Text Analysis**: Analyze Chinese text and get HSK level information for each word
    * **Translation**: Multi-provider translation with DeepL, Google, and MyMemory
    * **Text Management**: Save and organize analyzed texts with tags
    * **Vocabulary Lists**: Create custom vocabulary lists and export to Anki
    * **User Management**: Multi-user support with role-based access

    ## Authentication

    Most endpoints require authentication using JWT tokens. Include the token in the
    `Authorization` header:
    ```
    Authorization: Bearer <your-token>
    ```

    Get a token by calling `/api/auth/login` with your credentials.
    """,
    version="1.0.0",
    contact={"name": "QingDu Support", "url": "https://github.com/mkampl/qingdu"},
    license_info={"name": "MIT"},
)

# CORS. The SPA and the API live on the same origin in production, so no
# cross-origin requests need to be allowed at all — empty ALLOWED_ORIGINS
# (the default) yields an empty allow-list. Operators who actually need
# CORS (Vite dev server, staging tooling) set ALLOWED_ORIGINS explicitly,
# either to '*' or a comma-separated whitelist.
_cors_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if _cors_env:
    allowed_origins = [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
    # '*' + allow_credentials=True makes Starlette reflect any Origin with
    # Access-Control-Allow-Credentials — "every site may make credentialed
    # calls". Auth here is a Bearer header (not cookies) so the practical
    # risk is low, but the pairing is never right: with a wildcard, drop
    # credentials support; with an explicit whitelist, keep it.
    _wildcard = "*" in allowed_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=not _wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Export-Stats",
            "X-Rate-Limited",
            "Content-Disposition",
        ],
    )


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Tag every request with a UUID for log correlation."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Rate limiting — limiter object lives in app.core.rate_limit so routers can import it.
app.state.limiter = limiter


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)


# Static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Routers — order matters: specific API routes first, SPA fallback last.
app.include_router(health.router)
app.include_router(legal.router)
app.include_router(analyze.router)
app.include_router(translate.router)
app.include_router(tts.router)
app.include_router(vocab.router)
app.include_router(texts.router)
app.include_router(auth.router)
app.include_router(invitations.router)
app.include_router(admin.router)
app.include_router(vocab_lists.router)
app.include_router(anki.router)
app.include_router(extract.router)
app.include_router(words.router)
app.include_router(review.router)
app.include_router(convert.router)
app.include_router(stats.router)
app.include_router(export.router)
app.include_router(package.router)
app.include_router(pronounce.router)
app.include_router(library.router)

# Vue 3 SPA at /. Includes a catch-all /{rest:path} route, so this MUST be
# the last router registered or it will swallow API paths. Also registers
# /v2 + /v2/{rest:path} -> 301 redirect for back-compat with the staging URLs.
# No-op if frontend/dist isn't built yet (e.g. CI).
spa.mount(app)


# Dev key that shipped in .env.example until 2026-07. It is in git history,
# so any instance still signing tokens with it is forgeable by anyone.
_BURNED_SECRET_KEYS = {"9ndRcryRqp0DbvQBThQmjTybD6nIyHbAHiYOyj44DsE"}


def _validate_environment() -> None:
    """Fail fast at startup if required env vars are missing."""
    required_vars = ["SECRET_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Please check your .env file or environment configuration."
        )
    if os.getenv("SECRET_KEY") in _BURNED_SECRET_KEYS:
        raise ValueError(
            "SECRET_KEY is the publicly-known development key that used to "
            "ship in .env.example - anyone can forge auth tokens against it. "
            "Generate a fresh one:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    logger.info("Environment validation passed")
    logger.info(f"LOG_LEVEL: {os.getenv('LOG_LEVEL', 'INFO')}")
    logger.info(f"PORT: {os.getenv('PORT', '8000')}")
    logger.info(f"ALLOWED_ORIGINS: {os.getenv('ALLOWED_ORIGINS', '*')}")
    logger.info(f"DEEPL_API_KEY configured: {bool(os.getenv('DEEPL_API_KEY'))}")
    logger.info(
        f"GOOGLE_TRANSLATE_API_KEY configured: {bool(os.getenv('GOOGLE_TRANSLATE_API_KEY'))}"
    )


@app.on_event("startup")
async def startup_event() -> None:
    """Load HSK vocabulary, init the DB, and warm up jieba."""
    import json

    import jieba

    from app import state as _state
    from app.core.constants import HSK_WORD_BASE_FREQ
    from app.core.paths import DATA_DIR

    _validate_environment()

    vocab_file = DATA_DIR / "hsk_vocabulary.json"

    logger.info("Downloading fresh HSK vocabulary from GitHub...")
    try:
        await download_hsk_vocabulary()
        logger.info(f"Successfully downloaded {len(hsk_vocab)} HSK words")
    except Exception as e:
        logger.error(f"Failed to download vocabulary from GitHub: {e}", exc_info=True)
        if vocab_file.exists():
            logger.warning("Falling back to cached vocabulary...")
            try:
                with open(vocab_file, encoding="utf-8") as f:
                    _state.hsk_vocab.clear()
                    _state.hsk_vocab.update(json.load(f))
                logger.info(f"Loaded {len(hsk_vocab)} HSK words from cache")
            except Exception as cache_error:
                logger.error(f"Failed to load from cache: {cache_error}", exc_info=True)
                logger.warning(
                    "Application will start without vocabulary - some features may not work"
                )
        else:
            logger.warning(
                "No cache available. Application will start without vocabulary - "
                "some features may not work"
            )

    # CC-CEDICT — overlay richer meanings onto hsk_vocab and populate
    # `cedict_vocab` for non-HSK lookups. Safe to no-op if the download
    # fails and no cache exists; the app keeps working on plain HSK data.
    logger.info("Loading CC-CEDICT...")
    try:
        await load_cedict()
    except Exception as e:
        logger.warning("CC-CEDICT load failed (%s); proceeding with HSK only", e)

    # Refresh per-user word snapshots so any pinyin/meaning improvements
    # from the dictionary load propagate to rows that were snapshotted
    # earlier with stale (or worse) glosses.
    from app.services.snapshot_backfill import run_at_startup as _refresh_snapshots

    _refresh_snapshots()

    logger.info("Initializing jieba tokenizer...")
    jieba.initialize()
    logger.info("Adding HSK words to jieba dictionary with high frequency...")
    added_to_jieba = 0
    for word, data in hsk_vocab.items():
        if len(word) > 1:
            base_freq = max(data.get("frequency", 0) * 100, HSK_WORD_BASE_FREQ)
            jieba.add_word(word, freq=base_freq)
            added_to_jieba += 1
    logger.info(f"Added {added_to_jieba} multi-character HSK words with priority to jieba")

    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")

    # Bootstrap default admin if no users exist.
    import secrets

    from app.auth import get_password_hash
    from app.core.paths import DATA_DIR
    from app.database import SessionLocal, User

    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            # Per-deploy random password. Written once to disk so the operator
            # can recover it after a fresh container start, and printed loudly
            # to the startup logs. Keeps a public deployment from shipping a
            # well-known default ('admin123').
            password = secrets.token_urlsafe(16)
            admin_user = User(
                username="admin",
                password_hash=get_password_hash(password),
                is_admin=True,
                must_change_password=True,
                invite_quota=-1,
            )
            db.add(admin_user)
            db.commit()

            try:
                bootstrap_file = DATA_DIR / "admin_bootstrap.txt"
                bootstrap_file.write_text(
                    f"username: admin\npassword: {password}\n",
                    encoding="utf-8",
                )
                bootstrap_file.chmod(0o600)
            except Exception:
                # Disk write is convenience, not correctness — logs always win.
                pass

            banner = "=" * 60
            logger.warning(banner)
            logger.warning("Initial admin user created — CHANGE PASSWORD ON FIRST LOGIN")
            logger.warning("  username: admin")
            logger.warning(f"  password: {password}")
            logger.warning("Also written to /app/data/admin_bootstrap.txt (mode 0600).")
            logger.warning(banner)
        else:
            logger.info(f"Found {user_count} existing user(s)")
    except Exception as e:
        logger.error(f"Error setting up users: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

    # Phase 2.7 — kick off the account-lifecycle sweep. Runs immediately
    # so a fresh container catches up on anyone who went dormant while it
    # was offline, then again every 6 h. Silently no-ops when both
    # soft_delete_days and hard_delete_days are 0 (the default).
    #
    # Skipped under pytest (conftest sets QINGDU_SKIP_SCHEDULER=1) — the
    # TestClient context manager triggers this startup, and an orphan
    # asyncio task that outlives the test session crashes CI on event-loop
    # teardown with "Task was destroyed but it is pending!" errors.
    if not os.getenv("QINGDU_SKIP_SCHEDULER"):
        import asyncio

        from app.services.lifecycle import run_lifecycle_pass

        LIFECYCLE_INTERVAL_S = 6 * 60 * 60

        async def _lifecycle_loop() -> None:
            try:
                run_lifecycle_pass()
            except Exception:
                logger.exception("initial lifecycle pass failed")
            while True:
                await asyncio.sleep(LIFECYCLE_INTERVAL_S)
                try:
                    run_lifecycle_pass()
                except Exception:
                    logger.exception("scheduled lifecycle pass failed")

        task = asyncio.create_task(_lifecycle_loop())
        app.state.lifecycle_task = task
        logger.info("Lifecycle scheduler started (interval=%ds)", LIFECYCLE_INTERVAL_S)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cancel background tasks cleanly. Without this the asyncio loop
    teardown logs `Task was destroyed but it is pending!` for our
    lifecycle scheduler, which CI sometimes promotes to a non-zero
    exit code."""
    import asyncio
    import contextlib

    task = getattr(app.state, "lifecycle_task", None)
    if task is None or task.done():
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

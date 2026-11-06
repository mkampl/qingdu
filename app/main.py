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

from app.core.constants import APP_VERSION
from app.core.paths import STATIC_DIR
from app.core.rate_limit import limiter
from app.database import init_db
from app.routers import (
    admin,
    analyze,
    anki,
    auth,
    capabilities,
    convert,
    export,
    external,
    extract,
    folders,
    grammar,
    health,
    invitations,
    legal,
    library,
    package,
    placement,
    readability,
    reading_help,
    review,
    series,
    spa,
    stats,
    texts,
    tokens,
    translate,
    tts,
    vocab,
    vocab_lists,
    words,
)
from app.services.cedict_loader import load_cedict
from app.services.hsk_loader import load_hsk_vocabulary
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
    Analyse Chinese text against HSK 1-9, learn its words with FSRS review,
    and read graded texts. The web app and the Android app use this API.

    Most endpoints need a JWT: call `/api/auth/login` and send the token as
    `Authorization: Bearer <token>`. The `/api/external/*` endpoints also take
    a personal access token (`qd_…`, issued under `/api/tokens`).
    """,
    version=APP_VERSION,
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
        expose_headers=["Content-Disposition"],
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
app.include_router(capabilities.router)
app.include_router(legal.router)
app.include_router(analyze.router)
app.include_router(translate.router)
app.include_router(tts.router)
app.include_router(vocab.router)
app.include_router(folders.router)
app.include_router(grammar.router)
app.include_router(placement.router)
app.include_router(series.router)
app.include_router(reading_help.router)
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
app.include_router(library.router)
app.include_router(tokens.router)
app.include_router(external.router)
app.include_router(readability.router)

# Vue 3 SPA at /. Includes a catch-all /{rest:path} route, so this MUST be
# the last router registered or it will swallow API paths. Also registers
# 301 redirects from the old /v2 paths.
# No-op if frontend/dist isn't built yet (e.g. CI).
spa.mount(app)


# Dev key that shipped in .env.example until 2026-07. It is in git history,
# so any instance still signing tokens with it is forgeable by anyone.
_BURNED_SECRET_KEYS = {"9ndRcryRqp0DbvQBThQmjTybD6nIyHbAHiYOyj44DsE"}


def _release_startup_memory() -> None:
    """Hand fragmented heap memory back to the OS after the startup loads
    (HSK vocab, CC-CEDICT, jieba dictionary). They briefly hold several
    copies of the vocabulary, and CPython does not return freed arenas on
    its own. glibc's malloc_trim does; a no-op where it is unavailable."""
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


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
    logger.info(f"ALLOWED_ORIGINS: {os.getenv('ALLOWED_ORIGINS') or '(none)'}")
    logger.info(f"DEEPL_API_KEY configured: {bool(os.getenv('DEEPL_API_KEY'))}")
    logger.info(
        f"GOOGLE_TRANSLATE_API_KEY configured: {bool(os.getenv('GOOGLE_TRANSLATE_API_KEY'))}"
    )


async def _load_dictionaries() -> None:
    """HSK vocabulary, then CC-CEDICT on top, then jieba. The app still
    starts when one of them fails, with fewer meanings."""
    from app.services.segmentation import prime_jieba

    logger.info("Loading pinned HSK vocabulary...")
    try:
        await load_hsk_vocabulary()
        logger.info(f"Loaded {len(hsk_vocab)} HSK words")
    except Exception as e:
        logger.error(f"Failed to load HSK vocabulary: {e}", exc_info=True)
        logger.warning("Application will start without vocabulary - some features may not work")

    logger.info("Loading CC-CEDICT...")
    try:
        await load_cedict()
    except Exception as e:
        logger.warning("CC-CEDICT load failed (%s); proceeding with HSK only", e)

    logger.info("Initializing jieba tokenizer...")
    added_to_jieba = prime_jieba()
    logger.info(f"Added {added_to_jieba} multi-character HSK words with priority to jieba")


def _start_background_tasks() -> None:
    """Start the periodic tasks; shutdown_event cancels them.

    Skipped under pytest (conftest sets QINGDU_SKIP_SCHEDULER=1): a task
    that outlives the TestClient breaks event-loop teardown."""
    if os.getenv("QINGDU_SKIP_SCHEDULER"):
        return
    import asyncio

    from app.services import grammar_book, grammar_tagging, lifecycle, llm

    app.state.lifecycle_task = asyncio.create_task(lifecycle.run_forever())
    logger.info("Lifecycle scheduler started (interval=%ds)", lifecycle.LIFECYCLE_INTERVAL_S)
    app.state.grammar_prewarm_task = asyncio.create_task(grammar_book.prewarm_in_background())
    if llm.config() is not None:
        app.state.llm_probe_task = asyncio.create_task(llm.probe_forever())
        app.state.grammar_tagging_task = asyncio.create_task(grammar_tagging.worker())


@app.on_event("startup")
async def startup_event() -> None:
    """Load the dictionaries, set up the DB, then start background tasks."""
    from app.services.admin_bootstrap import ensure_admin
    from app.services.snapshot_backfill import run_at_startup as refresh_snapshots

    _validate_environment()
    await _load_dictionaries()
    _release_startup_memory()
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")
    # Refresh user-word glosses when the dictionary version changed.
    refresh_snapshots()
    ensure_admin()
    _start_background_tasks()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cancel background tasks cleanly. Without this the asyncio loop
    teardown logs `Task was destroyed but it is pending!` for our
    lifecycle scheduler, which CI sometimes promotes to a non-zero
    exit code."""
    import asyncio
    import contextlib

    for name in (
        "lifecycle_task",
        "grammar_prewarm_task",
        "llm_probe_task",
        "grammar_tagging_task",
    ):
        task = getattr(app.state, name, None)
        if task is None or task.done():
            continue
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

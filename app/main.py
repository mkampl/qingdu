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
    health,
    invitations,
    pages,
    texts,
    translate,
    tts,
    vocab,
    vocab_lists,
)
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

# CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Export-Stats", "X-Rate-Limited", "Content-Disposition"],
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


# Routers
app.include_router(pages.router)
app.include_router(health.router)
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


def _validate_environment() -> None:
    """Fail fast at startup if required env vars are missing."""
    required_vars = ["SECRET_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Please check your .env file or environment configuration."
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
    from app.auth import get_password_hash
    from app.database import SessionLocal, User

    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            admin_user = User(
                username="admin",
                password_hash=get_password_hash("admin123"),
                is_admin=True,
                must_change_password=True,
                invite_quota=-1,
            )
            db.add(admin_user)
            db.commit()
            logger.warning("Initial admin user created: admin / admin123 (CHANGE PASSWORD!)")
        else:
            logger.info(f"Found {user_count} existing user(s)")
    except Exception as e:
        logger.error(f"Error setting up users: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

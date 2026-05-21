from fastapi import FastAPI, Request, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import jieba
import json
import os
from pathlib import Path
from pypinyin import lazy_pinyin, Style
import httpx
from functools import lru_cache
from typing import List, Tuple, Optional, Dict
import asyncio
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.database import init_db, get_db, SavedText, InvitationToken, User as UserModel
from sqlalchemy.orm import Session, joinedload
from fastapi import Depends
from functools import lru_cache
from app.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    require_auth,
    require_admin,
    require_auth_flexible
)
import uuid
from datetime import datetime, timedelta
from app.database import User, VocabularyList
from pydantic import BaseModel
import genanki
from gtts import gTTS
import tempfile
import shutil
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from cachetools import TTLCache
from uuid import uuid4
from app.core.constants import (
    ANALYZE_RATE_LIMIT,
    TRANSLATE_RATE_LIMIT,
    AUTH_RATE_LIMIT,
    TRANSLATION_CACHE_SIZE,
    TRANSLATION_CACHE_TTL,
    UNKNOWN_WORD_CACHE_SIZE,
    UNKNOWN_WORD_CACHE_TTL,
    HSK_WORD_BASE_FREQ,
    API_TIMEOUT,
    HSK_DOWNLOAD_TIMEOUT,
    MAX_RETRY_ATTEMPTS,
    RETRY_MIN_WAIT,
    RETRY_MAX_WAIT,
    HSK_RETRY_MIN_WAIT,
    HSK_RETRY_MAX_WAIT,
    TEXT_LEVEL_THRESHOLD,
    HSK_VOCAB_URL,
    TRANSLATION_SOURCE_DEEPL,
    TRANSLATION_SOURCE_GOOGLE,
    TRANSLATION_SOURCE_MYMEMORY,
    TRANSLATION_SOURCE_HSK,
    TRANSLATION_SOURCE_HSK_CHARS,
    TRANSLATION_SOURCE_CACHE,
)
from app.konfuzius_parser import parse_konfuzius_old_hsk

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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

    Most endpoints require authentication using JWT tokens. Include the token in the `Authorization` header:
    ```
    Authorization: Bearer <your-token>
    ```

    Get a token by calling `/api/auth/login` with your credentials.
    """,
    version="1.0.0",
    contact={
        "name": "QingDu Support",
        "url": "https://github.com/mkampl/qingdu",
    },
    license_info={
        "name": "MIT",
    },
)

# CORS Configuration
from fastapi.middleware.cors import CORSMiddleware
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Export-Stats", "X-Rate-Limited", "Content-Disposition"],
)

# Request ID Middleware for tracking requests
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """
    Add unique request ID to each request for debugging and tracking
    The request ID is:
    - Stored in request.state for access in endpoints
    - Added to response headers as X-Request-ID
    - Can be logged with each operation for tracing
    """
    request_id = str(uuid4())
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as e:
        logger.error(f"Request {request_id} failed: {e}", exc_info=True)
        raise

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Custom JSON rate limit handler
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."}
    )

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Filesystem paths live in app.core.paths (directories are created on import).
from app.core.paths import BACKUP_DIR, BASE_DIR, DATA_DIR, STATIC_DIR, TEMPLATES_DIR

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Shared mutable application state lives in app.state.
from app.state import hsk_vocab, hsk_lists_original, unknown_word_cache
from app import state as _state  # used to rebind dicts via clear/update

# Character/radical lookup tables live in app.core.radicals.
from app.core.radicals import CHAR_TO_RADICAL, RADICAL_PINYIN


# Pydantic request/response schemas live in app.schemas now.
from app.schemas import (
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    SignupWithInviteRequest,
    TextAnalysisRequest,
    TranslationRequest,
    UpdateInviteQuotaRequest,
    WordInfo,
)
# Translation provider chain lives in app.services.translation.
from app.services.translation import (
    _call_translation_api,
    get_translation_with_source,
    translation_cache,
)

# unknown_word_cache lives in app.state and is re-imported at the top.

def validate_environment():
    """
    Validate required environment variables at startup
    Raises ValueError if any required variables are missing
    """
    required_vars = ["SECRET_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Please check your .env file or environment configuration."
        )

    # Log configuration (without sensitive data)
    logger.info("Environment validation passed")
    logger.info(f"LOG_LEVEL: {os.getenv('LOG_LEVEL', 'INFO')}")
    logger.info(f"PORT: {os.getenv('PORT', '8000')}")
    logger.info(f"ALLOWED_ORIGINS: {os.getenv('ALLOWED_ORIGINS', '*')}")
    logger.info(f"DEEPL_API_KEY configured: {bool(os.getenv('DEEPL_API_KEY'))}")
    logger.info(f"GOOGLE_TRANSLATE_API_KEY configured: {bool(os.getenv('GOOGLE_TRANSLATE_API_KEY'))}")

@app.on_event("startup")
async def startup_event():
    """Load HSK vocabulary on startup"""
    # Validate environment first
    validate_environment()

    vocab_file = DATA_DIR / "hsk_vocabulary.json"

    # Always try to download fresh vocabulary from GitHub on startup
    logger.info("Downloading fresh HSK vocabulary from GitHub...")
    try:
        await download_hsk_vocabulary()
        logger.info(f"Successfully downloaded {len(hsk_vocab)} HSK words")
    except Exception as e:
        logger.error(f"Failed to download vocabulary from GitHub: {e}", exc_info=True)

        # Fall back to cache if download fails
        if vocab_file.exists():
            logger.warning("Falling back to cached vocabulary...")
            try:
                with open(vocab_file, 'r', encoding='utf-8') as f:
                    # Mutate the shared state dict in place — rebinding would
                    # disconnect us from importers (services, routers).
                    _state.hsk_vocab.clear()
                    _state.hsk_vocab.update(json.load(f))
                logger.info(f"Loaded {len(hsk_vocab)} HSK words from cache")
            except Exception as cache_error:
                logger.error(f"Failed to load from cache: {cache_error}", exc_info=True)
                logger.warning("Application will start without vocabulary - some features may not work")
        else:
            logger.warning("No cache available. Application will start without vocabulary - some features may not work")

    logger.info("Initializing jieba tokenizer...")
    jieba.initialize()

    logger.info("Adding HSK words to jieba dictionary with high frequency...")
    multi_char_count = 0
    
    # Common multi-character words that must be recognized as units
    # priority_words = ['第一', '第二', '第三', '很多', '一个', '这个', '那个', '什么', 
    #                   '怎么', '为什么', '可以', '喝茶', '吃饭', '第一天', '每天',
    #                   '今天', '明天', '昨天', '去年', '今年', '明年', '一位', '一种',
    #                   '成都', '茶馆', '打麻将', '武侯祠', '三国', '诸葛亮', '道家',
    #                   '麻婆豆腐', '担担面', '当地人', '四川菜', '阴阳', '老先生', '这次']
    
    for word, data in hsk_vocab.items():
        if len(word) > 1:
            # Add with high frequency to prioritize HSK words in segmentation
            # Give extra priority to common multi-char words
            base_freq = max(data.get('frequency', 0) * 100, HSK_WORD_BASE_FREQ)
            # if word in priority_words:
            #     freq = base_freq * 10  # 10x priority for common words
            # else:
            freq = base_freq
            jieba.add_word(word, freq=freq)
            multi_char_count += 1
    
    logger.info(f"Added {multi_char_count} multi-character HSK words with priority to jieba")

    # Initialize database
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")

    # Create initial admin user if no users exist
    from app.database import SessionLocal
    db = SessionLocal()
    
    try:
        user_count = db.query(User).count()
        
        if user_count == 0:
            admin = User(
                username="admin",
                password_hash=get_password_hash("admin123"),
                is_admin=True,
                must_change_password=True,
                invite_quota=-1  # Unlimited invites for admin
            )
            db.add(admin)
            db.commit()
            logger.warning("Initial admin user created: admin / admin123 (CHANGE PASSWORD!)")
        else:
            logger.info(f"Found {user_count} existing user(s)")

    except Exception as e:
        logger.error(f"Error setting up users: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

    logger.info("Startup complete")

from app.services.hsk_loader import cleanup_old_backups, download_hsk_vocabulary  # noqa: E402

@app.get("/")
async def home(request: Request):
    """Serve main page"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "vocab_count": len(hsk_vocab)
    })

from app.services.word_lookup import create_compound_from_hsk, lookup_unknown_word  # noqa: E402,F401


@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True
)
@app.post("/api/analyze",
    summary="Analyze Chinese text",
    description="Analyzes Chinese text and returns HSK level information for each word, including pinyin, meaning, and statistics.",
    response_description="Analysis results with word-by-word breakdown and statistics",
    responses={
        200: {
            "description": "Successful analysis",
            "content": {
                "application/json": {
                    "example": {
                        "words": [
                            {
                                "text": "你好",
                                "hsk_level": "new-1",
                                "pinyin": "nǐ hǎo",
                                "meaning": "hello",
                                "is_hsk": True,
                                "translation_source": "hsk"
                            }
                        ],
                        "statistics": {
                            "total_characters": 2,
                            "total_words": 1,
                            "hsk_words": 1,
                            "hsk_distribution": {"hsk1": 1},
                            "estimated_level": "HSK 1"
                        }
                    }
                }
            }
        },
        503: {"description": "Vocabulary not loaded yet"},
        400: {"description": "Empty text provided"},
        429: {"description": "Rate limit exceeded (30 requests/minute)"}
    },
    tags=["Analysis"]
)
@limiter.limit(ANALYZE_RATE_LIMIT)
async def analyze_text(request: Request, data: TextAnalysisRequest) -> Dict:
    """Analyze Chinese text and return HSK information"""
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")

    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")

    return await analyze_chinese_text(text)


from app.services.segmentation import analyze_chinese_text  # noqa: E402

from app.services.levels import estimate_text_level  # noqa: E402,F401


from app.services.migrations import (
    migrate_analysis_data,
    migrate_vocabulary_sections,
    migrate_word_data,
)  # noqa: E402
@app.get("/api/vocabulary-stats")
async def vocabulary_stats():
    """Get vocabulary statistics"""
    if not hsk_vocab:
        return {"loaded": False, "count": 0}
    
    level_counts = {}
    for word_data in hsk_vocab.values():
        level = word_data['level']
        level_counts[level] = level_counts.get(level, 0) + 1
    
    return {
        "loaded": True,
        "count": len(hsk_vocab),
        "by_level": level_counts
    }

@app.get("/api/get-hsk-vocabulary")
async def get_hsk_vocabulary():
    """Get complete HSK vocabulary for text analysis (includes supplementation)"""
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")

    return hsk_vocab

@app.get("/api/get-hsk-lists-original")
async def get_hsk_lists_original():
    """Get original HSK vocabulary for list generation (no supplementation)"""
    if not hsk_lists_original:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")

    return hsk_lists_original

@app.get("/api/debug/vocab-sample")
async def debug_vocab_sample():
    """Debug endpoint: Show sample vocabulary entries to verify level_old is populated"""
    if not hsk_vocab:
        return {"error": "Vocabulary not loaded"}

    # Get first 20 words as sample
    sample = {}
    count_with_both = 0
    count_new_only = 0
    count_old_only = 0

    for i, (word, data) in enumerate(hsk_vocab.items()):
        if i < 20:
            sample[word] = {
                'level': data.get('level'),
                'level_new': data.get('level_new'),
                'level_old': data.get('level_old'),
                'pinyin': data.get('pinyin'),
                'meaning': data.get('meaning')
            }

        # Count level distribution
        has_new = data.get('level_new') is not None
        has_old = data.get('level_old') is not None

        if has_new and has_old:
            count_with_both += 1
        elif has_new:
            count_new_only += 1
        elif has_old:
            count_old_only += 1

    return {
        "sample": sample,
        "statistics": {
            "total_words": len(hsk_vocab),
            "with_both_levels": count_with_both,
            "new_hsk_only": count_new_only,
            "old_hsk_only": count_old_only
        }
    }

@app.get("/api/debug/vocab-lookup/{word}")
async def debug_vocab_lookup(word: str):
    """Debug endpoint: Look up a specific word in the vocabulary"""
    if not hsk_vocab:
        return {"error": "Vocabulary not loaded"}

    if word in hsk_vocab:
        return {
            "found": True,
            "word": word,
            "data": hsk_vocab[word]
        }
    else:
        # Check if individual characters exist
        char_data = {}
        for char in word:
            if char in hsk_vocab:
                char_data[char] = hsk_vocab[char]

        return {
            "found": False,
            "word": word,
            "message": "Word not in vocabulary",
            "characters": char_data if char_data else "No character data found"
        }

@app.get("/health",
    summary="Health check",
    description="Check if the application is running and vocabulary is loaded",
    response_description="Health status",
    tags=["System"]
)
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "vocab_loaded": len(hsk_vocab) > 0,
        "vocab_count": len(hsk_vocab)
    }

from app.services.tts import fetch_chinese_tts  # noqa: E402


@app.get("/api/tts/{text}")
async def text_to_speech(text: str):
    """Text-to-speech proxy for Google Translate TTS"""
    try:
        audio = await fetch_chinese_tts(text)
        from fastapi.responses import Response
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")

@lru_cache(maxsize=1000)
def cached_translation(text: str, target_lang: str) -> Optional[str]:
    """Cache translations to reduce API calls"""
    return None

@app.post("/api/translate")
@limiter.limit(TRANSLATE_RATE_LIMIT)
async def translate_text(request: Request, data: TranslationRequest) -> Dict:
    """Translate Chinese text to target language"""
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")
    
    cache_key = f"{text}_{data.target_lang}"
    if cache_key in translation_cache:
        cached_result = translation_cache[cache_key]
        # Handle both old (string) and new (dict) cache format
        if isinstance(cached_result, str):
            return {
                "translation": cached_result,
                "source": TRANSLATION_SOURCE_CACHE,
                "cached": True
            }
        else:
            return {
                "translation": cached_result.get('translation', cached_result),
                "source": cached_result.get('source', TRANSLATION_SOURCE_CACHE),
                "cached": True
            }
    
    # Try translation with source tracking
    translation_result = await get_translation_with_source(text)
    
    if translation_result:
        translation_cache[cache_key] = translation_result
        return {
            "translation": translation_result['translation'],
            "source": translation_result['source'],
            "cached": False
        }
    else:
        raise HTTPException(status_code=500, detail="All translation services failed")

@app.post("/api/texts/save")
async def save_text(
    request: Request,
    text_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Save analyzed text to database"""
    tags = text_data.get('tags', [])
    
    saved_text = SavedText(
        user_id=user.id,
        title=text_data.get('title'),
        content=text_data.get('content'),
        analysis_data=json.dumps(text_data.get('analysis_data')),
        tags=json.dumps(tags) if tags else None  # NEW: Save tags
    )
    db.add(saved_text)
    db.commit()
    db.refresh(saved_text)
    return {"id": saved_text.id, "message": "Text saved"}

@app.get("/api/texts")
async def get_texts(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get all saved texts for current user with optimized query"""
    # Use eager loading to avoid N+1 query problem
    texts = db.query(SavedText)\
        .options(joinedload(SavedText.user))\
        .filter(SavedText.user_id == user.id)\
        .order_by(SavedText.created_at.desc())\
        .all()
    
    result = []
    for text in texts:
        analysis_data = json.loads(text.analysis_data)
        # Automatically migrate old format data to new dual HSK system
        migrated_data = migrate_analysis_data(analysis_data)

        result.append({
            "id": text.id,
            "title": text.title,
            "content": text.content,
            "date": text.created_at.isoformat(),
            "analysisData": migrated_data,
            "tags": text.tags,
            "reading_progress": text.reading_progress or 0
        })

    return result

@app.delete("/api/texts/{text_id}")
async def delete_text(
    text_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete a saved text"""
    text = db.query(SavedText).filter(
        SavedText.id == text_id,
        SavedText.user_id == user.id  # <- NEU: nur eigene Texte
    ).first()
    
    if text:
        db.delete(text)
        db.commit()
        return {"message": "Text deleted"}
    return {"error": "Text not found"}

@app.patch("/api/texts/{text_id}")
async def update_text(
    text_id: int,
    data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update text (title, tags, reading_progress)"""
    text = db.query(SavedText).filter(
        SavedText.id == text_id,
        SavedText.user_id == user.id
    ).first()
    
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    
    # Update fields if provided
    if 'title' in data:
        text.title = data['title']

    if 'tags' in data:
        text.tags = json.dumps(data['tags']) if data['tags'] else None

    if 'reading_progress' in data:
        text.reading_progress = data['reading_progress']

    if 'content' in data:
        text.content = data['content']

    if 'analysis_data' in data:
        text.analysis_data = json.dumps(data['analysis_data'])

    db.commit()
    db.refresh(text)
    
    return {
        "id": text.id,
        "title": text.title,
        "message": "Text updated"
    }

@lru_cache(maxsize=10000)
def get_word_info(word: str) -> Optional[Dict]:
    """Cached word lookup for better performance"""
    return hsk_vocab.get(word)

# ==================== AUTH ENDPOINTS ====================

@app.post("/api/auth/login",
    summary="User login",
    description="Authenticate user and receive JWT access token. Default credentials: admin/admin123 (must be changed on first login).",
    response_description="JWT token and user information",
    responses={
        200: {
            "description": "Successful login",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                        "user": {
                            "username": "admin",
                            "is_admin": True,
                            "must_change_password": False
                        }
                    }
                }
            }
        },
        401: {"description": "Invalid username or password"},
        429: {"description": "Rate limit exceeded (5 requests/minute)"}
    },
    tags=["Authentication"]
)
@limiter.limit(AUTH_RATE_LIMIT)  # Prevent brute force attacks
async def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    """Login endpoint"""
    user = db.query(User).filter(User.username == data.username).first()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": user.username,
            "is_admin": user.is_admin,
            "must_change_password": user.must_change_password
        }
    }

@app.get("/api/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    """Get current user info"""
    if not user:
        return {"authenticated": False}
    
    return {
        "authenticated": True,
        "user": {
            "username": user.username,
            "is_admin": user.is_admin,
            "must_change_password": user.must_change_password
        }
    }

@app.post("/api/auth/logout")
async def logout():
    """Logout (client-side token removal)"""
    return {"message": "Logged out successfully"}

@app.post("/api/auth/change-password")
async def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Change password"""
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid old password"
        )
    
    # Validate new password
    from app.core.constants import MIN_PASSWORD_LENGTH
    if len(data.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    
    user.password_hash = get_password_hash(data.new_password)
    user.must_change_password = False
    db.commit()

    return {"message": "Password changed successfully"}

# ==================== INVITATION ENDPOINTS ====================

@app.post("/api/invitations/generate")
async def generate_invitation(
    request: Request,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Generate a new invitation token"""
    # Check remaining quota (skip check if quota is -1 = unlimited)
    used_count = db.query(InvitationToken).filter(
        InvitationToken.created_by_user_id == user.id
    ).count()

    if user.invite_quota >= 0 and used_count >= user.invite_quota:
        raise HTTPException(
            status_code=403,
            detail=f"Invitation quota exceeded. You have used {used_count}/{user.invite_quota} invitations."
        )

    # Generate token
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=30)

    invitation = InvitationToken(
        token=token,
        created_by_user_id=user.id,
        expires_at=expires_at
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    # Get base URL from request
    base_url = str(request.url).split('/api')[0] if hasattr(request, 'url') else 'http://localhost:8000'
    invite_url = f"{base_url}/?invite={token}"

    return {
        "id": invitation.id,
        "token": token,
        "invite_url": invite_url,
        "expires_at": invitation.expires_at.isoformat(),
        "remaining_quota": -1 if user.invite_quota == -1 else user.invite_quota - used_count - 1
    }

@app.get("/api/invitations/my-invitations")
async def get_my_invitations(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get all invitations created by the current user"""
    invitations = db.query(InvitationToken).filter(
        InvitationToken.created_by_user_id == user.id
    ).order_by(InvitationToken.created_at.desc()).all()

    used_count = len(invitations)

    return {
        "invitations": [{
            "id": inv.id,
            "token": inv.token[-8:],  # Show last 8 chars
            "full_token": inv.token,
            "status": "claimed" if inv.claimed_at else ("expired" if inv.expires_at < datetime.utcnow() else "pending"),
            "claimed_by": db.query(User).filter(User.id == inv.claimed_by_user_id).first().username if inv.claimed_by_user_id else None,
            "claimed_at": inv.claimed_at.isoformat() if inv.claimed_at else None,
            "expires_at": inv.expires_at.isoformat(),
            "created_at": inv.created_at.isoformat()
        } for inv in invitations],
        "quota": {
            "total": user.invite_quota,
            "used": used_count,
            "remaining": -1 if user.invite_quota == -1 else user.invite_quota - used_count
        }
    }

@app.get("/api/invitations/validate/{token}")
async def validate_invitation(
    token: str,
    db: Session = Depends(get_db)
):
    """Validate an invitation token (public endpoint)"""
    invitation = db.query(InvitationToken).filter(
        InvitationToken.token == token
    ).first()

    if not invitation:
        return {"valid": False, "reason": "not_found"}

    if invitation.claimed_at:
        return {"valid": False, "reason": "already_used"}

    if invitation.expires_at < datetime.utcnow():
        return {"valid": False, "reason": "expired"}

    creator = db.query(User).filter(User.id == invitation.created_by_user_id).first()

    return {
        "valid": True,
        "invited_by": creator.username if creator else "Unknown",
        "expires_at": invitation.expires_at.isoformat()
    }

# Signup with invitation
@app.post("/api/auth/signup-with-invite")
async def signup_with_invite(
    data: SignupWithInviteRequest,
    db: Session = Depends(get_db)
):
    """Register a new user with an invitation token"""
    # Validate token
    invitation = db.query(InvitationToken).filter(
        InvitationToken.token == data.token
    ).first()

    if not invitation:
        raise HTTPException(status_code=400, detail="Invalid invitation token")

    if invitation.claimed_at:
        raise HTTPException(status_code=400, detail="Invitation already used")

    if invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invitation expired")

    # Check if username exists
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    # Validate password
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Create user
    new_user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        must_change_password=False,  # No need to change password on first login
        invite_quota=5  # Default quota for new users
    )

    db.add(new_user)
    db.flush()  # Get the user ID

    # Mark invitation as claimed
    invitation.claimed_by_user_id = new_user.id
    invitation.claimed_at = datetime.utcnow()

    db.commit()

    # Create access token
    token = create_access_token(data={"sub": new_user.username})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "is_admin": new_user.is_admin
        }
    }

# ==================== ADMIN ENDPOINTS ====================

@app.get("/api/admin/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all users (admin only)"""
    users = db.query(User).all()
    return [{
        "id": u.id,
        "username": u.username,
        "is_admin": u.is_admin,
        "invite_quota": u.invite_quota,
        "last_active": u.last_active.isoformat(),
        "created_at": u.created_at.isoformat()
    } for u in users]

@app.post("/api/admin/users")
async def create_user(
    data: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create new user (admin only)"""
    # Check if username exists
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Create user
    user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        is_admin=False,
        must_change_password=True
    )
    db.add(user)
    db.commit()
    
    return {"message": f"User {data.username} created successfully"}

@app.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete admin users"
        )
    
    db.delete(user)
    db.commit()
    
    return {"message": f"User {user.username} deleted"}

@app.post("/api/admin/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    data: dict,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reset user password (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    from app.core.constants import MIN_PASSWORD_LENGTH
    new_password = data.get("new_password")
    if not new_password or len(new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    
    user.password_hash = get_password_hash(new_password)
    user.must_change_password = True
    db.commit()
    
    return {"message": f"Password reset for {user.username}"}

@app.post("/api/vocabulary-lists")
async def create_vocabulary_list(
    list_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create vocabulary list"""
    import random
    
    # Generate unique Anki deck ID
    anki_deck_id = 2000000 + random.randint(1, 999999)
    
    vocab_list = VocabularyList(
        user_id=user.id,
        name=list_data.get('name'),
        list_type=list_data.get('type', 'custom'),
        sections=json.dumps(list_data.get('sections', [])),
        anki_deck_id=anki_deck_id
    )
    db.add(vocab_list)
    db.commit()
    return {"id": vocab_list.id, "message": "List created"}

@app.get("/api/vocabulary-lists")
async def get_vocabulary_lists(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get all vocabulary lists for current user"""
    lists = db.query(VocabularyList).filter(
        VocabularyList.user_id == user.id
    ).all()

    result = []
    for l in lists:
        sections = json.loads(l.sections) if l.sections else []
        # Automatically migrate old format data to new dual HSK system
        migrated_sections = migrate_vocabulary_sections(sections)

        result.append({
            "id": l.id,
            "name": l.name,
            "type": l.list_type,
            "sections": migrated_sections
        })

    return result

@app.put("/api/vocabulary-lists/{list_id}")
async def update_vocabulary_list(
    list_id: int,
    list_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update vocabulary list"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()
    
    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")
    
    vocab_list.name = list_data.get('name', vocab_list.name)
    vocab_list.sections = json.dumps(list_data.get('sections', []))
    db.commit()
    
    return {"message": "List updated"}

@app.delete("/api/vocabulary-lists/{list_id}")
async def delete_vocabulary_list(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete vocabulary list"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()
    
    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")
    
    db.delete(vocab_list)
    db.commit()
    
    return {"message": "List deleted"}

@app.post("/api/vocabulary-lists/{list_id}/words")
async def add_word_to_list(
    list_id: int,
    word_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Add word to vocabulary list section"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    section_name = word_data.get('section_name')

    # Find or create section
    section = next((s for s in sections if s['name'] == section_name), None)
    if not section:
        section = {'name': section_name, 'words': []}
        sections.append(section)

    # Auto-generate pinyin from hanzi
    hanzi = word_data.get('hanzi')
    pinyin = ' '.join(lazy_pinyin(hanzi, style=Style.TONE))

    # Create word with auto-generated pinyin and 'Custom' level
    word = {
        'hanzi': hanzi,
        'pinyin': pinyin,
        'meaning': word_data.get('meaning'),
        'level': 'Custom'
    }

    if any(w['hanzi'] == word['hanzi'] for w in section['words']):
        return {"message": "Word already in list"}

    section['words'].append(word)
    vocab_list.sections = json.dumps(sections)
    db.commit()

    return {"message": "Word added", "pinyin": pinyin}

@app.post("/api/vocabulary-lists/{list_id}/sections")
async def add_section_to_list(
    list_id: int,
    section_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Add new section to vocabulary list"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    logger.info(f"Before adding: list {list_id} has {len(sections)} sections: {[s['name'] for s in sections]}")

    section_name = section_data.get('name', '').strip()

    if not section_name:
        raise HTTPException(status_code=400, detail="Section name required")

    # Check if section already exists
    if any(s['name'] == section_name for s in sections):
        raise HTTPException(status_code=400, detail="Section already exists")

    sections.append({'name': section_name, 'words': []})
    vocab_list.sections = json.dumps(sections)
    db.commit()
    db.refresh(vocab_list)

    # Verify the section was saved
    updated_sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    logger.info(f"After commit: list {list_id} has {len(updated_sections)} sections: {[s['name'] for s in updated_sections]}")

    return {"message": "Section added", "name": section_name, "total_sections": len(updated_sections)}

@app.put("/api/vocabulary-lists/{list_id}/sections")
async def rename_section(
    list_id: int,
    section_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Rename section in vocabulary list"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    old_name = section_data.get('old_name')
    new_name = section_data.get('new_name', '').strip()

    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="Both old_name and new_name required")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    section = next((s for s in sections if s['name'] == old_name), None)

    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Check if new name already exists
    if any(s['name'] == new_name for s in sections if s['name'] != old_name):
        raise HTTPException(status_code=400, detail="Section name already exists")

    section['name'] = new_name
    vocab_list.sections = json.dumps(sections)
    db.commit()

    return {"message": "Section renamed"}

@app.delete("/api/vocabulary-lists/{list_id}/sections/{section_name}")
async def delete_section(
    list_id: int,
    section_name: str,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete section from vocabulary list"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    section = next((s for s in sections if s['name'] == section_name), None)

    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    sections = [s for s in sections if s['name'] != section_name]
    vocab_list.sections = json.dumps(sections)
    db.commit()

    return {"message": "Section deleted", "word_count": len(section.get('words', []))}

@app.put("/api/vocabulary-lists/{list_id}/words")
async def update_word_in_list(
    list_id: int,
    word_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update word in vocabulary list"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    section_name = word_data.get('section_name')
    old_hanzi = word_data.get('old_hanzi')
    new_word = word_data.get('word')  # {hanzi, pinyin, meaning, level}

    if not section_name or not old_hanzi or not new_word:
        raise HTTPException(status_code=400, detail="section_name, old_hanzi, and word required")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    section = next((s for s in sections if s['name'] == section_name), None)

    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    word = next((w for w in section['words'] if w['hanzi'] == old_hanzi), None)

    if not word:
        raise HTTPException(status_code=404, detail="Word not found")

    # Update word - auto-generate pinyin from new hanzi
    new_hanzi = new_word.get('hanzi', word['hanzi'])
    word['hanzi'] = new_hanzi
    word['pinyin'] = ' '.join(lazy_pinyin(new_hanzi, style=Style.TONE))  # Auto-generate
    word['meaning'] = new_word.get('meaning', word['meaning'])
    word['level'] = 'Custom'  # Always set to Custom

    vocab_list.sections = json.dumps(sections)
    db.commit()

    return {"message": "Word updated", "pinyin": word['pinyin']}

@app.delete("/api/vocabulary-lists/{list_id}/words")
async def delete_word_from_list(
    list_id: int,
    word_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete word from vocabulary list"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    section_name = word_data.get('section_name')
    hanzi = word_data.get('hanzi')

    if not section_name or not hanzi:
        raise HTTPException(status_code=400, detail="section_name and hanzi required")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    section = next((s for s in sections if s['name'] == section_name), None)

    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    original_count = len(section['words'])
    section['words'] = [w for w in section['words'] if w['hanzi'] != hanzi]

    if len(section['words']) == original_count:
        raise HTTPException(status_code=404, detail="Word not found")

    vocab_list.sections = json.dumps(sections)
    db.commit()

    return {"message": "Word deleted"}

@app.get("/api/vocabulary-lists/{list_id}/check-audio")
async def check_audio_status(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Check audio cache status for vocabulary list (fast, no generation)"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []

    # Create cache directory
    audio_cache_dir = DATA_DIR / "audio_cache"
    audio_cache_dir.mkdir(exist_ok=True)

    # Count total words and check cache status
    total_words = 0
    cached_count = 0
    missing_words = []

    for section in sections:
        words = section.get('words', [])
        for word_data in words:
            hanzi = word_data.get('hanzi', '')
            if not hanzi:
                continue

            total_words += 1
            unicode_ids = "_".join(str(ord(char)) for char in hanzi)
            cache_filename = f"{unicode_ids}_zh.mp3"
            cache_path = audio_cache_dir / cache_filename

            if cache_path.exists() and cache_path.stat().st_size > 0:
                cached_count += 1
            else:
                missing_words.append(hanzi)

    missing_count = len(missing_words)
    estimated_seconds = missing_count * 0.5  # Rough estimate: 0.5s per word

    return {
        "total": total_words,
        "cached": cached_count,
        "missing": missing_count,
        "estimated_time": f"~{int(estimated_seconds)}s" if missing_count > 0 else "0s",
        "ready": missing_count == 0
    }

@app.post("/api/vocabulary-lists/{list_id}/prepare-export")
async def prepare_export_audio(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Generate missing audio files before export"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []

    # Create cache directory
    audio_cache_dir = DATA_DIR / "audio_cache"
    audio_cache_dir.mkdir(exist_ok=True)

    # Generate missing audio files
    total_words = 0
    generated_count = 0
    failed_count = 0
    consecutive_failures = 0
    rate_limited = False

    for section in sections:
        words = section.get('words', [])
        for word_data in words:
            hanzi = word_data.get('hanzi', '')
            if not hanzi:
                continue

            total_words += 1
            unicode_ids = "_".join(str(ord(char)) for char in hanzi)
            cache_filename = f"{unicode_ids}_zh.mp3"
            cache_path = audio_cache_dir / cache_filename

            # Skip if already cached
            if cache_path.exists() and cache_path.stat().st_size > 0:
                continue

            # Stop if rate limited
            if consecutive_failures >= 5:
                rate_limited = True
                failed_count += 1
                continue

            # Try to generate audio
            try:
                tts = gTTS(hanzi, lang='zh')
                tts.save(str(cache_path))
                generated_count += 1
                consecutive_failures = 0
                logger.info(f"Generated audio for: {hanzi}")
            except Exception as e:
                failed_count += 1
                consecutive_failures += 1
                logger.warning(f"Failed to generate audio for {hanzi}: {e}")

                if consecutive_failures >= 5:
                    rate_limited = True
                    logger.error("Rate limit reached during audio preparation")

    cached_count = total_words - generated_count - failed_count

    return {
        "total": total_words,
        "cached": cached_count,
        "generated": generated_count,
        "failed": failed_count,
        "rate_limited": rate_limited,
        "ready": failed_count == 0
    }

@app.get("/api/vocabulary-lists/{list_id}/export-anki")
async def export_vocabulary_list_anki(
    list_id: int,
    user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db)
):
    """Export vocabulary list as Anki .apkg file with stroke animations and subdecks"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()

    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")

    sections = json.loads(vocab_list.sections) if vocab_list.sections else []

    # Create cache directory for audio files
    audio_cache_dir = DATA_DIR / "audio_cache"
    audio_cache_dir.mkdir(exist_ok=True)
    
    # Create temporary directory for package assembly
    temp_dir = tempfile.mkdtemp(prefix='qingdu_anki_')
    media_files = []
    
    # Track statistics
    total_words = sum(len(s.get('words', [])) for s in sections)
    words_processed = 0
    audio_generated = 0
    audio_cached = 0
    audio_failed = 0
    failed_words = []
    rate_limited = False
    consecutive_failures = 0
    
    try:
        # Load template from file
        template_path = DATA_DIR / "hanzi_template.json"
        if not template_path.exists():
            raise HTTPException(status_code=500, detail="Template file not found")
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template_data = json.load(f)
        
        # Replace template placeholders
        qfmt = template_data['qfmt'].replace('__HANZI_WRITER_VERSION__', '2.2')
        qfmt = qfmt.replace('__CHARACTER_WIDTH__', '250').replace('__CHARACTER_HEIGHT__', '250')
        
        afmt = template_data['afmt'].replace('__HANZI_WRITER_VERSION__', '2.2')
        afmt = afmt.replace('__STROKE_ANIMATION_SPEED__', '1')
        afmt = afmt.replace('__DELAY_BETWEEN_STROKES__', '150')
        
        # Create Anki model
        model = genanki.Model(
            1607392319,
            'Hanzi Stroke Order QingDu',
            fields=[
                {'name': 'Translation'},
                {'name': 'Hanzi'},
                {'name': 'Pinyin'},
                {'name': 'Mp3'},
                {'name': 'DeckIdentifier'},
            ],
            templates=[{
                'name': 'Hanzi Card',
                'qfmt': qfmt,
                'afmt': afmt,
            }],
        )
        
        # Create subdecks for each section
        decks = []
        all_notes = []
        deck_id_base = vocab_list.anki_deck_id or (2000000 + list_id)
        
        for section in sections:
            section_name = section.get('name', 'Main')
            words = section.get('words', [])
            
            if not words:
                continue
            
            # Create subdeck: "List Name::Section Name"
            subdeck_name = f"{vocab_list.name}::{section_name}"
            subdeck_id = deck_id_base + hash(section_name) % 100000
            
            subdeck = genanki.Deck(subdeck_id, subdeck_name)
            deck_identifier = f"[{subdeck_name}]"
            
            for word_data in words:
                hanzi = word_data.get('hanzi', '')
                pinyin = word_data.get('pinyin', '')
                meaning = word_data.get('meaning', '')
                
                if not hanzi:
                    continue
                
                words_processed += 1
                mp3_field = ''
                
                # Generate or retrieve cached audio file
                try:
                    unicode_ids = "_".join(str(ord(char)) for char in hanzi)
                    cache_filename = f"{unicode_ids}_zh.mp3"
                    cache_path = audio_cache_dir / cache_filename
                    mp3_filename = os.path.join(temp_dir, f"{unicode_ids}_pronunciation.mp3")
                    
                    # ALWAYS check cache first - even if rate limited
                    if cache_path.exists() and cache_path.stat().st_size > 0:
                        shutil.copy2(cache_path, mp3_filename)
                        media_files.append(mp3_filename)
                        mp3_field = f'[sound:{os.path.basename(mp3_filename)}]'
                        audio_cached += 1
                        consecutive_failures = 0
                    
                    # Only try TTS if NOT cached and NOT rate limited
                    elif not rate_limited and consecutive_failures < 5:
                        try:
                            tts = gTTS(hanzi, lang='zh')
                            tts.save(mp3_filename)
                            shutil.copy2(mp3_filename, cache_path)
                            media_files.append(mp3_filename)
                            mp3_field = f'[sound:{os.path.basename(mp3_filename)}]'
                            audio_generated += 1
                            consecutive_failures = 0
                            
                            import time
                            time.sleep(0.1)
                            
                        except Exception as tts_error:
                            error_msg = str(tts_error)
                            if '429' in error_msg or 'Too Many Requests' in error_msg:
                                logger.warning(f"Rate limit hit at word '{hanzi}'")
                                rate_limited = True
                            else:
                                logger.debug(f"TTS failed for '{hanzi}': {tts_error}")
                                consecutive_failures += 1
                            
                            audio_failed += 1
                            failed_words.append(hanzi)
                    else:
                        # Rate limited or too many failures - skip TTS
                        audio_failed += 1
                
                except Exception as e:
                    audio_failed += 1
                    failed_words.append(hanzi)
                    logger.debug(f"Audio processing failed for '{hanzi}': {e}")
                
                # Create note
                note = genanki.Note(
                    model=model,
                    fields=[meaning, hanzi, pinyin, mp3_field, deck_identifier]
                )
                subdeck.add_note(note)
                all_notes.append(note)
            
            # Only add subdeck if it has notes
            if subdeck.notes:
                decks.append(subdeck)
        
        if not decks:
            raise HTTPException(status_code=400, detail="No words found to export")
        
        # Create package with all subdecks
        package = genanki.Package(decks)
        package.media_files = media_files
        
        # Write to temp file
        output_filename = f"{vocab_list.name.replace(' ', '_')}.apkg"
        output_path = os.path.join(temp_dir, output_filename)
        package.write_to_file(output_path)
        
        # Read file content
        with open(output_path, 'rb') as f:
            apkg_content = f.read()
        
        # Cleanup temp directory
        shutil.rmtree(temp_dir)

        # Log results
        logger.info(f"Export complete: {words_processed} words, {audio_cached} cached, {audio_generated} generated, {audio_failed} failed")
        if rate_limited:
            logger.warning(f"Rate limit reached. {audio_failed} cards created without audio.")

        # Return file using Response with explicit Content-Length
        from fastapi.responses import Response
        return Response(
            content=apkg_content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={output_filename}",
                "Content-Length": str(len(apkg_content)),
                "X-Export-Stats": f"{words_processed}|{audio_cached}|{audio_generated}|{audio_failed}",
                "X-Rate-Limited": "true" if rate_limited else "false"
            }
        )
    
    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        logger.error(f"Export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
     
@app.get("/api/vocabulary-lists/{list_id}/export")
async def export_vocabulary_list_csv(
    list_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Export vocabulary list as CSV"""
    vocab_list = db.query(VocabularyList).filter(
        VocabularyList.id == list_id,
        VocabularyList.user_id == user.id
    ).first()
    
    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")
    
    sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    
    # Build CSV content
    csv_lines = []
    for section in sections:
        for word in section.get('words', []):
            # Format: hanzi;pinyin;meaning;level
            hanzi = word.get('hanzi', '')
            pinyin = word.get('pinyin', '')
            meaning = word.get('meaning', '')
            level = word.get('level', '')
            
            line = f"{hanzi};{pinyin};{meaning};{level}"
            csv_lines.append(line)
    
    csv_content = "\n".join(csv_lines)
    
    from fastapi.responses import Response
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={vocab_list.name.replace(' ', '_')}.csv"
        }
    )
@app.get("/admin")
async def admin_page(request: Request):
    """Serve admin panel page"""
    return templates.TemplateResponse("admin.html", {"request": request})
@app.post("/api/admin/users/{user_id}/toggle-admin")
async def toggle_admin_status(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Toggle admin status for user"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent removing your own admin rights
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own admin status")
    
    user.is_admin = not user.is_admin
    db.commit()

    return {"message": f"User is now {'admin' if user.is_admin else 'regular user'}"}

@app.patch("/api/admin/users/{user_id}/invite-quota")
async def update_user_invite_quota(
    user_id: int,
    data: UpdateInviteQuotaRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update a user's invitation quota (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.invite_quota < -1:
        raise HTTPException(status_code=400, detail="Quota cannot be less than -1 (use -1 for unlimited)")

    user.invite_quota = data.invite_quota
    db.commit()

    return {
        "message": "Invite quota updated",
        "user_id": user.id,
        "username": user.username,
        "invite_quota": user.invite_quota
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

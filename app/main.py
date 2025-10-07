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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.database import init_db, get_db, SavedText
from sqlalchemy.orm import Session
from fastapi import Depends
from functools import lru_cache
from app.auth import (
    get_password_hash, 
    verify_password, 
    create_access_token,
    get_current_user,
    require_auth,
    require_admin
)
from app.database import User, VocabularyList
from pydantic import BaseModel
import genanki
from gtts import gTTS
import tempfile
import shutil

# Load environment variables
load_dotenv()

app = FastAPI(title="轻读 QingDu - Chinese Text Analyzer")
# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Directories
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "data"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Global vocabulary storage
hsk_vocab = {}
translation_cache = {}
unknown_word_cache = {}  # Cache for online lookups

class TextAnalysisRequest(BaseModel):
    text: str

class TranslationRequest(BaseModel):
    text: str
    target_lang: str = "en"

class WordInfo(BaseModel):
    text: str
    hsk_level: Optional[str] = None
    pinyin: Optional[str] = None
    meaning: Optional[str] = None
    meanings: Optional[List[str]] = None
    frequency: Optional[int] = None
    is_hsk: bool = False
    translation_source: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@app.on_event("startup")
async def startup_event():
    """Load HSK vocabulary on startup"""
    global hsk_vocab
    vocab_file = DATA_DIR / "hsk_vocabulary.json"
    
    if vocab_file.exists():
        # print("Loading HSK vocabulary from cache...")
        with open(vocab_file, 'r', encoding='utf-8') as f:
            hsk_vocab = json.load(f)
        # print(f"Loaded {len(hsk_vocab)} HSK words from cache")
    else:
        # print("Downloading HSK vocabulary from GitHub...")
        await download_hsk_vocabulary()
    
    # Check for common words and report if missing
    # common_words = ['第一天', '很多', '一个', '这个', '那个', '喝茶', '成都', '一位', '一种']
    # print("\nChecking common words in HSK database:")
    # for word in common_words:
    #     if word in hsk_vocab:
    #         print(f"  ✓ '{word}' found: {hsk_vocab[word]['meaning']}")
    #     else:
    #         print(f"  ✗ '{word}' MISSING from HSK database")
    
    # print("\nInitializing jieba tokenizer...")
    jieba.initialize()
    
    # print("Adding HSK words to jieba dictionary with high frequency...")
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
            base_freq = max(data.get('frequency', 0) * 100, 10000)
            # if word in priority_words:
            #     freq = base_freq * 10  # 10x priority for common words
            # else:
            freq = base_freq
            jieba.add_word(word, freq=freq)
            multi_char_count += 1
    
    # Force add priority words even if not in HSK with max frequency
    # for word in priority_words:
    #     if word not in hsk_vocab:
    #         jieba.add_word(word, freq=1000000)
    #         print(f"Force added priority word to jieba: {word}")

    # print(f"Added {multi_char_count} multi-character HSK words with priority to jieba")

    # Initialize database
    init_db()
    # print("Database initialized")

    # print("Startup complete!\n")

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
                must_change_password=True
            )
            db.add(admin)
            db.commit()
            print("✓ Initial admin user created: admin / admin123 (CHANGE PASSWORD!)")
        else:
            print(f"✓ Found {user_count} existing user(s)")
    
    except Exception as e:
        print(f"Error setting up users: {e}")
        db.rollback()
    finally:
        db.close()
    
    print("Startup complete!\n")

async def download_hsk_vocabulary():
    """Download and process HSK vocabulary from GitHub"""
    global hsk_vocab
    url = "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/refs/heads/main/complete.json"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            raw_data = response.json()
        
        processed = 0
        char_levels = {}  # Track lowest HSK level for each character
        
        for entry in raw_data:
            if not isinstance(entry, dict):
                continue
            
            simplified = entry.get('simplified')
            if not simplified:
                continue
            
            levels = entry.get('level', [])
            if not levels:
                continue
            
            forms = entry.get('forms', [])
            if not forms:
                continue
            
            # Choose best form (prefer substantive meanings over names/abbreviations)
            best_form = None
            fallback_form = None
            
            for form in forms:
                form_meanings = form.get('meanings', [])
                if not form_meanings:
                    continue
                
                first_meaning = form_meanings[0]
                
                if fallback_form is None:
                    fallback_form = form
                
                if first_meaning.startswith('surname ') or first_meaning.startswith('abbr. for '):
                    continue
                
                best_form = form
                break
            
            best_form = best_form or fallback_form or forms[0]
            
            # Extract data from best form
            transcriptions = best_form.get('transcriptions', {})
            pinyin = transcriptions.get('pinyin', '')
            meanings = best_form.get('meanings', [])
            
            hsk_level = None
            for level in levels:
                if isinstance(level, str) and level.startswith('new-'):
                    hsk_level = level
                    break
            
            if not hsk_level:
                for level in levels:
                    if isinstance(level, str) and level.startswith('old-'):
                        hsk_level = level.replace('old-', 'new-')
                        break
            
            if hsk_level and simplified:
                # Build new entry
                new_entry = {
                    'pinyin': pinyin,
                    'meaning': meanings[0] if meanings else 'No translation',
                    'meanings': meanings,
                    'level': hsk_level,
                    'frequency': entry.get('frequency', 0)
                }
                
                if simplified not in hsk_vocab:
                    hsk_vocab[simplified] = new_entry
                else:
                    # Compare entries
                    existing = hsk_vocab[simplified]
                    existing_level = int(existing['level'].replace('new-', '').replace('+', ''))
                    new_level = int(hsk_level.replace('new-', '').replace('+', ''))
                    
                    existing_meaning = existing.get('meaning', '')
                    new_meaning = new_entry['meaning']
                    
                    existing_is_bad = 'abbr.' in existing_meaning or 'variant of' in existing_meaning
                    new_is_good = 'abbr.' not in new_meaning and 'variant of' not in new_meaning
                    
                    should_replace = (
                        new_level < existing_level or
                        (new_level == existing_level and existing_is_bad and new_is_good)
                    )
                    
                    if should_replace:
                        hsk_vocab[simplified] = new_entry
                
                processed += 1
                
                # Track the lowest HSK level for each character
                level_num = int(hsk_level.replace('new-', '').replace('+', ''))
                for char in simplified:
                    if char not in char_levels or level_num < char_levels[char]:
                        char_levels[char] = level_num
        
        # Now add individual characters with their lowest HSK level
        for char, level_num in char_levels.items():
            if char not in hsk_vocab:
                char_pinyin_list = lazy_pinyin(char, style=Style.TONE)
                char_pinyin = ' '.join(char_pinyin_list)
                hsk_vocab[char] = {
                    'pinyin': char_pinyin,
                    'meaning': f'(character, HSK {level_num})',
                    'meanings': [f'character component'],
                    'level': f'new-{level_num}',
                    'frequency': 0
                }
        
        vocab_file = DATA_DIR / "hsk_vocabulary.json"
        with open(vocab_file, 'w', encoding='utf-8') as f:
            json.dump(hsk_vocab, f, ensure_ascii=False, indent=2)
        
        # print(f"Processed and saved {processed} HSK words + {len(char_levels)} individual characters")
    
    except Exception as e:
        print(f"Error downloading vocabulary: {e}")
        raise

@app.get("/")
async def home(request: Request):
    """Serve main page"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "vocab_count": len(hsk_vocab)
    })

async def lookup_unknown_word(word: str) -> Optional[Dict]:
    """
    Look up unknown word online using translation API and pypinyin
    """
    # Check cache first
    if word in unknown_word_cache:
        return unknown_word_cache[word]
    
    # Get pinyin using pypinyin
    pinyin_result = lazy_pinyin(word, style=Style.TONE)
    word_pinyin = ' '.join(pinyin_result)
    
    # Try online translation
    translation_result = await get_translation_with_source(word)
    
    if translation_result:
        word_info = {
            'pinyin': word_pinyin,
            'meaning': translation_result['translation'],
            'meanings': [translation_result['translation']],
            'level': 'unknown',
            'frequency': 0,
            'translation_source': translation_result['source']
        }
        
        # Cache the result
        unknown_word_cache[word] = word_info
        return word_info
    
    return None

async def create_compound_from_hsk(word: str) -> Optional[Dict]:
    """
    Create compound word info from HSK characters with online translation
    Uses highest HSK level from component characters
    """
    chars = list(word)
    char_pinyins = []
    char_levels = []
    char_meanings = []
    
    # Check if all characters are in HSK and collect their levels
    for char in chars:
        if char in hsk_vocab:
            char_pinyins.append(hsk_vocab[char]['pinyin'])
            char_meanings.append(hsk_vocab[char]['meaning'])
            level_str = hsk_vocab[char]['level'].replace('new-', '').replace('old-', '').replace('+', '')
            try:
                char_levels.append(int(level_str))
            except:
                char_levels.append(1)
        else:
            return None
    
    # Build pinyin from HSK characters
    compound_pinyin = ' '.join(char_pinyins)
    
    # Use highest level from component characters
    max_level = max(char_levels)
    compound_level = f'new-{max_level}'
    
    # Fallback meaning from characters
    fallback_meaning = ' + '.join(char_meanings)
    
    # Try to get proper translation online
    translation_result = await get_translation_with_source(word)
    
    if translation_result:
        translation = translation_result['translation']
        source = translation_result['source']
        
        # Check if translation is just pinyin (failed translation)
        # If translation contains only Latin letters and spaces, it's probably just pinyin
        # Only use fallback if translation seems invalid (too short or same as pinyin)
        if len(translation) < 3 or translation.lower() == compound_pinyin.lower().replace(' ', ''):
            translation = fallback_meaning
            source = 'hsk-chars'
        
        return {
            'pinyin': compound_pinyin,
            'meaning': translation,
            'meanings': [translation],
            'level': compound_level,
            'frequency': 0,
            'translation_source': source
        }
    
    # If online lookup completely failed, use character meanings
    return {
        'pinyin': compound_pinyin,
        'meaning': fallback_meaning,
        'meanings': char_meanings,
        'level': compound_level,
        'frequency': 0,
        'translation_source': 'hsk-chars'
    }

async def get_translation_with_source(text: str) -> Optional[Dict]:
    """
    Get translation with multiple API support and source tracking
    Priority: DeepL > Google > MyMemory
    """
    # Check for API keys from environment
    deepl_key = os.getenv('DEEPL_API_KEY')
    google_key = os.getenv('GOOGLE_TRANSLATE_API_KEY')
    
    # Try DeepL first if available
    if deepl_key:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                url = "https://api-free.deepl.com/v2/translate"
                data = {
                    'auth_key': deepl_key,
                    'text': text,
                    'target_lang': 'EN',
                    'source_lang': 'ZH'
                }
                response = await client.post(url, data=data)
                response.raise_for_status()
                result = response.json()
                
                if result.get('translations'):
                    return {
                        'translation': result['translations'][0]['text'],
                        'source': 'deepl'
                    }
        except Exception as e:
            print(f"DeepL API failed for '{text}': {e}")
    
    # Try Google Translate if available
    if google_key:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                url = f"https://translation.googleapis.com/language/translate/v2"
                params = {
                    'key': google_key,
                    'q': text,
                    'target': 'en',
                    'source': 'zh'
                }
                response = await client.post(url, params=params)
                response.raise_for_status()
                result = response.json()
                
                if result.get('data', {}).get('translations'):
                    return {
                        'translation': result['data']['translations'][0]['translatedText'],
                        'source': 'google'
                    }
        except Exception as e:
            print(f"Google Translate API failed for '{text}': {e}")
    
    # Fallback to free MyMemory API
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            url = f"https://api.mymemory.translated.net/get?q={text}&langpair=zh|en"
            response = await client.get(url)
            response.raise_for_status()
            result = response.json()
            
            if result.get('responseStatus') == 200:
                return {
                    'translation': result['responseData']['translatedText'],
                    'source': 'mymemory'
                }
    except Exception as e:
        print(f"MyMemory API failed for '{text}': {e}")
    
    return None

@app.post("/api/analyze")
@limiter.limit("30/minute")
async def analyze_text(request: Request, data: TextAnalysisRequest) -> Dict:
    """Analyze Chinese text and return HSK information"""
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")
    
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")
    
    segments = list(jieba.cut(text))
    
    # Debug logging - show what jieba segmented
    # print(f"Analyzing text, total segments: {len(segments)}")
    # print(f"Segmentation result: {' | '.join(segments)}")
    
    words = []
    hsk_stats = {f'hsk{i}': 0 for i in range(1, 10)}
    total_hsk_words = 0
    
    for segment in segments:
        word_info = WordInfo(text=segment)
        
        vocab_entry = get_word_info(segment)
        if vocab_entry:
            vocab_entry = hsk_vocab[segment]
            word_info.hsk_level = vocab_entry['level']
            word_info.pinyin = vocab_entry['pinyin']
            word_info.meaning = vocab_entry['meaning']
            word_info.meanings = vocab_entry['meanings']
            word_info.frequency = vocab_entry['frequency']
            word_info.is_hsk = True
            word_info.translation_source = 'hsk'  # Mark as HSK vocabulary
            
            level_num = vocab_entry['level'].replace('new-', '').replace('old-', '').replace('+', '')
            try:
                level_key = f'hsk{int(level_num)}'
                if level_key in hsk_stats:
                    hsk_stats[level_key] += 1
                total_hsk_words += 1
            except ValueError:
                pass
        
        elif len(segment) > 1:
            # First check: is this a compound of HSK characters?
            chars = list(segment)
            all_chars_in_hsk = all(char in hsk_vocab for char in chars)
            
            if all_chars_in_hsk:
                # It's an HSK compound - use compound method with online translation
                compound_info = await create_compound_from_hsk(segment)
                if compound_info:
                    word_info.hsk_level = compound_info['level']
                    word_info.pinyin = compound_info['pinyin']
                    word_info.meaning = compound_info['meaning']
                    word_info.meanings = compound_info['meanings']
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    word_info.translation_source = compound_info.get('translation_source')
                #     print(f"Compound created for '{segment}': {compound_info['meaning']}")
                # else:
                #     print(f"Compound method failed for '{segment}'")
            else:
                # Debug: show which character is missing
                # missing_chars = [char for char in chars if char not in hsk_vocab]
                # if missing_chars:
                #     print(f"Not HSK compound '{segment}': missing chars {missing_chars}")
                
                # Not an HSK compound - do online lookup for everything
                online_info = await lookup_unknown_word(segment)
                if online_info:
                    word_info.hsk_level = 'unknown'
                    word_info.pinyin = online_info['pinyin']
                    word_info.meaning = online_info['meaning']
                    word_info.meanings = online_info['meanings']
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    word_info.translation_source = online_info.get('translation_source')
                #     print(f"Online lookup for '{segment}': {online_info['meaning']}")
                # else:
                #     # Debug: log segments that couldn't be looked up
                #     if segment.strip() and not segment.isspace() and segment not in ['，', '。', '！', '？', '；', '：', '"', '"', ''', ''']:
                #         print(f"Could not find info for: '{segment}'")
        
        words.append(word_info.dict())
    
    # Debug: Print first word to verify translation_source
    # if words:
    #     print(f"DEBUG - First word data: {words[0]}")
    
    estimated_level = estimate_text_level(hsk_stats, total_hsk_words)
    
    return {
        'words': words,
        'statistics': {
            'total_characters': len(text),
            'total_words': len(segments),
            'hsk_words': total_hsk_words,
            'hsk_distribution': hsk_stats,
            'estimated_level': estimated_level
        }
    }

def estimate_text_level(hsk_stats: Dict, total_hsk_words: int) -> str:
    """Estimate text difficulty based on HSK word distribution"""
    if total_hsk_words == 0:
        return "Unknown"
    
    # Calculate cumulative percentage approach
    # Text level = highest level where you'd understand 80%+ of words
    cumulative_words = 0
    
    for level in range(1, 10):
        cumulative_words += hsk_stats.get(f'hsk{level}', 0)
        percentage = (cumulative_words / total_hsk_words) * 100
        
        # If you know up to this level and understand 80%+ of words, this is the text level
        if percentage >= 80:
            return f"HSK {level}"
    
    # If even HSK 9 doesn't cover 80%, it's beyond HSK
    return "HSK 9+"

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
    """Get complete HSK vocabulary for client-side list generation"""
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")
    
    return hsk_vocab

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "vocab_loaded": len(hsk_vocab) > 0,
        "vocab_count": len(hsk_vocab)
    }

@app.get("/api/tts/{text}")
async def text_to_speech(text: str):
    """Text-to-speech proxy for Google Translate TTS"""
    try:
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text}&tl=zh-CN&client=gtx"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            from fastapi.responses import Response
            return Response(
                content=response.content,
                media_type="audio/mpeg",
                headers={
                    "Cache-Control": "public, max-age=86400"
                }
            )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")

@lru_cache(maxsize=1000)
def cached_translation(text: str, target_lang: str) -> Optional[str]:
    """Cache translations to reduce API calls"""
    return None

@app.post("/api/translate")
@limiter.limit("20/minute")
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
                "source": "cache",
                "cached": True
            }
        else:
            return {
                "translation": cached_result.get('translation', cached_result),
                "source": cached_result.get('source', 'cache'),
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
    """Get all saved texts for current user"""
    texts = db.query(SavedText).filter(
        SavedText.user_id == user.id
    ).order_by(SavedText.created_at.desc()).all()
    
    return [{
        "id": text.id,
        "title": text.title,
        "content": text.content,
        "date": text.created_at.isoformat(),
        "analysisData": json.loads(text.analysis_data),
        "tags": text.tags,
        "reading_progress": text.reading_progress or 0  # NEW
    } for text in texts]

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
    
    if 'reading_progress' in data:  # ADD THIS
        text.reading_progress = data['reading_progress']
    
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

@app.post("/api/auth/login")
async def login(data: LoginRequest, db: Session = Depends(get_db)):
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
    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters"
        )
    
    user.password_hash = get_password_hash(data.new_password)
    user.must_change_password = False
    db.commit()
    
    return {"message": "Password changed successfully"}

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
    
    new_password = data.get("new_password")
    if not new_password or len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters"
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
    
    return [{
        "id": l.id,
        "name": l.name,
        "type": l.list_type,
        "sections": json.loads(l.sections) if l.sections else []
    } for l in lists]

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
    
    # Check if word already exists
    word = {
        'hanzi': word_data.get('hanzi'),
        'pinyin': word_data.get('pinyin'),
        'meaning': word_data.get('meaning'),
        'level': word_data.get('level')
    }
    
    if any(w['hanzi'] == word['hanzi'] for w in section['words']):
        return {"message": "Word already in list"}
    
    section['words'].append(word)
    vocab_list.sections = json.dumps(sections)
    db.commit()
    
    return {"message": "Word added"}

@app.get("/api/vocabulary-lists/{list_id}/export-anki")
async def export_vocabulary_list_anki(
    list_id: int,
    user: User = Depends(require_auth),
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
                
                # Check if we should stop trying TTS
                if rate_limited or consecutive_failures >= 5:
                    # Skip TTS generation, just create card without audio
                    note = genanki.Note(
                        model=model,
                        fields=[meaning, hanzi, pinyin, '', deck_identifier]
                    )
                    subdeck.add_note(note)
                    all_notes.append(note)
                    audio_failed += 1
                    continue
                
                # Generate or retrieve cached audio file
                try:
                    unicode_ids = "_".join(str(ord(char)) for char in hanzi)
                    cache_filename = f"{unicode_ids}_zh.mp3"
                    cache_path = audio_cache_dir / cache_filename
                    
                    # Prepare temp file path
                    mp3_filename = os.path.join(temp_dir, f"{unicode_ids}_pronunciation.mp3")
                    
                    # Check cache first
                    if cache_path.exists() and cache_path.stat().st_size > 0:
                        # Use cached audio
                        shutil.copy2(cache_path, mp3_filename)
                        media_files.append(mp3_filename)
                        audio_cached += 1
                        consecutive_failures = 0
                    else:
                        # Generate new audio
                        try:
                            tts = gTTS(hanzi, lang='zh')
                            tts.save(mp3_filename)
                            
                            # Save to cache for future use
                            shutil.copy2(mp3_filename, cache_path)
                            media_files.append(mp3_filename)
                            audio_generated += 1
                            consecutive_failures = 0
                            
                            # Small delay to avoid hammering API
                            import time
                            time.sleep(0.1)
                            
                        except Exception as tts_error:
                            # Check if it's a rate limit error
                            error_msg = str(tts_error)
                            if '429' in error_msg or 'Too Many Requests' in error_msg:
                                print(f"⚠️ Rate limit hit at word '{hanzi}'. Stopping TTS generation.")
                                rate_limited = True
                                audio_failed += 1
                                failed_words.append(hanzi)
                            else:
                                print(f"TTS failed for '{hanzi}': {tts_error}")
                                consecutive_failures += 1
                                audio_failed += 1
                                failed_words.append(hanzi)
                            
                            mp3_field = ''
                    
                    if mp3_filename in media_files:
                        mp3_field = f'[sound:{os.path.basename(mp3_filename)}]'
                
                except Exception as e:
                    audio_failed += 1
                    failed_words.append(hanzi)
                    consecutive_failures += 1
                    print(f"Audio processing failed for '{hanzi}': {e}")
                
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
        print(f"Export complete: {words_processed} words, {audio_cached} cached, {audio_generated} generated, {audio_failed} failed")
        if rate_limited:
            print(f"⚠️ Rate limit reached. {audio_failed} cards created without audio.")
        
        # Return file
        from fastapi.responses import Response
        return Response(
            content=apkg_content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={output_filename}",
                "X-Export-Stats": f"{words_processed}|{audio_cached}|{audio_generated}|{audio_failed}",
                "X-Rate-Limited": "true" if rate_limited else "false"
            }
        )
    
    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        print(f"Export error: {e}")
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
from fastapi import FastAPI, Request, HTTPException
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

app = FastAPI(title="轻读 QingDu - Chinese Text Analyzer")

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

@app.on_event("startup")
async def startup_event():
    """Load HSK vocabulary on startup"""
    global hsk_vocab
    vocab_file = DATA_DIR / "hsk_vocabulary.json"
    
    if vocab_file.exists():
        print("Loading HSK vocabulary from cache...")
        with open(vocab_file, 'r', encoding='utf-8') as f:
            hsk_vocab = json.load(f)
        print(f"Loaded {len(hsk_vocab)} HSK words from cache")
    else:
        print("Downloading HSK vocabulary from GitHub...")
        await download_hsk_vocabulary()
    
    # Check for common words and report if missing
    common_words = ['第一天', '很多', '一个', '这个', '那个', '喝茶', '成都', '一位', '一种']
    print("\nChecking common words in HSK database:")
    for word in common_words:
        if word in hsk_vocab:
            print(f"  ✓ '{word}' found: {hsk_vocab[word]['meaning']}")
        else:
            print(f"  ✗ '{word}' MISSING from HSK database")
    
    print("\nInitializing jieba tokenizer...")
    jieba.initialize()
    
    print("Adding HSK words to jieba dictionary with high frequency...")
    multi_char_count = 0
    
    # Common multi-character words that must be recognized as units
    priority_words = ['第一', '第二', '第三', '很多', '一个', '这个', '那个', '什么', 
                      '怎么', '为什么', '可以', '喝茶', '吃饭', '第一天', '每天',
                      '今天', '明天', '昨天', '去年', '今年', '明年', '一位', '一种',
                      '成都', '茶馆', '打麻将', '武侯祠', '三国', '诸葛亮', '道家',
                      '麻婆豆腐', '担担面', '当地人', '四川菜', '阴阳', '老先生', '这次']
    
    for word, data in hsk_vocab.items():
        if len(word) > 1:
            # Add with high frequency to prioritize HSK words in segmentation
            # Give extra priority to common multi-char words
            base_freq = max(data.get('frequency', 0) * 100, 10000)
            if word in priority_words:
                freq = base_freq * 10  # 10x priority for common words
            else:
                freq = base_freq
            jieba.add_word(word, freq=freq)
            multi_char_count += 1
    
    # Force add priority words even if not in HSK with max frequency
    for word in priority_words:
        if word not in hsk_vocab:
            jieba.add_word(word, freq=1000000)
            print(f"Force added priority word to jieba: {word}")
    
    print(f"Added {multi_char_count} multi-character HSK words with priority to jieba")
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
            
            first_form = forms[0]
            transcriptions = first_form.get('transcriptions', {})
            pinyin = transcriptions.get('pinyin', '')
            meanings = first_form.get('meanings', [])
            
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
                hsk_vocab[simplified] = {
                    'pinyin': pinyin,
                    'meaning': meanings[0] if meanings else 'No translation',
                    'meanings': meanings,
                    'level': hsk_level,
                    'frequency': entry.get('frequency', 0)
                }
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
        
        print(f"Processed and saved {processed} HSK words + {len(char_levels)} individual characters")
    
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
    
    try:
        # Get pinyin using pypinyin
        pinyin_result = lazy_pinyin(word, style=Style.TONE)
        word_pinyin = ' '.join(pinyin_result)
        
        # Get translation using MyMemory API with shorter timeout
        async with httpx.AsyncClient(timeout=3.0) as client:
            url = f"https://api.mymemory.translated.net/get?q={word}&langpair=zh|en"
            response = await client.get(url)
            response.raise_for_status()
            result = response.json()
            
            if result.get('responseStatus') == 200:
                translation = result['responseData']['translatedText']
                
                word_info = {
                    'pinyin': word_pinyin,
                    'meaning': translation,
                    'meanings': [translation],
                    'level': 'unknown',
                    'frequency': 0
                }
                
                # Cache the result
                unknown_word_cache[word] = word_info
                return word_info
    
    except Exception as e:
        print(f"Online lookup failed for '{word}': {e}")
    
    return None

async def create_compound_from_hsk(word: str) -> Optional[Dict]:
    """
    Create compound word info from HSK characters with online translation
    Uses highest HSK level from component characters
    """
    chars = list(word)
    char_pinyins = []
    char_levels = []
    
    # Check if all characters are in HSK and collect their levels
    for char in chars:
        if char in hsk_vocab:
            char_pinyins.append(hsk_vocab[char]['pinyin'])
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
    
    # Try to get proper translation online
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            url = f"https://api.mymemory.translated.net/get?q={word}&langpair=zh|en"
            response = await client.get(url)
            response.raise_for_status()
            result = response.json()
            
            if result.get('responseStatus') == 200:
                translation = result['responseData']['translatedText']
                
                word_info = {
                    'pinyin': compound_pinyin,
                    'meaning': translation,
                    'meanings': [translation],
                    'level': compound_level,
                    'frequency': 0
                }
                return word_info
    except Exception as e:
        print(f"Online translation failed for compound '{word}': {e}")
    
    # Fallback: use character meanings if online fails
    char_meanings = [hsk_vocab[char]['meaning'] for char in chars]
    return {
        'pinyin': compound_pinyin,
        'meaning': ' + '.join(char_meanings),
        'meanings': char_meanings,
        'level': compound_level,
        'frequency': 0
    }

@app.post("/api/analyze")
async def analyze_text(data: TextAnalysisRequest) -> Dict:
    """Analyze Chinese text and return HSK information"""
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")
    
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")
    
    segments = list(jieba.cut(text))
    
    # Debug logging - show what jieba segmented
    print(f"Analyzing text, total segments: {len(segments)}")
    print(f"Segmentation result: {' | '.join(segments)}")
    
    words = []
    hsk_stats = {f'hsk{i}': 0 for i in range(1, 10)}
    total_hsk_words = 0
    
    for segment in segments:
        word_info = WordInfo(text=segment)
        
        if segment in hsk_vocab:
            vocab_entry = hsk_vocab[segment]
            word_info.hsk_level = vocab_entry['level']
            word_info.pinyin = vocab_entry['pinyin']
            word_info.meaning = vocab_entry['meaning']
            word_info.meanings = vocab_entry['meanings']
            word_info.frequency = vocab_entry['frequency']
            word_info.is_hsk = True
            
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
                    print(f"Compound created for '{segment}': {compound_info['meaning']}")
                else:
                    print(f"Compound method failed for '{segment}'")
            else:
                # Debug: show which character is missing
                missing_chars = [char for char in chars if char not in hsk_vocab]
                if missing_chars:
                    print(f"Not HSK compound '{segment}': missing chars {missing_chars}")
                
                # Not an HSK compound - do online lookup for everything
                online_info = await lookup_unknown_word(segment)
                if online_info:
                    word_info.hsk_level = 'unknown'
                    word_info.pinyin = online_info['pinyin']
                    word_info.meaning = online_info['meaning']
                    word_info.meanings = online_info['meanings']
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    print(f"Online lookup for '{segment}': {online_info['meaning']}")
                else:
                    # Debug: log segments that couldn't be looked up
                    if segment.strip() and not segment.isspace() and segment not in ['，', '。', '！', '？', '；', '：', '"', '"', ''', ''']:
                        print(f"Could not find info for: '{segment}'")
        
        words.append(word_info.dict())
    
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
    
    threshold = total_hsk_words * 0.2
    
    for level in range(9, 0, -1):
        if hsk_stats.get(f'hsk{level}', 0) > threshold:
            return f"HSK {level}"
    
    max_level = max(hsk_stats.items(), key=lambda x: x[1])
    return f"HSK {max_level[0].replace('hsk', '')}"

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
async def translate_text(data: TranslationRequest) -> Dict:
    """Translate Chinese text to target language"""
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")
    
    cache_key = f"{text}_{data.target_lang}"
    if cache_key in translation_cache:
        return {"translation": translation_cache[cache_key], "cached": True}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"https://api.mymemory.translated.net/get?q={text}&langpair=zh|{data.target_lang}"
            response = await client.get(url)
            response.raise_for_status()
            result = response.json()
            
            if result.get('responseStatus') == 200:
                translation = result['responseData']['translatedText']
                translation_cache[cache_key] = translation
                return {"translation": translation, "cached": False}
            else:
                raise HTTPException(status_code=500, detail="Translation service error")
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Translation timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
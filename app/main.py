from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import jieba
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
import httpx
from functools import lru_cache

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

class TextAnalysisRequest(BaseModel):
    text: str

class TranslationRequest(BaseModel):
    text: str
    target_lang: str = "de"

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
    
    print("Initializing jieba tokenizer...")
    jieba.initialize()
    
    print("Adding HSK words to jieba dictionary...")
    multi_char_count = 0
    for word in hsk_vocab.keys():
        if len(word) > 1:
            jieba.add_word(word)
            multi_char_count += 1
    
    print(f"Added {multi_char_count} multi-character words to jieba")
    print("Startup complete!")

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
        
        vocab_file = DATA_DIR / "hsk_vocabulary.json"
        with open(vocab_file, 'w', encoding='utf-8') as f:
            json.dump(hsk_vocab, f, ensure_ascii=False, indent=2)
        
        print(f"Processed and saved {processed} HSK words")
    
    except Exception as e:
        print(f"Error downloading vocabulary: {e}")
        raise

def create_compound_word_info(word: str) -> Optional[Dict]:
    """
    Create info for compound words not in HSK database
    by combining info from individual characters
    """
    chars = list(word)
    
    char_data = []
    for char in chars:
        if char in hsk_vocab:
            char_data.append(hsk_vocab[char])
        else:
            return None
    
    if not char_data:
        return None
    
    levels = [d['level'] for d in char_data]
    level_nums = []
    for level in levels:
        num = level.replace('new-', '').replace('old-', '').replace('+', '')
        try:
            level_nums.append(int(num))
        except:
            level_nums.append(1)
    
    max_level = max(level_nums)
    
    pinyins = [d['pinyin'] for d in char_data]
    meanings = [d['meaning'] for d in char_data]
    
    return {
        'pinyin': ' '.join(pinyins),
        'meaning': ' + '.join(meanings),
        'meanings': meanings,
        'level': f'new-{max_level}',
        'frequency': 0
    }

@app.get("/")
async def home(request: Request):
    """Serve main page"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "vocab_count": len(hsk_vocab)
    })

@app.post("/api/analyze")
async def analyze_text(data: TextAnalysisRequest) -> Dict:
    """Analyze Chinese text and return HSK information"""
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")
    
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")
    
    segments = list(jieba.cut(text))
    
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
            compound_info = create_compound_word_info(segment)
            if compound_info:
                word_info.hsk_level = compound_info['level']
                word_info.pinyin = compound_info['pinyin']
                word_info.meaning = compound_info['meaning']
                word_info.meanings = compound_info['meanings']
                word_info.frequency = 0
                word_info.is_hsk = True
                
                level_num = compound_info['level'].replace('new-', '')
                try:
                    level_key = f'hsk{int(level_num)}'
                    if level_key in hsk_stats:
                        hsk_stats[level_key] += 1
                    total_hsk_words += 1
                except ValueError:
                    pass
        
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
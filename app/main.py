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
    require_admin
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

# Directories
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Global vocabulary storage
hsk_vocab = {}

# Character to radical mapping (fallback for characters missing radical data in vocabulary)
CHAR_TO_RADICAL = {
    '汉': '氵', '语': '讠', '的': '白', '了': '乙', '我': '戈', '你': '亻',
    '他': '亻', '她': '女', '们': '亻', '这': '⻌', '那': '阝', '个': '亻',
    '什': '亻', '么': '丿', '时': '日', '候': '亻', '间': '门', '年': '丿',
    '月': '月', '日': '日', '天': '大', '上': '一', '下': '一', '来': '木',
    '去': '厶', '说': '讠', '话': '讠', '看': '手', '听': '口', '做': '亻',
    '吃': '口', '喝': '口', '买': '乛', '卖': '十', '想': '心', '知': '矢',
    '道': '⻌', '得': '彳', '会': '人', '能': '厶', '可': '口', '以': '亻',
    '和': '禾', '在': '土', '有': '月', '没': '氵', '很': '彳', '太': '大',
    '都': '阝', '还': '⻌', '就': '尢', '把': '扌', '被': '衤', '让': '讠',
    '给': '糹', '从': '人', '到': '至', '为': '丶', '对': '又', '关': '丷',
    '于': '二', '然': '灬', '后': '口', '前': '丷', '中': '丨', '里': '里',
    '外': '夕', '边': '⻌', '东': '一', '西': '西', '南': '十', '北': '丨',
    '大': '大', '小': '小', '多': '夕', '少': '小', '好': '女', '坏': '土',
    '新': '斤', '旧': '丨', '长': '长', '短': '矢', '高': '高', '低': '亻',
    '快': '忄', '慢': '忄', '早': '日', '晚': '日', '老': '老', '少': '小',
    '男': '田', '女': '女', '子': '子', '父': '父', '母': '毋', '哥': '口',
    '弟': '弓', '姐': '女', '妹': '女', '朋': '月', '友': '又', '人': '人',
    '先': '儿', '生': '生', '学': '⺌', '校': '木', '师': '巾', '教': '攵',
    '室': '宀', '班': '王', '书': '乛', '字': '子', '词': '讠', '句': '勹',
    '文': '文', '章': '立', '问': '门', '题': '页', '答': '⺮', '考': '耂',
    '试': '讠', '笔': '⺮', '纸': '糹', '本': '木', '读': '讠', '写': '冖',
    '记': '讠', '住': '亻', '走': '走', '跑': '足', '站': '立', '坐': '土',
    '躺': '身', '睡': '目', '起': '走', '开': '廾', '关': '丷', '进': '⻌',
    '出': '凵', '回': '囗', '过': '⻌', '到': '至', '离': '亠', '远': '⻌',
    '近': '⻌', '左': '工', '右': '口', '真': '十', '假': '亻', '对': '又',
    '错': '釒', '正': '一', '反': '厂', '同': '冂', '异': '廾', '用': '用',
    '种': '禾', '样': '木', '些': '二', '每': '母', '全': '入', '部': '阝',
    '分': '八', '别': '刂', '处': '夂', '所': '戶', '因': '囗', '果': '木',
    '原': '厂', '由': '丨', '经': '糹', '常': '巾', '但': '亻', '是': '日',
    '只': '口', '而': '而', '且': '一', '或': '口', '者': '耂', '比': '比',
    '较': '车', '最': '曰', '更': '一', '非': '非', '当': '⺌', '应': '广',
    '该': '讠', '各': '夂', '其': '八', '他': '亻', '它': '宀', '她': '女',
    '数': '攵', '量': '里', '次': '冫', '第': '⺮', '几': '几', '百': '白',
    '千': '丿', '万': '一', '亿': '亻',
    # Additional common characters
    '意': '心', '思': '心', '感': '心', '情': '忄', '爱': '爫', '觉': '见',
    '认': '讠', '识': '讠', '事': '亅', '件': '亻', '作': '亻', '工': '工',
    '动': '力', '活': '氵', '见': '见', '视': '见', '观': '见', '听': '口',
    '声': '士', '音': '音', '乐': '丿', '唱': '口', '歌': '欠', '跳': '足',
    '舞': '舛', '画': '田', '图': '囗', '片': '片', '影': '彡', '像': '亻',
    '照': '灬', '相': '木', '机': '木', '器': '口', '具': '八', '品': '口',
    '物': '牛', '东': '一', '西': '西', '南': '十', '北': '丨', '方': '方',
    '向': '丿', '面': '面', '位': '亻', '场': '土', '地': '土', '区': '匸',
    '城': '土', '市': '巾', '街': '行', '路': '足', '车': '车', '船': '舟',
    '飞': '飞', '机': '木', '火': '火', '水': '水', '电': '雨', '气': '气',
    '风': '风', '雨': '雨', '雪': '雨', '云': '二', '晴': '日', '阴': '阝',
    '冷': '冫', '热': '灬', '暖': '日', '凉': '冫', '温': '氵', '度': '广',
    '色': '色', '红': '糹', '黄': '黄', '蓝': '艹', '绿': '糹', '黑': '黑',
    '白': '白', '灰': '火', '紫': '糹', '粉': '米', '金': '金', '银': '金',
    '铜': '金', '铁': '金', '钱': '金', '元': '二', '块': '土', '角': '角',
    '价': '亻', '值': '亻', '贵': '贝', '贱': '贝', '费': '贝', '花': '艹',
    '买': '乛', '卖': '十', '售': '口', '购': '贝', '商': '口', '店': '广',
    '铺': '金', '场': '土', '馆': '饣', '院': '阝', '楼': '木', '房': '户',
    '门': '门', '窗': '穴', '墙': '土', '顶': '页', '底': '广', '层': '尸',
    '间': '门', '厅': '厂', '室': '宀', '厨': '厂', '卫': '卩', '床': '广',
    '桌': '木', '椅': '木', '柜': '木', '箱': '竹', '包': '勹', '袋': '衣',
    '服': '月', '衣': '衣', '裤': '衤', '裙': '衤', '鞋': '革', '帽': '巾',
    '衫': '衤', '套': '大', '件': '亻', '条': '木', '双': '又', '只': '口',
    '副': '刂', '套': '大', '身': '身', '体': '亻', '头': '页', '脸': '月',
    '眼': '目', '耳': '耳', '鼻': '鼻', '嘴': '口', '齿': '齿', '牙': '牙',
    '舌': '舌', '手': '手', '指': '扌', '脚': '月', '腿': '月', '臂': '月',
    '肩': '月', '背': '月', '腰': '月', '肚': '月', '胸': '月', '心': '心',
    '肝': '月', '肺': '月', '胃': '月', '肠': '月', '血': '血', '病': '疒',
    '疼': '疒', '痛': '疒', '伤': '亻', '药': '艹', '医': '匸', '院': '阝',
    '健': '亻', '康': '广', '安': '宀', '全': '入', '危': '厂', '险': '阝',
    '死': '歹', '亡': '亠', '活': '氵', '命': '口', '救': '攵', '助': '力',
    '帮': '巾', '护': '扌', '卫': '卩', '守': '宀', '保': '亻', '养': '羊',
    '育': '月', '培': '土', '训': '讠', '练': '糹', '习': '习', '复': '彳',
    '预': '页', '备': '夂', '准': '冫', '确': '石', '定': '宀', '决': '冫',
    '择': '扌', '选': '⻌', '择': '扌', '取': '又', '受': '又', '接': '扌',
    '待': '彳', '遇': '⻌', '迎': '⻌', '送': '⻌', '归': '彐', '返': '⻌',
    '始': '女', '终': '糹', '初': '刀', '末': '木', '首': '首', '尾': '尸',
    '完': '宀', '结': '糹', '束': '木', '继': '糹', '续': '糹', '停': '亻',
    '止': '止', '休': '亻', '息': '心', '闲': '门', '忙': '忄', '累': '糸',
    '劳': '力', '苦': '艹', '甜': '甘', '酸': '酉', '辣': '辛', '咸': '口',
    '淡': '氵', '浓': '氵', '厚': '厂', '薄': '艹', '深': '氵', '浅': '氵',
    '宽': '宀', '窄': '穴', '粗': '米', '细': '糹', '轻': '车', '重': '里',
    '硬': '石', '软': '车', '滑': '氵', '糙': '米', '光': '儿', '暗': '日',
    '亮': '亠', '明': '日', '清': '氵', '楚': '木', '洁': '氵', '脏': '月',
    '干': '干', '湿': '氵', '燥': '火', '润': '氵', '滑': '氵', '涩': '氵'
}

# Radical to pinyin mapping (common Chinese radicals)
RADICAL_PINYIN = {
    '一': 'yī', '丨': 'gǔn', '丶': 'zhǔ', '丿': 'piě', '乙': 'yǐ', '乚': 'yǐ', '乛': 'yǐ',
    '亅': 'jué', '二': 'èr', '亠': 'tóu', '人': 'rén', '亻': 'rén', '儿': 'ér',
    '入': 'rù', '八': 'bā', '冂': 'jiōng', '冖': 'mì', '冫': 'bīng',
    '几': 'jǐ', '凵': 'kǎn', '刀': 'dāo', '刂': 'dāo', '力': 'lì',
    '勹': 'bāo', '匕': 'bǐ', '匚': 'fāng', '匸': 'xì', '十': 'shí',
    '卜': 'bǔ', '卩': 'jié', '厂': 'chǎng', '厶': 'sī', '又': 'yòu',
    '口': 'kǒu', '囗': 'wéi', '土': 'tǔ', '士': 'shì', '夂': 'zhǐ',
    '夊': 'suī', '夕': 'xī', '大': 'dà', '女': 'nǚ', '子': 'zǐ',
    '宀': 'mián', '寸': 'cùn', '小': 'xiǎo', '⺌': 'xiǎo', '尢': 'wāng', '尸': 'shī', '耂': 'lǎo',
    '屮': 'chè', '山': 'shān', '巛': 'chuān', '工': 'gōng', '己': 'jǐ',
    '巾': 'jīn', '干': 'gān', '幺': 'yāo', '广': 'guǎng', '廴': 'yǐn',
    '廾': 'gǒng', '弋': 'yì', '弓': 'gōng', '彐': 'jì', '彡': 'shān',
    '彳': 'chì', '心': 'xīn', '忄': 'xīn', '⺗': 'xīn', '⺖': 'xīn', '戈': 'gē', '戶': 'hù',
    '户': 'hù', '手': 'shǒu', '扌': 'shǒu', '支': 'zhī', '攴': 'pū',
    '攵': 'pū', '文': 'wén', '斗': 'dǒu', '斤': 'jīn', '方': 'fāng',
    '无': 'wú', '日': 'rì', '曰': 'yuē', '月': 'yuè', '木': 'mù',
    '欠': 'qiàn', '止': 'zhǐ', '歹': 'dǎi', '殳': 'shū', '毋': 'wú',
    '比': 'bǐ', '毛': 'máo', '氏': 'shì', '气': 'qì', '水': 'shuǐ',
    '氵': 'shuǐ', '火': 'huǒ', '灬': 'huǒ', '爪': 'zhǎo', '爫': 'zhǎo',
    '父': 'fù', '爻': 'yáo', '爿': 'pán', '片': 'piàn', '牙': 'yá',
    '牛': 'niú', '犭': 'quǎn', '犬': 'quǎn', '玄': 'xuán', '玉': 'yù',
    '王': 'wáng', '瓜': 'guā', '瓦': 'wǎ', '甘': 'gān', '生': 'shēng',
    '用': 'yòng', '田': 'tián', '疋': 'pǐ', '疒': 'chuáng', '癶': 'bō',
    '白': 'bái', '皮': 'pí', '皿': 'mǐn', '目': 'mù', '矛': 'máo',
    '矢': 'shǐ', '石': 'shí', '⺕': 'shí', '示': 'shì', '⺬': 'shì', '⺭': 'shì', '礻': 'shì', '禸': 'róu', '禾': 'hé',
    '穴': 'xué', '立': 'lì', '竹': 'zhú', '⺮': 'zhú', '米': 'mǐ',
    '糸': 'mì', '糹': 'mì', '缶': 'fǒu', '网': 'wǎng', '罒': 'wǎng',
    '羊': 'yáng', '羽': 'yǔ', '老': 'lǎo', '而': 'ér', '耒': 'lěi', '习': 'xí',
    '耳': 'ěr', '聿': 'yù', '肉': 'ròu', '⺼': 'ròu', '月': 'yuè', '臣': 'chén',
    '自': 'zì', '至': 'zhì', '臼': 'jiù', '舌': 'shé', '舛': 'chuǎn',
    '舟': 'zhōu', '艮': 'gèn', '色': 'sè', '艸': 'cǎo', '艹': 'cǎo', '⺾': 'cǎo', '⺿': 'cǎo',
    '虍': 'hū', '虫': 'chóng', '血': 'xuè', '行': 'xíng', '衣': 'yī',
    '衤': 'yī', '襾': 'yà', '西': 'xī', '見': 'jiàn', '见': 'jiàn',
    '角': 'jiǎo', '言': 'yán', '訁': 'yán', '讑': 'yán', '谷': 'gǔ',
    '豆': 'dòu', '豕': 'shǐ', '豸': 'zhì', '貝': 'bèi', '贝': 'bèi',
    '赤': 'chì', '走': 'zǒu', '足': 'zú', '⻊': 'zú', '身': 'shēn',
    '車': 'chē', '车': 'chē', '辛': 'xīn', '辰': 'chén', '辵': 'chuò',
    '⻌': 'chuò', '辶': 'chuò', '邑': 'yì', '阝': 'fù', '⻏': 'fù', '酉': 'yǒu', '釆': 'biàn',
    '里': 'lǐ', '金': 'jīn', '釒': 'jīn', '長': 'cháng', '长': 'cháng',
    '門': 'mén', '门': 'mén', '阜': 'fù', '隶': 'lì', '隹': 'zhuī',
    '雨': 'yǔ', '靑': 'qīng', '青': 'qīng', '非': 'fēi', '面': 'miàn',
    '革': 'gé', '韋': 'wéi', '韦': 'wéi', '韭': 'jiǔ', '音': 'yīn',
    '頁': 'yè', '页': 'yè', '風': 'fēng', '风': 'fēng', '飛': 'fēi',
    '飞': 'fēi', '食': 'shí', '飠': 'shí', '饣': 'shí', '首': 'shǒu', '香': 'xiāng',
    '馬': 'mǎ', '马': 'mǎ', '骨': 'gǔ', '高': 'gāo', '髟': 'biāo',
    '鬥': 'dòu', '鬯': 'chàng', '鬲': 'lì', '鬼': 'guǐ', '魚': 'yú',
    '魚': 'yú', '鱼': 'yú', '鳥': 'niǎo', '鸟': 'niǎo', '鹵': 'lǔ',
    '鹿': 'lù', '麥': 'mài', '麦': 'mài', '麻': 'má', '黃': 'huáng',
    '黄': 'huáng', '黍': 'shǔ', '黑': 'hēi', '黹': 'zhǐ', '黽': 'mǐn',
    '鼎': 'dǐng', '鼓': 'gǔ', '鼠': 'shǔ', '鼻': 'bí', '齊': 'qí',
    '齿': 'chǐ', '齒': 'chǐ', '龍': 'lóng', '龙': 'lóng', '龜': 'guī',
    '龟': 'guī', '龠': 'yuè'
}

# TTL Caches with size limits
translation_cache = TTLCache(maxsize=TRANSLATION_CACHE_SIZE, ttl=TRANSLATION_CACHE_TTL)
unknown_word_cache = TTLCache(maxsize=UNKNOWN_WORD_CACHE_SIZE, ttl=UNKNOWN_WORD_CACHE_TTL)

class TextAnalysisRequest(BaseModel):
    text: str

class TranslationRequest(BaseModel):
    text: str
    target_lang: str = "en"

class WordInfo(BaseModel):
    text: str
    hsk_level: Optional[str] = None
    level_new: Optional[str] = None
    level_old: Optional[str] = None
    pinyin: Optional[str] = None
    meaning: Optional[str] = None
    meanings: Optional[List[str]] = None
    frequency: Optional[int] = None
    is_hsk: bool = False
    translation_source: Optional[str] = None
    radical: Optional[str] = None
    radical_pinyin: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

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

    global hsk_vocab
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
                    hsk_vocab = json.load(f)
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

def cleanup_old_backups(max_age_days: int = 30):
    """
    Remove backup files older than max_age_days

    Args:
        max_age_days: Maximum age of backups to keep (default: 30 days)
    """
    try:
        now = datetime.now()
        deleted_count = 0

        for backup_file in BACKUP_DIR.glob("*.json"):
            # Parse date from filename: complete_hsk_YYYY-MM-DD.json or hsk_vocabulary_YYYY-MM-DD.json
            try:
                date_str = backup_file.stem.split('_')[-1]  # Get last part (date)
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                age_days = (now - file_date).days

                if age_days > max_age_days:
                    backup_file.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old backup: {backup_file.name} (age: {age_days} days)")
            except (ValueError, IndexError):
                # Skip files that don't match expected naming pattern
                continue

        if deleted_count > 0:
            logger.info(f"Cleanup complete: removed {deleted_count} old backup(s)")
    except Exception as e:
        logger.warning(f"Backup cleanup failed: {e}")

@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=HSK_RETRY_MIN_WAIT, max=HSK_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True
)
async def download_hsk_vocabulary():
    """
    Download and process HSK vocabulary from GitHub
    Includes automatic retry with exponential backoff for network errors
    """
    global hsk_vocab

    try:
        async with httpx.AsyncClient(timeout=HSK_DOWNLOAD_TIMEOUT) as client:
            response = await client.get(HSK_VOCAB_URL)
            response.raise_for_status()
            raw_data = response.json()

        # Backup raw GitHub source with timestamp
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            raw_backup_file = BACKUP_DIR / f"complete_hsk_{today}.json"

            # Only create backup if one doesn't exist for today
            if not raw_backup_file.exists():
                with open(raw_backup_file, 'w', encoding='utf-8') as f:
                    json.dump(raw_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Backup saved: {raw_backup_file.name}")

                # Clean up old backups
                cleanup_old_backups(max_age_days=30)
        except Exception as e:
            logger.warning(f"Failed to create backup (non-critical): {e}")

        processed = 0
        char_levels_new = {}  # Track lowest NEW HSK level for each character
        char_levels_old = {}  # Track lowest OLD HSK level for each character

        # Debug counters
        total_entries = 0
        entries_with_both = 0
        entries_with_new_only = 0
        entries_with_old_only = 0

        for entry in raw_data:
            total_entries += 1
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

            # Extract BOTH new and old HSK levels
            level_new = None
            level_old = None
            for level in levels:
                if isinstance(level, str):
                    if level.startswith('new-'):
                        level_new = level
                    elif level.startswith('old-'):
                        level_old = level

            # Track level statistics for debugging
            if level_new and level_old:
                entries_with_both += 1
            elif level_new:
                entries_with_new_only += 1
            elif level_old:
                entries_with_old_only += 1

            # Need at least one level to include the word
            if (level_new or level_old) and simplified:
                # Extract radical information
                radical = entry.get('radical', '')

                # Build new entry with both levels
                new_entry = {
                    'pinyin': pinyin,
                    'meaning': meanings[0] if meanings else 'No translation',
                    'meanings': meanings,
                    'level_new': level_new,
                    'level_old': level_old,
                    'level': level_new or level_old,  # Backward compatibility
                    'frequency': entry.get('frequency', 0),
                    'radical': radical
                }

                if simplified not in hsk_vocab:
                    hsk_vocab[simplified] = new_entry
                else:
                    # Merge entries - keep best data from both
                    existing = hsk_vocab[simplified]

                    # Compare new HSK levels - keep the lower one
                    existing_new = existing.get('level_new')
                    new_new = new_entry.get('level_new')

                    best_level_new = existing_new
                    if new_new:
                        if not existing_new:
                            best_level_new = new_new
                        else:
                            existing_new_num = int(existing_new.replace('new-', '').replace('+', ''))
                            new_new_num = int(new_new.replace('new-', '').replace('+', ''))
                            if new_new_num < existing_new_num:
                                best_level_new = new_new

                    # Compare old HSK levels - keep the lower one
                    existing_old = existing.get('level_old')
                    new_old = new_entry.get('level_old')

                    best_level_old = existing_old
                    if new_old:
                        if not existing_old:
                            best_level_old = new_old
                        else:
                            existing_old_num = int(existing_old.replace('old-', ''))
                            new_old_num = int(new_old.replace('old-', ''))
                            if new_old_num < existing_old_num:
                                best_level_old = new_old

                    # Choose the best primary level (prefer new HSK)
                    best_level = best_level_new or best_level_old

                    # Compare meanings - prefer non-abbreviated, non-variant
                    existing_meaning = existing.get('meaning', '')
                    new_meaning = new_entry['meaning']

                    existing_is_bad = 'abbr.' in existing_meaning or 'variant of' in existing_meaning
                    new_is_good = 'abbr.' not in new_meaning and 'variant of' not in new_meaning

                    best_meaning = new_meaning if new_is_good else existing_meaning
                    best_meanings = new_entry['meanings'] if new_is_good else existing.get('meanings', [])
                    best_pinyin = new_entry['pinyin'] if new_is_good else existing.get('pinyin', '')
                    best_radical = new_entry.get('radical') or existing.get('radical', '')

                    # Merge into a single entry with best data from both
                    hsk_vocab[simplified] = {
                        'pinyin': best_pinyin,
                        'meaning': best_meaning,
                        'meanings': best_meanings,
                        'level_new': best_level_new,
                        'level_old': best_level_old,
                        'level': best_level,
                        'frequency': max(existing.get('frequency', 0), new_entry.get('frequency', 0)),
                        'radical': best_radical
                    }

                processed += 1

                # Track the lowest HSK level for each character in BOTH systems
                for char in simplified:
                    # Track new HSK level
                    if level_new:
                        level_new_num = int(level_new.replace('new-', '').replace('+', ''))
                        if char not in char_levels_new or level_new_num < char_levels_new[char]:
                            char_levels_new[char] = level_new_num

                    # Track old HSK level
                    if level_old:
                        level_old_num = int(level_old.replace('old-', ''))
                        if char not in char_levels_old or level_old_num < char_levels_old[char]:
                            char_levels_old[char] = level_old_num
        
        # Now add individual characters with their lowest HSK level from BOTH systems
        # Combine both character level dictionaries
        all_chars = set(char_levels_new.keys()) | set(char_levels_old.keys())

        for char in all_chars:
            if char not in hsk_vocab:
                char_pinyin_list = lazy_pinyin(char, style=Style.TONE)
                char_pinyin = ' '.join(char_pinyin_list)

                # Get levels from both systems if available
                level_new_num = char_levels_new.get(char)
                level_old_num = char_levels_old.get(char)

                char_level_new = f'new-{level_new_num}' if level_new_num else None
                char_level_old = f'old-{level_old_num}' if level_old_num else None

                # Primary level (prefer new)
                primary_level = char_level_new or char_level_old
                display_num = level_new_num or level_old_num

                hsk_vocab[char] = {
                    'pinyin': char_pinyin,
                    'meaning': f'(character, HSK {display_num})',
                    'meanings': [f'character component'],
                    'level': primary_level,
                    'level_new': char_level_new,
                    'level_old': char_level_old,
                    'frequency': 0
                }

        # Supplement missing levels from constituent characters
        # If a word is missing level_new or level_old, but all its characters have that level,
        # calculate it from the characters (same logic as compound words)
        supplemented_new = 0
        supplemented_old = 0

        for word, word_data in hsk_vocab.items():
            # Skip single characters and words that are character components
            if len(word) == 1 or word_data.get('meaning', '').startswith('(character'):
                continue

            chars = list(word)

            # Try to supplement missing level_new
            if not word_data.get('level_new'):
                char_levels_list = []
                all_chars_have_level = True

                for char in chars:
                    if char in hsk_vocab and hsk_vocab[char].get('level_new'):
                        level_str = hsk_vocab[char]['level_new'].replace('new-', '').replace('+', '')
                        try:
                            char_levels_list.append(int(level_str))
                        except:
                            all_chars_have_level = False
                            break
                    else:
                        all_chars_have_level = False
                        break

                if all_chars_have_level and char_levels_list:
                    max_level = max(char_levels_list)
                    word_data['level_new'] = f'new-{max_level}'
                    if not word_data.get('level'):
                        word_data['level'] = f'new-{max_level}'
                    supplemented_new += 1

            # Try to supplement missing level_old
            if not word_data.get('level_old'):
                char_levels_list = []
                all_chars_have_level = True

                for char in chars:
                    if char in hsk_vocab and hsk_vocab[char].get('level_old'):
                        level_str = hsk_vocab[char]['level_old'].replace('old-', '')
                        try:
                            char_levels_list.append(int(level_str))
                        except:
                            all_chars_have_level = False
                            break
                    else:
                        all_chars_have_level = False
                        break

                if all_chars_have_level and char_levels_list:
                    max_level = max(char_levels_list)
                    word_data['level_old'] = f'old-{max_level}'
                    supplemented_old += 1

        if supplemented_new > 0 or supplemented_old > 0:
            logger.info(f"Supplemented missing levels from characters: {supplemented_new} level_new, {supplemented_old} level_old")

        # Add radical_pinyin for all entries
        radical_pinyin_added = 0
        radical_from_mapping = 0
        for word, word_data in hsk_vocab.items():
            radical = word_data.get('radical', '')
            if radical:
                # First try to find radical in HSK vocabulary
                if radical in hsk_vocab:
                    word_data['radical_pinyin'] = hsk_vocab[radical].get('pinyin', '')
                    radical_pinyin_added += 1
                # Fall back to radical pinyin mapping
                elif radical in RADICAL_PINYIN:
                    word_data['radical_pinyin'] = RADICAL_PINYIN[radical]
                    radical_from_mapping += 1
                else:
                    word_data['radical_pinyin'] = ''
            else:
                word_data['radical_pinyin'] = ''

        if radical_pinyin_added > 0 or radical_from_mapping > 0:
            logger.info(f"Added radical pinyin: {radical_pinyin_added} from vocabulary, {radical_from_mapping} from mapping")

        # For multi-character words, combine radicals from all characters
        multi_char_radicals_updated = 0
        chars_missing_radicals = 0
        for word, word_data in hsk_vocab.items():
            if len(word) > 1:  # Multi-character word
                char_radicals = []
                char_radical_pinyins = []

                for char in word:
                    char_radical = ''
                    char_radical_pinyin = ''

                    # Try to get radical from character's vocabulary entry
                    if char in hsk_vocab:
                        char_data = hsk_vocab[char]
                        char_radical = char_data.get('radical', '')
                        char_radical_pinyin = char_data.get('radical_pinyin', '')

                    # If still no radical, try fallback character-to-radical mapping
                    if not char_radical and char in CHAR_TO_RADICAL:
                        char_radical = CHAR_TO_RADICAL[char]
                        # Get pinyin for this radical
                        if char_radical in RADICAL_PINYIN:
                            char_radical_pinyin = RADICAL_PINYIN[char_radical]

                    # If character has radical, add it to the list
                    if char_radical:
                        char_radicals.append(char_radical)
                        char_radical_pinyins.append(char_radical_pinyin if char_radical_pinyin else '')
                    else:
                        # Character is still missing radical data even after fallback
                        chars_missing_radicals += 1
                        logger.debug(f"Character '{char}' in word '{word}' is missing radical data (not in vocab or fallback)")

                # If we found at least one radical, combine them
                # Note: This might result in fewer radicals than characters if some are missing
                if char_radicals:
                    word_data['radical'] = ' + '.join(char_radicals)
                    word_data['radical_pinyin'] = ' + '.join(char_radical_pinyins)
                    multi_char_radicals_updated += 1

        if multi_char_radicals_updated > 0:
            logger.info(f"Updated radicals for {multi_char_radicals_updated} multi-character words")
        if chars_missing_radicals > 0:
            logger.warning(f"Found {chars_missing_radicals} characters missing radical data in multi-character words")

        # Save processed vocabulary
        vocab_file = DATA_DIR / "hsk_vocabulary.json"
        with open(vocab_file, 'w', encoding='utf-8') as f:
            json.dump(hsk_vocab, f, ensure_ascii=False, indent=2)

        # Backup processed vocabulary with timestamp
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            processed_backup_file = BACKUP_DIR / f"hsk_vocabulary_{today}.json"

            # Only create backup if one doesn't exist for today
            if not processed_backup_file.exists():
                with open(processed_backup_file, 'w', encoding='utf-8') as f:
                    json.dump(hsk_vocab, f, ensure_ascii=False, indent=2)
                logger.info(f"Processed vocabulary backup saved: {processed_backup_file.name}")
        except Exception as e:
            logger.warning(f"Failed to backup processed vocabulary (non-critical): {e}")

        total_chars = len(set(char_levels_new.keys()) | set(char_levels_old.keys()))
        logger.info(f"Processed and saved {processed} HSK words + {total_chars} individual characters")
        logger.info(f"Level distribution from source: {entries_with_both} with both, {entries_with_new_only} new only, {entries_with_old_only} old only (out of {total_entries} total entries)")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error downloading vocabulary: {e.response.status_code}", exc_info=True)
        raise
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.error(f"Network error downloading vocabulary: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error downloading vocabulary: {e}", exc_info=True)
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
            'translation_source': translation_result.get('source', TRANSLATION_SOURCE_MYMEMORY)
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
    char_levels_new = []
    char_levels_old = []
    char_meanings = []

    # Collect radicals from all characters (for compound words)
    char_radicals = []
    char_radical_pinyins = []

    # Check if all characters are in HSK and collect their levels
    for char in chars:
        if char in hsk_vocab:
            char_data = hsk_vocab[char]
            char_pinyins.append(char_data['pinyin'])
            char_meanings.append(char_data['meaning'])

            # Get radical from this character
            char_radical = char_data.get('radical', '')

            # If no radical in vocabulary, try fallback mapping
            if not char_radical and char in CHAR_TO_RADICAL:
                char_radical = CHAR_TO_RADICAL[char]

            if char_radical:
                char_radicals.append(char_radical)
                # Try to find pinyin for the radical
                if char_radical in hsk_vocab:
                    char_radical_pinyins.append(hsk_vocab[char_radical].get('pinyin', ''))
                elif char_radical in RADICAL_PINYIN:
                    char_radical_pinyins.append(RADICAL_PINYIN[char_radical])
                else:
                    char_radical_pinyins.append('')

            # Collect new HSK level
            level_new = char_data.get('level_new')
            if level_new:
                level_new_str = level_new.replace('new-', '').replace('+', '')
                try:
                    char_levels_new.append(int(level_new_str))
                except:
                    char_levels_new.append(1)

            # Collect old HSK level
            level_old = char_data.get('level_old')
            if level_old:
                level_old_str = level_old.replace('old-', '')
                try:
                    char_levels_old.append(int(level_old_str))
                except:
                    pass  # Character doesn't have old HSK level
        else:
            return None

    # Build pinyin from HSK characters
    compound_pinyin = ' '.join(char_pinyins)

    # Calculate compound levels from component characters
    # Use highest level from each HSK system
    compound_level_new = None
    compound_level_old = None

    if char_levels_new:
        max_new = max(char_levels_new)
        compound_level_new = f'new-{max_new}'

    if char_levels_old:
        max_old = max(char_levels_old)
        compound_level_old = f'old-{max_old}'

    # Primary level (prefer new HSK)
    compound_level = compound_level_new or compound_level_old or 'new-1'

    # Fallback meaning from characters
    fallback_meaning = ' + '.join(char_meanings)

    # Combine radicals from all characters
    compound_radical = ' + '.join(char_radicals) if char_radicals else ''
    compound_radical_pinyin = ' + '.join(char_radical_pinyins) if char_radical_pinyins else ''

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
            'level_new': compound_level_new,
            'level_old': compound_level_old,
            'frequency': 0,
            'translation_source': source,
            'radical': compound_radical,
            'radical_pinyin': compound_radical_pinyin
        }

    # If online lookup completely failed, use character meanings
    return {
        'pinyin': compound_pinyin,
        'meaning': fallback_meaning,
        'meanings': char_meanings,
        'level': compound_level,
        'level_new': compound_level_new,
        'level_old': compound_level_old,
        'frequency': 0,
        'translation_source': 'hsk-chars',
        'radical': compound_radical,
        'radical_pinyin': compound_radical_pinyin
    }

@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True
)
async def _call_translation_api(client: httpx.AsyncClient, url: str, method: str = 'POST', **kwargs) -> httpx.Response:
    """
    Make HTTP request with retry logic for network errors
    """
    if method.upper() == 'POST':
        response = await client.post(url, **kwargs)
    else:
        response = await client.get(url, **kwargs)
    response.raise_for_status()
    return response

async def get_translation_with_source(text: str) -> Optional[Dict]:
    """
    Get translation with multiple API support and source tracking
    Priority: DeepL > Google > MyMemory
    Includes automatic retry for network errors
    """
    # Check for API keys from environment
    deepl_key = os.getenv('DEEPL_API_KEY')
    google_key = os.getenv('GOOGLE_TRANSLATE_API_KEY')

    # Try DeepL first if available
    if deepl_key:
        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                url = "https://api-free.deepl.com/v2/translate"
                data = {
                    'auth_key': deepl_key,
                    'text': text,
                    'target_lang': 'EN',
                    'source_lang': 'ZH'
                }
                response = await _call_translation_api(client, url, method='POST', data=data)
                result = response.json()

                if result.get('translations'):
                    return {
                        'translation': result['translations'][0]['text'],
                        'source': TRANSLATION_SOURCE_DEEPL
                    }
        except httpx.HTTPStatusError as e:
            logger.warning(f"DeepL API error {e.response.status_code} for '{text}'")
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(f"DeepL API network error for '{text}': {e}")
        except Exception as e:
            logger.debug(f"DeepL API failed for '{text}': {e}")

    # Try Google Translate if available
    if google_key:
        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                url = f"https://translation.googleapis.com/language/translate/v2"
                params = {
                    'key': google_key,
                    'q': text,
                    'target': 'en',
                    'source': 'zh'
                }
                response = await _call_translation_api(client, url, method='POST', params=params)
                result = response.json()

                if result.get('data', {}).get('translations'):
                    return {
                        'translation': result['data']['translations'][0]['translatedText'],
                        'source': TRANSLATION_SOURCE_GOOGLE
                    }
        except httpx.HTTPStatusError as e:
            logger.warning(f"Google Translate API error {e.response.status_code} for '{text}'")
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(f"Google Translate API network error for '{text}': {e}")
        except Exception as e:
            logger.debug(f"Google Translate API failed for '{text}': {e}")

    # Fallback to free MyMemory API
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            url = f"https://api.mymemory.translated.net/get?q={text}&langpair=zh|en"
            response = await _call_translation_api(client, url, method='GET')
            result = response.json()

            if result.get('responseStatus') == 200:
                return {
                    'translation': result['responseData']['translatedText'],
                    'source': TRANSLATION_SOURCE_MYMEMORY
                }
    except httpx.HTTPStatusError as e:
        logger.warning(f"MyMemory API error {e.response.status_code} for '{text}'")
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.warning(f"MyMemory API network error for '{text}': {e}")
    except Exception as e:
        logger.debug(f"MyMemory API failed for '{text}': {e}")

    return None

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

    # Split by line breaks first to preserve them
    lines = text.split('\n')
    segments = []

    for i, line in enumerate(lines):
        if line.strip():  # Only process non-empty lines
            segments.extend(list(jieba.cut(line)))
        # Add line break marker between lines (but not after the last line)
        if i < len(lines) - 1:
            segments.append('\n')

    words = []
    hsk_stats_new = {f'hsk{i}': 0 for i in range(1, 10)}
    hsk_stats_old = {f'hsk{i}': 0 for i in range(1, 7)}  # Old HSK only has 6 levels
    total_hsk_words_new = 0
    total_hsk_words_old = 0

    for segment in segments:
        # Handle line breaks specially
        if segment == '\n':
            word_info = WordInfo(
                text='\n',
                is_hsk=False,
                hsk_level='',
                pinyin='',
                meaning='',
                meanings=[],
                frequency=0,
                translation_source='linebreak'
            )
            words.append(word_info)
            continue

        word_info = WordInfo(text=segment)

        vocab_entry = get_word_info(segment)
        if vocab_entry:
            vocab_entry = hsk_vocab[segment]
            word_info.hsk_level = vocab_entry['level']
            word_info.level_new = vocab_entry.get('level_new')
            word_info.level_old = vocab_entry.get('level_old')
            word_info.pinyin = vocab_entry['pinyin']
            word_info.meaning = vocab_entry['meaning']
            word_info.meanings = vocab_entry['meanings']
            word_info.frequency = vocab_entry['frequency']
            word_info.is_hsk = True
            word_info.translation_source = TRANSLATION_SOURCE_HSK  # Mark as HSK vocabulary
            word_info.radical = vocab_entry.get('radical', '')
            word_info.radical_pinyin = vocab_entry.get('radical_pinyin', '')

            # Track statistics for BOTH HSK systems
            level_new = vocab_entry.get('level_new')
            if level_new:
                level_new_num = level_new.replace('new-', '').replace('+', '')
                try:
                    level_key = f'hsk{int(level_new_num)}'
                    if level_key in hsk_stats_new:
                        hsk_stats_new[level_key] += 1
                    total_hsk_words_new += 1
                except ValueError:
                    pass

            level_old = vocab_entry.get('level_old')
            if level_old:
                level_old_num = level_old.replace('old-', '')
                try:
                    level_key = f'hsk{int(level_old_num)}'
                    if level_key in hsk_stats_old:
                        hsk_stats_old[level_key] += 1
                    total_hsk_words_old += 1
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
                    word_info.level_new = compound_info.get('level_new')
                    word_info.level_old = compound_info.get('level_old')
                    word_info.pinyin = compound_info['pinyin']
                    word_info.meaning = compound_info['meaning']
                    word_info.meanings = compound_info['meanings']
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    word_info.translation_source = compound_info.get('translation_source')
                    word_info.radical = compound_info.get('radical', '')
                    word_info.radical_pinyin = compound_info.get('radical_pinyin', '')

                    # Track compound word in statistics for BOTH HSK systems
                    level_new = compound_info.get('level_new')
                    if level_new:
                        level_new_num = level_new.replace('new-', '').replace('+', '')
                        try:
                            level_key = f'hsk{int(level_new_num)}'
                            if level_key in hsk_stats_new:
                                hsk_stats_new[level_key] += 1
                            total_hsk_words_new += 1
                        except ValueError:
                            pass

                    level_old = compound_info.get('level_old')
                    if level_old:
                        level_old_num = level_old.replace('old-', '')
                        try:
                            level_key = f'hsk{int(level_old_num)}'
                            if level_key in hsk_stats_old:
                                hsk_stats_old[level_key] += 1
                            total_hsk_words_old += 1
                        except ValueError:
                            pass
            else:
                # Not an HSK compound - do online lookup for everything
                online_info = await lookup_unknown_word(segment)
                if online_info:
                    word_info.hsk_level = 'unknown'
                    word_info.level_new = None
                    word_info.level_old = None
                    word_info.pinyin = online_info['pinyin']
                    word_info.meaning = online_info['meaning']
                    word_info.meanings = online_info['meanings']
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    word_info.translation_source = online_info.get('translation_source')

        words.append(word_info.dict())

    # Calculate estimated level for BOTH HSK systems
    estimated_level_new = estimate_text_level(hsk_stats_new, total_hsk_words_new)
    estimated_level_old = estimate_text_level(hsk_stats_old, total_hsk_words_old)

    return {
        'words': words,
        'statistics': {
            'total_characters': len(text),
            'total_words': len(segments),
            # New HSK statistics
            'hsk_words_new': total_hsk_words_new,
            'hsk_distribution_new': hsk_stats_new,
            'estimated_level_new': estimated_level_new,
            # Old HSK statistics
            'hsk_words_old': total_hsk_words_old,
            'hsk_distribution_old': hsk_stats_old,
            'estimated_level_old': estimated_level_old,
            # Legacy fields (for backwards compatibility, use new HSK)
            'hsk_words': total_hsk_words_new,
            'hsk_distribution': hsk_stats_new,
            'estimated_level': estimated_level_new
        }
    }

def estimate_text_level(hsk_stats: Dict, total_hsk_words: int) -> str:
    """
    Estimate text difficulty based on HSK word distribution

    Args:
        hsk_stats: Dictionary with HSK level counts
        total_hsk_words: Total number of HSK words in text

    Returns:
        Estimated HSK level as string (e.g., "HSK 3" or "HSK 9+")
    """
    if total_hsk_words == 0:
        return "Unknown"

    # Calculate cumulative percentage approach
    # Text level = highest level where you'd understand TEXT_LEVEL_THRESHOLD% of words
    cumulative_words = 0

    for level in range(1, 10):
        cumulative_words += hsk_stats.get(f'hsk{level}', 0)
        percentage = (cumulative_words / total_hsk_words) * 100

        # If you know up to this level and understand TEXT_LEVEL_THRESHOLD% of words
        if percentage >= TEXT_LEVEL_THRESHOLD:
            return f"HSK {level}"

    # If even HSK 9 doesn't cover TEXT_LEVEL_THRESHOLD%, it's beyond HSK
    return "HSK 9+"

def migrate_word_data(word_data: Dict) -> Dict:
    """
    Migrate old word data format to new dual HSK system format.

    Old format: { "hsk_level": "new-3", ... }
    New format: { "hsk_level": "new-3", "level_new": "new-3", "level_old": "old-2", ... }

    Args:
        word_data: Word data dictionary (may be old or new format)

    Returns:
        Migrated word data with level_new and level_old fields
    """
    # Check if already migrated (has level_new or level_old)
    if 'level_new' in word_data or 'level_old' in word_data:
        return word_data

    # Get the old hsk_level value
    old_level = word_data.get('hsk_level') or word_data.get('level')

    # If no level at all, return as-is
    if not old_level:
        return word_data

    # Try to look up the word in current vocabulary to get both levels
    word_text = word_data.get('text') or word_data.get('word')
    if word_text and word_text in hsk_vocab:
        vocab_entry = hsk_vocab[word_text]
        word_data['level_new'] = vocab_entry.get('level_new')
        word_data['level_old'] = vocab_entry.get('level_old')
        # Update hsk_level to match current vocab
        word_data['hsk_level'] = vocab_entry.get('level')
    elif word_text and len(word_text) > 1:
        # For multi-character words not in vocabulary, try compound calculation
        # This handles words like "很多" that are created dynamically
        chars = list(word_text)
        if all(char in hsk_vocab for char in chars):
            # Calculate both levels from component characters
            char_levels_new = []
            char_levels_old = []

            for char in chars:
                char_data = hsk_vocab[char]

                level_new = char_data.get('level_new')
                if level_new:
                    try:
                        level_num = int(level_new.replace('new-', '').replace('+', ''))
                        char_levels_new.append(level_num)
                    except (ValueError, AttributeError):
                        pass

                level_old = char_data.get('level_old')
                if level_old:
                    try:
                        level_num = int(level_old.replace('old-', ''))
                        char_levels_old.append(level_num)
                    except (ValueError, AttributeError):
                        pass

            # Set both levels if we found character data
            if char_levels_new:
                word_data['level_new'] = f'new-{max(char_levels_new)}'
            else:
                word_data['level_new'] = None

            if char_levels_old:
                word_data['level_old'] = f'old-{max(char_levels_old)}'
            else:
                word_data['level_old'] = None

            # Update primary level
            if word_data['level_new']:
                word_data['hsk_level'] = word_data['level_new']
            elif word_data['level_old']:
                word_data['hsk_level'] = word_data['level_old']

            return word_data
        else:
            # Not all characters are in HSK, fall back to guessing
            if old_level.startswith('new-'):
                word_data['level_new'] = old_level
                word_data['level_old'] = None
            elif old_level.startswith('old-'):
                word_data['level_new'] = None
                word_data['level_old'] = old_level
            else:
                # Unknown format, assume it's new HSK
                word_data['level_new'] = old_level
                word_data['level_old'] = None
    else:
        # Word not in current vocab or no text field
        # Assume old_level is from new HSK system (most common case)
        if old_level.startswith('new-'):
            word_data['level_new'] = old_level
            word_data['level_old'] = None
        elif old_level.startswith('old-'):
            word_data['level_new'] = None
            word_data['level_old'] = old_level
        else:
            # Unknown format, assume it's new HSK
            word_data['level_new'] = old_level
            word_data['level_old'] = None

    return word_data

def migrate_analysis_data(analysis_data: Dict) -> Dict:
    """
    Migrate saved analysis data to new dual HSK system format.
    Recalculates statistics for both New and Old HSK systems.

    Args:
        analysis_data: Analysis data containing words array

    Returns:
        Migrated analysis data with updated statistics
    """
    if not analysis_data or 'words' not in analysis_data:
        return analysis_data

    # Migrate each word in the words array
    migrated_words = []
    for word in analysis_data['words']:
        migrated_word = migrate_word_data(word)
        migrated_words.append(migrated_word)

    analysis_data['words'] = migrated_words

    # Recalculate statistics for BOTH HSK systems from migrated words
    hsk_stats_new = {f'hsk{i}': 0 for i in range(1, 10)}
    hsk_stats_old = {f'hsk{i}': 0 for i in range(1, 7)}
    total_hsk_words_new = 0
    total_hsk_words_old = 0

    for word in migrated_words:
        # Skip non-HSK words (punctuation, line breaks, etc.)
        if not word.get('is_hsk'):
            continue

        # Count New HSK statistics
        level_new = word.get('level_new')
        if level_new:
            level_new_num = level_new.replace('new-', '').replace('+', '')
            try:
                level_key = f'hsk{int(level_new_num)}'
                if level_key in hsk_stats_new:
                    hsk_stats_new[level_key] += 1
                total_hsk_words_new += 1
            except ValueError:
                pass

        # Count Old HSK statistics
        level_old = word.get('level_old')
        if level_old:
            level_old_num = level_old.replace('old-', '')
            try:
                level_key = f'hsk{int(level_old_num)}'
                if level_key in hsk_stats_old:
                    hsk_stats_old[level_key] += 1
                total_hsk_words_old += 1
            except ValueError:
                pass

    # Estimate text level for both systems
    estimated_level_new = estimate_text_level(hsk_stats_new, total_hsk_words_new)
    estimated_level_old = estimate_text_level(hsk_stats_old, total_hsk_words_old)

    # Update statistics object with both HSK systems
    if 'statistics' not in analysis_data:
        analysis_data['statistics'] = {}

    stats = analysis_data['statistics']

    # New HSK statistics
    stats['hsk_words_new'] = total_hsk_words_new
    stats['hsk_distribution_new'] = hsk_stats_new
    stats['estimated_level_new'] = estimated_level_new

    # Old HSK statistics
    stats['hsk_words_old'] = total_hsk_words_old
    stats['hsk_distribution_old'] = hsk_stats_old
    stats['estimated_level_old'] = estimated_level_old

    # Legacy fields (for backwards compatibility, use new HSK)
    stats['hsk_words'] = total_hsk_words_new
    stats['hsk_distribution'] = hsk_stats_new
    stats['estimated_level'] = estimated_level_new

    return analysis_data

def migrate_vocabulary_sections(sections: List[Dict]) -> List[Dict]:
    """
    Migrate vocabulary list sections to new dual HSK system format.

    Args:
        sections: List of sections containing words

    Returns:
        Migrated sections
    """
    if not sections:
        return sections

    migrated_sections = []
    for section in sections:
        if 'words' in section and section['words']:
            migrated_words = []
            for word in section['words']:
                migrated_word = migrate_word_data(word)
                migrated_words.append(migrated_word)
            section['words'] = migrated_words
        migrated_sections.append(section)

    return migrated_sections

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
class SignupWithInviteRequest(BaseModel):
    token: str
    username: str
    password: str

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

class UpdateInviteQuotaRequest(BaseModel):
    invite_quota: int

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
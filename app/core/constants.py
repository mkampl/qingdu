"""
Application constants and configuration values
"""

# Rate Limiting
ANALYZE_RATE_LIMIT = "30/minute"
TRANSLATE_RATE_LIMIT = "20/minute"
AUTH_RATE_LIMIT = "5/minute"

# Cache Configuration
TRANSLATION_CACHE_SIZE = 5000
TRANSLATION_CACHE_TTL = 3600  # 1 hour in seconds
UNKNOWN_WORD_CACHE_SIZE = 2000
UNKNOWN_WORD_CACHE_TTL = 1800  # 30 minutes in seconds

# HSK Configuration
HSK_WORD_BASE_FREQ = 10000
HSK_MIN_LEVEL = 1
HSK_MAX_LEVEL = 9

# API Configuration
API_TIMEOUT = 5.0  # seconds
HSK_DOWNLOAD_TIMEOUT = 30.0  # seconds

# Retry Configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_MIN_WAIT = 1  # seconds
RETRY_MAX_WAIT = 5  # seconds
HSK_RETRY_MIN_WAIT = 2  # seconds
HSK_RETRY_MAX_WAIT = 10  # seconds

# Text Analysis
TEXT_LEVEL_THRESHOLD = 80  # percentage for level estimation

# Authentication
TOKEN_EXPIRE_DAYS = 30
MIN_PASSWORD_LENGTH = 8

# Translation API Sources
TRANSLATION_SOURCE_DEEPL = "deepl"
TRANSLATION_SOURCE_GOOGLE = "google"
TRANSLATION_SOURCE_MYMEMORY = "mymemory"
TRANSLATION_SOURCE_HSK = "hsk"
TRANSLATION_SOURCE_HSK_CHARS = "hsk-chars"
TRANSLATION_SOURCE_CACHE = "cache"

# HSK Vocabulary
HSK_VOCAB_URL = "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/refs/heads/main/complete.json"

# CC-CEDICT — the primary Chinese-English dictionary source we layer on
# top of the HSK list. Format: `traditional simplified [pinyin] /m1/m2/.../`.
# License: CC-BY-SA 4.0. Distributed as a single gzip-compressed UTF-8
# text file (~4 MB compressed, ~9 MB unpacked, ~120k entries). Refreshed
# weekly upstream; we cache the decompressed .u8 locally and re-fetch
# if it ages beyond CEDICT_REFRESH_DAYS.
CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
CEDICT_REFRESH_DAYS = 7
CEDICT_SOURCE_TAG = "cc-cedict"

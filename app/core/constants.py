"""
Application constants and configuration values
"""

# Rate Limiting
ANALYZE_RATE_LIMIT = "30/minute"
TRANSLATE_RATE_LIMIT = "20/minute"
AUTH_RATE_LIMIT = "5/minute"

# Input caps. Analyze has to take whatever the importers produce (URL and
# document extraction stop at 50k chars), translate and sentence TTS only
# ever see one sentence or paragraph at a time.
MAX_ANALYZE_CHARS = 60_000
MAX_TRANSLATE_CHARS = 5_000
MAX_TTS_CHARS = 2_000

# Cache Configuration
TRANSLATION_CACHE_SIZE = 5000
TRANSLATION_CACHE_TTL = 3600  # 1 hour in seconds

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
TRANSLATION_SOURCE_LLM = "llm"
TRANSLATION_SOURCE_HSK = "hsk"
TRANSLATION_SOURCE_HSK_CHARS = "hsk-chars"
TRANSLATION_SOURCE_CEDICT = "cedict"
# Not a dictionary word: no meaning, only its dictionary parts.
TRANSLATION_SOURCE_PARTS = "parts"
TRANSLATION_SOURCE_CACHE = "cache"

# HSK Vocabulary (drkameleon/complete-hsk-vocabulary, MIT). The file the
# app loads is vendored under app/data/dict/ at the commit recorded in
# VERSION.json; this template is only used by tools/refresh_dictionaries.py
# and by the startup fallback when the vendored copy is missing.
HSK_VOCAB_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/{ref}/complete.json"
)

# CC-CEDICT — the primary Chinese-English dictionary source we layer on
# top of the HSK list. Format: `traditional simplified [pinyin] /m1/m2/.../`.
# License: CC-BY-SA 4.0. mdbg publishes only a moving "latest" export, so
# a reviewed snapshot is vendored under app/data/dict/ (see VERSION.json)
# and replaced by hand with tools/refresh_dictionaries.py. The URL is used
# by that tool and as a last-resort startup fallback.
CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
CEDICT_SOURCE_TAG = "cc-cedict"

# Bump whenever the code that picks a word's reading or headline gloss
# changes (cedict_loader scoring, word_info resolution, learner glosses).
# It is part of the dictionary version, so the next startup refreshes the
# pinyin/meaning snapshots on users' words once.
GLOSS_RULES_VERSION = 4

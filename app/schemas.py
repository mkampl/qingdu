from pydantic import BaseModel


class TextAnalysisRequest(BaseModel):
    text: str


class TranslationRequest(BaseModel):
    text: str
    target_lang: str = "en"


class WordInfo(BaseModel):
    text: str
    hsk_level: str | None = None
    level_new: str | None = None
    level_old: str | None = None
    pinyin: str | None = None
    meaning: str | None = None
    meanings: list[str] | None = None
    frequency: int | None = None
    is_hsk: bool = False
    translation_source: str | None = None
    radical: str | None = None
    radical_pinyin: str | None = None
    # Per-user state ('learning' | 'known' | 'ignored'). None = 'new' or
    # request was anonymous. Populated by the analyze router when there's
    # an authenticated user.
    user_state: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class SignupWithInviteRequest(BaseModel):
    token: str
    username: str
    password: str


class UpdateInviteQuotaRequest(BaseModel):
    invite_quota: int


# --- User word state (Phase A) ---

VALID_WORD_STATES = frozenset({"learning", "known", "ignored"})


class WordStateUpdate(BaseModel):
    word: str
    state: str  # 'learning' | 'known' | 'ignored'
    source_text_id: int | None = None


class BulkMarkKnownRequest(BaseModel):
    words: list[str]
    source_text_id: int | None = None

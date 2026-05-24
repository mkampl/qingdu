from pydantic import BaseModel


class TextAnalysisRequest(BaseModel):
    text: str
    # Phase #99 — optional glossary picker.
    # None / omitted -> use all the user's glossary-flagged vocabulary lists.
    # []             -> explicitly use no glossary (even if lists are flagged).
    # [3, 5]         -> use only those lists.
    glossary_list_ids: list[int] | None = None


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
    # Phase #99 — name of the glossary list this word's meaning came from,
    # when `translation_source == "glossary"`. The popover surfaces this.
    glossary_source: str | None = None


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


class ImportHskRequest(BaseModel):
    """Bulk-mark every HSK word at level <= up_to_level as known."""

    up_to_level: int  # 1-9 for new HSK, 1-6 for old HSK
    hsk_version: str = "new"  # 'new' | 'old'

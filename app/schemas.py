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
    # Phase #100 — name of the pre-analyzed package this word came from,
    # when `translation_source == "package"`. Lets the user attribute
    # contextual meanings to the right LLM / curator. Optional `notes`
    # carries any free-form annotation the package author provided.
    package_source: str | None = None
    notes: str | None = None


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


# --- Pre-analyzed package import (Phase #100) ----------------------------


class PackageToken(BaseModel):
    """
    One unit of text in a pre-analyzed Qingdu package. Non-punctuation
    tokens must carry `pinyin` and `meaning` so the reader has something
    to display; punctuation tokens (`is_punct: true`) pass through
    unchanged and only need `text`.
    """

    text: str
    is_punct: bool = False
    pinyin: str | None = None
    meaning: str | None = None
    meanings: list[str] | None = None
    notes: str | None = None


class QingduPackage(BaseModel):
    """
    A pre-analyzed text package — the input format for /api/import/package.

    Designed to be produced by an LLM (or curated by hand) so users can
    import specialised corpora (Daoist, Buddhist, Classical Chinese, legal,
    medical) where jieba's segmentation and DeepL/Google's translation
    perform poorly. The same character may appear multiple times with
    different meanings — that contextual disambiguation is the headline
    value vs an in-app jieba pass.
    """

    qingdu_package_version: str = "1"
    title: str | None = None
    byline: str | None = None
    # Human-readable identifier for the package author / LLM ("my-daoist-llm-v3",
    # "Wang-Bi-edition", "Lin-Yutang-1955"). Surfaced in the reader so users
    # can attribute meanings to the right source.
    source: str | None = None
    # IETF / ISO language tag hint. "lzh" = Literary Chinese, "zho" = Modern.
    # Optional — informs which downstream defaults to choose, not a guard.
    language_hint: str | None = None
    text: str
    tokens: list[PackageToken]
    # Optional sentence-level pre-translations. Keys are the exact text of
    # the sentence; values are the translation. Used to seed the translation
    # cache so the user gets instant results when they tap a sentence.
    sentence_translations: dict[str, str] | None = None

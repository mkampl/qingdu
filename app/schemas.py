from pydantic import BaseModel, Field


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
    # Register tags stripped off the dictionary headline ("bound form",
    # "coll." ...), shown as a small badge next to `meaning`.
    meaning_tags: list[str] | None = None
    # All dictionary readings of a polyphone, main one first:
    # [{pinyin, primary, meanings, meaning_tags, is_main, example}].
    # None when the word has a single reading.
    readings: list[dict] | None = None
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
    # Set only for tokens that are not dictionary words: the dictionary
    # words they are made of, [{word, pinyin, meaning}]. Such a token has
    # no meaning of its own and cannot be saved as a user word.
    parts: list[dict] | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    """Self-service account deletion — password re-entry required so a
    left-open session can't nuke the account."""

    password: str


class SignupWithInviteRequest(BaseModel):
    token: str
    username: str
    password: str


class UpdateInviteQuotaRequest(BaseModel):
    invite_quota: int


class OpenRegisterRequest(BaseModel):
    """Phase 2.7 — payload for `POST /api/auth/register` (open registration).
    The captcha pair is required when the instance has captcha enabled; the
    server treats a missing pair as a failed captcha when it's required."""

    username: str
    password: str
    captcha_token: str | None = None
    captcha_answer: int | str | None = None
    # Honeypot — a hidden field that real users never see. Bots fill every
    # input they find. Any non-empty value here → silent reject.
    honeypot: str | None = None


class RegistrationSettingsUpdate(BaseModel):
    """Partial update of the instance-wide registration / lifecycle config.
    Admin-only. Unknown keys are ignored by the service layer."""

    registration_open: bool | None = None
    registration_per_ip_24h: int | None = None
    registration_daily_cap: int | None = None
    registration_captcha: bool | None = None
    lifecycle_soft_delete_days: int | None = None
    lifecycle_hard_delete_days: int | None = None


class UserSettingsUpdate(BaseModel):
    """Partial update of the current user's tunable settings.

    All fields are optional — callers may send any subset. The auth
    router rejects invalid values via simple range checks (see PATCH
    /api/auth/me/settings).
    """

    daily_new_words: int | None = None  # 0..30 enforced server-side
    hsk_focus_version: str | None = None  # "new" | "old"
    display_script: str | None = None  # "auto" | "simp" | "trad"
    review_retention: float | None = None  # 0.85..0.97 enforced server-side
    review_window: str | None = None  # "now" | "today" | "tomorrow"
    review_focus: str | None = None  # "both" | "reading" | "writing"
    timezone: str | None = None  # IANA name, e.g. "Europe/Vienna"
    # Reader/review preferences (services/ui_settings); merged key by key,
    # unknown keys and invalid values are dropped.
    ui_settings: dict | None = None


# --- User word state (Phase A) ---

VALID_WORD_STATES = frozenset({"learning", "known", "ignored"})


class WordStateUpdate(BaseModel):
    word: str
    state: str  # 'learning' | 'known' | 'ignored'
    source_text_id: int | None = None
    # Phase #100 follow-up — optional package-curated snapshot. Only sent
    # by the reader when the clicked word came from a pre-analyzed JSON
    # package (translation_source === "package"). Backend stamps these
    # onto UserWord and marks meaning_source = "package" so the gloss
    # the user actually read survives into the SRS queue. Omitting them
    # (the normal HSK / CC-CEDICT / pypinyin path) leaves today's
    # behaviour unchanged — backend falls through to the dictionary
    # lookup chain in lookup_pinyin_meaning().
    meaning: str | None = None
    pinyin: str | None = None
    translation_source: str | None = None
    # Phase #120 — the package name (e.g. "dao_de_jing_ch1") that owns
    # this gloss. Used as the source_tag on the resulting user_word_glosses
    # row so the UI can show "[Dao De Jing]" next to that meaning.
    package_source: str | None = None
    # The sentence the word was met in, and the library text it came from
    # (saved texts are named by source_text_id). Kept as the word's sample
    # sentence when it has none yet.
    sentence: str | None = Field(None, max_length=1000)
    library_slug: str | None = Field(None, max_length=120)


class WordSnapshot(BaseModel):
    """One package-sourced snapshot for the bulk endpoint — same fields
    as the per-word path above, keyed by surface form in the request."""

    meaning: str | None = None
    pinyin: str | None = None
    translation_source: str | None = None
    package_source: str | None = None  # Phase #120 — see WordStateUpdate


class BulkMarkKnownRequest(BaseModel):
    words: list[str]
    source_text_id: int | None = None
    # Optional per-word package snapshots. Keys are the exact surface
    # forms the caller is marking known; values follow the same
    # "only when sourced from a package" rule as WordStateUpdate. The
    # SPA's complete-section action can build this from analysisData
    # before posting so curated meanings make it into the SRS pool.
    snapshots: dict[str, WordSnapshot] | None = None


class SnoozeRequest(BaseModel):
    """Push a word's due date back by `days` (default 3)."""

    word: str = Field(min_length=1)
    days: int = Field(3, ge=1, le=365)


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

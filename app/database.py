from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    must_change_password = Column(Boolean, default=True)
    last_active = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    invite_quota = Column(Integer, default=5)  # How many invites this user can send
    # Phase F2 — daily activity streak. `streak_last_active` is the date (UTC)
    # of the most recent qualifying action; `streak_count` is the length of
    # the contiguous run leading up to that date.
    streak_count = Column(Integer, default=0)
    streak_last_active = Column(Date, nullable=True)
    # Phase F3 — streak freezes. Earned automatically (see streak.py), not
    # purchasable — this app has no payment rails. Banked count; consumed
    # one-per-missed-day to bridge a gap instead of resetting the streak.
    streak_freeze_count = Column(Integer, default=0)
    # Phase #96 — systematic learning. Daily target of new HSK words to
    # auto-enroll into the 'learning' pool; pulled from `hsk_focus_version`'s
    # list in (level, random-within-level) order. 0 disables the auto-enroll
    # (the default — new users opt in via Settings).
    daily_new_words = Column(Integer, default=0)
    hsk_focus_version = Column(String(8), default="new")
    # Phase #96 follow-up — global script preference. 'auto' leaves text
    # alone, 'simp' coerces every Chinese surface to Simplified, 'trad'
    # to Traditional. Applied server-side at every endpoint that returns
    # Chinese text (review queue, analyze, saved texts, vocab lists).
    display_script = Column(String(8), default="auto")
    # Phase #117 — FSRS retention target. 0.90 was the original default and
    # matches AnkiDroid FSRS but lands hard-feeling early intervals (review
    # 3 → 10d, review 4 → 40d). 0.95 lines up much better with classic
    # Anki SM-2 (which most users carry as their intuition baseline) at
    # the cost of slightly more reviews per word. Range 0.85-0.97 is what
    # the FSRS authors call "the meaningful tuning band"; outside that the
    # scheduler stops behaving usefully.
    review_retention = Column(Float, default=0.95)
    # Phase #119 — look-ahead window for the review queue. People review
    # roughly once a day, not every 30 minutes, so "due now" alone leaves
    # half of today's batch on the table. The setting widens the cutoff:
    #   'now'      → due_at <= now (strict, the original FSRS-conformant
    #                pull; for users who really do review every hour)
    #   'today'    → due_at < midnight tomorrow (the new default — covers
    #                the typical once-a-day session without waiting for
    #                each card to flip due during the session)
    #   'tomorrow' → due_at < midnight day-after-tomorrow (pre-pull for
    #                "I won't be around tomorrow")
    review_window = Column(String(16), default="today")
    # Which skill the mixed review trains between the intro and the produce
    # stage: "both" (read, then write), "reading" or "writing".
    review_focus = Column(String(16), default="both")
    # IANA zone name ("Europe/Vienna"). Day boundaries for streaks, due
    # today, reviewed today, auto-enrol and the sparkline follow it
    # (services.localday). NULL until the SPA sends the browser's zone;
    # treated as UTC meanwhile.
    timezone = Column(String(64), nullable=True)
    # Reader and review preferences the SPA keeps per account (JSON; see
    # services/ui_settings), so every device shows the same. NULL until
    # the first device sends its own.
    ui_settings = Column(Text, nullable=True)
    # Phase 2.7 — account lifecycle. `active` is the default; the lifecycle
    # scheduler flips dormant accounts to `dormant` and (after the hard
    # threshold) hard-deletes them. Self-hosters can disable the whole
    # mechanism via system_settings; defaults below leave it off.
    account_status = Column(String(16), default="active")
    # Embedded as the `tv` claim in every session JWT. Bumping it (password
    # change, admin reset) invalidates all tokens issued before.
    token_version = Column(Integer, default=0, nullable=False, server_default="0")

    # Relationships
    texts = relationship("SavedText", back_populates="user", cascade="all, delete-orphan")
    vocabulary_lists = relationship(
        "VocabularyList", back_populates="user", cascade="all, delete-orphan"
    )
    user_words = relationship("UserWord", back_populates="user", cascade="all, delete-orphan")
    # cascade is load-bearing: created_by_user_id is NOT NULL, so without it
    # SQLAlchemy tries to null the FK on user delete and the whole delete
    # rolls back with an IntegrityError — which silently broke both the admin
    # delete button and the lifecycle hard-delete sweep for any user who had
    # ever created an invitation. Claimed invitations *by* the user are fine:
    # claimed_by_user_id is nullable and gets SET NULL.
    created_invitations = relationship(
        "InvitationToken",
        foreign_keys="InvitationToken.created_by_user_id",
        back_populates="creator",
        cascade="all, delete-orphan",
    )
    claimed_invitation = relationship(
        "InvitationToken",
        foreign_keys="InvitationToken.claimed_by_user_id",
        back_populates="claimer",
        uselist=False,
    )


class SavedText(Base):
    __tablename__ = "saved_texts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(500))
    content = Column(Text)
    tags = Column(Text, nullable=True)
    reading_progress = Column(Integer, default=0)  # 0-100%
    analysis_data = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Phase G3 — public sharing. NULL means "not shared"; a UUID4 means
    # the text is reachable via /api/share/{token}. Revoking is a SET NULL.
    share_token = Column(String(36), unique=True, nullable=True, index=True)
    # Phase #99 — per-text override of which glossaries apply at re-analyze
    # time. JSON array of int IDs. NULL means "use all the user's
    # glossary-flagged lists" (the default).
    glossary_list_ids = Column(Text, nullable=True)
    # Folder the text lives in (text_folders); NULL = top level. Inside a
    # folder the texts are read in `position` order (NULLs after, by date).
    folder_id = Column(Integer, ForeignKey("text_folders.id"), nullable=True, index=True)
    position = Column(Integer, nullable=True)
    # Comprehension questions the LLM wrote for the text (services/text_quiz),
    # JSON with the answer key; never sent to the browser as is.
    quiz = Column(Text, nullable=True)

    user = relationship("User", back_populates="texts")


class GrammarProgress(Base):
    """How the user is doing with one grammar pattern (services/grammar_book):
    a box that a good practice round raises, and when it is due again."""

    __tablename__ = "grammar_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "pattern_id", name="uq_grammar_progress_user_pattern"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pattern_id = Column(String(64), nullable=False)
    box = Column(Integer, nullable=False, default=0)
    due_at = Column(DateTime, nullable=True)
    last_at = Column(DateTime, nullable=True)
    correct = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)


class TextSeries(Base):
    """A topic series (services/text_series): a folder of texts the LLM
    writes one after another on one topic, each building on the last and
    bringing about `new_words` words the user doesn't know yet."""

    __tablename__ = "text_series"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    folder_id = Column(Integer, ForeignKey("text_folders.id"), nullable=False)
    topic = Column(String(200), nullable=False)
    level = Column(Integer, nullable=False, default=3)  # HSK 1-6, 7 = 7-9
    new_words = Column(Integer, nullable=False, default=10)
    length = Column(String(10), nullable=False, default="medium")
    generating_since = Column(DateTime, nullable=True)
    last_error = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GrammarSentenceTag(Base):
    """Grammar points the LLM found in one sentence (services/grammar_tagging),
    shared by everyone who reads it; re-done when the catalog changes."""

    __tablename__ = "grammar_sentence_tags"

    sentence_hash = Column(String(40), primary_key=True)
    catalog_version = Column(Integer, nullable=False, default=0)
    tags = Column(Text, nullable=False, default="[]")
    model = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LlmUsage(Base):
    """LLM requests a user made on one day (services/llm daily limit)."""

    __tablename__ = "llm_usage"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_llm_usage_user_day"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    day = Column(Date, nullable=False)
    count = Column(Integer, nullable=False, default=0)


class TextFolder(Base):
    """A folder of saved texts. Folders nest (`parent_id`, NULL = top
    level); a text lives in at most one folder."""

    __tablename__ = "text_folders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    parent_id = Column(Integer, ForeignKey("text_folders.id"), nullable=True)
    position = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class VocabularyList(Base):
    __tablename__ = "vocabulary_lists"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255))
    list_type = Column(String(50))  # 'hsk', 'auto', 'custom'
    sections = Column(Text)  # JSON string
    anki_deck_id = Column(Integer, nullable=True)
    # Phase #99 — when true, this list's entries override HSK lookup during
    # /api/analyze. Used for specialized corpora (Daoist, Buddhist, jargon)
    # where the default meanings don't fit.
    apply_as_glossary = Column(Boolean, default=False)
    # Dictionary version (dict_data.dict_version) the words' pinyin and
    # meanings were last refreshed against; see services/gloss_refresh.
    dict_version = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="vocabulary_lists")


class UserLibraryProgress(Base):
    """Per-user completion state for a bundled library text (app/data/library).

    Absence of a row means "not started". `status` is 'read' (self-reported
    via the Mark as read button) or 'quiz' (all questions answered correctly
    in one sitting). A quiz pass is never downgraded back to 'read' by a
    later manual mark — quiz is the stronger signal.
    """

    __tablename__ = "user_library_progress"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    slug = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False)  # 'read' | 'quiz'
    score = Column(Integer, nullable=True)  # correct-answer count, quiz only
    completed_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_user_library_progress"),)


class ApiToken(Base):
    """Personal access token for external integrations — Phase #121, e.g. a
    speech/LLM companion app that wants to read a user's known words and
    report newly-encountered vocabulary back (see app/routers/external.py).

    Separate from the JWT session auth in app/auth.py: these are
    long-lived, user-issued, scope-limited, and revocable without touching
    the user's password or logging out their browser session. Token
    management itself (create/list/revoke) is JWT-session-only — a leaked
    PAT must never be able to mint more tokens or revoke the others.

    Only the hash is stored; the raw token is shown once at creation and
    never persisted or logged. `token_prefix` (first chars of the raw
    token) lets the owner recognise a token in the list UI without it
    being reconstructable. `scopes` is a space-separated string drawn from
    the fixed set in app/auth.py:API_TOKEN_SCOPES.
    """

    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(64), nullable=False)
    token_hash = Column(String(128), nullable=False, unique=True)
    token_prefix = Column(String(16), nullable=False)
    scopes = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User")

    __table_args__ = (Index("ix_api_tokens_user", "user_id"),)


class UserWord(Base):
    """
    Per-user state for a Chinese word. Absence of a row means 'new' (the user
    has never interacted with this word). Rows are created lazily — typically
    the first time a user clicks on a word or bulk-marks a section known.

    SRS columns (ease, due_at, last_reviewed_at) are reserved for Phase B and
    left at their defaults until the review loop is wired up; carrying them
    here from the start avoids a migration when Phase B lands.
    """

    __tablename__ = "user_words"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    word = Column(String(64), nullable=False)
    # 'learning' | 'known' | 'ignored' — 'new' is absence-of-row.
    state = Column(String(16), nullable=False, default="learning")
    seen_count = Column(Integer, default=1)
    # Phase #96 — snapshot of the word's pinyin and meaning at insert time.
    # /api/review/queue serves these directly so reviews always have a
    # gloss, even for compounds and Dao-De-Jing-style imports whose
    # translations are not in the upstream HSK list.
    pinyin = Column(String(128), nullable=True)
    meaning = Column(Text, nullable=True)
    # Phase #100 follow-up — provenance of the pinyin/meaning snapshot above.
    # NULL on legacy rows (pre-this-column); "dictionary" when the snapshot
    # came from lookup_pinyin_meaning() (HSK / CC-CEDICT / compound /
    # pypinyin); "package" when the caller passed a curated meaning from a
    # pre-analyzed JSON package (e.g. the bundled Dao De Jing). Once a row
    # is stamped "package", subsequent clicks from any other package or
    # the dictionary chain do NOT overwrite the meaning — first-package
    # wins to keep SRS reviews stable.
    meaning_source = Column(String(32), nullable=True)
    # Phase B remainder (cloze mode) — a sample sentence from one of the
    # user's saved texts containing this word. Populated lazily when the
    # row enters the /api/review/queue?mode=cloze pool. NULL means we
    # haven't found a containing sentence yet (or the user has no saved
    # text with this word — that's fine, the card just skips cloze).
    sample_sentence = Column(Text, nullable=True)
    # Where sample_sentence came from: a saved text's or library text's
    # title. NULL for sentences from unsaved reading or older rows.
    sample_source = Column(String(160), nullable=True)
    # SM-2-style ease * 100. Legacy; FSRS uses stability/difficulty below.
    ease = Column(Integer, default=250)
    # FSRS-4.5 state. `fsrs_state` carries the full Card JSON for round-tripping
    # (state machine + step + last_review timestamps). `stability` / `difficulty`
    # / `due_at` mirror the same numbers so we can SELECT for "due now" without
    # decoding every row's JSON.
    stability = Column(Float, nullable=True)
    difficulty = Column(Float, nullable=True)
    fsrs_state = Column(Text, nullable=True)
    due_at = Column(DateTime, nullable=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    # Phase 1.3 — Mixed-mode review cycle tracking. `modes_completed` is a
    # JSON list of mode names already graded `Good` or better in the
    # current cycle (e.g. ["recognition", "cloze"]); FSRS only advances
    # once all four mode names are present. Any failing grade clears the
    # list so the next attempt re-starts the cycle. `modes_cycle_started_at`
    # stamps the first grade of a cycle for analytics; it's NULL until a
    # mixed-mode cycle is in flight.
    modes_completed = Column(Text, nullable=False, default="[]")
    modes_cycle_started_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="user_words")

    glosses = relationship(
        "UserWordGloss",
        back_populates="user_word",
        cascade="all, delete-orphan",
        order_by="UserWordGloss.created_at",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "word", name="uq_user_word"),
        Index("ix_user_words_user_state", "user_id", "state"),
        # Hot path: "what's due right now for user X" — used by /api/review/queue.
        Index("ix_user_words_user_due", "user_id", "due_at"),
    )


class UserWordGloss(Base):
    """Phase #120 — one of possibly many glosses for the same user-word.

    Lets a daoist 道 carry both the CEDICT primary ("the way; path;
    principle") AND the Dao-De-Jing package gloss ("Tao — the source")
    side by side on the same SRS card, so review shows both with their
    provenance tag and the reader popover surfaces the right one for
    the active text without having to choose one as the canonical.

    Provenance:
    - source='dictionary': the CEDICT / HSK / compound chain lookup at
      the time of insertion. Refreshed by snapshot_backfill on startup.
    - source='package': a curated gloss from a pre-analyzed JSON
      package. `source_tag` carries the package name so the popover /
      review-card can show e.g. "[Dao De Jing]".
    - source='list': a vocab list's own meaning for the word (the list was
      learned, or used as glossary in a text the user pre-learned);
      `source_tag` is the list name.
    - source='text': what the word means in a text's sentence, by the LLM,
      kept when the word is pre-learned from that text; `source_tag` is
      the text's title.
    """

    __tablename__ = "user_word_glosses"

    id = Column(Integer, primary_key=True)
    user_word_id = Column(Integer, ForeignKey("user_words.id", ondelete="CASCADE"), nullable=False)
    pinyin = Column(String(128), nullable=True)
    meaning = Column(Text, nullable=False)
    # 'dictionary' | 'package' | 'list' | 'text'
    source = Column(String(32), nullable=False)
    # NULL for dictionary; the package name (e.g. "dao_de_jing_ch1") for
    # package-sourced glosses. Used as the human-facing tag in the UI.
    source_tag = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user_word = relationship("UserWord", back_populates="glosses")

    __table_args__ = (
        UniqueConstraint("user_word_id", "source", "source_tag", name="uq_userword_gloss"),
        Index("ix_userword_gloss_userword", "user_word_id"),
    )


class TextWord(Base):
    """A word the user pre-learned for a text ("make this text readable").

    `text_key` names the text: "saved:<id>", "library:<slug>", or
    "text:<hash>" for unsaved reading. The rows let the reader show how
    many of a text's words are already on their way, and let a review
    session focus on one text's words. `gloss_source`/`gloss_tag` name the
    text's own meaning for the word (a package or glossary gloss) so that
    session can lead with it.
    """

    __tablename__ = "text_words"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text_key = Column(String(200), nullable=False)
    word = Column(String(64), nullable=False)
    title = Column(String(160), nullable=True)
    gloss_source = Column(String(32), nullable=True)
    gloss_tag = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "text_key", "word", name="uq_text_word"),
        Index("ix_text_words_user_key", "user_id", "text_key"),
    )


class UserWordEvent(Base):
    """
    Append-only log of word-state interactions. Powers analytics, undo, and
    future ML. We keep it separate from `user_words` so the read path for the
    reader stays one indexed lookup per user.
    """

    __tablename__ = "user_word_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    word = Column(String(64), nullable=False)
    # 'seen' | 'state_change' | 'bulk_mark_known' | 'review'
    event_type = Column(String(32), nullable=False)
    new_state = Column(String(16), nullable=True)
    # 1-4 when event_type == 'review' (FSRS Rating: Again/Hard/Good/Easy).
    grade = Column(Integer, nullable=True)
    # Phase 1.3 — which modality fired this review event ('recognition',
    # 'dictation', 'writing', 'cloze'). NULL on non-review events and on
    # legacy review events pre-Phase 1.3.
    mode = Column(String(16), nullable=True)
    source_text_id = Column(
        Integer, ForeignKey("saved_texts.id", ondelete="SET NULL"), nullable=True
    )
    # How many words one event stands for. NULL means one; the HSK import
    # logs a single bulk_mark_known row for thousands of words and stores
    # the count here so weekly stats can add it up.
    word_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_user_word_events_user_created", "user_id", "created_at"),)


class InvitationToken(Base):
    __tablename__ = "invitation_tokens"

    id = Column(Integer, primary_key=True)
    token = Column(String(36), unique=True, nullable=False, index=True)  # UUID4
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    claimed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship(
        "User", foreign_keys=[created_by_user_id], back_populates="created_invitations"
    )
    claimer = relationship(
        "User", foreign_keys=[claimed_by_user_id], back_populates="claimed_invitation"
    )


class SystemSetting(Base):
    """Phase 2.7 — key/value store for instance-wide admin toggles. Lives in
    the DB (not env vars) so the admin can flip them from the UI without a
    redeploy. Keys are namespaced (e.g. `registration.open`,
    `registration.per_ip_24h`, `lifecycle.soft_delete_days`). Values are
    stored as JSON-encoded strings to allow ints, bools, and lists in one
    column."""

    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SignupAttempt(Base):
    """Phase 2.7 — per-IP rate-limit tracking for open registration. Rows
    older than 24 h are pruned in the lifecycle pass. `successful` lets us
    differentiate failed captcha / username-taken / global-cap-hit attempts
    from real signups when surfacing stats."""

    __tablename__ = "signup_attempts"

    id = Column(Integer, primary_key=True)
    ip_address = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    successful = Column(Boolean, default=False)

    __table_args__ = (Index("ix_signup_attempts_ip_created", "ip_address", "created_at"),)


# Database setup
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR}/qingdu.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record):
    """WAL lets the two uvicorn workers write concurrently instead of
    fighting over the rollback journal ("database is locked" 500s), and
    busy_timeout makes the rare remaining collision wait instead of throw.
    WAL is a persistent DB property but setting it per-connection is
    harmless and covers fresh databases."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Engine, "connect")
def _sqlite_functions(dbapi_connection, _connection_record):
    """SQL helpers implemented in Python, registered on every SQLite
    connection (the app engine and the in-memory engines tests build).

    pinyin_key() backs the /words pinyin search. Spelling it as nested
    replace() calls in SQL hits "parser stack overflow" on some SQLite builds.
    """
    if not hasattr(dbapi_connection, "create_function"):
        return
    from app.services.word_search import pinyin_key

    dbapi_connection.create_function("pinyin_key", 1, pinyin_key, deterministic=True)


def init_db():
    """Initialize database and handle schema migrations"""
    import logging

    from sqlalchemy import inspect, text

    logger = logging.getLogger(__name__)
    inspector = inspect(engine)

    # Create all tables if they don't exist
    Base.metadata.create_all(bind=engine)

    # Handle schema updates for existing databases
    db = SessionLocal()
    try:
        # Check if invite_quota column exists in users table
        if inspector.has_table("users"):
            columns = [col["name"] for col in inspector.get_columns("users")]
            if "invite_quota" not in columns:
                logger.info("Adding invite_quota column to users table")
                with engine.connect() as conn:
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN invite_quota INTEGER DEFAULT 5")
                    )
                    conn.commit()

        # Phase #99 — glossary support: apply_as_glossary on vocab lists,
        # glossary_list_ids on saved texts (both idempotent ALTERs).
        if inspector.has_table("vocabulary_lists"):
            vl_cols = {col["name"] for col in inspector.get_columns("vocabulary_lists")}
            if "apply_as_glossary" not in vl_cols:
                logger.info("Adding apply_as_glossary column to vocabulary_lists")
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE vocabulary_lists ADD COLUMN apply_as_glossary "
                            "BOOLEAN DEFAULT 0"
                        )
                    )
                    conn.commit()
            if "dict_version" not in vl_cols:
                logger.info("Adding dict_version column to vocabulary_lists")
                with engine.connect() as conn:
                    conn.execute(
                        text("ALTER TABLE vocabulary_lists ADD COLUMN dict_version VARCHAR(64)")
                    )
                    conn.commit()

        # Phase G3 — share_token column on saved_texts (idempotent ALTER).
        # Phase #99 — glossary_list_ids on saved_texts.
        if inspector.has_table("saved_texts"):
            st_cols = {col["name"] for col in inspector.get_columns("saved_texts")}
            if "share_token" not in st_cols:
                logger.info("Adding share_token column to saved_texts")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE saved_texts ADD COLUMN share_token VARCHAR(36)"))
                    conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS ix_saved_texts_share_token "
                            "ON saved_texts(share_token)"
                        )
                    )
                    conn.commit()
            if "glossary_list_ids" not in st_cols:
                logger.info("Adding glossary_list_ids column to saved_texts")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE saved_texts ADD COLUMN glossary_list_ids TEXT"))
                    conn.commit()
            # Text folders: the folder a text lives in and its place there.
            if "folder_id" not in st_cols:
                logger.info("Adding folder_id and position columns to saved_texts")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE saved_texts ADD COLUMN folder_id INTEGER"))
                    conn.execute(text("ALTER TABLE saved_texts ADD COLUMN position INTEGER"))
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_saved_texts_folder_id "
                            "ON saved_texts(folder_id)"
                        )
                    )
                    conn.commit()
            # Comprehension questions for the text (services/text_quiz).
            if "quiz" not in st_cols:
                logger.info("Adding quiz column to saved_texts")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE saved_texts ADD COLUMN quiz TEXT"))
                    conn.commit()

        # Phase F2 — streak columns on users (idempotent ALTER).
        # Phase #96 — daily_new_words + hsk_focus_version on users.
        if inspector.has_table("users"):
            user_cols = {col["name"] for col in inspector.get_columns("users")}
            with engine.connect() as conn:
                if "streak_count" not in user_cols:
                    logger.info("Adding streak_count column to users")
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN streak_count INTEGER DEFAULT 0")
                    )
                if "streak_last_active" not in user_cols:
                    logger.info("Adding streak_last_active column to users")
                    conn.execute(text("ALTER TABLE users ADD COLUMN streak_last_active DATE"))
                if "streak_freeze_count" not in user_cols:
                    logger.info("Adding streak_freeze_count column to users")
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN streak_freeze_count INTEGER DEFAULT 0")
                    )
                if "daily_new_words" not in user_cols:
                    logger.info("Adding daily_new_words column to users")
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN daily_new_words INTEGER DEFAULT 0")
                    )
                if "hsk_focus_version" not in user_cols:
                    logger.info("Adding hsk_focus_version column to users")
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN hsk_focus_version "
                            "VARCHAR(8) DEFAULT 'new'"
                        )
                    )
                if "display_script" not in user_cols:
                    logger.info("Adding display_script column to users")
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN display_script VARCHAR(8) DEFAULT 'auto'"
                        )
                    )
                if "review_retention" not in user_cols:
                    logger.info("Adding review_retention column to users")
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN review_retention FLOAT DEFAULT 0.95")
                    )
                if "review_window" not in user_cols:
                    logger.info("Adding review_window column to users")
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN review_window VARCHAR(16) DEFAULT 'today'"
                        )
                    )
                if "review_focus" not in user_cols:
                    logger.info("Adding review_focus column to users")
                    conn.execute(
                        text("ALTER TABLE users ADD COLUMN review_focus VARCHAR(16) DEFAULT 'both'")
                    )
                if "timezone" not in user_cols:
                    logger.info("Adding timezone column to users")
                    conn.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR(64)"))
                if "ui_settings" not in user_cols:
                    logger.info("Adding ui_settings column to users")
                    conn.execute(text("ALTER TABLE users ADD COLUMN ui_settings TEXT"))
                # Phase 2.7 — account lifecycle status.
                if "account_status" not in user_cols:
                    logger.info("Adding account_status column to users")
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN account_status "
                            "VARCHAR(16) DEFAULT 'active'"
                        )
                    )
                if "token_version" not in user_cols:
                    logger.info("Adding token_version column to users")
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"
                        )
                    )
                conn.commit()

        # Phase B — FSRS columns on user_words + grade on user_word_events.
        # Phase #96 — pinyin + meaning snapshot on user_words so reviews
        # always have a gloss even when the upstream HSK list doesn't
        # cover the word.
        if inspector.has_table("user_words"):
            uw_cols = {col["name"] for col in inspector.get_columns("user_words")}
            needed = [
                ("stability", "FLOAT"),
                ("difficulty", "FLOAT"),
                ("fsrs_state", "TEXT"),
                ("pinyin", "VARCHAR(128)"),
                ("meaning", "TEXT"),
                ("sample_sentence", "TEXT"),
                ("sample_source", "VARCHAR(160)"),
                # Phase #100 follow-up — provenance of the meaning snapshot
                # so package-sourced glosses can be preserved against
                # dictionary fallback on re-clicks. See UserWord model.
                ("meaning_source", "VARCHAR(32)"),
                # Phase 1.3 — Mixed-mode review cycle tracking.
                ("modes_completed", "TEXT NOT NULL DEFAULT '[]'"),
                ("modes_cycle_started_at", "DATETIME"),
            ]
            with engine.connect() as conn:
                for name, sql_type in needed:
                    if name not in uw_cols:
                        logger.info("Adding %s column to user_words", name)
                        conn.execute(text(f"ALTER TABLE user_words ADD COLUMN {name} {sql_type}"))
                conn.commit()

        # Phase #96 follow-up — bring legacy 'known' rows into the SRS
        # rotation. Before this change 'known' was a terminal opt-out
        # (no due_at, never queued); now it's just a high-stability
        # learning-like card. Seed legacy rows with a Review-phase FSRS
        # state and scatter their first due dates across (60d, 180d).
        if inspector.has_table("user_words"):
            from app.services.srs import already_known_state

            session = SessionLocal()
            try:
                legacy = (
                    session.query(UserWord)
                    .filter(
                        UserWord.state == "known",
                        UserWord.fsrs_state.is_(None),
                    )
                    .all()
                )
                if legacy:
                    logger.info("Seeding %d legacy 'known' rows with FSRS state", len(legacy))
                    for r in legacy:
                        seeded = already_known_state()
                        # state stays 'known' — only the SRS fields fill in.
                        r.fsrs_state = seeded["fsrs_state"]
                        r.stability = seeded["stability"]
                        r.difficulty = seeded["difficulty"]
                        r.due_at = seeded["due_at"]
                        r.last_reviewed_at = seeded["last_reviewed_at"]
                    session.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning("legacy-known seeding failed (%s) — skipping", e)
                session.rollback()
            finally:
                session.close()
        if inspector.has_table("user_word_events"):
            ev_cols = {col["name"] for col in inspector.get_columns("user_word_events")}
            if "grade" not in ev_cols:
                logger.info("Adding grade column to user_word_events")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE user_word_events ADD COLUMN grade INTEGER"))
                    conn.commit()
            # Phase 1.3 — review event modality.
            if "mode" not in ev_cols:
                logger.info("Adding mode column to user_word_events")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE user_word_events ADD COLUMN mode VARCHAR(16)"))
                    conn.commit()
            if "word_count" not in ev_cols:
                logger.info("Adding word_count column to user_word_events")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE user_word_events ADD COLUMN word_count INTEGER"))
                    conn.commit()

        # Phase #120 — backfill user_word_glosses for legacy rows. Every
        # existing UserWord with a meaning gets one initial gloss row
        # carrying its current meaning + pinyin + source. Idempotent:
        # rows with at least one gloss are skipped.
        if inspector.has_table("user_words") and inspector.has_table("user_word_glosses"):
            session = SessionLocal()
            try:
                missing = (
                    session.query(UserWord)
                    .outerjoin(UserWordGloss, UserWordGloss.user_word_id == UserWord.id)
                    .filter(UserWordGloss.id.is_(None), UserWord.meaning.isnot(None))
                    .all()
                )
                if missing:
                    logger.info("Backfilling user_word_glosses for %d legacy rows", len(missing))
                    for r in missing:
                        if not r.meaning:
                            continue
                        source = "package" if r.meaning_source == "package" else "dictionary"
                        # We don't have the original package name on legacy
                        # rows — tag with "legacy" so the UI can render
                        # something. Future package clicks will create
                        # fresh tagged entries.
                        source_tag = "legacy" if source == "package" else None
                        session.add(
                            UserWordGloss(
                                user_word_id=r.id,
                                pinyin=r.pinyin,
                                meaning=r.meaning,
                                source=source,
                                source_tag=source_tag,
                            )
                        )
                    session.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning("user_word_glosses backfill failed (%s) — skipping", e)
                session.rollback()
            finally:
                session.close()
    except Exception:
        # Every ALTER above is guarded by a column check, so a re-run on an
        # up-to-date schema never gets here. Anything that does is a real
        # failure: refuse to boot rather than serve on a half-migrated schema.
        logger.exception("Error updating database schema")
        raise
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

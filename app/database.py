from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
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

    # Relationships
    texts = relationship("SavedText", back_populates="user", cascade="all, delete-orphan")
    vocabulary_lists = relationship(
        "VocabularyList", back_populates="user", cascade="all, delete-orphan"
    )
    user_words = relationship("UserWord", back_populates="user", cascade="all, delete-orphan")
    created_invitations = relationship(
        "InvitationToken",
        foreign_keys="InvitationToken.created_by_user_id",
        back_populates="creator",
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

    user = relationship("User", back_populates="texts")


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
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="vocabulary_lists")


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
    # translations are not in the upstream HSK list and would otherwise
    # be lost once unknown_word_cache (TTL 30min) evicts them.
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
    """

    __tablename__ = "user_word_glosses"

    id = Column(Integer, primary_key=True)
    user_word_id = Column(Integer, ForeignKey("user_words.id", ondelete="CASCADE"), nullable=False)
    pinyin = Column(String(128), nullable=True)
    meaning = Column(Text, nullable=False)
    # 'dictionary' | 'package'
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
    source_text_id = Column(
        Integer, ForeignKey("saved_texts.id", ondelete="SET NULL"), nullable=True
    )
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


# Database setup
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR}/qingdu.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
                # Phase #100 follow-up — provenance of the meaning snapshot
                # so package-sourced glosses can be preserved against
                # dictionary fallback on re-clicks. See UserWord model.
                ("meaning_source", "VARCHAR(32)"),
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
    except Exception as e:
        logger.error(f"Error updating database schema: {e}")
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

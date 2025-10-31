from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json
from pathlib import Path

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

    # Relationships
    texts = relationship("SavedText", back_populates="user", cascade="all, delete-orphan")
    vocabulary_lists = relationship("VocabularyList", back_populates="user", cascade="all, delete-orphan")
    created_invitations = relationship("InvitationToken", foreign_keys="InvitationToken.created_by_user_id", back_populates="creator")
    claimed_invitation = relationship("InvitationToken", foreign_keys="InvitationToken.claimed_by_user_id", back_populates="claimer", uselist=False)

class SavedText(Base):
    __tablename__ = "saved_texts"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    title = Column(String(500))
    content = Column(Text)
    tags = Column(Text, nullable=True)
    reading_progress = Column(Integer, default=0)  # 0-100%
    analysis_data = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="texts")

class VocabularyList(Base):
    __tablename__ = "vocabulary_lists"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(255))
    list_type = Column(String(50))  # 'hsk', 'auto', 'custom'
    sections = Column(Text)  # JSON string
    anki_deck_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="vocabulary_lists")

class InvitationToken(Base):
    __tablename__ = "invitation_tokens"

    id = Column(Integer, primary_key=True)
    token = Column(String(36), unique=True, nullable=False, index=True)  # UUID4
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    claimed_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by_user_id], back_populates="created_invitations")
    claimer = relationship("User", foreign_keys=[claimed_by_user_id], back_populates="claimed_invitation")

# Database setup
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR}/qingdu.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize database and handle schema migrations"""
    from sqlalchemy import inspect
    import logging

    logger = logging.getLogger(__name__)
    inspector = inspect(engine)

    # Create all tables if they don't exist
    Base.metadata.create_all(bind=engine)

    # Handle schema updates for existing databases
    db = SessionLocal()
    try:
        # Check if invite_quota column exists in users table
        if inspector.has_table("users"):
            columns = [col['name'] for col in inspector.get_columns('users')]
            if 'invite_quota' not in columns:
                logger.info("Adding invite_quota column to users table")
                with engine.connect() as conn:
                    conn.execute('ALTER TABLE users ADD COLUMN invite_quota INTEGER DEFAULT 5')
                    conn.commit()
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

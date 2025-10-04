from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json
from pathlib import Path

Base = declarative_base()

class SavedText(Base):
    __tablename__ = "saved_texts"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500))
    content = Column(Text)
    analysis_data = Column(Text)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

# Database setup
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR}/qingdu.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    import os
    # Only create tables if they don't exist
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if not inspector.has_table("saved_texts"):
        Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

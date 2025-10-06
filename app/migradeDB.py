"""Add anki_deck_id to vocabulary_lists table"""
from app.database import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Add column
        conn.execute(text(
            "ALTER TABLE vocabulary_lists ADD COLUMN anki_deck_id INTEGER"
        ))
        
        # Generate IDs for existing lists
        conn.execute(text("""
            UPDATE vocabulary_lists 
            SET anki_deck_id = 2000000 + (id * 1000) + ABS(RANDOM() % 1000)
            WHERE anki_deck_id IS NULL
        """))
        
        conn.commit()
        print("Migration completed: anki_deck_id added")

if __name__ == "__main__":
    migrate()
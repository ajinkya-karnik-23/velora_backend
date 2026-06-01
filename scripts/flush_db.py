from sqlalchemy import create_engine , text
import os 
from dotenv import load_dotenv 

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not found in environment variables.")


DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg",
    "postgresql")


engine = create_engine(DATABASE_URL)

def flush_db():
    with engine.begin() as conn:
        tables = conn.execute(text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename != 'alembic_version';""")).fetchall()
        tables_names = ", ".join([table[0] for table in tables])
        conn.execute(text(
            f"TRUNCATE TABLE {tables_names} RESTART IDENTITY CASCADE"
        ))
        print("✅ Database flushed successfully.")
        print("Schema preserved")
if __name__ == "__main__":
    flush_db()

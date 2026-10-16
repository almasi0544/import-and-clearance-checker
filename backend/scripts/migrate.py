"""Create or update the database tables.

From the repository root:
    python backend/scripts/migrate.py

Uses DATABASE_URL from your .env file, for example:
    postgresql://user:password@localhost:5432/clearance
    sqlite:///.local/dev.db        (for local work before PostgreSQL is ready)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_env_file  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.db.migrate import migrate  # noqa: E402

if __name__ == "__main__":
    load_env_file(Path(__file__).resolve().parents[2] / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Error: DATABASE_URL is not set. Add it to your .env file.")
    db = Database.connect(url)
    try:
        migrate(db)
    finally:
        db.close()

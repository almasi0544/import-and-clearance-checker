"""Create four demo users (one for each role) so the endpoints can be tried in DEMO_MODE.

From the repository root:
    python backend/scripts/seed_demo_users.py

The password hash is a placeholder and is NOT a real hash, so these users cannot log in with a password.
They work only with the DEMO_MODE header placeholder. Almasi's login and real demo accounts replace this."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_env_file  # noqa: E402
from app.db.database import Database, new_id  # noqa: E402

DEMO_USERS = [("Demo Importer", "importer@demo.test", "importer"), ("Demo Agent", "agent@demo.test", "clearing_agent"),
              ("Demo Reviewer", "reviewer@demo.test", "reviewer"), ("Demo Admin", "admin@demo.test", "admin")]
PLACEHOLDER_HASH = "!placeholder-not-a-real-hash"


def seed(db):
    """Add the demo users that do not exist yet. Returns the emails added."""
    added = []
    for name, email, role in DEMO_USERS:
        if db.query_one("SELECT id FROM users WHERE email = ?", (email,)) is None:
            db.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                       (new_id(), name, email, PLACEHOLDER_HASH, role))
            added.append(email)
    db.commit()
    return added


if __name__ == "__main__":
    load_env_file(Path(__file__).resolve().parents[2] / ".env")
    if os.environ.get("DEMO_MODE", "").lower() != "true":
        sys.exit("Error: set DEMO_MODE=true in your .env file first. This script is for demo use only.")
    if not os.environ.get("DATABASE_URL"):
        sys.exit("Error: DATABASE_URL is not set. Add it to your .env file.")
    db = Database.connect(os.environ["DATABASE_URL"])
    try:
        added = seed(db)
    finally:
        db.close()
    print("Added: " + ", ".join(added) if added else "The demo users already exist.")

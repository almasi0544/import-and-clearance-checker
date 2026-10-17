"""Give the four demo users a real password (argon2 hash) so they can log in.

From the repository root:
    python backend/scripts/set_demo_passwords.py
Reads DEMO_PASSWORD (at least 12 characters) from your .env file. Demo data only: never use a real password."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_env_file  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

DEMO_EMAILS = ("importer@demo.test", "agent@demo.test", "reviewer@demo.test", "admin@demo.test")

if __name__ == "__main__":
    load_env_file(Path(__file__).resolve().parents[2] / ".env")
    password = os.environ.get("DEMO_PASSWORD", "")
    if os.environ.get("DEMO_MODE", "").lower() != "true":
        sys.exit("Error: set DEMO_MODE=true in your .env file first. This script is for demo use only.")
    if len(password) < 12:
        sys.exit("Error: set DEMO_PASSWORD (at least 12 characters) in your .env file.")
    if not os.environ.get("DATABASE_URL"):
        sys.exit("Error: DATABASE_URL is not set. Add it to your .env file.")
    db = Database.connect(os.environ["DATABASE_URL"])
    try:
        done = []
        for email in DEMO_EMAILS:
            if db.query_one("SELECT id FROM users WHERE email = ?", (email,)) is not None:
                db.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hash_password(password), email))
                done.append(email)
        db.commit()
    finally:
        db.close()
    print("Password set for: " + ", ".join(done) if done else "No demo users found. Run seed_demo_users.py first.")
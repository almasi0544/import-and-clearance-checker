"""Things every endpoint needs: a database connection, and the logged-in user.

get_current_user below is a PLACEHOLDER so the endpoints can be built and tried now. It reads the header
X-Demo-User (an email address) and works only when DEMO_MODE=true. Almasi's token login replaces it.
Keep the name and the result (a dict with id, name, email, role) the same, so nothing else changes."""
import os
from pathlib import Path

from fastapi import Depends, Header

from app.db.database import Database
from app.errors import Unauthorized

REPO_ROOT = Path(__file__).resolve().parents[3]


def get_db():
    db = Database.connect(os.environ["DATABASE_URL"])
    try:
        yield db
    finally:
        db.close()


def upload_dir():
    return os.environ.get("UPLOAD_DIR") or str(REPO_ROOT / "uploads")


def get_current_user(x_demo_user: str | None = Header(default=None), db: Database = Depends(get_db)):
    if os.environ.get("DEMO_MODE", "").lower() != "true":
        raise Unauthorized("Log in to continue.")
    if not x_demo_user:
        raise Unauthorized("Log in to continue.")
    user = db.query_one("SELECT id, name, email, role FROM users WHERE email = ?", (x_demo_user.strip().lower(),))
    if user is None:
        raise Unauthorized("Log in to continue.")
    return user

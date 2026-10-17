"""Things every endpoint needs: a database connection, and the logged-in user.

get_current_user reads the Authorization: Bearer <token> header, checks the signed token and loads the user
from the database, so the role is always the current one. The result is a dict with id, name, email, role."""
import os
from pathlib import Path

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.database import Database
from app.errors import Forbidden, Unauthorized
from app.services.auth import read_token

REPO_ROOT = Path(__file__).resolve().parents[3]
bearer = HTTPBearer(auto_error=False)


def get_db():
    db = Database.connect(os.environ["DATABASE_URL"])
    try:
        yield db
    finally:
        db.close()


def upload_dir():
    return os.environ.get("UPLOAD_DIR") or str(REPO_ROOT / "uploads")


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Security(bearer),
                     db: Database = Depends(get_db)):
    if credentials is None:
        raise Unauthorized("Log in to continue.")
    user_id = read_token(credentials.credentials)
    user = db.query_one("SELECT id, name, email, role FROM users WHERE id = ?", (user_id,))
    if user is None:
        raise Unauthorized("Log in to continue.")
    return user


def require_role(*roles):
    """Use as Depends(require_role("reviewer", "admin")): logged in AND one of these roles, or 403."""
    def check(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise Forbidden("Your role cannot do this.")
        return user
    return check
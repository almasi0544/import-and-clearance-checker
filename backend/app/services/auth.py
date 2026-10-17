"""Login security: argon2 password hashing, signed tokens with an expiry, one generic failure message.

Passwords are never stored or logged. A token carries only the user id and its times: the role is read from the
database on every request, so a role change or a deleted user takes effect at once."""
import os
import time
from typing import Optional

import jwt
from argon2 import PasswordHasher

from app.errors import Unauthorized
from app.services.audit import audit

ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32
_hasher = PasswordHasher()
# Checked when the email is unknown, so the answer takes the same time and does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except Exception:  # wrong password, placeholder hash or damaged hash: all mean "no"
        return False


def _secret() -> str:
    secret = os.environ.get("SECRET_KEY", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError("SECRET_KEY must be a random value of at least 32 characters.")
    return secret


def _lifetime_seconds() -> int:
    try:
        minutes = int(os.environ.get("TOKEN_EXPIRE_MINUTES", "60"))
    except ValueError:
        minutes = 60
    return max(1, min(minutes, 24 * 60)) * 60


def create_token(user_id: str, now: Optional[int] = None) -> str:
    now = int(time.time()) if now is None else now
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + _lifetime_seconds()}, _secret(), algorithm=ALGORITHM)


def read_token(token: str) -> str:
    """The user id inside a valid token. Every problem gives the same 401, so the caller learns nothing."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        raise Unauthorized("Log in to continue.")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise Unauthorized("Log in to continue.")
    return sub


def login(db, email, password) -> str:
    """Check the credentials, write the audit row, return a token. One generic 401 for every failure."""
    email = (email or "").strip().lower()
    user = db.query_one("SELECT id, name, email, role, password_hash FROM users WHERE email = ?", (email,))
    good = verify_password(password or "", user["password_hash"] if user else _DUMMY_HASH)
    if user is None or not good:
        if user is not None:
            audit(db, {"id": user["id"]}, "login_failed")
            db.commit()
        raise Unauthorized("Wrong email or password.")
    audit(db, {"id": user["id"]}, "login")
    db.commit()
    return create_token(user["id"])
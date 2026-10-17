"""Safe uploads: check the real file type and the size, store under a random name outside the public folder.
(Almasi owns this file: please review and harden it.)"""
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from app.errors import BadRequest

DEFAULT_MAX_MB = 10
# the first bytes of each allowed file type -> (mime type, file extension)
SIGNATURES = [
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
]


def max_upload_bytes(env=None):
    env = os.environ if env is None else env
    try:
        mb = float(env.get("MAX_UPLOAD_MB") or DEFAULT_MAX_MB)
    except ValueError:
        mb = DEFAULT_MAX_MB
    return int(mb * 1024 * 1024)


def sniff(content):
    """The real file type from the content, not from the file name. Returns (mime, extension) or raises."""
    for signature, mime, ext in SIGNATURES:
        if content.startswith(signature):
            return mime, ext
    raise BadRequest("Only PDF, PNG and JPEG files are accepted.")


def check_upload(content, max_bytes):
    if not content:
        raise BadRequest("The file is empty.")
    if len(content) > max_bytes:
        raise BadRequest(f"The file is too large. The limit is {max_bytes // (1024 * 1024)} MB.")
    return sniff(content)


def save_file(upload_dir, content, ext):
    """Write the file under a random name. Returns (stored name, sha256). The original name is never used."""
    name = uuid4().hex + ext
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
    (Path(upload_dir) / name).write_bytes(content)
    return name, hashlib.sha256(content).hexdigest()


def remove_file(upload_dir, name):
    if name:
        (Path(upload_dir) / name).unlink(missing_ok=True)

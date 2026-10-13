"""Reads settings from environment variables. Secrets live in a local .env file that is never committed."""
import os
from pathlib import Path


def load_env_file(path=".env", environ=None):
    """Load KEY=VALUE lines from a .env file into the environment.
    Values already set in the environment win. Lines starting with # are ignored."""
    environ = os.environ if environ is None else environ
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in environ:
            environ[key] = value

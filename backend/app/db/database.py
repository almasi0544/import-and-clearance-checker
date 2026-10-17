"""A thin database layer that works on PostgreSQL (production) and SQLite (tests and local work).

Write SQL with ? placeholders. On PostgreSQL they are converted to %s.
Rows come back as plain dicts, with UUIDs and timestamps as text.
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def new_id():
    """A random UUID as text. IDs are random so they cannot be guessed."""
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, conn, dialect):
        self.conn = conn
        self.dialect = dialect          # "postgres" or "sqlite"

    @classmethod
    def connect(cls, url):
        if url.startswith("sqlite:///"):
            path = url[len("sqlite:///"):] or ":memory:"
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)   # the web server uses worker threads
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return cls(conn, "sqlite")
        if url.startswith(("postgresql://", "postgres://")):
            import psycopg
            from psycopg.rows import dict_row
            return cls(psycopg.connect(url, row_factory=dict_row), "postgres")
        raise ValueError("DATABASE_URL must start with postgresql:// or sqlite:///")

    # ---------- queries ----------
    def _sql(self, sql):
        return sql.replace("?", "%s") if self.dialect == "postgres" else sql

    @staticmethod
    def _clean(row):
        out = dict(row)
        for key, value in out.items():
            if isinstance(value, uuid.UUID):
                out[key] = str(value)
            elif isinstance(value, datetime):
                out[key] = value.isoformat()
        return out

    def execute(self, sql, params=()):
        """Run one statement. Returns the number of rows changed."""
        return self.conn.execute(self._sql(sql), tuple(params)).rowcount

    def query(self, sql, params=()):
        cur = self.conn.execute(self._sql(sql), tuple(params))
        return [self._clean(r) for r in cur.fetchall()]

    def query_one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ---------- JSON columns ----------
    def json_param(self, obj):
        """Wrap a Python value so it can be stored in a JSON column."""
        if self.dialect == "postgres":
            from psycopg.types.json import Jsonb
            return Jsonb(obj)
        return json.dumps(obj)

    @staticmethod
    def load_json(value):
        """A JSON column value as Python data (SQLite returns text, PostgreSQL returns data)."""
        return json.loads(value) if isinstance(value, (str, bytes)) else value

    # ---------- transactions ----------
    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    @contextmanager
    def transaction(self):
        """Commit if the block succeeds, roll back if it raises."""
        try:
            yield self
            self.commit()
        except Exception:
            self.rollback()
            raise

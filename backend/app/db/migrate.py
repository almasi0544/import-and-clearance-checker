"""Applies the SQL files in backend/migrations/ in order and remembers which ones were applied,
so the whole structure can be rebuilt from code. Files ending in .pg.sql run on PostgreSQL only."""
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _version(path):
    name = path.name
    return name[:-len(".pg.sql")] if name.endswith(".pg.sql") else name[:-len(".sql")]


def migrate(db, migrations_dir=DEFAULT_DIR, out=print):
    """Apply every migration that has not been applied yet. Returns the versions applied now."""
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
               "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.commit()
    done = {r["version"] for r in db.query("SELECT version FROM schema_migrations")}
    applied = []
    for path in sorted(Path(migrations_dir).glob("*.sql")):
        if path.name.endswith(".pg.sql") and db.dialect != "postgres":
            continue
        version = _version(path)
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            if db.dialect == "sqlite":
                db.conn.executescript(sql)
            else:
                db.conn.execute(sql)
            db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            db.commit()
        except Exception:
            db.rollback()
            raise
        applied.append(version)
        out(f"Applied {version}")
    if not applied:
        out("Nothing to do: the database is up to date.")
    return applied

-- PostgreSQL only (the runner skips files ending in .pg.sql on SQLite).
-- Makes audit_events append-only: nobody can update or delete an event, not even the app.
-- Almasi: please review and test this on the real database (try an UPDATE and a DELETE).

CREATE OR REPLACE FUNCTION audit_events_block_changes() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_no_update_delete
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_block_changes();

import sqlite3
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts backend on the path)
from app.db.database import Database, new_id
from app.db.migrate import DEFAULT_DIR, migrate

TABLES = {"users", "shipments", "documents", "extractions", "analysis_runs", "findings",
          "agent_results", "review_actions", "audit_events", "evolus_calls"}


def silent(*args):
    pass


class DbCase(unittest.TestCase):
    def setUp(self):
        self.db = Database.connect("sqlite:///:memory:")
        migrate(self.db, out=silent)

    def tearDown(self):
        self.db.close()

    # small helpers that insert valid rows
    def user(self, role="clearing_agent", email=None):
        uid = new_id()
        self.db.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                        (uid, "Test User", email or f"{uid}@example.com", "hash", role))
        return uid

    def shipment(self, owner):
        sid = new_id()
        self.db.execute("INSERT INTO shipments (id, reference, owner_id) VALUES (?, ?, ?)", (sid, "SHP-1", owner))
        return sid

    def document(self, shipment, owner, doc_type="packing_list"):
        did = new_id()
        self.db.execute("INSERT INTO documents (id, shipment_id, doc_type, file_path, file_hash, mime_type, size_bytes, uploaded_by) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (did, shipment, doc_type, "abc123.pdf", "hash", "application/pdf", 2900, owner))
        return did

    def run_and_finding(self, shipment, user):
        rid, fid = new_id(), new_id()
        self.db.execute("INSERT INTO analysis_runs (id, shipment_id, started_by, rule_pack_version, results) VALUES (?, ?, ?, ?, ?)",
                        (rid, shipment, user, "tz-0.1", self.db.json_param({"C3": "finding"})))
        self.db.execute("INSERT INTO findings (id, shipment_id, run_id, check_id, severity, document_a, document_b, field, values_json, message) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (fid, shipment, rid, "C3", "high", "packing_list", "bill_of_lading", "gross_weight",
                         self.db.json_param({"packing_list": 2500, "bill_of_lading": 2700}), "Gross weight differs by 200 kg (8 percent)."))
        return rid, fid


class TestMigrations(DbCase):
    def tables(self):
        return {r["name"] for r in self.db.query("SELECT name FROM sqlite_master WHERE type='table'")}

    def test_all_ten_tables_are_created(self):
        self.assertTrue(TABLES <= self.tables())

    def test_running_the_migrations_again_does_nothing(self):
        self.assertEqual(migrate(self.db, out=silent), [])
        self.assertEqual(self.db.query("SELECT COUNT(*) AS n FROM schema_migrations")[0]["n"], 1)

    def test_postgres_only_files_are_skipped_on_sqlite(self):
        self.assertTrue((DEFAULT_DIR / "002_audit_append_only.pg.sql").exists())
        versions = [r["version"] for r in self.db.query("SELECT version FROM schema_migrations")]
        self.assertEqual(versions, ["001_create_tables"])

    def test_a_failing_migration_is_not_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "001_bad.sql").write_text("CREATE TABLE oops (;")
            db = Database.connect("sqlite:///:memory:")
            with self.assertRaises(sqlite3.Error):
                migrate(db, Path(d), out=silent)
            self.assertEqual(db.query("SELECT COUNT(*) AS n FROM schema_migrations")[0]["n"], 0)

    def test_the_database_can_be_rebuilt_in_a_new_file(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database.connect(f"sqlite:///{d}/new/dev.db")
            migrate(db, out=silent)
            self.assertIn("findings", {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")})
            db.close()

    def test_placeholders_are_converted_for_postgres(self):
        pg = Database(None, "postgres")
        self.assertEqual(pg._sql("SELECT * FROM t WHERE a = ? AND b = ?"), "SELECT * FROM t WHERE a = %s AND b = %s")

    def test_a_bad_database_url_is_rejected(self):
        with self.assertRaises(ValueError):
            Database.connect("mysql://x")


class TestRules(DbCase):
    def test_a_shipment_starts_as_created_and_gets_a_timestamp(self):
        sid = self.shipment(self.user())
        row = self.db.query_one("SELECT status, country, created_at FROM shipments WHERE id = ?", (sid,))
        self.assertEqual((row["status"], row["country"]), ("created", "TZ"))
        self.assertTrue(row["created_at"])

    def test_a_shipment_needs_a_real_owner(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.shipment(new_id())

    def test_email_must_be_unique(self):
        self.user(email="a@example.com")
        with self.assertRaises(sqlite3.IntegrityError):
            self.user(email="a@example.com")

    def test_roles_are_limited_to_the_four_roles(self):
        for role in ("importer", "clearing_agent", "reviewer", "admin"):
            self.user(role)
        with self.assertRaises(sqlite3.IntegrityError):
            self.user("hacker")

    def test_statuses_are_limited(self):
        sid = self.shipment(self.user())
        self.db.execute("UPDATE shipments SET status = 'in_review' WHERE id = ?", (sid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE shipments SET status = 'done' WHERE id = ?", (sid,))

    def test_one_document_of_each_type_per_shipment(self):
        owner = self.user()
        sid = self.shipment(owner)
        self.document(sid, owner, "packing_list")
        self.document(sid, owner, "bill_of_lading")
        with self.assertRaises(sqlite3.IntegrityError):
            self.document(sid, owner, "packing_list")

    def test_document_type_is_limited(self):
        owner = self.user()
        with self.assertRaises(sqlite3.IntegrityError):
            self.document(self.shipment(owner), owner, "passport")

    def test_an_extraction_is_confirmed_completely_or_not_at_all(self):
        owner = self.user()
        did = self.document(self.shipment(owner), owner)
        eid = new_id()
        self.db.execute("INSERT INTO extractions (id, document_id, schema_version, fields_extracted) VALUES (?, ?, ?, ?)",
                        (eid, did, "1", self.db.json_param({"packages": 500})))
        with self.assertRaises(sqlite3.IntegrityError):    # confirmed fields without who and when
            self.db.execute("UPDATE extractions SET fields_confirmed = ? WHERE id = ?", (self.db.json_param({}), eid))
        self.db.execute("UPDATE extractions SET fields_confirmed = ?, confirmed_by = ?, confirmed_at = ? WHERE id = ?",
                        (self.db.json_param({"packages": 500}), owner, "2026-10-13T10:00:00", eid))

    def test_one_extraction_per_document(self):
        owner = self.user()
        did = self.document(self.shipment(owner), owner)
        for i in range(2):
            try:
                self.db.execute("INSERT INTO extractions (id, document_id, schema_version, fields_extracted) VALUES (?, ?, ?, ?)",
                                (new_id(), did, "1", self.db.json_param({})))
            except sqlite3.IntegrityError:
                self.assertEqual(i, 1)
                return
        self.fail("a second extraction for the same document was accepted")

    def test_severity_and_finding_status_are_limited(self):
        owner = self.user()
        sid = self.shipment(owner)
        _, fid = self.run_and_finding(sid, owner)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE findings SET severity = 'critical' WHERE id = ?", (fid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE findings SET status = 'ignored' WHERE id = ?", (fid,))

    def test_one_agent_result_per_run(self):
        owner = self.user()
        sid = self.shipment(owner)
        rid, _ = self.run_and_finding(sid, owner)
        sql = ("INSERT INTO agent_results (id, shipment_id, run_id, fix_list, needs_human, reply_valid) VALUES (?, ?, ?, ?, ?, ?)")
        self.db.execute(sql, (new_id(), sid, rid, self.db.json_param([]), True, True))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(sql, (new_id(), sid, rid, self.db.json_param([]), True, True))

    def test_resolving_needs_a_note_and_a_finding(self):
        reviewer = self.user("reviewer")
        sid = self.shipment(self.user())
        _, fid = self.run_and_finding(sid, reviewer)
        sql = "INSERT INTO review_actions (id, shipment_id, finding_id, user_id, action, note) VALUES (?, ?, ?, ?, ?, ?)"
        self.db.execute(sql, (new_id(), sid, fid, reviewer, "resolve", "Shipper confirmed 2,500 kg."))
        with self.assertRaises(sqlite3.IntegrityError):       # no note
            self.db.execute(sql, (new_id(), sid, fid, reviewer, "resolve", None))
        with self.assertRaises(sqlite3.IntegrityError):       # a blank note
            self.db.execute(sql, (new_id(), sid, fid, reviewer, "accept", "   "))
        with self.assertRaises(sqlite3.IntegrityError):       # resolve without a finding
            self.db.execute(sql, (new_id(), sid, None, reviewer, "resolve", "note"))

    def test_approving_a_case_has_no_finding(self):
        reviewer = self.user("reviewer")
        sid = self.shipment(self.user())
        _, fid = self.run_and_finding(sid, reviewer)
        sql = "INSERT INTO review_actions (id, shipment_id, finding_id, user_id, action) VALUES (?, ?, ?, ?, ?)"
        self.db.execute(sql, (new_id(), sid, None, reviewer, "approve"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(sql, (new_id(), sid, fid, reviewer, "approve"))


class TestWholeChain(DbCase):
    def test_a_case_can_be_stored_from_upload_to_approval_and_read_back(self):
        agent, reviewer = self.user("clearing_agent"), self.user("reviewer")
        sid = self.shipment(agent)
        did = self.document(sid, agent)
        self.db.execute("INSERT INTO extractions (id, document_id, schema_version, fields_extracted) VALUES (?, ?, ?, ?)",
                        (new_id(), did, "1", self.db.json_param({"total_gross_weight": 2500, "weight_unit": "kg"})))
        rid, fid = self.run_and_finding(sid, agent)
        self.db.execute("INSERT INTO agent_results (id, shipment_id, run_id, summary, fix_list, needs_human, reply_valid, model_name) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (new_id(), sid, rid, "One difference.", self.db.json_param([{"finding_id": "F1", "action": "Ask the shipper."}]), True, True, "model-x"))
        self.db.execute("INSERT INTO review_actions (id, shipment_id, finding_id, user_id, action, note) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id(), sid, fid, reviewer, "resolve", "Confirmed."))
        self.db.execute("INSERT INTO review_actions (id, shipment_id, user_id, action) VALUES (?, ?, ?, ?)", (new_id(), sid, reviewer, "approve"))
        self.db.execute("INSERT INTO audit_events (id, user_id, action, object_type, object_id, details) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id(), reviewer, "case_approved", "shipment", sid, self.db.json_param({"findings": 1})))
        self.db.execute("INSERT INTO evolus_calls (id, method, endpoint, shipment_id, document_id, http_status, duration_ms, ok) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (new_id(), "POST", "/agents/A/json/E/ask-file", sid, did, 200, 812, True))
        self.db.commit()

        row = self.db.query_one("SELECT f.check_id, f.values_json, a.needs_human FROM findings f "
                                "JOIN agent_results a ON a.run_id = f.run_id WHERE f.shipment_id = ?", (sid,))
        self.assertEqual(row["check_id"], "C3")
        self.assertEqual(Database.load_json(row["values_json"]), {"packing_list": 2500, "bill_of_lading": 2700})
        self.assertTrue(row["needs_human"])
        self.assertEqual(self.db.query_one("SELECT COUNT(*) AS n FROM review_actions WHERE shipment_id = ?", (sid,))["n"], 2)

    def test_a_failed_transaction_leaves_nothing_behind(self):
        owner = self.user()
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction():
                self.shipment(owner)
                self.shipment(new_id())          # bad owner: the whole block is rolled back
        self.assertEqual(self.db.query_one("SELECT COUNT(*) AS n FROM shipments")["n"], 0)

    def test_ids_are_random_and_unique(self):
        ids = {new_id() for _ in range(1000)}
        self.assertEqual(len(ids), 1000)


if __name__ == "__main__":
    unittest.main()

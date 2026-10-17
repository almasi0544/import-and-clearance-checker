import hashlib
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
from app.db.database import Database, new_id
from app.db.migrate import migrate
from app.errors import BadRequest, Conflict, Forbidden, NotFound
from app.services import shipments as svc
from app.services.audit import audit

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 20


class Case(unittest.TestCase):
    def setUp(self):
        self.db = Database.connect("sqlite:///:memory:")
        migrate(self.db, out=lambda *a: None)
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "uploads"

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def user(self, role, name=None):
        uid = new_id()
        self.db.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                        (uid, name or role, f"{uid}@example.com", "hash", role))
        self.db.commit()
        return self.db.query_one("SELECT id, name, email, role FROM users WHERE id = ?", (uid,))

    def upload(self, user, shipment_id, doc_type="packing_list", content=PDF, **kw):
        return svc.upload_document(self.db, user, shipment_id, doc_type, content, self.dir, **kw)

    def events(self, action):
        return self.db.query("SELECT * FROM audit_events WHERE action = ?", (action,))


class TestCreate(Case):
    def test_an_importer_and_a_clearing_agent_can_create(self):
        for role in ("importer", "clearing_agent"):
            s = svc.create_shipment(self.db, self.user(role), "SHP-0001")
            self.assertEqual((s["status"], s["country"], s["reference"]), ("created", "TZ", "SHP-0001"))

    def test_a_reviewer_and_an_admin_cannot_create(self):
        for role in ("reviewer", "admin"):
            with self.assertRaises(Forbidden):
                svc.create_shipment(self.db, self.user(role), "SHP-0001")

    def test_the_owner_comes_from_the_user(self):
        agent = self.user("clearing_agent")
        s = svc.create_shipment(self.db, agent, "SHP-0001")
        self.assertEqual(s["owner_id"], agent["id"])

    def test_the_owner_and_the_status_cannot_be_passed_in(self):
        agent = self.user("clearing_agent")
        with self.assertRaises(TypeError):
            svc.create_shipment(self.db, agent, "SHP-0001", owner_id=new_id())
        with self.assertRaises(TypeError):
            svc.create_shipment(self.db, agent, "SHP-0001", status="approved")

    def test_the_reference_is_checked(self):
        agent = self.user("clearing_agent")
        for bad in ("", "   ", None, "x" * 101):
            with self.assertRaises(BadRequest):
                svc.create_shipment(self.db, agent, bad)

    def test_the_country_is_checked_and_made_upper_case(self):
        agent = self.user("clearing_agent")
        self.assertEqual(svc.create_shipment(self.db, agent, "A", "ke")["country"], "KE")
        for bad in ("TZA", "1", "T "):
            with self.assertRaises(BadRequest):
                svc.create_shipment(self.db, agent, "B", bad)

    def test_creating_writes_an_audit_event(self):
        agent = self.user("clearing_agent")
        s = svc.create_shipment(self.db, agent, "SHP-0001")
        ev = self.events("shipment_created")
        self.assertEqual((len(ev), ev[0]["object_id"], ev[0]["user_id"]), (1, s["id"], agent["id"]))

    def test_a_failed_create_leaves_no_shipment_and_no_event(self):
        with self.assertRaises(Forbidden):
            svc.create_shipment(self.db, self.user("reviewer"), "SHP-0001")
        self.assertEqual(self.db.query_one("SELECT COUNT(*) AS n FROM shipments")["n"], 0)
        self.assertEqual(self.events("shipment_created"), [])


class TestVisibility(Case):
    def setUp(self):
        super().setUp()
        self.imp_a, self.imp_b = self.user("importer", "A"), self.user("importer", "B")
        self.agent, self.other_agent = self.user("clearing_agent"), self.user("clearing_agent")
        self.reviewer, self.admin = self.user("reviewer"), self.user("admin")
        self.s_a = svc.create_shipment(self.db, self.imp_a, "A-1")["id"]
        self.s_b = svc.create_shipment(self.db, self.imp_b, "B-1")["id"]
        self.s_agent = svc.create_shipment(self.db, self.agent, "G-1")["id"]

    def ids(self, user):
        return {s["id"] for s in svc.list_shipments(self.db, user)}

    def test_an_importer_sees_only_their_own_cases(self):
        self.assertEqual(self.ids(self.imp_a), {self.s_a})

    def test_a_clearing_agent_sees_their_own_and_assigned_cases(self):
        self.assertEqual(self.ids(self.agent), {self.s_agent})
        self.db.execute("UPDATE shipments SET assigned_agent_id = ? WHERE id = ?", (self.agent["id"], self.s_a))
        self.db.commit()
        self.assertEqual(self.ids(self.agent), {self.s_agent, self.s_a})
        self.assertEqual(self.ids(self.other_agent), set())

    def test_a_reviewer_and_an_admin_see_every_case(self):
        everything = {self.s_a, self.s_b, self.s_agent}
        self.assertEqual(self.ids(self.reviewer), everything)
        self.assertEqual(self.ids(self.admin), everything)

    def test_showing_someone_elses_case_is_not_found(self):
        with self.assertRaises(NotFound):
            svc.get_shipment(self.db, self.imp_b, self.s_a)

    def test_a_case_that_does_not_exist_gives_the_same_answer(self):
        for sid in (new_id(), "not-a-uuid", "", "1; DROP TABLE users"):
            with self.assertRaises(NotFound) as cm:
                svc.get_shipment(self.db, self.imp_a, sid)
            self.assertEqual(cm.exception.message, "Shipment not found.")

    def test_the_owner_and_a_reviewer_can_show_a_case(self):
        self.assertEqual(svc.get_shipment(self.db, self.imp_a, self.s_a)["reference"], "A-1")
        self.assertEqual(svc.get_shipment(self.db, self.reviewer, self.s_a)["id"], self.s_a)

    def test_the_list_is_newest_first(self):
        self.db.execute("UPDATE shipments SET created_at = '2026-10-01 10:00:00' WHERE id = ?", (self.s_a,))
        second = svc.create_shipment(self.db, self.imp_a, "A-2")["id"]
        self.db.execute("UPDATE shipments SET created_at = '2026-10-02 10:00:00' WHERE id = ?", (second,))
        self.db.commit()
        self.assertEqual([s["id"] for s in svc.list_shipments(self.db, self.imp_a)], [second, self.s_a])


class TestUpload(Case):
    def setUp(self):
        super().setUp()
        self.agent = self.user("clearing_agent")
        self.sid = svc.create_shipment(self.db, self.agent, "SHP-0001")["id"]

    def stored(self):
        return sorted(p.name for p in self.dir.glob("*")) if self.dir.exists() else []

    def test_a_pdf_is_stored_under_a_random_name_with_its_hash(self):
        r = self.upload(self.agent, self.sid)
        self.assertEqual((r["doc_type"], r["mime_type"], r["size_bytes"]), ("packing_list", "application/pdf", len(PDF)))
        self.assertEqual(r["file_hash"], hashlib.sha256(PDF).hexdigest())
        row = self.db.query_one("SELECT file_path, uploaded_by FROM documents WHERE id = ?", (r["id"],))
        self.assertRegex(row["file_path"], r"^[0-9a-f]{32}\.pdf$")
        self.assertEqual((self.dir / row["file_path"]).read_bytes(), PDF)
        self.assertEqual(row["uploaded_by"], self.agent["id"])

    def test_png_and_jpeg_are_accepted(self):
        self.assertEqual(self.upload(self.agent, self.sid, "commercial_invoice", PNG)["mime_type"], "image/png")
        self.assertEqual(self.upload(self.agent, self.sid, "bill_of_lading", JPEG)["mime_type"], "image/jpeg")

    def test_a_text_file_renamed_to_pdf_is_refused(self):
        with self.assertRaises(BadRequest) as cm:
            self.upload(self.agent, self.sid, content=b"this is just text, not a PDF")
        self.assertIn("PDF, PNG and JPEG", cm.exception.message)
        self.assertEqual(self.stored(), [])

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(BadRequest):
            self.upload(self.agent, self.sid, content=b"")

    def test_a_file_over_the_limit_is_refused(self):
        with self.assertRaises(BadRequest) as cm:
            self.upload(self.agent, self.sid, content=PDF + b"0" * 100, max_bytes=50)
        self.assertIn("too large", cm.exception.message)
        self.assertEqual(self.stored(), [])

    def test_the_limit_comes_from_max_upload_mb(self):
        from app.services.uploads import max_upload_bytes
        self.assertEqual(max_upload_bytes({"MAX_UPLOAD_MB": "2"}), 2 * 1024 * 1024)
        self.assertEqual(max_upload_bytes({}), 10 * 1024 * 1024)
        self.assertEqual(max_upload_bytes({"MAX_UPLOAD_MB": "abc"}), 10 * 1024 * 1024)

    def test_an_unknown_document_type_is_refused(self):
        with self.assertRaises(BadRequest):
            self.upload(self.agent, self.sid, "passport")

    def test_a_reviewer_and_an_admin_cannot_upload(self):
        for role in ("reviewer", "admin"):
            with self.assertRaises(Forbidden):
                self.upload(self.user(role), self.sid)

    def test_someone_elses_case_is_not_found_not_forbidden(self):
        with self.assertRaises(NotFound):
            self.upload(self.user("importer"), self.sid)
        with self.assertRaises(NotFound):
            self.upload(self.agent, new_id())

    def test_the_case_moves_to_documents_uploaded_when_all_three_are_there(self):
        self.upload(self.agent, self.sid, "commercial_invoice")
        self.upload(self.agent, self.sid, "packing_list")
        self.assertEqual(svc.get_shipment(self.db, self.agent, self.sid)["status"], "created")
        r = self.upload(self.agent, self.sid, "bill_of_lading")
        self.assertEqual(r["shipment_status"], "documents_uploaded")
        self.assertEqual(svc.get_shipment(self.db, self.agent, self.sid)["status"], "documents_uploaded")

    def test_uploading_again_replaces_the_document_and_its_extraction(self):
        first = self.upload(self.agent, self.sid)
        old_name = self.db.query_one("SELECT file_path FROM documents WHERE id = ?", (first["id"],))["file_path"]
        self.db.execute("INSERT INTO extractions (id, document_id, schema_version, fields_extracted) VALUES (?, ?, ?, ?)",
                        (new_id(), first["id"], "1", self.db.json_param({"packages": 500})))
        self.db.commit()
        second = self.upload(self.agent, self.sid, content=PDF + b"changed")
        self.assertTrue(second["replaced"])
        self.assertEqual(self.db.query_one("SELECT COUNT(*) AS n FROM documents WHERE shipment_id = ?", (self.sid,))["n"], 1)
        self.assertEqual(self.db.query_one("SELECT COUNT(*) AS n FROM extractions")["n"], 0)
        self.assertNotIn(old_name, self.stored())
        self.assertEqual(len(self.stored()), 1)

    def test_replacing_a_document_after_confirmation_sends_the_case_back(self):
        for t in svc.DOC_TYPES:
            self.upload(self.agent, self.sid, t)
        self.db.execute("UPDATE shipments SET status = 'confirmed' WHERE id = ?", (self.sid,))
        self.db.commit()
        self.assertEqual(self.upload(self.agent, self.sid, "packing_list", PDF + b"v2")["shipment_status"], "documents_uploaded")

    def test_an_approved_case_cannot_be_changed(self):
        self.db.execute("UPDATE shipments SET status = 'approved' WHERE id = ?", (self.sid,))
        self.db.commit()
        with self.assertRaises(Conflict):
            self.upload(self.agent, self.sid)

    def test_showing_a_case_lists_documents_without_the_stored_file_path(self):
        self.upload(self.agent, self.sid)
        shown = svc.get_shipment(self.db, self.agent, self.sid)
        self.assertEqual(len(shown["documents"]), 1)
        self.assertNotIn("file_path", shown["documents"][0])
        self.assertEqual(shown["documents"][0]["doc_type"], "packing_list")

    def test_uploading_writes_an_audit_event_without_the_file_name(self):
        r = self.upload(self.agent, self.sid)
        ev = self.events("document_uploaded")
        self.assertEqual((len(ev), ev[0]["object_id"]), (1, r["id"]))
        self.assertNotIn(".pdf", ev[0]["details"])

    def test_a_database_failure_leaves_no_orphan_file(self):
        original = svc.audit
        svc.audit = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("audit failed"))
        try:
            with self.assertRaises(RuntimeError):
                self.upload(self.agent, self.sid)
        finally:
            svc.audit = original
        self.assertEqual(self.stored(), [])
        self.assertEqual(self.db.query_one("SELECT COUNT(*) AS n FROM documents")["n"], 0)


class TestAuditHelper(Case):
    def test_an_event_can_be_written_without_a_user(self):
        audit(self.db, None, "login_failed", details={"reason": "unknown email"})
        self.db.commit()
        self.assertIsNone(self.events("login_failed")[0]["user_id"])


if __name__ == "__main__":
    unittest.main()

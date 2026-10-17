"""Ownership over real HTTP: real tokens, real routes, a throwaway database file.
Proves that the 404 for someone else's case holds at the endpoint, not just in the service functions."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (puts backend/ on sys.path)
from fastapi.testclient import TestClient

from app.db.database import Database, new_id
from app.db.migrate import migrate
from app.main import app
from app.services.auth import hash_password

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PASSWORD = "a-long-test-password-123"


class OwnerOverHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        db_file = root / "test.db"
        # set after the app is imported, so nothing in .env can overwrite these values
        patcher = mock.patch.dict(os.environ, {
            "DATABASE_URL": f"sqlite:///{db_file}",
            "SECRET_KEY": "test-secret-" + "x" * 32,
            "UPLOAD_DIR": str(root / "uploads"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)

        db = Database.connect(os.environ["DATABASE_URL"])
        migrate(db, out=lambda *a: None)
        self.emails = {}
        for key, role in (("a", "importer"), ("b", "importer"), ("reviewer", "reviewer")):
            email = f"{key}-{new_id()}@example.com"
            db.execute("INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                       (new_id(), key, email, hash_password(PASSWORD), role))
            self.emails[key] = email
        db.commit()
        db.close()

        self.client = TestClient(app)
        self.addCleanup(self.tmp.cleanup)

    def login(self, key):
        r = self.client.post("/auth/login", json={"email": self.emails[key], "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    def make_case(self, headers):
        r = self.client.post("/shipments", json={"reference": "TEST-1"}, headers=headers)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["id"]

    def upload(self, shipment_id, headers):
        return self.client.post(f"/shipments/{shipment_id}/documents", headers=headers,
                                data={"doc_type": "packing_list"},
                                files={"file": ("p.pdf", PDF, "application/pdf")})

    # ---- positive controls: if these fail, the other tests prove nothing ----
    def test_the_owner_can_read_and_upload(self):
        a = self.login("a")
        sid = self.make_case(a)
        self.assertEqual(self.client.get(f"/shipments/{sid}", headers=a).status_code, 200)
        self.assertEqual(self.upload(sid, a).status_code, 201)

    # ---- the real tests ----
    def test_another_importer_gets_404_on_show(self):
        a, b = self.login("a"), self.login("b")
        sid = self.make_case(a)
        r = self.client.get(f"/shipments/{sid}", headers=b)
        self.assertEqual(r.status_code, 404)
        missing = self.client.get(f"/shipments/{new_id()}", headers=b)
        self.assertEqual(r.json(), missing.json(), "not-yours must look identical to does-not-exist")

    def test_another_importer_gets_404_on_upload_and_nothing_is_attached(self):
        a, b = self.login("a"), self.login("b")
        sid = self.make_case(a)
        self.assertEqual(self.upload(sid, b).status_code, 404)
        self.assertEqual(self.client.get(f"/shipments/{sid}", headers=a).json()["documents"], [])

    def test_the_list_hides_other_peoples_cases(self):
        a, b = self.login("a"), self.login("b")
        sid = self.make_case(a)
        self.assertNotIn(sid, [s["id"] for s in self.client.get("/shipments", headers=b).json()])
        self.assertIn(sid, [s["id"] for s in self.client.get("/shipments", headers=a).json()])

    def test_the_owner_cannot_be_set_from_the_request(self):
        a = self.login("a")
        r = self.client.post("/shipments", json={"reference": "X", "owner_id": "someone-else"}, headers=a)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.get(f"/shipments/{r.json()['id']}", headers=self.login("b")).status_code, 404)

    def test_no_token_is_401_everywhere(self):
        sid = self.make_case(self.login("a"))
        self.assertEqual(self.client.get("/shipments").status_code, 401)
        self.assertEqual(self.client.get(f"/shipments/{sid}").status_code, 401)
        r = self.client.post(f"/shipments/{sid}/documents", data={"doc_type": "packing_list"},
                             files={"file": ("p.pdf", PDF, "application/pdf")})
        self.assertEqual(r.status_code, 401)

    def test_a_reviewer_can_read_but_not_upload(self):
        sid = self.make_case(self.login("a"))
        rv = self.login("reviewer")
        self.assertEqual(self.client.get(f"/shipments/{sid}", headers=rv).status_code, 200)
        self.assertEqual(self.upload(sid, rv).status_code, 403)


if __name__ == "__main__":
    unittest.main()
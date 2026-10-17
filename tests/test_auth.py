import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import jwt  # noqa: E402
from app.errors import Unauthorized  # noqa: E402
from app.services import auth  # noqa: E402


class AuthTests(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("SECRET_KEY", "TOKEN_EXPIRE_MINUTES")}
        os.environ["SECRET_KEY"] = "x" * 48
        os.environ["TOKEN_EXPIRE_MINUTES"] = "30"

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_password_round_trip(self):
        h = auth.hash_password("correct horse battery")
        self.assertNotIn("correct horse", h)
        self.assertTrue(auth.verify_password("correct horse battery", h))
        self.assertFalse(auth.verify_password("wrong password", h))

    def test_placeholder_hash_never_verifies(self):
        self.assertFalse(auth.verify_password("anything", "!placeholder-not-a-real-hash"))

    def test_token_round_trip(self):
        self.assertEqual(auth.read_token(auth.create_token("user-1")), "user-1")

    def test_expired_token_is_rejected(self):
        old = auth.create_token("user-1", now=int(time.time()) - 7200)
        with self.assertRaises(Unauthorized):
            auth.read_token(old)

    def test_tampered_token_is_rejected(self):
        head, payload, sig = auth.create_token("user-1").split(".")
        with self.assertRaises(Unauthorized):
            auth.read_token(".".join([head, payload, "A" * len(sig)]))

    def test_token_from_another_key_is_rejected(self):
        token = auth.create_token("user-1")
        os.environ["SECRET_KEY"] = "y" * 48
        with self.assertRaises(Unauthorized):
            auth.read_token(token)

    def test_unsigned_token_is_rejected(self):
        forged = jwt.encode({"sub": "admin", "exp": int(time.time()) + 600}, key="", algorithm="none")
        with self.assertRaises(Unauthorized):
            auth.read_token(forged)

    def test_weak_secret_is_refused(self):
        os.environ["SECRET_KEY"] = "short"
        with self.assertRaises(RuntimeError):
            auth.create_token("user-1")


if __name__ == "__main__":
    unittest.main()
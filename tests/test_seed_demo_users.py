import importlib.util
import unittest
from pathlib import Path

import helpers
from app.db.database import Database
from app.db.migrate import migrate

spec = importlib.util.spec_from_file_location("seed_demo_users", helpers.ROOT / "backend" / "scripts" / "seed_demo_users.py")
seed_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_module)


class TestSeed(unittest.TestCase):
    def setUp(self):
        self.db = Database.connect("sqlite:///:memory:")
        migrate(self.db, out=lambda *a: None)

    def test_one_user_per_role_and_running_twice_adds_nothing(self):
        self.assertEqual(len(seed_module.seed(self.db)), 4)
        self.assertEqual(seed_module.seed(self.db), [])
        roles = {r["role"] for r in self.db.query("SELECT role FROM users")}
        self.assertEqual(roles, {"importer", "clearing_agent", "reviewer", "admin"})

    def test_the_hash_is_a_placeholder_that_cannot_be_a_real_password_hash(self):
        seed_module.seed(self.db)
        for r in self.db.query("SELECT password_hash FROM users"):
            self.assertTrue(r["password_hash"].startswith("!"))


if __name__ == "__main__":
    unittest.main()

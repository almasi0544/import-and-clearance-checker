import json
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
from fake_evolus import FakeEvolus
from app.services.evolus_client import EvolusClient, EvolusError, RateLimiter
from app.services.run_extraction import run

IDS = {"EXT_INV": "commercial_invoice", "EXT_PL": "packing_list", "EXT_BL": "bill_of_lading"}
ENV = {"EVOLUS_API_KEY": "secret-key-123", "EVOLUS_APPLICATION_ID": "app-1", "EVOLUS_AGENT_ID": "AG1",
       "EVOLUS_EXTRACTOR_INVOICE_ID": "EXT_INV", "EVOLUS_EXTRACTOR_PACKING_LIST_ID": "EXT_PL",
       "EVOLUS_EXTRACTOR_BILL_OF_LADING_ID": "EXT_BL"}


class TestRunExtraction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(helpers.ROOT / "test-data" / "set05", self.root / "test-data" / "set05")
        self.lines = []

    def tearDown(self):
        self.tmp.cleanup()

    def serve(self, tweak=None):
        docs = helpers.load_documents(5)

        def handler(request):
            doc_type = IDS[request["path"].split("/json/")[1].split("/")[0]]
            data = json.loads(json.dumps(docs[doc_type]))
            if tweak:
                tweak(doc_type, data)
            return 200, data

        server = FakeEvolus(handler=handler).start()
        self.addCleanup(server.stop)
        client = EvolusClient("secret-key-123", "app-1", base_url=server.base_url, agent_id="AG1", limiter=RateLimiter(1000))
        return server, client

    def go(self, client, **kw):
        return run(5, ENV, self.root, client=client, out=self.lines.append, **kw)

    def test_runs_all_three_documents_and_everything_matches(self):
        server, client = self.serve()
        result = self.go(client)
        self.assertEqual(len(server.requests), 3)
        for doc_type, r in result["results"].items():
            self.assertEqual(r["summary"]["wrong"], [], doc_type)
        self.assertEqual(len(result["calls"]), 3)

    def test_saves_the_json_under_local(self):
        _, client = self.serve()
        self.go(client)
        saved = self.root / ".local" / "extractions" / "set05" / "packing_list.json"
        self.assertEqual(json.loads(saved.read_text())["document_type"], "packing_list")

    def test_a_misread_field_is_reported(self):
        def tweak(doc_type, data):
            if doc_type == "bill_of_lading":
                data["gross_weight"] = 2000
        _, client = self.serve(tweak)
        wrong = self.go(client)["results"]["bill_of_lading"]["summary"]["wrong"]
        self.assertEqual([w["field"] for w in wrong], ["gross_weight"])
        self.assertEqual((wrong[0]["expected"], wrong[0]["actual"]), (2700, 2000))

    def test_dry_run_calls_nothing_and_reports_missing_settings(self):
        env = dict(ENV)
        del env["EVOLUS_EXTRACTOR_PACKING_LIST_ID"]
        result = run(5, env, self.root, dry_run=True, out=self.lines.append)
        self.assertEqual(result["missing"], ["EVOLUS_EXTRACTOR_PACKING_LIST_ID"])
        self.assertTrue(any("NOT SET" in line for line in self.lines))
        self.assertFalse(any("secret-key-123" in line for line in self.lines))

    def test_missing_settings_stop_the_run_with_a_clear_message(self):
        with self.assertRaises(EvolusError) as cm:
            run(5, {"EVOLUS_API_KEY": "secret-key-123"}, self.root, out=self.lines.append)
        self.assertIn("EVOLUS_APPLICATION_ID", str(cm.exception))
        self.assertNotIn("secret-key-123", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

import helpers  # noqa: F401  (puts backend on the path)
from fake_evolus import FakeEvolus
from app.services.evolus_client import EvolusClient, EvolusError, RateLimiter

KEY = "secret-key-123"


class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


class TestEvolusClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "doc.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 test document")
        self.sleeps = []
        self.servers = []

    def tearDown(self):
        for s in self.servers:
            s.stop()
        self.tmp.cleanup()

    def server(self, *responses, handler=None):
        s = FakeEvolus(responses, handler).start()
        self.servers.append(s)
        return s

    def client(self, server, **kw):
        return EvolusClient(KEY, "app-1", base_url=server.base_url, agent_id="AG1", sleep=self.sleeps.append,
                            limiter=RateLimiter(max_calls=1000), **kw)

    # what is sent
    def test_sends_headers_params_and_file(self):
        s = self.server((200, {"hello": "world"}))
        data = self.client(s).extract("EX1", self.pdf)
        self.assertEqual(data, {"hello": "world"})
        req = s.requests[0]
        self.assertEqual(req["path"], "/api/v1/agents/AG1/json/EX1/ask-file")
        self.assertEqual(req["query"], "useWebhook=false")
        self.assertEqual(req["headers"]["x-apikey"], KEY)
        self.assertEqual(req["headers"]["x-application-id"], "app-1")
        self.assertIn("multipart/form-data", req["headers"]["content-type"])
        self.assertIn(b"%PDF-1.4 test document", req["body"])

    def test_the_extract_path_can_be_changed(self):
        s = self.server((200, {}))
        self.client(s, extract_path="/extractors/{extractor_id}/run").extract("EX9", self.pdf)
        self.assertEqual(s.requests[0]["path"], "/api/v1/extractors/EX9/run")

    # the call record
    def test_each_call_is_recorded_without_secrets(self):
        s = self.server((200, {"a": 1}))
        seen = []
        c = self.client(s, on_call=seen.append)
        c.extract("EX1", self.pdf, shipment_id="SHP-1", document_id="D1")
        rec = c.calls[0].to_dict()
        self.assertEqual((rec["endpoint"], rec["http_status"], rec["ok"]), ("/agents/AG1/json/EX1/ask-file", 200, True))
        self.assertEqual((rec["shipment_id"], rec["document_id"]), ("SHP-1", "D1"))
        self.assertGreaterEqual(rec["duration_ms"], 0)
        self.assertNotIn(KEY, str(rec))
        self.assertEqual(len(seen), 1)

    def test_the_key_is_not_shown_in_repr(self):
        self.assertNotIn(KEY, repr(EvolusClient(KEY, "app-1")))

    # errors that must not be retried
    def test_401_gives_a_clear_message_and_no_retry(self):
        s = self.server((401, {"error": "no"}))
        c = self.client(s)
        with self.assertRaises(EvolusError) as cm:
            c.extract("EX1", self.pdf)
        self.assertEqual(cm.exception.status_code, 401)
        self.assertIn("EVOLUS_API_KEY", str(cm.exception))
        self.assertEqual(len(s.requests), 1)
        self.assertFalse(c.calls[0].ok)

    def test_402_means_credits_have_run_out(self):
        s = self.server((402, {}))
        with self.assertRaises(EvolusError) as cm:
            self.client(s).extract("EX1", self.pdf)
        self.assertIn("credits", str(cm.exception))
        self.assertEqual(len(s.requests), 1)

    def test_404_points_to_the_ids(self):
        s = self.server((404, {}))
        with self.assertRaises(EvolusError) as cm:
            self.client(s).extract("EX1", self.pdf)
        self.assertIn("EVOLUS_EXTRACT_PATH", str(cm.exception))

    # retries
    def test_a_500_is_retried_and_then_succeeds(self):
        s = self.server((500, {}), (200, {"ok": True}))
        c = self.client(s)
        self.assertEqual(c.extract("EX1", self.pdf), {"ok": True})
        self.assertEqual(len(s.requests), 2)
        self.assertEqual([r.http_status for r in c.calls], [500, 200])
        self.assertEqual(self.sleeps, [1])

    def test_gives_up_after_the_retries(self):
        s = self.server((503, {}))
        with self.assertRaises(EvolusError) as cm:
            self.client(s, max_retries=2).extract("EX1", self.pdf)
        self.assertEqual(cm.exception.status_code, 503)
        self.assertEqual(len(s.requests), 3)

    def test_a_429_waits_for_retry_after(self):
        s = self.server((429, {}, {"Retry-After": "3"}), (200, {"ok": True}))
        self.client(s).extract("EX1", self.pdf)
        self.assertEqual(self.sleeps, [3])

    def test_a_timeout_is_retried_then_reported(self):
        session = mock.Mock()
        session.post.side_effect = requests.Timeout()
        c = EvolusClient(KEY, "app-1", agent_id="AG1", session=session, sleep=self.sleeps.append, limiter=RateLimiter(1000))
        with self.assertRaises(EvolusError) as cm:
            c.extract("EX1", self.pdf)
        self.assertIn("in time", str(cm.exception))
        self.assertEqual(session.post.call_count, 3)
        self.assertEqual([r.error for r in c.calls], ["timeout"] * 3)

    def test_a_connection_error_is_reported(self):
        session = mock.Mock()
        session.post.side_effect = requests.ConnectionError()
        c = EvolusClient(KEY, "app-1", agent_id="AG1", session=session, sleep=self.sleeps.append, limiter=RateLimiter(1000))
        with self.assertRaises(EvolusError) as cm:
            c.extract("EX1", self.pdf)
        self.assertIn("Could not reach Evolus", str(cm.exception))

    # bad answers and bad input
    def test_an_answer_that_is_not_json_is_an_error(self):
        s = self.server((200, "this is not json"))
        with self.assertRaises(EvolusError) as cm:
            self.client(s).extract("EX1", self.pdf)
        self.assertIn("valid JSON", str(cm.exception))

    def test_a_missing_file_fails_before_any_call(self):
        s = self.server((200, {}))
        c = self.client(s)
        with self.assertRaises(EvolusError):
            c.extract("EX1", Path(self.tmp.name) / "nope.pdf")
        self.assertEqual(s.requests, [])
        self.assertEqual(c.calls, [])

    def test_from_env_names_the_missing_variables(self):
        with self.assertRaises(EvolusError) as cm:
            EvolusClient.from_env({"EVOLUS_API_KEY": KEY})
        self.assertIn("EVOLUS_APPLICATION_ID", str(cm.exception))
        self.assertNotIn(KEY, str(cm.exception))

    def test_from_env_reads_the_settings(self):
        c = EvolusClient.from_env({"EVOLUS_API_KEY": KEY, "EVOLUS_APPLICATION_ID": "app-1", "EVOLUS_AGENT_ID": "AG1",
                                   "EVOLUS_BASE_URL": "http://x/api/v1/"})
        self.assertEqual((c.base_url, c.agent_id, c.application_id), ("http://x/api/v1", "AG1", "app-1"))


class TestRateLimiter(unittest.TestCase):
    def test_waits_when_the_limit_is_reached(self):
        clock = Clock()
        limiter = RateLimiter(max_calls=3, period=60, clock=clock, sleep=clock.sleep)
        for _ in range(3):
            limiter.wait()
        self.assertEqual(clock.slept, [])
        clock.t += 20
        limiter.wait()
        self.assertEqual(clock.slept, [40])

    def test_does_not_wait_when_the_window_has_passed(self):
        clock = Clock()
        limiter = RateLimiter(max_calls=2, period=60, clock=clock, sleep=clock.sleep)
        limiter.wait()
        limiter.wait()
        clock.t += 61
        limiter.wait()
        self.assertEqual(clock.slept, [])


if __name__ == "__main__":
    unittest.main()

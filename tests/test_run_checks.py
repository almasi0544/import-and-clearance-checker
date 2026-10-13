"""Runs C3 and C4 on all ten synthetic sets and compares with the answer key
(the expected_check_outcomes in each setNN_expected.json)."""
import unittest

import helpers
from app.engine.checks import findings_from, run_checks

KEY_TO_OUTCOME = {"pass": "pass", "FINDING": "finding", "skip": "skipped_not_present"}


class TestAgainstTheAnswerKey(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    def test_c3_and_c4_match_the_answer_key_on_every_set(self):
        for n in range(1, 11):
            data = helpers.load_set(n)
            results = {r.check_id: r for r in run_checks(data["documents"], self.rules)}
            for check_id in ("C3", "C4"):
                expected = KEY_TO_OUTCOME[data["expected_check_outcomes"][check_id]]
                self.assertEqual(results[check_id].outcome, expected, f"set {n}, {check_id}")

    def test_clean_sets_give_no_findings(self):
        for n in (1, 2, 3):
            self.assertEqual(findings_from(run_checks(helpers.load_documents(n), self.rules)), [], f"set {n}")

    def test_set_5_gives_exactly_one_finding_c3(self):
        found = findings_from(run_checks(helpers.load_documents(5), self.rules))
        self.assertEqual([f.check_id for f in found], ["C3"])
        self.assertEqual(found[0].to_dict()["severity"], "high")


if __name__ == "__main__":
    unittest.main()

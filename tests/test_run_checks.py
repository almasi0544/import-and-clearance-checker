"""Runs the checks on all ten synthetic sets and compares with the answer key
(the expected_check_outcomes and expected_findings in each setNN_expected.json)."""
import unittest

import helpers
from app.engine.checks import CHECKS, findings_from, run_checks

KEY_TO_OUTCOME = {"pass": "pass", "FINDING": "finding", "skip": "skipped_not_present"}
IMPLEMENTED = ["C1", "C2", "C3", "C4", "C5", "C6"]


class TestAgainstTheAnswerKey(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    def test_the_implemented_checks_run_in_order(self):
        self.assertEqual([r.check_id for r in run_checks(helpers.load_documents(1), self.rules)], IMPLEMENTED)
        self.assertEqual(len(CHECKS), len(IMPLEMENTED))

    def test_every_implemented_check_matches_the_answer_key_on_every_set(self):
        for n in range(1, 11):
            data = helpers.load_set(n)
            results = {r.check_id: r for r in run_checks(data["documents"], self.rules)}
            for check_id in IMPLEMENTED:
                expected = KEY_TO_OUTCOME[data["expected_check_outcomes"][check_id]]
                self.assertEqual(results[check_id].outcome, expected, f"set {n}, {check_id}")

    def test_the_findings_are_the_planted_errors_and_nothing_else(self):
        for n in range(1, 11):
            data = helpers.load_set(n)
            expected = sorted({f["check_id"] for f in data["expected_findings"] if f["check_id"] in IMPLEMENTED})
            found = sorted({f.check_id for f in findings_from(run_checks(data["documents"], self.rules))})
            self.assertEqual(found, expected, f"set {n}")

    def test_clean_sets_give_no_findings(self):
        for n in (1, 2, 3):
            self.assertEqual(findings_from(run_checks(helpers.load_documents(n), self.rules)), [], f"set {n}")

    def test_set_5_gives_exactly_one_finding_c3(self):
        found = findings_from(run_checks(helpers.load_documents(5), self.rules))
        self.assertEqual([f.check_id for f in found], ["C3"])
        self.assertEqual(found[0].to_dict()["severity"], "high")

    def test_set_7_gives_two_c1_findings_and_set_8_gives_one_c6_finding(self):
        self.assertEqual([f.check_id for f in findings_from(run_checks(helpers.load_documents(7), self.rules))], ["C1", "C1"])
        self.assertEqual([f.check_id for f in findings_from(run_checks(helpers.load_documents(8), self.rules))], ["C6"])


if __name__ == "__main__":
    unittest.main()

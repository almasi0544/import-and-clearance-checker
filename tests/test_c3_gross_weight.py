import unittest

import helpers
from app.engine.checks import check_c3


def docs(pl_gross=850, bl_gross=850, pl_unit="kg", bl_unit="kg"):
    return {
        "packing_list": {"total_gross_weight": pl_gross, "weight_unit": pl_unit},
        "bill_of_lading": {"gross_weight": bl_gross, "weight_unit": bl_unit},
    }


class TestC3GrossWeight(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    # values equal
    def test_equal_weights_pass(self):
        r = check_c3(docs(850, 850), self.rules)
        self.assertEqual(r.outcome, "pass")
        self.assertIsNone(r.finding)

    def test_clean_set_1_passes(self):
        self.assertEqual(check_c3(helpers.load_documents(1), self.rules).outcome, "pass")

    # values different
    def test_set_5_gives_a_high_finding(self):
        r = check_c3(helpers.load_documents(5), self.rules)
        self.assertEqual(r.outcome, "finding")
        f = r.finding
        self.assertEqual((f.check_id, f.severity, f.field), ("C3", "high", "gross_weight"))
        self.assertEqual(f.documents, ["packing_list", "bill_of_lading"])
        self.assertEqual(f.values, {"packing_list": 2500, "bill_of_lading": 2700})
        self.assertEqual(
            f.message,
            "Gross weight differs by 200 kg (8 percent): 2500 kg on the packing list, 2700 kg on the bill of lading.")

    def test_percent_is_measured_against_the_packing_list(self):
        r = check_c3(docs(200, 100), self.rules)
        self.assertIn("(50 percent)", r.finding.message)

    # field missing
    def test_missing_value_is_skipped_not_a_finding(self):
        for d in (docs(None, 850), docs(850, None)):
            r = check_c3(d, self.rules)
            self.assertEqual(r.outcome, "skipped_not_present")
            self.assertIsNone(r.finding)

    def test_missing_key_or_document_is_skipped(self):
        self.assertEqual(check_c3({"packing_list": {}, "bill_of_lading": {}}, self.rules).outcome, "skipped_not_present")
        self.assertEqual(check_c3({}, self.rules).outcome, "skipped_not_present")

    # tolerance
    def test_exactly_at_the_tolerance_passes(self):
        self.assertEqual(check_c3(docs(1000, 1010), self.rules).outcome, "pass")

    def test_just_over_the_tolerance_is_a_finding(self):
        self.assertEqual(check_c3(docs(1000, 1010.1), self.rules).outcome, "finding")

    def test_tolerance_comes_from_the_rule_pack(self):
        wide = dict(self.rules, weight_tolerance_percent=10)
        self.assertEqual(check_c3(helpers.load_documents(5), wide).outcome, "pass")

    # units
    def test_pounds_are_converted_to_kilograms(self):
        self.assertEqual(check_c3(docs(2204.62262, 1000, pl_unit="lb"), self.rules).outcome, "pass")

    def test_pounds_against_the_same_number_of_kilograms_is_a_finding(self):
        r = check_c3(docs(100, 100, pl_unit="lb"), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertIn("45.36 kg on the packing list", r.finding.message)

    def test_unknown_unit_cannot_be_compared(self):
        r = check_c3(docs(850, 850, pl_unit=None), self.rules)
        self.assertEqual(r.outcome, "cannot_compare")
        self.assertEqual(r.finding.severity, "low")


if __name__ == "__main__":
    unittest.main()

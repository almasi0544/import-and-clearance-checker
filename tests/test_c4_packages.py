import unittest

import helpers
from app.engine.checks import check_c4


def docs(pl_n=500, pl_type="carton", bl_n=500, bl_type="carton"):
    return {
        "packing_list": {"packages": pl_n, "package_type": pl_type},
        "bill_of_lading": {"packages": bl_n, "package_type": bl_type},
    }


class TestC4Packages(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    # values equal
    def test_equal_counts_pass(self):
        r = check_c4(docs(), self.rules)
        self.assertEqual(r.outcome, "pass")
        self.assertIsNone(r.finding)

    def test_clean_sets_pass(self):
        for n in (1, 2, 3, 10):
            self.assertEqual(check_c4(helpers.load_documents(n), self.rules).outcome, "pass", f"set {n}")

    def test_same_type_written_differently_is_still_the_same_type(self):
        self.assertEqual(check_c4(docs(500, "cartons", 500, "Carton"), self.rules).outcome, "pass")
        self.assertEqual(check_c4(docs(500, "ctns", 500, "carton"), self.rules).outcome, "pass")

    def test_a_whole_number_written_as_a_decimal_is_equal(self):
        self.assertEqual(check_c4(docs(500.0, "carton", 500, "carton"), self.rules).outcome, "pass")

    # values different
    def test_set_4_gives_a_high_finding(self):
        r = check_c4(helpers.load_documents(4), self.rules)
        self.assertEqual(r.outcome, "finding")
        f = r.finding
        self.assertEqual((f.check_id, f.severity, f.field), ("C4", "high", "packages"))
        self.assertEqual(f.documents, ["packing_list", "bill_of_lading"])
        self.assertEqual(f.values, {"packing_list": 500, "bill_of_lading": 470})
        self.assertEqual(f.message, "Number of packages differs: 500 on the packing list, 470 on the bill of lading.")

    def test_different_counts_with_differently_written_types_are_a_finding(self):
        self.assertEqual(check_c4(docs(500, "ctns", 470, "carton"), self.rules).outcome, "finding")

    # field missing
    def test_missing_count_is_skipped_not_a_finding(self):
        for d in (docs(None, "carton", 500, "carton"), docs(500, "carton", None, "carton")):
            r = check_c4(d, self.rules)
            self.assertEqual(r.outcome, "skipped_not_present")
            self.assertIsNone(r.finding)

    def test_missing_key_or_document_is_skipped(self):
        self.assertEqual(check_c4({"packing_list": {}, "bill_of_lading": {}}, self.rules).outcome, "skipped_not_present")
        self.assertEqual(check_c4({}, self.rules).outcome, "skipped_not_present")

    # different package types
    def test_pallets_against_cartons_cannot_be_compared(self):
        r = check_c4(docs(2, "pallet", 25, "carton"), self.rules)
        self.assertEqual(r.outcome, "cannot_compare")
        self.assertEqual(r.finding.severity, "low")
        self.assertEqual(
            r.finding.message,
            "Packages cannot be compared: 2 pallets on the packing list, 25 cartons on the bill of lading. Please confirm.")

    def test_a_count_of_one_uses_the_singular(self):
        r = check_c4(docs(1, "pallet", 10, "carton"), self.rules)
        self.assertIn("1 pallet on the packing list", r.finding.message)

    def test_equal_numbers_with_different_types_still_cannot_be_compared(self):
        self.assertEqual(check_c4(docs(10, "pallet", 10, "carton"), self.rules).outcome, "cannot_compare")

    # missing type: the counts are compared as they are
    def test_unknown_type_with_equal_counts_passes(self):
        self.assertEqual(check_c4(docs(500, None, 500, "carton"), self.rules).outcome, "pass")

    def test_unknown_type_with_different_counts_is_a_high_finding(self):
        r = check_c4(docs(500, None, 470, "carton"), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertEqual(r.finding.severity, "high")


if __name__ == "__main__":
    unittest.main()

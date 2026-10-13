import unittest

import helpers
from app.engine.checks import check_c5


def docs(inv_lines, pl_lines):
    return {"commercial_invoice": {"lines": inv_lines}, "packing_list": {"lines": pl_lines}}


def line(q, unit="pcs"):
    return {"quantity": q, "unit": unit}


class TestC5Quantity(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    # values equal
    def test_equal_quantities_pass(self):
        r = check_c5(docs([line(5000)], [line(5000)]), self.rules)
        self.assertEqual((r.outcome, r.findings), ("pass", []))

    def test_clean_sets_pass_including_the_long_item_list(self):
        for n in (1, 2, 3, 4, 5, 7, 8, 9, 10):
            self.assertEqual(check_c5(helpers.load_documents(n), self.rules).outcome, "pass", f"set {n}")

    def test_several_lines_are_added_up(self):
        r = check_c5(docs([line(3000), line(2000)], [line(5000)]), self.rules)
        self.assertEqual(r.outcome, "pass")

    def test_unit_spelling_does_not_matter(self):
        self.assertEqual(check_c5(docs([line(10, "pcs")], [line(10, "Pieces")]), self.rules).outcome, "pass")
        self.assertEqual(check_c5(docs([line(10, "set")], [line(10, "sets")]), self.rules).outcome, "pass")

    # values different
    def test_set_6_gives_a_high_finding(self):
        r = check_c5(helpers.load_documents(6), self.rules)
        self.assertEqual(r.outcome, "finding")
        f = r.finding
        self.assertEqual((f.check_id, f.severity, f.field), ("C5", "high", "quantity"))
        self.assertEqual(f.documents, ["commercial_invoice", "packing_list"])
        self.assertEqual(f.values, {"commercial_invoice": 5000, "packing_list": 4800})
        self.assertEqual(f.message, "Quantity differs: 5000 on the invoice, 4800 on the packing list.")

    def test_one_unit_that_differs_is_named_when_there_are_several_units(self):
        r = check_c5(docs([line(10, "pcs"), line(5, "sets")], [line(10, "pcs"), line(4, "sets")]), self.rules)
        self.assertEqual(len(r.findings), 1)
        self.assertEqual(r.finding.message, "Quantity differs (set): 5 on the invoice, 4 on the packing list.")

    # field missing
    def test_missing_lines_are_skipped_not_a_finding(self):
        for d in (docs([], [line(5)]), docs([line(5)], []), {}):
            r = check_c5(d, self.rules)
            self.assertEqual((r.outcome, r.findings), ("skipped_not_present", []))

    def test_a_line_without_a_quantity_makes_the_total_unreliable_so_it_is_skipped(self):
        r = check_c5(docs([line(3000), line(None)], [line(3000)]), self.rules)
        self.assertEqual(r.outcome, "skipped_not_present")

    # units
    def test_pieces_against_sets_cannot_be_compared(self):
        r = check_c5(docs([line(5000, "pcs")], [line(5000, "sets")]), self.rules)
        self.assertEqual(r.outcome, "cannot_compare")
        self.assertEqual(r.finding.severity, "low")
        self.assertEqual(r.finding.message,
                         "Quantity cannot be compared: 5000 pieces on the invoice, 5000 sets on the packing list. Please confirm.")

    def test_a_missing_unit_means_the_totals_are_compared_as_they_are(self):
        self.assertEqual(check_c5(docs([line(5000, None)], [line(5000, "pcs")]), self.rules).outcome, "pass")
        self.assertEqual(check_c5(docs([line(5000, None)], [line(4800, "pcs")]), self.rules).outcome, "finding")


if __name__ == "__main__":
    unittest.main()

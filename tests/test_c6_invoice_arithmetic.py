import unittest

import helpers
from app.engine.checks import check_c6


def invoice(lines, subtotal=None, total_value=None):
    return {"commercial_invoice": {"lines": lines, "subtotal": subtotal, "total_value": total_value}}


def line(q, price, total):
    return {"quantity": q, "unit_price": price, "line_total": total}


class TestC6InvoiceArithmetic(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    # values equal
    def test_correct_arithmetic_passes(self):
        r = check_c6(invoice([line(5000, 0.84, 4200)], 4200, 4200), self.rules)
        self.assertEqual((r.outcome, r.findings), ("pass", []))

    def test_clean_sets_pass_including_the_twelve_line_invoice(self):
        for n in (1, 2, 3, 4, 5, 6, 7, 9, 10):
            self.assertEqual(check_c6(helpers.load_documents(n), self.rules).outcome, "pass", f"set {n}")

    def test_subtotal_is_used_when_the_total_includes_tax(self):
        r = check_c6(invoice([line(1, 2500, 2500), line(1, 1750, 1750)], subtotal=4250, total_value=4600.63), self.rules)
        self.assertEqual(r.outcome, "pass")

    # values different
    def test_set_8_gives_one_finding_for_the_wrong_line_only(self):
        r = check_c6(helpers.load_documents(8), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertEqual(len(r.findings), 1)
        f = r.finding
        self.assertEqual((f.check_id, f.severity, f.field), ("C6", "high", "lines[2].line_total"))
        self.assertEqual(f.documents, ["commercial_invoice"])
        self.assertEqual(f.values, {"quantity": 500, "unit_price": 8.4, "expected": 4200, "stated": 4500})
        self.assertEqual(f.message, "Invoice line 2: 500 x 8.4 is 4200, but the line total is 4500.")

    def test_lines_that_do_not_add_up_to_the_total_are_a_finding(self):
        r = check_c6(invoice([line(1, 100, 100), line(1, 200, 200)], total_value=350), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertEqual(r.finding.field, "total_value")
        self.assertEqual(r.finding.message, "Invoice lines add up to 300, but the stated total is 350.")

    def test_the_subtotal_wording_is_used_when_the_subtotal_is_wrong(self):
        r = check_c6(invoice([line(1, 100, 100)], subtotal=120, total_value=120), self.rules)
        self.assertEqual(r.finding.message, "Invoice lines add up to 100, but the stated subtotal is 120.")

    def test_a_wrong_line_and_a_wrong_total_give_two_findings(self):
        r = check_c6(invoice([line(2, 10, 25)], total_value=30), self.rules)
        self.assertEqual([f.field for f in r.findings], ["lines[1].line_total", "total_value"])

    # tolerance
    def test_a_difference_of_one_cent_passes_and_two_cents_is_a_finding(self):
        self.assertEqual(check_c6(invoice([line(1, 10, 10.01)], total_value=10.01), self.rules).outcome, "pass")
        self.assertEqual(check_c6(invoice([line(1, 10, 10.02)], total_value=10.02), self.rules).outcome, "finding")

    def test_the_tolerance_comes_from_the_rule_pack(self):
        wide = dict(self.rules, money_tolerance=1)
        self.assertEqual(check_c6(invoice([line(1, 10, 10.5)], total_value=10.5), wide).outcome, "pass")

    # field missing
    def test_no_lines_is_skipped_not_a_finding(self):
        for d in (invoice([], total_value=100), {}):
            r = check_c6(d, self.rules)
            self.assertEqual((r.outcome, r.findings), ("skipped_not_present", []))

    def test_a_line_with_a_missing_number_is_skipped_not_a_finding(self):
        r = check_c6(invoice([line(5, None, 50)]), self.rules)
        self.assertEqual(r.outcome, "skipped_not_present")

    def test_a_missing_line_total_skips_the_total_check_but_still_checks_other_lines(self):
        r = check_c6(invoice([line(2, 10, 20), line(3, 10, None)], total_value=999), self.rules)
        self.assertEqual(r.outcome, "pass")

    def test_a_missing_total_still_checks_each_line(self):
        r = check_c6(invoice([line(2, 10, 25)]), self.rules)
        self.assertEqual(r.outcome, "finding")


if __name__ == "__main__":
    unittest.main()

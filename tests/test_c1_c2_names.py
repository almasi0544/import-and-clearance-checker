import unittest
from difflib import SequenceMatcher

import helpers
from app.engine.checks import check_c1, check_c2


def c1_docs(inv="Example Imports Ltd", pl="Example Imports Ltd", bl="Example Imports Ltd"):
    return {"commercial_invoice": {"buyer": {"name": inv}}, "packing_list": {"consignee": {"name": pl}},
            "bill_of_lading": {"consignee": {"name": bl}}}


def c2_docs(inv="Example Exports Ltd", pl="Example Exports Ltd", bl="Example Exports Ltd"):
    return {"commercial_invoice": {"seller": {"name": inv}}, "packing_list": {"shipper": {"name": pl}},
            "bill_of_lading": {"shipper": {"name": bl}}}


class TestC1Consignee(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    # values equal
    def test_equal_names_pass(self):
        r = check_c1(c1_docs(), self.rules)
        self.assertEqual((r.outcome, r.findings), ("pass", []))

    def test_clean_sets_pass(self):
        for n in (1, 2, 3, 4, 5, 6, 8, 9, 10):
            self.assertEqual(check_c1(helpers.load_documents(n), self.rules).outcome, "pass", f"set {n}")

    def test_case_punctuation_and_company_suffix_are_ignored(self):
        docs = c1_docs("EXAMPLE IMPORTS, LTD.", "Example Imports Limited", "example imports")
        self.assertEqual(check_c1(docs, self.rules).outcome, "pass")

    # values different
    def test_set_7_gives_one_finding_for_each_pair_with_the_bill_of_lading(self):
        r = check_c1(helpers.load_documents(7), self.rules)
        self.assertEqual(r.outcome, "finding")
        self.assertEqual([f.documents for f in r.findings],
                         [["commercial_invoice", "bill_of_lading"], ["packing_list", "bill_of_lading"]])
        f = r.findings[0]
        self.assertEqual((f.check_id, f.severity, f.field), ("C1", "high", "consignee.name"))
        self.assertEqual(f.message, 'Consignee name differs: "Tanga Agro Supplies Ltd" on the invoice, '
                                    '"Tanga Agrotech Distributors Ltd" on the bill of lading.')
        self.assertEqual(r.findings[1].message, 'Consignee name differs: "Tanga Agro Supplies Ltd" on the packing list, '
                                                '"Tanga Agrotech Distributors Ltd" on the bill of lading.')

    def test_a_clearly_different_name_is_a_finding(self):
        self.assertEqual(check_c1(c1_docs(bl="Other Traders Ltd"), self.rules).outcome, "finding")

    # field missing
    def test_a_missing_name_is_skipped_for_that_document_only(self):
        r = check_c1(c1_docs(pl=None), self.rules)
        self.assertEqual(r.outcome, "pass")          # the invoice and the bill of lading still agree
        r = check_c1(c1_docs(pl=None, bl="Other Traders Ltd"), self.rules)
        self.assertEqual(len(r.findings), 1)

    def test_fewer_than_two_names_is_skipped_not_a_finding(self):
        r = check_c1(c1_docs(pl=None, bl=None), self.rules)
        self.assertEqual((r.outcome, r.findings), ("skipped_not_present", []))
        self.assertEqual(check_c1({}, self.rules).outcome, "skipped_not_present")

    def test_an_empty_name_or_a_suffix_only_counts_as_missing(self):
        self.assertEqual(check_c1(c1_docs(pl="", bl="Ltd"), self.rules).outcome, "skipped_not_present")

    # threshold
    def test_a_one_letter_typo_passes_at_the_default_threshold(self):
        docs = c1_docs(inv="Tanga Agro Supplies Ltd", pl="Tanga Agro Supplies Ltd", bl="Tanga Agro Suplies Ltd")
        self.assertEqual(check_c1(docs, self.rules).outcome, "pass")

    def test_a_stricter_threshold_flags_the_typo(self):
        docs = c1_docs(inv="Tanga Agro Supplies Ltd", pl="Tanga Agro Supplies Ltd", bl="Tanga Agro Suplies Ltd")
        self.assertEqual(check_c1(docs, dict(self.rules, name_similarity_threshold=1.0)).outcome, "finding")

    def test_a_name_exactly_at_the_threshold_passes(self):
        ratio = SequenceMatcher(None, "tanga agro supplies", "tanga agrotech distributors").ratio()
        docs = c1_docs(inv="Tanga Agro Supplies Ltd", pl="Tanga Agro Supplies Ltd", bl="Tanga Agrotech Distributors Ltd")
        self.assertEqual(check_c1(docs, dict(self.rules, name_similarity_threshold=ratio)).outcome, "pass")


class TestC2Shipper(unittest.TestCase):
    def setUp(self):
        self.rules = helpers.load_rules()

    def test_equal_names_pass(self):
        self.assertEqual(check_c2(c2_docs(), self.rules).outcome, "pass")

    def test_clean_sets_pass(self):
        for n in range(1, 11):
            self.assertEqual(check_c2(helpers.load_documents(n), self.rules).outcome, "pass", f"set {n}")

    def test_a_different_shipper_is_a_finding_with_the_shipper_wording(self):
        r = check_c2(c2_docs(bl="Another Exporter Co., Ltd"), self.rules)
        self.assertEqual(r.outcome, "finding")
        f = r.findings[0]
        self.assertEqual((f.check_id, f.field), ("C2", "shipper.name"))
        self.assertEqual(f.message, 'Shipper name differs: "Example Exports Ltd" on the invoice, '
                                    '"Another Exporter Co., Ltd" on the bill of lading.')

    def test_a_missing_name_is_skipped(self):
        self.assertEqual(check_c2(c2_docs(inv=None, pl=None), self.rules).outcome, "skipped_not_present")


if __name__ == "__main__":
    unittest.main()

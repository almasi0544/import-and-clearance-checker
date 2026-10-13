import unittest

import helpers
from app.services.accuracy import MISSING, compare_documents, flatten, summarise


class TestAccuracy(unittest.TestCase):
    def test_identical_documents_match_on_every_field(self):
        doc = helpers.load_documents(5)["packing_list"]
        summary = summarise(compare_documents(doc, doc))
        self.assertEqual(summary["correct"], summary["total"])
        self.assertEqual(summary["wrong"], [])

    def test_nested_fields_and_lists_get_paths(self):
        flat = flatten({"a": {"b": 1}, "lines": [{"q": 2}, {"q": 3}], "codes": ["x", "y"]})
        self.assertEqual(flat, {"a.b": 1, "lines[0].q": 2, "lines[1].q": 3, "codes": ["x", "y"]})

    def test_numbers_match_whether_written_as_int_or_float(self):
        rows = compare_documents({"w": 2500}, {"w": 2500.0})
        self.assertTrue(rows[0]["match"])

    def test_a_wrong_value_is_listed(self):
        summary = summarise(compare_documents({"w": 2500, "n": "A"}, {"w": 2700, "n": "A"}))
        self.assertEqual((summary["correct"], summary["total"]), (1, 2))
        self.assertEqual(summary["wrong"][0]["field"], "w")

    def test_a_missing_field_is_wrong_and_marked(self):
        rows = compare_documents({"w": 2500}, {})
        self.assertFalse(rows[0]["match"])
        self.assertEqual(rows[0]["actual"], MISSING)

    def test_null_matches_null_but_not_zero(self):
        self.assertTrue(compare_documents({"v": None}, {"v": None})[0]["match"])
        self.assertFalse(compare_documents({"v": None}, {"v": 0})[0]["match"])

    def test_lists_of_plain_values_ignore_order(self):
        self.assertTrue(compare_documents({"codes": ["a", "b"]}, {"codes": ["b", "a"]})[0]["match"])

    def test_text_is_compared_exactly(self):
        self.assertFalse(compare_documents({"n": "Tanga Agro Supplies Ltd"}, {"n": "Tanga Agro Suplies Ltd"})[0]["match"])


if __name__ == "__main__":
    unittest.main()

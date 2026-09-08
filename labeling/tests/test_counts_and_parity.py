"""The published counts, and the train/validation parity claims, must agree with each other."""
import json, os, re, unittest
from _load import DATA

ROOT = DATA.parent
with open(DATA / "label_counts.json") as _fh:
    COUNTS = json.load(_fh)
README = (ROOT / "README.md").read_text()


class TestCounts(unittest.TestCase):
    def test_training_arithmetic_closes(self):
        """attempts - citation = HARD rows; HARD - crutch = CFHL rows."""
        for m in ("8B", "32B"):
            c = COUNTS["training"][m]
            self.assertEqual(c["attempts"] - c["citation_dropped"], c["hard_rows"], m)
            self.assertEqual(c["hard_rows"] - c["crutch_dropped"], c["cfhl_rows"], m)

    def test_training_values(self):
        t = COUNTS["training"]
        self.assertEqual((t["8B"]["citation_dropped"], t["32B"]["citation_dropped"]), (71, 51))
        self.assertEqual((t["8B"]["crutch_dropped"], t["32B"]["crutch_dropped"]), (23, 2))
        self.assertEqual((t["8B"]["attr_err"], t["32B"]["attr_err"]), (0, 0))
        self.assertEqual((t["8B"]["cfhl_rows"], t["32B"]["cfhl_rows"]), (1850, 1891))
        self.assertEqual((t["8B"]["cfhl_positives"], t["32B"]["cfhl_positives"]), (364, 417))

    def test_validation_values(self):
        v = COUNTS["validation_13_arms"]
        self.assertEqual((v["8B"]["citation_dropped"], v["32B"]["citation_dropped"]), (106, 100))
        self.assertEqual((v["8B"]["attr_err"], v["32B"]["attr_err"]), (0, 1))

    def test_readme_table_matches_the_data(self):
        """The counts quoted in README.md must be the ones in label_counts.json."""
        t, v = COUNTS["training"], COUNTS["validation_13_arms"]
        for a, b in ((t["8B"]["citation_dropped"], t["32B"]["citation_dropped"]),
                     (t["8B"]["crutch_dropped"], t["32B"]["crutch_dropped"]),
                     (v["8B"]["citation_dropped"], v["32B"]["citation_dropped"])):
            self.assertIn(f"{a} / {b}", README, f"README is missing the pair {a} / {b}")


class TestSplitParity(unittest.TestCase):
    def test_one_header_builder_serves_both_splits(self):
        """No duplicated header logic: the builder's own contract says both paths must call it."""
        src = (ROOT / "code" / "lenient_headers.py").read_text()
        self.assertIn("MUST call this", src)
        self.assertIn("no\nduplicated header logic", src.replace("  ", " ").replace("\n", "\n"))

    def test_crutch_purge_is_training_only_and_declared_so(self):
        self.assertFalse(COUNTS["validation_13_arms"]["8B"]["crutch_applied"])
        self.assertFalse(COUNTS["validation_13_arms"]["32B"]["crutch_applied"])
        self.assertIn("training only, by design", README)

    def test_readme_states_why_that_is_not_an_inconsistency(self):
        self.assertIn("not a solve either way", README.replace("\n", " "))

    def test_residual_timeout_is_documented_as_not_a_filter(self):
        self.assertIn("surfaced for reporting only", README.replace("\n", " ").replace("**", ""))


if __name__ == "__main__":
    unittest.main()

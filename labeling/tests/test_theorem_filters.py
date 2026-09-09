"""Mechanisms 1 and 3: the two theorem-level filters, and the safety property they are claimed to have."""
import json, unittest
from _load import DATA

def load(n):
    with open(DATA / n) as fh:
        return json.load(fh)

dead = lambda n: load(n)["theorem_ids"]   # the drop-list files wrap the ids in a provenance record


class TestTheoremFilters(unittest.TestCase):
    def test_dead_statement_filter_counts(self):
        """Stage 1 removes theorems whose statement already fails to compile: 1,367/419 -> 1,080/319."""
        self.assertEqual(len(dead("dead_statements_train.json")), 1367 - 1080)
        self.assertEqual(len(dead("dead_statements_val.json")), 419 - 319)

    def test_elaboration_filter_keep_list_sizes(self):
        self.assertEqual(len(load("clean_keep_train.json")), 243)
        self.assertEqual(len(load("clean_keep_val.json")), 90)

    def test_keep_and_drop_lists_are_disjoint(self):
        for keep, dead_f in (("clean_keep_train.json", "dead_statements_train.json"),
                             ("clean_keep_val.json", "dead_statements_val.json")):
            k = {t.split("@")[0] for t in load(keep)}
            d = {t.split("@")[0] for t in load(dead_f)["theorem_ids"]}
            self.assertEqual(k & d, set(), f"{keep} overlaps {dead_f}")

    def test_train_and_validation_keep_lists_are_disjoint(self):
        self.assertEqual(set(load("clean_keep_train.json")) & set(load("clean_keep_val.json")), set())

    def test_classification_covers_every_kept_theorem(self):
        """Fail-loud contract: no kept theorem may be missing a collider class."""
        cls = load("theorem_classification.json")["classification"]
        for keep in ("clean_keep_train.json", "clean_keep_val.json"):
            for t in load(keep):
                self.assertIn(t.split("@")[0], cls, f"{t} has no classification")

    def test_class_counts(self):
        c = load("theorem_classification.json")["counts"]
        self.assertEqual(c["COLLIDER_AESOP"], 2)
        self.assertEqual(c["COLLIDER_NONAESOP"] + c["COLLIDER_AESOP"], 325)
        self.assertEqual(c["NONCOLLIDER"], 8)
        self.assertEqual(sum(c.values()), 333)

    def test_the_two_aesop_colliders_are_the_named_ones(self):
        self.assertEqual(sorted(load("theorem_classification.json")["aesop_rules"]),
                         ["Complex.continuous_sinh", "ENNReal.measurable_toReal"])

    def test_readme_orders_the_rename_before_the_elaboration_filter(self):
        """The order is load-bearing, not cosmetic.

        The elaboration filter's keep rule is "the statement elaborates once renamed": without the rename a
        collider is rejected as already declared before Lean reaches the statement, so the filter cannot run.
        An earlier revision of the README listed the rename after the filter.
        """
        readme = (DATA.parent / "README.md").read_text(encoding="utf-8")
        rows = [ln for ln in readme.splitlines() if ln.startswith("| ") and "**" in ln]
        rename = next(n for n, ln in enumerate(rows) if "**rename**" in ln)
        elab = next(n for n, ln in enumerate(rows) if "**statement-elaboration filter**" in ln)
        self.assertLess(rename, elab,
                        "the README must list the rename before the statement-elaboration filter")
        self.assertIn("with the rename already applied", readme,
                      "the elaboration row must say the test runs under the rename")


if __name__ == "__main__":
    unittest.main()

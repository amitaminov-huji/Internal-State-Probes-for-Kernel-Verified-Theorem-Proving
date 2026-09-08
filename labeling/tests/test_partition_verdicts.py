"""Mechanisms 6-7 and the attribute-error guard: the set algebra that turns verdicts into labels."""
import unittest
import _load


def row(tid, hard_ok, soft_ok, cited=False, attr_err=False):
    return {"orig": {"theorem_id": tid, "seed": 0}, "hard_ok": hard_ok, "soft_ok": soft_ok,
            "hard_cited": cited, "attr_err": attr_err}


class TestPartitionVerdicts(unittest.TestCase):
    def setUp(self):
        self.part = _load.partition_verdicts()

    def test_plain_success_reaches_every_set(self):
        hard, soft, cfhl, n = self.part([row("t", True, True)])
        self.assertEqual((len(hard), len(soft), len(cfhl), n), (1, 1, 1, 0))
        self.assertTrue(hard[0]["success"] and cfhl[0]["success"])

    def test_citation_drop_removes_a_citing_SUCCESS(self):
        hard, soft, cfhl, _ = self.part([row("t", True, True, cited=True)])
        self.assertEqual(len(hard), 0)          # dropped from HARD
        self.assertEqual(len(cfhl), 0)          # and therefore from CFHL
        self.assertEqual(len(soft), 1)          # SOFT is rename-only, unaffected

    def test_citation_does_not_drop_a_FAILURE(self):
        """The filter targets leaky positives; a citing failure is an ordinary negative."""
        hard, _, cfhl, _ = self.part([row("t", False, False, cited=True)])
        self.assertEqual((len(hard), len(cfhl)), (1, 1))
        self.assertFalse(hard[0]["success"])

    def test_crutch_purge_drops_from_CFHL_but_keeps_the_negative_in_HARD(self):
        hard, soft, cfhl, _ = self.part([row("t", False, True)])
        self.assertEqual(len(hard), 1)
        self.assertFalse(hard[0]["success"])    # kept as a negative
        self.assertEqual(len(cfhl), 0)          # but not used to train CFHL
        self.assertEqual(len(soft), 1)
        self.assertTrue(soft[0]["success"])

    def test_attr_err_is_excluded_from_ALL_three_sets(self):
        hard, soft, cfhl, n = self.part([row("t", True, True, attr_err=True)])
        self.assertEqual((len(hard), len(soft), len(cfhl), n), (0, 0, 0, 1))


class TestAttrErrMessages(unittest.TestCase):
    """The guard's message list, and the ambiguity blind spot it deliberately does not cover.

    This is a CHARACTERISATION test: `ambiguous identifier` is absent on purpose, and that absence is the
    documented reason `gcd_greatest` was never surfaced. See ../README.md.
    """

    def setUp(self):
        import sys
        _load.partition_verdicts()                 # loads and registers the real module
        self.mod = sys.modules["relabel_lenient"]

    def test_message_list_is_exactly_three(self):
        self.assertEqual(tuple(self.mod._ATTR_MSGS),
                         ("not registered", "unknown identifier", "unknown constant"))

    def test_ambiguous_identifier_is_not_matched(self):
        r = {"errors": [{"data": "ambiguous identifier 'gcd_greatest', possible interpretations ..."}]}
        self.assertFalse(self.mod._err_on_attribute(r, "gcd_greatest"))

    def test_a_quoted_target_with_a_listed_message_IS_matched(self):
        r = {"errors": [{"data": "unknown identifier 'Foo.bar'"}]}
        self.assertTrue(self.mod._err_on_attribute(r, "Foo.bar"))

    def test_a_different_identifier_is_not_misread(self):
        r = {"errors": [{"data": "unknown identifier 'SomeOtherLemma'"}]}
        self.assertFalse(self.mod._err_on_attribute(r, "Foo.bar"))

    def test_substring_superset_is_not_misread(self):
        r = {"errors": [{"data": "unknown identifier 'Nat.addfoo'"}]}
        self.assertFalse(self.mod._err_on_attribute(r, "Nat.add"))


if __name__ == "__main__":
    unittest.main()

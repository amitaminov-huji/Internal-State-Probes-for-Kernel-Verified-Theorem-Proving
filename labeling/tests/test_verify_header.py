"""Mechanisms 2, 4 and 5: the rename, the simp erase, and the conditional aesop erase."""
import unittest
import _load

H = "import Mathlib\nimport Aesop\n\nset_option maxHeartbeats 0\n\nopen BigOperators Real Nat Topology Rat\n\n"


class TestVerifyHeader(unittest.TestCase):
    def setUp(self):
        self.build = _load.lenient_headers().build_verify_header

    def test_noncollider_erases_nothing(self):
        h = self.build(H, "Foo", "Foo.bar", "hard", "NONCOLLIDER")
        self.assertNotIn("attribute [-simp]", h)
        self.assertNotIn("attribute [-aesop]", h)
        self.assertIn("namespace Foo", h)

    def test_simp_erase_on_plain_collider(self):
        h = self.build(H, "Foo", "Foo.bar", "hard", "COLLIDER_NONAESOP")
        self.assertIn("attribute [-simp] Foo.bar", h)
        self.assertNotIn("attribute [-aesop]", h)

    def test_aesop_erase_only_for_aesop_colliders(self):
        h = self.build(H, "Complex", "Complex.continuous_sinh", "hard", "COLLIDER_AESOP")
        self.assertIn("attribute [-simp] Complex.continuous_sinh", h)
        self.assertIn("attribute [-aesop] Complex.continuous_sinh", h)

    def test_both_erases_precede_the_namespace(self):
        """Root-level placement: the attributes must come BEFORE `namespace`, for unambiguous resolution."""
        h = self.build(H, "Complex", "Complex.continuous_sinh", "hard", "COLLIDER_AESOP")
        self.assertLess(h.index("attribute [-simp]"), h.index("namespace Complex"))
        self.assertLess(h.index("attribute [-aesop]"), h.index("namespace Complex"))

    def test_soft_mode_erases_nothing(self):
        for cls in ("NONCOLLIDER", "COLLIDER_NONAESOP", "COLLIDER_AESOP"):
            self.assertNotIn("attribute [-", self.build(H, "Foo", "Foo.bar", "soft", cls))

    def test_root_level_target_emits_a_bare_name_and_no_namespace(self):
        """The gcd_greatest shape: a target with no namespace yields an unqualified attribute line."""
        h = self.build(H, "", "gcd_greatest", "hard", "COLLIDER_NONAESOP")
        self.assertIn("attribute [-simp] gcd_greatest", h)
        self.assertNotIn("namespace", h)

    def test_unknown_class_and_mode_fail_loud(self):
        with self.assertRaises(ValueError):
            self.build(H, "Foo", "Foo.bar", "hard", "NOT_A_CLASS")
        with self.assertRaises(ValueError):
            self.build(H, "Foo", "Foo.bar", "sideways", "NONCOLLIDER")


if __name__ == "__main__":
    unittest.main()

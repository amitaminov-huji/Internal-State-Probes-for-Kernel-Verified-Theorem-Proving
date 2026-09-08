"""Lean-level checks: the erases really disable the rules. Skipped unless LEAN_TESTS=1.

These need a Lean 4.9.0-rc1 toolchain with the pinned mathlib. Set LEAN_WORKSPACE and LAKE to your checkout.
Expected verdicts are the ones recorded in ../../../writing/documents/aesop_namespace_removal_edge_case.md.
"""
import os, subprocess, tempfile, unittest

LEAN_WORKSPACE = os.environ.get("LEAN_WORKSPACE", "")
LAKE = os.environ.get("LAKE", "lake")
H = ("import Mathlib\nimport Aesop\n\nset_option maxHeartbeats 400000\n\n"
     "open BigOperators Real Nat Topology Rat\n")


@unittest.skipUnless(os.environ.get("LEAN_TESTS") == "1" and LEAN_WORKSPACE,
                     "set LEAN_TESTS=1 and LEAN_WORKSPACE to run the Lean checks")
class TestAesopErase(unittest.TestCase):
    def _proves(self, body):
        with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as f:
            f.write(H + body); path = f.name
        out = subprocess.run([LAKE, "env", "lean", path], cwd=LEAN_WORKSPACE,
                             capture_output=True, text=True, timeout=900)
        return out.returncode == 0 and "error:" not in (out.stdout + out.stderr)

    def test_continuity_control_proves(self):
        self.assertTrue(self._proves("\nnamespace Complex\ntheorem t : Continuous sinh := by continuity\nend Complex\n"))

    def test_our_header_disables_the_continuity_rule(self):
        self.assertFalse(self._proves(
            "attribute [-simp] Complex.continuous_sinh\nattribute [-aesop] Complex.continuous_sinh\n"
            "namespace Complex\ntheorem t : Continuous sinh := by continuity\nend Complex\n"))

    def test_measurability_control_proves(self):
        self.assertTrue(self._proves("\nnamespace ENNReal\ntheorem t : Measurable ENNReal.toReal := by measurability\nend ENNReal\n"))

    def test_our_header_disables_the_measurability_rule(self):
        self.assertFalse(self._proves(
            "attribute [-simp] ENNReal.measurable_toReal\nattribute [-aesop] ENNReal.measurable_toReal\n"
            "namespace ENNReal\ntheorem t : Measurable ENNReal.toReal := by measurability\nend ENNReal\n"))

    def test_bare_aesop_cannot_apply_these_lemmas_even_unguarded(self):
        """@[continuity]/@[measurability] feed NAMED rule sets a bare `aesop` never consults."""
        self.assertFalse(self._proves("\nnamespace Complex\ntheorem t : Continuous sinh := by aesop\nend Complex\n"))


if __name__ == "__main__":
    unittest.main()

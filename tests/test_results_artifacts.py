"""The shipped per-attempt results must reproduce the numbers this repo claims in its README."""
import json, pathlib, re, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
ARMS = [("8B", "base", 41, 560), ("8B", "steer", 35, 461),
        ("32B", "base", 60, 897), ("32B", "steer", 59, 744)]
N_THEOREMS, N_ATTEMPTS = 360, 11520


def verdicts(model, arm):
    p = ROOT / "results" / f"mobench_mob_{model}_{arm}_robust_verdicts.jsonl"
    with open(p) as fh:
        return [json.loads(l) for l in fh if l.strip()]


class TestResultsArtifacts(unittest.TestCase):
    def test_every_arm_has_a_complete_sweep(self):
        for m, arm, _, _ in ARMS:
            rows = verdicts(m, arm)
            self.assertEqual(len(rows), N_ATTEMPTS, f"{m} {arm}")
            self.assertEqual(len({r["theorem_id"] for r in rows}), N_THEOREMS, f"{m} {arm}")

    def test_solved_theorems_and_verifying_attempts(self):
        for m, arm, thms, atts in ARMS:
            valid = [r for r in verdicts(m, arm) if r.get("valid")]
            self.assertEqual(len(valid), atts, f"{m} {arm} verifying attempts")
            self.assertEqual(len({r["theorem_id"] for r in valid}), thms, f"{m} {arm} solved theorems")

    def test_solved_proofs_file_matches_the_verdicts(self):
        """Every verifying attempt, and only those, should appear in the solved-proofs file."""
        for m, arm, _, atts in ARMS:
            p = ROOT / "results" / f"mobench_mob_{m}_{arm}_solved_proofs.jsonl"
            with open(p) as fh:
                n = sum(1 for l in fh if l.strip())
            self.assertEqual(n, atts, f"{m} {arm}: solved_proofs rows vs verifying attempts")

    def test_readme_headline_table_matches_the_artifacts(self):
        """The 41/35/60/59 table in README.md must be what the shipped verdicts actually say."""
        base = {m: t for m, a, t, _ in ARMS if a == "base"}
        steer = {m: t for m, a, t, _ in ARMS if a == "steer"}
        self.assertRegex(README, rf"Base\s*\|\s*\*\*{base['8B']}\*\*\s*\|\s*\*\*{base['32B']}\*\*")
        self.assertRegex(README, rf"Steered\s*\|\s*{steer['8B']}\s*\|\s*{steer['32B']}")

    def test_readme_attempt_level_numbers_match(self):
        txt = " ".join(README.split())
        self.assertIn("560 to 461", txt)
        self.assertIn("897 to 744", txt)

    def test_no_attempt_is_valid_with_an_off_whitelist_axiom(self):
        """The verification contract, checked on the artifacts rather than asserted."""
        allowed = {"propext", "Classical.choice", "Quot.sound"}
        for m, arm, _, _ in ARMS:
            for r in verdicts(m, arm):
                if r.get("valid"):
                    self.assertTrue(set(r.get("axioms") or []) <= allowed,
                                    f"{m} {arm} {r.get('attempt')}: {r.get('axioms')}")


if __name__ == "__main__":
    unittest.main()

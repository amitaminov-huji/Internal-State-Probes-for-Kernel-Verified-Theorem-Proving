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

    def test_base_and_steered_join_only_under_the_canonical_id(self):
        """The two arms spell 131 of the 360 theorem ids differently, and the README says so.

        A base file says `2006_A1` where the matching steered file says `imo_sl_2006_A1`, because the
        arms come from different runs. Per-arm counts do not care, which is why every other test here
        passes either way, but a naive join by `theorem_id` drops those 131 on both sides and gives the
        wrong per-theorem gains and losses. This pins both halves: that the raw ids really do disagree
        (so the README's warning is not stale) and that the canonical id recovers the published lists.
        """
        def canon(tid):
            return tid[len("imo_sl_"):] if tid.startswith("imo_sl_") else tid

        def solved(m, arm, key):
            out = {}
            for r in verdicts(m, arm):
                k = key(r["theorem_id"])
                out[k] = out.get(k, 0) + bool(r.get("valid"))
            return out

        for m, n_gain, n_loss in (("8B", 2, 8), ("32B", 5, 6)):
            raw_b, raw_s = solved(m, "base", lambda x: x), solved(m, "steer", lambda x: x)
            self.assertNotEqual(set(raw_b), set(raw_s),
                                f"{m}: raw ids now agree; the README's join warning needs updating")
            b, s = solved(m, "base", canon), solved(m, "steer", canon)
            self.assertEqual(set(b), set(s), f"{m}: canonical ids must match across arms")
            self.assertEqual(len(b), 360, m)
            gains = [k for k in b if b[k] == 0 and s[k] > 0]
            losses = [k for k in b if b[k] > 0 and s[k] == 0]
            self.assertEqual(len(gains), n_gain, f"{m} gains: {sorted(gains)}")
            self.assertEqual(len(losses), n_loss, f"{m} losses: {sorted(losses)}")

    def test_no_attempt_is_valid_with_an_off_whitelist_axiom(self):
        """The verification contract, checked on the artifacts rather than asserted."""
        allowed = {"propext", "Classical.choice", "Quot.sound"}
        for m, arm, _, _ in ARMS:
            for r in verdicts(m, arm):
                if r.get("valid"):
                    self.assertTrue(set(r.get("axioms") or []) <= allowed,
                                    f"{m} {arm} {r.get('attempt')}: {r.get('axioms')}")

    def test_a_verifying_attempt_compiled(self):
        """`valid` implies the Lean process exited 0, which is stronger than it sounds.

        The verdicts are written in two timeout tiers: a first pass, then an escalation for whatever
        timed out. Until 2026-09-13 the escalation refreshed `valid` but left `exit_code` and `axioms`
        at the abandoned first-tier values, so 43 (8B) and 127 (32B) base rows read `valid: true`
        beside `exit_code: -1`, and carried an empty axiom list. That empty list is also why
        test_no_attempt_is_valid_with_an_off_whitelist_axiom passed on them vacuously. This test is
        the one that bites.
        """
        for m, arm, _, _ in ARMS:
            for r in verdicts(m, arm):
                if r.get("valid"):
                    self.assertEqual(r.get("exit_code"), 0,
                                     f"{m} {arm} {r.get('attempt')}: valid but exit_code="
                                     f"{r.get('exit_code')!r}")

    def test_a_negative_exit_code_means_an_unresolved_timeout(self):
        """`exit_code: -1` is a timeout that never resolved, so such an attempt is never valid."""
        for m, arm, _, _ in ARMS:
            for r in verdicts(m, arm):
                if r.get("exit_code") == -1:
                    self.assertFalse(r.get("valid"),
                                     f"{m} {arm} {r.get('attempt')}: timed out yet valid")


if __name__ == "__main__":
    unittest.main()

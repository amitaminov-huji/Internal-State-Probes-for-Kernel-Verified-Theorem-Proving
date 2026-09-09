"""The shipped probe checkpoints: architecture, sizes, and the absence of a step-index feature."""
import json, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = {"8B": 4096, "32B": 5120}
PARAMS = {"probe_8B_fc": 2_114_049, "probe_32B_fc": 2_642_433,
          "probe_8B_lstm": 673_281, "probe_32B_lstm": 806_401}

try:
    import torch
except ImportError:                                   # torch is optional for the rest of the suite
    torch = None


def load(name):
    obj = torch.load(ROOT / "probes" / f"{name}.pt", map_location="cpu", weights_only=False)
    sd = obj.get("state_dict", obj) if isinstance(obj, dict) else obj
    return obj, sd


@unittest.skipIf(torch is None, "torch not installed")
class TestProbes(unittest.TestCase):
    def test_parameter_counts(self):
        for name, want in PARAMS.items():
            _, sd = load(name)
            n = sum(v.numel() for v in sd.values() if hasattr(v, "numel"))
            self.assertEqual(n, want, f"{name}: parameter count")

    def test_no_step_index_feature_in_the_input(self):
        """MLP consumes 2H (previous + current line-start state), LSTM consumes H. A step channel would
        make these 2H+1 and H+1. The deployed probes are hidden-state only."""
        for name in PARAMS:
            model = "8B" if "_8B_" in name else "32B"
            expected = 2 * H[model] if name.endswith("_fc") else H[model]
            _, sd = load(name)
            first = next(k for k, v in sd.items() if hasattr(v, "ndim") and v.ndim == 2)
            self.assertEqual(sd[first].shape[1], expected,
                             f"{name}: {first} in_features (a step feature would give {expected + 1})")

    def test_use_step_idx_flag_is_false(self):
        for name in PARAMS:
            obj, _ = load(name)
            self.assertIsInstance(obj, dict)
            self.assertIn("use_step_idx", obj, f"{name}: checkpoint records no use_step_idx flag")
            self.assertFalse(obj["use_step_idx"], f"{name}: use_step_idx must be False")

    def test_no_state_dict_key_mentions_a_step_channel(self):
        for name in PARAMS:
            _, sd = load(name)
            self.assertEqual([k for k in sd if "step" in k.lower()], [], f"{name}")

    def test_readme_quotes_auroc_to_two_decimals_matching_the_checkpoints(self):
        """The reporting precision is two decimals, and each cell must be its checkpoint's own value.

        The repo drifted to three decimals while the paper, thesis and deck all reported two; the
        coherence harness bans three-decimal ROC-AUC but never reads this repo.
        """
        readme = (ROOT / "probes" / "README.md").read_text(encoding="utf-8")
        # the AUROC table alone: three columns, unlike the checkpoint table above it
        table = [ln for ln in readme.splitlines()
                 if ln.startswith("| ") and ("LSTM" in ln or "MLP" in ln) and len(ln.split("|")) == 5]
        self.assertEqual(len(table), 4, "expected one AUROC row per checkpoint")
        for ln in table:
            for cell in [c.strip() for c in ln.split("|")[2:4]]:
                self.assertRegex(cell, r"^0\.\d{2}$", f"ROC-AUC must be two decimals, got {cell!r}")
        want = {}
        for name in PARAMS:
            _, sd = load(name)
            ck = torch.load(str(ROOT / "probes" / f"{name}.pt"), map_location="cpu", weights_only=False)
            m = ck.get("metadata", {}) or {}
            key = ("8B" if "_8B_" in name else "32B") + (" LSTM" if name.endswith("_lstm") else " MLP")
            want[key] = (round(m["kfold_grouped_auroc"] + 1e-9, 2),
                         round(m["mobench_boundary_auroc"] + 1e-9, 2))
        for ln in table:
            cells = [c.strip() for c in ln.split("|")[1:4]]
            got = (float(cells[1]), float(cells[2]))
            self.assertEqual(got, want[cells[0]], f"{cells[0]}: README {got} vs checkpoint {want[cells[0]]}")
        # and the spread the paper quotes
        ind = [v[0] for v in want.values()]; ood = [v[1] for v in want.values()]
        self.assertEqual((min(ind), max(ind)), (0.89, 0.92))
        self.assertEqual((min(ood), max(ood)), (0.81, 0.86))

    def test_readme_names_the_lstm_as_the_deployed_head(self):
        txt = " ".join((ROOT / "README.md").read_text().split())
        self.assertIn("The deployed controller is the LSTM", txt)


class TestBoundaryTokens(unittest.TestCase):
    def test_line_start_token_set_is_the_229_indentation_ids(self):
        with open(ROOT / "probes" / "boundary_token_ids.json") as fh:
            d = json.load(fh)
        ids = d["ids"] if isinstance(d, dict) else d
        self.assertEqual(len(ids), 229)


if __name__ == "__main__":
    unittest.main()

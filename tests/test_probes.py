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

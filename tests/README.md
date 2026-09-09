# Artifact tests

Checks that the shipped results and probes are what this repo claims they are.

```bash
python -m unittest discover -s tests            # results + probes (needs torch for the probe tests)
cd labeling/tests && python -m unittest discover -s .   # the labelling mechanisms
```

| file | covers |
|---|---|
| `test_results_artifacts.py` | every arm is a complete 360x32 sweep; solved theorems and verifying attempts equal the README table (41/35/60/59, 560/461/897/744); `solved_proofs` rows match the verdicts; no `valid` attempt rests on an off-whitelist axiom |
| `test_probes.py` | parameter counts match the paper; the MLP consumes 2H and the LSTM H, so there is **no step-index feature**; `use_step_idx` is `False` in every checkpoint; the line-start token set has 229 ids; the ROC-AUC table is quoted to two decimals and each cell matches its own checkpoint |

The axiom test is the verification contract checked against the artifacts rather than asserted in prose.

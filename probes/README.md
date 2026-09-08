# Deployed probes

The failure probes are small heads trained on the frozen base model's internal states, with labels taken from
the Lean kernel's verdict on the whole proof attempt (see [`../robust_verification/`](../robust_verification/)).
The base model's weights are never updated.

Two heads were trained. **The deployed controller is the LSTM head**, selected on held-out theorems by a
validation contest that searched a grid shared by both heads. The MLP head is shipped for reference; the paper reports
both heads' numbers side by side. It was never deployed.

| File | Base model | Head | Params | Deployed |
|---|---|---|---:|---|
| `probe_8B_lstm.pt`  | Goedel-Prover-V2-8B  | LSTM | 673,281   | **yes** |
| `probe_32B_lstm.pt` | Goedel-Prover-V2-32B | LSTM | 806,401   | **yes** |
| `probe_8B_fc.pt`    | Goedel-Prover-V2-8B  | MLP  | 2,114,049 | no |
| `probe_32B_fc.pt`   | Goedel-Prover-V2-32B | MLP  | 2,642,433 | no |

**Selected steering setting, identical on both base models: frequency penalty, `alpha = 0.15`.**

## Where the probe reads

At **line starts**, the indentation that opens each proof line, not at newlines. In the Lean block a newline is followed by the *next line's
indentation*, so a probe reading there sees the state just before whitespace; the indentation token is the one
that immediately precedes real Lean content (81-99% of the time, against under 8% for a bare newline). The
line-start set is the 229 vocabulary items that decode to a whitespace run of two or more spaces, listed in
[`boundary_token_ids.json`](boundary_token_ids.json) (the filename keeps the earlier internal name). It is identical for both base models, whose tokenizers are
byte-identical.

## Heads

Both read the base model's final-normalization hidden state (`model.model.norm`), dimension `H` = 4096 (8B) /
5120 (32B), z-scored with the mean and standard deviation stored in the checkpoint. **Neither head takes a step
or position feature.**

```
LSTM (deployed)  LayerNorm(H) -> Linear(H, 128) -> ReLU -> LSTM(128) -> LayerNorm(128)
                 -> Linear(128, 64) -> ReLU -> Dropout -> Linear(64, 1) -> sigmoid = p_fail
                 The (h, c) state is carried across the line starts of one attempt and reset for the next.

MLP (reference)  LayerNorm(2H) -> Linear(2H, 256) -> ReLU -> Dropout -> Linear(256, 1) -> sigmoid = p_fail
                 Input is the concatenation of the previous and current line-start states.
```

## A note on the stored metadata

Each checkpoint's `metadata` carries `val_auroc_rowlevel_optimistic`, an in-training row-level holdout value of
about 0.98-0.99. **That number is optimistic by construction**, because per-line rows from a single theorem fall
on both sides of the split. The honest numbers are also stored, and are the ones the paper reports:
`kfold_grouped_auroc` (theorem-grouped, in domain) and `mobench_boundary_auroc` (out of domain).

| checkpoint | theorem-grouped K-fold | MathOlympiadBench (out of domain) |
|---|---|---|
| 8B LSTM  | 0.907 | 0.826 |
| 32B LSTM | 0.915 | 0.855 |
| 8B MLP   | 0.892 | 0.831 |
| 32B MLP  | 0.907 | 0.808 |

These are point estimates on a single run; we report no confidence intervals, and no ROC-AUC difference here
should be called significant. The values above are the ones stored in each checkpoint; the paper and the thesis
round them to two decimals, because the fold-to-fold standard deviation is +/- 0.02 to 0.04.

See [`../guides/steered_generation_example.md`](../guides/steered_generation_example.md) for how `p_fail` is
turned into a steering signal.

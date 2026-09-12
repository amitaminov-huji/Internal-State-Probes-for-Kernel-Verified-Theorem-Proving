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
that immediately precedes real Lean content: inside the Lean block the next token is real content in 89-97% of
firings, measured over every base attempt of both models on the training and the test theorems. The
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

## How they were trained

Adam at `1e-3` for **30 fixed epochs** from **seed 0**, about five minutes per head on one GPU. The base model
is frozen throughout; only the head's parameters move.

The unit of a batch differs because the unit of a training example does. For the MLP an example is one line
start and a batch is **512** of them (115,285 readings on 8B, 177,552 on 32B). For the LSTM an example is a
whole attempt read in order, and a batch is **64** attempts padded to a common length with a mask, so the loss
counts only real line starts and never the padding (1,805 attempts on 8B, 1,891 on 32B).

The loss is binary cross-entropy weighted by the ratio of verifying to failing examples among the training
examples used, applied to the failing class; failures dominate, so the weight is below one and pulls them down,
which is the same as pulling the rare verifying examples up. The per-feature mean and standard deviation are
computed on the training line starts alone and stored in the checkpoint, so the deployed controller sees
exactly the inputs the head was fitted on. There is no early stopping, no learning-rate schedule, no weight
decay and no gradient clipping. After each epoch the head is scored on a held-out slice and **the best epoch's
weights are kept**, not the last epoch's — which is what the next section is about.

## A note on the stored metadata

Each checkpoint's `metadata` carries `val_auroc_rowlevel_optimistic`, an in-training row-level holdout value of
about 0.98-0.99. **That number is optimistic by construction.** The labelled collection carries no
separate validation split, so training falls back to a **10% holdout drawn at random from the training data
itself** — over rows for the MLP and over whole attempts for the LSTM, and grouped by theorem in neither case.
Line starts of one proof therefore sit on both sides of it, and a head can score well there by recognising a
proof it has already largely seen. It is also the largest of 30 such evaluations, one per epoch, on the very
slice that chooses the epoch. The honest numbers are also stored, and are the ones the paper reports:
`kfold_grouped_auroc` (theorem-grouped, in domain) and `mobench_boundary_auroc` (out of domain).

| checkpoint | theorem-grouped K-fold | MathOlympiadBench (out of domain) |
|---|---|---|
| 8B LSTM  | 0.91 | 0.83 |
| 32B LSTM | 0.92 | 0.86 |
| 8B MLP   | 0.89 | 0.83 |
| 32B MLP  | 0.91 | 0.81 |

These are point estimates on a single run; we report no confidence intervals, and no ROC-AUC difference here
should be called significant. We quote two decimals throughout, as the paper and the thesis do, because the
fold-to-fold standard deviation is +/- 0.02 to 0.04; each checkpoint's `metadata` stores the unrounded value.
Across the four heads that is 0.89-0.92 in domain and 0.81-0.86 out of domain, the ranges the paper reports.

See [`../guides/steered_generation_example.md`](../guides/steered_generation_example.md) for how `p_fail` is
turned into a steering signal.

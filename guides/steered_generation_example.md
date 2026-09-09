# Guide: steered generation on an example theorem

Goal: show how the probe reads a frozen Goedel-Prover-V2's internal state and turns it into a steering signal.

## 1. Load the probe and turn a hidden state into `p_fail`

The checkpoint is a small dict: the head's weights, the feature normalizer (`normalizer_mean` /
`normalizer_std`), and a little config. The deployed head is the **LSTM**, which reads one line start at a time
and carries its own `(h, c)` state across the line starts of an attempt, resetting for the next attempt.

The block below is self-contained and runnable; it needs only `torch` and the checkpoint.

```python
import torch, torch.nn as nn

ckpt = torch.load("probes/probe_8B_lstm.pt", map_location="cpu", weights_only=True)
H = ckpt["hidden_size"]                     # 4096 (8B) / 5120 (32B)

class FailureProbeLSTM(nn.Module):
    """One z-scored line-start hidden state -> p_fail, carrying state across an attempt."""
    def __init__(self, H, lstm_hidden=128, clf_hidden=64):
        super().__init__()
        self.input_proj = nn.Sequential(
            nn.LayerNorm(H), nn.Linear(H, lstm_hidden), nn.ReLU())
        self.lstm = nn.LSTM(lstm_hidden, lstm_hidden, num_layers=1, batch_first=True)
        self.classifier_head = nn.Sequential(
            nn.LayerNorm(lstm_hidden), nn.Linear(lstm_hidden, clf_hidden),
            nn.ReLU(), nn.Dropout(0.0), nn.Linear(clf_hidden, 1))

    def forward(self, h, state=None):        # h: (1, 1, H), already z-scored
        x, state = self.lstm(self.input_proj(h), state)
        return torch.sigmoid(self.classifier_head(x)).view(-1), state

probe = FailureProbeLSTM(H)
probe.load_state_dict(ckpt["state_dict"])
probe.eval()

# Feature normalization is REQUIRED: the head was fitted on standardized inputs.
mean = torch.as_tensor(ckpt["normalizer_mean"], dtype=torch.float32)
std  = torch.as_tensor(ckpt["normalizer_std"],  dtype=torch.float32).clamp_min(1e-8)

def znorm(h):                                # per-dimension z-score, as applied at training time
    return (h - mean) / std

# One attempt. In practice h_t is the base model's final-normalization hidden state
# (model.model.norm output) at an indentation token.
state = None                                 # reset at the START of every attempt
for h_t in line_start_hidden_states:           # <- replace with the real hidden states, in order
    p_fail, state = probe(znorm(h_t).view(1, 1, -1), state)
    # ... steer the next-token logits here, see step 3
```

For the **MLP** head (`probe_8B_fc.pt`, not deployed) the input is instead the concatenation of the previous and
current line-start states, `[h_{t-1}; h_t]`, both z-scored, with no recurrent state. One detail matters if you
reproduce its numbers: at an attempt's **first** line start there is no previous state, and the deployed
convention supplies a plain zero **in normalized space** (`torch.zeros(H)` passed straight through), *not*
`znorm(torch.zeros(H))`, which would be `-mean/std`. The two differ only at that one line start and change the
reported ROC-AUC by less than `1e-3`, but the zero-in-normalized-space form is what the released numbers use.

## 2. Where the probe fires

At **line starts**: any token whose id is in
[`probes/boundary_token_ids.json`](../probes/boundary_token_ids.json) (the filename keeps the
earlier internal name; 229 ids, the vocabulary items decoding to
a whitespace run of two or more spaces). These are the tokens that immediately precede a proof line's real
content. Note that they also occur inside the model's chain-of-thought, and the deployed processor applies no
region gate, so roughly a third of firings happen while the model is still reasoning in prose.

```python
import json
LINE_START_IDS = set(json.load(open("probes/boundary_token_ids.json"))["ids"])

def at_line_start(token_ids):                # token_ids: the ids generated so far
    return bool(token_ids) and token_ids[-1] in LINE_START_IDS
```

## 3. Steer the next-token logits at the line start

The selected setting is the same for both base models: **frequency penalty, `alpha = 0.15`**.

```python
alpha = 0.15

# frequency rule (deployed): penalize tokens already emitted, scaled by p_fail
logits[j] = logits[j] - alpha * p_fail * freq[j]        # freq[j] = count of token j so far

# temperature rule (searched, not selected): flatten the whole distribution
logits = logits * torch.exp(torch.tensor(-alpha * p_fail))
```

The temperature multiplier `exp(-alpha * p_fail)` is exactly sampling at temperature `exp(alpha * p_fail)`, so
at `p_fail = 1` and `alpha = 0.15` it raises the temperature by about 16%. The two rules are not equally strong
at equal alpha: at `alpha = 0.15` the frequency rule moves 5-18 points of mass off the top token where the
temperature rule moves about one.

In practice this runs as a vLLM `logits_processor` invoked at each step; the probe runs on the CPU and the base
weights are never updated.

## 4. Generate on an example theorem, then verify

```python
statement = r"""import Mathlib
import Aesop
set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem sq_nonneg_example (x : Real) : 0 <= x ^ 2 := by
"""
# ... generate steered completions with the logits processor above ...
from verify_lean_robust import verify_one
solved = any(verify_one("sq_nonneg_example", header + completion, timeout=1800)["valid"]
             for completion in attempts)
```

A theorem counts as solved when at least one of its 32 steered attempts verifies. See
[`robust_verification_example.md`](robust_verification_example.md) for the verification step in isolation.

## What to expect

Steering with this setting does **not** improve the prover. On MathOlympiadBench it solves 35 theorems of 360
against the base's 41 on 8B, and 59 against 60 on 32B, and it costs about a sixth of all verifying attempts on
both base models. The per-attempt effect is real and visible in the generations, which are 14-21% shorter; it simply does not
convert into proofs. The results in
[`../results/`](../results/) are the full record of both arms.

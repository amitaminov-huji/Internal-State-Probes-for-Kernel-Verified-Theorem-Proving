# Robust verification

`verify_lean_robust.py` checks a candidate Lean proof against the kernel in a **fresh process**, and accepts it only
if it type-checks with a trusted axiom set. This is the measurement authority for every number in the paper.

`lean_comments.py` is an optional helper, not part of that authority: it removes Lean comments so a text-level
check can be run on code alone. See "Recommended change to step 1".

## Protocol (four steps)

1. Reject placeholder or malformed strings (empty, `None`, error markers) **and any source that
   contains `sorry`**, before compiling anything. The compiler's own `declaration uses 'sorry'`
   warning is caught separately at step 4, so an incomplete proof is rejected either way.
2. Append `#print axioms <thm>` to the Lean file.
3. Compile with `lake env lean` under mathlib4, Lean **4.9.0-rc1**.
4. Reject on a nonzero exit code, any `error:`, a `declaration uses 'sorry'` warning, or an axiom set not contained in
   `{propext, Classical.choice, Quot.sound}`.

A long-running Lean server (REPL) that only reads the shape of the reply, by contrast, accepts proofs that rest on an
off-whitelist axiom (e.g. `native_decide` / a hand-written `axiom`) as false positives, because it never runs
`#print axioms`.

## Recommended change to step 1

Step 1 rejects any source containing `sorry` as a text match, before compiling. **We recommend changing
that**, and ship `lean_comments.py` so either option below is a one-line edit. `verify_lean_robust.py`
itself is unchanged, so every number in the paper still comes from the protocol exactly as described above.

The text check cannot make a bad proof pass, because steps 3 and 4 catch `sorry` on their own: the
compiler emits `declaration uses 'sorry'`, and `#print axioms` reports `sorryAx`, which is outside the
whitelist. What the text check can do is reject a *good* proof, in two ways that a regex over raw source
cannot distinguish from real code:

- **the word inside a comment**, in any of Lean's four comment forms (`--`, `/- -/`, `/-- -/`, `/-! -/`);
- **the word inside a string literal**, e.g. `#eval "sorry"`.

Measured across 59,181 attempts from this project: **106** carry `sorry` only inside a comment, and
**none** carries it only inside a string literal. The check has never actually cost us an attempt, because
all 106 are rejected one step earlier as assembler placeholders — the same failure that comments a proof
body out is what marks the file unusable. But that is a property of this corpus, not a guarantee.

**Option A, recommended: delete the text check.** Steps 3 and 4 are complete on their own, so removing it
costs no soundness and removes both false-rejection risks at once. The price is compute: the attempts it
rejects early would now be compiled (5,116 of 59,181 here, about 9%).

```python
#   if re.search(r'\bsorry\b', s):
#       return False, 'source contains `sorry`'
```

**Option B: keep the early reject, run it on code only.**

```python
from lean_comments import contains_sorry_outside_comments
if contains_sorry_outside_comments(s):
    return False, 'source contains `sorry`'
```

This removes the comment case. The string-literal case remains, which is why Option A is the recommendation.

**Do not try to fix the string case by stripping string literals.** Generated Lean is not guaranteed to
balance its quotes, and a scanner that treats a stray `"` as an opening delimiter swallows everything after
it, including real tactics. That happened once in these 59,181 attempts, and the swallowed span held a
genuine `sorry`. `lean_comments.py` therefore *tracks* strings, so `--` inside a literal is not mistaken for
a comment, but never removes them.

Removing a comment is safe in a way removing a string is not: a comment holds nothing the compiler reads, so
at worst the early reject misses something and steps 3 and 4 catch it.

## Requirements

- A mathlib4 checkout on the **Lean 4.9.0-rc1** toolchain, installed with `elan`.
- A Goedel-Prover-V2 checkout, for `lean_compiler/repl_scheduler_rule_based.py` (the Lean path helpers).

Paths default to the standard Linux layout and are overridden by environment variables of the same name:

| variable | default | what it points at |
|---|---|---|
| `GOEDEL_PROVER_V2` | `~/Goedel-Prover-V2` | the prover checkout, from which the two below are derived |
| `LEAN_WORKSPACE` | `$GOEDEL_PROVER_V2/mathlib4` | the mathlib4 workspace `lake env lean` runs in |
| `LEAN_COMPILER_DIR` | `$GOEDEL_PROVER_V2/lean_compiler` | the directory holding `repl_scheduler_rule_based.py` |
| `LAKE` | `~/.elan/bin/lake` | the `lake` binary (elan's default install location) |

For example:

```bash
LEAN_WORKSPACE=/opt/mathlib4 LAKE=$(which lake) python verify_lean_robust.py
```

## API

```python
from verify_lean_robust import verify_one
res = verify_one(name="my_thm", code=full_lean_source, timeout=1800)
# res = {"valid": bool, "reason": str, "exit_code": int|None, "axioms": [...], ...}
```

`valid=True` means the proof compiled cleanly with an axiom set inside the whitelist. See
[`../guides/robust_verification_example.md`](../guides/robust_verification_example.md) for a worked example.

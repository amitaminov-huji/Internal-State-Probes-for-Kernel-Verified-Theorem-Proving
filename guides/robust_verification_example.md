# Guide: robustly verify a proof

Goal: check one Lean proof end-to-end with the robust protocol.

## 1. An example theorem and a (correct) proof

Build the full Lean source exactly as the model's output would be assembled: the canonical header, the theorem, and
the proof body.

```python
full_code = r"""import Mathlib
import Aesop
set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

theorem add_comm_example (a b : Nat) : a + b = b + a := by
  omega
"""
```

## 2. Verify

```python
from verify_lean_robust import verify_one
res = verify_one(name="add_comm_example", code=full_code, timeout=600)
print(res["valid"], res["axioms"])   # -> True [propext, Classical.choice, Quot.sound]  (or a subset)
```

`valid=True` and the axioms are inside the whitelist, so the proof is accepted.

## 3. A proof the REPL accepts but robust rejects (proving `False`)

`native_decide` trusts the *compiled* value of a definition, while the kernel trusts its *declared* value. An
`@[implemented_by]` attribute can make the two disagree, which turns `native_decide` into a proof of a false
statement. Here the kernel value of `n` is `2` but its compiled value is `1`, so `decide` proves `n = 2`,
`native_decide` proves `n = 1`, and `omega` derives `False`:

```python
bad = r"""import Mathlib
import Aesop
set_option maxHeartbeats 0
open BigOperators Real Nat Topology Rat

def m : Nat := 1
@[implemented_by m] def n : Nat := 2
theorem bad : False := by
  have h1 : n = 2 := by decide
  have h2 : n = 1 := by native_decide
  omega
"""
res = verify_one(name="bad", code=bad, timeout=600)
print(res["valid"], res["axioms"])   # -> False  ['Lean.ofReduceBool', 'propext', 'Quot.sound']
```

The proof compiles with no error and no `sorry`, so a shape-only REPL scorer marks it complete, a false positive.
Robust verification runs `#print axioms bad`, sees the off-whitelist `Lean.ofReduceBool`, and rejects it, which is
what stops the false positives a REPL scorer admits.

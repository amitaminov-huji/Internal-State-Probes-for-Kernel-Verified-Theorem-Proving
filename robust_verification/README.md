# Robust verification

`verify_lean_robust.py` checks a candidate Lean proof against the kernel in a **fresh process**, and accepts it only
if it type-checks with a trusted axiom set. This is the measurement authority for every number in the paper.

## Protocol (four steps)

1. Reject placeholder or malformed strings (empty, `None`, error markers).
2. Append `#print axioms <thm>` to the Lean file.
3. Compile with `lake env lean` under mathlib4, Lean **4.9.0-rc1**.
4. Reject on a nonzero exit code, any `error:`, a `declaration uses 'sorry'` warning, or an axiom set not contained in
   `{propext, Classical.choice, Quot.sound}`.

A long-running Lean server (REPL) that only reads the shape of the reply, by contrast, accepts proofs that rest on an
off-whitelist axiom (e.g. `native_decide` / a hand-written `axiom`) as false positives, because it never runs
`#print axioms`.

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

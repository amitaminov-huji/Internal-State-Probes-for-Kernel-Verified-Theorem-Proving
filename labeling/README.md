# Labelling

How a proof attempt on a mathlib-derived theorem becomes a training label or a validation solve. The code
here is the deployed code, not a re-implementation.

## Why any of this is needed

Every training and validation theorem is a mathlib lemma, so the environment that checks a candidate proof
already contains the answer. Under a full `import Mathlib` the rebuilt declaration collides with the original
and Lean rejects it as *already declared* before the proof is even read, recording a correct proof as a
failure. That force-failed **1,018 of the 1,367** training theorems.

A second problem is independent of the collision. We use Goedel-Prover-V2's released prompt and elaborate
each proof under the context that prompt shows the model, so we never supply file-local context the model has
not seen. A mathlib statement is written against its own file, its section `variable` binders and their
instance arguments, its `open` scopes and local notation, and the corpus gives us the theorem's span without
them, so a statement that needs that context cannot elaborate. Dropping those is what leaves about 20% of the
theorems, **243** training and **90** validation.

## The seven mechanisms, in the order they apply

| # | mechanism | level | applies in |
|---|---|---|---|
| 1 | **dead-statement filter**: drop theorems whose statement already fails to compile (1,367/419 -> 1,080/319) | theorem | both |
| 2 | **rename**: give the rebuilt head a unique `__us` suffix so the declaration is legal. Applied here first, and still in force at checking time | theorem + verify-time | both |
| 3 | **statement-elaboration filter**: keep only theorems whose rebuilt `header + statement := by sorry` elaborates **with the rename already applied** (-> **243 / 90**) | theorem | both |
| 4 | **`attribute [-simp] <target>`**: remove the target's own simp entry, on every collider | verify-time | both |
| 5 | **`attribute [-aesop] <target>`**: in addition, where the target is a registered aesop rule (2 of the 325 colliders) | verify-time | both |
| 6 | **crutch purge**: drop an attempt that *fails* with the guard but *passes* without it | attempt | **training only, by design** |
| 7 | **citation filter**: drop any surviving success whose proof text names the target | attempt | both |
| + | **attribute-error guard**: exclude an attempt whose prepended attribute line itself errored | attempt | both |

The rename precedes the elaboration filter because it is what makes the filter possible: without it a
collider is rejected as *already declared* before Lean ever reaches the statement, so a broken statement and
a merely colliding one are indistinguishable. The keep decision is exactly "the statement elaborates once
renamed".

Mechanisms 2, 4 and 5 are emitted only at **checking time**; the prompt the model saw never contains them.
Mechanism 5 is conditional because the command errors unless the target already is an aesop rule, so it is
gated on the per-theorem classification in `data/theorem_classification.json`.

**A positive therefore means three things at once**: it compiled under the guard, it did not cite the target,
and it did not lean on the target's own automation entry.

## Why mechanism 6 is training-only

The crutch purge only removes attempts that already **failed** under the guard. Training keeps labelled rows,
so removing them changes what the probe sees. The validation contest counts *solves*, and a hard-failure is
not a solve either way, so excluding it versus marking it unsuccessful gives identical solved and passing
counts. It is a design choice, not an inconsistency.

## Not a filter

`l2_residual_timeout` marks an attempt that still timed out after the escalated limit. It is **surfaced for
reporting only** and never drops or passes an attempt: such an attempt stays an ordinary failure. This is why
every reported score is a lower bound.

## How often each fired

| filter | training 8B / 32B | validation 8B / 32B (13 arms) |
|---|---|---|
| attribute-error guard | 0 / 0 | 0 / 1 |
| citation filter | 71 / 51 | 106 / 100 |
| crutch purge | 23 / 2 | not applied |

Training runs over 1,944 attempts per model, leaving **1,850** (8B) and **1,891** (32B) labelled rows, with
364 and 417 positives.

## Layout

- `code/lenient_headers.py`, `build_verify_header`, the single builder both splits call (mechanisms 2, 4 and 5).
- `code/relabel_lenient.py`, `partition_verdicts` (mechanisms 6-7 and the guard), `_err_on_attribute`.
- `code/classify_theorems.py`, assigns each theorem `NONCOLLIDER` / `COLLIDER_NONAESOP` / `COLLIDER_AESOP`.
- `code/citation_filter.py`, `code/filtered_dataset.py`, mechanism 7, and mechanisms 1 and 3.
- `data/`, the classification and the keep- and drop-lists the filters produce.
- `tests/`, a runnable demonstration that each mechanism does what this file says.
- `../guides/labeling_example.md`, one theorem end to end.

## Two caveats

- **The attribute-error guard has a blind spot.** It matches `not registered`, `unknown identifier` and
  `unknown constant`, but **not** `ambiguous identifier`. One validation theorem, `gcd_greatest`, is declared
  at root level, so its complete name has no prefix; the header's `open Nat` then makes that name collide
  with `Nat.gcd_greatest` and Lean errors on the attribute line before reading the proof. All 104 of its
  attempts fail regardless of the model. It is in neither the training nor the test set and scored zero in
  every contest arm, so it moved no result. Only a namespace-less target is exposed this way: the other 324
  of the 325 colliders have a namespaced complete name.
- **The labels are leakage-reduced, not leakage-free.** Erasing the target's own entries does not reach a
  differently-named sibling or a more general form, which Lean gives no way to remove from an imported
  environment; nor an alias a name-based filter misses; nor an easy goal closed by other library lemmas.

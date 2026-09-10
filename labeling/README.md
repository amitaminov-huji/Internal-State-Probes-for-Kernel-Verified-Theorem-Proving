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

## What counts as a label

The rules above can be stated exactly. For an attempt `a` (one theorem paired with one sampling seed),
verification yields four predicates:

| | meaning |
|---|---|
| `h(a)` | compiles under the checking header (`__us` rename + `[-simp]` on colliders + conditional `[-aesop]`) and passes robust verification |
| `s(a)` | compiles under the rename alone, i.e. with the target still fully available, both by name and through its own automation entries |
| `c(a)` | the proof text names the target lemma |
| `e(a)` | the prepended attribute line itself errored |

Writing `A` for the attempts of a split:

```
P_train = P_val = { a in A : h and not c }
N_train         = { a in A : not s and not e }
D_train         = { a in A : (h and c)  or  (s and not h)  or  e }
                               citation      automation       attribute
                               filter        erase            guard
A = P_train + N_train + D_train
```

A positive is an attempt the kernel accepts with the target's own automation entries removed and without
naming it. A **negative label** is one the kernel rejects **even when the target is fully available**, by name
or through its automation. The three terms of `D_train` are exactly the three attempt-level mechanisms, so the
partition is also the reason each of them exists.

Two implications hold, measured over all 3,888 training attempts with 0 violations each. **`h => s`**: the
checking header only removes lemmas, so anything compiling under it compiles without it, which is why the
negative rule reads `not s` rather than `not h and not s`. It is worth measuring rather than assuming, because
dropping a `simp` lemma can in principle stop `simp` diverging. **`e => not h`**: the guard is consulted only
on a failure, so `not e` excludes only an attribute error whose proof also fails unguarded. No training
attempt is of that kind, but the term is not redundant.

**Validation applies the same positive rule and discards nothing** (there is no `D_val`; a citing pass or an
attribute error is simply not a solve), **and its negatives are never used**: the contest ranks arms by
theorems solved, then by passing attempts, both of which count positives only.

### What the mechanisms cost

Of the attempts the kernel accepts with the target fully available (458 on 8B, 470 on 32B), the automation
erase removes 23 and 2 (5.0%, 0.4%) and the citation filter 71 and 51 (15.5%, 10.9%), leaving the 364 and 417
positives the probes train on. Among the negative labels, 3.8% (8B) and 4.2% (32B) name the target, against
16.3% and 10.9% of accepted proofs; how many reach it through automation is very difficult to measure, because
a failed attempt has no completed proof to attribute steps to. Per-mechanism counts are in the table above.

Both definitions are the strictest available in this setup: on the positive side the smallest set, since every
alternative is a superset; on the negative side the highest evidential bar, since an attempt counts as a
failure only if it fails with the target fully available. Softening either changes little: relaxing the
positive rule adds at most 94 attempts on 8B (+25.8%) and 53 on 32B (+12.7%), and relaxing the negative rule,
by no longer counting a failure that names the target, removes 56 (-3.8%) and 62 (-4.2%). Those are kept
deliberately: an attempt given the target that still failed is the best-evidenced negative there is.

## Why the citation filter matches positions, not mentions

The filter asks *where* the target's name appears, not *whether* it appears. It flags a name after
`exact`/`apply`/`refine`, immediately after `:=`, after `using`, before a rewrite arrow, or inside a
`[...]` bracket. The obvious alternative, "drop any success whose proof contains the name", is worse in both
directions. The population is the **positive labels** of the training and validation theorem proof attempts,
that is, exactly what the deployed filter passed: 781 in training (364 on 8B and 417 on 32B, the counts above) plus 2,617 in validation,
**3,398** attempts.

| rule | positives it would discard | citations it would miss |
|---|---:|---:|
| deployed: the name in a citation position | — (this set is its output) | — |
| naive: **short** name anywhere | **71** of 3,398 (2.1%) | 0 |
| naive: **full** name anywhere | 0 | **29** of 122 |

The two failure modes are opposite. The 71 positives a short-name rule would discard are not citations:
`id`, the identity function, in `g ∘ f = id` (64 attempts, target `Function.LeftInverse.id`); `ext`, the
*tactic* (3, target `Group.ext`); `map`, a field access `A.map f` (3, target `Matrix.IsDiag.map`); and one
`simpa [toReal] using Real.toReal_zero` (target `EReal.toReal_zero`). That last one is not a lemma from
another namespace, which is what we first assumed: `Real.toReal_zero` **does not exist**, and the attempt
compiles because `simp [toReal]` closes the goal on its own, with Lean's linter suggesting `simp` instead of
`simpa`. The statement is true by definition, so no lemma is involved at all.

A name rule would also fire on the model quoting the theorem it was asked to prove. Blanking Lean comments and
re-checking, the target's full name appears in 373 attempts and in **29 of them only inside a comment**. All 29
are negatives, where the citation filter is never consulted, so nothing would have changed here; nothing
prevents the same echo in a positive, and there it would discard a genuine success. A full-name rule never over-catches, but of the **122** citations the filter did
remove from the accepted training attempts (71 on 8B, 51 on 32B) only **93** carry the full name: the other
**29** name the target by its short name alone, and a full-name rule would have admitted all 29 as
positives. The short name is needed, and requiring a citation position is what makes matching it safe.

The opposite risk, a real citation in a position the list does not cover, was checked by sweeping **all
13,248** training and validation attempts (243 theorems x 8 attempts x 2 base models = 3,888 training;
90 x 4 x 13 contest arms x 2 = 9,360 validation) for a target name the filter did not flag. 350 attempts mention it
uncaught; 33 of those use the full name, all in *failing* attempts, and **29 of the 33** are the model echoing
the theorem statement in a `--` comment rather than citing it. The other 4 put the name in code: one restates
the theorem as a nested declaration, and three are genuine citations of the form `have h := @X ...`, which the
filter misses because Lean's explicit-argument prefix `@` defeats the `:=` and `using` patterns (the
`exact`/`apply`/`refine` and bracket patterns allow arbitrary text and survive it). The 71 accepted ones are
the short-name false alarms above. **No accepted proof cites the target through a form the filter missed.**

Those three missed citations are not leakage that escaped, and the formal definitions are what settle it. The
filter is consulted **only on successes**: the positive rule is `h ∧ ¬c`, and the partition gates the citation
drop on `hard_ok`, so a citing failure keeps its negative label. The negative rule is `¬s ∧ ¬e`, with **no `c`
term at all** — a negative is by definition an attempt that failed *with the target fully available*, by name
and through its automation, and allowing that is exactly what makes the negative evidentially strict. So those
three are the negative rule working: the model applied the very lemma it was asked to prove and the kernel
still rejected the proof. The `@` gap would matter for an *accepted* attempt of that shape, and none occurs.
Like the `aesop (add norm simp X)` form, it is left unfixed: the labels are frozen.

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

Two notes on reading the code. It is the code that ran, changed in exactly one way: the absolute paths
it used on our cluster are replaced by `<REPO>`, which you set to your own checkout. And its docstrings
carry a second, older numbering from the design document this was built against, in which the citation
filter is "mechanism 3"; that numbering is unrelated to the table above.

## Three caveats

- **The attribute-error guard has two blind spots, and has never bound.**
  *First, the message list.* It matches `not registered`, `unknown identifier` and `unknown constant`, but
  **not** `ambiguous identifier`. One validation theorem, `gcd_greatest`, is declared at root level, so its
  complete name has no prefix; the header's `open Nat` then makes that name collide with `Nat.gcd_greatest`
  and Lean errors on the attribute line before reading the proof. All 104 of its attempts fail regardless of
  the model. It is in neither the training nor the test set and scored zero in every contest arm, so it moved
  no result.
  *Second, the quoting.* The guard requires the target's name as a quoted identifier, and Lean quotes names as
  `'X'`, so a sibling ending in a prime makes the target's own quoted form a substring of an unrelated error.
  The guard fired exactly once in the project, on `Ordinal.lift_lt` in one 32B contest arm, and that firing was
  a **false positive** of exactly this kind: `unknown constant 'Ordinal.lift_lt'.mpr'` came from the proof
  body, which used the primed sibling `Ordinal.lift_lt'`, while the attribute line compiled cleanly. That
  attempt was failing anyway, so the guard changed no label and no count anywhere in this project.
  *Neither is fixed here*, because the labels are frozen and either fix would change what was measured.
- **`gcd_greatest` is the only broken header, measured.** Over the 243 training theorems the stored compiles
  show no error on any theorem's attribute line; in validation a broken header would fail every attempt of its
  theorem, so we compiled the header of each of the 28 theorems that scored zero in every arm, and found only
  this one. A namespace-less complete name is the reason it happens, not the evidence that it happens only
  here.
- **The labels are leakage-reduced, not leakage-free.** Erasing the target's own entries does not reach a
  differently-named sibling or a more general form, which Lean gives no way to remove from an imported
  environment; nor an alias a name-based filter misses; nor an easy goal closed by other library lemmas.

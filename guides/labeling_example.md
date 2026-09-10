# Labelling one theorem, end to end

`Finset.Subset.refl` from `Mathlib/Data/Finset/Basic.lean`, a `COLLIDER_NONAESOP` among the retained validation theorems.
Everything below is the deployed builder's output or a verbatim stored artifact.

## 1. What the model saw (prompt header)

The namespace travels into the prompt; the blinding does not. The model is never shown the attribute line or
the rename.

```lean
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

namespace Finset
```

## 2. What the checker saw (verify header, from `build_verify_header`)

```lean
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

attribute [-simp] Finset.Subset.refl
namespace Finset
```

Two additions, both verification-time only: `attribute [-simp] Finset.Subset.refl` erases the target's own
simp entry, and it sits **before** `namespace Finset` so the name resolves unambiguously at root level. Had
this theorem been one of the two registered aesop rules, an `attribute [-aesop]` line would follow the simp
one, still before the namespace.

## 3. The attempt as stored

Verbatim from `validation_contest_w2cfhl/8B/val_ext/vanilla/metadata_labeled.jsonl`
(seed 0, `success = True`):

```lean
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

attribute [-simp] Finset.Subset.refl
namespace Finset.Subset

theorem Subset.refl__us (s : Finset α) : s ⊆ s := by 
  have h_main : s ⊆ s := by
    intro x hx
    exact hx
  exact h_main
```

Note the head is `Subset.refl__us`, not `Subset.refl`: the rename is what makes the declaration legal under a
full import.

## 4. What each attempt-level filter decides

| filter | on this attempt | why |
|---|---|---|
| attribute-error guard | pass | the attribute line compiled; no `not registered` / `unknown identifier` / `unknown constant` error naming the target |
| citation filter | pass | the proof body never names `Finset.Subset.refl` |
| crutch purge | not applied | validation only counts solves; in **training** this would drop an attempt that fails with the guard but passes without it |

So this counts as a solve: compiled under the guard, no citation, no reliance on the target's own automation
entry.

## 5. The same theorem, had the proof cited the target

`... := by exact Finset.Subset.refl s` would compile and would be a *success* under plain verification. The
citation filter drops it, because a proof of a lemma is not allowed to be that lemma. That is the single
largest filter in practice: 71 (8B) and 51 (32B) such successes were dropped in training.

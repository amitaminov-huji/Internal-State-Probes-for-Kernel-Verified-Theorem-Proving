# Labelling one theorem, end to end

`Finset.Subset.refl` from `Mathlib/Data/Finset/Basic.lean`, a `COLLIDER_NONAESOP` among the retained validation theorems.
Everything below is the deployed builder's output or a verbatim stored artifact.

## 1. What the model saw (the prompt)

The namespace travels into the prompt; the blinding does not. The model is never shown the attribute line or
the rename. Here is this theorem's prompt header:

```lean
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

namespace Finset.Subset
```

That header sits inside the released completion prompt template, which is what the model is actually
decoded from. **Training and validation prompts have the same structure**, so one stored example shows it
for both. This one is verbatim from a training attempt (`Function.const_comp`, seed 0,
`hidden_states_w2/8B/shard_0/attempts.jsonl`, fields `prompt` and `prompt_token_ids`); validation prompts
are not stored, which is why the example is a training one rather than this section's theorem.

````
<|im_start|>user
Complete the following Lean 4 code:

```lean4
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

namespace Function

theorem const_comp {γ : Sort*} (f : α → β) (c : γ) : const β c ∘ f = const α c```

Before producing the Lean 4 code to formally prove the given theorem, provide a detailed proof plan outlining the main proof steps and strategies.
The plan should highlight key ideas, intermediate lemmas, and proof structures that will guide the construction of the final formal proof.<|im_end|>
<|im_start|>assistant
````

**Four parts**: the instruction, the Lean header with the theorem's namespace, the formal statement, and the
closing instruction to plan the proof first. A MathOlympiadBench prompt has **five**, because those theorems
carry an informal statement of the problem as a comment, and its statement ends `:= by sorry` where a library
statement ends at its type. The template is identical in both cases; only what is slotted into it differs.

## 2. What the checker saw (verify header, from `build_verify_header`)

```lean
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

attribute [-simp] Finset.Subset.refl
namespace Finset.Subset
```

Two additions, both verification-time only: `attribute [-simp] Finset.Subset.refl` erases the target's own
simp entry, and it sits **before** `namespace Finset.Subset` so the name resolves unambiguously at root level. Had
this theorem been one of the two registered aesop rules, an `attribute [-aesop]` line would follow the simp
one, still before the namespace. The namespace is the theorem's own, `Finset.Subset`, so the head below is
`Subset.refl__us` rather than `refl__us`: the rebuilt statement keeps the source's spelling of the head.

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

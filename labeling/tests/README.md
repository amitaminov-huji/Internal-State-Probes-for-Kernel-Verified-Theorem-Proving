# Tests

Demonstrations that each labelling and filtering mechanism does what `../README.md` says.

```bash
python -m unittest discover -s .          # CPU only, no artifact tree needed
LEAN_TESTS=1 LEAN_WORKSPACE=/path/to/mathlib4 python -m unittest discover -s .   # adds the Lean checks
```

| file | covers |
|---|---|
| `test_verify_header.py` | the rename, the simp erase, the conditional aesop erase, and that both erases precede `namespace` |
| `test_partition_verdicts.py` | the citation filter, the crutch purge, the attribute-error guard, its message list and its two blind spots |
| `test_theorem_filters.py` | the dead-statement and statement-elaboration filters, keep/drop disjointness, class counts |
| `test_counts_and_parity.py` | the published counts close arithmetically and match this README; crutch purge is training-only |
| `test_lean_slow.py` | the erases really disable the rules in Lean (skipped by default) |

Four are deliberately **characterisation** tests, pinning behaviour that produced the released labels so it
is not mistaken for a bug, including where that behaviour is wrong:
`test_ambiguous_identifier_is_not_matched` (the `gcd_greatest` blind spot),
`test_a_primed_sibling_IS_misread_the_known_defect` and `test_the_one_real_firing_was_this_defect` (the
quoting defect, which made the guard's only firing in the project a false positive), and
`test_crutch_purge_is_training_only_and_declared_so`. The two defect tests **fail if the predicate is ever
fixed**, which is the intent: the labels are frozen, so a fix would change what was measured.

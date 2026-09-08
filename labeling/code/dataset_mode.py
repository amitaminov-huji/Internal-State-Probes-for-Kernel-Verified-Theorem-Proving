"""Clean-dataset (collision-prefilter) mode toggle — POC, default OFF.

The scaled pipeline's default path KEEPS every LeanDojo theorem (75% of whose reconstructed
statements collide with the real Mathlib name under `import Mathlib`) and handles the resulting
citation channel with three collision-era mechanisms: the `__us` verify-head rename
(`reconstruct.py`), the `attribute [-simp] X` erase (`to_generation_record`), and the citation
text filter (`citation_filter.py`).

An ALTERNATIVE dataset is a pool PREFILTERED to non-colliding theorems only (`full_name` absent
from `import Mathlib`). For such theorems the target lemma X is not in the environment, so the
citation channel cannot occur — the three mechanisms above become unnecessary. This flag turns
them OFF (it does NOT delete them), so the alternative can be evaluated as an ablation/robustness
baseline without losing the default path.

`CLEAN_DATASET_MODE=1` (alias `PREFILTER_COLLISIONS=1`) enables it. Default OFF → the default
recover+filter behavior is byte-identical. Feasibility POC + the reason this is an ablation, not
the main dataset (positive-class collapse): rundocs/citation_channel_investigation.md §10.
"""
from __future__ import annotations

import os


def clean_dataset_mode() -> bool:
    """True iff the pool is a prefiltered non-collider set and the collision-era mechanisms
    (`__us` rename, `attribute [-simp] X` erase, citation filter) should be turned OFF."""
    return (os.environ.get("CLEAN_DATASET_MODE", "0") == "1"
            or os.environ.get("PREFILTER_COLLISIONS", "0") == "1")

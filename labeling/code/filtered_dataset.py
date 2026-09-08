"""Single source for the dead-statement-FILTERED scale2p5 dataset + the FILTERED_DATASET_MODE
toggle (default OFF). Mirrors dataset_mode.py.

When FILTERED_DATASET_MODE=1, a consumer that resolves its COLLECTION_DIR / MANIFEST through the
helpers below reads the filtered copies under new_results/data/leandojo_filtered (dead-statement
theorems removed): the collection VIEW (features symlinked to the original + filtered labels) and
the filtered manifest (dead train+val removed, hash recomputed). Default OFF -> byte-identical to
the unfiltered pipeline. See new_results/analysis/dead_statement_filter_plan.md.

INVARIANT: a filtered manifest is only ever paired with the filtered VIEW (filtered labels) —
never the original labels — else split_of() KeyErrors on removed ids. Resolving BOTH through this
module keeps them consistent.
"""
from __future__ import annotations

import json
import os

REPO = "<REPO>"
FILTERED_ROOT = f"{REPO}/new_results/data/leandojo_filtered"
FILTERED_MANIFEST = f"{FILTERED_ROOT}/split_manifest_scale2p5_filtered.json"
DEAD_JSON = {"train": f"{FILTERED_ROOT}/dead_statements_train.json",
             "validation": f"{FILTERED_ROOT}/dead_statements_val.json"}
# stage-2 statement-elaboration drops (collider statement-recon failures + genuine >600s timeouts), kept
# in a SEPARATE file so the stage-1 dead-statement list stays dead-only; dead_theorem_ids() unions both.
ELAB_JSON = {"train": f"{FILTERED_ROOT}/elaboration_drop_train.json",
             "validation": f"{FILTERED_ROOT}/elaboration_drop_val.json"}


def filtered_dataset_mode() -> bool:
    return os.environ.get("FILTERED_DATASET_MODE", "0") == "1"


def filtered_collection_dir(model: str) -> str:
    return f"{FILTERED_ROOT}/collection_{model}"


def _model_of(path: str) -> str | None:
    """Infer 8B/32B from a *_train_scale2p5 collection path (32B first — substring safety)."""
    for m in ("32B", "8B"):
        if f"{m}_train_scale2p5" in path or f"collection_{m}" in path:
            return m
    return None


def resolve_collection_dir(default: str) -> str:
    """Map a train collection path to its filtered VIEW when the toggle is on; else pass through."""
    if not filtered_dataset_mode():
        return default
    m = _model_of(default)
    view = filtered_collection_dir(m) if m else None
    return view if view and os.path.isdir(view) else default


def resolve_manifest(default: str) -> str:
    """Return the filtered manifest when the toggle is on and it exists; else pass through."""
    if filtered_dataset_mode() and os.path.exists(FILTERED_MANIFEST):
        return FILTERED_MANIFEST
    return default


def dead_theorem_ids(split: str) -> set:
    """The FULL removed set for a split ('train'/'validation') = stage-1 dead statements UNION stage-2
    statement-elaboration drops (STMT_RECON + genuine timeouts). This is the set every consumer must
    exclude to stay on the CLEAN theorems. {} if the files are absent."""
    out: set = set()
    p = DEAD_JSON.get(split)
    if p and os.path.exists(p):
        out |= set(json.load(open(p))["theorem_ids"])
    e = ELAB_JSON.get(split)
    if e and os.path.exists(e):
        out |= {r["theorem_id"] for r in json.load(open(e))}   # elaboration_drop = list of {theorem_id, reason}
    return out

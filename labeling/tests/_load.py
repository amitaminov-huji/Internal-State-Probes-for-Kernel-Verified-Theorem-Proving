"""Import the deployed modules for testing without pulling the full research pipeline.

`lenient_headers` is stdlib-only and imports directly. `relabel_lenient.partition_verdicts` is a pure
function living in a module whose top-level imports reach the verifier and several pipeline packages, none of
which it needs; we stub those so the REAL function is exercised rather than a copy.
"""
import importlib.util, pathlib, sys, types

CODE = pathlib.Path(__file__).resolve().parent.parent / "code"
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def lenient_headers():
    return _load("lenient_headers", CODE / "lenient_headers.py")


def _stub_pipeline():
    """Stub the pipeline packages the shipped modules import but do not need under test.

    Installed by every loader below, so no loader depends on another having run first.
    """
    for name in ("verify_lean_robust", "probe_pipeline", "probe_pipeline.data",
                 "probe_pipeline.inference", "probe_pipeline.labeling"):
        sys.modules.setdefault(name, types.ModuleType(name))
    for name, attrs in (("probe_pipeline.data.reconstruct", ()),
                        ("probe_pipeline.data.citation_filter", ("is_citation",)),
                        ("probe_pipeline.data.dataset_mode", ("clean_dataset_mode",)),
                        ("probe_pipeline.data.filtered_dataset", ("dead_theorem_ids",)),
                        ("probe_pipeline.inference.legacy_assembly", ("assemble_legacy",)),
                        ("probe_pipeline.labeling.lenient_headers", ("Classification", "build_verify_header"))):
        if name in sys.modules:
            continue
        m = types.ModuleType(name)
        for a in attrs:
            setattr(m, a, lambda *a_, **k_: None)
        sys.modules[name] = m


def citation_filter():
    """The shipped citation filter, with its pipeline imports stubbed."""
    _stub_pipeline()
    return _load("citation_filter", CODE / "citation_filter.py")


def partition_verdicts():
    _stub_pipeline()
    return _load("relabel_lenient", CODE / "relabel_lenient.py").partition_verdicts

"""Expose T3 compaction regressions to canonical and same-stem smoke discovery."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SOURCE = (Path(__file__).resolve().parents[1] / "integrations" /
           "t3_cost_aware_compaction" / "test_compaction.py")
_SPEC = spec_from_file_location("t3_compaction_regression_suite", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_SUITE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SUITE)
T3AdaptiveCompactionTests = _SUITE.T3AdaptiveCompactionTests

"""Prevent stale October 15 Fabric release instructions being executed as current.

Static source-only release check; never reads a live M2 host or changes worker policy.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "integrations" / "fleet" / "ubuntu_thermal_headroom_20261013"
DOCUMENTS = (
    "OPUS_NEXT_RELEASE_FRONTIER_20261015.md",
    "FABRIC_COMBINED_SPARSE_CPU_SCOPE_RELEASE_EVIDENCE_20261015.md",
    "README.md",
)
MARKER = "DO_NOT_REAPPLY_COMBINED_PATCH"


def test_all_historical_release_docs_have_dated_top_level_supersession():
    for name in DOCUMENTS:
        text = (ROOT / name).read_text()
        top = text[:2100]
        assert MARKER in top, name
        assert "2026-10-16" in top, name
        assert "12/18/12/12" in top, name
        assert "80°C" in top, name
        assert "no force reset" in top, name


def test_current_overlay_does_not_erase_original_historical_evidence():
    frontier = (ROOT / DOCUMENTS[0]).read_text()
    combined = (ROOT / DOCUMENTS[1]).read_text()
    policy = (ROOT / DOCUMENTS[2]).read_text()
    assert "DONE_WHEN" in frontier
    assert "NOT_INSTALLED / NOT_RELEASED" in combined
    assert "HISTORICAL_POLICY_ONLY_DO_NOT_APPLY" in policy
    assert "DO_NOT_REDO_STATIC_RESTORE" in policy

"""Static regression guard for fleet source-release registry separation.

This guards repository proposal contents only; never reads/writes M2 policy,
never restores configured capacity and never interferes with emergency derates.
"""
from pathlib import Path
import re

BASE = Path(__file__).resolve().parents[1] / "integrations/fleet/ubuntu_thermal_headroom_20261013"
HISTORICAL = {"intel_package_thermal_admission.patch", "precheckout_disk_admission.patch"}


def _registry_deltas(patch: str) -> bool:
    return bool(re.search(r"(?m)^(?:--- a|\+\+\+ b)/hosts\.json$", patch))


def test_release_candidates_never_include_host_registry_rewrites():
    for candidate in ("FABRIC_COMBINED_SPARSE_AND_CPU_SCOPE_20261015.patch",
                      "FABRIC_ACCEPTED_WORKTREE_RECLAIM_PLAN_20261015.patch"):
        assert not _registry_deltas((BASE/candidate).read_text()), candidate


def test_historical_registry_patches_are_explicitly_quarantined_in_docs():
    found = {p.name for p in BASE.glob("*.patch") if _registry_deltas(p.read_text())}
    assert found == HISTORICAL, f"New registry-bearing patch requires source-owner review: {found}"
    docs = (BASE/"README.md").read_text()
    assert "HISTORICAL_POLICY_ONLY_DO_NOT_APPLY" in docs
    for filename in HISTORICAL:
        assert f"{chr(96)}{filename}{chr(96)}" in docs
    assert docs.count("DO NOT APPLY TO LIVE REGISTRY") >= len(HISTORICAL)


def test_current_capacity_documentation_fences_obsolete_rethrottle():
    docs = (BASE/"README.md").read_text()
    frontier = (BASE/"OPUS_NEXT_RELEASE_FRONTIER_20261015.md").read_text()
    for document in (docs,frontier):
        assert "DO_NOT_REDO_STATIC_RESTORE" in document
        assert "726ce27f38ecc8ce407cc0496e61ea66db3e731eb4ce3a60f9ae291a0321e048" in document
    assert "max_active=1, load_gate=4" not in frontier
    assert "conservative one-lane new-worker limits" not in frontier
    assert "12/18/12/12" in docs and "12/18/12/12" in frontier
    assert "new-job" in docs and "new-job" in frontier


def test_neither_release_candidate_embeds_a_legacy_derate():
    for candidate in ("FABRIC_COMBINED_SPARSE_AND_CPU_SCOPE_20261015.patch",
                      "FABRIC_ACCEPTED_WORKTREE_RECLAIM_PLAN_20261015.patch"):
        data=(BASE/candidate).read_text()
        assert not re.search(r"(?m)^\+.*(?:max_active.*[=:]\s*1|ubuntu[23].*max_active.*1)", data)


def test_registry_patch_detector_catches_new_policy_rewrite():
    assert _registry_deltas("--- a/hosts.json\n+++ b/hosts.json\n@@ -1 +1 @@\n")
    assert not _registry_deltas("--- a/remote_sub.sh\n+++ b/remote_sub.sh\n")
    assert not _registry_deltas("note only: previous hosts.json was modified")


def test_board_runbook_distinguishes_current_gate_from_firmware_thermal_point():
    board = (BASE / "BOARD_LEVEL_THERMAL_ACCEPTANCE.md").read_text()
    assert "**80°C**" in board
    assert "85°C" in board
    assert "not the current Fabric admission threshold" in board
    assert "refuses new automatic placement at 85°C" not in board
    assert "DO_NOT_REDO_STATIC_RESTORE" in board
    assert "12/18/12/12" in board
    assert "Both hosts already report Balanced" in board
    assert "https://www.msi.com/Landing/msi-click-bios-intel-amd-motherboard" in board

"""Source-only test of the M2 host guard overlay. Never modify installed hooks."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from integrations.cursor_agent_mastermind import m2_host_guard_overlay as overlay


ROOT = Path(__file__).resolve().parents[1]
LIVE_GUARD = Path.home() / ".claude/hooks/mastermind_fabric_routing_guard.py"
EXPECTED_COMPANION = "d9dd42958800ea888279d62d457814bd16230af4d1e9f6d9bca11c07bf0413dd"


def test_overlay_requires_exact_preimage_and_is_pure() -> None:
    assert overlay.EXPECTED_PREIMAGE.startswith("d1fabbcb")
    assert overlay.EXPECTED_CANDIDATE.startswith("9c701148")
    with pytest.raises(overlay.StaleHostGuardError, match="preimage"):
        overlay.compose_installed_guard(b"not a reviewed M2 guard")
    with pytest.raises(overlay.StaleHostGuardError, match="preimage"):
        overlay.compose_installed_guard(b"")


def test_overlay_only_admits_cursor_runtime_attested_task() -> None:
    insertion = overlay.INSERT
    assert 'tool == "Task" and "cursor_version" in payload' in insertion
    assert 'from cursor_native_child_policy import evaluate_cursor_task' in insertion
    assert 'is_mastermind_scope({"cwd": project_dir})' in insertion
    assert 'CURSOR_VERSION' not in insertion
    assert 'No Fabric worker authority.' in insertion
    assert 'if tool not in ("Agent", "Task")' not in insertion


def test_reviewed_companion_source_has_exact_digest() -> None:
    companion = ROOT / "ops/executive_os/cursor_native_child_policy.py"
    assert sha256(companion.read_bytes()).hexdigest() == EXPECTED_COMPANION


def test_exact_m2_host_overlay_composes_without_writing_live_guard() -> None:
    if not LIVE_GUARD.is_file():
        pytest.skip("M2 installed guard absent on independent host")
    original = LIVE_GUARD.read_bytes()
    if sha256(original).hexdigest() != overlay.EXPECTED_PREIMAGE:
        pytest.skip("M2 installed preimage changed, original-owner reconciliation required")
    candidate = overlay.compose_installed_guard(original)
    assert sha256(candidate).hexdigest() == overlay.EXPECTED_CANDIDATE
    compile(candidate, "m2_host_guard_candidate.py", "exec")
    assert sha256(LIVE_GUARD.read_bytes()).hexdigest() == overlay.EXPECTED_PREIMAGE

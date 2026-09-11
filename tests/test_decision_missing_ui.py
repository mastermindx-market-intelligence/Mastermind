"""Behavioral decision-log truth for missing PM submissions."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "app" / "static" / "index.html").read_text()
NODE = shutil.which("node")


def _slice(start_marker: str, end_marker: str) -> str:
    start = HTML.index(start_marker)
    return HTML[start:HTML.index(end_marker, start)]


def _presentation(payload: dict) -> dict:
    if NODE is None:
        pytest.skip("node is required for JavaScript behavior proof")
    start = HTML.index("function _decisionPresentation(d, isZh)")
    end = HTML.index("function _decisionActionChip(h, kind, isZh)", start)
    function = HTML[start:end]
    script = function + "\nconsole.log(JSON.stringify(_decisionPresentation(" + \
        json.dumps(payload) + ", false)));\n"
    result = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def test_missing_submission_is_not_presented_as_rejected_proposal() -> None:
    view = _presentation({"target_status": "rejected_no_submission"})
    assert view["kind"] == "missing"
    assert view["label"] == "DECISION MISSING — RECOVERY REQUIRED"
    assert "no valid portfolio decision" in view["note"].lower()
    assert "carried unchanged" in view["note"].lower()
    assert view["rows"] == []


def test_scheduler_table_surfaces_safe_decision_failure_reason() -> None:
    render = _slice("function renderDeskScheduler()", "function renderDeskStrategist()")
    assert "j.last_reason" in render
    assert "j.last_target_status" in render
    assert "replace(/_/g, ' ')" in render
    assert "esc(detailStr)" in render


def test_governance_rejection_remains_a_rejected_proposal() -> None:
    view = _presentation({
        "target_status": "rejected_packet_gate",
        "holdings": [{"ticker": "AAPL", "weight": 0.1}],
    })
    assert view["kind"] == "rejected"
    assert view["label"] == "NOT APPLIED / REJECTED"
    assert "proposal was not applied" in view["note"].lower()
    assert [row["ticker"] for row in view["rows"]] == ["AAPL"]

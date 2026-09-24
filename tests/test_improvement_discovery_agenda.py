"""The real Agenda producer/reader contract: additive, private-safe, no priority changes."""
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from brain import improvement_agenda as A
from brain import improvement_discovery as D

# Shared test input only, not an installed research corpus or a second registry.
from test_improvement_discovery import bundle, NOW  # noqa: F401


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "_OUT", tmp_path / "agenda")
    monkeypatch.setattr(A, "_ROOT", tmp_path)
    monkeypatch.setattr(A, "_VALIDATION_DIR", tmp_path / "validation")
    # A missing-input test must not inherit another module's live owner snapshot.
    from brain import nw_reflection
    monkeypatch.setattr(nw_reflection, "latest", lambda: {})
    for name in ("_from_calibration", "_from_journal", "_from_shadow", "_from_benchmark",
                 "_from_book_lifecycle", "_from_validation", "_from_cost_guard",
                 "_from_deploy_lag", "_from_model_drift", "_from_nw_reflection",
                 "_from_experiment_registry", "_from_accruing_experiments", "_from_experiment_tristate"):
        monkeypatch.setattr(A, name, lambda *args: [])
    monkeypatch.setattr(A, "_load_agentos_readiness", lambda: ({}, {
        "available": False, "degraded": ["isolated fixture"], "schema": None}, "macro_unavailable"))
    return tmp_path


def test_real_agenda_keeps_ranked_items_identical(isolated, monkeypatch, bundle):
    fixed = A._item("known", A.CLASS_NW, "Existing ranked item", evidence=["existing receipt"],
                    suggested_fix="Existing scoped fix", fix_type=A.FIX_CODE,
                    expected_impact="Existing impact", owner=A.OWNER_OPUS)
    monkeypatch.setattr(A, "_from_nw_reflection", lambda *args: [deepcopy(fixed)])
    before = A.build(date(2026, 9, 24), cio_rep={})
    after = A.build(date(2026, 9, 24), cio_rep={}, discovery_bundle=bundle, discovery_now=NOW)
    for key in ("items", "n_items", "class_counts", "owners", "readiness_input"):
        assert before[key] == after[key]
    assert after["discovery"]["diagnosis_counts"] == {"EVIDENCED_GAP": 1}
    assert "no jobs dispatched" in after["note"]


def test_existing_writer_and_latest_preserve_safe_projection(isolated, bundle):
    bundle["observations"][0]["finding"] = "PRIVATE_FINDING_NEVER_PUBLISH"
    report = A.build(date(2026, 9, 24), cio_rep={}, discovery_bundle=bundle, discovery_now=NOW)
    receipt = A.write(date(2026, 9, 24), prebuilt=report)
    assert receipt["ok"] is True
    reread = A.latest()
    assert reread["discovery"] == report["discovery"]
    assert "PRIVATE_FINDING" not in json.dumps(reread)
    md = (isolated / "agenda" / "AGENDA.md").read_text()
    assert "EVIDENCED_GAP: 1" in md  # visible even with zero ranked items
    assert "PRIVATE_FINDING" not in md


@pytest.mark.parametrize("value,now,reason", [(None, None, "NOT_SUPPLIED"),
    ({"PRIVATE_SECRET": "do not echo"}, NOW, "INVALID_INPUT"),
    ({}, None, "EXPLICIT_CLOCK_REQUIRED")])
def test_missing_and_malformed_are_visible_not_clean(isolated, value, now, reason):
    report = A.build(date(2026, 9, 24), cio_rep={}, discovery_bundle=value, discovery_now=now)
    assert report["discovery"]["state"] == "UNAVAILABLE"
    assert report["discovery"]["reason_code"] == reason
    assert "PRIVATE_SECRET" not in json.dumps(report)
    assert "zero gaps cannot be inferred" in report["note"]


def test_cli_real_entrypoint_and_invalid_payload_is_opaque(isolated, bundle):
    cli = Path(__file__).resolve().parents[1] / "scripts" / "improvement_discovery.py"
    source = isolated / "input.json"; source.write_text(json.dumps(bundle))
    run = subprocess.run([sys.executable, str(cli), str(source), "--now", NOW,
                          "--format", "public-summary"], capture_output=True, text=True, timeout=10)
    assert run.returncode == 0
    assert json.loads(run.stdout)["jobs_created"] == 0
    source.write_text('{"PRIVATE_SECRET": true}')
    run = subprocess.run([sys.executable, str(cli), str(source), "--now", NOW],
                         capture_output=True, text=True, timeout=10)
    assert run.returncode == 2
    assert "PRIVATE_SECRET" not in run.stderr
    assert not run.stdout

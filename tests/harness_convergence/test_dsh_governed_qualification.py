"""Adversarial qualification CLI tests; no external donor/provider required."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
QUALIFIER = ROOT / "scripts/qualify_dsh_governed_worker.py"


def launch(supply: Path, evidence: Path):
    return subprocess.run(
        [sys.executable, str(QUALIFIER), "--supply", str(supply),
         "--evidence-dir", str(evidence)],
        cwd=ROOT, capture_output=True, text=True, timeout=12, check=False,
    )


def test_absent_supply_never_records_skipped_tests_as_success(tmp_path):
    receipt = tmp_path / "receipt"
    result = launch(tmp_path / "does-not-exist", receipt)
    assert result.returncode == 2, result.stderr
    report = json.loads((receipt / "qualification.json").read_text())
    assert report["status"] == "MISSING_SUPPLY"
    assert report["provider_calls"] == 0 and report["installed"] is False
    assert not (receipt / "tests.xml").exists()


def test_manifest_absence_is_not_silently_skipped(tmp_path):
    supply = tmp_path / "supply"
    supply.mkdir()
    receipt = tmp_path / "receipt"
    result = launch(supply, receipt)
    assert result.returncode == 2, result.stderr
    report = json.loads((receipt / "qualification.json").read_text())
    assert report["status"] == "MISSING_SUPPLY"
    assert not (receipt / "pytest-output.txt").exists()


def test_wrong_donor_pin_refuses_before_launch(tmp_path):
    supply = tmp_path / "supply"
    supply.mkdir()
    (supply / "supply-manifest.json").write_text(json.dumps({
        "donor": "not-the-frozen-donor",
        "profile_head": "4159c403cf63bac8bd18138fa232911589afe06f",
        "r4_patch": "243ec445db513db3bb9ff0cad05bc70550df972a785b8af1546d89c055cadc1f",
        "profile_artifact": "c77814901495ebb3131d28b4968bd3f1cce3f39233e1c0cb580de5a7b9f9106c",
    }))
    receipt = tmp_path / "receipt"
    result = launch(supply, receipt)
    assert result.returncode == 2, result.stderr
    report = json.loads((receipt / "qualification.json").read_text())
    assert report["status"] == "PIN_MISMATCH"
    assert not (receipt / "tests.xml").exists()


def test_existing_receipt_cannot_be_rewritten(tmp_path):
    supply = tmp_path / "missing"
    receipt = tmp_path / "receipt"
    assert launch(supply, receipt).returncode == 2
    before = hashlib.sha256((receipt / "qualification.json").read_bytes()).digest()
    repeated = launch(supply, receipt)
    assert repeated.returncode == 2
    assert "EXISTING_EVIDENCE" in repeated.stderr
    assert hashlib.sha256((receipt / "qualification.json").read_bytes()).digest() == before


def test_evidence_inside_source_tree_refused(tmp_path):
    # No Git/source pollution, even when the supply is missing.
    receipt = ROOT / ".dsh-qualification-invalid-output"
    assert not receipt.exists()
    response = launch(tmp_path / "missing", receipt)
    assert response.returncode == 2
    assert "INVALID_EVIDENCE" in response.stderr
    assert not receipt.exists()


def test_zero_exit_with_all_skipped_cases_is_not_acceptance(tmp_path, monkeypatch):
    import argparse
    import importlib.util
    from types import SimpleNamespace
    import xml.etree.ElementTree as ET

    spec = importlib.util.spec_from_file_location("dsh_governed_qualifier", QUALIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    supply = tmp_path / "supply"
    supply.mkdir()
    (supply / "supply-manifest.json").write_text("{}")
    monkeypatch.setattr(module, "verify_supply", lambda _path: {
        "donor": module.EXPECTED_DONOR,
        "profile_artifact": module.EXPECTED_PROFILE_SHA,
    })

    def false_green(argv, **_kwargs):
        index = argv.index("--junitxml")
        report = Path(argv[index + 1])
        ET.ElementTree(ET.Element("testsuite", {
            "tests": "11", "failures": "0", "errors": "0", "skipped": "11",
        })).write(report)
        return SimpleNamespace(returncode=0, stdout="11 skipped", stderr="")

    monkeypatch.setattr(module.subprocess, "run", false_green)
    destination = tmp_path / "receipt"
    code = module.qualify(argparse.Namespace(supply=str(supply), evidence_dir=str(destination)))
    assert code == 2
    proof = json.loads((destination / "qualification.json").read_text())
    assert proof["status"] == "NOT_QUALIFIED"
    assert proof["junit"]["skipped"] == 11
    assert proof["provider_calls"] == 0

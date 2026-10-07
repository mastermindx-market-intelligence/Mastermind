#!/usr/bin/env python3
"""Verify this static I3 development evidence capsule; never write or promote it.

No owner/provider/network/runtime calls occur here. Success checks this capsule's
integrity and scope, not I3 reconstruction/classification/utility/production gates.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MACRO_PIN = "37122b69fffa98cb160022c4831df0338ef3e7e3"
GOLDEN_DELIVERY = {"kind": "committed_golden_fixture", "attested": False, "production_issuer_service": False}
REFUSAL = "unlinked source vintages require an explicit typed revision lineage"
CASE_HASHES = {
    "aapl_same_filing_annual_revenue": "a752302d0d11457920be1425cb9ebb6d1f29560b7f1e8f41a5de98075083c6af",
    "aapl_unlinked_assets": "aa6f82dc415e2d3449118c627deb339f98814f0a1be6dff61e88f8819495bb21",
}

class EvidenceError(ValueError):
    pass

def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)

def load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"cannot read evidence {path.name}: {type(exc).__name__}") from exc

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifest = load(root / "PACKAGE_MANIFEST.json")
    require(manifest["kind"] == "static_review_candidate_not_runtime_registry", "wrong manifest purpose")
    listed = manifest["files"]
    actual = {f.relative_to(root).as_posix() for f in root.rglob("*") if f.is_file() and f.name != "PACKAGE_MANIFEST.json" and "__pycache__" not in f.parts}
    require(actual == set(listed), "manifest file set differs")
    for name, wanted in listed.items():
        path = root / name
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "unsafe evidence path")
        require(not path.is_symlink(), "symlink evidence not allowed")
        require(sha(path) == wanted["sha256"] and path.stat().st_size == wanted["bytes"], f"byte mismatch: {name}")
    ev = root / "evidence"
    cap = load(ev / "CAPTURE_BOUNDARY.json")
    require(cap["source_pin"] == MACRO_PIN, "wrong source pin")
    require(cap["development_exposed"] is True and cap["heldout"] is False, "development exposure lost")
    for key in ("trial_registered", "runtime_exposure_writer_bound", "production_emitted", "classification_graded", "utility_graded", "prediction_graded", "rights_promotion"):
        require(cap[key] is False, f"unearned capability: {key}")
    method_path = ev / "method-before-execution.json"
    method = load(method_path)
    require(sha(method_path) == cap["method_before_execution_sha256"], "method hash mismatch")
    require(method["source_commit"] == MACRO_PIN, "method source drift")
    require(method["heldout"] is False and method["trial_registered"] is False and method["production_emission"] is False, "method scope widened")
    require(set(method["requests"]) == set(CASE_HASHES), "unrecorded query case")
    reports: dict[str, Any] = {}
    for case, expected in CASE_HASHES.items():
        response_path = ev / f"{case}.response.json"
        response = load(response_path)
        receipt = load(ev / f"{case}.receipt.json")
        require(sha(response_path) == expected == receipt["response_sha256"] == receipt["actual_sha256"], f"owner response identity drift: {case}")
        require(receipt["method_sha256"] == cap["method_before_execution_sha256"], "receipt method drift")
        require(receipt["I3_emission_at"] is None and receipt["historical_emission_at"] is None, "fabricated emission")
        require(receipt["trial_registered"] is False and receipt["development_only"] is True, "receipt maturity widened")
        require(response["delivery"] == GOLDEN_DELIVERY, "golden delivery promoted")
        require(response["authority"] == {"class": "context_only", "display_only": True}, "owner authority altered")
        roots = set(response["receipt"]["root_cell_ids"])
        cells = [n for n in response["receipt"]["nodes"] if n["cell_id"] in roots]
        require(cells == receipt["root_cells"], "receipt differs from original owner cells")
        reports[case] = {"response_sha256": expected, "root_cell_ids": [n["cell_id"] for n in cells]}
        if case == "aapl_same_filing_annual_revenue":
            require(len(cells) == 2 and all(n["state"] == "value" for n in cells), "positive input pair missing")
            require([n["value"] for n in cells] == ["391035000000", "416161000000"], "pinned source values changed")
            require(all(n["provenance"]["selected_raw_fact"]["source"]["accession"] == "0000320193-25-000079" for n in cells), "not one source filing")
            require(all(n["period"]["calendar_kind"] == "unknown" for n in cells), "unknown fiscal metadata fabricated")
        else:
            require(len(cells) == 1 and cells[0]["state"] == "not_evaluable", "unlinked refusal erased")
            require(cells[0]["reason"] == REFUSAL and cells[0]["value"] is None, "unlinked refusal altered")
    attempts = [load(ev / f"pytest-attempt-{i}.json") for i in (1, 2, 3, 4)]
    require([a["exit_code"] for a in attempts] == [1, 1, 1, 0], "setup/result history changed")
    require(attempts[-1]["observed_result"] == "4 PASSED, 1 deprecation warning, 9.88s", "test result drift")
    require(all(a["i3_acceptance"] is False and a["production_proof"] is False for a in attempts), "component pass promoted")
    delta = load(ev / "targeted-source-delta.json")
    require(delta["current_pin"] == MACRO_PIN and len(delta["files"]) == 10, "dependency scope drift")
    require(all(x["snapshot_matches_current"] for x in delta["files"]), "snapshot source mismatch")
    changed = [x["path"] for x in delta["files"] if not x["unchanged_from_audit"]]
    require(changed == ["engine/company_intelligence/event_workspace.py"], "targeted delta changed")
    comparator = load(root / "COMPARATOR_DEFINITION_CANDIDATE.json")
    require(comparator["admitted"] is False, "candidate self-admitted")
    return {"capsule_integrity": "PASS", "owner_input_tests": "4 passed after three preserved setup failures", "cases": reports, "targeted_changed_dependencies": changed, "i3_acceptance": False, "production_proof": False, "independent_review": "separate_required_receipt"}

if __name__ == "__main__":
    try:
        print(json.dumps(verify(), indent=2))
    except (EvidenceError, KeyError, TypeError) as exc:
        raise SystemExit(f"EVIDENCE_INVALID: {exc}") from exc

#!/usr/bin/env python3
"""Run the fixed AAPL baseline experiment as development evidence, not a trial.

Uses only the pre-existing isolated, pinned FIF source snapshot. No download,
Git checkout, source repair, service write, publisher, registry or model is used.
Each output directory is new; previous inputs/results are never overwritten.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import site
import subprocess
import sys

from baseline_replay import SOURCE_PIN, ReplayRefusal, canonical, compare_snapshots, digest

ROOT = Path(__file__).resolve().parent

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def write_new(path: Path, obj: object) -> None:
    with path.open("x", encoding="utf-8") as file:
        file.write(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve(strict=True)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    original = json.loads((ROOT / "evidence/targeted-source-delta.json").read_text())
    if original["current_pin"] != SOURCE_PIN: raise ReplayRefusal("source_pin_changed")
    for row in original["files"]:
        path = source / row["path"]
        if not path.is_file() or digest(path.read_bytes()) != row["current_sha256"]:
            raise ReplayRefusal("pinned_dependency_mismatch:" + row["path"])
        checks.append({"path": row["path"], "sha256": row["current_sha256"]})
    for name in ("security-master-input.json", "issuer-master-input.json"):
        row = json.loads((ROOT / "evidence" / name).read_text())
        path = source / row["path"]
        if not path.is_file() or digest(path.read_bytes()) != row["sha256"]:
            raise ReplayRefusal("pinned_identity_input_mismatch")
        checks.append({"path": row["path"], "sha256": row["sha256"]})
    method = json.loads((ROOT / "BASELINE_REPLAY_METHOD.json").read_text())
    if method["source_commit"] != SOURCE_PIN: raise ReplayRefusal("method_source_pin")
    requests = {}
    for name, cutoffs in method["snapshots"].items():
        requests[name] = {"schema": "fundamental_forensics.financial_query_request/v1", "entity_id": "ISS:US-XNAS-AAPL", "metric_ids": method["metric_ids"], "periods": method["periods"], "policy": {"selection": "latest_known_as_of", **cutoffs}}
    metadata = {"kind": "development_fixture_method_before_execution", "source_commit": SOURCE_PIN, "recorded_at": now(), "runner_sha256": digest(Path(__file__).read_bytes()), "replay_module_sha256": digest((ROOT / "baseline_replay.py").read_bytes()), "method_file_sha256": digest((ROOT / "BASELINE_REPLAY_METHOD.json").read_bytes()), "checked_local_dependencies": checks, "requests": requests, "comparison_pairs": method["comparisons"], "development_exposed": True, "trial_registered": False, "production_emission": False, "owner_admission_changed": False}
    write_new(out / "method-before-execution.json", metadata)
    isolated_home = out / "isolated-home"; isolated_home.mkdir()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(isolated_home), "PYTHONPATH": str(source) + os.pathsep + site.getusersitepackages(), "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    child = r"""from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys
from engine.fundamental_forensics.ixbrl_raw_ledger import GoldenAaplFinancialQueryProvider
from engine.fundamental_forensics.query_service import execute_financial_query
source=Path(sys.argv[1]);out=Path(sys.argv[2]);meta=json.loads((out/'method-before-execution.json').read_text());provider=GoldenAaplFinancialQueryProvider(source);receipts=[]
for name,req in meta['requests'].items():
 started=datetime.now(timezone.utc).isoformat()
 r=execute_financial_query(body=json.dumps(req,separators=(',',':')).encode(),provider=provider)
 with (out/(name+'.response.json')).open('xb') as f:f.write(r.body)
 row={'name':name,'response_sha256':r.sha256,'bytes':len(r.body),'actual_started_at':started,'actual_completed_at':datetime.now(timezone.utc).isoformat(),'owner_coverage':r.envelope['coverage'],'query_hash':r.envelope['receipt']['query_hash'],'production_issuer_service':False}
 receipts.append(row)
 print(json.dumps(row),flush=True)
with (out/'owner-queries.json').open('x') as f:json.dump(receipts,f,indent=2)
"""
    with (out / "owner_query_driver.py").open("x") as file: file.write(child)
    write_new(out / "owner-driver-before-execution.json", {"driver_sha256": digest(child.encode()), "recorded_at": now(), "method_sha256": digest((out / "method-before-execution.json").read_bytes())})
    results = {"kind": "development_baseline_replay_result", "started_at": now(), "source_commit": SOURCE_PIN, "method_capture_sha256": digest((out / "method-before-execution.json").read_bytes()), "comparisons": [], "i3_accepted": False, "production_proof": False, "emitted_at": None}
    try:
        proc = subprocess.run([sys.executable, str(out / "owner_query_driver.py"), str(source), str(out)], cwd=source, env=env, capture_output=True, text=True, timeout=60)
        results["owner_process_exit"] = proc.returncode
        log = proc.stdout + proc.stderr
        with (out / "owner-query-output.txt").open("x") as file: file.write(log)
        results["owner_process_log_sha256"] = digest(log.encode())
        print(log[-4000:])
        if proc.returncode: raise ReplayRefusal("owner_process_failed")
        owner_receipts = {r["name"]:r for r in json.loads((out / "owner-queries.json").read_text())}
        for pair in method["comparisons"]:
            before, after = pair["before"], pair["after"]
            inputs = [(out / (name + ".response.json")).read_bytes() for name in (before, after)]
            kwargs = {"before_sha256": owner_receipts[before]["response_sha256"], "after_sha256": owner_receipts[after]["response_sha256"], "before_request": requests[before], "after_request": requests[after]}
            result = compare_snapshots(*inputs, **kwargs)
            repeated = compare_snapshots(*inputs, **kwargs)
            if canonical(result) != canonical(repeated): raise ReplayRefusal("nondeterministic_reconstruction")
            write_new(out / (pair["name"] + ".comparison.json"), result)
            row = {"name": pair["name"], "artifact_sha256": result["artifact_sha256"], "requested_variables": result["payload"]["requested_variable_count"], "counts": result["payload"]["counts"]}
            results["comparisons"].append(row)
            print(json.dumps(row), flush=True)
        results["state"] = "fixture_replay_completed_not_admitted"
        return 0
    except (ReplayRefusal, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        results.update(state="fixture_replay_failed", error_type=type(exc).__name__, error=str(exc))
        print("REPLAY_FAILED", str(exc), file=sys.stderr)
        return 1
    finally:
        results["completed_at"] = now()
        write_new(out / "result.json", results)

if __name__ == "__main__":
    raise SystemExit(main())

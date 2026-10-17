#!/usr/bin/env python3
"""Replay unchanged FIF owner inputs in a new, isolated non-git snapshot.

Run inside an admitted source workspace. This exports only the fixed accepted
Macro commit from its existing object store. It never clones/fetches/checks out,
changes owner files, invokes a runtime writer, registers trials, or deploys.
Required existing dependencies include pytest, PyYAML, pandas/pyarrow, FastAPI,
httpx, lxml and BeautifulSoup. Dependency failures are recorded, not auto-repaired.
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
import tarfile

PIN = "37122b69fffa98cb160022c4831df0338ef3e7e3"
PATHS = ["engine", "app", "collectors", "config", "lib", "tests/test_fundamental_forensics_ixbrl_raw_ledger.py", "tests/fixtures/fundamental_forensics/aapl_10k_2025", "tests/fixtures/fundamental_forensics/aapl_10q_2026q3", "data/reference/security_master.parquet", "data/reference/issuer_master.parquet"]
TESTS = ["test_required_governed_aapl_values", "test_unlinked_vintages_are_not_evaluable", "test_pit_cutoffs_hide_future_knowledge", "test_statement_query_reconciliation_for_direct_metrics"]
ROOT = Path(__file__).resolve().parent

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macro-git-dir", required=True, type=Path, help="Existing Macro common Git object store; read only")
    parser.add_argument("--output-dir", required=True, type=Path, help="New, nonexistent scratch directory inside the admitted workspace")
    args = parser.parse_args()
    git_dir = args.macro_git_dir.resolve(strict=True)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / "source"; source.mkdir()
    home = out / "isolated-home"; home.mkdir()
    archive = out / "accepted-source.tar"
    command = [sys.executable, "-m", "pytest", "-c", "/dev/null", "--noconftest", "-p", "no:cacheprovider", "-q", *[f"tests/test_fundamental_forensics_ixbrl_raw_ledger.py::{name}" for name in TESTS]]
    capture = {"kind": "development_owner_input_replay", "source_commit": PIN, "source_paths": PATHS, "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "frozen_query_method_sha256": hashlib.sha256((ROOT / "evidence/method-before-execution.json").read_bytes()).hexdigest(), "python": sys.version, "recorded_before_execution_at": now(), "test_command": command, "development_exposed": True, "heldout": False, "trial_registered": False, "production_proof": False, "i3_acceptance": False}
    (out / "method-before-execution.json").write_text(json.dumps(capture, indent=2) + "\n")
    result = {"started_at": now(), "state": "setup_started", "pytest_exit_code": None, "queries_executed": False}
    exit_code = 1
    try:
        with archive.open("xb") as stream:
            subprocess.run(["git", "--git-dir=" + str(git_dir), "archive", "--format=tar", PIN, *PATHS], stdout=stream, check=True, timeout=60)
        if archive.stat().st_size > 1024 * 1024 * 1024:
            raise ValueError("bounded source snapshot exceeds 1 GiB")
        with tarfile.open(archive) as bundle:
            bundle.extractall(source, filter="data")
        result["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "PYTHONPATH": str(source) + os.pathsep + site.getusersitepackages(), "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        tests = subprocess.run(command, cwd=source, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
        (out / "pytest.txt").write_text(tests.stdout)
        result.update(pytest_exit_code=tests.returncode, pytest_output_sha256=hashlib.sha256(tests.stdout.encode()).hexdigest(), state="owner_test_failed" if tests.returncode else "owner_tests_passed")
        print(tests.stdout)
        if tests.returncode:
            return tests.returncode
        query_code = """from pathlib import Path
import hashlib,json,sys
from engine.fundamental_forensics.ixbrl_raw_ledger import GoldenAaplFinancialQueryProvider
from engine.fundamental_forensics.query_service import execute_financial_query
source=Path(sys.argv[1]); definitions=Path(sys.argv[2]); out=Path(sys.argv[3]); provider=GoldenAaplFinancialQueryProvider(source)
method=json.loads(definitions.read_text()); receipts=[]
for name,request in method['requests'].items():
 r=execute_financial_query(body=json.dumps(request,separators=(',',':')).encode(),provider=provider)
 (out/(name+'.response.json')).write_bytes(r.body)
 expected=(definitions.parent/(name+'.response.json')).read_bytes()
 if r.body != expected: raise ValueError('owner replay differs from pinned captured case: '+name)
 receipts.append({'case':name,'response_sha256':hashlib.sha256(r.body).hexdigest(),'bytes':len(r.body)})
(out/'owner-query-replay.json').write_text(json.dumps(receipts,indent=2)+'\\n')
print(json.dumps(receipts))
"""
        (out / "query_replay.py").write_text(query_code)
        queries = subprocess.run([sys.executable, str(out / "query_replay.py"), str(source), str(ROOT / "evidence/method-before-execution.json"), str(out)], cwd=source, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
        (out / "queries.txt").write_text(queries.stdout)
        result.update(query_exit_code=queries.returncode, queries_executed=True, state="replay_passed" if queries.returncode == 0 else "query_replay_failed")
        print(queries.stdout)
        exit_code = queries.returncode
        return exit_code
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        result.update(state="setup_or_execution_failed", error_type=type(exc).__name__, error=str(exc))
        print(f"REPLAY_FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        result.update(completed_at=now(), production_proof=False, i3_acceptance=False)
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""DR-D1 clean-host disaster-recovery drill.

Fabricates a production-representative Executive RuntimeStore (same
migrations, a synthetic Jobs/Attempts/Events workload), then runs the full
Stage A-D chain: backup -> verify -> export/encrypt -> ship -> **delete the
local copies** -> fetch on the same fresh environment -> full restore
verification chain -> logical-state equality against the recorded pre-loss
state. Measures and reports RPO/RTO and writes a drill receipt.

Runs on a disposable environment (a GitHub Actions hosted runner, or a local
throwaway directory) with zero dependence on the control host's filesystem,
launchd state, or Executive service. ``--offline`` uses the local
create-only directory transport instead of GitHub releases -- this is what
CI and the test suite exercise, since it proves the identical Stage A-D
chain with zero network traffic and zero credential dependency.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.executive_backup import create_online_backup, verify_restore_drill  # noqa: E402
from control_plane.executive_dr import (  # noqa: E402
    ExecutiveDRError,
    decrypt_export,
    encrypt_export,
    fetch_export_directory,
    fetch_export_github,
    read_export_backup_manifest,
    ship_export_directory,
    ship_export_github,
)
from control_plane.executive_dr import _write_private_json  # noqa: E402
from control_plane.executive_runtime import AttemptLease, Runtime  # noqa: E402

DRILL_RECEIPT_SCHEMA_VERSION = "mastermind.executive_dr_drill_receipt/v1"
_DEFAULT_REPO_ENV = "DR_DRILL_REPO"
_DEFAULT_REPO = "mastermindx-market-intelligence/Mastermind"
_DEFAULT_TOKEN_ENV = "GITHUB_TOKEN"
_ALL_ZERO_SHA = "0" * 40


def _now_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def _source_release_commit() -> str:
    override = os.environ.get("DR_DRILL_SOURCE_COMMIT")
    if override:
        return override
    try:
        completed = subprocess.run(
            ["git", "-C", str(_ROOT), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _ALL_ZERO_SHA
    sha = completed.stdout.strip()
    if completed.returncode == 0 and len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
        return sha
    return _ALL_ZERO_SHA


def _fabricate_runtime(root: Path) -> Runtime:
    """Same migrations as production; a small synthetic workload."""

    runtime = Runtime.at(root)
    runtime.workers.register_worker(
        "dr-drill-worker-01",
        provider="codex",
        account_label="dr-drill",
        worker_type="mock",
        capabilities=["code", "research"],
    )
    runtime.workers.register_worker(
        "dr-drill-worker-02",
        provider="claude",
        account_label="dr-drill",
        worker_type="mock",
        capabilities=["research"],
    )
    job_ids = []
    for index in range(5):
        job = runtime.jobs.create_job(
            f"dr-drill synthetic objective {index}",
            department="dr-drill",
            priority=index,
        )
        job_ids.append(job.job_id)
    # Claim and complete a couple of them so the workload is representative
    # (mixed QUEUED / RUNNING / COMPLETED status, non-empty Attempts+Events).
    lease = runtime.attempts.claim_job(job_ids[0], worker_id="dr-drill-worker-01")
    if not isinstance(lease, AttemptLease):
        raise ExecutiveDRError("dr-drill fixture: claim_job did not return a plain AttemptLease for job 0")
    runtime.attempts.complete_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        payload={"summary": "dr-drill synthetic completion"},
    )
    lease2 = runtime.attempts.claim_job(job_ids[1], worker_id="dr-drill-worker-02")
    if not isinstance(lease2, AttemptLease):
        raise ExecutiveDRError("dr-drill fixture: claim_job did not return a plain AttemptLease for job 1")
    return runtime


def _logical_state_from_connection(connection: sqlite3.Connection) -> dict[str, Any]:
    workers = [str(row[0]) for row in connection.execute("SELECT worker_id FROM workers ORDER BY 1")]
    jobs = [
        [str(row[0]), str(row[1]), str(row[2])]
        for row in connection.execute("SELECT job_id, objective, status FROM jobs ORDER BY 1")
    ]
    attempts = [
        [str(row[0]), str(row[1]), str(row[2])]
        for row in connection.execute("SELECT attempt_id, job_id, status FROM attempts ORDER BY 1")
    ]
    events = [
        [int(row[0]), str(row[1]), str(row[2])]
        for row in connection.execute("SELECT event_id, event_type, aggregate_id FROM events ORDER BY 1")
    ]
    return {"workers": workers, "jobs": jobs, "attempts": attempts, "events": events}


def _logical_state(runtime: Runtime) -> dict[str, Any]:
    with runtime.store.read() as connection:
        return _logical_state_from_connection(connection)


def _logical_state_from_sqlite_file(path: Path) -> dict[str, Any]:
    """Read-only, immutable-URI open -- mirrors executive_backup._readonly_database.

    Deliberately bypasses ``RuntimeStore``/``Runtime.at`` here: those
    constructors are for the ONE canonical live database and its writers,
    with mkdir/chmod/migration side effects that do not belong on a restored
    drill copy we only need to read back for comparison. The restored file
    was already fully verified (schema, integrity, digests) by
    ``verify_restore_drill`` before this is called.
    """

    encoded = quote(str(path), safe="/")
    connection = sqlite3.connect(f"file:{encoded}?mode=ro&immutable=1", uri=True, isolation_level=None, timeout=5.0)
    try:
        connection.execute("PRAGMA query_only=ON")
        return _logical_state_from_connection(connection)
    finally:
        connection.close()


class DrillFailed(ExecutiveDRError):
    """Carries a PARTIAL receipt (stage reached, typed state, timings so
    far) so a failed drill still produces evidence (adversarial review M8)."""

    def __init__(self, receipt: dict[str, Any]) -> None:
        super().__init__(str(receipt.get("error_message") or "drill failed"))
        self.receipt = receipt


def run_drill(*, work_root: Path, offline: bool, repo: str, token_env: str, api_base: str) -> dict[str, Any]:
    """Run the full Stage A-D chain.

    On success returns the receipt dict directly. On ANY failure -- at any
    stage -- raises `DrillFailed` carrying a partial receipt (stage reached,
    typed error state, every timing captured before the failure); it never
    raises a bare, evidence-free exception (adversarial review M8).
    """

    stage_timings_ms: dict[str, int] = {}
    started_ms = _now_ms()
    current_stage = "fabricate"
    pre_loss_state: dict[str, Any] | None = None

    try:
        stage_start = _now_ms()
        runtime_root = work_root / "fabricated-runtime"
        runtime = _fabricate_runtime(runtime_root)
        pre_loss_state = _logical_state(runtime)
        stage_timings_ms["fabricate"] = _now_ms() - stage_start

        current_stage = "backup"
        stage_start = _now_ms()
        backup_dir = work_root / "backups"
        backup_receipt = create_online_backup(runtime.store, backup_dir)
        stage_timings_ms["backup"] = _now_ms() - stage_start

        current_stage = "encrypt"
        stage_start = _now_ms()
        master_key = base64.b64encode(os.urandom(32)).decode("ascii")
        staging_dir = work_root / "staging"
        source_release_commit = _source_release_commit()
        export_receipt = encrypt_export(
            backup_receipt.database_path,
            backup_receipt.manifest_path,
            master_key,
            staging_dir,
            transport_target="directory" if offline else "github-release",
            retention_class="drill",
            source_release_commit=source_release_commit,
        )
        stage_timings_ms["encrypt"] = _now_ms() - stage_start

        current_stage = "ship"
        stage_start = _now_ms()
        vault_dir = work_root / "vault"
        if offline:
            ship_receipt = ship_export_directory(export_receipt.ciphertext_path, export_receipt.envelope_path, directory=vault_dir)
        else:
            # Adversarial review M10: the drill lane ALWAYS ships draft
            # releases -- no git tag/ref is created for a draft until a
            # human publishes it, so routine (weekly + on-demand) drills
            # never accumulate permanent, undecryptable-elsewhere tags on
            # the product repo. The production/vault lane (the nightly
            # backup daemon via executive_dr_cli.py, which defaults
            # `draft=False`) is entirely separate and never pruned.
            ship_receipt = ship_export_github(
                export_receipt.ciphertext_path, export_receipt.envelope_path,
                repo=repo, token_env=token_env, api_base=api_base, draft=True,
            )
        stage_timings_ms["ship"] = _now_ms() - stage_start

        # Discard every local copy -- the fetch below proves the off-host
        # object, not a filesystem cache of it.
        current_stage = "discard_local"
        stage_start = _now_ms()
        for local_path in (backup_receipt.database_path, backup_receipt.manifest_path, export_receipt.ciphertext_path, export_receipt.envelope_path):
            try:
                os.unlink(local_path)
            except FileNotFoundError:
                pass
        stage_timings_ms["discard_local"] = _now_ms() - stage_start

        # fetch_to_verified_ms measures ONLY this drill's own automated
        # fetch->decrypt->verify component (adversarial review M7) -- it is
        # NOT the packet's RTO target, which additionally includes host
        # provisioning and is measured by the full ceremony drill in
        # DR_RUNBOOK.md, not by this script alone.
        fetch_to_verified_start_ms = _now_ms()

        current_stage = "fetch"
        stage_start = _now_ms()
        fetched_dir = work_root / "fetched"
        if offline:
            fetch_receipt = fetch_export_directory(ship_receipt.tag, directory=vault_dir, dest_dir=fetched_dir)
        else:
            fetch_receipt = fetch_export_github(ship_receipt.tag, repo=repo, dest_dir=fetched_dir, token_env=token_env, api_base=api_base)
        stage_timings_ms["fetch"] = _now_ms() - stage_start

        current_stage = "decrypt"
        stage_start = _now_ms()
        manifest = read_export_backup_manifest(fetch_receipt.envelope_path)
        database_filename = manifest["database"]["filename"]
        restored_dir = work_root / "restored"
        restored_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        restored_path = restored_dir / database_filename
        decrypt_receipt = decrypt_export(fetch_receipt.ciphertext_path, fetch_receipt.envelope_path, master_key, restored_path)
        manifest_path = restored_path.with_suffix(".manifest.json")
        _write_private_json(manifest_path, manifest)
        stage_timings_ms["decrypt"] = _now_ms() - stage_start

        current_stage = "verify"
        stage_start = _now_ms()
        restore_drill_receipt = verify_restore_drill(restored_path, manifest_path)
        post_restore_state = _logical_state_from_sqlite_file(restored_path)
        logical_state_equal = post_restore_state == pre_loss_state
        stage_timings_ms["verify"] = _now_ms() - stage_start
        if not logical_state_equal:
            raise ExecutiveDRError(
                "restored logical state (workers/jobs/attempts/events) differs from the pre-loss state"
            )

        fetch_to_verified_ms = _now_ms() - fetch_to_verified_start_ms
        total_ms = _now_ms() - started_ms

        return {
            "schema_version": DRILL_RECEIPT_SCHEMA_VERSION,
            "ok": True,
            "offline": offline,
            "export_id": export_receipt.export_id,
            "tag": ship_receipt.tag,
            "transport": ship_receipt.transport,
            "backup_id": backup_receipt.backup_id,
            "source_release_commit": source_release_commit,
            "restored_database_path": str(restored_path),
            "restore_drill": restore_drill_receipt.to_dict(),
            "ciphertext_byte_size": export_receipt.byte_size,
            "stage_timings_ms": stage_timings_ms,
            "fetch_to_verified_ms": fetch_to_verified_ms,
            "total_ms": total_ms,
            "logical_state_equal": logical_state_equal,
            "pre_loss_state": pre_loss_state,
            "post_restore_state": post_restore_state,
        }
    except Exception as exc:
        total_ms = _now_ms() - started_ms
        state = getattr(exc, "state", None)
        failure_receipt = {
            "schema_version": DRILL_RECEIPT_SCHEMA_VERSION,
            "ok": False,
            "offline": offline,
            "failed_stage": current_stage,
            "error_state": state.value if state is not None else "UNKNOWN",
            "error_message": str(exc),
            "stage_timings_ms": stage_timings_ms,
            "total_ms": total_ms,
            "pre_loss_state": pre_loss_state,
        }
        raise DrillFailed(failure_receipt) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DR-D1 clean-host disaster-recovery drill.")
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Root working directory (default: a fresh temp directory, removed only on request).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the local create-only directory transport instead of GitHub releases (no network, no credentials).",
    )
    parser.add_argument("--repo", default=os.environ.get(_DEFAULT_REPO_ENV, _DEFAULT_REPO))
    parser.add_argument("--token-env", default=_DEFAULT_TOKEN_ENV)
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--receipt-out", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    owns_work_dir = args.work_dir is None
    if args.work_dir is not None:
        work_root = Path(args.work_dir).expanduser()
        work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        work_root.chmod(0o700)
    else:
        import tempfile

        work_root = Path(tempfile.mkdtemp(prefix="mastermind-dr-drill-"))

    ok = True
    try:
        receipt = run_drill(
            work_root=work_root,
            offline=args.offline,
            repo=args.repo,
            token_env=args.token_env,
            api_base=args.api_base,
        )
    except DrillFailed as exc:
        receipt = exc.receipt
        ok = False
    except ExecutiveDRError as exc:
        # Should not normally happen -- run_drill wraps every failure into
        # DrillFailed -- but never let a truly unexpected typed error escape
        # without at least SOME receipt (adversarial review M8).
        receipt = {
            "schema_version": DRILL_RECEIPT_SCHEMA_VERSION,
            "ok": False,
            "offline": args.offline,
            "failed_stage": "unknown",
            "error_state": getattr(exc, "state", None).value if getattr(exc, "state", None) is not None else "UNKNOWN",
            "error_message": str(exc),
            "stage_timings_ms": {},
            "total_ms": 0,
            "pre_loss_state": None,
        }
        ok = False

    payload = json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    sys.stdout.write(payload)
    if args.receipt_out is not None:
        args.receipt_out.write_text(payload, encoding="utf-8")

    if ok:
        if owns_work_dir:
            import shutil

            shutil.rmtree(work_root, ignore_errors=True)
        summary = (
            f"DR-D1 drill OK: export={receipt['export_id']} transport={receipt['transport']} "
            f"fetch_to_verified_ms={receipt['fetch_to_verified_ms']} logical_state_equal={receipt['logical_state_equal']}"
        )
        sys.stdout.write(summary + "\n")
        return 0

    # Adversarial review M8: never rm -rf the work directory on failure --
    # it is the evidence an operator needs to investigate, and CI's
    # upload-artifact step only reaches the receipt, not this directory.
    sys.stderr.write(f"DR-D1 drill FAILED at stage {receipt.get('failed_stage')}: {receipt.get('error_message')}\n")
    sys.stderr.write(f"work directory retained for investigation: {work_root}\n")
    return 65


if __name__ == "__main__":
    raise SystemExit(main())

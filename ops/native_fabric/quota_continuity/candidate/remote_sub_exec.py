#!/usr/bin/env python3
"""Run one remote sub.sh task under the existing physical LaneLease.

This is not a scheduler. The Studio-side remote_sub.sh remains the placement and
provider-lease owner; this helper only closes the host-admission race between
telemetry selection and process start.
"""
from __future__ import annotations

import json
import hashlib
from contextlib import ExitStack
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
import native_remote
import time

from lane_runtime import (
    LaneAdmissionRefused,
    LaneLease,
    LaneRuntimeConfigError,
    LaneRuntimeError,
    OwnedProcessStartError,
    cleanup_receipt_is_proven,
    install_signal_cleanup,
    load_runtime_config,
    parse_bounded_seconds,
    run_owned_process,
)


def _fail(message: str, code: int) -> int:
    print(message, file=sys.stderr, flush=True)
    return code


def grok_plaintext_and_usage(raw: str, run_id: str, model: str):
    """Normalize one Grok headless JSON response using observed usage only.

    Legacy inert/older plain responders keep the exact plaintext result with
    unknown usage. Malformed structured results expose no JSON thought fields.
    """
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        # Non-JSON legacy plaintext is okay. A malformed structured payload
        # must not expose possible private reasoning on an error path.
        return ("", None) if raw.lstrip().startswith(("{", "[")) else (raw, None)
    if not isinstance(parsed, dict):
        return "", None
    text = parsed.get("text")
    if not isinstance(text, str):
        return "", None
    usage = parsed.get("usage")
    sid = parsed.get("sessionId")
    if not isinstance(usage, dict) or not isinstance(sid, str) or not 0 < len(sid) <= 256:
        return text, None
    names = ("input_tokens", "cache_read_input_tokens", "output_tokens", "total_tokens")
    if not all(type(usage.get(k)) is int and 0 <= usage[k] <= 2**53 for k in names):
        return text, None
    extra = usage.get("cache_creation_input_tokens", 0)
    if type(extra) is not int or not 0 <= extra <= 2**53:
        return text, None
    noncached, cached, output, observed_total = (usage[k] for k in names)
    full_input = noncached + cached + extra
    if full_input > 2**53 or full_input + output != observed_total:
        return text, None
    return text, {
        "schema": "mastermind.grok_usage.v1",
        "status": "observed",
        "reason": "native_headless_final",
        "session_ids": [sid],
        "input_tokens": full_input,
        "cached_tokens": cached,
        "output_tokens": output,
        "total_tokens": observed_total,
        "source": "grok_native_headless",
        "served_model": model,
        "run_id": run_id,
    }



def grok_output_binding(receipt, contract, manifest, raw_stdout, display_stdout, env):
    """Original producer binds normalized output; never backfills an old run."""
    import artifact_production
    if grok_plaintext_and_usage(raw_stdout, contract['run_id'], 'grok-4.6')[0] != display_stdout:
        raise ValueError('grok_output_transform_mismatch')
    row = json.loads(Path(receipt).read_text().splitlines()[-1])
    raw = raw_stdout.encode('utf-8');normalized = display_stdout.encode('utf-8')
    if (row.get('schema') != 'mastermind.local_owned_process_receipt.v1'
            or row.get('label') != contract['run_id']
            or row.get('returncode') != 0 or row.get('timed_out') is not False
            or row.get('stdout_truncated') is not False or row.get('stderr_truncated') is not False
            or not cleanup_receipt_is_proven(row.get('cleanup') or {})
            or row.get('stdout_bytes') != len(raw)
            or row.get('stdout_sha256') != hashlib.sha256(raw).hexdigest()):
        raise ValueError('grok_output_capture_unqualified')
    scope = {k:env.get(v,'') for k,v in {'root':'POOL_ORCHESTRATOR_ID',
        'parent':'POOL_PARENT_RUN_ID','run_id':'REMOTE_SUB_RUN_ID','host':'LANE_REMOTE_HOST',
        'lease_id':'POOL_LEASE_ID','account':'POOL_ACCOUNT','support_digest':'SUPPORT_DIGEST'}.items()}
    if any(scope[k] != contract[k] for k in ('root','parent','run_id','support_digest')):
        raise ValueError('grok_output_scope')
    if not all(native_remote.IDENT.fullmatch(scope[k]) for k in ('root','parent','run_id','host','lease_id','account')):
        raise ValueError('grok_output_scope')
    return dict(schema='mastermind.grok_normalized_output.v1', algorithm='grok_plaintext_and_usage_v1',
        **scope, mode='grok', model='grok-4.6', raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),
        normalized_bytes=len(normalized),normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        contract=contract,manifest=manifest)


# The exact reviewed Macro sparse-owner blob from draft #9194. This is a
# deployment fence, not permission to install that draft into an old host.
# Any source revision requires new review/test and an explicit hash update.
_MACRO_FABRIC_SPARSE_BLOB = "75297acb10d0cef4d01730a59fdcad19c7cfd3e6"


class SparseWorkspaceRefused(ValueError):
    def __init__(self, reason: str, *, effect_unknown: bool = False):
        super().__init__(reason)
        self.effect_unknown = effect_unknown


def _new_macro_workspace(key: str, cwd: str, here: Path, env: dict,
                         config) -> str:
    """Optional pre-mint within the incumbent LaneLease, before worker START.

    No parallel worker/queue/authority is created. A failed or uncertain mint
    leaves its original lease and worktree for original-carrier reconciliation.
    """
    commit = os.environ.get("FABRIC_NEW_MACRO_COMMIT", "")
    if not commit:
        return cwd
    if (re.fullmatch(r"[0-9a-f]{40}", commit) is None
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", key) is None
            or os.environ.get("REMOTE_SUB_RUN_ID") != key
            or not os.environ.get("POOL_ORCHESTRATOR_ID")
            or not os.environ.get("POOL_PARENT_RUN_ID")
            or not os.environ.get("POOL_LEASE_ID")):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_SCOPE_REFUSED")
    donor = Path.home() / "lanes" / "repos" / "macro"
    try:
        if Path(cwd).resolve(strict=True) != donor.resolve(strict=True):
            raise SparseWorkspaceRefused("FABRIC_SPARSE_DONOR_REFUSED")
    except (OSError, RuntimeError) as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_DONOR_UNAVAILABLE") from exc
    helper = donor / "scripts" / "worktree_sparse.py"
    try:
        info = helper.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_size > 131072 or helper.is_symlink()):
            raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_UNQUALIFIED")
        content = helper.read_bytes()
    except OSError as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_UNAVAILABLE") from exc
    # Detect concurrent modification of the shared source between the
    # verified read and the controlled child start. Git blob proof binds
    # reviewed code; inode/stat is the ordinary shared-file drift guard.
    try:
        after_read = helper.lstat()
    except OSError as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_CHANGED") from exc
    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
        after_read.st_dev, after_read.st_ino, after_read.st_size, after_read.st_mtime_ns
    ):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_CHANGED")
    git_blob = hashlib.sha1(
        b"blob " + str(len(content)).encode() + b"\0" + content
    ).hexdigest()
    if git_blob != _MACRO_FABRIC_SPARSE_BLOB:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_BLOB_MISMATCH")
    destination = Path.home() / "lanes" / "wt" / key
    if os.path.lexists(destination):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_DESTINATION_EXISTS")
    receipt = here / "lanes" / (key + ".workspace-mint.process.jsonl")
    if os.path.lexists(receipt):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_MINT_RECEIPT_EXISTS")
    # Only the invocation of the approved Macro owner receives the one-shot
    # flag. Do not leak it into the subsequent model's shell environment.
    mint_env = dict(env)
    mint_env["MASTERMIND_FABRIC_SPARSE_NEW"] = "1"
    try:
        result = run_owned_process(
            [sys.executable, str(helper), "fabric-mint", key, commit],
            cwd=str(donor), timeout=180.0, env=mint_env, nice=config.nice,
            label=key + ":workspace-mint", receipt_path=receipt,
            timeout_returncode=124,
        )
    except (OSError, ValueError, LaneRuntimeError, OwnedProcessStartError) as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_MINT_EFFECT_UNKNOWN",
                                     effect_unknown=True) from exc
    if (result.returncode != 0 or result.timed_out
            or not result.cleanup_proven or result.stdout_truncated
            or result.stderr_truncated):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_MINT_UNVERIFIED",
                                     effect_unknown=True)
    try:
        after_mint = helper.lstat()
        current_helper = helper.read_bytes()
    except OSError as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_EFFECT_UNKNOWN",
                                     effect_unknown=True) from exc
    if ((after_mint.st_dev, after_mint.st_ino, after_mint.st_size,
         after_mint.st_mtime_ns) !=
        (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        or current_helper != content):
        raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_EFFECT_UNKNOWN",
                                     effect_unknown=True)

    def git_value(root: Path, *args: str) -> str:
        try:
            p = subprocess.run(
                ["git", "--no-optional-locks", "-C", str(root), *args],
                capture_output=True, text=True, timeout=9, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SparseWorkspaceRefused(
                "FABRIC_SPARSE_VERIFY_UNKNOWN", effect_unknown=True
            ) from exc
        if p.returncode or len(p.stdout) > 8192:
            raise SparseWorkspaceRefused("FABRIC_SPARSE_VERIFY_REFUSED",
                                         effect_unknown=True)
        return p.stdout.strip()

    try:
        dstat = destination.lstat()
        gstat = (destination / ".git").lstat()
        donor_git = (donor / ".git").resolve(strict=True)
        gitdir = Path(git_value(destination, "rev-parse", "--path-format=absolute",
                                "--git-dir")).resolve(strict=True)
        if (not stat.S_ISDIR(dstat.st_mode) or destination.is_symlink()
                or dstat.st_uid != os.getuid()
                or not stat.S_ISREG(gstat.st_mode)
                or (destination / ".git").is_symlink()
                or gitdir.parent != donor_git / "worktrees"
                or git_value(destination, "rev-parse", "HEAD") != commit
                or git_value(destination, "branch", "--show-current") != "lane/" + key
                or git_value(destination, "config", "--get", "core.sparseCheckout") != "true"
                or git_value(destination, "status", "--porcelain=v1", "-uall")):
            raise SparseWorkspaceRefused("FABRIC_SPARSE_POSTCONDITION_REFUSED",
                                         effect_unknown=True)
    except OSError as exc:
        raise SparseWorkspaceRefused("FABRIC_SPARSE_POSTCONDITION_UNKNOWN",
                                     effect_unknown=True) from exc
    return str(destination)


def _execute(argv: list[str], state: dict) -> int:
    if len(argv) != 6:
        return _fail(
            "usage: remote_sub_exec.py <key> <mode> <packet> <cwd> <model>", 2
        )
    _, key, mode, packet, cwd, model = argv
    here = Path(__file__).resolve().parent
    packet_path = Path(packet)
    if not packet_path.is_file():
        return _fail("REMOTE_SUB_PACKET_MISSING", 2)
    try:
        prompt = packet_path.read_text(encoding="utf-8")
    except OSError:
        return _fail("REMOTE_SUB_PACKET_UNREADABLE", 2)

    artifact_contract = None
    if prompt.startswith("FABRIC_ARTIFACT_REQUEST_V1 "):
        try:
            import artifact_production
            artifact_contract = artifact_production.parse_packet(prompt)
            artifact_production.bind(artifact_contract, key, mode, os.environ, here)
        except (ImportError, ValueError, TypeError, KeyError, RecursionError):
            return _fail("ARTIFACT_DELIVERY_CONTRACT_REFUSED", 65)
    artifact_failure = False

    # Tilde belongs to this host, not to the controller that selected it.
    if cwd.startswith("~") and cwd != "~" and not cwd.startswith("~/"):
        return _fail("REMOTE_SUB_CWD_REFUSED", 2)
    try:
        cwd = str(Path(cwd).expanduser())
        if not Path(cwd).is_dir():
            return _fail("REMOTE_SUB_CWD_MISSING", 2)
    except (OSError, RuntimeError):
        return _fail("REMOTE_SUB_CWD_UNREADABLE", 2)

    if mode in native_remote.MODES:
        try:
            native_remote.scope(key, mode, model, here, os.environ, timing=state.get("timing"))
        except (ValueError, OSError) as exc:
            return _fail(str(exc), 78)

    try:
        timeout = parse_bounded_seconds(
            os.environ.get("REMOTE_SUB_CHILD_TIMEOUT"),
            default=7000.0,
            minimum=0.05,
            maximum=7200.0,
            key="REMOTE_SUB_CHILD_TIMEOUT",
        )
    except LaneRuntimeConfigError as exc:
        return _fail("REMOTE_SUB_PREFLIGHT_REFUSED " + str(exc), 78)

    config = load_runtime_config(os.environ, cpu_count=os.cpu_count() or 1)
    install_signal_cleanup()
    active_dir = here / "active"
    try:
        lease = LaneLease.acquire(
            active_dir,
            key=key,
            label=key,
            env=os.environ,
            reconcile_unreleased=True,
        )
    except LaneAdmissionRefused as exc:
        payload = json.dumps(
            exc.snapshot.public_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        return _fail("REMOTE_SUB_ADMISSION_REFUSED " + payload, 75)
    except LaneRuntimeError as exc:
        return _fail("REMOTE_SUB_ADMISSION_ERROR " + type(exc).__name__, 78)

    # Prompt bytes must not consume the operating system's per-argument limit.
    # The already-delivered file stays inside the existing per-run transport.
    if mode in ("glm", "minimax", "qwen"):
        command = ["bash", str(here / "sub.sh"), "--prompt-file", mode, str(packet_path.resolve()), cwd]
    else:
        command = ["bash", str(here / "sub.sh"), mode, prompt, cwd]
    if model:
        command.append(model)
    if mode in native_remote.MODES:
        command = native_remote.command(mode, model, prompt, cwd, packet_path=packet_path.resolve())
    lanes_dir = here / "lanes"
    child_env = dict(os.environ)
    child_env.pop('FABRIC_OPERATOR_CAPABILITY', None)
    if child_env.get('FABRIC_OPERATOR_CAPSULE'):
        from fabric_operator_client import load_operator_environment
        try:
            child_env = load_operator_environment(child_env, key, mode, model, packet_path.read_bytes())
        except (OSError, ValueError, TypeError):
            lease.release()
            return _fail("OPERATOR_CAPSULE_REFUSED", 78)
    child_env["POOL_USAGE_FILE"] = str(lanes_dir / f"{key}.usage.json")
    child_env["POOL_USAGE_RUN_ID"] = key
    child_env["POOL_OUTCOME_FILE"] = str(lanes_dir / f"{key}.provider.json")
    if mode in native_remote.MODES:
        timeout = min(timeout, float(os.environ["NATIVE_LEASE_DEADLINE"])-time.time())
        if timeout <= 0:
            lease.release()
            return _fail("native_remote_lease_expired", 78)
    receipt = here / "lanes" / f"{key}.process.jsonl"
    diagnostic_reader = None
    if child_env.get('FABRIC_OPERATOR_CAPABILITY'):
        from fabric_operator_diagnostics import collect
        diagnostic_reader = lambda: collect(here, key)
    try:
        with lease, ExitStack() as artifact_stack:
            artifact_owner = (artifact_stack.enter_context(artifact_production.NewDirectory(artifact_contract))
                              if artifact_contract is not None else None)
            # Physical admission + original provider lease already succeeded.
            # Mint only this explicitly NEW, pinned workspace before worker START.
            try:
                cwd = _new_macro_workspace(key, cwd, here, child_env, config)
            except SparseWorkspaceRefused as exc:
                if exc.effect_unknown:
                    lease.hold_for_reconciliation("sparse_workspace_effect_unknown")
                return _fail(str(exc), 76 if exc.effect_unknown else 78)
            child_env.pop("MASTERMIND_FABRIC_SPARSE_NEW", None)
            child_env.pop("FABRIC_NEW_MACRO_COMMIT", None)
            if os.environ.get("FABRIC_NEW_MACRO_COMMIT"):
                child_env["FABRIC_WORKSPACE_READY"] = "1"
                child_env["FABRIC_WORKSPACE_RUN_ID"] = key
            # Do not alter any ordinary/legacy worker argv. Only a qualified
            # brand-new sparse checkout needs its CWD rebound before START.
            if os.environ.get("FABRIC_NEW_MACRO_COMMIT"):
                if mode in ("glm", "minimax", "qwen"):
                    command = ["bash", str(here / "sub.sh"), "--prompt-file", mode,
                               str(packet_path.resolve()), cwd]
                else:
                    command = ["bash", str(here / "sub.sh"), mode, prompt, cwd]
                if model:
                    command.append(model)
                if mode in native_remote.MODES:
                    command = native_remote.command(
                        mode, model, prompt, cwd, packet_path=packet_path.resolve()
                    )
            if mode in native_remote.MODES:
                child_env = native_remote.environment(mode, model, key, here, child_env)
            # Worker-spawned shell tools inherit PATH. The immutable, reviewed
            # "yes" shim bounds CPU-stealer lifetime even when an agent leaves
            # an unbounded background "taskset ... yes" shell running.
            if sys.platform.startswith("linux"):
                guard = here / "yes"
                if (not guard.is_file() or guard.is_symlink()
                        or not os.access(guard, os.X_OK)):
                    return _fail("FABRIC_CPU_STRESS_GUARD_UNAVAILABLE", 78)
                child_env["PATH"] = str(here) + os.pathsep + child_env.get("PATH", "/usr/bin:/bin")
            # Optional CPU fan-out budget is subordinate to the incumbent
            # physical LaneLease, not a replacement owner or a new worker.
            cpu_scope = None
            if child_env.get("FABRIC_CPU_SCOPE_QUOTA_PCT"):
                try:
                    import fabric_cpu_scope
                except ImportError:
                    return _fail("FABRIC_CPU_SCOPE_LIBRARY_UNAVAILABLE", 78)
                try:
                    cpu_scope = fabric_cpu_scope.prepare_scope(key, mode, command, child_env)
                except fabric_cpu_scope.CpuScopeRefused:
                    return _fail("FABRIC_CPU_SCOPE_PRESTART_REFUSED", 78)
                except fabric_cpu_scope.CpuScopeEffectUnknown:
                    lease.hold_for_reconciliation("cpu_scope_prestart_unknown")
                    return _fail("FABRIC_CPU_SCOPE_EFFECT_UNKNOWN", 76)
                if cpu_scope is not None:
                    command = list(cpu_scope.command)
                    child_env = dict(cpu_scope.env)
            install_signal_cleanup(on_unproven=lease.hold_for_reconciliation)
            try:
                state["started"] = True
                result = run_owned_process(
                    command,
                    cwd=cwd,
                    timeout=timeout,
                    env=child_env,
                    nice=config.nice,
                    label=key,
                    receipt_path=receipt,
                    timeout_returncode=124,
                    receipt_diagnostics=diagnostic_reader,
                )
            except OwnedProcessStartError as exc:
                state["started"] = False
                number = str(exc.error_number) if exc.error_number is not None else "unknown"
                return _fail("REMOTE_SUB_EXEC_NOT_STARTED errno=" + number, 78)
            finally:
                # run_owned_process owns the original process GROUP. When a
                # child calls setsid(), it can leave that group and survive
                # cleanup_proven=true. The original worker lease must not be
                # released until the exact quota cgroup also has no PIDs.
                if cpu_scope is not None and state["started"]:
                    try:
                        state["cpu_scope_settlement"] = fabric_cpu_scope.settle_scope(cpu_scope)
                    except fabric_cpu_scope.CpuScopeEffectUnknown:
                        state["cpu_scope_effect_unknown"] = True
                        lease.hold_for_reconciliation("cpu_scope_cleanup_unproven")
                    except (OSError, ValueError, TypeError):
                        state["cpu_scope_effect_unknown"] = True
                        lease.hold_for_reconciliation("cpu_scope_cleanup_unproven")
                if state["started"]:
                    proven = False
                    try:
                        row = json.loads(receipt.read_text().splitlines()[-1])
                        proven = row.get("label") == key and cleanup_receipt_is_proven(row.get("cleanup", {}))
                    except (OSError, ValueError, IndexError):
                        pass
                    if not proven:
                        lease.hold_for_reconciliation("worker_cleanup_unproven")
            if state.get("cpu_scope_effect_unknown"):
                return _fail("REMOTE_CPU_SCOPE_UNSETTLED", 76)

            display_stdout = result.stdout
            if mode == "grok":
                # Normalize even when the provider rc is nonzero. Never
                # echo structured JSON including its private thought field.
                display_stdout, usage_record = grok_plaintext_and_usage(result.stdout, key, model)
                if (usage_record is not None and result.returncode == 0
                        and result.cleanup_proven
                        and not result.stdout_truncated and not result.stderr_truncated):
                    usage_file = Path(child_env["POOL_USAGE_FILE"])
                    try:
                        fd = os.open(usage_file,
                                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                        with os.fdopen(fd, "w") as output:
                            json.dump(usage_record, output, sort_keys=True)
                            output.write("\n")
                            output.flush()
                            os.fsync(output.fileno())
                    except OSError:
                        # Metering failure is unknown usage, never invented spend
                        # and never a reason to replay a completed provider call.
                        pass
            if (artifact_contract is not None and result.returncode == 0
                    and result.cleanup_proven and not result.stdout_truncated and not result.stderr_truncated):
                try:
                    manifest = artifact_production.verify_completion(
                        artifact_contract, artifact_owner, display_stdout, child_env["LANE_REMOTE_HOST"])
                    if mode == "grok":
                        state['output_binding'] = grok_output_binding(
                            receipt, artifact_contract, manifest, result.stdout, display_stdout, child_env)
                    if mode in artifact_production.ORDINARY_MODES:
                        artifact_production.record_ordinary_completion(
                            receipt, artifact_contract, manifest, result.stdout, mode=mode)
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    artifact_failure = True

    except (LaneRuntimeError, OSError, ValueError) as exc:
        if state.get("started"):
            return _fail("REMOTE_CLEANUP_UNPROVEN " + type(exc).__name__, 76)
        return _fail("REMOTE_SUB_RUNTIME_ERROR " + type(exc).__name__, 78)

    if display_stdout:
        sys.stdout.write(display_stdout)
        sys.stdout.flush()
    # A successful worker's stderr is transport/diagnostic chatter, not its
    # return value. Keep it out of the parent result. On any worker/result/
    # cleanup failure, preserve the bounded stderr so diagnosis remains visible.
    result_failed = (
        int(result.returncode) != 0
        or not result.cleanup_proven
        or result.stdout_truncated
        or result.stderr_truncated
    )
    if result.stderr and result_failed:
        sys.stderr.write(result.stderr)
        sys.stderr.flush()
    if not result.cleanup_proven:
        return _fail("REMOTE_CLEANUP_UNPROVEN", 76)
    if result.stdout_truncated or result.stderr_truncated:
        marker = "NATIVE_CAPTURE_TRUNCATED" if mode in native_remote.MODES else "REMOTE_CAPTURE_TRUNCATED"
        return _fail(marker, 76)
    if artifact_failure:
        return _fail("ARTIFACT_DELIVERY_CONTRACT_FAILED", 65)
    return int(result.returncode)


def main(argv: list[str]) -> int:
    state = {"started": False}
    if len(argv) == 6 and argv[2] in native_remote.MODES:
        state["timing"] = {"remote_exec_entered_at": time.time()}
    is_go = len(argv) == 6 and argv[2] == "go-codex"
    rc = 78
    try:
        rc = _execute(argv, state)
        return rc
    except BaseException as exc:
        if isinstance(exc, SystemExit) and isinstance(exc.code, int):
            rc = exc.code
        raise
    finally:
        if len(argv) == 6 and argv[2] in native_remote.MODES:
            native_remote.terminal(Path(__file__).resolve().parent, argv[1], argv[2], argv[5], os.environ, state["started"], rc, timing=state.get("timing"), output_binding=state.get("output_binding"))
        if is_go:
            from lane_runtime import cleanup_receipt_is_proven
            from go_remote_capsule import IDENT
            key = argv[1]
            if not IDENT.fullmatch(key):
                raise ValueError("invalid run key")
            names = {"root":"POOL_ORCHESTRATOR_ID", "lease_id":"POOL_LEASE_ID",
                     "account":"POOL_ACCOUNT", "run_id":"REMOTE_SUB_RUN_ID",
                     "host":"LANE_REMOTE_HOST"}
            scope = {k:os.environ.get(v, "") for k,v in names.items()}
            scope["model"] = argv[5]
            if scope["run_id"] != key or not all(IDENT.fullmatch(v) for v in scope.values()):
                raise ValueError("invalid worker scope")
            folder = Path(__file__).resolve().parent / "lanes"
            folder.mkdir(exist_ok=True)
            cleanup = None
            if state["started"]:
                try:
                    rows = (folder / (key+".process.jsonl")).read_text().splitlines()
                    record = json.loads(rows[-1])
                    if record.get("schema") == "mastermind.local_owned_process_receipt.v1" and record.get("label") == key:
                        cleanup = record.get("cleanup")
                except (OSError, ValueError, IndexError):
                    pass
            value = {"schema":"mastermind.go.worker-terminal.v1", **scope,
                     "started":state["started"], "returncode":rc, "cleanup":cleanup,
                     "cleanup_proven":(not state["started"] or cleanup_receipt_is_proven(cleanup or {}))}
            fd = os.open(folder / (key+".go-terminal.json"), os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(value, output); output.write("\n"); output.flush(); os.fsync(output.fileno())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

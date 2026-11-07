"""Execute one provider-plan request inside the incumbent native slot.

Uses the original request artifacts, owned-process receipts, Broker quota
observer and ledger. It neither acquires capacity nor retries an inference.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import os
from pathlib import Path
import re
import subprocess
import sys
import time

_effect_may_have_started = False

HERE = Path(__file__).resolve().parent
POOLS = frozenset({"byteplus", "experiential"})


class PlanLeaseRefused(ValueError):
    pass


def validate_plan_lease(env, model, *, expected_pool, db_path=None, now=None):
    """Read the incumbent Broker lease; this adapter cannot grant or mutate it.

    The accepted GLM helper is embedded in a separately sealed initializer and
    remains byte-identical. New pools validate the same original lease schema
    without reinterpreting that GLM binding or accepting its remote shortcut.
    """
    if expected_pool not in POOLS or env.get("LANE_LEASED") == "1":
        raise PlanLeaseRefused("PLAN_LOCAL_PROVIDER_LEASE_REQUIRED")
    values = [env.get(key) for key in ("POOL_ACCOUNT", "POOL_LEASE_ID", "POOL_ORCHESTRATOR_ID")]
    if any(type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value)
           for value in values):
        raise PlanLeaseRefused("PLAN_LEASE_IDENTITY_REQUIRED")
    account, lease_id, root = values
    if db_path is None:
        import lease_broker
        db_path = lease_broker.DEFAULT_DB
    path = Path(db_path).absolute()
    if path.is_symlink() or not path.is_file():
        raise PlanLeaseRefused("PLAN_LEASE_UNAVAILABLE")
    conn = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=.25)
    try:
        row = conn.execute(
            "SELECT account,pool,model,orchestrator_id,state,last_heartbeat,ttl,granted_at,renewable,purpose "
            "FROM leases WHERE id=? LIMIT 1", (lease_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise PlanLeaseRefused("PLAN_LEASE_UNAVAILABLE")
    found, pool, selected, owner, state, heartbeat, ttl, granted, renewable, purpose = row
    stamp = time.time() if now is None else now
    numeric = (stamp, heartbeat, ttl, granted)
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in numeric)
            or found != account or pool != expected_pool or selected != model or owner != root
            or purpose != "WORKER" or state not in ("held", "rented") or heartbeat <= 0 or ttl <= 0
            or not granted <= heartbeat <= stamp < heartbeat + ttl
            or type(renewable) is not int or renewable not in (0, 1)
            or (renewable == 0 and stamp >= granted + ttl)):
        raise PlanLeaseRefused("PLAN_LEASE_BINDING_MISMATCH")
    return account


def original_request(pool, model, cwd, prompt, env, *, reserve=False):
    import provider_outcome as outcome
    run = env.get("POOL_RUN_ID", "")
    root = env.get("POOL_ORCHESTRATOR_ID", "")
    if not outcome.IDENT.fullmatch(run) or not outcome.IDENT.fullmatch(root):
        raise ValueError("PLAN_ORIGINAL_IDENTITY_REQUIRED")
    if env.get("LANE_LEASED") == "1":
        raise ValueError("PLAN_LOCAL_PROVIDER_LEASE_REQUIRED")
    state = HERE / "state" / "remote_sub"
    request_raw = outcome.regular_bytes(state / (run + ".request.json"), 32768)
    request = json.loads(request_raw)
    launch = json.loads(outcome.regular_bytes(state / (run + ".request-launch.json"), 32768))
    packet = outcome.regular_bytes(state / (run + ".request.packet"), 1024 * 1024)
    if (request.get("schema") != "mastermind.fabric_request_artifact.v1"
            or launch.get("schema") != "mastermind.fabric_request_launch.v1"
            or any(row.get("run_id") != run or row.get("root_id") != root
                   for row in (request, launch))
            or request.get("task_class") != env.get("POOL_TASK_CLASS")
            or request.get("cwd") != cwd
            or request.get("parent_run_id") != launch.get("parent_run_id")
            or launch.get("state") != "LAUNCH_ATTEMPT_RESERVED"
            or launch.get("request_sha256") != outcome.digest(request_raw)
            or launch.get("route", {}).get("POOL") != pool
            or launch.get("route", {}).get("MODEL") != model
            or request.get("packet_sha256") != outcome.digest(packet)
            or launch.get("packet_sha256") != outcome.digest(packet)
            or outcome.regular_bytes(Path(prompt), 1024 * 1024) != packet):
        raise ValueError("PLAN_ORIGINAL_REQUEST_BINDING_MISMATCH")
    # This is the same one-shot artifact family used by capacity_preflight.
    # Never remove it after a possible provider effect, including an error.
    if reserve:
        outcome.write_new(state / (run + ".task-cli-started.json"), {
        "schema": "mastermind.task_cli_start_reserved.v1", "run_id": run, "reserved_at": time.time(),
        "root_id": root, "pool": pool, "model": model,
        "request_sha256": outcome.digest(request_raw),
        "lease_id": env["POOL_LEASE_ID"], "account": env["POOL_ACCOUNT"],
    })
    return run, state


def _command(pool, model, cwd, prompt, env):
    if pool == "byteplus":
        turns = env.get("POOL_REQUEST_MAX_TURNS") or env.get("POOL_MAX_TURNS") or "32"
        if not str(turns).isdigit() or not 1 <= int(turns) <= 64:
            raise ValueError("BYTEPLUS_TURN_BOUND_REFUSED")
        return [sys.executable, str(HERE / "byteplus_coding_plan.py"),
                cwd, model, prompt, str(turns)]
    command = [sys.executable, str(HERE / "experiential_bridge.py"), "exec",
               "--run-id", env["POOL_RUN_ID"], "--cwd", cwd, "--model", model,
               "--task-class", env["POOL_TASK_CLASS"], "--prompt-file", prompt,
               "--root", env["POOL_ORCHESTRATOR_ID"],
               "--parent", env.get("POOL_PARENT_RUN_ID", "")]
    for name in ("retention_acknowledged", "sensitive_data_opt_in",
                 "proprietary_code", "code_exposure_opt_in", "strict_manual_pin"):
        command += ["--" + name.replace("_", "-"), env.get("EXPERIENTIAL_" + name.upper(), "0")]
    return command


def invoke(pool, model, cwd, prompt):
    global _effect_may_have_started
    import provider_outcome as outcome
    import lease_broker
    import pool_ledger
    from lane_runtime import load_runtime_config, parse_bounded_seconds, run_owned_process

    if pool not in POOLS or not Path(cwd).is_dir():
        raise ValueError("PLAN_WORKER_ARGUMENTS_REFUSED")
    env = dict(os.environ)
    if env.get("LANE_LEASED") == "1":
        raise ValueError("PLAN_LOCAL_PROVIDER_LEASE_REQUIRED")
    account = validate_plan_lease(env, model, expected_pool=pool)
    command = _command(pool, model, cwd, prompt, env)
    run, state = original_request(pool, model, cwd, prompt, env)
    config = load_runtime_config(env)
    timeout = parse_bounded_seconds(env.get("POOL_CHILD_TIMEOUT_SECONDS"),
                                    default=3600, minimum=1, maximum=14400,
                                    key="POOL_CHILD_TIMEOUT_SECONDS")
    process_path = state / (run + ".process.jsonl")
    target = state / (run + ".provider.json")
    # Capture the actual provider process before deriving a terminal outcome.
    _effect_may_have_started = True
    result = run_owned_process(command, cwd=Path(cwd), env=env, timeout=timeout,
                               nice=config.nice, label=run, receipt_path=process_path,
                               timeout_returncode=124)
    raw = result.stdout.encode()
    capture = state / (run + ".provider-stdout.txt")
    for path, data in ((capture, raw), (state / (run + ".provider-stderr.txt"), result.stderr.encode())):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    if not result.cleanup_proven or result.stdout_truncated or result.stderr_truncated:
        print("PLAN_PROCESS_RECONCILIATION_REQUIRED", file=sys.stderr)
        return 76
    detail = {}
    if pool == "byteplus":
        display, fields, final = outcome.parse_claude(raw, result.returncode)
        usage = (final or {}).get("usage") or {}
    else:
        usage = {}
        fields = {"kind": "unknown"}
        display = ""
        try:
            frame = json.loads(raw)
            if frame.get("state") == "EXECUTED" and frame.get("model") == model:
                detail = frame.get("outcome") or {}
                if detail.get("http_status") == 200 and type(detail.get("content")) is str:
                    display = detail["content"]
                    fields = {"kind": "success"}
        except (ValueError, AttributeError):
            pass
        if result.returncode != 0:
            # Only the bridge's closed reason enum; never classify prose.
            reason = result.stderr.strip().split(":", 1)[0]
            fields["kind"] = {
                "GATEWAY_RATE_LIMITED": "rate_limit",
                "GATEWAY_AUTH_REFUSED": "authentication",
                "GATEWAY_REQUEST_REFUSED": "invalid_request",
                "GATEWAY_UPSTREAM_ERROR": "provider_error",
            }.get(reason, "unknown")
            fields["transport_reason"] = reason if re.fullmatch(r"[A-Z_]{1,80}", reason) else "UNCLASSIFIED"
    br = lease_broker.default_broker()
    conn = br._conn()
    try:
        row = conn.execute("SELECT host FROM leases WHERE id=?", (env["POOL_LEASE_ID"],)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError("PLAN_ORIGINAL_LEASE_MISSING")
    receipt_env = {**env, "REMOTE_SUB_RUN_ID": run, "LANE_REMOTE_HOST": row["host"]}
    fields.update(command_rc=result.returncode, stdout_sha256=outcome.digest(raw))
    value = outcome.bound_outcome(fields, receipt_env, pool, model)
    value["source_generation"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if detail:
        value["plan"] = {key: detail.get(key) for key in (
            "plan_lane", "provider_request_id", "cost_status", "cost_usd_observed", "cost_settled")}
    outcome.write_new(target, value)
    if result.timed_out:
        print("PLAN_PROCESS_TIMED_OUT_RECONCILE_ORIGINAL", file=sys.stderr)
        return 76
    observed = subprocess.run([
        sys.executable, str(HERE / "lease_broker.py"), "observe-provider",
        "--lease-id", env["POOL_LEASE_ID"], "--root-id", env["POOL_ORCHESTRATOR_ID"],
        "--run-id", run, "--outcome", str(target), "--process", str(process_path),
    ], capture_output=True, text=True, timeout=30)
    if observed.returncode != 0:
        print("PLAN_QUOTA_OBSERVATION_RECONCILIATION_REQUIRED", file=sys.stderr)
        return 76
    rc = result.returncode
    if rc == 0 and fields["kind"] != "success":
        rc = 1
    tokens = {}
    if all(type(usage.get(key)) is int and usage[key] >= 0
           for key in ("input_tokens", "output_tokens")):
        tokens = {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"]}
    pool_ledger.append(pool=pool, task_class=env["POOL_TASK_CLASS"], model=model,
                       rc=rc, signal="ok" if rc == 0 else fields["kind"], **tokens)
    sys.stdout.write(display)
    if display and not display.endswith("\n"):
        sys.stdout.write("\n")
    if rc:
        print("PLAN_PROVIDER_TERMINAL kind=" + fields["kind"], file=sys.stderr)
    print("PLAN_PROVIDER_RECEIPT=" + str(target), file=sys.stderr)
    return rc


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 4:
        raise ValueError("PLAN_WORKER_ARGUMENTS_REFUSED")
    return invoke(*args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileExistsError:
        print("PLAN_ORIGINAL_EFFECT_ALREADY_RESERVED_RECONCILE", file=sys.stderr)
        raise SystemExit(76 if _effect_may_have_started else 78)
    except Exception as exc:
        prefix = "PLAN_WORKER_RECONCILIATION_REQUIRED " if _effect_may_have_started else "PLAN_WORKER_REFUSED "
        print(prefix + type(exc).__name__, file=sys.stderr)
        raise SystemExit(76 if _effect_may_have_started else 78)

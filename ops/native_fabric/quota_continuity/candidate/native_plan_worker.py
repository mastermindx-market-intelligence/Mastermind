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


def resolve_local_cwd(value):
    """Resolve the ordinary local ~ contract without changing request identity."""
    if type(value) is not str or not value or not (
            value == "~" or value.startswith("~/") or Path(value).is_absolute()):
        raise ValueError("PLAN_LOCAL_WORKDIR_REQUIRED")
    resolved = Path(value).expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("PLAN_LOCAL_WORKDIR_REQUIRED")
    return str(resolved)


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
    cwd_bound = request.get("cwd") == cwd
    if "execution_cwd" in launch:
        cwd_bound = (launch.get("execution_cwd") == cwd
                     and resolve_local_cwd(request.get("cwd")) == cwd)
    if (request.get("schema") != "mastermind.fabric_request_artifact.v1"
            or launch.get("schema") != "mastermind.fabric_request_launch.v1"
            or any(row.get("run_id") != run or row.get("root_id") != root
                   for row in (request, launch))
            or request.get("task_class") != env.get("POOL_TASK_CLASS")
            or not cwd_bound
            or request.get("parent_run_id") != launch.get("parent_run_id")
            or launch.get("state") != "LAUNCH_ATTEMPT_RESERVED"
            or launch.get("request_sha256") != outcome.digest(request_raw)
            or launch.get("route", {}).get("POOL") != pool
            or launch.get("route", {}).get("MODEL") != model
            or request.get("packet_sha256") != outcome.digest(packet)
            or launch.get("packet_sha256") != outcome.digest(packet)
            or outcome.regular_bytes(Path(prompt), 1024 * 1024) != packet):
        raise ValueError("PLAN_ORIGINAL_REQUEST_BINDING_MISMATCH")
    if launch.get("selection_mode") == "AUTO":
        context = request.get("provider_plan_context")
        if (type(context) is not dict
                or context.get("schema") != "mastermind.provider_plan_auto_context.v1"
                or context.get("root_id") != root
                or context.get("parent_run_id") != request.get("parent_run_id")):
            raise ValueError("PLAN_AUTO_REQUEST_FACTS_MISMATCH")
        if pool == "experiential":
            from experiential_plan_policy import FREE_CHAT_MODELS
            consents = context.get("consents")
            if (model not in FREE_CHAT_MODELS or context.get("response_only") is not True
                    or type(consents) is not dict
                    or set(consents) != {"retention_acknowledged", "sensitive_data_opt_in",
                        "proprietary_code", "code_exposure_opt_in"}
                    or any(type(value) is not bool or env.get("EXPERIENTIAL_"+key.upper()) != ("1" if value else "0")
                           for key, value in consents.items())
                    or consents.get("retention_acknowledged") is not True
                    or consents.get("sensitive_data_opt_in") is not True
                    or (consents.get("proprietary_code") and not consents.get("code_exposure_opt_in"))):
                raise ValueError("PLAN_AUTO_FREE_RESPONSE_FACTS_MISMATCH")
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
    sys.stdout.write(display)
    if display and not display.endswith("\n"):
        sys.stdout.write("\n")
    if rc:
        print("PLAN_PROVIDER_TERMINAL kind=" + fields["kind"], file=sys.stderr)
    print("PLAN_PROVIDER_RECEIPT=" + str(target), file=sys.stderr)
    return rc


def record_admission_refusal(pool, reason, rc, *, env=None):
    """The actual slot gate records that provider acquisition was not reached."""
    import provider_outcome as outcome
    env = dict(os.environ) if env is None else env
    if pool not in POOLS or reason not in {
            "host_admission", "physical_admission", "host_policy",
            "child_runtime", "lease_ttl", "pool_capacity", "local_flock"}:
        raise ValueError("PLAN_ADMISSION_REASON_INVALID")
    run, root = env.get("POOL_RUN_ID", ""), env.get("POOL_ORCHESTRATOR_ID", "")
    if not outcome.IDENT.fullmatch(run) or not outcome.IDENT.fullmatch(root) or rc not in {75, 78}:
        raise ValueError("PLAN_ADMISSION_IDENTITY_INVALID")
    state = HERE / "state/remote_sub"
    request_raw = outcome.regular_bytes(state/(run+".request.json"), 32768)
    launch_raw = outcome.regular_bytes(state/(run+".request-launch.json"), 32768)
    request, launch = json.loads(request_raw), json.loads(launch_raw)
    if (request.get("run_id") != run or request.get("root_id") != root
            or launch.get("run_id") != run or launch.get("root_id") != root
            or launch.get("request_sha256") != outcome.digest(request_raw)
            or launch.get("route", {}).get("POOL") != pool
            or launch.get("route", {}).get("MODEL") != env.get("POOL_SELECTED_MODEL")
            or request.get("parent_run_id") != launch.get("parent_run_id")):
        raise ValueError("PLAN_ADMISSION_REQUEST_MISMATCH")
    outcome.write_new(state/(run+".plan-admission-refused.json"), {
        "schema":"mastermind.plan_admission_refusal.v1", "run_id":run, "root_id":root,
        "parent_run_id":request.get("parent_run_id"), "pool":pool,
        "model":env["POOL_SELECTED_MODEL"], "phase":"before_provider_acquire",
        "reason":reason, "rc":rc, "observed_at":time.time(),
        "request_sha256":outcome.digest(request_raw),
        "launch_sha256":outcome.digest(launch_raw),
        "slot_sha256":outcome.digest((HERE/"slot.py").read_bytes()),
    })


def _local_terminal_facts(pool, model, run, state, rc, result, env):
    """Join original owner receipts after slot has returned; no state mutation."""
    import provider_outcome as outcome
    root = env["POOL_ORCHESTRATOR_ID"]
    key = "plan-"+hashlib.sha256((root+"\n"+run+"\n"+pool).encode()).hexdigest()[:40]
    marker = HERE/"active"/key
    if marker.exists() or marker.is_symlink():
        raise ValueError("PLAN_PHYSICAL_CUSTODY_UNSETTLED")
    refused = state/(run+".plan-admission-refused.json")
    if refused.exists() or refused.is_symlink():
        row = json.loads(outcome.regular_bytes(refused, 32768))
        request_raw = outcome.regular_bytes(state/(run+".request.json"), 32768)
        launch_raw = outcome.regular_bytes(state/(run+".request-launch.json"), 32768)
        for name, expected in {
                "schema":"mastermind.plan_admission_refusal.v1", "run_id":run,
                "root_id":root, "parent_run_id":env.get("POOL_PARENT_RUN_ID") or None,
                "pool":pool, "model":model, "rc":rc, "phase":"before_provider_acquire",
                "request_sha256":outcome.digest(request_raw),
                "launch_sha256":outcome.digest(launch_raw),
                "slot_sha256":outcome.digest((HERE/"slot.py").read_bytes())}.items():
            if row.get(name) != expected:
                raise ValueError("PLAN_ADMISSION_RETURN_MISMATCH")
        if (rc not in {75,78} or row.get("reason") not in {
                "host_admission","physical_admission","host_policy",
                "child_runtime","lease_ttl","pool_capacity","local_flock"}
                or result or any((state/(run+s)).exists() or (state/(run+s)).is_symlink()
                    for s in (".task-cli-started.json",".provider.json",".process.jsonl"))):
            raise ValueError("PLAN_ADMISSION_RETURN_UNQUALIFIED")
        return "admission", "local_"+row["reason"], {}
    if rc == 76:
        raise ValueError("PLAN_LOCAL_EFFECT_UNCERTAIN")
    raw = outcome.regular_bytes(state/(run+".provider.json"), 16384)
    value = json.loads(raw)
    processes = outcome.regular_bytes(state/(run+".process.jsonl"), 1024*1024).splitlines()
    if len(processes) != 1:
        raise ValueError("PLAN_PROCESS_RETURN_AMBIGUOUS")
    outcome.validate_receipt(value, json.loads(processes[0]), run)
    reservation = json.loads(outcome.regular_bytes(state/(run+".task-cli-started.json"), 32768))
    request_sha = outcome.digest(outcome.regular_bytes(state/(run+".request.json"), 32768))
    if (any(value.get(k) != v for k,v in {
            "root_id":root,"provider":pool,"model":model,
            "source_generation":outcome.digest(Path(__file__).read_bytes())}.items())
            or any(reservation.get(k) != v for k,v in {
                "schema":"mastermind.task_cli_start_reserved.v1",
                "run_id":run,"root_id":root,"pool":pool,"model":model,
                "request_sha256":request_sha, "lease_id":value.get("lease_id"),
                "account":value.get("account")}.items())):
        raise ValueError("PLAN_PROVIDER_RETURN_BINDING")
    import lease_broker
    database = Path(lease_broker.DEFAULT_DB).resolve(strict=True)
    conn = sqlite3.connect(database.as_uri()+"?mode=ro", uri=True, timeout=.25)
    conn.row_factory = sqlite3.Row
    try:
        lease = conn.execute("SELECT * FROM leases WHERE id=?", (value["lease_id"],)).fetchone()
    finally:
        conn.close()
    if (lease is None or any(lease[k] != v for k,v in {
            "orchestrator_id":root,"pool":pool,"model":model,"account":value["account"],
            "host":value["host"],"state":"released",
            "quota_outcome_sha256":outcome.digest(raw)}.items())):
        raise ValueError("PLAN_PROVIDER_CUSTODY_UNSETTLED")
    capture = outcome.regular_bytes(state/(run+".provider-stdout.txt"), 8*1024*1024)
    if value["stdout_sha256"] != outcome.digest(capture):
        raise ValueError("PLAN_PROVIDER_CAPTURE_CHANGED")
    tokens = {}
    if pool == "byteplus":
        display, fields, final = outcome.parse_claude(capture, value["command_rc"])
        if fields["kind"] != value["kind"]:
            raise ValueError("PLAN_PROVIDER_CLASSIFICATION_CHANGED")
        usage = (final or {}).get("usage") or {}
        if all(type(usage.get(k)) is int and usage[k] >= 0
               for k in ("input_tokens","output_tokens")):
            tokens = {k:usage[k] for k in ("input_tokens","output_tokens")}
    else:
        display = ""
        if value["kind"] == "success":
            frame = json.loads(capture)
            if (frame.get("state") != "EXECUTED" or frame.get("model") != model
                    or frame.get("run_id") != run
                    or frame.get("outcome",{}).get("http_status") != 200
                    or type(frame.get("outcome",{}).get("content")) is not str):
                raise ValueError("PLAN_PROVIDER_RESPONSE_CHANGED")
            display = frame["outcome"]["content"]
    expected_result = (display+("\n" if display and not display.endswith("\n") else "")).encode()
    expected_rc = value["command_rc"]
    if expected_rc == 0 and value["kind"] != "success":
        expected_rc = 1
    if result != expected_result or rc != expected_rc or value["kind"] == "unknown":
        raise ValueError("PLAN_LOCAL_RESULT_UNQUALIFIED")
    signal = "ok" if rc == 0 else "quota" if value["kind"] in outcome.CAPACITY else "other"
    return signal, "provider_"+value["kind"], tokens


def local_controller(pool, model, cwd, prompt, output, log, local_command):
    """The existing M2 controller's capture and terminal publication join.

    sub.sh/slot retain all process, lease, timeout and inference ownership.
    This synchronous adapter adds no outer timeout, provider call or retry.
    """
    global _effect_may_have_started
    import provider_outcome as outcome
    import pool_ledger
    import stat
    from datetime import datetime, timezone
    env = dict(os.environ)
    run = env.get("POOL_RUN_ID", "")
    if not outcome.IDENT.fullmatch(run):
        raise ValueError("PLAN_LOCAL_RUN_INVALID")
    state = HERE/"state/remote_sub"
    output, log = Path(output), Path(log)
    if (output.resolve() != (HERE/"lanes"/(run+".remote.stdout")).resolve()
            or log.resolve() != (state/(run+".log")).resolve()):
        raise ValueError("PLAN_LOCAL_DESTINATION_INVALID")

    def event(message):
        line = (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
                + f" [remote_sub id={run} host=m2] "+message+"\n")
        fd = os.open(log, os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError("PLAN_LOCAL_LOG_UNSAFE")
            if os.write(fd,line.encode()) != len(line.encode()):
                raise OSError("PLAN_LOCAL_LOG_SHORT_WRITE")
            os.fsync(fd)
        finally:
            os.close(fd)
        sys.stderr.write(line)

    # An occupied capture belongs to the original attempt. Do not append a
    # fresh refusal over its existing DONE or re-run its worker.
    stderr_path = state/(run+".local-stderr.txt")
    if any(path.exists() or path.is_symlink() for path in (output,stderr_path)):
        print("PLAN_ORIGINAL_EFFECT_ALREADY_RESERVED_RECONCILE",file=sys.stderr)
        return 76
    try:
        original_request(pool,model,cwd,prompt,env)
        descriptors = []
        try:
            for path in (output,state/(run+".local-stderr.txt")):
                descriptors.append(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        except BaseException:
            for fd in descriptors:
                os.close(fd)
            raise
    except FileExistsError:
        print("PLAN_ORIGINAL_EFFECT_ALREADY_RESERVED_RECONCILE",file=sys.stderr)
        return 76
    except Exception:
        event("PLAN_LOCAL_PREPARATION_REFUSED rc=78 before_worker=1")
        return 78
    event("LOCAL_PLAN_LAUNCH")
    _effect_may_have_started = True
    try:
        with os.fdopen(descriptors[0],"wb") as stdout, os.fdopen(descriptors[1],"wb") as stderr:
            proc = subprocess.run([local_command,str(HERE/"sub.sh"),"--prompt-file",
                pool,prompt,cwd,model],env=env,stdout=stdout,stderr=stderr)
            stdout.flush(); os.fsync(stdout.fileno())
            stderr.flush(); os.fsync(stderr.fileno())
        rc = proc.returncode
        if rc < 0:
            rc = 128-rc
        event("LOCAL_RETURNED rc="+str(rc))
    except Exception:
        event("PLAN_LOCAL_EFFECT_UNKNOWN signal=effect_unknown phase=controller_wait")
        return 76
    try:
        result = outcome.regular_bytes(output,8*1024*1024)
        signal, reason, tokens = _local_terminal_facts(pool,model,run,state,rc,result,env)
    except Exception:
        event("PLAN_LOCAL_EFFECT_UNKNOWN signal=effect_unknown phase=terminal_qualification")
        return 76
    try:
        published = pool_ledger.append(pool=pool,task_class="remote-"+pool,
            job_class=env["POOL_TASK_CLASS"],model=model,run_id=run,
            root_id=env["POOL_ORCHESTRATOR_ID"],parent_run_id=env.get("POOL_PARENT_RUN_ID") or None,
            rc=rc,signal=signal,reason=reason,strict=True,**tokens)
        if not published:
            event("TERMINAL_PUBLICATION_FAILED worker_rc="+str(rc)+" signal="+signal+" recovery_required=1")
            return 74
        event("DONE rc="+str(rc)+" signal="+signal+" reason="+reason)
    except Exception:
        # Publication may have persisted: retain LOCAL_RETURNED/SETTLING,
        # never repeat the append or relabel a completed send as preflight.
        return 74
    try:
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        # The standard result and terminal already persist in original owners.
        # Prevent interpreter shutdown from flushing the same broken pipe.
        null = os.open(os.devnull,os.O_WRONLY)
        try:
            os.dup2(null,sys.stdout.fileno())
        finally:
            os.close(null)
    return rc


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 8 and args[0] == "local-controller":
        return local_controller(*args[1:])
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

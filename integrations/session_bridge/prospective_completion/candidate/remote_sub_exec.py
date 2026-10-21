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
        packet_bytes = packet_path.read_bytes()
        prompt = packet_bytes.decode("utf-8")
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
    completion_binding = None
    if os.environ.get('FABRIC_COMPLETION_BINDING'):
        if artifact_contract is not None:
            return _fail('COMPLETION_ARTIFACT_CONFLICT', 78)
        try:
            completion_binding = completion_producer_binding(
                os.environ['FABRIC_COMPLETION_BINDING'], packet_bytes, key, mode, model, os.environ)
            import artifact_production
            if artifact_production.source_digest(here) != completion_binding['support_digest']:
                raise ValueError('completion_executing_source_changed')
        except (OSError, ValueError, TypeError, KeyError):
            return _fail('COMPLETION_BINDING_REFUSED', 78)

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

    if completion_binding is not None:
        timeout = min(timeout, completion_binding['worker_deadline'] - time.time())
        if timeout <= 0:
            return _fail('COMPLETION_DEADLINE_REFUSED', 78)
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
            completion_owner = None
            if completion_binding is not None:
                import artifact_production
                completion_owner = artifact_stack.enter_context(artifact_production.NewDirectory(completion_binding))
                prepare_completion(completion_owner, completion_binding)
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
            install_signal_cleanup(on_unproven=lease.hold_for_reconciliation)
            if completion_binding is not None:
                timeout = min(timeout, completion_binding['worker_deadline'] - time.time())
                if timeout <= 0:return _fail('COMPLETION_DEADLINE_REFUSED', 78)
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
                if state["started"]:
                    proven = False
                    try:
                        row = json.loads(receipt.read_text().splitlines()[-1])
                        proven = row.get("label") == key and cleanup_receipt_is_proven(row.get("cleanup", {}))
                    except (OSError, ValueError, IndexError):
                        pass
                    if not proven:
                        lease.hold_for_reconciliation("worker_cleanup_unproven")

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
            if completion_owner is not None:
                publish_completion(completion_owner, completion_binding, receipt.read_bytes(),
                                   display_stdout.encode('utf-8'), result.returncode)
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


# Prospective collection evidence only. Never grants retry, admission or acceptance.
def validate_completion_binding(value):
    import re
    fields = {'schema', 'run_id', 'root', 'parent', 'host', 'mode', 'model', 'cwd',
              'packet_sha256', 'support_digest', 'hosts_sha256', 'local_sources', 'controller', 'lease_id', 'account',
              'controller_deadline', 'worker_deadline', 'lease_ttl_requested'}
    if type(value) is not dict or set(value) != fields or value['schema'] != 'mastermind.prospective_completion.v1':
        raise ValueError('completion_binding_schema')
    ident = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
    for k in ('run_id', 'root', 'parent', 'host', 'model', 'lease_id', 'account'):
        if type(value[k]) is not str or not ident.fullmatch(value[k]):
            raise ValueError('completion_binding_identity')
    if value['mode'] not in ('glm', 'qwen', 'minimax') or value['cwd'] != '~':
        raise ValueError('completion_binding_profile')
    for k in ('packet_sha256', 'support_digest', 'hosts_sha256'):
        if type(value[k]) is not str or not re.fullmatch('[a-f0-9]{64}', value[k]):
            raise ValueError('completion_binding_digest')
    sources = value['local_sources']
    if (type(sources) is not dict or set(sources) != {'fabric_task.py','remote_sub.sh','original_delivery_collector.py','artifact_delivery.py','artifact_reader.py','remote_sub_exec.py'}
            or any(type(v) is not str or not re.fullmatch('[a-f0-9]{64}',v) for v in sources.values())):
        raise ValueError('completion_source_binding')
    c = value['controller']
    if type(c) is not dict or set(c) != {'pid', 'generation', 'started_at', 'lock_device', 'lock_inode'}:
        raise ValueError('completion_controller_identity')
    if any(type(c[k]) is not int or c[k] < 0 for k in ('pid', 'started_at', 'lock_device', 'lock_inode')) or c['pid'] <= 0:
        raise ValueError('completion_controller_identity')
    if type(c['generation']) is not str or not re.fullmatch('[a-f0-9]{32}', c['generation']):
        raise ValueError('completion_controller_generation')
    if any(type(value[k]) is not int for k in ('controller_deadline', 'worker_deadline', 'lease_ttl_requested')):
        raise ValueError('completion_deadline')
    if not (c['started_at'] < value['worker_deadline'] <= value['controller_deadline'] <= c['started_at'] + 7200
            and 900 <= value['lease_ttl_requested'] <= 7500):
        raise ValueError('completion_deadline')
    return value


def completion_producer_binding(path, packet, key, mode, model, env):
    import stat
    import artifact_reader
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1 or not 0 < s.st_size <= 16384:
            raise ValueError('completion_binding_file')
        raw = os.read(fd, 16385)
        if len(raw) != s.st_size or artifact_reader.identity(os.fstat(fd)) != artifact_reader.identity(s) or artifact_reader.identity(Path(path).lstat()) != artifact_reader.identity(s):
            raise ValueError('completion_binding_changed')
    finally:
        os.close(fd)
    b = validate_completion_binding(artifact_reader.strict_json(raw))
    expected = {'run_id':key, 'mode':mode, 'model':model,
        'root':env.get('POOL_ORCHESTRATOR_ID'), 'parent':env.get('POOL_PARENT_RUN_ID'),
        'host':env.get('LANE_REMOTE_HOST'), 'lease_id':env.get('POOL_LEASE_ID'),
        'account':env.get('POOL_ACCOUNT'), 'support_digest':env.get('SUPPORT_DIGEST')}
    if any(b[k] != v for k, v in expected.items()) or hashlib.sha256(packet).hexdigest() != b['packet_sha256']:
        raise ValueError('completion_producer_scope')
    if time.time() >= b['worker_deadline']:
        raise ValueError('completion_producer_deadline')
    return b


def prepare_completion(owner, binding):
    import artifact_reader
    owner.verify()
    fd = os.open('binding.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=owner.fd)
    with os.fdopen(fd, 'wb') as f:
        f.write(artifact_reader.canonical(binding)); f.flush(); os.fsync(f.fileno())
    os.fsync(owner.fd); os.fsync(owner.tmp); owner.verify()


def publish_completion(owner, binding, process_raw, stdout, returncode):
    import artifact_reader
    import artifact_production
    process = artifact_reader.strict_json(process_raw)
    if (process.get('label') != binding['run_id'] or process.get('returncode') != returncode
            or type(returncode) is not int or not cleanup_receipt_is_proven(process.get('cleanup', {}))
            or process.get('stdout_truncated') is not False or process.get('stderr_truncated') is not False):
        raise ValueError('completion_process_unproven')
    if not isinstance(stdout, bytes) or not 0 < len(stdout) <= artifact_reader.MAX_FILE:
        raise ValueError('completion_output_bound')
    # The existing process owner supplies actual START/end/PID and cleanup.
    # Bind its bytes and actual retained display output; no pre-exec START claim.
    process['prospective_completion'] = {'binding': binding,
        'stdout_sha256': hashlib.sha256(stdout).hexdigest(), 'stdout_bytes': len(stdout)}
    blobs = {'stdout.txt':stdout, 'process.json':artifact_reader.canonical(process),
             'returncode.txt':str(returncode).encode() + b'\n'}
    for name, data in blobs.items():
        if len(data) > artifact_reader.MAX_FILE:
            raise ValueError('completion_file_bound')
        owner.verify()
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=owner.fd)
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.fsync(owner.fd)
    # Terminal marker is last. Any interrupted prefix remains nonterminal.
    terminal = artifact_reader.canonical({'schema':'mastermind.prospective_terminal.v1',
        'binding_sha256':hashlib.sha256(artifact_reader.canonical(binding)).hexdigest(),
        'files':{k:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in blobs.items()}})
    owner.verify()
    fd = os.open('terminal.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=owner.fd)
    with os.fdopen(fd, 'wb') as f:
        f.write(terminal);f.flush();os.fsync(f.fileno())
    os.fsync(owner.fd);owner.verify()


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

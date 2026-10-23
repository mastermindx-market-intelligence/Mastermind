"""Bounded foreground continuation of proven initial quota rejections.

Each attempt stays an immutable native Fabric run. Correlation artifacts below
are not a queue, acceptance, native conversation binding, or restart authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

import provider_outcome
from commission_deadline import CommissionDeadlineExpired, remaining_seconds

MAX_ATTEMPTS = 3
SCHEMA = "mastermind.fabric_continuation.v1"


def _path(here, run, suffix):
    if not provider_outcome.IDENT.fullmatch(run):
        raise ValueError("continuation_run_invalid")
    return Path(here) / "state" / "remote_sub" / (run + suffix)


def _read(path):
    value = json.loads(provider_outcome.regular_bytes(path, 32768))
    if not isinstance(value, dict):
        raise ValueError("continuation_artifact_invalid")
    return value


def eligible(api, here, run, root, parent):
    """Check original ledger, process, observer, packet and released lease."""
    status = api.inspect_run(run)
    if (status.get("state") == "TERMINAL_FAILURE" and status.get("signal") == "quota"
            and status.get("reason") == "prelease_quota_cooldown"
            and status.get("execution_absence_proven") is True
            and status.get("root_id") == root and status.get("parent_run_id") == parent):
        import quota_circuit
        return quota_circuit.validate_prelease_refusal(here, run, root, parent,
                                                       packet_limit=api.MAX_RESULT_BYTES)
    if (status.get("state") != "TERMINAL" or status.get("signal") != "quota"
            or type(status.get("rc")) is not int or status["rc"] == 0
            or status.get("root_id") != root or status.get("parent_run_id") != parent):
        raise ValueError("continuation_predecessor_not_qualified")
    value = _read(_path(here, run, ".provider.json"))
    record = _read(_path(here, run, ".provider-observed.json"))
    if (value.get("kind") not in provider_outcome.CAPACITY
            or value.get("initial_rejection") is not True
            or record.get("recorded") is not True or record.get("kind") != value.get("kind")
            or value.get("command_rc") != status["rc"]):
        raise ValueError("continuation_not_initial_capacity_rejection")
    proof=value.get("pre_task_evidence")
    if (not isinstance(proof,dict) or proof.get("schema")!="mastermind.capacity_preflight.v1"
            or proof.get("task_cli_started") is not False or proof.get("attempts")!=1
            or proof.get("api_status")!=429
            or status["rc"]!=75
            or proof.get("control_flow_owner") not in {"sub.sh","glm_bound_claude.py"}):
        raise ValueError("continuation_task_not_started_unproven")
    import capacity_preflight
    error={"type":proof.get("error_type"),"code":proof.get("error_code")}
    if capacity_preflight.classify_error(value.get('provider'),proof['api_status'],error)!=value['kind']:
        raise ValueError("continuation_preflight_error_unqualified")
    if (proof.get('request_sha256')!=provider_outcome.digest(capacity_preflight.payload(value['model']))
            or any(not isinstance(proof.get(k),str) or not re.fullmatch('[a-f0-9]{64}',proof[k]) for k in
                   ('endpoint_sha256','response_sha256','support_digest','control_flow_sha256','helper_sha256'))):
        raise ValueError("continuation_preflight_identity_invalid")
    manifest=_read(_path(here,run,".support.json"))
    canonical=json.dumps({"schema":"remote-support-code.v1","files":manifest},sort_keys=True,separators=(',',':')).encode()
    support_sha=provider_outcome.digest(canonical)
    log=provider_outcome.regular_bytes(_path(here,run,".log"),8*1024*1024).decode('utf-8',errors='replace')
    if (proof.get("support_digest")!=support_sha
            or re.findall(r'SUPPORT_VERSION_READY digest=([a-f0-9]{64})',log)!=[support_sha]
            or manifest.get(proof["control_flow_owner"])!=proof.get("control_flow_sha256")
            or manifest.get("capacity_preflight.py")!=proof.get("helper_sha256")):
        raise ValueError("continuation_preflight_source_binding")
    process_raw = provider_outcome.regular_bytes(_path(here, run, ".process.jsonl"), 1048576)
    process = json.loads(process_raw.splitlines()[-1])
    provider_outcome.validate_receipt(value, process, run)
    import lease_broker
    br = lease_broker.default_broker()
    conn = br._conn()
    try:
        lease = conn.execute("SELECT * FROM leases WHERE id=?", (value.get("lease_id"),)).fetchone()
        if (lease is None or lease["state"] != "released"
                or lease["orchestrator_id"] != root
                or lease["account"] != value.get("account")
                or lease["host"] != value.get("host")
                or lease["model"] != value.get("model")
                or br.provider_name(lease["pool"]) != value.get("provider")
                or lease["quota_outcome_sha256"] != provider_outcome.digest(
                    provider_outcome.regular_bytes(_path(here, run, ".provider.json"), 16384))):
            raise ValueError("continuation_lease_not_settled")
    finally:
        conn.close()
    request = _read(_path(here, run, ".request.json"))
    if (request.get("schema") != "mastermind.fabric_request_artifact.v1"
            or request.get("root_id") != root or request.get("parent_run_id") != parent
            or request.get("run_id") != run or request.get("packet") != run + ".request.packet"):
        raise ValueError("continuation_packet_binding")
    packet = provider_outcome.regular_bytes(_path(here, run, ".request.packet"), api.MAX_RESULT_BYTES)
    if provider_outcome.digest(packet) != request.get("packet_sha256"):
        raise ValueError("continuation_packet_changed")
    return {"packet_sha256": request["packet_sha256"],
            "provider_sha256": provider_outcome.digest(provider_outcome.regular_bytes(
                _path(here, run, ".provider.json"), 16384)),
            "process_sha256": provider_outcome.digest(process_raw), "kind": value["kind"]}


def foreground(api, run_id, task_class, **kwargs):
    """Called once by request --quota-fallback; never resurrected by a read."""
    root, parent = kwargs.get("root_id"), kwargs.get("parent_run_id")
    unsupported = ("pool", "prefer", "requested_model", "artifact_names", "native_return",
                   "qualification_host", "new_macro_worktree", "cpu_scope_percent")
    if not root or not parent or any(kwargs.get(k) for k in unsupported):
        raise ValueError("continuation_contract_not_qualified")
    if os.environ.get("POOL_OPERATOR_CHILD_BUDGET", "0") != "0":
        raise ValueError("continuation_operator_children_not_qualified")
    if not all(provider_outcome.IDENT.fullmatch(v) for v in (run_id, root, parent)):
        raise ValueError("continuation_identity_invalid")
    if kwargs.get("max_turns") is not None:
        kwargs["max_turns"] = api.validate_request_max_turns(kwargs["max_turns"])
    here = api.HERE
    # The native transport's existing total fuse is conserved across attempts.
    budget = int(os.environ.get("REMOTE_SUB_MAX_SECS", "7200"))
    if not 1 <= budget <= 7200:
        raise ValueError("continuation_budget_invalid")
    floor = 7200 if kwargs.get("task_complexity") == "C3_FRONTIER_JUDGMENT" else (
        3600 if kwargs.get("task_complexity") in (None, "", "C2_COMPLEX_BOUNDED") else 0)
    budget = max(budget, floor)
    deadline_ns = time.monotonic_ns() + budget * 1_000_000_000
    request_path = _path(here, run_id, ".continuation-request.json")
    request_path.parent.mkdir(parents=True, exist_ok=True)
    if any(p.exists() or p.is_symlink() for p in (*api._paths(run_id),
               _path(here, run_id, ".request.json"), _path(here, run_id, ".request.packet"))):
        raise ValueError("continuation_origin_already_exists")
    provider_outcome.write_new(request_path, {"schema": SCHEMA, "origin_run_id": run_id,
        "root_id": root, "parent_run_id": parent, "max_attempts": MAX_ATTEMPTS,
        "wall_seconds": budget, "deadline_ns": deadline_ns, "background_execution": False,
        **({"max_turns": kwargs["max_turns"]} if kwargs.get("max_turns") is not None else {})})
    current, rc, reason = run_id, 75, "controller_exception"
    try:
        for ordinal in range(MAX_ATTEMPTS):
            remaining = int(remaining_seconds(deadline_ns))
            if remaining < 30:
                reason = "commission_time_exhausted"
                break
            rc = 75
            reason = "controller_exception"
            try:
                rc = api.request(current, task_class, **kwargs, request_remaining_seconds=remaining,
                                 request_capacity_preflight=True, request_deadline_ns=deadline_ns)
            except CommissionDeadlineExpired:
                reason = "commission_time_exhausted"
                break
            except Exception:
                # An ordinary no-route refusal has its own retained request
                # proof. It ends this foreground invocation, never starts an
                # additional attempt and never becomes quota replay evidence.
                status = api.inspect_run(current)
                if (status.get("state") == "REQUEST_REFUSED_BEFORE_LAUNCH"
                        and status.get("execution_absence_proven") is True):
                    reason = "request_refused_before_launch"
                    break
                raise
            if rc == 0:
                reason = "terminal_return"
                break
            if remaining_seconds(deadline_ns) < 30:
                reason = "commission_time_exhausted"
                break
            try:
                proof = eligible(api, here, current, root, parent)
            except (OSError, ValueError, KeyError, IndexError):
                reason = "continuation_evidence_unqualified"
                break
            if ordinal + 1 >= MAX_ATTEMPTS:
                reason = "attempt_bound_reached"
                break
            # A successor gets fresh immutable identity. Root and organizational
            # parent are conserved; predecessor is correlation, not its parent.
            successor = run_id[:90] + ".q" + str(ordinal + 1) + "." + uuid.uuid4().hex[:16]
            provider_outcome.write_new(_path(here, current, ".successor.json"), {
                "schema": SCHEMA, "origin_run_id": run_id, "predecessor_run_id": current,
                "successor_run_id": successor, "ordinal": ordinal + 1,
                "root_id": root, "parent_run_id": parent, **proof,
            })
            print("FABRIC_QUOTA_CONTINUATION predecessor=" + current + " successor=" + successor, flush=True)
            # Freeze and reuse task bytes, never reconstruct from assistant text.
            kwargs = dict(kwargs, packet=_path(here, run_id, ".request.packet"), stdin_bytes=None)
            current = successor
        return int(rc)
    finally:
        provider_outcome.write_new(_path(here, run_id, ".continuation-finished.json"), {
            "schema": SCHEMA, "origin_run_id": run_id, "effective_run_id": current,
            "root_id": root, "parent_run_id": parent, "controller_rc": rc,
            "reason": reason, "background_execution": False,
        })


def resolve(api, run_id):
    """Read-only explicit projection; exact-run inspect/result/accept stay exact."""
    here = api.HERE
    path = _path(here, run_id, ".continuation-request.json")
    if not path.exists() and not path.is_symlink():
        status = api.inspect_run(run_id)
        return {"schema": SCHEMA, "requested_run_id": run_id, "effective_run_id": run_id,
                "effective_status": status, "prior_attempts": [], "controller_return": "NOT_APPLICABLE"}
    intent = _read(path)
    root, parent = intent.get("root_id"), intent.get("parent_run_id")
    if (intent.get("schema") != SCHEMA or intent.get("origin_run_id") != run_id
            or intent.get("max_attempts") != MAX_ATTEMPTS or intent.get("background_execution") is not False):
        raise ValueError("continuation_origin_invalid")
    current, previous, seen = run_id, [], {run_id}
    for ordinal in range(MAX_ATTEMPTS):
        link_path = _path(here, current, ".successor.json")
        if not link_path.exists() and not link_path.is_symlink():
            break
        link = _read(link_path)
        successor = link.get("successor_run_id")
        if (link.get("schema") != SCHEMA or link.get("origin_run_id") != run_id
                or link.get("predecessor_run_id") != current or link.get("ordinal") != ordinal + 1
                or link.get("root_id") != root or link.get("parent_run_id") != parent
                or not isinstance(successor, str) or not provider_outcome.IDENT.fullmatch(successor)
                or successor in seen or ordinal + 1 >= MAX_ATTEMPTS):
            raise ValueError("continuation_link_invalid")
        proof = eligible(api, here, current, root, parent)
        if any(link.get(k) != v for k,v in proof.items()):
            raise ValueError("continuation_proof_changed")
        previous.append(api.inspect_run(current))
        seen.add(successor); current = successor
    final = api.inspect_run(current)
    if final.get("root_id") not in (None, root) or final.get("parent_run_id") not in (None, parent):
        raise ValueError("continuation_successor_identity")
    if previous:
        leaf_request = _path(here, current, ".request.json")
        if leaf_request.exists() or leaf_request.is_symlink():
            origin_request = _read(_path(here, run_id, ".request.json"))
            leaf = _read(leaf_request)
            if (leaf.get("schema") != "mastermind.fabric_request_artifact.v1"
                    or leaf.get("run_id") != current or leaf.get("root_id") != root
                    or leaf.get("parent_run_id") != parent
                    or leaf.get("packet") != current + ".request.packet"
                    or any(leaf.get(k) != origin_request.get(k) for k in
                           ("packet_sha256", "task_class", "cwd"))
                    or provider_outcome.digest(provider_outcome.regular_bytes(
                        _path(here,current,".request.packet"),api.MAX_RESULT_BYTES)) != origin_request.get("packet_sha256")):
                raise ValueError("continuation_successor_task_changed")
        elif final.get("state") != "NOT_FOUND":
            raise ValueError("continuation_successor_request_missing")
        if final.get("result_available") or final.get("state") == "TERMINAL":
            if final.get("root_id") != root or final.get("parent_run_id") != parent:
                raise ValueError("continuation_successor_terminal_identity")
    finished = _path(here, run_id, ".continuation-finished.json")
    returned = "UNCONFIRMED"
    return_reason = None
    if finished.exists() or finished.is_symlink():
        row = _read(finished)
        if (row.get("schema") != SCHEMA or row.get("origin_run_id") != run_id
                or row.get("effective_run_id") != current or row.get("root_id") != root
                or row.get("parent_run_id") != parent or row.get("background_execution") is not False):
            raise ValueError("continuation_return_invalid")
        return_reason = row.get("reason")
        returned = "UNCONFIRMED" if return_reason == "controller_exception" else "RECORDED"
    return {"schema": SCHEMA, "requested_run_id": run_id, "effective_run_id": current,
            "effective_status": final, "prior_attempts": previous, "controller_return": returned,
            "controller_reason": return_reason}


def wait(api, run_id, timeout, interval):
    if not 0 <= timeout <= 7200 or not 0.05 <= interval <= 10:
        raise ValueError("continuation_wait_bounds")
    deadline = time.monotonic() + timeout
    while True:
        value = resolve(api, run_id)
        if value["controller_return"] != "UNCONFIRMED" or time.monotonic() >= deadline:
            return value
        time.sleep(min(interval, max(0, deadline-time.monotonic())))

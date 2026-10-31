"""Draft-only historical correlation for a top-level, plain-packet launch.

No production profile, CLI, transport, admission or lifecycle integration exists.
The caller supplies reviewed historical expectations, not credentials. Even a
successful result grants no read, retry, acceptance or terminal-state authority.
Evidence must be staged in a dedicated private bundle; never point this API at
the live controller store. Native events are retained verbatim, not new receipts.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shlex

from native_plain_packet_check import EvidenceReadSet, Unqualified, digest, strict_json

SUFFIXES = frozenset({"request.json", "request-launch.json", "request.packet",
                      "support.json", "log", "native.jsonl"})
PROFILE_KEYS = frozenset({"run_id", "root_id", "parent_run_id", "host", "sha256",
                          "launch_call_id", "lost_call_id", "controller_handle"})
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
LOG_LINE = re.compile(r"\S+ \[remote_sub id=(\S+) host=(\S+)\] ([A-Z_]+)(?: (.*))?\Z")
ALLOWED_EVENTS = frozenset({"RUN_RESERVED", "ECONOMIC_POLICY", "LEASE_WAIT", "LEASE_OK",
                            "SCP", "SUPPORT_VERSION_READY", "LAUNCH", "LAUNCH_ATTEMPT",
                            "POLL", "POLL_PENDING"})
LIMIT = 2 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise Unqualified(reason)


def decode(raw):
    value = strict_json(raw)

    def finite(item):
        if isinstance(item, float):
            require(math.isfinite(item), "nonfinite_json_number")
        elif isinstance(item, dict):
            for child in item.values():
                finite(child)
        elif isinstance(item, list):
            for child in item:
                finite(child)

    finite(value)
    return value


def _profile(profile):
    # Snapshot into private values; a caller cannot mutate expectations mid-read.
    p = decode(json.dumps(profile, allow_nan=False))
    require(type(p) is dict and set(p) == PROFILE_KEYS, "profile_shape")
    for key in PROFILE_KEYS - {"sha256", "controller_handle"}:
        require(type(p[key]) is str and SAFE_ID.fullmatch(p[key]), "profile_identity")
    require(p["root_id"] == p["parent_run_id"], "nested_legacy_scope_unsupported")
    require(p["launch_call_id"] != p["lost_call_id"], "native_call_identity")
    require(type(p["controller_handle"]) is int and p["controller_handle"] > 0,
            "controller_handle")
    require(type(p["sha256"]) is dict and set(p["sha256"]) == SUFFIXES, "profile_hashes")
    require(all(type(v) is str and SHA.fullmatch(v) for v in p["sha256"].values()),
            "profile_hashes")
    return p


def _records(raw, p):
    request, launch = decode(raw["request.json"]), decode(raw["request-launch.json"])
    request_keys = {"schema", "run_id", "root_id", "parent_run_id", "task_class", "cwd",
                    "automatic_background_execution", "created_at", "packet",
                    "packet_bytes", "packet_sha256"}
    launch_keys = {"schema", "run_id", "root_id", "parent_run_id", "created_at", "state",
                   "request_sha256", "packet_sha256"}
    require(type(request) is dict and set(request) == request_keys, "request_shape")
    require(type(launch) is dict and set(launch) == launch_keys, "launch_shape")
    for record in (request, launch):
        require(all(record[k] == p[k] for k in ("run_id", "root_id", "parent_run_id")),
                "historical_identity")
        require(type(record["created_at"]) in (int, float) and record["created_at"] > 0,
                "historical_time")
    require(launch["created_at"] >= request["created_at"], "historical_time_order")
    require(request["schema"] == "mastermind.fabric_request_artifact.v1"
            and request["task_class"] == "review" and request["cwd"] == "~"
            and request["automatic_background_execution"] is False, "request_contract")
    require(request["packet"] == p["run_id"] + ".request.packet"
            and type(request["packet_bytes"]) is int
            and request["packet_bytes"] == len(raw["request.packet"])
            and request["packet_sha256"] == digest(raw["request.packet"]), "packet_binding")
    require(launch["schema"] == "mastermind.fabric_request_launch.v1"
            and launch["state"] == "LAUNCH_ATTEMPT_RESERVED"
            and launch["request_sha256"] == digest(raw["request.json"])
            and launch["packet_sha256"] == request["packet_sha256"], "launch_binding")
    support = decode(raw["support.json"])
    require(type(support) is dict and bool(support), "support_shape")
    require(all(type(k) is str and k and not k.startswith("/") and ".." not in k.split("/")
                and type(v) is str and SHA.fullmatch(v) for k, v in support.items()),
            "support_shape")
    return digest(json.dumps({"schema": "remote-support-code.v1", "files": support},
                             sort_keys=True, separators=(",", ":")).encode())


def _log(raw, p, support_digest):
    events = []
    for line in raw.decode("utf-8").splitlines():
        match = LOG_LINE.fullmatch(line)
        require(match is not None, "log_shape")
        run, host, event, body = match.groups()
        require(run == p["run_id"] and host == p["host"], "log_identity")
        require(event in ALLOWED_EVENTS, "unsupported_or_adverse_log_event")
        require(not re.search(r"\b(?:EFFECT_UNKNOWN|\w*REFUSED|\w*DENIED|RETRY|REPLACEMENT)\b",
                              body or ""), "adverse_log_body")
        events.append((event, body or ""))
    names = [event for event, _ in events]
    for event in ("RUN_RESERVED", "LEASE_OK", "SUPPORT_VERSION_READY", "LAUNCH", "LAUNCH_ATTEMPT"):
        require(names.count(event) == 1, "log_event_count:" + event)
    require(names.index("RUN_RESERVED") < names.index("LEASE_OK")
            < names.index("SUPPORT_VERSION_READY") < names.index("LAUNCH")
            < names.index("LAUNCH_ATTEMPT"), "log_event_order")
    values = dict(events)
    require(values["RUN_RESERVED"] == "explicit=1", "reservation_contract")
    require(re.fullmatch(r"digest=" + support_digest + r" policy=[0-9a-f]{64}",
                         values["SUPPORT_VERSION_READY"]), "support_binding")
    run = p["run_id"]
    require(values["LAUNCH"] == f"stdout=lanes_{run}.stdout rc_file=ext/lanes_{run}.rc cwd=~",
            "launch_paths")
    require(values["LAUNCH_ATTEMPT"] == "attempt=1", "launch_attempt")


def _loss_carrier(source, handle):
    """Recognize literal calls plus the exact retained result renderer, not JS.

    Only flat literal argument objects are supported. No evaluation, computed
    values, additional statements, reassignment or substitute output is allowed.
    """
    require(type(source) is str, "native_loss_call")
    match = re.fullmatch(
        r'const r=await Promise\.allSettled\(\[\s*(.*?)\s*\]\);'
        r'r\.forEach\(\(v,i\)=>text\(\{i,\.\.\.v\}\)\);\s*', source, re.S)
    require(match is not None, "native_loss_carrier")
    body, pos, calls = match[1], 0, []
    decoder = json.JSONDecoder()

    def space():
        nonlocal pos
        while pos < len(body) and body[pos].isspace():
            pos += 1

    while pos < len(body):
        space()
        call = re.match(r"tools\.(write_stdin|exec_command)\(\{", body[pos:])
        require(call is not None and len(calls) < 16, "native_loss_literal_call")
        method = call[1]
        pos += call.end()
        args = {}
        while True:
            space()
            if body[pos:pos + 1] == '"':
                key, end = decoder.raw_decode(body, pos)
                pos = end
            else:
                key_match = re.match(r"[A-Za-z_][A-Za-z_0-9]*", body[pos:])
                require(key_match is not None, "native_loss_argument_key")
                key = key_match[0]
                pos += key_match.end()
            space()
            require(key not in args and body[pos:pos + 1] == ":", "native_loss_argument_key")
            pos += 1
            space()
            value, pos = decoder.raw_decode(body, pos)
            require(type(value) in (str, int), "native_loss_literal_value")
            args[key] = value
            space()
            if body[pos:pos + 1] == "}":
                pos += 1
                break
            require(body[pos:pos + 1] == ",", "native_loss_literal_object")
            pos += 1
        require(body[pos:pos + 1] == ")", "native_loss_literal_call")
        pos += 1
        if method == "write_stdin":
            require(set(args) == {"session_id", "chars", "yield_time_ms", "max_output_tokens"}
                    and type(args["session_id"]) is int and args["session_id"] > 0
                    and args["chars"] == ""
                    and type(args["yield_time_ms"]) is int and args["yield_time_ms"] > 0
                    and type(args["max_output_tokens"]) is int and args["max_output_tokens"] > 0,
                    "native_loss_stdin_args")
        else:
            require(set(args) <= {"cmd", "workdir", "yield_time_ms", "max_output_tokens"}
                    and type(args.get("cmd")) is str, "native_loss_exec_args")
        calls.append((method, args))
        space()
        if pos < len(body):
            require(body[pos:pos + 1] == ",", "native_loss_call_separator")
            pos += 1
            space()
    require(bool(calls) and calls[0][0] == "write_stdin"
            and calls[0][1]["session_id"] == handle, "native_loss_first_call")


def _native(raw, p):
    rows = [decode(line) for line in raw.splitlines()]
    require(len(rows) == 5 and all(type(r) is dict for r in rows), "native_inventory")
    meta, call, returned, lost, loss = rows
    require(meta.get("type") == "session_meta" and type(meta.get("payload")) is dict
            and meta["payload"].get("id") == p["parent_run_id"], "native_session")
    payloads = []
    for row in rows[1:]:
        require(row.get("type") == "response_item" and type(row.get("payload")) is dict,
                "native_event_shape")
        payloads.append(row["payload"])
    c, r, lc, lr = payloads
    require(c.get("type") == "function_call" and c.get("name") == "exec_command"
            and c.get("call_id") == r.get("call_id") == p["launch_call_id"]
            and r.get("type") == "function_call_output", "native_launch_pair")
    args = decode(c.get("arguments", "null"))
    require(type(args) is dict and type(args.get("cmd")) is str, "native_launch_command")
    # Recognize only the historical final simple request line; never execute it.
    words = shlex.split(args["cmd"].strip().splitlines()[-1])
    require(len(words) >= 3 and words[0] == "python3"
            and Path(words[1]).name == "fabric_task.py" and words[2] == "request",
            "native_launch_command")
    flags = words[3:]
    require(len(flags) % 2 == 0 and len(set(flags[::2])) == len(flags[::2]),
            "native_launch_flags")
    opts = dict(zip(flags[::2], flags[1::2]))
    require(set(opts) <= {"--id", "--class", "--task-complexity", "--subject-pool",
                           "--cwd", "--root", "--parent", "--packet"}, "native_launch_flags")
    require(all(opts.get(k) == v for k, v in {
        "--id": p["run_id"], "--class": "review", "--cwd": "~",
        "--root": p["root_id"], "--parent": p["parent_run_id"]}.items())
        and bool(opts.get("--packet")), "native_launch_identity")
    handle = str(p["controller_handle"])
    require(type(r.get("output")) is str
            and re.findall(r"Process running with session ID (\d+)", r["output"]) == [handle]
            and "Process exited" not in r["output"], "native_controller_handle")
    require(lc.get("type") == "custom_tool_call" and lc.get("name") == "exec"
            and lc.get("call_id") == lr.get("call_id") == p["lost_call_id"]
            and lr.get("type") == "custom_tool_call_output", "native_loss_pair")
    _loss_carrier(lc.get("input"), p["controller_handle"])
    output = lr.get("output")
    require(type(output) is list and all(type(item) is dict and item.get("type") == "input_text"
                                        and type(item.get("text")) is str for item in output),
            "native_loss_output")
    indexed = [decode(item["text"]) for item in output if item["text"].startswith("{")]
    require(all(type(item) is dict and type(item.get("i")) is int for item in indexed),
            "native_loss_index")
    first = [item for item in indexed if item["i"] == 0]
    require(len(first) == 1 and first[0] == {"i": 0, "status": "rejected",
            "reason": "write_stdin failed: Unknown process id " + handle}, "native_loss_result")


def qualify_bundle(directory: Path, profile: dict) -> dict:
    """Correlate a reviewed six-file private bundle without granting any authority.

    The profile is an assertion, not authentication. No profile is shipped for a
    live run. Current reader authorization and broker/host custody remain absent.
    """
    try:
        p = _profile(profile)
        directory = Path(directory)
        require(directory.is_absolute() and ".." not in directory.parts, "bundle_path")
        names = {p["run_id"] + "." + suffix for suffix in SUFFIXES}
        with EvidenceReadSet() as held:
            held.require_directory(directory, mode=0o700)
            chain = held.chain(directory)
            require(set(os.listdir(chain.fd)) == names, "bundle_inventory")
            raw = {}
            for suffix in sorted(SUFFIXES):
                data = held.read(directory / (p["run_id"] + "." + suffix), mode=0o600, limit=LIMIT)
                require(digest(data) == p["sha256"][suffix], "artifact_digest:" + suffix)
                raw[suffix] = data
            support = _records(raw, p)
            _log(raw["log"], p, support)
            _native(raw["native.jsonl"], p)
            require(set(os.listdir(chain.fd)) == names, "bundle_inventory_changed")
            held.verify()
        return {"schema": "mastermind.fabric_legacy_provenance_draft.v1",
                "run_id": p["run_id"], "root_id": p["root_id"],
                "parent_run_id": p["parent_run_id"], "recorded_host": p["host"],
                "predicate": "HISTORICAL_RECORDS_CORRELATED",
                "basis": "caller_reviewed_expectations_not_authentication",
                "artifact_sha256": p["sha256"], "support_digest": support,
                "read_admitted": False, "worker": "UNKNOWN", "stdout_rc": "NOT_READ",
                "producer_contract": "NOT_RETAINED", "current_reader_authority": "UNQUALIFIED",
                "current_broker_host_custody": "UNQUALIFIED", "retry_allowed": False,
                "acceptance_eligible": False, "canonical_state_changed": False}
    except Unqualified:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OSError, RecursionError) as exc:
        raise Unqualified("legacy_bundle_unqualified") from exc

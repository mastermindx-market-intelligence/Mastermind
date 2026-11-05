"""PATCH_ONLY: read this original run's current bytes; never settle its lifecycle.

The incumbent adapter owns transport and the pre-read intent. No function here
launches a worker, talks to a host, edits a lease, or publishes a legacy result.
"""
from __future__ import annotations

import ast
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import artifact_delivery as delivery
import run_observation as observation

RUN = "mm-os-mac-release-review-20261010-01a104e6"
ROOT = "01a104e6-58f8-76d3-8d99-1302a1cca072"
HOST = "ubuntu1"
SUPPORT_DIGEST = "8df7ac415890db623dc24ab9d00a18d0df49dcd9c7a453d43e51014dbff7c499"
PROCESS_SHA256 = "f1d84c0eef378f3c8edd08605ea4ac17a76d1fdb7f8ceac2550cfcf2a5ff0b1d"
LOG_SHA256 = "ec80f718d72a546a7ad8336baebd216831546ccad742c56295d651e96c208372"
PACKET_SHA256 = "5386102be7859c07235727ca88c471c64c49251cad8547a0adc5118d74ab107a"
INTENT = "Original parent authorizes current rc/stdout/process bytes retained to new evidence only; no original controller, lease, terminal or acceptance adjudication."
REQUEST_SCHEMA = "mastermind.original_result_current_read_request.v1"
RESPONSE_SCHEMA = "mastermind.original_result_current_read_response.v1"
MAX_FILE = 65536
MAX_RESPONSE = 200000
PATHS = {"returncode": ("lanes_" + RUN + ".rc",),
         "process": ("lanes", RUN + ".process.jsonl"),
         "stdout": ("lanes_" + RUN + ".stdout",)}
LOCAL_NAMES = {"stdout": "stdout.txt", "process": "process.jsonl", "returncode": "returncode.txt"}
FALSE_CLAIMS = {"execution_replayed": False, "effect_state_changed": False,
                "outcome_accepted": False, "original_controller_inactive_proven": False,
                "original_child_identity_proven": False}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def request_for(run, root):
    if type(run) is not str or type(root) is not str or run != RUN or root != ROOT:
        raise ValueError("current_read_scope_mismatch")
    return {"schema": REQUEST_SCHEMA, "run_id": RUN, "root": ROOT, "host": HOST,
            "support_digest": SUPPORT_DIGEST, "process_sha256": PROCESS_SHA256,
            "log_sha256": LOG_SHA256, "packet_sha256": PACKET_SHA256,
            "current_parent_intent": INTENT}


def validate_request(request):
    if type(request) is not dict or request != request_for(RUN, ROOT):
        raise ValueError("current_read_request_mismatch")


def validate_files(files):
    if files["returncode"] != b"0\n":
        raise ValueError("current_returncode_unqualified")
    process = files["process"]
    if not process.endswith(b"\n") or len(process.splitlines()) != 1 or digest(process) != PROCESS_SHA256:
        raise ValueError("current_process_pin_mismatch")
    # This validates the record's capture/cleanup claims and stdout length join.
    # It does NOT establish a missing original controller/lease binding.
    delivery.validate_capsule_process(process, files["stdout"], RUN)


def read_current(request):
    """Host-side bounded filesystem read, called only by the incumbent transport."""
    validate_request(request)
    uid = os.getuid()
    home = observation.pwd.getpwuid(uid).pw_dir
    with observation.Reader(home, uid) as reader:
        support = observation.support(reader, SUPPORT_DIGEST)
        reader.descend("lanes")
        reader.descend("ext")
        held = {role: reader.read(path, 16 if role == "returncode" else MAX_FILE)
                for role, path in PATHS.items()}
        files = {role: value[0] for role, value in held.items()}
        validate_files(files)
        # Re-read all three while their parent directory descriptors stay held.
        # Checking bytes and identities also rejects same-content replacement.
        for role in ("stdout", "process", "returncode"):
            raw, info = reader.read(PATHS[role], 16 if role == "returncode" else MAX_FILE)
            before_raw, before_info = held[role]
            if raw != before_raw or observation.identity(info) != observation.identity(before_info):
                raise ValueError("current_files_changed")
        reader.verify()
    return {"schema": RESPONSE_SCHEMA, "request_sha256": digest(canonical(request)),
            "state": "CURRENT_BYTES_AVAILABLE", "observed_at": datetime.now(timezone.utc).isoformat(),
            "support": support, **FALSE_CLAIMS,
            "files": {role: {"bytes": len(raw), "sha256": digest(raw),
                              "content_b64": base64.b64encode(raw).decode("ascii")}
                      for role, raw in files.items()}}


def source_bytes():
    paths = {"module": Path(__file__), "observer": Path(observation.__file__),
             "delivery": Path(delivery.__file__)}
    return {key: delivery.local_file(path, 1048576) for key, path in paths.items()}


def qualify(request):
    """Current original-parent read evidence, explicitly not old lease evidence."""
    import run_observation_delivery as existing
    validate_request(request)
    original = existing.request_for(RUN, ROOT)
    if original["host"] != HOST or original["support_digest"] != SUPPORT_DIGEST:
        raise ValueError("current_read_original_scope_changed")
    evidence = existing.qualify(original)
    if (evidence["evidence_sha256"]["log"] != LOG_SHA256 or
            evidence["evidence_sha256"]["packet"] != PACKET_SHA256):
        raise ValueError("current_read_original_sources_changed")
    before = source_bytes()
    if source_bytes() != before or existing.qualify(original) != evidence:
        raise ValueError("current_read_sources_changed")
    return {"original_read_evidence": evidence,
            "read_sources_sha256": {key: digest(raw) for key, raw in before.items()},
            "authority": INTENT}


def code_for_request(request, *, expected_hashes):
    """Source-bound code for the owner's existing isolated Python read transport.

    Only the existing process validator function is embedded from delivery; its
    full source file is hash-bound. No installed delivery transport is embedded.
    """
    validate_request(request)
    raw = source_bytes()
    if type(expected_hashes) is not dict or {key: digest(value) for key, value in raw.items()} != expected_hashes:
        raise ValueError("current_read_embedded_source_mismatch")
    delivery_source = raw["delivery"].decode()
    matches = [node for node in ast.parse(delivery_source).body
               if isinstance(node, ast.FunctionDef) and node.name == "validate_capsule_process"]
    if len(matches) != 1 or matches[0].decorator_list:
        raise ValueError("current_read_validator_source_unavailable")
    validator = ast.get_source_segment(delivery_source, matches[0])
    code = (
        "import sys,types,json,hashlib\n"
        "from datetime import datetime\n"
        "ob=types.ModuleType('run_observation');sys.modules[ob.__name__]=ob\n"
        "exec(" + repr(raw["observer"].decode()) + ",ob.__dict__)\n"
        "de=types.ModuleType('artifact_delivery');sys.modules[de.__name__]=de\n"
        "de.__dict__.update(reader=ob,datetime=datetime)\n"
        "exec(" + repr(validator) + ",de.__dict__)\n"
        "ns={'__name__':'_original_result_read'}\n"
        "exec(" + repr(raw["module"].decode()) + ",ns)\n"
        "raw=sys.stdin.buffer.read(8193)\n"
        "if len(raw)>8192: raise ValueError('request_limit')\n"
        "req=ob.strict_json(raw)\n"
        "if req!=" + repr(request) + ": raise ValueError('bound_request_mismatch')\n"
        "response=ns['read_current'](req)\n"
        "print(ns['canonical'](response).decode())\n"
    )
    if source_bytes() != raw:
        raise ValueError("current_read_sources_changed")
    return code


def validate_response(raw, request):
    validate_request(request)
    if type(raw) is not bytes or len(raw) > MAX_RESPONSE:
        raise ValueError("current_read_response_limit")
    value = observation.strict_json(raw)
    keys = {"schema", "request_sha256", "state", "observed_at", "support", "files", *FALSE_CLAIMS}
    if (type(value) is not dict or set(value) != keys or value["schema"] != RESPONSE_SCHEMA
            or value["request_sha256"] != digest(canonical(request))
            or value["state"] != "CURRENT_BYTES_AVAILABLE"
            or any(value[key] is not False for key in FALSE_CLAIMS)):
        raise ValueError("current_read_response_binding")
    observation.timestamp(value["observed_at"])
    support = value["support"]
    if (type(support) is not dict or set(support) != {"digest", "verified_code_files", "verification",
                "running_process_source_identity_proven", "release_links_verified"}
            or support["digest"] != SUPPORT_DIGEST or type(support["verified_code_files"]) is not int
            or support["verified_code_files"] != 24 or support["verification"] != "manifest_and_fixed_code_hashes"
            or support["running_process_source_identity_proven"] is not False
            or support["release_links_verified"] is not False):
        raise ValueError("current_read_support_binding")
    entries = value["files"]
    if type(entries) is not dict or set(entries) != set(PATHS):
        raise ValueError("current_read_file_set")
    files = {}
    for role, entry in entries.items():
        if (type(entry) is not dict or set(entry) != {"bytes", "sha256", "content_b64"}
                or type(entry["content_b64"]) is not str or type(entry["bytes"]) is not int
                or not 0 <= entry["bytes"] <= (16 if role == "returncode" else MAX_FILE)):
            raise ValueError("current_read_file_shape")
        try:
            data = base64.b64decode(entry["content_b64"], validate=True)
        except (ValueError, UnicodeError):
            raise ValueError("current_read_encoding") from None
        if (len(data) != entry["bytes"] or digest(data) != entry["sha256"]
                or base64.b64encode(data).decode("ascii") != entry["content_b64"]):
            raise ValueError("current_read_file_integrity")
        files[role] = data
    validate_files(files)
    return value, files


def retain_response(request, raw, destination, *, expected_evidence):
    """Retain already received current bytes to a fresh evidence leaf only.

    Caller must qualify and record current intent BEFORE its existing transport.
    This function deliberately has no transport, registry or lifecycle writer.
    """
    value, files = validate_response(raw, request)
    def unchanged():
        if qualify(request) != expected_evidence:
            raise ValueError("current_read_sources_changed")
    unchanged()
    chain = delivery.reserve_destination(destination)
    receipt = {"schema": "mastermind.original_result_current_read_receipt.v1",
               "request": request, "evidence": expected_evidence,
               "state": "CURRENT_BYTES_AVAILABLE", "observed_at": value["observed_at"],
               "provenance": "Current observed bytes only; original lifecycle and acceptance remain unadjudicated.",
               "response_sha256": digest(raw), **FALSE_CLAIMS, "files": []}
    try:
        delivery.write_exclusive(chain.fd, "request.json", canonical({"request": request, "evidence": expected_evidence}))
        for role, data in files.items():
            chain.verify()
            delivery.write_exclusive(chain.fd, LOCAL_NAMES[role], data)
            receipt["files"].append({"path": role, "local_name": LOCAL_NAMES[role],
                                     "bytes": len(data), "sha256": digest(data)})
        delivery.publish_receipt(chain, receipt, {"paths": list(PATHS)}, verify_source=unchanged)
        return receipt
    finally:
        chain.close()

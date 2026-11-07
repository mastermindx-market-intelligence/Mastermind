"""Finite current-owner source read; never successful worker-result recovery.

Admitted against the original assigning parent's explicit Research Factory
request, independently received by Fabric Integration on 2026-10-13. Constants
bound that reviewed scope; they are not caller authentication or new authority.
The unchanged reader's stdout digest is owner-supplied correlation only.
"""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time

import artifact_delivery as delivery
import artifact_reader as reader

RUN_ID = "rf-static-checks-01a1333c-v1"
ROOT = PARENT = "01a1333c-a475-7052-95a8-72a88eb8c17b"
HOST = "ubuntu0"
DESTINATION = Path("/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/static-current-evidence-v1")
STDOUT_CORRELATION = "cda1a432039c5f400936ff9ee4bd4fe9e7984823b1b81d514efd2a556b1505bf"
READER_SHA256 = "e2b08b7967df0e4193ba668cf6f72225429138a9361322c42db6ec84150e3469"
FILES = (
    ("/tmp/fabric-b98b46176702775bb392631281ca4b20a246b4f3/static_checks.py", 29756,
     "7c54af50b531e428ef9f7576daffe146bc470e9eed7ec25531612e2638723224"),
    ("/tmp/fabric-b98b46176702775bb392631281ca4b20a246b4f3/test_research_codegen_static_checks.py", 11206,
     "9686ee2ee165426861fc0e54d3645f3ae3c0bc4eb90a905a02e7fc02571470d3"),
)
SOURCE_HASHES = {
    "log": "a65cc9f5ec0b1b461b48bbcfec07583e004e8dfac11360e34f1cf180dad1c817",
    "process.jsonl": "f4fe460996eca9d0b0ef3b9dfd8505d034570a65ce92522d9f1877d76a8580cd",
}


FIXED_CANARY_RUN = "rf-fixed-smoke-runsc-01a1333c-v1"
FIXED_CANARY_PROFILE = {
    "run_id": FIXED_CANARY_RUN, "root": ROOT, "parent": PARENT,
    "host": "ubuntu1", "mode": "qwen",
    "destination": Path("/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/runtime-release/physical-qualification/fixed-canary-current-evidence-v1"),
    "stdout_correlation": "bb19027a1441ea3b544b79a936bdf6d4519413c68e0a72591ab32a191df69c40",
    "process_stdout_bytes": 50846,
    "process_stdout_sha256": "711b4d929597641a9e0437ed740f1168ec90e51db66a51dc2a1ca28048f5a89d",
    "source_hashes": {
        "log": "0ec7cf75e57e6254a23e5b293fbf82eb59e2028a20744522e5a693006270c138",
        "process.jsonl": "42fea118a19269c6877829566b91ad09fb1cbe5a83ddec0c5b688cd5b3b34015",
    },
    "files": (
        ("/tmp/fabric-9aaa06749fb054c708e129f89059be75332ce59c/canary-carrier.json", 2183,
         "551fe37cae00c19ff3267c8908802c8879c2ca72d7f0edf3dbc1bf481b74d475"),
        ("/tmp/fabric-9aaa06749fb054c708e129f89059be75332ce59c/source-tests.log", 196,
         "9354d4dcf00b432b8a53cff9fa7fdf9d96de531dac8d4b42ea0d508e06f743f9"),
    ),
}


FIXED_CANARY_V2_RUN = "rf-fixed-smoke-runsc-01a1333c-v2"
FIXED_CANARY_V2_PROFILE = {
    "run_id": FIXED_CANARY_V2_RUN, "root": ROOT, "parent": PARENT,
    "host": "ubuntu1", "mode": "qwen",
    "destination": Path("/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/runtime-release/physical-qualification/corrected-canary-v2-current-evidence-v1"),
    "stdout_correlation": "11bd7423e5937f2e37632f35f315cb022a541157220f9d06c524f56f90055718",
    "process_stdout_bytes": 21291,
    "process_stdout_sha256": "a4c03230c1a98123ff5c22a0593e7e2b146f47c4f264d1b9627ba8f7ffa6d16c",
    "source_hashes": {
        "log": "b08bc0116de15f4b0d799fa79249c1d7d940bbc4a87b022f6c42841d1abb60e5",
        "process.jsonl": "be53d07b03a21dc6cda30239b16918d0387259aaa031ebea00f8913e4738ee42",
    },
    "files": (
        ("/tmp/fabric-1ade7b8621f37aac74950ec6e69711947342d9ef/canary-carrier.json", 17348,
         "563e4fc256ff6e10c33e8e82698ce3e685b1af98b5cc557de7250bc09b50fe12"),
        ("/tmp/fabric-1ade7b8621f37aac74950ec6e69711947342d9ef/source-tests.log", 197,
         "433f479390499c89c78e6c1daf30355bd440a9b01cb5c20a0c63fd121e3f2b65"),
    ),
}


FIXED_CANARY_V3_RUN = 'rf-fixed-smoke-runsc-01a1333c-v3'
FIXED_CANARY_V3_PROFILE = {'run_id': 'rf-fixed-smoke-runsc-01a1333c-v3',
 'root': '01a1333c-a475-7052-95a8-72a88eb8c17b',
 'parent': '01a1333c-a475-7052-95a8-72a88eb8c17b',
 'host': 'ubuntu1',
 'mode': 'qwen',
 'destination': Path('/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/runtime-release/physical-qualification/corrected-canary-v3-current-evidence-v1'),
 'stdout_correlation': '4630b08a03d2e437a8050b34f8badac2510b7a9856189ff22cc3654a5d575d1d',
 'process_stdout_bytes': 28430,
 'process_stdout_sha256': '6a100697e0259a9c84fb026b07a44b4be3ab752cfb353aae664c4031823d1459',
 'source_hashes': {'log': '5b46fbafbd6e968fdb0ab1238de1a73a89181c8d3347cd0a1813ada9e38746ed',
                   'process.jsonl': 'c2c7fa0ed52ee9290d4e8e2c3a81454baec1720c47255a6e6107e486e8b0a448'},
 'files': (('/tmp/fabric-15203092e376eff322c8e468619a326f25c33c52/canary-carrier.json',
            19164,
            'c32c2c9961427af8d859214c15893a9bb954ba8f14e118ebcaf485d9399ed5bb'),
           ('/tmp/fabric-15203092e376eff322c8e468619a326f25c33c52/source-tests.log',
            197,
            'e8b3e58fb51e9bd54ba6d8dcb37c4ca334a52f08dad3bc45cffc67f2d3f54f19'))}


def _profile(run_id):
    # Four exact independently commissioned reads, not a caller-supplied profile.
    # No global rebinding: an invocation cannot change the other operation.
    if run_id == FIXED_CANARY_V3_RUN:
        return FIXED_CANARY_V3_PROFILE
    if run_id == FIXED_CANARY_V2_RUN:
        return FIXED_CANARY_V2_PROFILE
    if run_id == FIXED_CANARY_RUN:
        return FIXED_CANARY_PROFILE
    if run_id != RUN_ID:
        raise ValueError("current_evidence_run_not_admitted")
    return {"run_id": RUN_ID, "root": ROOT, "parent": PARENT,
            "host": HOST, "mode": "glm", "destination": DESTINATION,
            "stdout_correlation": STDOUT_CORRELATION,
            "process_stdout_bytes": 5702,
            "process_stdout_sha256": "d738dc3336aaef80c3845cecac686adae628586c12fd97ac4997984c85817fdc",
            "source_hashes": SOURCE_HASHES, "files": FILES}


def request_for(run_id):
    profile = _profile(run_id)
    request = dict(schema=reader.SCHEMA, run_id=run_id, root=profile["root"],
                   parent=profile["parent"], host=profile["host"],
                   stdout_sha256=profile["stdout_correlation"],
                   paths=[row[0] for row in profile["files"]])
    reader.validate_request(request)
    return request


def private_source(path):
    """Use incumbent held-chain read plus the stricter private binding mode."""
    with delivery.DirectoryChain(path.parent) as chain:
        before = os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
            raise ValueError("current_evidence_private_source_required")
        raw = delivery.read_local_at(chain, path.name, 65536)
        after = os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)
        if reader.identity(before) != reader.identity(after):
            raise ValueError("current_evidence_private_source_changed")
        return raw


def validate_process(raw, profile=None):
    """Metadata only: does NOT verify or open the original captured stdout."""
    profile = _profile(RUN_ID) if profile is None else profile
    row = reader.strict_json(raw)
    if (type(row) is not dict or row.get("schema") != "mastermind.local_owned_process_receipt.v1"
            or row.get("label") != profile["run_id"] or type(row.get("returncode")) is not int
            or row["returncode"] != 0 or row.get("timed_out") is not False
            or type(row.get("pid")) is not int or row["pid"] <= 0
            or type(row.get("pgid")) is not int or row["pgid"] != row["pid"]
            or row.get("runtime_failure_code", "missing") is not None
            or type(row.get("stdout_bytes")) is not int or row["stdout_bytes"] != profile["process_stdout_bytes"]
            or row.get("stdout_sha256") != profile["process_stdout_sha256"]
            or row.get("stdout_truncated") is not False or row.get("stderr_truncated") is not False):
        raise ValueError("current_evidence_process_unqualified")
    start = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(row["ended_at"].replace("Z", "+00:00"))
    if start.tzinfo is None or end.tzinfo is None or end < start:
        raise ValueError("current_evidence_process_time_invalid")
    cleanup = row.get("cleanup")
    if (type(cleanup) is not dict or cleanup.get("identity_verified") is not True
            or cleanup.get("census_proven") is not True or cleanup.get("status") != "not_needed"
            or cleanup.get("error_code", "missing") is not None
            or type(cleanup.get("residual_count")) is not int or cleanup["residual_count"] != 0):
        raise ValueError("current_evidence_cleanup_unproven")
    for stem in ("stdin_delivery", "stdout_capture", "stderr_capture"):
        if cleanup.get(stem + "_complete") is not True or cleanup.get(stem + "_error", "missing") is not None:
            raise ValueError("current_evidence_capture_unproven")


def qualify(run_id):
    import fabric_task
    profile = _profile(run_id)
    request = request_for(run_id)
    delivery.assert_capsule_family(run_id)
    sources = {suffix: private_source(delivery.HERE / "state/remote_sub" / (run_id + "." + suffix))
               for suffix in profile["source_hashes"]}
    if any(delivery.digest(sources[suffix]) != expected for suffix, expected in profile["source_hashes"].items()):
        raise ValueError("current_evidence_original_source_changed")
    prefix = (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=" + re.escape(run_id)
              + " host=" + re.escape(profile["host"]) + r"\] (.*)")
    events = [match.group(1) for line in sources["log"].decode("utf-8").splitlines()
              if (match := re.fullmatch(prefix, line))]
    for key, expected in {
        "LAUNCH_ATTEMPT ": ["LAUNCH_ATTEMPT attempt=1"],
        "LAUNCH ": [f"LAUNCH stdout=lanes_{run_id}.stdout rc_file=ext/lanes_{run_id}.rc cwd=~"],
        "REMOTE_DONE ": ["REMOTE_DONE rc=65"],
        "DONE ": ["DONE rc=65 signal=other reason=remote_nonzero"],
    }.items():
        if [event for event in events if event.startswith(key)] != expected:
            raise ValueError("current_evidence_original_controller_mismatch")
    validate_process(sources["process.jsonl"], profile)
    status = fabric_task.inspect_run(run_id)
    if (status.get("run_id") != run_id or status.get("state") != "TERMINAL"
            or type(status.get("rc")) is not int or status["rc"] != 65 or status.get("signal") != "other"
            or status.get("root_id") != profile["root"] or status.get("parent_run_id") != profile["parent"]
            or status.get("lineage_state") != "VERIFIED_TERMINAL"
            or status.get("accepted") is True or status.get("acceptance_state") == "ACCEPTED"):
        raise ValueError("current_evidence_original_projection_unqualified")
    registry = delivery.local_file(delivery.HERE / "hosts.json")
    host = reader.strict_json(registry).get(profile["host"])
    if (type(host) is not dict or profile["mode"] not in host.get("allowed_modes", [])
            or type(host.get("ssh_alias")) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", host["ssh_alias"])):
        raise ValueError("current_evidence_receiver_unqualified")
    if delivery.digest(delivery.local_file(delivery.HERE / "artifact_reader.py", 65536)) != READER_SHA256:
        raise ValueError("current_evidence_reader_changed")
    delivery.assert_capsule_family(run_id)
    return {"request": request, "evidence_sha256": dict(profile["source_hashes"]),
            "registry_sha256": delivery.digest(registry), "reader_sha256": READER_SHA256,
            "ssh_alias": host["ssh_alias"], "original_projection": status,
            "authority": "Independently received and reviewed assigning-owner current read intent; not producer attestation or authentication by labels."}


def export(run_id, destination):
    profile = _profile(run_id)
    # Correlate the invoking root with the independently verified commission.
    # Environment labels are caller discipline, not authentication or authority.
    if (os.environ.get("CODEX_THREAD_ID") != profile["root"]
            or os.environ.get("POOL_ORCHESTRATOR_ID") not in (None, "", profile["root"])):
        raise ValueError("current_evidence_assigning_parent_required")
    # One fresh, exact destination retains any attempted read. Another pathname
    # cannot silently retry a refused/uncertain operation through this profile.
    if str(destination) != str(profile["destination"]):
        raise ValueError("current_evidence_destination_not_admitted")
    evidence = qualify(run_id)
    request = evidence["request"]
    chain = delivery.reserve_destination(destination)
    receipt = {"schema": "mastermind.fabric_current_failed_artifact_evidence.v1",
               "profile": "current_owner_evidence_only", "request": request, "evidence": evidence,
               "destination": str(destination), "state": "READ_PENDING", "files": [],
               "read_transport_state": "MAY_START_AFTER_THIS_INTENT",
               "requested_content_constraints": [{"path": p, "bytes": n, "sha256": h} for p, n, h in profile["files"]],
               "requested_content_constraints_matched": False,
               "original_execution_rc": 65, "original_artifact_contract_passed": False,
               "historical_worker_bytes_attested": False, "stdout_reverified": False,
               "producer_manifest_verified": False, "execution_replayed": False,
               "original_operation_mutated": False, "outcome_accepted": False,
               "provenance": "Current guarded file bytes compared with owner-requested constraints. The stdout digest is unverified correlation, not a historical seal; COMPLETE never changes the failed worker outcome."}

    def unchanged():
        if qualify(run_id) != evidence:
            raise ValueError("current_evidence_source_changed")

    try:
        delivery.write_exclusive(chain.fd, "request.json", reader.canonical(receipt))
        try:
            unchanged(); chain.verify()
            receipt["read_transport_state"] = "ATTEMPTED_UNCONFIRMED"
            raw = delivery.transport(evidence["ssh_alias"], request)
            receipt["read_transport_state"] = "RESPONSE_RECEIVED"
            files = delivery.validate_response(raw, request)
            for (item, data), (path, size, digest) in zip(files, profile["files"]):
                if data is not None and (item["path"] != path or len(data) != size or item["sha256"] != digest):
                    raise ValueError("current_evidence_requested_content_mismatch")
            unchanged(); chain.verify()
            for item, data in files:
                entry = dict(item)
                if data is not None:
                    name = item["path"].rsplit("/", 1)[1]
                    delivery.write_exclusive(chain.fd, name, data)
                    entry["local_name"] = name
                receipt["files"].append(entry)
                delivery.verify_delivered(chain, receipt["files"])
            receipt["state"] = "COMPLETE" if all(item["status"] == "RETRIEVED" for item in receipt["files"]) else "PARTIAL"
            receipt["requested_content_constraints_matched"] = receipt["state"] == "COMPLETE"
        except (OSError, ValueError, TypeError, KeyError, RecursionError, subprocess.SubprocessError, sqlite3.Error):
            delivery.unavailable(receipt, request)
        receipt["observed_at_epoch"] = time.time()
        delivery.publish_receipt(chain, receipt, request,
                                 verify_source=unchanged if receipt["state"] in ("COMPLETE", "PARTIAL") else None)
        return receipt
    finally:
        chain.close()

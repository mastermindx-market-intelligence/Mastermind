"""Closed local Workbench readiness evidence; no lifecycle or browser authority."""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import os
import re

MEDIA_TYPE = "application/vnd.mastermind.workbench-readiness+json"
SCHEMA = "mastermind.workbench_readiness.v1"
PURPOSE = b"mastermind.workbench.local-readiness.v1\0"
KEYS = {"schema", "nonce", "pid", "process_start_identity", "service_uid",
        "host_id", "boot_session_id", "config_sha256", "ready", "fleet_observation", "acquisition_sha256"}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def config_fingerprint(config):
    document = dataclasses.asdict(config)
    # Adding the explicit v5 opt-in must not change installed v1-v4 identities.
    if document.get("schema") != "mastermind.workbench_action_service.v5":
        document.pop("browser_fabric_credentials_file", None)
    return hashlib.sha256(encoded(document)).hexdigest()


def _proof(value, key):
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("READINESS_KEY_INVALID")
    return hmac.new(key, PURPOSE + encoded(value), hashlib.sha256).hexdigest()


def snapshot(runtime, config, *, ready, nonce, acquisition_sha256=None):
    if type(nonce) is not str or re.fullmatch("[0-9a-f]{64}", nonce) is None or type(ready) is not bool:
        raise ValueError("READINESS_REQUEST_INVALID")
    from control_plane.codex_worker import ProcessInspector
    inspector = ProcessInspector()
    process = inspector.inspect(os.getpid())
    host = runtime.services.host_binding
    if (process.effective_uid != os.geteuid() or process.real_uid != os.geteuid()
            or inspector.boot_session_id() != host.boot_session_id):
        raise ValueError("READINESS_PROCESS_INVALID")
    value = {
        "schema": SCHEMA, "nonce": nonce, "pid": os.getpid(),
        "process_start_identity": process.start_identity, "service_uid": os.geteuid(),
        "host_id": host.host_id, "boot_session_id": host.boot_session_id,
        "config_sha256": config_fingerprint(config), "ready": ready,
        "fleet_observation": "unobserved", "acquisition_sha256": acquisition_sha256,
    }
    return dict(value, proof=_proof(value, runtime.services.action_token_key))


def verify_snapshot(value, *, key, nonce, process, host_id, config_sha256, acquisition_sha256=None):
    if type(value) is not dict or set(value) != KEYS | {"proof"}:
        return False
    unsigned = {k: value[k] for k in KEYS}
    if (value["schema"] != SCHEMA or value["nonce"] != nonce
            or type(value["pid"]) is not int or value["pid"] != process["pid"]
            or type(value["service_uid"]) is not int or value["service_uid"] != process["service_uid"]
            or value["process_start_identity"] != process["process_start_identity"]
            or value["boot_session_id"] != process["boot_session_id"]
            or value["host_id"] != host_id or value["config_sha256"] != config_sha256
            or value["acquisition_sha256"] != acquisition_sha256
            or type(value["ready"]) is not bool or value["fleet_observation"] != "unobserved"
            or type(value["proof"]) is not str or re.fullmatch("[0-9a-f]{64}", value["proof"]) is None):
        return False
    return hmac.compare_digest(value["proof"], _proof(unsigned, key))

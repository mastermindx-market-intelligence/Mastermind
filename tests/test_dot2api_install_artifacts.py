from __future__ import annotations

import json
import plistlib
from pathlib import Path

from ops.executive_os.dot2api_worker_service import CONFIG_SCHEMA_VERSION, _FIELDS

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "ops" / "executive_os" / "dot2api-worker.json.template"
PLIST = ROOT / "ops" / "executive_os" / "com.mastermind.executive.worker.dot2api.plist.template"
RUNBOOK = ROOT / "docs" / "runbooks" / "dot2api-worker.md"
BINDINGS = ROOT / "ops" / "executive_os" / "remote-worker-bindings.dot2api.json.template"


def test_dot2api_config_template_matches_closed_service_schema() -> None:
    raw = CONFIG.read_text(encoding="utf-8")
    value = json.loads(raw)
    assert set(value) == _FIELDS
    assert value["schema_version"] == CONFIG_SCHEMA_VERSION
    assert value["dot2api_base_url"] == "http://127.0.0.1:8788"
    assert value["queue"] == "dot"
    assert value["require_secret_canary"] is True
    assert value["operator_harness_armed"] is False
    assert value["control_uid"] == "__CONTROL_UID__"
    assert value["worker_uid"] == "__WORKER_UID__"
    assert value["worker_gid"] == "__WORKER_GID__"
    assert value["worker_user"] == "__WORKER_USER__"
    assert value["python_binary_sha256"] == "__PYTHON_SHA256_64_HEX__"
    assert value["transport_script_sha256"] == "__DOT2API_TRANSPORT_SHA256_64_HEX__"
    serialized = json.dumps(value, sort_keys=True)
    assert '"token"' not in serialized.lower()
    assert "MMX_DOT2API_TOKEN" not in serialized
    assert "credential" not in serialized.lower()


def test_dot2api_launchd_template_has_no_credential_or_parallel_control_plane() -> None:
    raw = PLIST.read_text(encoding="utf-8")
    replacements = {
        "__PYTHON_BINARY__": "/usr/bin/python3",
        "__WORKER_ENTRYPOINT__": "/release/scripts/executive_os_dot2api_worker.py",
        "__WORKER_CONFIG__": "/config/dot2api-worker.json",
        "__RELEASE_ROOT__": "/release",
        "__WORKER_USER__": "_mastermind_dot2api",
        "__WORKER_GROUP__": "_mastermind_dot2api",
        "__PROVIDER_HOME__": "/provider-home",
        "__WORKER_SOCKET__": "/var/run/mastermind-executive/dot2api-worker.sock",
        "__WORKER_STDOUT__": "/var/log/mastermind-dot2api.out.log",
        "__WORKER_STDERR__": "/var/log/mastermind-dot2api.err.log",
    }
    for source, target in replacements.items():
        raw = raw.replace(source, target)
    value = plistlib.loads(raw.encode("utf-8"))
    assert value["Label"] == "com.mastermind.executive.worker.dot2api"
    assert value["ProgramArguments"] == [
        "/usr/bin/python3", "-I", "-S", "-B",
        "/release/scripts/executive_os_dot2api_worker.py",
        "serve", "--config", "/config/dot2api-worker.json",
    ]
    assert set(value["Sockets"]) == {"WorkerBroker"}
    assert value["Sockets"]["WorkerBroker"]["SockPathMode"] == 0o600
    assert "MMX_DOT2API_TOKEN" not in value["EnvironmentVariables"]
    serialized = plistlib.dumps(value).lower()
    assert b"credential" not in serialized
    assert b"dot2api.token" not in serialized


def test_dot2api_runbook_pins_upstream_and_separates_activation() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Pluviobyte/dot2api@66a761505ff73c5dca730260efcaeb5697db81ad" in text
    assert "BUILT_NOT_PROVEN / PRODUCTION_DISARMED" in text
    assert "READ/RESEARCH-only" in text
    assert "max_attempts=1" in text
    assert "originating parent" in text
    assert "separate reviewed activation" in text


def test_dot2api_control_binding_template_is_exact_and_secret_free() -> None:
    value = json.loads(BINDINGS.read_text(encoding="utf-8"))
    assert value["schema"] == "mastermind.remote_worker_host_bindings/v1"
    assert len(value["bindings"]) == 1
    row = value["bindings"][0]
    assert row["adapter_id"] == "dot2api"
    assert row["worker_id"] == "dot2api-01"
    assert row["worker_user"] == "__WORKER_USER__"
    assert row["worker_uid"] == "__WORKER_UID__"
    assert row["worker_gid"] == "__WORKER_GID__"
    assert row["secret_canary_verdict"]["passed"] is True
    assert row["secret_canary_verdict"]["worker_id"] == row["worker_id"]
    assert "token" not in json.dumps(value).lower()
    assert "password" not in json.dumps(value).lower()
    assert "private_key" not in json.dumps(value).lower()

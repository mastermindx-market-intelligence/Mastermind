from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pytest

from ops.executive_os import company_dialogue_principal_edge as edge


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def config_fixture(tmp_path, monkeypatch):
    release = tmp_path / "releases" / ("a" * 40)
    release.mkdir(parents=True)
    config_path = tmp_path / "principal-edge.json"
    runtime_root = tmp_path / "runtime"
    (runtime_root / "bin").mkdir(parents=True)
    python = runtime_root / "bin/python3.12"
    python.write_bytes(b"fixture python")

    monkeypatch.setattr(edge, "SOURCE", release)
    monkeypatch.setattr(edge, "CONFIG", config_path)
    monkeypatch.setattr(edge.shared, "sealed", lambda path, **kwargs: Path(path))

    receipt_sha = "3" * 64
    raw = {
        "schema": edge.SCHEMA,
        "release_sha": release.name,
        "control_uid": 450,
        "worker_uid": 451,
        "runtime_entry_sha256": digest(Path(edge.shared.__file__)),
        "principal_entry_sha256": digest(Path(edge.__file__)),
        "receipt_sha256": receipt_sha,
    }
    config_path.write_text(json.dumps(raw, sort_keys=True) + "\n")
    config_path.chmod(0o444)

    seen = []

    def shared_verify(value):
        seen.append(dict(value))
        return runtime_root, {"shared": True}

    monkeypatch.setattr(edge.shared, "verify", shared_verify)
    return raw, runtime_root, seen


def test_principal_edge_config_is_distinct_and_reuses_shared_runtime(config_fixture):
    raw, runtime_root, seen = config_fixture

    assert edge.read_config() == raw
    root, receipt = edge.verify(raw)

    assert root == runtime_root
    assert receipt == {"shared": True}
    assert seen == [
        {
            "schema": edge.shared.SCHEMA,
            "release_sha": raw["release_sha"],
            "control_uid": raw["control_uid"],
            "worker_uid": raw["worker_uid"],
            "entry_sha256": raw["runtime_entry_sha256"],
            "receipt_sha256": raw["receipt_sha256"],
        }
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "wrong"),
        ("release_sha", "b" * 40),
        ("runtime_entry_sha256", "4" * 64),
        ("principal_entry_sha256", "5" * 64),
    ],
)
def test_principal_edge_refuses_config_or_source_binding_drift(
    config_fixture, field, value
):
    raw, _, _ = config_fixture
    changed = dict(raw)
    changed[field] = value

    with pytest.raises(edge.PrincipalEdgeError):
        edge.verify(changed)


def test_read_config_refuses_shape_uid_and_mode_drift(config_fixture):
    raw, _, _ = config_fixture
    path = edge.CONFIG

    path.chmod(0o644)
    with pytest.raises(edge.PrincipalEdgeError, match="mode"):
        edge.read_config()

    path.chmod(0o444)
    changed = dict(raw)
    changed["worker_uid"] = changed["control_uid"]
    path.chmod(0o644)
    path.write_text(json.dumps(changed))
    path.chmod(0o444)
    with pytest.raises(edge.PrincipalEdgeError, match="config differs"):
        edge.read_config()

    changed = dict(raw)
    changed["extra"] = True
    path.chmod(0o644)
    path.write_text(json.dumps(changed))
    path.chmod(0o444)
    with pytest.raises(edge.PrincipalEdgeError, match="config differs"):
        edge.read_config()


def _arm_main(monkeypatch, raw, runtime_root):
    monkeypatch.setattr(edge, "read_config", lambda: dict(raw))
    monkeypatch.setattr(edge, "verify", lambda _value=None: (runtime_root, {}))
    monkeypatch.setattr(edge, "_require_isolated_runtime", lambda: None)
    monkeypatch.setattr(edge.os, "geteuid", lambda: raw["worker_uid"])


def test_stdio_exec_uses_exact_shared_immutable_runtime(config_fixture, monkeypatch):
    raw, runtime_root, _ = config_fixture
    _arm_main(monkeypatch, raw, runtime_root)
    calls = []

    class Executed(Exception):
        pass

    def execute(path, argv, env):
        calls.append((path, argv, env))
        raise Executed()

    monkeypatch.setattr(edge.os, "execve", execute)

    with pytest.raises(Executed):
        edge.main(["stdio"])

    python = runtime_root / "bin/python3.12"
    assert calls == [
        (
            python,
            [str(python), "-I", "-B", str(Path(edge.__file__)), "sdk-stdio"],
            edge.ENV,
        )
    ]


def test_stdio_refuses_wrong_worker_uid_before_exec(config_fixture, monkeypatch):
    raw, runtime_root, _ = config_fixture
    _arm_main(monkeypatch, raw, runtime_root)
    monkeypatch.setattr(edge.os, "geteuid", lambda: raw["worker_uid"] + 1)
    monkeypatch.setattr(
        edge.os,
        "execve",
        lambda *_args, **_kwargs: pytest.fail("exec must not occur"),
    )

    with pytest.raises(edge.PrincipalEdgeError, match="worker UID"):
        edge.main(["stdio"])


def test_sdk_stdio_uses_principal_unix_transport_only(config_fixture, monkeypatch):
    from integrations import company_dialogue_principal_host_transport as transport

    raw, runtime_root, _ = config_fixture
    _arm_main(monkeypatch, raw, runtime_root)
    python = runtime_root / "bin/python3.12"
    base = Path("/fixture/base")
    monkeypatch.setattr(
        edge,
        "_interpreter_identity",
        lambda: (python, runtime_root, base),
    )
    monkeypatch.setattr(edge.shared, "BASE_PYTHON", base / "bin/python3.12")
    observed = []

    async def run(**kwargs):
        observed.append(kwargs)

    monkeypatch.setattr(transport, "run_principal_company_dialogue_stdio", run)

    assert edge.main(["sdk-stdio"]) == 0
    assert observed == [
        {
            "socket_path": edge.SOCKET,
            "server_uid": raw["control_uid"],
        }
    ]


def test_principal_edge_has_no_provision_install_or_runtime_owner():
    source = Path(edge.__file__).read_text(encoding="utf-8")
    assert "choices=(\"verify\", \"stdio\", \"sdk-stdio\")" in source
    for forbidden in (
        "def provision(",
        "def _provision(",
        "pip install",
        "create_job(",
        "append_event(",
        "Runtime.at(",
        "subprocess.run(",
        "urlopen(",
    ):
        assert forbidden not in source


def test_principal_edge_test_is_in_existing_ci_gate():
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_company_dialogue_principal_edge.py" in gate["included"]

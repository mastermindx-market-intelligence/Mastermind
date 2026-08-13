"""Unit proof for the narrow root-to-worker launch transition."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import executive_os_phase1c_worker_wrapper as wrapper


def _trusted_file(path: Path, payload: bytes = b"fixture\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o444)
    return path


def _config(*, uid: int, gid: int, control_uid: int, home: Path) -> dict[str, object]:
    return {
        "schema_version": "mastermind.executive_worker_broker_config/v1",
        "control_uid": control_uid,
        "worker_uid": uid,
        "worker_gid": gid,
        "worker_user": "_mastermind_worker",
        "worker_id": "codex-01",
        "workspace_root": "/private/workspaces",
        "run_root": "/private/runs",
        "provider_home": os.fspath(home),
        "codex_binary": "/private/bin/codex",
        "allowed_codex_versions": ["0.147.0"],
        "required_team_identifier": "2DC432GLL2",
        "launchd_socket_name": "WorkerBroker",
        "uid_sweep_receipt": "/private/state/uid-sweep.json",
        "require_secret_canary": True,
    }


def test_load_drop_policy_binds_root_inputs_and_directory_identity(tmp_path: Path) -> None:
    owner_uid = os.getuid()
    worker_gid = os.getgid()
    worker_uid = owner_uid if owner_uid > 0 else 451
    control_uid = worker_uid + 1
    release = tmp_path / "release"
    release.mkdir(mode=0o755)
    _trusted_file(release / ".executive-release-manifest.json", b"{}\n")
    _trusted_file(release / "scripts" / "executive_os_phase1c_worker.py")
    wrapper_path = _trusted_file(tmp_path / "worker-wrapper.py")
    python_path = _trusted_file(tmp_path / "python3.12")
    python_path.chmod(0o555)
    home = tmp_path / "provider-home"
    home.mkdir(mode=0o700)
    config_path = tmp_path / "worker.json"
    config_path.write_text(
        json.dumps(
            _config(
                uid=worker_uid,
                gid=worker_gid,
                control_uid=control_uid,
                home=home,
            )
        ),
        encoding="utf-8",
    )
    config_path.chmod(0o440)
    account = SimpleNamespace(
        pw_uid=worker_uid,
        pw_gid=worker_gid,
        pw_dir=os.fspath(home),
        pw_shell="/usr/bin/false",
    )

    policy = wrapper.load_drop_policy(
        config_path,
        release,
        trusted_root_uid=owner_uid,
        account_lookup=lambda _name: account,
        wrapper_path=wrapper_path,
        python_path=python_path,
    )

    assert (policy.uid, policy.gid) == (worker_uid, worker_gid)
    assert policy.home == home
    assert policy.entrypoint == release / "scripts" / "executive_os_phase1c_worker.py"


def test_load_drop_policy_rejects_writable_config(tmp_path: Path) -> None:
    config_path = tmp_path / "worker.json"
    config_path.write_text("{}", encoding="utf-8")
    config_path.chmod(0o660)
    release = tmp_path / "release"
    release.mkdir(mode=0o755)

    with pytest.raises(wrapper.WorkerWrapperError):
        wrapper.load_drop_policy(
            config_path,
            release,
            trusted_root_uid=os.getuid(),
        )


def test_drop_worker_privileges_clears_groups_before_gid_and_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    state: dict[str, object] = {
        "uid": 0,
        "gid": 0,
        "groups": [0, 12, 61, 80, 100],
    }

    def setgroups(values: list[int]) -> None:
        calls.append(("setgroups", list(values)))
        if state["uid"] != 0:
            raise PermissionError("fixture privilege drop")
        state["groups"] = list(values)

    def setgid(value: int) -> None:
        calls.append(("setgid", value))
        state["gid"] = value

    def setuid(value: int) -> None:
        calls.append(("setuid", value))
        if state["uid"] != 0:
            raise PermissionError("fixture privilege drop")
        state["uid"] = value

    monkeypatch.setattr(wrapper.os, "setgroups", setgroups)
    monkeypatch.setattr(wrapper.os, "setgid", setgid)
    monkeypatch.setattr(wrapper.os, "setuid", setuid)
    monkeypatch.setattr(wrapper.os, "getgroups", lambda: list(state["groups"]))
    monkeypatch.setattr(wrapper.os, "getuid", lambda: int(state["uid"]))
    monkeypatch.setattr(wrapper.os, "geteuid", lambda: int(state["uid"]))
    monkeypatch.setattr(wrapper.os, "getgid", lambda: int(state["gid"]))
    monkeypatch.setattr(wrapper.os, "getegid", lambda: int(state["gid"]))

    wrapper.drop_worker_privileges(451, 451)

    assert calls == [
        ("setgroups", []),
        ("setgid", 451),
        ("setuid", 451),
        ("setgroups", [451]),
        ("setuid", 0),
    ]


def test_drop_worker_privileges_fails_if_any_group_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wrapper.os, "setgroups", lambda _values: None)
    monkeypatch.setattr(wrapper.os, "setgid", lambda _value: None)
    monkeypatch.setattr(wrapper.os, "setuid", lambda _value: None)
    monkeypatch.setattr(wrapper.os, "getuid", lambda: 451)
    monkeypatch.setattr(wrapper.os, "geteuid", lambda: 451)
    monkeypatch.setattr(wrapper.os, "getgid", lambda: 451)
    monkeypatch.setattr(wrapper.os, "getegid", lambda: 451)
    monkeypatch.setattr(wrapper.os, "getgroups", lambda: [12])

    with pytest.raises(wrapper.WorkerWrapperError):
        wrapper.drop_worker_privileges(451, 451)

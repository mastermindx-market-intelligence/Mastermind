"""Static, Linux-safe validation for the reviewed macOS launchd surface."""
from __future__ import annotations

import plistlib
import json
import copy
import os
import re
import stat
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "executive_os"
CONTROL = OPS / "com.mastermind.executive.control.plist.template"
WORKER = OPS / "com.mastermind.executive.worker.codex.plist.template"


def _plist(path: Path) -> dict:
    with path.open("rb") as handle:
        return plistlib.load(handle)


def _assert_private_unix_socket(socket_config: dict, *, mode: int) -> None:
    assert set(socket_config) == {
        "SockPathName",
        "SockType",
        "SockPassive",
        "SockPathOwner",
        "SockPathGroup",
        "SockPathMode",
    }
    assert str(socket_config["SockPathName"]).startswith("__")
    assert socket_config["SockType"] == "stream"
    assert socket_config["SockPassive"] is True
    assert socket_config["SockPathMode"] == mode
    forbidden = {
        "SockNodeName",
        "SockServiceName",
        "SockFamily",
        "SockProtocol",
        "Bonjour",
        "MulticastGroup",
    }
    assert forbidden.isdisjoint(socket_config)


def test_launchd_templates_are_two_non_root_persistent_system_jobs() -> None:
    control = _plist(CONTROL)
    worker = _plist(WORKER)
    assert control["Label"] == "com.mastermind.executive.control"
    assert worker["Label"] == "com.mastermind.executive.worker.codex"
    assert control["UserName"] == "__CONTROL_USER__"
    assert worker["UserName"] == "__WORKER_USER__"
    assert control["UserName"] != worker["UserName"]
    assert worker["InitGroups"] is False

    for value in (control, worker):
        assert value["RunAtLoad"] is True
        assert value["KeepAlive"] is True
        assert value["AbandonProcessGroup"] is False
        assert value["ProcessType"] == "Background"
        assert value["Umask"] == 0o77
        assert 1 <= value["ExitTimeOut"] <= 30
        assert value["HardResourceLimits"]["Core"] == 0
        assert value["HardResourceLimits"]["FileSize"] > 0
        argv = value["ProgramArguments"]
        assert argv[0].startswith("__")
        assert not any(item in {"/bin/sh", "/bin/bash", "/usr/bin/env"} for item in argv)
        expected_environment = {
            "HOME",
            "LANG",
            "LC_ALL",
            "NO_COLOR",
            "PATH",
            "PYTHONUNBUFFERED",
            "TZ",
        }
        if value is control:
            assert argv == [
                "__PYTHON_BINARY__",
                "-I",
                "-S",
                "-B",
                "__CONTROL_WRAPPER__",
                "--config",
                "__CONTROL_CONFIG__",
                "--sentinel-file",
                "__CONTROL_SENTINEL_FILE__",
                "--attestation",
                "__CONTROL_ENV_ATTESTATION__",
                "--release-root",
                "__RELEASE_ROOT__",
            ]
            assert "EXECUTIVE_CONTROL_CANARY_VALUE" not in value["EnvironmentVariables"]
        else:
            assert argv == [
                "__PYTHON_BINARY__",
                "-I",
                "-S",
                "-B",
                "__WORKER_ENTRYPOINT__",
                "serve",
                "--config",
                "__WORKER_CONFIG__",
            ]
        assert set(value["EnvironmentVariables"]) == expected_environment

    _assert_private_unix_socket(control["Sockets"]["Operator"], mode=0o660)
    _assert_private_unix_socket(worker["Sockets"]["WorkerBroker"], mode=0o600)
    assert worker["Sockets"]["WorkerBroker"]["SockPathOwner"] == 450
    assert worker["Sockets"]["WorkerBroker"]["SockPathGroup"] == 450


def test_root_scripts_are_syntax_valid_and_service_control_is_fixed_scope() -> None:
    scripts = sorted(OPS.glob("*.sh"))
    assert scripts
    for script in scripts:
        assert script.stat().st_mode & 0o111, f"{script.name} must be executable"
        completed = subprocess.run(
            ["/bin/bash", "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, f"{script.name}: {completed.stderr}"

    lifecycle = (OPS / "service-control.sh").read_text(encoding="utf-8")
    assert "{start|stop|restart|status}" in lifecycle
    assert "com.mastermind.executive.control" in lifecycle
    assert "com.mastermind.executive.worker.codex" in lifecycle
    assert "--label" not in lifecycle and "eval " not in lifecycle


def test_uninstall_preserves_runtime_and_install_does_not_embed_secrets() -> None:
    uninstall = (OPS / "uninstall.sh").read_text(encoding="utf-8")
    install = (OPS / "install.sh").read_text(encoding="utf-8")
    assert "/var/db/mastermind-executive" in uninstall
    assert "rm -rf" not in uninstall
    assert "auth.json" not in CONTROL.read_text(encoding="utf-8")
    assert "auth.json" not in WORKER.read_text(encoding="utf-8")
    assert "API_KEY" not in install and "ACCESS_TOKEN" not in install
    assert "import yaml" not in install and "PyYAML" not in install
    prerequisites = (OPS / "HOST_PREREQUISITES.md").read_text(encoding="utf-8")
    assert "-I -S -B" in prerequisites
    assert "no ambient Python fallback" in prerequisites


def test_host_scripts_use_tools_available_at_absolute_macos_paths() -> None:
    install = (OPS / "install.sh").read_text(encoding="utf-8")
    assert "/usr/bin/realpath" not in install
    assert 'runtime_target="$(/usr/bin/readlink -f "$runtime_link")"' in install

    for name in ("acceptance.sh", "service-control.sh"):
        source = (OPS / name).read_text(encoding="utf-8")
        assert '$(/usr/bin/dirname "$0")' in source
        assert '$(dirname "$0")' not in source


def test_control_canary_uses_post_drop_wrapper_not_launchd_environment() -> None:
    control = _plist(CONTROL)
    argv = control["ProgramArguments"]
    assert argv[4] == "__CONTROL_WRAPPER__"
    assert "__CONTROL_SENTINEL_FILE__" in argv
    assert "__CONTROL_ENV_ATTESTATION__" in argv
    assert "EXECUTIVE_CONTROL_CANARY_VALUE" not in control["EnvironmentVariables"]
    wrapper = (ROOT / "scripts" / "executive_os_phase1c_control_wrapper.py").read_text(
        encoding="utf-8"
    )
    probe = (ROOT / "scripts" / "executive_os_phase1c_env_probe.py").read_text(
        encoding="utf-8"
    )
    assert "os.execve" in wrapper
    assert "exact_mode=0o440" in wrapper
    assert wrapper.index("attest_current_service_environment(") < wrapper.index(
        "service_main("
    )
    assert '"PYTHONDONTWRITEBYTECODE": "1"' in wrapper
    assert "KERN_PROCARGS2" in probe
    assert '"/bin/launchctl", "print"' in probe
    assert '"/bin/ps", "eww"' in probe


def test_control_wrapper_post_exec_argv_contains_no_canary_name(
    monkeypatch,
) -> None:
    from scripts import executive_os_phase1c_control_wrapper as wrapper

    executable = Path(sys.executable).resolve(strict=True)
    fixture_gid = os.getegid()
    release = wrapper._ROOT
    config = release / "fixture-control.json"
    attestation = release / "fixture-control-environment.json"
    account = type(
        "Account",
        (),
        {"pw_dir": "/var/empty/mastermind-executive", "pw_gid": fixture_gid},
    )()
    config_info = type(
        "Stat",
        (),
        {"st_mode": stat.S_IFREG | 0o440, "st_uid": 0, "st_gid": fixture_gid},
    )()
    root_file_info = type(
        "Stat",
        (),
        {"st_mode": stat.S_IFREG | 0o444, "st_uid": 0},
    )()
    root_dir_info = type(
        "Stat",
        (),
        {"st_mode": stat.S_IFDIR | 0o755, "st_uid": 0},
    )()
    captured = {}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            os.fspath(wrapper.Path(__file__)),
            "--config",
            os.fspath(config),
            "--sentinel-file",
            os.fspath(release / "fixture-sentinel"),
            "--attestation",
            os.fspath(attestation),
            "--release-root",
            os.fspath(release),
        ],
    )
    monkeypatch.setattr(wrapper.Path, "cwd", classmethod(lambda _cls: release))
    monkeypatch.setattr(wrapper.pwd, "getpwuid", lambda _uid: account)
    monkeypatch.setattr(wrapper.os, "geteuid", lambda: 501)
    monkeypatch.setattr(wrapper.os, "getuid", lambda: 501)
    monkeypatch.setattr(wrapper.os, "getegid", lambda: fixture_gid)
    monkeypatch.setattr(wrapper.os, "getgid", lambda: fixture_gid)
    monkeypatch.setattr(wrapper.Path, "read_text", lambda path, **_kwargs: json.dumps(
        {
            "control_uid": 501,
            "control_environment_attestation_path": os.fspath(attestation),
            "proof_base_sha": "a" * 40,
            "commit_sha": "a" * 40,
        }
        if path == config
        else {"commit_sha": "a" * 40}
    ))
    monkeypatch.setattr(
        wrapper.Path,
        "lstat",
        lambda path: (
            config_info
            if path == config
            else root_dir_info
            if path == release
            else root_file_info
        ),
    )
    monkeypatch.setattr(
        wrapper,
        "_private_file",
        lambda *_args, **_kwargs: ("b" * 64 + "\n").encode(),
    )
    monkeypatch.setattr(wrapper.Path, "resolve", lambda path, **_kwargs: path)
    monkeypatch.setattr(wrapper.sys, "executable", os.fspath(executable))
    monkeypatch.setattr(wrapper.os, "execve", lambda path, argv, env: captured.update(
        path=path, argv=argv, env=env
    ) or (_ for _ in ()).throw(OSError("fixture stop")))

    assert wrapper.main() == 2
    assert captured["argv"][4].endswith("executive_os_phase1c_control_wrapper.py")
    assert "-c" not in captured["argv"]
    assert wrapper.SENTINEL_NAME not in "\0".join(captured["argv"])
    assert wrapper.SENTINEL_NAME in captured["env"]


def test_installer_program_argument_indices_match_template_payload_slots() -> None:
    install = (OPS / "install.sh").read_text(encoding="utf-8")
    expected = {
        "CONTROL_PLIST": {
            0: "__PYTHON_BINARY__",
            4: "__CONTROL_WRAPPER__",
            6: "__CONTROL_CONFIG__",
            8: "__CONTROL_SENTINEL_FILE__",
            10: "__CONTROL_ENV_ATTESTATION__",
            12: "__RELEASE_ROOT__",
        },
        "WORKER_PLIST": {
            0: "__PYTHON_BINARY__",
            4: "__WORKER_ENTRYPOINT__",
            7: "__WORKER_CONFIG__",
        },
    }
    templates = {"CONTROL_PLIST": _plist(CONTROL), "WORKER_PLIST": _plist(WORKER)}
    for variable, slots in expected.items():
        argv = templates[variable]["ProgramArguments"]
        for index, placeholder in slots.items():
            assert argv[index] == placeholder
            pattern = rf"plutil -replace ProgramArguments\.{index} -string .*\$\{{?{variable}\}}?"
            assert re.search(pattern, install), (variable, index)


def test_worker_entrypoint_imports_under_exact_isolated_plist_shape() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(ROOT / "scripts" / "executive_os_phase1c_worker.py"),
            "--help",
        ],
        cwd=ROOT,
        env={
            "HOME": os.environ.get("HOME", "/tmp"),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_control_config_template_tracks_strict_service_schema() -> None:
    from scripts.executive_os_phase1c import (
        CONTROL_CONFIG_SCHEMA_VERSION,
        _CONFIG_OPTIONAL,
        _CONFIG_REQUIRED,
    )

    value = json.loads((OPS / "control.json.template").read_text(encoding="utf-8"))
    assert value["schema_version"] == CONTROL_CONFIG_SCHEMA_VERSION
    assert set(value) == _CONFIG_REQUIRED | _CONFIG_OPTIONAL


def _membership_snapshot() -> dict:
    return {
        "users": {
            "_mastermind_exec": {
                "primary_gid": 450,
                "unique_uid": 450,
                "generated_uid": "00000000-0000-4000-8000-000000000001",
            },
            "_mastermind_worker": {
                "primary_gid": 451,
                "unique_uid": 451,
                "generated_uid": "00000000-0000-4000-8000-000000000002",
            },
            "operator": {
                "primary_gid": 20,
                "unique_uid": 501,
                "generated_uid": "00000000-0000-4000-8000-000000000003",
            },
        },
        "groups": {
            "_mastermind_exec": {
                "primary_gid": 450,
                "generated_uid": "00000000-0000-4000-8000-000000000004",
                "name_members": (),
                "uuid_members": (),
                "nested_groups": (),
            },
            "_mastermind_worker": {
                "primary_gid": 451,
                "generated_uid": "00000000-0000-4000-8000-000000000005",
                "name_members": ("_mastermind_exec",),
                "uuid_members": ("00000000-0000-4000-8000-000000000001",),
                "nested_groups": (),
            },
            "_mastermind_ops": {
                "primary_gid": 453,
                "generated_uid": "00000000-0000-4000-8000-000000000006",
                "name_members": ("operator",),
                "uuid_members": ("00000000-0000-4000-8000-000000000003",),
                "nested_groups": (),
            },
        },
        "group_primary_gids": {
            "_mastermind_exec": 450,
            "_mastermind_worker": 451,
            "_mastermind_ops": 453,
            "staff": 20,
        },
    }


def _validate_membership(snapshot: dict) -> None:
    from ops.executive_os.acceptance import _validate_protected_membership_snapshot

    _validate_protected_membership_snapshot(
        snapshot,
        control_user="_mastermind_exec",
        worker_user="_mastermind_worker",
        operator_user="operator",
        control_uid=450,
        worker_uid=451,
        operator_uid=501,
        control_gid=450,
        worker_gid=451,
        ops_gid=453,
    )


def test_membership_census_rejects_hidden_primary_gid_user() -> None:
    import pytest

    snapshot = _membership_snapshot()
    snapshot["users"]["rogue"] = {
        "primary_gid": 451,
        "unique_uid": 799,
        "generated_uid": "00000000-0000-4000-8000-000000000099",
    }
    with pytest.raises(RuntimeError, match="hidden primary-GID"):
        _validate_membership(snapshot)


def test_membership_census_rejects_uuid_only_group_member() -> None:
    import pytest

    snapshot = copy.deepcopy(_membership_snapshot())
    snapshot["groups"]["_mastermind_worker"]["uuid_members"] += (
        "00000000-0000-4000-8000-000000000099",
    )
    with pytest.raises(RuntimeError, match="UUID-only"):
        _validate_membership(snapshot)


def test_membership_census_rejects_duplicate_uid_alias() -> None:
    import pytest

    snapshot = copy.deepcopy(_membership_snapshot())
    snapshot["users"]["control-alias"] = {
        "primary_gid": 20,
        "unique_uid": 450,
    }
    with pytest.raises(RuntimeError, match="duplicate or aliased owners"):
        _validate_membership(snapshot)


def test_membership_census_rejects_duplicate_gid_alias() -> None:
    import pytest

    snapshot = copy.deepcopy(_membership_snapshot())
    snapshot["group_primary_gids"]["worker-alias"] = 451
    with pytest.raises(RuntimeError, match="duplicate or aliased owners"):
        _validate_membership(snapshot)


def test_host_scripts_census_all_directory_membership_representations() -> None:
    for name in ("bootstrap-host.sh", "install.sh"):
        source = (OPS / name).read_text(encoding="utf-8")
        assert "-list /Users PrimaryGroupID" in source
        assert "GroupMembership" in source
        assert "GroupMembers" in source
        assert "NestedGroups" in source
        assert "GeneratedUID" in source
        assert '-list "/$record_type" "$attribute"' in source
        assert "Users UniqueID" in source
        assert "Groups PrimaryGroupID" in source
        assert "NR==1 {print $1}" not in source


def test_service_accounts_use_supported_disabled_authentication_policy_check() -> None:
    for name in (
        "bootstrap-host.sh",
        "install.sh",
        "provision-worker-auth.sh",
    ):
        source = (OPS / name).read_text(encoding="utf-8")
        assert "/usr/bin/dscl" in source
        assert "-authonly" in source
        assert "-14167" in source
        assert "eDSAuthAccountDisabled" in source
        assert '-create "/Users/$name" AuthenticationAuthority' not in source

    acceptance = (OPS / "acceptance.py").read_text(encoding="utf-8")
    assert '["/usr/bin/dscl", ".", "-authonly"' in acceptance
    assert "-14167" in acceptance
    assert "eDSAuthAccountDisabled" in acceptance


def test_disabled_authentication_policy_parser_is_exact() -> None:
    import pytest

    from ops.executive_os.acceptance import (
        AcceptanceError,
        _authentication_authority_values,
        _authentication_probe_is_disabled,
    )

    disabled_stdout = (
        b"Authentication for node /Local/Default failed. "
        b"(-14167, eDSAuthAccountDisabled)\n"
    )
    disabled_stderr = b"<dscl_cmd> DS Error: -14167 (eDSAuthAccountDisabled)\n"
    assert _authentication_probe_is_disabled(87, disabled_stdout, disabled_stderr)
    assert not _authentication_probe_is_disabled(0, disabled_stdout, disabled_stderr)
    assert not _authentication_probe_is_disabled(
        87, disabled_stdout, b"<dscl_cmd> DS Error: -14090 (eDSAuthFailed)\n"
    )
    assert not _authentication_probe_is_disabled(87, b"unexpected", disabled_stderr)
    assert _authentication_authority_values(
        0, b"", b"No such key: AuthenticationAuthority\n"
    ) == ()
    assert _authentication_authority_values(
        0, b"AuthenticationAuthority: ;DisabledUser;\n", b""
    ) == (";DisabledUser;",)
    with pytest.raises(AcceptanceError, match="malformed"):
        _authentication_authority_values(0, b"", b"unexpected\n")
    with pytest.raises(AcceptanceError, match="exit 77"):
        _authentication_authority_values(77, b"", b"permission denied\n")


def test_directory_attribute_parser_accepts_standard_and_native_keys() -> None:
    import pytest

    from ops.executive_os.acceptance import (
        AcceptanceError,
        _parse_directory_attribute,
    )

    assert _parse_directory_attribute("UniqueID", b"UniqueID: 450\n") == "450"
    assert (
        _parse_directory_attribute("IsHidden", b"dsAttrTypeNative:IsHidden: 1\n")
        == "1"
    )
    assert (
        _parse_directory_attribute(
            "RealName", b"RealName:\n _mastermind_exec service account\n"
        )
        == "_mastermind_exec service account"
    )
    with pytest.raises(AcceptanceError, match="wrong key"):
        _parse_directory_attribute("IsHidden", b"Different:IsHidden: 1\n")
    with pytest.raises(AcceptanceError, match="empty"):
        _parse_directory_attribute("IsHidden", b"")


def test_shell_attribute_parsers_bind_the_requested_key_and_native_prefix() -> None:
    for name in (
        "bootstrap-host.sh",
        "install.sh",
        "provision-worker-auth.sh",
    ):
        source = (OPS / name).read_text(encoding="utf-8")
        assert '-v attribute="$attribute"' in source
        assert 'native="dsAttrTypeNative:" attribute ":"' in source
        assert "if (NR == 0 || malformed) exit 65" in source
        assert 'sub(/^[^:]*:[[:space:]]*/, "")' not in source


def test_bootstrap_uses_supported_user_identity_and_disable_operations() -> None:
    source = (OPS / "bootstrap-host.sh").read_text(encoding="utf-8")

    assert '-create "/Users/$name" GeneratedUID' not in source
    assert 'read_attribute "/Users/$name" GeneratedUID' in source
    assert (
        '/usr/bin/pwpolicy -n /Local/Default -u "$name" -disableuser' in source
    )
    assert "ensure_authentication_disabled \"$name\"" in source
    assert "assert_reviewed_authentication_authority \"$name\"" in source
    assert "eDSAuthMethodNotSupported" in source
    assert '"$status" -eq 11' in source
    assert '"$state" = needs_disable' in source


def test_acceptance_derives_assignment_roots_from_durable_job_and_attempt() -> None:
    import pytest

    from ops.executive_os.acceptance import AcceptanceError, _durable_assignment_paths

    workspace_root = Path("/var/db/mastermind-executive/jobs/workspaces")
    run_root = Path("/var/db/mastermind-executive/jobs/runs")
    job = {
        "job_id": "job-1",
        "current_attempt_id": "attempt-1",
        "worktree": str(workspace_root / "proof-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
    }
    attempt = {
        "attempt_id": "attempt-1",
        "job_id": "job-1",
        "result_path": str(run_root / "attempt-1" / "output" / "result.json"),
    }
    assert _durable_assignment_paths(
        job, attempt, workspace_root=workspace_root, run_root=run_root
    ) == (Path(job["worktree"]), run_root / "attempt-1")

    drifted = dict(attempt, result_path="/tmp/attempt-1/output/result.json")
    with pytest.raises(AcceptanceError, match="escaped"):
        _durable_assignment_paths(
            job, drifted, workspace_root=workspace_root, run_root=run_root
        )


def _assignment_seal_payload() -> dict:
    def identity(path: str, mode: int) -> dict:
        return {
            "path": path,
            "device": 7,
            "inode": 11 if path.endswith("workspace") else 12,
            "mode": mode,
            "uid": 450,
            "gid": 451,
            "mtime_ns": 1,
        }

    workspace = "/var/db/mastermind-executive/jobs/workspaces/workspace"
    run = "/var/db/mastermind-executive/jobs/runs/attempt-1"
    return {
        "schema_version": "mastermind.executive_assignment_seal/v1",
        "attempt_id": "attempt-1",
        "job_id": "job-1",
        "sealed_at": "2026-08-11T00:00:00+00:00",
        "control_uid": 450,
        "passed": True,
        "paths": {
            "workspace": {
                "before": identity(workspace, 0o750),
                "after": identity(workspace, 0o700),
                "worker_traversal_revoked": True,
            },
            "run": {
                "before": identity(run, 0o770),
                "after": identity(run, 0o700),
                "worker_traversal_revoked": True,
            },
        },
        "uid_sweep": {
            "schema_version": "mastermind.executive_uid_sweep/v1",
            "passed": True,
            "residual_pids_after": [],
        },
    }


def test_acceptance_validates_terminal_assignment_seal_identity_and_modes() -> None:
    import pytest

    from ops.executive_os.acceptance import (
        AcceptanceError,
        _validate_assignment_seal_payload,
    )

    payload = _assignment_seal_payload()
    _validate_assignment_seal_payload(
        payload,
        job_id="job-1",
        attempt_id="attempt-1",
        workspace=Path("/var/db/mastermind-executive/jobs/workspaces/workspace"),
        run_dir=Path("/var/db/mastermind-executive/jobs/runs/attempt-1"),
        control_uid=450,
        worker_gid=451,
    )

    drifted = copy.deepcopy(payload)
    drifted["paths"]["run"]["after"]["mode"] = 0o750
    with pytest.raises(AcceptanceError, match="run"):
        _validate_assignment_seal_payload(
            drifted,
            job_id="job-1",
            attempt_id="attempt-1",
            workspace=Path("/var/db/mastermind-executive/jobs/workspaces/workspace"),
            run_dir=Path("/var/db/mastermind-executive/jobs/runs/attempt-1"),
            control_uid=450,
            worker_gid=451,
        )


def _raw_probe_payload(*, allowed: bool) -> dict:
    operation = {
        "allowed": allowed,
        "error_class": None if allowed else "PermissionError",
        "errno_name": None if allowed else "EACCES",
    }
    return {
        "schema_version": "mastermind.executive_raw_worker_path_probe/v1",
        "effective_uid": 451,
        "real_uid": 451,
        "effective_gid": 451,
        "real_gid": 451,
        "supplementary_gids": [451],
        "results": {
            "workspace": {
                "open": dict(operation),
                "stat": dict(operation),
                "list": dict(operation),
            }
        },
    }


def test_acceptance_raw_worker_probe_requires_eacces_for_every_operation() -> None:
    import pytest

    from ops.executive_os.acceptance import (
        AcceptanceError,
        _validate_raw_worker_probe_payload,
    )

    denied = _raw_probe_payload(allowed=False)
    _validate_raw_worker_probe_payload(
        denied,
        expected_labels={"workspace"},
        worker_uid=451,
        worker_gid=451,
        expect_access=False,
    )
    allowed = _raw_probe_payload(allowed=True)
    _validate_raw_worker_probe_payload(
        allowed,
        expected_labels={"workspace"},
        worker_uid=451,
        worker_gid=451,
        expect_access=True,
    )

    ambiguous = copy.deepcopy(denied)
    ambiguous["results"]["workspace"]["stat"]["errno_name"] = "EPERM"
    with pytest.raises(AcceptanceError, match="EACCES"):
        _validate_raw_worker_probe_payload(
            ambiguous,
            expected_labels={"workspace"},
            worker_uid=451,
            worker_gid=451,
            expect_access=False,
        )


def test_acceptance_covers_success_lost_rotation_active_and_resealed_boundaries() -> None:
    source = (OPS / "acceptance.py").read_text(encoding="utf-8")
    for receipt in (
        "success-terminal-assignment-boundary.json",
        "lost-terminal-assignment-boundary.json",
        "requeue-workspace-rotation-boundary.json",
        "requeue-active-assignment-boundary.json",
        "requeued-terminal-assignment-boundary.json",
        "requeued-archive-still-denied.json",
    ):
        assert receipt in source
    assert '"open"' in source
    assert '"stat"' in source
    assert '"list"' in source
    assert 'os.path.join(path,".")' in source


def test_release_manifest_rejects_ownership_and_group_write_drift() -> None:
    import pytest

    from ops.executive_os.release_manifest import (
        ReleaseManifestError,
        _validate_owned_info,
    )

    _validate_owned_info(
        SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFREG | 0o644),
        label="safe.py",
    )
    with pytest.raises(ReleaseManifestError, match="root:wheel"):
        _validate_owned_info(
            SimpleNamespace(st_uid=501, st_gid=20, st_mode=stat.S_IFREG | 0o644),
            label="mutable.py",
        )
    with pytest.raises(ReleaseManifestError, match="writable"):
        _validate_owned_info(
            SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFREG | 0o664),
            label="group-write.py",
        )


def test_installer_stops_old_daemons_before_first_release_or_policy_mutation() -> None:
    source = (OPS / "install.sh").read_text(encoding="utf-8")
    stop = source.index('/bin/launchctl disable "system/$CONTROL_LABEL"')
    control_absent = source.index(
        'if /bin/launchctl print "system/$CONTROL_LABEL"', stop
    )
    worker_absent = source.index(
        'if /bin/launchctl print "system/$WORKER_LABEL"', control_absent
    )
    archive = source.index('/usr/bin/git -C "$SOURCE_REPO" archive')
    config_write = source.index('temporary.write_text(', archive)
    plist_install = source.index('/usr/bin/install -o root -g wheel -m 0644')
    assert stop < control_absent < worker_absent < archive < config_write < plist_install
    assert "trap leave_installed_services_stopped EXIT" in source
    tail_after_plists = source[plist_install:]
    assert '/bin/launchctl bootstrap' not in tail_after_plists

"""Static, Linux-safe validation for the reviewed macOS launchd surface."""
from __future__ import annotations

import plistlib
import json
import copy
import os
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
    assert "ProcessInspector" not in probe


def test_environment_probe_validates_cross_uid_ps_identity(monkeypatch) -> None:
    import pytest

    from scripts import executive_os_phase1c_env_probe as probe

    identity = {
        "pid": 4242,
        "pgid": 4242,
        "session_id": 4242,
        "start_identity": "1723500000.123456",
        "boot_id": "00000000-0000-4000-8000-000000000001",
        "effective_uid": 450,
        "effective_gid": 450,
        "real_uid": 450,
        "real_gid": 450,
    }
    observed = {
        key: identity[key]
        for key in (
            "pid",
            "pgid",
            "session_id",
            "effective_uid",
            "effective_gid",
            "real_uid",
            "real_gid",
        )
    }
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=(identity["boot_id"] + "\n").encode(),
        stderr=b"",
    )
    monkeypatch.setattr(probe.subprocess, "run", lambda *args, **kwargs: completed)

    assert probe._expected_identity(json.dumps(identity), 4242, observed) == identity

    observed["effective_uid"] = 451
    with pytest.raises(probe.ProbeError, match="expected_identity_mismatch"):
        probe._expected_identity(json.dumps(identity), 4242, observed)


def test_environment_probe_uses_posix_session_id_not_darwin_sess(
    monkeypatch,
) -> None:
    from scripts import executive_os_phase1c_env_probe as probe

    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=b"4242 4200 Tue Aug 12 19:00:00 2026 450 450 450 450\n",
        stderr=b"",
    )
    captured: dict[str, list[str]] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return completed

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    monkeypatch.setattr(probe.os, "getsid", lambda pid: 4200)

    _raw, identity = probe._identity(4242)
    assert "sess=" not in captured["argv"][2]
    assert identity == {
        "pid": 4242,
        "pgid": 4200,
        "session_id": 4200,
        "effective_uid": 450,
        "effective_gid": 450,
        "real_uid": 450,
        "real_gid": 450,
    }


def test_kern_procargs_denial_classification_is_cross_uid_and_exact(
    monkeypatch,
) -> None:
    import errno

    from scripts import executive_os_phase1c_env_probe as probe

    monkeypatch.setattr(probe.os, "geteuid", lambda: 451)
    for observed in (errno.EACCES, errno.EPERM, errno.EINVAL):
        assert probe._is_kern_procargs_denial(observed, target_uid=450)
        assert not probe._is_kern_procargs_denial(observed, target_uid=451)
    assert not probe._is_kern_procargs_denial(errno.EIO, target_uid=450)


def test_acceptance_prepares_control_owned_receipt_container(
    tmp_path, monkeypatch
) -> None:
    import pytest

    from ops.executive_os import acceptance

    monkeypatch.setattr(acceptance, "_assert_no_acl", lambda path: None)
    receipt_root = tmp_path / "acceptance" / ("a" * 40)
    acceptance._prepare_acceptance_receipt_root(
        receipt_root,
        control_uid=os.geteuid(),
        control_gid=os.getegid(),
    )

    for path in (receipt_root.parent, receipt_root):
        info = path.lstat()
        assert info.st_uid == os.geteuid()
        assert info.st_gid == os.getegid()
        assert stat.S_IMODE(info.st_mode) == 0o700

    with pytest.raises(acceptance.AcceptanceError, match="already exists"):
        acceptance._prepare_acceptance_receipt_root(
            receipt_root,
            control_uid=os.geteuid(),
            control_gid=os.getegid(),
        )


def test_acceptance_rejects_existing_receipt_container_metadata_drift(
    tmp_path, monkeypatch
) -> None:
    import pytest

    from ops.executive_os import acceptance

    monkeypatch.setattr(acceptance, "_assert_no_acl", lambda path: None)
    container = tmp_path / "acceptance"
    container.mkdir(mode=0o755)

    with pytest.raises(acceptance.AcceptanceError, match="container metadata drifted"):
        acceptance._prepare_acceptance_receipt_root(
            container / ("a" * 40),
            control_uid=os.geteuid(),
            control_gid=os.getegid(),
        )


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


def test_installer_replaces_whole_program_argument_arrays() -> None:
    install = (OPS / "install.sh").read_text(encoding="utf-8")
    assert "render_launchd_program_arguments.py" in install
    assert install.count("render_launchd_program_arguments.py") == 2
    assert "plutil -replace ProgramArguments." not in install
    assert '"$CONTROL_PLIST" --' in install
    assert '"$WORKER_PLIST" --' in install


def test_launchd_program_argument_renderer_is_exact_and_atomic(tmp_path: Path) -> None:
    from ops.executive_os.render_launchd_program_arguments import (
        render_program_arguments,
    )

    control = tmp_path / "control.plist"
    control.write_bytes(CONTROL.read_bytes())
    control.chmod(0o640)
    expected = [
        "/runtime/python3.12",
        "-I",
        "-S",
        "-B",
        "/release with spaces/control_wrapper.py",
        "--config",
        "/private/control.json",
    ]
    before = control.stat()
    render_program_arguments(control, expected)
    after = control.stat()
    with control.open("rb") as handle:
        rendered = plistlib.load(handle)
    assert rendered["ProgramArguments"] == expected
    assert not any("__" in value for value in rendered["ProgramArguments"])
    assert stat.S_IMODE(after.st_mode) == stat.S_IMODE(before.st_mode)
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)


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


def test_privileged_source_cleanliness_checks_do_not_refresh_worktree_index() -> None:
    install = (OPS / "install.sh").read_text(encoding="utf-8")
    acceptance = (OPS / "acceptance.py").read_text(encoding="utf-8")

    assert (
        '/usr/bin/git --no-optional-locks -C "$SOURCE_REPO" status '
        "--porcelain=v1 --untracked-files=normal"
    ) in install
    assert (
        '"/usr/bin/git",\n'
        '                "--no-optional-locks",\n'
        '                "-C",\n'
        '                self.source_repository,\n'
        '                "status",'
    ) in acceptance


def test_canary_activation_uses_bounded_control_command_not_signal() -> None:
    service = (ROOT / "control_plane" / "executive_service.py").read_text(
        encoding="utf-8"
    )
    cli = (ROOT / "scripts" / "executive_os_phase1c.py").read_text(encoding="utf-8")
    acceptance = (OPS / "acceptance.py").read_text(encoding="utf-8")

    assert 'command == "activate-canary"' in service
    assert '("activate-canary", "Validate and activate' in cli
    assert 'self._control_request("activate-canary")' in acceptance
    assert "signal.SIGHUP" not in cli
    assert "signal.SIGHUP" not in acceptance


def test_acceptance_canonicalizes_canary_paths_like_control_service(tmp_path: Path) -> None:
    from ops.executive_os.acceptance import _canonical_canary_paths

    physical = tmp_path / "private/var/db/mastermind-executive"
    physical.mkdir(parents=True)
    alias = tmp_path / "var"
    alias.symlink_to(tmp_path / "private/var", target_is_directory=True)
    config = {
        "runtime_root": str(alias / "db/mastermind-executive/control/db"),
        "proof_source_repository": str(
            alias / "db/mastermind-executive/control/admin-checkout" / ("a" * 40)
        ),
        "worker_provider_home": str(
            alias / "db/mastermind-executive/workers/codex-01/provider-home"
        ),
    }

    paths = _canonical_canary_paths(config)
    assert paths == {
        "runtime_root": physical / "control/db",
        "database": physical / "control/db/data/control_plane/executive.sqlite3",
        "administrative_checkout_sentinel": (
            physical
            / "control/admin-checkout"
            / ("a" * 40)
            / ".git/executive-secret-canary"
        ),
        "other_worker_home_sentinel": (
            physical / "canary-fixtures/other-worker-home/sentinel"
        ),
        "forbidden_production_sentinel": (
            physical / "canary-fixtures/production-like/sentinel"
        ),
        "codex_home": physical / "workers/codex-01/provider-home",
    }


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


def test_host_word_sorting_avoids_bsd_awk_index_builtin() -> None:
    for name in ("bootstrap-host.sh", "install.sh"):
        source = (OPS / name).read_text(encoding="utf-8")
        assert "for (index=" not in source
        assert "for (field_number=1; field_number<=NF; field_number++)" in source


def test_acceptance_requires_exact_reviewed_macos_directory_group_sets() -> None:
    import pytest

    from ops.executive_os.acceptance import (
        AcceptanceError,
        _validate_service_directory_group_sets,
    )

    system = {
        "everyone": 12,
        "localaccounts": 61,
        "_lpoperator": 100,
        "com.apple.access_disabled": 396,
    }
    worker = _validate_service_directory_group_sets(
        system_group_gids=system,
        control_groups=[450, 451, 12, 61, 100],
        worker_groups=[451, 12, 61, 396, 100],
        control_gid=450,
        worker_gid=451,
    )
    assert worker == {451, 12, 61, 396, 100}
    assert _validate_service_directory_group_sets(
        system_group_gids=system,
        control_groups=[450, 451, 12, 61, 100, 396],
        worker_groups=[451, 12, 61, 100],
        control_gid=450,
        worker_gid=451,
    ) == {451, 12, 61, 100}
    with pytest.raises(AcceptanceError, match="worker account"):
        _validate_service_directory_group_sets(
            system_group_gids=system,
            control_groups=[450, 451, 12, 61, 100],
            worker_groups=[451, 12, 61, 396, 100, 999],
            control_gid=450,
            worker_gid=451,
        )
    with pytest.raises(AcceptanceError, match="system group"):
        _validate_service_directory_group_sets(
            system_group_gids={**system, "everyone": 999},
            control_groups=[450, 451, 12, 61, 100],
            worker_groups=[451, 12, 61, 396, 100],
            control_gid=450,
            worker_gid=451,
        )


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
        expected_supplementary_gids={451},
        expect_access=False,
    )
    allowed = _raw_probe_payload(allowed=True)
    _validate_raw_worker_probe_payload(
        allowed,
        expected_labels={"workspace"},
        worker_uid=451,
        worker_gid=451,
        expected_supplementary_gids={451},
        expect_access=True,
    )

    ambient = copy.deepcopy(denied)
    ambient["supplementary_gids"] = [12, 61, 100, 396, 451]
    _validate_raw_worker_probe_payload(
        ambient,
        expected_labels={"workspace"},
        worker_uid=451,
        worker_gid=451,
        expected_supplementary_gids={12, 61, 100, 396, 451},
        expect_access=False,
    )
    unexpected = copy.deepcopy(ambient)
    unexpected["supplementary_gids"].append(999)
    with pytest.raises(AcceptanceError, match="wrong worker principal"):
        _validate_raw_worker_probe_payload(
            unexpected,
            expected_labels={"workspace"},
            worker_uid=451,
            worker_gid=451,
            expected_supplementary_gids={12, 61, 100, 396, 451},
            expect_access=False,
        )
    malformed = copy.deepcopy(denied)
    malformed["supplementary_gids"] = [{}]
    with pytest.raises(AcceptanceError, match="wrong worker principal"):
        _validate_raw_worker_probe_payload(
            malformed,
            expected_labels={"workspace"},
            worker_uid=451,
            worker_gid=451,
            expected_supplementary_gids={451},
            expect_access=False,
        )

    ambiguous = copy.deepcopy(denied)
    ambiguous["results"]["workspace"]["stat"]["errno_name"] = "EPERM"
    with pytest.raises(AcceptanceError, match="EACCES"):
        _validate_raw_worker_probe_payload(
            ambiguous,
            expected_labels={"workspace"},
            worker_uid=451,
            worker_gid=451,
            expected_supplementary_gids={451},
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

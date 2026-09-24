"""Static, Linux-safe validation for the reviewed macOS launchd surface."""
from __future__ import annotations

import plistlib
import json
import copy
import os
import pytest
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
    assert worker["GroupName"] == "__WORKER_GROUP__"
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
    _assert_private_unix_socket(
        control["Sockets"]["DialogueObservation"], mode=0o660
    )
    assert control["Sockets"]["DialogueObservation"]["SockPathOwner"] == 450
    assert control["Sockets"]["DialogueObservation"]["SockPathGroup"] == 457
    _assert_private_unix_socket(worker["Sockets"]["WorkerBroker"], mode=0o600)
    assert worker["Sockets"]["WorkerBroker"]["SockPathOwner"] == 450
    assert worker["Sockets"]["WorkerBroker"]["SockPathGroup"] == 450


def test_executive_daemons_do_not_throttle_disk_io() -> None:
    # Regression pin for the real-host Phase 1C acceptance timeout at
    # create-proof-job: launchd's LowPriorityIO=true is inherited by every
    # child process the daemon spawns (I/O policy is inherited across
    # fork/exec), so the admin-checkout workspace `git clone --local
    # --no-hardlinks --no-checkout` -- measured at ~1.9s at normal I/O
    # priority on this host, with a 22 MB result against a 31 MB .git, so
    # volume was never the issue -- measured >180s (the probe's own bound)
    # under IOPOL_THROTTLE, which is exactly what LowPriorityIO=true sets,
    # against a 60s service timeout. The same inherited throttle also
    # explains the `codex --version` (0.12s normal vs. 10s budget) and
    # `codesign --verify --strict` (2.3s normal vs. 60s budget) timeouts,
    # and why a manual `_mastermind_exec` shell reproduction always
    # succeeded: an interactive shell has normal I/O policy; only launchd's
    # plist-driven daemon start applies the throttle. Both Executive
    # launchd plists must never set the key again. ProcessType=Background
    # (CPU scheduling politeness, not disk I/O) is retained and is not the
    # defect -- it stays asserted on both templates below.
    for value in (_plist(CONTROL), _plist(WORKER)):
        assert "LowPriorityIO" not in value
        assert value["ProcessType"] == "Background"


@pytest.mark.skipif(sys.platform != "darwin", reason="plutil is a Darwin-only binary")
def test_generated_launchd_plists_pass_plutil_lint(tmp_path: Path) -> None:
    # The raw templates are not what ships: install.sh (1) installs the
    # template file as-is, (2) replaces ProgramArguments wholesale via
    # render_launchd_program_arguments.py, then (3) replaces the remaining
    # placeholder-bearing keys with individual `plutil -replace` calls,
    # before finally running `plutil -lint` on the result (see the block in
    # ops/executive_os/install.sh starting at
    # `CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"`). Mirror
    # that exact sequence -- same commands, representative substitutions --
    # so lint exercises what an install actually produces, not a
    # __PLACEHOLDER__-riddled template plutil would never see in practice.
    from ops.executive_os.render_launchd_program_arguments import (
        render_program_arguments,
    )

    def plutil(*args: str) -> None:
        completed = subprocess.run(
            ["/usr/bin/plutil", *args],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr

    control = tmp_path / "control.plist"
    control.write_bytes(CONTROL.read_bytes())
    control.chmod(0o644)
    render_program_arguments(
        control,
        [
            "/opt/mastermind-python/bin/python3.12",
            "-I",
            "-S",
            "-B",
            "/release/scripts/executive_os_phase1c_control_wrapper.py",
            "--config",
            "/config/control.json",
            "--sentinel-file",
            "/config/control-env-canary",
            "--attestation",
            "/state/control-environment-attestation.json",
            "--release-root",
            "/release",
        ],
    )
    plutil("-replace", "WorkingDirectory", "-string", "/release", str(control))
    plutil("-replace", "UserName", "-string", "_mastermind_exec", str(control))
    plutil("-replace", "GroupName", "-string", "_mastermind_exec", str(control))
    plutil(
        "-replace", "EnvironmentVariables.HOME", "-string",
        "/var/db/mastermind-executive/control/home", str(control),
    )
    plutil(
        "-replace", "Sockets.Operator.SockPathName", "-string",
        "/var/run/mastermind-executive/control.sock", str(control),
    )
    plutil("-replace", "Sockets.Operator.SockPathOwner", "-integer", "450", str(control))
    plutil("-replace", "Sockets.Operator.SockPathGroup", "-integer", "453", str(control))
    plutil(
        "-replace", "Sockets.DialogueObservation.SockPathName", "-string",
        "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
        str(control),
    )
    plutil(
        "-replace", "Sockets.DialogueObservation.SockPathOwner", "-integer",
        "450", str(control),
    )
    plutil(
        "-replace", "Sockets.DialogueObservation.SockPathGroup", "-integer",
        "457", str(control),
    )
    plutil(
        "-replace", "Sockets.DialogueObservation.SockPathMode", "-integer",
        "432", str(control),
    )
    plutil(
        "-replace", "StandardOutPath", "-string",
        "/var/log/mastermind-executive/control/stdout.log", str(control),
    )
    plutil(
        "-replace", "StandardErrorPath", "-string",
        "/var/log/mastermind-executive/control/stderr.log", str(control),
    )

    worker = tmp_path / "worker.plist"
    worker.write_bytes(WORKER.read_bytes())
    worker.chmod(0o644)
    render_program_arguments(
        worker,
        [
            "/opt/mastermind-python/bin/python3.12",
            "-I",
            "-S",
            "-B",
            "/release/scripts/executive_os_phase1c_worker.py",
            "serve",
            "--config",
            "/config/worker.json",
        ],
    )
    plutil("-replace", "WorkingDirectory", "-string", "/release", str(worker))
    plutil("-replace", "UserName", "-string", "_mastermind_worker", str(worker))
    plutil("-replace", "GroupName", "-string", "_mastermind_worker", str(worker))
    plutil(
        "-replace", "EnvironmentVariables.HOME", "-string",
        "/var/db/mastermind-executive/workers/codex-01/provider-home", str(worker),
    )
    plutil(
        "-replace", "Sockets.WorkerBroker.SockPathName", "-string",
        "/var/run/mastermind-executive/worker.sock", str(worker),
    )
    plutil("-replace", "Sockets.WorkerBroker.SockPathOwner", "-integer", "450", str(worker))
    plutil("-replace", "Sockets.WorkerBroker.SockPathGroup", "-integer", "450", str(worker))
    plutil("-replace", "Sockets.WorkerBroker.SockPathMode", "-integer", "384", str(worker))
    plutil(
        "-replace", "StandardOutPath", "-string",
        "/var/log/mastermind-executive/worker/stdout.log", str(worker),
    )
    plutil(
        "-replace", "StandardErrorPath", "-string",
        "/var/log/mastermind-executive/worker/stderr.log", str(worker),
    )

    completed = subprocess.run(
        ["/usr/bin/plutil", "-lint", str(control), str(worker)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    rendered_control = plistlib.loads(control.read_bytes())
    assert set(rendered_control["Sockets"]) == {
        "Operator",
        "CeoIngress",
        "DialogueObservation",
    }
    assert rendered_control["Sockets"]["DialogueObservation"] == {
        "SockPathName": (
            "/var/run/mastermind-dialogue-observation/"
            "dialogue-observation.sock"
        ),
        "SockType": "stream",
        "SockPassive": True,
        "SockPathOwner": 450,
        "SockPathGroup": 457,
        "SockPathMode": 0o660,
    }

    for rendered_path in (control, worker):
        with rendered_path.open("rb") as handle:
            rendered = plistlib.load(handle)
        assert "LowPriorityIO" not in rendered
        assert rendered["ProcessType"] == "Background"


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
    # DR-B1 added backup and the privileged-action wave adds one socket-activated
    # root broker. All four still replace ProgramArguments wholesale via the
    # reviewed renderer, never piecemeal via `plutil -replace ProgramArguments.N`.
    assert install.count("render_launchd_program_arguments.py") == 4
    assert "plutil -replace ProgramArguments." not in install
    assert '"$CONTROL_PLIST" --' in install
    assert '"$WORKER_PLIST" --' in install
    assert '"$BACKUP_PLIST" --' in install
    assert '"$PRIVILEGED_PLIST" --' in install
    assert 'scripts/executive_os_phase1c_worker.py"' in install
    assert 'ops/executive_os/run_nightly_backup.sh"' in install
    assert 'plutil -replace UserName -string "$WORKER_USER" "$WORKER_PLIST"' in install
    assert 'plutil -replace GroupName -string "$WORKER_GROUP" "$WORKER_PLIST"' in install
    assert 'plutil -replace UserName -string "$CONTROL_USER" "$BACKUP_PLIST"' in install
    assert 'WORKER_SUPPLEMENTARY_GIDS' in install
    assert 'worker account has an unreviewed macOS directory group vector' in install
    assert 'verify_reviewed_system_group com.apple.access_disabled 396' in install


def test_installer_ships_the_backup_daemon_disabled_like_the_others() -> None:
    install = (OPS / "install.sh").read_text(encoding="utf-8")
    assert 'BACKUP_LABEL="com.mastermind.executive.backup"' in install
    for line in (
        '/bin/launchctl disable "system/$BACKUP_LABEL"',
        '/bin/launchctl bootout "system/$BACKUP_LABEL"',
    ):
        assert line in install
    assert 'if /bin/launchctl print "system/$BACKUP_LABEL" >/dev/null 2>&1; then' in install
    assert (
        '/usr/bin/install -o root -g wheel -m 0644 "$RELEASE_ROOT/ops/executive_os/$BACKUP_LABEL.plist.template" "$BACKUP_PLIST"'
        in install
    )


def test_worker_config_requires_sorted_exact_ambient_group_allowlist(
    tmp_path: Path,
) -> None:
    import pytest

    from scripts.executive_os_phase1c_worker import WorkerConfigError, _load_config

    value = {
        "schema_version": "mastermind.executive_worker_broker_config/v4",
        "control_uid": 450,
        "worker_uid": 451,
        "worker_gid": 451,
        "allowed_supplementary_gids": [12, 61, 100, 396],
        "worker_user": "_mastermind_worker",
        "worker_id": "codex-01",
        "workspace_root": "/private/workspaces",
        "run_root": "/private/runs",
        "provider_home": "/private/provider-home",
        "codex_binary": "/private/bin/codex",
        "codex_attestation_receipt": "/private/state/codex-attestation.json",
        "allowed_codex_versions": ["0.147.0"],
        "required_team_identifier": "2DC432GLL2",
        "launchd_socket_name": "WorkerBroker",
        "uid_sweep_receipt": "/private/state/uid-sweep.json",
        "require_secret_canary": True,
        "operator_harness_armed": False,
    }
    path = tmp_path / "worker.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o440)
    assert _load_config(path, require_root_owner=False)[
        "allowed_supplementary_gids"
    ] == [12, 61, 100, 396]

    value["allowed_supplementary_gids"] = [12, 61, 999, 100]
    path.chmod(0o640)
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o440)
    with pytest.raises(WorkerConfigError, match="supplementary groups"):
        _load_config(path, require_root_owner=False)


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
    # Installed product groups and the optional read-profile selector stay
    # omitted in the unconfigured template. Null groups fail validation;
    # an omitted executive_mcp_profile preserves the legacy generation.
    installed_product_keys = {
        "executive_mcp_profile",
        "content_observer",
        "content_observer_profile_path",
        "workspace_acquisition",
        "workspace_resource_policy",
        "workspace_control_room",
    }
    assert installed_product_keys <= _CONFIG_OPTIONAL
    assert set(value) == _CONFIG_REQUIRED | (_CONFIG_OPTIONAL - installed_product_keys)


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


def _relay_membership_snapshot() -> dict:
    snapshot = copy.deepcopy(_membership_snapshot())
    snapshot["users"]["_mastermind_agent_relay"] = {
        "primary_gid": 457,
        "unique_uid": 457,
        "generated_uid": "00000000-0000-4000-8000-000000000007",
    }
    snapshot["groups"]["_mastermind_agent_relay"] = {
        "primary_gid": 457,
        "generated_uid": "00000000-0000-4000-8000-000000000008",
        "name_members": ("_mastermind_exec",),
        "uuid_members": ("00000000-0000-4000-8000-000000000001",),
        "nested_groups": (),
    }
    snapshot["group_primary_gids"]["_mastermind_agent_relay"] = 457
    return snapshot


def _validate_relay_membership(snapshot: dict) -> None:
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
        agent_relay_present=True,
    )


def test_acceptance_protected_membership_accepts_exact_agent_relay_shape() -> None:
    _validate_relay_membership(_relay_membership_snapshot())


def test_acceptance_protected_membership_rejects_agent_relay_member_drift() -> None:
    import pytest

    snapshot = _relay_membership_snapshot()
    snapshot["groups"]["_mastermind_agent_relay"]["name_members"] = ()
    with pytest.raises(RuntimeError, match="named members drifted"):
        _validate_relay_membership(snapshot)


def test_acceptance_protected_membership_rejects_agent_relay_uuid_drift() -> None:
    import pytest

    snapshot = _relay_membership_snapshot()
    snapshot["groups"]["_mastermind_agent_relay"]["uuid_members"] = (
        "00000000-0000-4000-8000-000000000099",
    )
    with pytest.raises(RuntimeError, match="UUID-only or stale"):
        _validate_relay_membership(snapshot)


def test_acceptance_protected_membership_rejects_agent_relay_uid_or_gid_alias() -> None:
    import pytest

    uid_alias = _relay_membership_snapshot()
    uid_alias["users"]["relay-alias"] = {"primary_gid": 20, "unique_uid": 457}
    with pytest.raises(RuntimeError, match="duplicate or aliased owners"):
        _validate_relay_membership(uid_alias)

    gid_alias = _relay_membership_snapshot()
    gid_alias["group_primary_gids"]["relay-alias"] = 457
    with pytest.raises(RuntimeError, match="duplicate or aliased owners"):
        _validate_relay_membership(gid_alias)


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
    source_policy = (OPS / "install_source_policy.py").read_text(encoding="utf-8")
    acceptance = (OPS / "acceptance.py").read_text(encoding="utf-8")

    assert '["/usr/bin/git", "--no-optional-locks", "-C", str(repo), *args]' in source_policy
    assert '"status",\n        "--porcelain=v1",\n        "--untracked-files=normal",' in source_policy
    assert "--refresh" not in source_policy
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


def test_acceptance_allows_a_bounded_worker_broker_startup_window() -> None:
    # Renamed: the worker no longer has a cold codesign/--version
    # attestation path at startup (control_plane.codex_worker.
    # load_codex_attestation_receipt replaced it -- see
    # tests/test_executive_codex_attestation_receipt.py), so a bound this
    # generous is no longer justified by *that* cost specifically. It is
    # kept as a general allowance for the broker's other real startup work
    # (the UID sweep, socket activation, interpreter start) on a cold,
    # possibly host-loaded start. LowPriorityIO=true disk I/O throttling --
    # once inherited by this same startup path -- was removed from both
    # Executive launchd plists (see
    # test_executive_daemons_do_not_throttle_disk_io above); this test only
    # pins that the bound still exists and has not silently shrunk.
    acceptance = (OPS / "acceptance.py").read_text(encoding="utf-8")

    assert "WorkerBrokerClient(sys.argv[1],timeout_seconds=90.0)" in acceptance
    assert 'timeout=120.0,\n            label="worker broker status"' in acceptance


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


def test_bootstrap_waits_boundedly_for_disabled_authentication_propagation(
    tmp_path: Path,
) -> None:
    source = (OPS / "bootstrap-host.sh").read_text(encoding="utf-8")
    function_body = source.split(
        "wait_for_authentication_disabled() {", 1
    )[1].split("\n}", 1)[0]
    sleep_body = source.split(
        "sleep_for_authentication_propagation() {", 1
    )[1].split("\n}", 1)[0]
    ensure_body = source.split("ensure_authentication_disabled() {", 1)[1].split(
        "\n}", 1
    )[0]
    assert "for attempt in 1 2 3 4 5" in function_body
    assert "sleep_for_authentication_propagation" in function_body
    assert sleep_body.strip() == "/bin/sleep 1"
    assert "did not reach authentication-disabled state" in function_body
    assert "/usr/bin/pwpolicy" not in function_body
    assert ensure_body.count("/usr/bin/pwpolicy") == 1
    assert ensure_body.index('if [ "$state" = needs_disable ]; then') < ensure_body.index(
        "/usr/bin/pwpolicy"
    ) < ensure_body.index('wait_for_authentication_disabled "$name"')

    def run_wait(case_name: str, states: tuple[str, ...]):
        case_root = tmp_path / case_name
        case_root.mkdir()
        state_file = case_root / "states"
        probe_counter = case_root / "probes"
        sleep_counter = case_root / "sleeps"
        state_file.write_text("".join(f"{state}\n" for state in states), encoding="utf-8")
        probe_counter.write_text("0\n", encoding="utf-8")
        sleep_counter.write_text("0\n", encoding="utf-8")
        script = "\n".join(
            (
                "set -euo pipefail",
                "assert_reviewed_authentication_authority() { :; }",
                "authentication_state() {",
                '  observed="$(/bin/cat "$PROBE_COUNTER")"',
                "  observed=$((observed + 1))",
                "  /usr/bin/printf '%s\\n' \"$observed\" >\"$PROBE_COUNTER\"",
                '  state="$(/usr/bin/sed -n "${observed}p" "$PROBE_STATES")"',
                '  [ -n "$state" ] || return 65',
                '  [ "$state" != error ] || return 65',
                '  /bin/echo "$state"',
                "}",
                "sleep_for_authentication_propagation() {",
                '  observed="$(/bin/cat "$SLEEP_COUNTER")"',
                "  observed=$((observed + 1))",
                "  /usr/bin/printf '%s\\n' \"$observed\" >\"$SLEEP_COUNTER\"",
                "}",
                "wait_for_authentication_disabled() {",
                function_body,
                "}",
                "wait_for_authentication_disabled _synthetic_service",
            )
        )
        completed = subprocess.run(
            ["/bin/bash", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PROBE_COUNTER": str(probe_counter),
                "PROBE_STATES": str(state_file),
                "SLEEP_COUNTER": str(sleep_counter),
            },
        )
        return (
            completed,
            int(probe_counter.read_text(encoding="utf-8")),
            int(sleep_counter.read_text(encoding="utf-8")),
        )

    completed, probes, sleeps = run_wait("eventual", ("needs_disable", "disabled"))
    assert completed.returncode == 0, completed.stderr
    assert (probes, sleeps) == (2, 1)

    completed, probes, sleeps = run_wait("already", ("disabled",))
    assert completed.returncode == 0, completed.stderr
    assert (probes, sleeps) == (1, 0)

    completed, probes, sleeps = run_wait("exhausted", ("needs_disable",) * 5)
    assert completed.returncode == 65
    assert (probes, sleeps) == (5, 4)
    assert "did not reach authentication-disabled state" in completed.stderr

    for case_name, state in (("unexpected", "unexpected"), ("error", "error")):
        completed, probes, sleeps = run_wait(case_name, (state,))
        assert completed.returncode == 65
        assert (probes, sleeps) == (1, 0)


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


def test_bootstrap_provisions_exact_personal_pro_worker_realms_without_activation() -> None:
    source = (OPS / "bootstrap-host.sh").read_text(encoding="utf-8")

    assert 'PROVIDER_SLOT_RESOLVER="$SCRIPT_DIR/provider_worker_slots.py"' in source
    assert 'PERSONAL_PRO_SLOT_IDS=("codex-pro-01" "codex-pro-02" "codex-pro-03")' in source
    assert '"$SYSTEM_PYTHON" -I -S -B "$PROVIDER_SLOT_RESOLVER"' in source
    assert 'for slot_id in "${PERSONAL_PRO_SLOT_IDS[@]}"; do' in source
    for field in (
        "worker_user",
        "worker_group",
        "worker_uid",
        "worker_gid",
        "provider_home",
    ):
        assert f'slot_field "$slot_id" {field}' in source
    assert 'ensure_group "$slot_group" "$slot_gid"' in source
    assert 'ensure_user "$slot_user" "$slot_uid" "$slot_gid" "$slot_home"' in source
    assert '-a "$CONTROL_USER" -t user "$slot_group"' not in source
    assert 'assert_exact_members "$slot_group" "$slot_gid" "$slot_user" ""' in source
    assert '-o "$slot_user" -g "$slot_group" -m 0700 "$slot_home"' in source
    assert '-o "$slot_user" -g "$slot_group" -m 0700 "$slot_root/state"' in source
    assert "launchctl" not in source
    assert "service-control.sh" not in source
    assert "/bin/cp" not in source and "/usr/bin/cp" not in source


def test_personal_pro_groups_do_not_widen_existing_control_group_vector() -> None:
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
    with pytest.raises(AcceptanceError, match="control account"):
        _validate_service_directory_group_sets(
            system_group_gids=system,
            control_groups=[450, 451, 454, 12, 61, 100],
            worker_groups=[451, 12, 61, 100],
            control_gid=450,
            worker_gid=451,
        )

    source = (OPS / "bootstrap-host.sh").read_text(encoding="utf-8")
    assert '-a "$CONTROL_USER" -t user "$slot_group"' not in source
    assert 'assert_exact_members "$slot_group" "$slot_gid" "$slot_user" ""' in source


def test_personal_pro_bootstrap_identity_values_remain_catalog_owned() -> None:
    source = (OPS / "bootstrap-host.sh").read_text(encoding="utf-8")

    for private_identity_literal in (
        "_mastermind_codex_01",
        "_mastermind_codex_02",
        "_mastermind_codex_03",
    ):
        assert private_identity_literal not in source
    assert 'slot_field "$slot_id" worker_uid' in source
    assert 'slot_field "$slot_id" worker_gid' in source


def test_host_word_sorting_avoids_bsd_awk_index_builtin() -> None:
    for name in ("bootstrap-host.sh", "install.sh"):
        source = (OPS / name).read_text(encoding="utf-8")
        assert "for (index=" not in source
        assert "for (field_number=1; field_number<=NF; field_number++)" in source


def test_acceptance_service_group_vector_allows_only_exact_reviewed_agent_relay_gid() -> None:
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
    with pytest.raises(AcceptanceError, match="control account"):
        _validate_service_directory_group_sets(
            system_group_gids=system,
            control_groups=[450, 451, 457, 12, 61, 100],
            worker_groups=[451, 12, 61, 100],
            control_gid=450,
            worker_gid=451,
        )
    assert _validate_service_directory_group_sets(
        system_group_gids=system,
        control_groups=[450, 451, 457, 12, 61, 100],
        worker_groups=[451, 12, 61, 100],
        control_gid=450,
        worker_gid=451,
        agent_relay_gid=457,
    ) == {451, 12, 61, 100}
    with pytest.raises(AcceptanceError, match="agent relay group identity"):
        _validate_service_directory_group_sets(
            system_group_gids=system,
            control_groups=[450, 451, 999, 12, 61, 100],
            worker_groups=[451, 12, 61, 100],
            control_gid=450,
            worker_gid=451,
            agent_relay_gid=999,
        )
    with pytest.raises(AcceptanceError, match="control account"):
        _validate_service_directory_group_sets(
            system_group_gids=system,
            control_groups=[450, 451, 457, 999, 12, 61, 100],
            worker_groups=[451, 12, 61, 100],
            control_gid=450,
            worker_gid=451,
            agent_relay_gid=457,
        )


def test_acceptance_agent_relay_constants_match_reviewed_a2_host_contract() -> None:
    import ops.executive_os.acceptance as acceptance

    assert acceptance.AGENT_RELAY_USER == "_mastermind_agent_relay"
    assert acceptance.AGENT_RELAY_GROUP == "_mastermind_agent_relay"
    assert acceptance.AGENT_RELAY_UID == 457
    assert acceptance.AGENT_RELAY_GID == 457
    assert str(acceptance.AGENT_RELAY_HOME) == "/var/db/mastermind-agent-relay/home"

    host_source = (OPS / "prepare-a2-agent-relay-host.sh").read_text(encoding="utf-8")
    for literal in (
        'RELAY_USER="_mastermind_agent_relay"',
        'RELAY_GROUP="_mastermind_agent_relay"',
        'RELAY_UID="457"',
        'RELAY_GID="457"',
        'EXEC_USER="_mastermind_exec"',
    ):
        assert literal in host_source


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
            "schema_version": "mastermind.executive_uid_sweep/v2",
            "observed_at": "2026-08-11T00:00:01+00:00",
            "reason": "run_terminal",
            "worker_uid": 451,
            "broker_pid": 42419,
            "residual_pids_before": [],
            "residual_pids_after": [],
            "signal_name": "SIGKILL",
            "signal_sent": False,
            "quiescent_observations": 2,
            "ambient_pids": [],
            "ambient_identities": [],
            "ambient_attribution": "absent",
            "passed": True,
            "found_residuals": False,
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
    # Normal Executive daemons stay inert. The only bootstrap is the explicitly
    # armed privileged broker, after exact-release verification.
    assert '/bin/launchctl bootstrap system "$CONTROL_PLIST"' not in tail_after_plists
    assert '/bin/launchctl bootstrap system "$WORKER_PLIST"' not in tail_after_plists
    assert '/bin/launchctl bootstrap system "$BACKUP_PLIST"' not in tail_after_plists
    assert tail_after_plists.count('/bin/launchctl bootstrap') == 1
    arm = tail_after_plists.index('if [ "$ARM_PRIVILEGED_BROKER" = "1" ]; then')
    bootstrap = tail_after_plists.index('/bin/launchctl bootstrap system "$PRIVILEGED_PLIST"')
    manifest_verify = tail_after_plists.rindex('release_manifest.py" verify', 0, arm)
    assert manifest_verify < arm < bootstrap


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS plutil installer rendering')
def test_installer_renders_every_control_socket_path(tmp_path):
    """Exercise the installer's real socket substitutions without root or launchd."""
    import shlex

    destination = tmp_path / 'control.plist'
    destination.write_bytes(CONTROL.read_bytes())
    replacements = {
        '$CONTROL_PLIST': str(destination),
        '$CONTROL_UID': '450',
        '$OPS_GID': '453',
    }
    for line in (OPS / 'install.sh').read_text().splitlines():
        if (line.startswith('/usr/bin/plutil -replace Sockets.')
                and line.endswith('"$CONTROL_PLIST"')):
            argv = [replacements.get(part, part) for part in shlex.split(line)]
            subprocess.run(argv, check=True, capture_output=True, text=True)

    sockets = plistlib.loads(destination.read_bytes())['Sockets']
    assert sockets['CeoIngress'] == {
        'SockPathName': '/var/run/mastermind-executive/ceo-ingress.sock',
        'SockType': 'stream', 'SockPassive': True,
        'SockPathOwner': 450, 'SockPathGroup': 452, 'SockPathMode': 0o660,
    }
    assert all(Path(row['SockPathName']).is_absolute() for row in sockets.values())
    assert all('__' not in row['SockPathName'] for row in sockets.values())
def test_privileged_broker_launchd_template_is_root_socket_activated_and_closed() -> None:
    path = OPS / "com.mastermind.executive.privileged.plist.template"
    value = _plist(path)
    assert value["Label"] == "com.mastermind.executive.privileged"
    assert value["UserName"] == "root"
    assert value["GroupName"] == "wheel"
    assert "RunAtLoad" not in value
    assert "KeepAlive" not in value
    assert value["ProcessType"] == "Background"
    assert value["Umask"] == 0o77
    assert value["ProgramArguments"] == [
        "__PYTHON_BINARY__",
        "-I",
        "-S",
        "-B",
        "__PRIVILEGED_ENTRYPOINT__",
        "serve",
        "--config",
        "__PRIVILEGED_CONFIG__",
    ]
    assert not any(
        item in {"/bin/sh", "/bin/bash", "/usr/bin/env"}
        for item in value["ProgramArguments"]
    )
    assert set(value["Sockets"]) == {"PrivilegedActions"}
    _assert_private_unix_socket(value["Sockets"]["PrivilegedActions"], mode=0o660)
    assert value["Sockets"]["PrivilegedActions"]["SockPathOwner"] == 450
    assert value["Sockets"]["PrivilegedActions"]["SockPathGroup"] == 453
    assert set(value["EnvironmentVariables"]) == {
        "HOME", "LANG", "LC_ALL", "NO_COLOR", "PATH", "PYTHONUNBUFFERED", "TZ"
    }
    assert not any(
        token in key.upper()
        for key in value["EnvironmentVariables"]
        for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    )


def test_installer_privileged_broker_is_explicitly_armed_and_never_edits_sudoers() -> None:
    text = (OPS / "install.sh").read_text(encoding="utf-8")
    assert 'PRIVILEGED_LABEL="com.mastermind.executive.privileged"' in text
    assert 'ARM_PRIVILEGED_BROKER="0"' in text
    assert '--arm-privileged-broker) ARM_PRIVILEGED_BROKER="1"; shift ;;' in text
    assert 'PRIVILEGED_CONFIG="$SYSTEM_ROOT/config/privileged-broker.json"' in text
    assert 'PRIVILEGED_RECEIPT_ROOT="$RUNTIME_ROOT/privileged-actions/receipts"' in text
    assert 'PRIVILEGED_SOCKET="/var/run/mastermind-executive/privileged.sock"' in text
    assert '/etc/sudoers' not in text
    assert 'NOPASSWD' not in text
    arm = text.index('if [ "$ARM_PRIVILEGED_BROKER" = "1" ]; then')
    enable = text.index('/bin/launchctl enable "system/$PRIVILEGED_LABEL"', arm)
    bootstrap = text.index('/bin/launchctl bootstrap system "$PRIVILEGED_PLIST"', enable)
    live = text.index('PRIVILEGED_BROKER_LIVE="1"', bootstrap)
    assert arm < enable < bootstrap < live
    assert '/usr/bin/stat -f' in text[live - 1800 : live]


def test_failed_privileged_arm_cleanup_proves_the_root_daemon_is_absent() -> None:
    text = (OPS / "install.sh").read_text(encoding="utf-8")
    start = text.index("leave_installed_services_stopped() {")
    end = text.index("trap leave_installed_services_stopped EXIT", start)
    cleanup = text[start:end]
    assert 'if /bin/launchctl print "system/$PRIVILEGED_LABEL" >/dev/null 2>&1; then' in cleanup
    assert "privileged LaunchDaemon remained loaded after cleanup" in cleanup


def test_privileged_broker_budget_exceeds_provider_inference_canary_budget() -> None:
    install = (OPS / "install.sh").read_text(encoding="utf-8")
    canary = (OPS / "provider_inference_canary.py").read_text(encoding="utf-8")
    assert '"timeout_seconds": 600' in install
    assert 'timeout_seconds: float = 180.0' in canary


def test_privileged_client_and_broker_entrypoints_are_in_release_manifest_surface() -> None:
    install = (OPS / "install.sh").read_text(encoding="utf-8")
    for relative in (
        "scripts/executive_os_privileged_broker.py",
        "scripts/mmx_admin.py",
        "control_plane/executive_privileged_action.py",
        "control_plane/executive_privileged_broker.py",
    ):
        assert relative in install or "release_manifest.py" in install


def test_privileged_broker_cli_rejects_unknown_command_without_traceback(tmp_path: Path) -> None:
    target = ROOT / "scripts" / "executive_os_privileged_broker.py"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(target),
            "--definitely-not-a-real-subcommand",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "arguments are required: command" in result.stderr
    assert "Traceback" not in result.stderr


# === W1H3F R13: wrapper-owned live-attestation validator (Sol R80, PR #677) ===
#
# The wrapper writes the document; the same wrapper now owns the validator
# that H3 consumes.  ``ATTESTATION_FIELDS`` and ``PROCESS_IDENTITY_FIELDS``
# are the closed field sets the wrapper writes and that the validator
# enforces; ``SCHEMA_VERSION`` is the wrapper's own constant.  H3 must NOT
# restate any of them.

from dataclasses import dataclass


@dataclass(frozen=True)
class _FakeIdentity:
    pgid: int
    session_id: int
    start_identity: str
    effective_uid: int
    effective_gid: int
    real_uid: int
    real_gid: int


class _FakeProcessInspector:
    """Stand-in for ``control_plane.codex_worker.ProcessInspector``.

    The validator's only injection point; tests pin the live observation
    (``boot_session_id`` and ``inspect(pid)``) so the fresh-observation
    refusal path is deterministic on Linux.
    """

    def __init__(self, *, boot_id: str = "boot-aaaa", identity: _FakeIdentity | None = None):
        self.boot_id = boot_id
        self.identity = identity or _FakeIdentity(
            pgid=4242,
            session_id=4242,
            start_identity="1723500000.000000",
            effective_uid=501,
            effective_gid=20,
            real_uid=501,
            real_gid=20,
        )
        self.calls: list[int] = []

    def boot_session_id(self) -> str:
        return self.boot_id

    def inspect(self, pid: int) -> _FakeIdentity:
        self.calls.append(pid)
        return self.identity


_EXPECTED_CONFIG_SHA = "a" * 64
_EXPECTED_RELEASE_SHA = "b" * 40
_EXPECTED_PID = 4242


def _good_document() -> dict[str, object]:
    """A document the validator accepts, byte-for-byte what the producer writes."""

    return {
        "schema_version": "mastermind.executive_control_environment_attestation/v1",
        "observed_at": "2026-09-16T12:00:00+00:00",
        "process_identity": {
            "pid": _EXPECTED_PID,
            "pgid": 4242,
            "session_id": 4242,
            "start_identity": "1723500000.000000",
            "boot_id": "boot-aaaa",
            "effective_uid": 501,
            "effective_gid": 20,
            "real_uid": 501,
            "real_gid": 20,
        },
        "config_sha256": _EXPECTED_CONFIG_SHA,
        "release_manifest_sha256": "c" * 64,
        "release_commit_sha": _EXPECTED_RELEASE_SHA,
        "python_executable_path": "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "python_executable_sha256": "d" * 64,
        "sentinel_name_sha256": "e" * 64,
        "sentinel_value_sha256": "f" * 64,
        "sentinel_present": True,
    }


def test_attestation_validator_accepts_the_producers_own_output():
    """D10 (positive, wrapper-self-validation): the wrapper writes what it validates."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    inspector = _FakeProcessInspector()
    document = _good_document()

    assert (
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=inspector,
        )
        == document
    )
    # The validator really did consult the inspector (fresh-observation).
    assert inspector.calls == [_EXPECTED_PID]


def test_attestation_validator_refuses_a_stale_attested_config_digest():
    """D1: config_sha256 in the document does not match the disk digest."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    document["config_sha256"] = "9" * 64

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


def test_attestation_validator_refuses_a_stale_attested_release_sha():
    """D2: release_commit_sha in the document does not match the installed SHA."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    document["release_commit_sha"] = "z" * 40

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


def test_attestation_validator_refuses_a_stale_start_identity_with_the_same_pid():
    """D3a: same PID, different start_identity -> fresh observation refuses."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    # Pin a stale start_identity the LIVE process no longer carries.
    document["process_identity"]["start_identity"] = "1723499999.999999"
    inspector = _FakeProcessInspector()

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=inspector,
        )


def test_attestation_validator_refuses_a_stale_boot_identity_with_the_same_pid():
    """D3b: same PID, different boot_id -> fresh observation refuses."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    document["process_identity"]["boot_id"] = "boot-stale-bbbb"
    inspector = _FakeProcessInspector(boot_id="boot-live-cccc")

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=inspector,
        )


def test_attestation_validator_refuses_a_status_pid_that_differs_from_the_attested_pid():
    """D4a: status ``pid`` != document ``pid`` refuses."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID + 1,
            inspector=_FakeProcessInspector(),
        )


@pytest.mark.parametrize("bad_pid", [True, False, "4242", 1.5, None, 0, -1, 2**31])
def test_attestation_validator_refuses_a_non_int_or_out_of_range_pid(bad_pid):
    """D4b: non-int / bool / out-of-range status PID refuses."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=bad_pid,  # type: ignore[arg-type]
            inspector=_FakeProcessInspector(),
        )


def test_attestation_validator_refuses_malformed_top_level_fields():
    """D6a: extra / missing / renamed top-level fields refuse."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    base = _good_document()

    # Missing field
    missing = {k: v for k, v in base.items() if k != "sentinel_present"}
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            missing,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )

    # Extra field
    extra = dict(base)
    extra["extra_top"] = "nope"
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            extra,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )

    # Renamed field
    renamed = dict(base)
    renamed["schemaVersion"] = renamed.pop("schema_version")
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            renamed,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )

    # Wrong schema_version
    wrong_schema = dict(base)
    wrong_schema["schema_version"] = "wrong"
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            wrong_schema,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


def test_attestation_validator_refuses_non_utc_or_unparseable_observed_at():
    """D6b: observed_at must be an ISO-8601 UTC string."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    base = _good_document()

    for bad in ("2026-09-16 12:00:00", "not-a-date", "", "2026-09-16T12:00:00"):
        document = dict(base)
        document["observed_at"] = bad
        with pytest.raises(wrapper.ControlWrapperError):
            wrapper.validate_control_environment_attestation(
                document,
                expected_config_sha256=_EXPECTED_CONFIG_SHA,
                expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
                expected_pid=_EXPECTED_PID,
                inspector=_FakeProcessInspector(),
            )


def test_attestation_validator_refuses_malformed_process_identity_fields():
    """D6c: extra / missing / renamed process_identity fields refuse."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    base = _good_document()

    # Missing
    missing = dict(base)
    missing["process_identity"] = {k: v for k, v in base["process_identity"].items() if k != "boot_id"}
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            missing,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )

    # Extra
    extra = dict(base)
    extra["process_identity"] = dict(base["process_identity"], extra_field="x")
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            extra,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )

    # Renamed
    renamed = dict(base)
    inner = dict(base["process_identity"])
    inner["process_id"] = inner.pop("pid")
    renamed["process_identity"] = inner
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            renamed,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


def test_attestation_validator_refuses_sentinel_present_when_not_exactly_true():
    """D6d: ``sentinel_present`` must be the literal ``True``."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    base = _good_document()
    for bad in (1, "true", 1.0, None, False):
        document = dict(base)
        document["sentinel_present"] = bad
        with pytest.raises(wrapper.ControlWrapperError):
            wrapper.validate_control_environment_attestation(
                document,
                expected_config_sha256=_EXPECTED_CONFIG_SHA,
                expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
                expected_pid=_EXPECTED_PID,
                inspector=_FakeProcessInspector(),
            )


def test_attestation_validator_refuses_non_dict_documents():
    """D6e: the validator refuses non-dict, list, int, None, str inputs."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    for bad in ([], "string", 1, 1.5, None):
        with pytest.raises(wrapper.ControlWrapperError):
            wrapper.validate_control_environment_attestation(
                bad,
                expected_config_sha256=_EXPECTED_CONFIG_SHA,
                expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
                expected_pid=_EXPECTED_PID,
                inspector=_FakeProcessInspector(),
            )


def test_attestation_validator_is_import_safe_and_pure():
    """Importing the wrapper does not execve / fork / touch the FS."""

    import importlib

    import scripts.executive_os_phase1c_control_wrapper as wrapper_module

    module = importlib.reload(wrapper_module)
    assert module.validate_control_environment_attestation.__module__ == (
        "scripts.executive_os_phase1c_control_wrapper"
    )
    # Validator signature is pure: only the document, expected digests, expected
    # PID, and inspector are parameters; no filesystem, no execve.
    import inspect

    signature = inspect.signature(module.validate_control_environment_attestation)
    assert set(signature.parameters) == {
        "document",
        "expected_config_sha256",
        "expected_release_commit_sha",
        "expected_pid",
        "inspector",
    }
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )


def test_attestation_validator_is_owned_only_by_the_wrapper_module():
    """H3 must NOT restate the closed field sets; they live in the wrapper."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    assert isinstance(wrapper.ATTESTATION_FIELDS, frozenset)
    assert isinstance(wrapper.PROCESS_IDENTITY_FIELDS, frozenset)
    assert (
        wrapper.ATTESTATION_FIELDS
        == frozenset(
            {
                "schema_version",
                "observed_at",
                "process_identity",
                "config_sha256",
                "release_manifest_sha256",
                "release_commit_sha",
                "python_executable_path",
                "python_executable_sha256",
                "sentinel_name_sha256",
                "sentinel_value_sha256",
                "sentinel_present",
            }
        )
    )
    assert wrapper.PROCESS_IDENTITY_FIELDS == frozenset(
        {
            "pid",
            "pgid",
            "session_id",
            "start_identity",
            "boot_id",
            "effective_uid",
            "effective_gid",
            "real_uid",
            "real_gid",
        }
    )


def test_attestation_validator_treats_inspector_exceptions_as_refusals():
    """The fresh-observation call is the ONLY injection point; an exception refuses."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    class _BoomInspector(_FakeProcessInspector):
        def inspect(self, pid):  # type: ignore[override]
            raise RuntimeError("inspector failure")

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            _good_document(),
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_BoomInspector(),
        )


def _producer_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Config / release / attestation triple the real producer accepts."""

    release = tmp_path / "release"
    release.mkdir()
    (release / ".executive-release-manifest.json").write_text(
        json.dumps({"commit_sha": _EXPECTED_RELEASE_SHA}), encoding="utf-8"
    )
    config = tmp_path / "control.json"
    config.write_text(json.dumps({"control_uid": os.geteuid()}), encoding="utf-8")
    tmp_path.chmod(0o700)
    return config, release, tmp_path / "attestation.json"


def test_producer_refuses_to_write_a_document_its_own_validator_rejects(
    monkeypatch, tmp_path
) -> None:
    """Sol R80 item 2 (WRITER side): ``attest_current_service_environment`` validates
    the document it constructs THROUGH the wrapper-owned validator BEFORE the atomic
    write, and a document that fails that validator is NEVER written.

    This is the discriminator for the producer. ``..._accepts_the_producers_own_output``
    validates a SYNTHETIC document, so it stays green even when the producer never calls
    the validator at all -- bypassing the call is a mutation that must turn THIS test red.
    """

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    config, release, target = _producer_fixture(tmp_path)
    inspector = _FakeProcessInspector()
    monkeypatch.setattr(wrapper, "ProcessInspector", lambda: inspector)

    seen: list[dict[str, object]] = []

    def refusing(document, **kwargs):
        seen.append({"document": document, **kwargs})
        raise wrapper.ControlWrapperError("fixture refusal")

    monkeypatch.setattr(wrapper, "validate_control_environment_attestation", refusing)

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.attest_current_service_environment(
            config_path=config,
            attestation_path=target,
            release=release,
            sentinel="c" * 64,
        )

    # The producer consulted the ONE wrapper-owned validator, with explicit expected
    # facts taken from current evidence -- not from the document it just built.
    assert len(seen) == 1
    assert seen[0]["expected_pid"] == os.getpid()
    assert seen[0]["expected_release_commit_sha"] == _EXPECTED_RELEASE_SHA
    assert seen[0]["expected_config_sha256"] == wrapper._sha256(config)
    assert seen[0]["inspector"] is inspector
    # ...and nothing reached disk.
    assert not target.exists()


def test_producer_output_is_written_only_after_it_passes_the_real_validator(
    monkeypatch, tmp_path
) -> None:
    """Sol R80 discriminator: the wrapper producer's OWN output passes its OWN validator.

    Unlike the synthetic-document positive, this drives the real writer end to end and
    then re-validates the bytes that actually landed on disk.
    """

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    config, release, target = _producer_fixture(tmp_path)
    inspector = _FakeProcessInspector()
    monkeypatch.setattr(wrapper, "ProcessInspector", lambda: inspector)

    returned = wrapper.attest_current_service_environment(
        config_path=config,
        attestation_path=target,
        release=release,
        sentinel="c" * 64,
    )

    assert target.exists()
    assert stat.S_IMODE(target.lstat().st_mode) == 0o400
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == returned
    assert set(written) == wrapper.ATTESTATION_FIELDS
    assert written["config_sha256"] == wrapper._sha256(config)
    assert written["release_commit_sha"] == _EXPECTED_RELEASE_SHA
    assert written["process_identity"]["pid"] == os.getpid()

    # The bytes on disk validate under the same closed rules, with the same observation.
    assert (
        wrapper.validate_control_environment_attestation(
            written,
            expected_config_sha256=wrapper._sha256(config),
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=os.getpid(),
            inspector=inspector,
        )
        == written
    )


# R13 blocking finding (W1H3F): every fact the validator re-observes through the
# injected ProcessInspector is an authority check, so every one of them needs its
# OWN stale-value discriminator. Before this, only ``start_identity`` and ``boot_id``
# had one, and deleting any of the other six comparisons left both owning suites green.
_FRESH_OBSERVATION_FACTS = frozenset(
    {
        "pgid",
        "session_id",
        "start_identity",
        "boot_id",
        "effective_uid",
        "effective_gid",
        "real_uid",
        "real_gid",
    }
)


def test_every_process_identity_fact_has_a_stale_observation_discriminator() -> None:
    """Structural guard: the parameterization below must cover the whole closed set.

    ``pid`` is excluded because it is bound by ``expected_pid`` and has its own
    dedicated tests. If a tenth identity fact is ever added to the wrapper's closed
    set, this test fails until a stale-observation discriminator exists for it.
    """

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    assert set(wrapper.PROCESS_IDENTITY_FIELDS) == _FRESH_OBSERVATION_FACTS | {"pid"}


@pytest.mark.parametrize("fact", sorted(_FRESH_OBSERVATION_FACTS))
def test_attestation_validator_refuses_each_stale_fresh_observation_fact(fact: str) -> None:
    """Sol R80 item 4: the attested identity must equal the FRESHLY OBSERVED identity.

    One case per fact, so each individual comparison is load-bearing: removing any
    single fact from the validator's fresh-observation comparison turns exactly this
    test red for that fact instead of leaving the suites green.
    """

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    live = document["process_identity"][fact]
    document["process_identity"][fact] = (
        live + 1 if isinstance(live, int) and not isinstance(live, bool) else f"{live}-stale"
    )

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("pgid", 4242.0),
        ("session_id", 4242.0),
        ("effective_uid", 501.0),
        ("effective_gid", 20.0),
        ("real_uid", 501.0),
        ("real_gid", 20.0),
        ("pgid", True),
        ("effective_uid", -1),
    ],
)
def test_attestation_validator_refuses_non_exact_identity_integer_types(
    field, bad_value
):
    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    document["process_identity"][field] = bad_value
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


def test_attestation_validator_refuses_unicode_control_in_matching_identity_text():
    """B2: fresh matching identity text still refuses Unicode Cc controls."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    unsafe_identity = "1723500000.\u0085"
    document = _good_document()
    document["process_identity"]["start_identity"] = unsafe_identity
    inspector = _FakeProcessInspector(
        identity=_FakeIdentity(
            pgid=4242,
            session_id=4242,
            start_identity=unsafe_identity,
            effective_uid=501,
            effective_gid=20,
            real_uid=501,
            real_gid=20,
        )
    )

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=inspector,
        )


def test_attestation_validator_refuses_unicode_control_in_executable_path():
    """B2: a canonical-looking absolute path refuses Unicode Cc controls."""

    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    document["python_executable_path"] = "/tmp/python\u0085bin"

    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("start_identity", ""),
        ("start_identity", "value\nsecond"),
        ("boot_id", "value\x00suffix"),
        ("boot_id", "x" * 257),
        ("boot_id", 7),
    ],
)
def test_attestation_validator_refuses_unsafe_identity_text(field, bad_value):
    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    document["process_identity"][field] = bad_value
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/\x00bad",
        "/tmp/python\nother",
        "/tmp/../python",
        "/tmp//python",
        "//tmp/python",
        "relative/python",
    ],
)
def test_attestation_validator_refuses_noncanonical_executable_paths(bad_path):
    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    document["python_executable_path"] = bad_path
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=_EXPECTED_RELEASE_SHA,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


@pytest.mark.parametrize(
    "expected,document_value",
    [
        ("B" * 40, "b" * 40),
        ("b" * 39, "b" * 39),
        ("b" * 40, "B" * 40),
        ("b" * 40, "b" * 39),
    ],
)
def test_attestation_validator_requires_exact_lowercase_commit_identity(
    expected, document_value
):
    from scripts import executive_os_phase1c_control_wrapper as wrapper

    document = _good_document()
    document["release_commit_sha"] = document_value
    with pytest.raises(wrapper.ControlWrapperError):
        wrapper.validate_control_environment_attestation(
            document,
            expected_config_sha256=_EXPECTED_CONFIG_SHA,
            expected_release_commit_sha=expected,
            expected_pid=_EXPECTED_PID,
            inspector=_FakeProcessInspector(),
        )


# HF1-B uses the real loader and configuration-bound producer. Native process
# attestation remains the existing loader; tests inject only its observed result.
def _hf1b_control_fixture(tmp_path):
    import hashlib
    from test_executive_os_sqlite import _hf1b_claim_fixture
    from scripts import executive_os_phase1c as cli
    runtime, root, work, command, definition, observation = _hf1b_claim_fixture(tmp_path)
    raw = {
        "schema_version": cli.CONTROL_CONFIG_SCHEMA_VERSION,
        "runtime_root": str(runtime.store.root),
        "control_socket_path": str(tmp_path / "control.sock"),
        "launchd_socket_name": "Operator", "worker_broker_socket_path": str(tmp_path / "worker.sock"),
        "worker_provider_home": str(tmp_path / "worker-home"),
        "worker_runs_root": str(tmp_path / "runs"), "receipts_root": str(tmp_path / "receipts"),
        "proof_source_repository": str(tmp_path / "source"),
        "proof_workspace_root": str(tmp_path / "workspaces"), "proof_base_sha": "a" * 40,
        "backup_root": str(tmp_path / "backups"), "control_uid": os.geteuid(),
        "worker_uid": os.geteuid() + 10000, "worker_gid": os.getegid(),
        "worker_user": "fixture-worker", "shared_run_gid": os.getegid(),
        "allowed_peer_uids": [os.geteuid()],
        "secret_canary_receipt_path": str(tmp_path / "canary.json"),
        "control_environment_attestation_path": str(tmp_path / "attestation.json"),
        "worker_id": "worker-a", "worker_account_label": "hf1b-fixture-a",
        "quota_class": "default", "model": "gpt-5.6-sol", "effort": "xhigh", "cost_class": "small",
        "exact_worker_claim_target": {"mode": "fixed", "definition": definition, "max_age_ms": 30000},
    }
    path = tmp_path / "hf1b-control.json"
    data = json.dumps(raw, sort_keys=True).encode()
    path.write_bytes(data)
    path.chmod(0o600)
    # This result stands in for native process/release observation, not its test.
    attestation = {"config_sha256": hashlib.sha256(data).hexdigest(),
                   "process_identity": {"pid": 4242}, "release_commit_sha": "a" * 40}
    return cli, runtime, root, work, command, raw, path, attestation


def _hf1b_bind(cli, raw, path, attestation):
    binder = getattr(cli, "_bind_exact_worker_target_source", None)
    assert callable(binder), "HF1-B attested configuration producer is not implemented"
    return binder(raw, attestation, _producer_capability=cli._CONTROL_TARGET_COMPOSITION,
                  attestation_loader=lambda: dict(attestation))


def test_hf1b_template_target_is_explicitly_disabled():
    raw = json.loads((OPS / "control.json.template").read_text())
    assert raw.get("exact_worker_claim_target") == {"mode": "disabled"}


def test_hf1b_real_loader_snapshot_binds_first_claim(tmp_path):
    cli, runtime, _, work, command, _, path, attestation = _hf1b_control_fixture(tmp_path)
    loaded = cli.load_control_config(path)
    producer = _hf1b_bind(cli, loaded, path, attestation)
    target = producer.for_job(work.job_id, now_ms=runtime.store.now_ms())
    claim = runtime.attempts.dispatch_cycle_job(work.job_id, command_id=command, exact_target=target)
    assert claim.claimed_now and claim.attempt.worker_id == "worker-a"
    evidence = runtime.store.get_event_by_command_id(command).payload["exact_worker_target"]
    assert evidence["observation"]["source_sha256"] == attestation["config_sha256"]
    assert evidence["definition"]["job_id"] == work.job_id


def test_hf1b_plain_mapping_cannot_replace_loaded_source(tmp_path):
    cli, _, _, _, _, raw, path, attestation = _hf1b_control_fixture(tmp_path)
    _hf1b_bind_method = getattr(cli, "_bind_exact_worker_target_source", None)
    assert callable(_hf1b_bind_method), "HF1-B attested configuration producer is not implemented"
    with pytest.raises(cli.ServiceError, match="target"):
        _hf1b_bind(cli, raw, path, attestation)


@pytest.mark.parametrize("mutation", ["atomic_replace", "same_inode", "attestation", "raw_target", "raw_broker"])
def test_hf1b_consumed_snapshot_cannot_be_freshened_by_later_hash(tmp_path, mutation):
    import hashlib
    cli, _, _, _, _, raw, path, attestation = _hf1b_control_fixture(tmp_path)
    loaded = cli.load_control_config(path)
    if mutation in {"atomic_replace", "same_inode"}:
        raw["exact_worker_claim_target"]["definition"]["source_generation"] = "changed-generation"
        data = json.dumps(raw, sort_keys=True).encode()
        if mutation == "atomic_replace":
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(data)
            replacement.chmod(0o600)
            replacement.replace(path)
        else:
            path.write_bytes(data)
        # Attesting the NEW path must never authenticate the earlier object.
        attestation["config_sha256"] = hashlib.sha256(data).hexdigest()
    elif mutation == "attestation":
        attestation["config_sha256"] = "0" * 64
    elif mutation == "raw_target":
        loaded["exact_worker_claim_target"]["definition"]["source_generation"] = "caller-changed"
    else:
        loaded["worker_broker_socket_path"] = tmp_path / "different-worker.sock"
    with pytest.raises(cli.ServiceError, match="target"):
        _hf1b_bind(cli, loaded, path, attestation)


@pytest.mark.parametrize("bad", [None, {}, {"mode": "fixed"}, {"mode": "disabled", "fallback": "auto"},
                                 {"mode": "automatic"}])
def test_hf1b_malformed_target_config_does_not_enable_default_selection(tmp_path, bad):
    cli, _, _, _, _, raw, path, _ = _hf1b_control_fixture(tmp_path)
    raw["exact_worker_claim_target"] = bad
    path.write_text(json.dumps(raw))
    with pytest.raises(cli.ServiceError, match="target"):
        cli.load_control_config(path)


def test_hf1b_fixed_broker_worker_mismatch_refuses(tmp_path):
    cli, _, _, _, _, raw, path, attestation = _hf1b_control_fixture(tmp_path)
    raw["worker_id"] = "another-broker-worker"
    path.write_text(json.dumps(raw))
    with pytest.raises(cli.ServiceError, match="target"):
        cli.load_control_config(path)


def test_hf1b_source_changes_after_binding_refuse_fresh_issue(tmp_path):
    cli, runtime, _, work, _, _, path, attestation = _hf1b_control_fixture(tmp_path)
    loaded = cli.load_control_config(path)
    producer = _hf1b_bind(cli, loaded, path, attestation)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(cli.ServiceError, match="target"):
        producer.for_job(work.job_id, now_ms=runtime.store.now_ms())


def test_hf1b_foreign_job_does_not_fall_through_to_untargeted_mode(tmp_path):
    cli, runtime, _, _, _, _, path, attestation = _hf1b_control_fixture(tmp_path)
    producer = _hf1b_bind(cli, cli.load_control_config(path), path, attestation)
    with pytest.raises(cli.ServiceError, match="target"):
        producer.for_job("JOB-OTHER", now_ms=runtime.store.now_ms())


def test_hf1b_factory_requires_and_consumes_attested_producer(tmp_path, monkeypatch):
    cli, runtime, _, work, _, _, path, attestation = _hf1b_control_fixture(tmp_path)
    loaded = cli.load_control_config(path)
    with pytest.raises(cli.ServiceError, match="target"):
        cli._service_from_config(loaded)
    producer = _hf1b_bind(cli, loaded, path, attestation)
    captured = {}
    def capture_service(config, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(config=config)
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda name: object())
    monkeypatch.setattr(cli, "ExecutiveControlService", capture_service)
    cli._service_from_config(loaded, exact_target_source=producer)
    supervisor = captured["supervisor_factory"](runtime)
    selected = supervisor._exact_target_provider(work.job_id)
    assert selected.definition["worker_id"] == "worker-a"
    assert selected.observation["source_sha256"] == attestation["config_sha256"]
    assert supervisor.adapter is not None


def test_hf1b_absent_and_disabled_config_preserve_legacy_composition(tmp_path):
    cli, _, _, _, _, raw, path, _ = _hf1b_control_fixture(tmp_path)
    for optional in (None, {"mode": "disabled"}):
        if optional is None:
            raw.pop("exact_worker_claim_target", None)
        else:
            raw["exact_worker_claim_target"] = optional
        path.write_text(json.dumps(raw))
        loaded = cli.load_control_config(path)
        assert getattr(loaded, "_target_snapshot", None) is None



def test_hf1b_loaded_source_through_supervisor_returns_consumable_result(tmp_path):
    import asyncio
    from test_executive_supervisor import Hf1bResultAdapter, FakeInspector, _supervisor
    from control_plane.executive_runtime import JobStatus
    from control_plane.executive_coo_cycle import CooCycle
    cli, runtime, root, work, command, _, path, attestation = _hf1b_control_fixture(tmp_path)
    producer = _hf1b_bind(cli, cli.load_control_config(path), path, attestation)
    adapter = Hf1bResultAdapter(FakeInspector(), runtime, work)
    supervisor = _supervisor(runtime, tmp_path, adapter,
        exact_target_provider=lambda job_id: producer.for_job(job_id, now_ms=runtime.store.now_ms()))
    os.chown(adapter.provider_home, -1, os.getegid())
    async def exercise():
        active = await supervisor.start_cycle_job(work.job_id, command_id=command)
        adapter.inspector.live = False
        finished = await supervisor.finish_job(active)
        assert finished.job.status is JobStatus.COMPLETED
        replay = await supervisor.start_cycle_job(work.job_id, command_id=command)
        assert replay.outcome == "TERMINAL" and adapter.start_count == 1
        event = runtime.store.get_event_by_command_id(command)
        assert event.payload["exact_worker_target"]["observation"]["source_sha256"] == attestation["config_sha256"]
        assert CooCycle(runtime).run_once(root.job_id).action == "HANDOFF_CREATED"
    asyncio.run(exercise())


# Hot content profiles keep the fixed source path in the attested Control config
# while root may atomically replace only the canonical profile document.
def _disabled_content_profiles():
    return {
        "schema": "mastermind.executive_content_profiles.v1",
        "profiles": {
            "web": {"enabled": False, "profile": None},
            "mac": {"enabled": False, "profile": None},
        },
    }


def _write_content_profile(path: Path, value) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    path.chmod(0o440)


def _install_root_profile_metadata(monkeypatch, cli, profile_path: Path):
    """Present a temp file as the production UID0:GID 0440 object."""

    target = Path(profile_path)
    opened = set()
    flags = []
    metadata = {
        "uid": 0,
        "gid": os.getegid(),
        "mode": 0o440,
        "file_type": stat.S_IFREG,
        "nlink": 1,
    }
    real_open = cli.os.open
    real_fstat = cli.os.fstat
    real_lstat = cli.Path.lstat

    def secured(info):
        return SimpleNamespace(
            st_dev=info.st_dev,
            st_ino=info.st_ino,
            st_uid=metadata["uid"],
            st_gid=metadata["gid"],
            st_mode=metadata["file_type"] | metadata["mode"],
            st_nlink=metadata["nlink"],
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
            st_ctime_ns=info.st_ctime_ns,
        )

    def guarded_open(path, open_flags, *args, **kwargs):
        fd = real_open(path, open_flags, *args, **kwargs)
        if Path(path) == target:
            opened.add(fd)
            flags.append(open_flags)
        return fd

    def guarded_fstat(fd):
        info = real_fstat(fd)
        return secured(info) if fd in opened else info

    def guarded_lstat(path):
        info = real_lstat(path)
        return secured(info) if Path(path) == target else info

    monkeypatch.setattr(
        cli,
        "_sealed_content_profile_ancestors",
        lambda _path: (("/", (1, 1, 0, 0, stat.S_IFDIR | 0o755, 1, 0, 1, 1)),),
    )
    monkeypatch.setattr(cli.os, "open", guarded_open)
    monkeypatch.setattr(cli.os, "fstat", guarded_fstat)
    monkeypatch.setattr(cli.Path, "lstat", guarded_lstat)
    return metadata, flags


def _hot_content_raw(tmp_path: Path, profile_path: Path):
    from test_c1_ceo_ingress_composition import _raw

    raw = _raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid() + 10,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=tmp_path / "macro",
        content_observer_profile_path=profile_path,
    )
    return raw


def _hot_source(
    tmp_path, monkeypatch, value=None, *, expected_release_sha="a" * 40
):
    import hashlib
    from scripts import executive_os_phase1c as cli

    profile_path = tmp_path / "content-profiles.json"
    _write_content_profile(
        profile_path,
        _disabled_content_profiles() if value is None else value,
    )
    metadata, flags = _install_root_profile_metadata(
        monkeypatch, cli, profile_path
    )
    config_path = tmp_path / "control.json"
    config_path.write_bytes(b'{"fixed":"startup"}')
    config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()
    attestation = {
        "config_sha256": config_sha256,
        "process_identity": {
            "pid": 4242,
            "start_identity": "startup",
            "boot_id": "boot",
        },
        "release_commit_sha": expected_release_sha,
        "receipt": "fixed-startup-attestation",
    }
    current = {"value": copy.deepcopy(attestation)}
    source = cli._HotContentProfileSource(
        profile_path=profile_path,
        expected_gid=os.getegid(),
        expected_release_sha=expected_release_sha,
        config_path=config_path,
        startup_attestation=attestation,
        attestation_loader=lambda: copy.deepcopy(current["value"]),
    )
    return cli, source, profile_path, config_path, current, metadata, flags


def test_hot_content_disabled_file_starts_without_inline_or_runtime_effects(
    tmp_path, monkeypatch
):
    from scripts import executive_os_phase1c as cli
    from test_c1_ceo_ingress_composition import _write_config

    profile_path = tmp_path / "disabled-content-profiles.json"
    disabled = _disabled_content_profiles()
    _write_content_profile(profile_path, disabled)
    _, flags = _install_root_profile_metadata(monkeypatch, cli, profile_path)
    raw = _hot_content_raw(tmp_path, profile_path)
    loaded = cli.load_control_config(_write_config(tmp_path, raw))

    assert loaded["content_observer_profile_path"] == profile_path
    assert "content_observer" not in loaded
    assert disabled == json.loads(profile_path.read_text(encoding="utf-8"))
    assert flags and flags[-1] & os.O_NOFOLLOW
    assert flags[-1] & os.O_NONBLOCK
    assert flags[-1] & os.O_CLOEXEC


def test_hot_content_requires_app_peer_and_refuses_both_sources(
    tmp_path, monkeypatch
):
    from scripts import executive_os_phase1c as cli
    from test_c1_ceo_ingress_composition import _raw, _write_config

    profile_path = tmp_path / "content-profiles.json"
    _write_content_profile(profile_path, _disabled_content_profiles())
    _install_root_profile_metadata(monkeypatch, cli, profile_path)
    without_app = _raw(tmp_path)
    without_app["content_observer_profile_path"] = profile_path
    with pytest.raises(cli.ServiceError, match="installed App peer"):
        cli.load_control_config(_write_config(tmp_path, without_app))

    both = _hot_content_raw(tmp_path, profile_path)
    both["content_observer"] = _disabled_content_profiles()
    with pytest.raises(cli.ServiceError, match="mutually exclusive"):
        cli.load_control_config(_write_config(tmp_path, both))


def test_legacy_inline_content_profile_parity(tmp_path):
    from scripts import executive_os_phase1c as cli
    from test_c1_ceo_ingress_composition import _write_config

    raw = _hot_content_raw(tmp_path, tmp_path / "unused.json")
    raw.pop("content_observer_profile_path")
    raw["content_observer"] = _disabled_content_profiles()
    loaded = cli.load_control_config(_write_config(tmp_path, raw))
    assert loaded["content_observer"] == _disabled_content_profiles()
    assert "content_observer_profile_path" not in loaded


def test_hot_content_path_composes_the_existing_observer_and_steward_factories(
    tmp_path, monkeypatch
):
    import importlib
    from scripts import executive_os_phase1c as cli

    raw = _hot_content_raw(tmp_path, tmp_path / "content-profiles.json")
    captured = {}
    installed = importlib.import_module("integrations.executive_mcp.installed")

    class FakeReaders:
        def __init__(self, **_kwargs):
            pass

        def observe(self):
            return {}

    class FakeService:
        def __init__(self, _config, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(installed, "InstalledExecutiveReaders", FakeReaders)
    monkeypatch.setattr(cli, "ExecutiveControlService", FakeService)
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda _name: object())
    monkeypatch.setattr(
        importlib.import_module("control_plane.executive_worker_broker"),
        "WorkerBrokerClient",
        lambda *_args, **_kwargs: object(),
    )
    loader = lambda: _disabled_content_profiles()
    cli._service_from_config(raw, content_profile_loader=loader)
    binding = captured["ceo_ingress_app_binding"]
    runtime = object()
    observer = binding.content_provider_factory(runtime)
    assert observer.runtime is runtime
    assert observer.profile_loader is loader
    assert callable(binding.steward_provider_factory)

    with pytest.raises(cli.ServiceError, match="profile loader"):
        cli._service_from_config(raw)


def _runtime_database_snapshot(runtime):
    """Exact durable Runtime rows; reads may not create events or Attempts."""

    with runtime.store.read() as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"')),
                    key=repr,
                )
            )
            for table in tables
        }


def test_hot_content_service_observer_refresh_and_error_have_zero_execution_effects(
    tmp_path, monkeypatch
):
    import asyncio
    import importlib
    from test_content_profile_profiles import pair
    from test_executive_content_observer_reconcile import _DirectBroker
    from test_steward_content_integration import fixture
    from integrations.executive_content_contract import ACCESS_SCHEMA, ContentProfileKey
    from scripts import executive_os_phase1c as cli

    clock, runtime, web, _adapter, broker = fixture(tmp_path)
    cli, source, path, config_path, _, _, _ = _hot_source(
        tmp_path,
        monkeypatch,
        expected_release_sha=web.release_sha,
    )
    raw = _hot_content_raw(tmp_path, path)
    raw["proof_base_sha"] = web.release_sha
    captured = {}
    broker_operations = []
    client_constructions = []
    tick_invocations = []

    class CountingBroker(_DirectBroker):
        async def request(self, operation, payload):
            broker_operations.append(operation)
            return await super().request(operation, payload)

    client = CountingBroker(broker)

    class FakeReaders:
        def __init__(self, **_kwargs):
            pass

        def observe(self):
            return {}

    class FakeService:
        def __init__(self, _config, **kwargs):
            captured.update(kwargs)

    def forbidden_tick(*_args, **_kwargs):
        tick_invocations.append(True)
        raise AssertionError("profile reload invoked CooCycle")

    installed = importlib.import_module("integrations.executive_mcp.installed")
    worker_broker = importlib.import_module("control_plane.executive_worker_broker")
    executive_service = importlib.import_module("control_plane.executive_service")
    monkeypatch.setattr(installed, "InstalledExecutiveReaders", FakeReaders)
    monkeypatch.setattr(cli, "ExecutiveControlService", FakeService)
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda _name: object())
    monkeypatch.setattr(
        executive_service.CooCycle,
        "run_once",
        forbidden_tick,
    )
    monkeypatch.setattr(
        worker_broker,
        "WorkerBrokerClient",
        lambda *_args, **_kwargs: client_constructions.append(True) or client,
    )
    cli._service_from_config(raw, content_profile_loader=source.load)
    binding = captured["ceo_ingress_app_binding"]
    observer = binding.content_provider_factory(runtime)

    before_runtime = _runtime_database_snapshot(runtime)
    before_config = config_path.read_bytes()
    before_clock = clock.value
    _, _, actual = pair(web)

    async def exercise():
        disabled = await observer.handle_frame(web.frame(ACCESS_SCHEMA))
        assert disabled == {"ok": False, "error": {"code": "ACCESS_DENIED"}}
        assert broker_operations == []
        assert _runtime_database_snapshot(runtime) == before_runtime

        replacement = path.with_suffix(".replacement")
        _write_content_profile(replacement, actual)
        replacement.replace(path)
        unenrolled = await observer.handle_frame(web.frame(ACCESS_SCHEMA))
        assert unenrolled == {
            "ok": False,
            "error": {"code": "GRANT_INVALIDATED"},
        }
        assert broker_operations == ["ohf-observer-status"]
        assert _runtime_database_snapshot(runtime) == before_runtime

        enrollment = await observer.enroll(ContentProfileKey.web)
        assert enrollment["status"] == "ACTIVE"
        assert broker_operations == [
            "ohf-observer-status",
            "ohf-observer-enroll",
        ]
        after_enrollment = _runtime_database_snapshot(runtime)
        changed_tables = {
            table
            for table in before_runtime
            if before_runtime[table] != after_enrollment[table]
        }
        assert changed_tables == {"events"}
        assert before_runtime["attempts"] == after_enrollment["attempts"]

        allowed = await observer.handle_frame(web.frame(ACCESS_SCHEMA))
        assert allowed["ok"] is True
        assert broker_operations == [
            "ohf-observer-status",
            "ohf-observer-enroll",
            "ohf-observer-status",
        ]
        assert _runtime_database_snapshot(runtime) == after_enrollment

        malformed = path.with_suffix(".malformed")
        malformed.write_bytes(b'{"schema":')
        malformed.chmod(0o440)
        malformed.replace(path)
        refused = await observer.handle_frame(web.frame(ACCESS_SCHEMA))
        assert refused["ok"] is False
        assert refused["error"]["code"] in {
            "ACCESS_DENIED",
            "CONTENT_UNAVAILABLE",
        }
        assert broker_operations == [
            "ohf-observer-status",
            "ohf-observer-enroll",
            "ohf-observer-status",
        ]
        assert _runtime_database_snapshot(runtime) == after_enrollment

        recovered_file = path.with_suffix(".recovered")
        _write_content_profile(recovered_file, actual)
        recovered_file.replace(path)
        recovered = await observer.handle_frame(web.frame(ACCESS_SCHEMA))
        assert recovered["ok"] is True
        assert broker_operations == [
            "ohf-observer-status",
            "ohf-observer-enroll",
            "ohf-observer-status",
            "ohf-observer-status",
        ]
        assert _runtime_database_snapshot(runtime) == after_enrollment

    asyncio.run(exercise())
    assert config_path.read_bytes() == before_config
    assert client_constructions == [True]
    assert tick_invocations == []
    assert clock.value == before_clock


@pytest.mark.parametrize(
    "value",
    [
        "relative/profile.json",
        "/private/profile/../profile.json",
        "/private/profile//content.json",
        "/private/profile/./content.json",
    ],
)
def test_hot_content_refuses_relative_or_non_normalized_paths(value):
    from scripts import executive_os_phase1c as cli

    with pytest.raises(cli.ServiceError, match="absolute|normalized"):
        cli._content_profile_path(value)


@pytest.mark.parametrize(
    ("changed", "uid", "mode"),
    [
        (None, 0, 0o755),
        ("/sealed/content", 501, 0o755),
        ("/sealed/content", 0, 0o775),
    ],
    ids=["sealed-positive", "nonroot", "group-writable"],
)
def test_hot_content_ancestor_sealing_is_exact(monkeypatch, changed, uid, mode):
    from scripts import executive_os_phase1c as cli

    path = Path("/sealed/content/profile.json")

    def directory_info(node):
        node_uid = uid if os.fspath(node) == changed else 0
        node_mode = mode if os.fspath(node) == changed else 0o755
        identity = abs(hash(os.fspath(node))) % 100000 + 1
        return SimpleNamespace(
            st_dev=1,
            st_ino=identity,
            st_uid=node_uid,
            st_gid=0,
            st_mode=stat.S_IFDIR | node_mode,
            st_nlink=1,
            st_size=0,
            st_mtime_ns=1,
            st_ctime_ns=1,
        )

    monkeypatch.setattr(cli.Path, "lstat", directory_info)
    if changed is None:
        observed = cli._sealed_content_profile_ancestors(path)
        assert tuple(item[0] for item in observed) == tuple(
            os.fspath(parent) for parent in path.parents
        )
    else:
        with pytest.raises(cli.ServiceError, match="root-owned and sealed"):
            cli._sealed_content_profile_ancestors(path)


def test_hot_content_refuses_disappearance_without_cached_fallback(
    tmp_path, monkeypatch
):
    cli, source, path, _, _, _, _ = _hot_source(tmp_path, monkeypatch)
    assert source.load() == _disabled_content_profiles()
    path.unlink()
    with pytest.raises(cli.ServiceError, match="unavailable"):
        source.load()


def test_hot_content_single_profile_file_preserves_legacy_shape(
    tmp_path, monkeypatch
):
    from dataclasses import asdict
    from test_executive_content_observer import profile

    single = asdict(profile(client_ref="a" * 64, release_sha="a" * 40))
    cli, source, _, _, _, _, _ = _hot_source(
        tmp_path,
        monkeypatch,
        value=single,
    )
    loaded = source.load()
    assert loaded == single
    assert cli._validate_content_profiles(
        loaded,
        expected_release_sha="a" * 40,
    ).profile_digest == single["profile_digest"]


def test_hot_content_atomic_complete_replacement_is_fresh_and_config_stable(
    tmp_path, monkeypatch
):
    from dataclasses import asdict
    from test_content_profile_profiles import pair
    from test_executive_content_observer import profile

    cli, source, path, config, _, _, _ = _hot_source(tmp_path, monkeypatch)
    before_config = config.read_bytes()
    _, _, actual = pair(profile(client_ref="a" * 64, release_sha="a" * 40))
    replacement = path.with_suffix(".replacement")
    _write_content_profile(replacement, actual)
    replacement.replace(path)

    loaded = source.load()
    assert loaded == actual
    assert config.read_bytes() == before_config
    parsed = cli._validate_content_profiles(loaded, expected_release_sha="a" * 40)
    assert asdict(parsed.web.profile) == actual["profiles"]["web"]["profile"]


@pytest.mark.parametrize("mutation", ["config", "attestation", "release"])
def test_hot_content_refuses_changed_startup_binding_or_release(
    tmp_path, monkeypatch, mutation
):
    from test_content_profile_profiles import pair
    from test_executive_content_observer import profile

    cli, source, path, config, current, _, _ = _hot_source(tmp_path, monkeypatch)
    if mutation == "config":
        config.write_bytes(b'{"fixed":"changed-path-or-bytes"}')
        match = "config or attestation changed"
    elif mutation == "attestation":
        current["value"]["process_identity"]["start_identity"] = "replacement"
        match = "config or attestation changed"
    else:
        _, _, wrong = pair(profile(client_ref="a" * 64, release_sha="b" * 40))
        replacement = path.with_suffix(".replacement")
        _write_content_profile(replacement, wrong)
        replacement.replace(path)
        match = "release differs"
    with pytest.raises(cli.ServiceError, match=match):
        source.load()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("uid", 501),
        ("gid", 999),
        ("mode", 0o640),
        ("nlink", 2),
        ("file_type", stat.S_IFIFO),
    ],
)
def test_hot_content_refuses_wrong_owner_group_mode_link_or_file_type(
    tmp_path, monkeypatch, field, value
):
    from scripts import executive_os_phase1c as cli

    path = tmp_path / "content-profiles.json"
    _write_content_profile(path, _disabled_content_profiles())
    metadata, _ = _install_root_profile_metadata(monkeypatch, cli, path)
    metadata[field] = value
    with pytest.raises(cli.ServiceError, match="source identity"):
        cli._read_content_profile_document(path, expected_gid=os.getegid())


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema":"one","schema":"two"}',
        b'{"schema":',
        b"x" * 65537,
    ],
)
def test_hot_content_refuses_duplicate_malformed_or_oversize_input(
    tmp_path, monkeypatch, payload
):
    from scripts import executive_os_phase1c as cli

    path = tmp_path / "content-profiles.json"
    path.write_bytes(payload)
    path.chmod(0o440)
    _install_root_profile_metadata(monkeypatch, cli, path)
    with pytest.raises(cli.ServiceError):
        cli._read_content_profile_document(path, expected_gid=os.getegid())


def test_hot_content_refuses_final_and_ancestor_symlinks(tmp_path, monkeypatch):
    from scripts import executive_os_phase1c as cli

    target = tmp_path / "target.json"
    _write_content_profile(target, _disabled_content_profiles())
    link = tmp_path / "profile-link.json"
    link.symlink_to(target)
    monkeypatch.setattr(
        cli,
        "_sealed_content_profile_ancestors",
        lambda _path: (("/", (1, 1, 0, 0, stat.S_IFDIR | 0o755, 1, 0, 1, 1)),),
    )
    with pytest.raises(cli.ServiceError):
        cli._read_content_profile_document(link, expected_gid=os.getegid())

    real_dir = tmp_path / "real"
    real_dir.mkdir()
    ancestor_link = tmp_path / "linked-parent"
    ancestor_link.symlink_to(real_dir, target_is_directory=True)
    monkeypatch.undo()
    with pytest.raises(cli.ServiceError, match="ancestors"):
        cli._content_profile_path(os.fspath(ancestor_link / "profile.json"))


@pytest.mark.parametrize("mutation", ["replace", "in_place"])
def test_hot_content_refuses_mid_read_replacement_or_in_place_write(
    tmp_path, monkeypatch, mutation
):
    from scripts import executive_os_phase1c as cli

    path = tmp_path / "content-profiles.json"
    _write_content_profile(path, _disabled_content_profiles())
    _install_root_profile_metadata(monkeypatch, cli, path)
    real_read = cli.os.read
    changed = False

    def changing_read(fd, size):
        nonlocal changed
        result = real_read(fd, size)
        if result and not changed:
            changed = True
            if mutation == "replace":
                replacement = path.with_suffix(".replacement")
                _write_content_profile(replacement, _disabled_content_profiles())
                replacement.replace(path)
            else:
                path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(cli.os, "read", changing_read)
    with pytest.raises(cli.ServiceError, match="content observer profile"):
        cli._read_content_profile_document(path, expected_gid=os.getegid())


def test_hot_content_invalid_snapshot_has_no_cached_fallback(tmp_path, monkeypatch):
    from test_content_profile_profiles import pair
    from test_executive_content_observer import profile

    cli, source, path, _, _, _, _ = _hot_source(tmp_path, monkeypatch)
    _, _, actual = pair(profile(client_ref="a" * 64, release_sha="a" * 40))
    replacement = path.with_suffix(".replacement")
    _write_content_profile(replacement, actual)
    replacement.replace(path)
    assert source.load() == actual

    malformed = path.with_suffix(".malformed")
    malformed.write_bytes(b'{"schema":')
    malformed.chmod(0o440)
    malformed.replace(path)
    with pytest.raises(cli.ServiceError):
        source.load()

    recovered = path.with_suffix(".recovered")
    _write_content_profile(recovered, _disabled_content_profiles())
    recovered.replace(path)
    assert source.load() == _disabled_content_profiles()

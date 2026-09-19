"""Existing-enrollment release rebind contract for the C1 SOL_STATE Relay.

The fixture is production shaped: a temporary installed-release tree with a real
release manifest, the real relay plist template, the real render primitive, the
real closed config owner and real attested private files.  Only surfaces that
cannot exist under an unprivileged test process are mirrored onto the test
account: the root euid, the pinned uid/gid identities, the service-account
lookup, the launchctl reads, and the release manifest's root-ownership check.

The stale-relay gate is never stubbed: the fixture host really is an enrolled
relay whose plist and config are bound to the previous release.
"""
from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import io
import json
import os
import plistlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.slack_executive import c1_runtime
from ops.executive_os import render_launchd_program_arguments

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (
    ROOT
    / "ops"
    / "executive_os"
    / "com.mastermind.executive.sol-state-relay.plist.template"
)
WORKSPACE = "T0BRD2AQXQV"
CHANNEL = "C0BSGABKBFY"
BOT = "U0C1BOTFIX1"
OLD_RELEASE = "1" * 40
NEW_RELEASE = "2" * 40
THIRD_RELEASE = "3" * 40
TOKEN_BYTES = b"INERT-EXISTING-RELAY-TOKEN-BYTES\n"
PLIST_NAME = "com.mastermind.executive.sol-state-relay.plist"
_DIGEST64_RE = re.compile(r"\b[0-9a-f]{64}\b")

# The reviewed C1 relay host contract, pinned here independently of the module
# so a fixture can still be built and a drift in the module is observable.
CONTRACT = {
    "RELAY_USER": "_mastermind_sol_relay",
    "RELAY_GROUP": "_mastermind_sol_relay",
    "RELAY_LABEL": "com.mastermind.executive.sol-state-relay",
    "CONTROL_LABEL": "com.mastermind.executive.control",
    "OPS_GID": 453,
    "DIALOGUE_RELAY_GID": 457,
    "PYTHON_BINARY": (
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
    ),
    "RELAY_HOME": "/var/db/mastermind-executive/sol-state-relay/home",
    "RELAY_STDOUT_PATH": (
        "/var/log/mastermind-executive/sol-state-relay/stdout.log"
    ),
    "RELAY_STDERR_PATH": (
        "/var/log/mastermind-executive/sol-state-relay/stderr.log"
    ),
    "DIALOGUE_OBSERVATION_SOCKET": (
        "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
    ),
}


def test_module_publishes_the_pinned_relay_host_contract():
    enrollment = _module()
    for name, value in CONTRACT.items():
        observed = getattr(enrollment, name)
        if isinstance(observed, Path):
            observed = os.fspath(observed)
        assert observed == value, name


def _module():
    try:
        return importlib.import_module("ops.executive_os.c1_relay_enrollment")
    except ModuleNotFoundError:
        pytest.fail("native C1 enrollment helper is not implemented")


def _shell_relay_document(release_root: Path, config_path: Path) -> dict[str, object]:
    """Compose the plist the way prepare-c1-sol-state-relay.sh does."""

    document = plistlib.loads(TEMPLATE.read_bytes())
    document["ProgramArguments"] = [
        CONTRACT["PYTHON_BINARY"],
        "-I",
        "-S",
        "-B",
        os.fspath(release_root / "scripts" / "c1_sol_state_relay.py"),
        "--config",
        os.fspath(config_path),
    ]
    document["WorkingDirectory"] = os.fspath(release_root)
    document["UserName"] = CONTRACT["RELAY_USER"]
    document["GroupName"] = CONTRACT["RELAY_GROUP"]
    document["EnvironmentVariables"]["HOME"] = CONTRACT["RELAY_HOME"]
    document["StandardOutPath"] = CONTRACT["RELAY_STDOUT_PATH"]
    document["StandardErrorPath"] = CONTRACT["RELAY_STDERR_PATH"]
    return document


@dataclass
class _Host:
    enrollment: object
    root: Path
    releases_root: Path
    old_root: Path
    new_root: Path
    control_config: Path
    control_plist: Path
    relay_plist: Path
    token_path: Path
    config_path: Path
    launchctl: list[list[str]]
    writes: list[Path]
    replace: object
    manifest_verify: list[tuple[str, str, str]] = field(default_factory=list)

    async def rebind(self, bot_user_id: str = BOT) -> dict[str, object]:
        return await self.enrollment._rebind(bot_user_id=bot_user_id)  # noqa: SLF001

    def plist_release(self) -> str:
        document = plistlib.loads(self.relay_plist.read_bytes())
        return Path(document["WorkingDirectory"]).name

    def config_release(self) -> str:
        return json.loads(self.config_path.read_text(encoding="utf-8"))["relay_version"]

    def config_document(self) -> dict[str, object]:
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def plist_document(self) -> dict[str, object]:
        return plistlib.loads(self.relay_plist.read_bytes())

    def identity(self, path: Path) -> tuple[int, int, int, int, bytes]:
        info = path.lstat()
        return (
            info.st_dev,
            info.st_ino,
            info.st_nlink,
            os.stat_result(info).st_mode,
            path.read_bytes(),
        )

    def write_plist(self, document: dict[str, object]) -> None:
        self.relay_plist.write_bytes(plistlib.dumps(document, sort_keys=True))
        self.relay_plist.chmod(0o644)

    def write_config(self, document: dict[str, object]) -> None:
        self.config_path.write_bytes(
            self.enrollment._canonical_config_bytes(document)  # noqa: SLF001
        )
        self.config_path.chmod(0o440)

    @property
    def plist_path(self) -> Path:
        return self.relay_plist

    def overwrite(self, path: Path, payload: bytes, *, mode: int) -> None:
        path.chmod(0o600)
        path.write_bytes(payload)
        path.chmod(mode)


def _install_host(
    monkeypatch,
    tmp_path: Path,
    *,
    plist_release: str = OLD_RELEASE,
    config_release: str = OLD_RELEASE,
    bot_user_id: str = BOT,
    with_token: bool = True,
    with_config: bool = True,
) -> _Host:
    enrollment = _module()
    root = tmp_path / "host"
    releases_root = root / "releases"
    old_root = releases_root / OLD_RELEASE
    new_root = releases_root / NEW_RELEASE
    (old_root / "scripts").mkdir(parents=True)
    (old_root / "scripts" / "c1_sol_state_relay.py").write_text(
        "# inert installed relay entrypoint\n", encoding="utf-8"
    )
    (new_root / "ops" / "executive_os").mkdir(parents=True)
    shutil.copyfile(TEMPLATE, new_root / "ops" / "executive_os" / TEMPLATE.name)
    (new_root / ".executive-release-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "mastermind.executive_release_manifest/v1",
                "commit_sha": NEW_RELEASE,
                "tree_sha": "a" * 40,
            }
        ),
        encoding="utf-8",
    )

    control_config = root / "control.json"
    control_plist = root / "control.plist"
    relay_plist = root / PLIST_NAME
    token_path = root / "sol-state-relay.token"
    config_path = root / "sol-state-relay.json"

    monkeypatch.setattr(enrollment, "_ROOT", new_root)
    monkeypatch.setattr(enrollment, "SYSTEM_RELEASE_ROOT", releases_root)
    monkeypatch.setattr(enrollment, "CONTROL_CONFIG", control_config)
    monkeypatch.setattr(enrollment, "CONTROL_PLIST", control_plist)
    monkeypatch.setattr(enrollment, "RELAY_PLIST", relay_plist)
    monkeypatch.setattr(c1_runtime, "TOKEN_PATH", token_path)
    monkeypatch.setattr(c1_runtime, "CONFIG_PATH", config_path)

    euid, egid = os.geteuid(), os.getegid()
    for name in (
        "RELAY_UID",
        "RELAY_PLIST_UID",
        "RELAY_CONFIG_UID",
        "CONTROL_CONFIG_UID",
        "CONTROL_PLIST_UID",
    ):
        monkeypatch.setattr(enrollment, name, euid, raising=False)
    for name in (
        "RELAY_GID",
        "RELAY_PLIST_GID",
        "RELAY_CONFIG_GID",
        "CONTROL_CONFIG_GID",
        "CONTROL_PLIST_GID",
    ):
        monkeypatch.setattr(enrollment, name, egid, raising=False)

    relay_home = SimpleNamespace(
        pw_uid=euid,
        pw_gid=egid,
        pw_dir=CONTRACT["RELAY_HOME"],
        pw_shell="/usr/bin/false",
    )
    relay_group = SimpleNamespace(gr_gid=egid, gr_mem=[])
    monkeypatch.setattr(enrollment.os, "geteuid", lambda: 0)
    monkeypatch.setattr(enrollment.sys, "platform", "darwin")
    monkeypatch.setattr(enrollment.pwd, "getpwnam", lambda _name: relay_home)
    monkeypatch.setattr(enrollment.grp, "getgrnam", lambda _name: relay_group)
    monkeypatch.setattr(
        enrollment.os, "getgrouplist", lambda _name, _gid: [egid]
    )
    monkeypatch.setattr(
        enrollment.grp,
        "getgrgid",
        lambda _gid: SimpleNamespace(gr_name=CONTRACT["RELAY_USER"]),
    )

    control_config.write_text(
        json.dumps(
            {
                "proof_base_sha": NEW_RELEASE,
                "ceo_ingress_launchd_socket_name": "CeoIngress",
                "ceo_ingress_peer_uid": enrollment.RELAY_UID,
                "ceo_ingress_socket_path": os.fspath(
                    c1_runtime.EXECUTIVE_SOCKET_PATH
                ),
                "dialogue_bridge_armed": False,
                "dialogue_observation_launchd_socket_name": "DialogueObservation",
                "dialogue_observation_peer_uid": CONTRACT["DIALOGUE_RELAY_GID"],
                "dialogue_observation_socket_path": os.fspath(
                    CONTRACT["DIALOGUE_OBSERVATION_SOCKET"]
                ),
                "dialogue_wake_retry_policy": {
                    "accepted_ttl_s": None,
                    "armed": False,
                    "max_delivery_attempts": None,
                    "reenable_on_binding_rotation": True,
                    "retry_cooldown_s": None,
                    "target_unavailable_backoff_s": None,
                },
            }
        ),
        encoding="utf-8",
    )
    control_config.chmod(0o440)
    control_plist.write_bytes(
        plistlib.dumps(
            {
                "Sockets": {
                    "Operator": {
                        "SockPathOwner": 450,
                        "SockPathGroup": CONTRACT["OPS_GID"],
                        "SockPathMode": 0o660,
                    },
                    "CeoIngress": {
                        "SockPathOwner": 450,
                        "SockPathGroup": enrollment.RELAY_GID,
                        "SockPathMode": 0o660,
                    },
                    "DialogueObservation": {
                        "SockPathName": os.fspath(
                            CONTRACT["DIALOGUE_OBSERVATION_SOCKET"]
                        ),
                        "SockPathOwner": 450,
                        "SockPathGroup": CONTRACT["DIALOGUE_RELAY_GID"],
                        "SockPathMode": 0o660,
                    },
                }
            }
        )
    )
    control_plist.chmod(0o644)

    if with_token:
        token_path.write_bytes(TOKEN_BYTES)
        token_path.chmod(0o400)
    if with_config:
        config_path.write_bytes(
            enrollment._canonical_config_bytes(  # noqa: SLF001
                enrollment.build_config_document(
                    bot_user_id=bot_user_id, release_sha=config_release
                )
            )
        )
        config_path.chmod(0o440)
    relay_plist.write_bytes(
        plistlib.dumps(
            _shell_relay_document(releases_root / plist_release, config_path),
            sort_keys=True,
        )
    )
    relay_plist.chmod(0o644)

    manifest_verify: list[tuple[str, str, str]] = []

    def verify(manifest_root, commit_sha, tree_sha):
        # The real verifier re-proves root:wheel ownership of every installed
        # object, which cannot exist in an unprivileged fixture.
        manifest_verify.append(
            (os.fspath(manifest_root), commit_sha, tree_sha)
        )

    monkeypatch.setattr(
        enrollment,
        "release_manifest",
        SimpleNamespace(
            MANIFEST_NAME=".executive-release-manifest.json", verify=verify
        ),
    )

    launchctl: list[list[str]] = []
    real_run = enrollment.subprocess.run

    def run(argv, **kwargs):
        if isinstance(argv, (list, tuple)) and list(argv[:1]) == ["/bin/launchctl"]:
            launchctl.append(list(argv))
            if list(argv[1:2]) == ["print"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="")
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "disabled services = {\n"
                    f'"{CONTRACT["RELAY_LABEL"]}" => disabled\n'
                    "}\n"
                ),
                stderr="",
            )
        return real_run(argv, **kwargs)

    monkeypatch.setattr(enrollment.subprocess, "run", run)

    # The control files and the relay plist are root-owned in production.  An
    # unprivileged fixture mirrors only that ownership expectation onto the test
    # account and still runs the real metadata check, so a refusal can never be
    # a privilege artifact.  Nothing else about the gate is stubbed.
    real_exact_file = enrollment._exact_file  # noqa: SLF001
    root_owned_paths = {control_config, control_plist, relay_plist}

    def exact_file(path, *, uid, gid, mode):
        if Path(path) in root_owned_paths:
            uid, gid = euid, egid
        real_exact_file(path, uid=uid, gid=gid, mode=mode)

    monkeypatch.setattr(enrollment, "_exact_file", exact_file)

    writes: list[Path] = []
    real_replace = enrollment._replace_exact_file_atomic  # noqa: SLF001

    def replace(path, payload, *, uid, gid, mode):
        writes.append(Path(path))
        real_replace(path, payload, uid=uid, gid=gid, mode=mode)

    monkeypatch.setattr(enrollment, "_replace_exact_file_atomic", replace)
    return _Host(
        enrollment=enrollment,
        root=root,
        releases_root=releases_root,
        old_root=old_root,
        new_root=new_root,
        control_config=control_config,
        control_plist=control_plist,
        relay_plist=relay_plist,
        token_path=token_path,
        config_path=config_path,
        launchctl=launchctl,
        writes=writes,
        replace=replace,
        manifest_verify=manifest_verify,
    )


def _forbidden_calls(host: _Host) -> list[str]:
    return sorted(
        {
            call[1]
            for call in host.launchctl
            if call[:1] == ["/bin/launchctl"]
        }
    )


def test_stale_enrolled_relay_rebinds_to_the_installed_release(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    enrollment = host.enrollment
    gate_calls: list[str] = []
    current_release_gate = enrollment._assert_host_prepared  # noqa: SLF001

    def recorded_gate():
        gate_calls.append("called")
        return current_release_gate()

    # Assert the rebind does not reuse the strict current-release gate, which
    # refuses any relay plist that is not already bound to this release tree.
    monkeypatch.setattr(enrollment, "_assert_host_prepared", recorded_gate)

    assert host.plist_release() == OLD_RELEASE
    assert host.config_release() == OLD_RELEASE
    before_token = host.identity(host.token_path)
    before_config = host.config_document()

    receipt = asyncio.run(host.rebind())

    assert gate_calls == []
    assert receipt == {
        "action": "rebound",
        "bot_user_id": BOT,
        "release_sha": NEW_RELEASE,
    }
    assert host.manifest_verify == [
        (os.fspath(host.new_root), NEW_RELEASE, "a" * 40)
    ]
    assert host.plist_release() == NEW_RELEASE
    assert host.config_release() == NEW_RELEASE
    assert host.plist_document() == _shell_relay_document(
        host.new_root, host.config_path
    )
    assert host.writes == [host.relay_plist, host.config_path]
    assert _forbidden_calls(host) == ["print", "print-disabled"]
    assert host.identity(host.token_path) == before_token
    after_config = host.config_document()
    assert after_config == {
        **before_config,
        "relay_version": NEW_RELEASE,
    }


def test_enroll_gate_still_requires_the_current_release_binding(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)

    # enroll/resume/verify keep the strict current-release semantics: the stale
    # relay plist must keep refusing them.
    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_ENROLLMENT_HOST_REFUSED"
    ):
        host.enrollment._assert_host_prepared()  # noqa: SLF001


def test_rebind_owns_no_provider_or_service_arm_path(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    enrollment = host.enrollment

    async def forbidden(**_kwargs):  # pragma: no cover - must never run
        raise AssertionError("rebind must not qualify or call a provider")

    def forbidden_sync(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("rebind must not read the credential")

    monkeypatch.setattr(enrollment, "qualify_token", forbidden)
    monkeypatch.setattr(c1_runtime, "verify_slack_identity", forbidden)
    monkeypatch.setattr(c1_runtime, "read_token_file", forbidden_sync)
    monkeypatch.setattr(enrollment, "_existing_token", forbidden_sync)
    monkeypatch.setattr(
        enrollment, "SlackWebApiStateClient", lambda **_kwargs: forbidden_sync
    )
    monkeypatch.setattr(
        enrollment, "SlackHttpTransport", lambda *_args, **_kwargs: forbidden_sync
    )

    receipt = asyncio.run(host.rebind())

    assert receipt["action"] == "rebound"
    forbidden_names = {
        "qualify_token",
        "verify_slack_identity",
        "read_token_file",
        "_existing_token",
        "SlackHttpTransport",
        "SlackWebApiStateClient",
        "fetch_history",
        "launchctl",
        "kickstart",
        "bootstrap",
    }
    identifiers: set[str] = set()
    for name in (
        "_rebind",
        "_stage_rebind_target",
        "_converge_rebind_pair",
        "_restore_rebind_pair",
        "_validate_rebind_pair",
        "_attest_token",
        "_load_rebind_config",
        "_read_rebind_pair",
    ):
        source = inspect.getsource(getattr(enrollment, name))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
    assert forbidden_names.isdisjoint(identifiers)


def test_rebind_cli_receipt_never_leaks_credential_material(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    stdout = io.StringIO()

    code = host.enrollment.run(
        ["rebind-release", "--expected-bot-user-id", BOT],
        stdin=io.BytesIO(),
        stdout=stdout,
        environ={},
    )

    receipt = json.loads(stdout.getvalue())
    assert code == 0
    assert receipt["action"] == "rebound"
    assert receipt["status"] == "PASS"
    assert receipt["release_sha"] == NEW_RELEASE
    assert TOKEN_BYTES.strip().decode() not in stdout.getvalue()
    assert _DIGEST64_RE.search(stdout.getvalue()) is None


@pytest.mark.parametrize(
    "arguments",
    (
        ["--release-sha", NEW_RELEASE],
        ["--target-sha", NEW_RELEASE],
        ["--config", "/tmp/config.json"],
        ["--token", "xoxb-inert"],
        ["--workspace", WORKSPACE],
        ["--channel", CHANNEL],
    ),
)
def test_rebind_parser_refuses_release_and_secret_knobs(monkeypatch, tmp_path, arguments):
    enrollment = _module()
    parser = enrollment.build_parser()
    parsed = parser.parse_args(["rebind-release", "--expected-bot-user-id", BOT])
    assert parsed.command == "rebind-release"
    assert parsed.expected_bot_user_id == BOT

    with pytest.raises(
        enrollment.C1EnrollmentError, match="C1_ENROLLMENT_ARGUMENTS_REFUSED"
    ):
        parser.parse_args(["rebind-release", "--expected-bot-user-id", BOT, *arguments])


@pytest.mark.parametrize(
    ("with_token", "with_config"),
    ((True, False), (False, True), (False, False)),
)
def test_rebind_refuses_partial_enrollment(monkeypatch, tmp_path, with_token, with_config):
    host = _install_host(
        monkeypatch, tmp_path, with_token=with_token, with_config=with_config
    )

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_PARTIAL_STATE"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []


def test_rebind_refuses_old_plist_config_disagreement(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path, config_release=THIRD_RELEASE)

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_VERSION_MISMATCH"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []
    assert host.plist_release() == OLD_RELEASE
    assert host.config_release() == THIRD_RELEASE


def test_rebind_refuses_stale_bot_identity(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path, bot_user_id="U0OTHERBOT1")

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_STALE_CONFIG"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []


def test_rebind_maps_malformed_config_to_a_typed_refusal(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    host.overwrite(
        host.config_path,
        b'{"schema":"mastermind.sol_state_relay_config.v1"}\n',
        mode=0o440,
    )

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_STALE_CONFIG"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []


def _mutated(document: dict[str, object], mutation: str) -> object:
    mutated = json.loads(json.dumps(document))
    program = mutated["ProgramArguments"]
    if mutation == "short":
        mutated["ProgramArguments"] = program[:3]
    elif mutation == "program_mapping":
        mutated["ProgramArguments"] = {"0": program[0]}
    elif mutation == "program_missing":
        del mutated["ProgramArguments"]
    elif mutation == "python_binary":
        program[0] = "/usr/bin/python3"
    elif mutation == "flag_order":
        program[1], program[3] = program[3], program[1]
    elif mutation == "extra_argument":
        program.append("--extra")
    elif mutation == "config_path":
        program[6] = "/tmp/other-config.json"
    elif mutation == "entrypoint_basename":
        program[4] = program[4].replace("c1_sol_state_relay.py", "decoy.py")
    elif mutation == "entrypoint_directory":
        program[4] = program[4].replace("/scripts/", "/other/")
    elif mutation == "entrypoint_foreign":
        program[4] = "/tmp/attacker/scripts/c1_sol_state_relay.py"
    elif mutation == "release_root_not_a_sha":
        mutated["WorkingDirectory"] = "/tmp/releases/not-a-release-sha"
    elif mutation == "release_root_mismatch":
        mutated["WorkingDirectory"] = mutated["WorkingDirectory"] + "-extra"
    elif mutation == "label":
        mutated["Label"] = "com.mastermind.executive.other"
    elif mutation == "user":
        mutated["UserName"] = "_mastermind_exec"
    elif mutation == "group":
        mutated["GroupName"] = "wheel"
    elif mutation == "extra_top_level":
        mutated["Program"] = "/bin/sh"
    elif mutation == "missing_static_key":
        del mutated["KeepAlive"]
    elif mutation == "umask":
        mutated["Umask"] = 0
    elif mutation == "limits":
        mutated["HardResourceLimits"] = {"Core": 0, "FileSize": 1}
    elif mutation == "extra_environment":
        mutated["EnvironmentVariables"]["EXTRA"] = "1"
    elif mutation == "missing_environment":
        del mutated["EnvironmentVariables"]["TZ"]
    elif mutation == "token_environment":
        mutated["EnvironmentVariables"]["SLACK_BOT_TOKEN"] = "xoxb-inert"
    elif mutation == "placeholder":
        mutated["EnvironmentVariables"]["PATH"] = "__PATH__"
    else:  # pragma: no cover - guard against a typo in the matrix
        raise AssertionError(mutation)
    return mutated


@pytest.mark.parametrize(
    "mutation",
    (
        "short",
        "program_mapping",
        "program_missing",
        "python_binary",
        "flag_order",
        "extra_argument",
        "config_path",
        "entrypoint_basename",
        "entrypoint_directory",
        "entrypoint_foreign",
        "release_root_not_a_sha",
        "release_root_mismatch",
        "label",
        "user",
        "group",
        "extra_top_level",
        "missing_static_key",
        "umask",
        "limits",
        "extra_environment",
        "missing_environment",
        "token_environment",
        "placeholder",
    ),
)
def test_rebind_refuses_malformed_old_enrollment_plists(monkeypatch, tmp_path, mutation):
    host = _install_host(monkeypatch, tmp_path)
    host.write_plist(_mutated(host.plist_document(), mutation))

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_PLIST_REFUSED"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []


@pytest.mark.parametrize("payload", (b"not a plist\n", b"", None))
def test_rebind_refuses_unparsable_or_non_mapping_plists(monkeypatch, tmp_path, payload):
    host = _install_host(monkeypatch, tmp_path)
    if payload is None:
        payload = plistlib.dumps(["not", "a", "mapping"])
    host.relay_plist.write_bytes(payload)
    host.relay_plist.chmod(0o644)

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_PLIST_REFUSED"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []


@pytest.mark.parametrize("target", ("token", "config", "plist"))
def test_rebind_refuses_symlinked_enrollment_files(monkeypatch, tmp_path, target):
    host = _install_host(monkeypatch, tmp_path)
    path = getattr(host, f"{target}_path")
    decoy = host.root / f"{target}.decoy"
    decoy.write_bytes(path.read_bytes())
    decoy.chmod(path.stat().st_mode & 0o777)
    path.unlink()
    os.symlink(decoy, path)
    expected = {
        "token": "C1_REBIND_TOKEN_REFUSED",
        "config": "C1_REBIND_STALE_CONFIG",
        "plist": "C1_REBIND_PLIST_REFUSED",
    }[target]

    with pytest.raises(host.enrollment.C1EnrollmentError, match=expected):
        asyncio.run(host.rebind())
    assert host.writes == []


def test_rebind_refuses_a_hard_linked_plist(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    os.link(host.relay_plist, host.root / "relay.plist.copy")

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_PLIST_REFUSED"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []


@pytest.mark.parametrize(
    ("target", "attribute", "expected"),
    (
        ("plist", "RELAY_PLIST_UID", "C1_REBIND_PLIST_REFUSED"),
        ("plist", "RELAY_PLIST_GID", "C1_REBIND_PLIST_REFUSED"),
        ("config", "RELAY_CONFIG_UID", "C1_REBIND_STALE_CONFIG"),
        ("config", "RELAY_CONFIG_GID", "C1_REBIND_STALE_CONFIG"),
        ("token", "RELAY_UID", "C1_REBIND_TOKEN_REFUSED"),
        ("token", "RELAY_GID", "C1_REBIND_TOKEN_REFUSED"),
    ),
)
def test_rebind_refuses_wrong_pinned_ownership(monkeypatch, tmp_path, target, attribute, expected):
    host = _install_host(monkeypatch, tmp_path)
    pinned = getattr(host.enrollment, attribute)
    monkeypatch.setattr(host.enrollment, attribute, pinned + 1)
    if target == "token":
        # Keep the substrate consistent with the drifted credential identity so
        # the refusal is proved by the token attestation itself, not by the
        # account lookup or the control-plane peer identity.
        enrollment = host.enrollment
        drifted = SimpleNamespace(
            pw_uid=enrollment.RELAY_UID,
            pw_gid=enrollment.RELAY_GID,
            pw_dir=CONTRACT["RELAY_HOME"],
            pw_shell="/usr/bin/false",
        )
        monkeypatch.setattr(enrollment.pwd, "getpwnam", lambda _name: drifted)
        monkeypatch.setattr(
            enrollment.grp,
            "getgrnam",
            lambda _name: SimpleNamespace(gr_gid=enrollment.RELAY_GID, gr_mem=[]),
        )
        monkeypatch.setattr(
            enrollment.os,
            "getgrouplist",
            lambda _name, _gid: [enrollment.RELAY_GID],
        )
        monkeypatch.setattr(
            enrollment.grp,
            "getgrgid",
            lambda _gid: SimpleNamespace(gr_name=CONTRACT["RELAY_USER"]),
        )
        control = json.loads(host.control_config.read_text(encoding="utf-8"))
        control["ceo_ingress_peer_uid"] = enrollment.RELAY_UID
        host.overwrite(
            host.control_config,
            json.dumps(control).encode("utf-8"),
            mode=0o440,
        )
        sockets = plistlib.loads(host.control_plist.read_bytes())
        sockets["Sockets"]["CeoIngress"]["SockPathGroup"] = enrollment.RELAY_GID
        host.overwrite(
            host.control_plist,
            plistlib.dumps(sockets),
            mode=0o644,
        )

    with pytest.raises(host.enrollment.C1EnrollmentError, match=expected):
        asyncio.run(host.rebind())
    assert host.writes == []


@pytest.mark.parametrize(
    ("target", "mode", "expected"),
    (
        ("plist", 0o600, "C1_REBIND_PLIST_REFUSED"),
        ("config", 0o600, "C1_REBIND_STALE_CONFIG"),
        ("token", 0o644, "C1_REBIND_TOKEN_REFUSED"),
    ),
)
def test_rebind_refuses_wrong_file_modes(monkeypatch, tmp_path, target, mode, expected):
    host = _install_host(monkeypatch, tmp_path)
    path = getattr(host, f"{target}_path")
    path.chmod(mode)

    with pytest.raises(host.enrollment.C1EnrollmentError, match=expected):
        asyncio.run(host.rebind())
    assert host.writes == []


@pytest.mark.parametrize("service", ("control_loaded", "relay_loaded", "relay_enabled"))
def test_rebind_refuses_while_a_service_is_not_disarmed(monkeypatch, tmp_path, service):
    host = _install_host(monkeypatch, tmp_path)
    enrollment = host.enrollment
    real_run = enrollment.subprocess.run

    def run(argv, **kwargs):
        if list(argv[:1]) == ["/bin/launchctl"]:
            host.launchctl.append(list(argv))
            if list(argv[1:2]) == ["print"]:
                loaded = (
                    service == "control_loaded"
                    and list(argv[2:3])
                    == [f"system/{enrollment.CONTROL_LABEL}"]
                ) or (
                    service == "relay_loaded"
                    and list(argv[2:3]) == [f"system/{CONTRACT["RELAY_LABEL"]}"]
                )
                return SimpleNamespace(
                    returncode=0 if loaded else 1, stdout="", stderr=""
                )
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    f'"{CONTRACT["RELAY_LABEL"]}" => '
                    f'{"enabled" if service == "relay_enabled" else "disabled"}\n'
                ),
                stderr="",
            )
        return real_run(argv, **kwargs)

    monkeypatch.setattr(enrollment.subprocess, "run", run)

    with pytest.raises(
        enrollment.C1EnrollmentError, match="C1_REBIND_SERVICE_RUNNING"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []


def test_rebind_refuses_service_state_drift_at_the_commit_boundary(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    enrollment = host.enrollment
    real_run = enrollment.subprocess.run
    relay_prints = 0

    def run(argv, **kwargs):
        nonlocal relay_prints
        if list(argv[:1]) == ["/bin/launchctl"]:
            host.launchctl.append(list(argv))
            if list(argv[1:2]) == ["print"]:
                loaded = False
                if list(argv[2:3]) == [f"system/{CONTRACT["RELAY_LABEL"]}"]:
                    relay_prints += 1
                    # The relay loads after the entry check but before the write.
                    loaded = relay_prints > 1
                return SimpleNamespace(
                    returncode=0 if loaded else 1, stdout="", stderr=""
                )
            return SimpleNamespace(
                returncode=0,
                stdout=f'"{CONTRACT["RELAY_LABEL"]}" => disabled\n',
                stderr="",
            )
        return real_run(argv, **kwargs)

    monkeypatch.setattr(enrollment.subprocess, "run", run)

    with pytest.raises(
        enrollment.C1EnrollmentError, match="C1_REBIND_SERVICE_RUNNING"
    ):
        asyncio.run(host.rebind())
    assert host.writes == []
    assert host.plist_release() == OLD_RELEASE
    assert host.config_release() == OLD_RELEASE


def test_rebind_reports_service_state_drift_after_the_commit(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    enrollment = host.enrollment
    real_run = enrollment.subprocess.run
    relay_prints = 0

    def run(argv, **kwargs):
        nonlocal relay_prints
        if list(argv[:1]) == ["/bin/launchctl"]:
            host.launchctl.append(list(argv))
            if list(argv[1:2]) == ["print"]:
                loaded = False
                if list(argv[2:3]) == [f"system/{CONTRACT["RELAY_LABEL"]}"]:
                    relay_prints += 1
                    loaded = relay_prints > 2
                return SimpleNamespace(
                    returncode=0 if loaded else 1, stdout="", stderr=""
                )
            return SimpleNamespace(
                returncode=0,
                stdout=f'"{CONTRACT["RELAY_LABEL"]}" => disabled\n',
                stderr="",
            )
        return real_run(argv, **kwargs)

    monkeypatch.setattr(enrollment.subprocess, "run", run)

    with pytest.raises(
        enrollment.C1EnrollmentError, match="C1_REBIND_SERVICE_RUNNING"
    ):
        asyncio.run(host.rebind())
    # The durable pair is still the coherent, verified new generation: a late
    # service-state drift must never be reported as a clean success, and it must
    # not be reported as a rollback either.
    assert host.plist_release() == NEW_RELEASE
    assert host.config_release() == NEW_RELEASE
    assert host.plist_document() == _shell_relay_document(
        host.new_root, host.config_path
    )


class _InjectedReplace:
    """Script one post-commit or pre-commit failure per replacement call."""

    def __init__(self, host: _Host, script: list[tuple[Path, str]]):
        self.host = host
        self.script = list(script)
        self.calls: list[Path] = []

    def __call__(self, path, payload, *, uid, gid, mode):
        path = Path(path)
        self.calls.append(path)
        if self.script and self.script[0][0] == path:
            _target, behaviour = self.script.pop(0)
            if behaviour == "commit_then_raise":
                self.host.replace(path, payload, uid=uid, gid=gid, mode=mode)
                raise self.host.enrollment.C1EnrollmentError(
                    "C1_ENROLLMENT_WRITE_REFUSED"
                )
            if behaviour == "raise_without_write":
                raise self.host.enrollment.C1EnrollmentError(
                    "C1_ENROLLMENT_WRITE_REFUSED"
                )
            if behaviour == "tamper_token_after":
                self.host.replace(path, payload, uid=uid, gid=gid, mode=mode)
                replacement = self.host.root / ".token.rotation"
                replacement.write_bytes(self.host.token_path.read_bytes())
                replacement.chmod(0o400)
                os.replace(replacement, self.host.token_path)
                return
        self.host.replace(path, payload, uid=uid, gid=gid, mode=mode)


def test_rebind_rolls_back_a_first_write_post_commit_failure(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    injection = _InjectedReplace(host, [(host.relay_plist, "commit_then_raise")])
    monkeypatch.setattr(host.enrollment, "_replace_exact_file_atomic", injection)
    plist_preimage = host.relay_plist.read_bytes()
    config_preimage = host.config_path.read_bytes()

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_WRITE_REFUSED"
    ):
        asyncio.run(host.rebind())

    # A clean refusal is only lawful with both durable files proven at the
    # exact preimages, never with one file rewound and the other advanced.
    assert host.relay_plist.read_bytes() == plist_preimage
    assert host.config_path.read_bytes() == config_preimage
    assert host.plist_release() == OLD_RELEASE
    assert host.config_release() == OLD_RELEASE


def test_rebind_completes_forward_after_a_second_write_post_commit_failure(
    monkeypatch, tmp_path
):
    host = _install_host(monkeypatch, tmp_path)
    injection = _InjectedReplace(host, [(host.config_path, "commit_then_raise")])
    monkeypatch.setattr(host.enrollment, "_replace_exact_file_atomic", injection)

    receipt = asyncio.run(host.rebind())

    assert receipt["action"] == "rebound"
    assert host.plist_release() == NEW_RELEASE
    assert host.config_release() == NEW_RELEASE
    assert host.plist_document() == _shell_relay_document(
        host.new_root, host.config_path
    )


def test_rebind_refuses_cleanly_when_a_write_fails_before_commit(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    injection = _InjectedReplace(host, [(host.config_path, "raise_without_write")])
    monkeypatch.setattr(host.enrollment, "_replace_exact_file_atomic", injection)
    plist_preimage = host.relay_plist.read_bytes()
    config_preimage = host.config_path.read_bytes()

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_WRITE_REFUSED"
    ):
        asyncio.run(host.rebind())

    assert host.relay_plist.read_bytes() == plist_preimage
    assert host.config_path.read_bytes() == config_preimage


def test_rebind_reports_a_proven_mixed_generation_instead_of_a_rollback(
    monkeypatch, tmp_path
):
    host = _install_host(monkeypatch, tmp_path)
    injection = _InjectedReplace(
        host,
        [
            (host.relay_plist, "commit_then_raise"),
            (host.relay_plist, "raise_without_write"),
        ],
    )
    monkeypatch.setattr(host.enrollment, "_replace_exact_file_atomic", injection)

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_MIXED_GENERATION"
    ):
        asyncio.run(host.rebind())

    # The remaining pair is provably half of each generation.  It is reported as
    # a mixed generation, never as a completed rollback.
    assert host.plist_release() == NEW_RELEASE
    assert host.config_release() == OLD_RELEASE


def test_rebind_restores_both_preimages_on_a_post_write_validation_failure(
    monkeypatch, tmp_path
):
    host = _install_host(monkeypatch, tmp_path)
    injection = _InjectedReplace(
        host, [(host.config_path, "tamper_token_after")]
    )
    monkeypatch.setattr(host.enrollment, "_replace_exact_file_atomic", injection)
    plist_preimage = host.relay_plist.read_bytes()
    config_preimage = host.config_path.read_bytes()
    token_bytes = host.token_path.read_bytes()

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_WRITE_REFUSED"
    ):
        asyncio.run(host.rebind())

    assert host.relay_plist.read_bytes() == plist_preimage
    assert host.config_path.read_bytes() == config_preimage
    assert host.plist_release() == OLD_RELEASE
    assert host.config_release() == OLD_RELEASE
    # The credential was never written by the rebind; the tampering is external
    # and is exactly what the post-write attestation detected.
    assert host.token_path.read_bytes() == token_bytes


@pytest.mark.parametrize(
    ("plist_release", "config_release"),
    ((NEW_RELEASE, OLD_RELEASE), (OLD_RELEASE, NEW_RELEASE)),
)
def test_rebind_finishes_a_crash_mixed_state_forward(
    monkeypatch, tmp_path, plist_release, config_release
):
    host = _install_host(
        monkeypatch, tmp_path, plist_release=plist_release, config_release=config_release
    )

    receipt = asyncio.run(host.rebind())

    assert receipt["action"] == "rebound"
    assert host.plist_release() == NEW_RELEASE
    assert host.config_release() == NEW_RELEASE


def test_rebind_same_release_replay_writes_nothing(monkeypatch, tmp_path):
    host = _install_host(
        monkeypatch,
        tmp_path,
        plist_release=NEW_RELEASE,
        config_release=NEW_RELEASE,
    )
    before_plist = host.identity(host.relay_plist)
    before_config = host.identity(host.config_path)
    before_token = host.identity(host.token_path)

    receipt = asyncio.run(host.rebind())

    assert receipt == {
        "action": "already-current",
        "bot_user_id": BOT,
        "release_sha": NEW_RELEASE,
    }
    assert host.writes == []
    assert host.identity(host.relay_plist) == before_plist
    assert host.identity(host.config_path) == before_config
    assert host.identity(host.token_path) == before_token


def test_rebind_replay_after_a_completed_rebind_is_a_no_write_no_op(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    asyncio.run(host.rebind())
    host.writes.clear()
    before_plist = host.identity(host.relay_plist)
    before_config = host.identity(host.config_path)

    receipt = asyncio.run(host.rebind())

    assert receipt["action"] == "already-current"
    assert host.writes == []
    assert host.identity(host.relay_plist) == before_plist
    assert host.identity(host.config_path) == before_config


def test_rendered_plist_matches_the_shell_render_owner_without_placeholders(
    monkeypatch, tmp_path
):
    host = _install_host(monkeypatch, tmp_path)
    enrollment = host.enrollment

    rendered = enrollment._render_relay_plist(host.new_root)  # noqa: SLF001

    composed = host.root / "composed.plist"
    shutil.copyfile(TEMPLATE, composed)
    composed.chmod(0o644)
    render_launchd_program_arguments.render_program_arguments(
        composed,
        _shell_relay_document(host.new_root, host.config_path)["ProgramArguments"],
    )
    document = plistlib.loads(composed.read_bytes())
    document["WorkingDirectory"] = os.fspath(host.new_root)
    document["UserName"] = CONTRACT["RELAY_USER"]
    document["GroupName"] = CONTRACT["RELAY_GROUP"]
    document["EnvironmentVariables"]["HOME"] = CONTRACT["RELAY_HOME"]
    document["StandardOutPath"] = CONTRACT["RELAY_STDOUT_PATH"]
    document["StandardErrorPath"] = CONTRACT["RELAY_STDERR_PATH"]

    assert plistlib.loads(rendered) == document
    assert plistlib.loads(rendered) == _shell_relay_document(
        host.new_root, host.config_path
    )
    assert "__" not in rendered.decode("utf-8")


def test_rebind_never_creates_a_missing_final_file(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path, with_config=False)
    host.config_path.write_bytes(
        host.enrollment._canonical_config_bytes(  # noqa: SLF001
            host.enrollment.build_config_document(
                bot_user_id=BOT, release_sha=OLD_RELEASE
            )
        )
    )
    host.config_path.chmod(0o440)
    host.config_path.unlink()

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_REBIND_PARTIAL_STATE"
    ):
        asyncio.run(host.rebind())


def test_replace_exact_file_atomic_refuses_a_missing_target(monkeypatch, tmp_path):
    host = _install_host(monkeypatch, tmp_path)
    missing = host.root / "absent.plist"

    with pytest.raises(
        host.enrollment.C1EnrollmentError, match="C1_ENROLLMENT_WRITE_REFUSED"
    ):
        host.enrollment._replace_exact_file_atomic(  # noqa: SLF001
            missing,
            b"payload\n",
            uid=os.geteuid(),
            gid=os.getegid(),
            mode=0o644,
        )
    assert not missing.exists()

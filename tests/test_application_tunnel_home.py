"""Fixed Ubuntu1 home forwards through the incumbent APPLICATION owner.

Real sealed files, original reverse journals, whole-authfile CAS and recovery.
Only systemd/process observations and the one existing service command are faked.
"""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from ops.executive_os import application_tunnel_control as control
from tests.test_application_tunnel_control import (
    CLIENT_SHA, SERVER_SHA, FINGERPRINT, INCUMBENT, _own, harness, sealed_root,
)
from tests.test_hermes_primary_application_tunnel import RoleSystem, role_stage, role_server

AUTH = "home-existing:" + "h" * 48
SSH_ACL = r"^R:127\.0\.0\.1:2222$"


class HomeSystem:
    def __init__(self, paths):
        self.paths = paths
        self.pid = 5700
        self.candidate = False
        self.streams = False
        self.restarts = 0
        self.extra_listeners = []

    def home_unit_identity(self, paths):
        return {"active": True, "main_pid": self.pid, "argv": [str(paths.home_launcher)],
                "fragment": str(paths.home_unit_file), "dropins": "", "user": "longr",
                "invocation": str(self.pid), "need_daemon_reload": "yes",
                "cgroup": "/system.slice/" + control.HOME_UNIT, "restart": "always",
                "restart_usec": "3s", "no_new_privileges": "yes"}

    def binary_identity(self, path):
        assert path == self.paths.home_binary
        return {"sha256": CLIENT_SHA, "output": "1.12.0"}

    def process_matches(self, pid, expected):
        return pid == self.pid and expected == control._home_argv(
            self.paths, FINGERPRINT, self.candidate)

    def process_image_identity(self, pid):
        assert pid == self.pid
        return {"pid": pid, "start_id": "fixture-home-" + str(pid), "sha256": CLIENT_SHA}

    def home_process_credential(self, pid):
        assert pid == self.pid
        return {"uid": control._home_owner(self.paths)["uid"],
                "credential_sha256": control.digest(AUTH.encode())}

    def listeners(self, port):
        assert port == control.RELAY_PORT
        return ([{"address": value, "pid": self.pid} for value in control.HOME_DESTINATIONS]
                if self.candidate else []) + self.extra_listeners

    def home_active_streams(self, pid):
        assert pid == self.pid
        return self.streams

    def restart_home(self):
        self.restarts += 1
        self.pid += 1
        self.candidate = True
        return {"returncode": 0, "stderr": ""}


class HomeHarness:
    def __init__(self, h):
        self.h = h
        self.paths = h.paths
        self.system = HomeSystem(h.paths)
        self.server = RoleSystem(unit={"active": True, "main_pid": 4242,
                                 "argv": control._server_expected_argv(h.paths)})
        for path, data, mode in (
            (h.paths.home_launcher, control.HOME_LAUNCHER, 0o755),
            (h.paths.home_unit_file, control.HOME_UNIT_BYTES, 0o644),
            (h.paths.home_credential, ("CHISEL_AUTH=" + AUTH + "\nCHISEL_FP=" + FINGERPRINT + "\n").encode(), 0o600),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            _own(path, mode)
        h.stage()
        h.write_authfile({**INCUMBENT, AUTH: [SSH_ACL]})
        raw, expected = h.bundle()
        original_bundle = h.paths.operation_root / "stage/server-bundle.json"
        receipt = control.apply_server(bundle_path=original_bundle, expected_digest=expected,
                                       paths=h.paths, system=self.server)
        self.original = self.save("original-receipt.json", receipt)
        control.apply_client(paths=h.paths, system=self.server)
        role_stage(h, self.original, self.server)
        self.predecessor = role_server(h, self.server)
        self.server._listeners = [
            {"address": value.removeprefix("R:"), "pid": 4242} for value in control._remotes(True)[0]]
        qualification = h.qualification()
        qualification["schema"] = control.HOME_QUALIFICATION_SCHEMA
        qualification["semantics"].update(normal_remote_destination_acl=True, simultaneous_home_forwards=True)
        h.write_qualification(qualification)
        self.args = dict(source_repo=h.source, source_sha=h.commit, release_root=h.release,
                         release_commit_sha=h.commit, release_tree_sha=h.tree,
                         qualification_path=h.qualification_path,
                         predecessor_server_receipt=self.predecessor, paths=h.paths, system=self.system)

    def save(self, name, value):
        path = self.h.root / name
        path.write_bytes(control.canonical(value))
        _own(path, 0o600)
        return path

    def stage(self):
        return control.stage_home(**self.args)

    def server_apply(self, apply=True):
        bundle = control._home_area(self.paths) / "server-bundle.json"
        return control.home_server(bundle_path=bundle, expected_digest=control.digest(bundle.read_bytes()),
                                   apply=apply, paths=self.paths, system=self.server)

    def grant(self):
        return self.save("home-grant.json", self.server_apply())

    def client(self, grant=None, **actions):
        return control.home_client(paths=self.paths, system=self.system, server_receipt=grant, **actions)


@pytest.fixture
def home(harness):
    return HomeHarness(harness)


def test_home_normal_acl_preserves_all_original_entries_and_ssh():
    before = {**INCUMBENT, AUTH: [SSH_ACL, r"^127\.0\.0\.1:8080$"]}
    entries, after = control._home_merge_authfile(control.canonical(before), control.digest(AUTH.encode()))
    assert entries == before and set(after) == set(before)
    assert after[AUTH] == before[AUTH] + list(control.HOME_REGEXES)
    assert all(after[key] == value for key, value in before.items() if key != AUTH)
    import re
    for pattern, remote in zip(control.HOME_REGEXES, control.HOME_DESTINATIONS):
        assert re.search(pattern, remote)
        for refused in ("R:" + remote, remote + "0", remote.replace("127.", "128."), "0.0.0.0:50142"):
            assert not re.search(pattern, refused)
    assert control.HOME_CANDIDATE.count(control.HOME_SSH_REMOTE.encode()) == 1
    assert all(value.encode() in control.HOME_CANDIDATE for value in control.HOME_REMOTES)


@pytest.mark.parametrize("entries,identity,reason", [
    ({**INCUMBENT, AUTH: [SSH_ACL]}, "0" * 64, "not unique"),
    ({**INCUMBENT, AUTH: [r"^R:127\.0\.0\.1:2223$"]}, control.digest(AUTH.encode()), "SSH grant"),
    ({**INCUMBENT, AUTH: [SSH_ACL, r"^127\.0\.0\.2:50142$"]}, control.digest(AUTH.encode()), "already granted"),
    ({**INCUMBENT, AUTH: [SSH_ACL], "foreign:" + "x" * 48: [r"^127\.0\.0\.3:50142$"]},
     control.digest(AUTH.encode()), "already granted"),
])
def test_home_acl_refuses_foreign_or_inexact_predecessor(entries, identity, reason):
    raw = control.canonical(entries)
    with pytest.raises(ValueError, match=reason) as error:
        control._home_merge_authfile(raw, identity)
    assert AUTH not in str(error.value) and control.canonical(entries) == raw


def test_home_successor_reuses_existing_unit_credential_and_reverse_journals(home):
    paths = home.paths
    credential = control._home_credential(paths)
    unit = control._capture_preimage(paths.home_unit_file)
    journals = {name: (paths.server_operation_root / name / "server-receipt.json").read_bytes()
                for name in ("operation", "operation-hermes-v2")}
    assert home.stage()["state"] == "STAGED"
    bundle = (control._home_area(paths) / "server-bundle.json").read_bytes()
    assert AUTH.encode() not in bundle
    grant = home.grant()
    assert home.client(grant, apply=True)["state"] == "FILE_APPLIED"
    assert home.system.restarts == 0
    assert home.client(restart=True)["state"] == "RESTART_RECONCILE_REQUIRED"
    result = home.client()
    assert result["state"] == "STARTED" and result["tunnel_proven"] is False
    assert result["application_proven"] is False and result["provider_effects_settled"] is False
    assert home.client(restart=True)["state"] == "STARTED" and home.system.restarts == 1
    assert control._home_credential(paths) == credential
    assert control._capture_preimage(paths.home_unit_file) == unit
    for name, raw in journals.items():
        assert (paths.server_operation_root / name / "server-receipt.json").read_bytes() == raw
    entries = json.loads(paths.server_authfile.read_bytes())
    assert entries[AUTH] == [SSH_ACL, *control.HOME_REGEXES]
    assert home.server.calls == []


def test_home_server_lost_ack_reconciles_without_rewriting(home, monkeypatch):
    home.stage()
    install = control._install
    calls = []
    def lost_ack(path, *args, **kwargs):
        calls.append(path)
        install(path, *args, **kwargs)
        raise OSError("fixture lost original acknowledgement")
    monkeypatch.setattr(control, "_install", lost_ack)
    with pytest.raises(OSError):
        home.server_apply()
    assert home.server_apply(False)["state"] == "GRANT_FILE_APPLIED"
    assert home.server_apply()["state"] == "GRANT_FILE_APPLIED"
    assert calls == [home.paths.server_authfile]


def test_home_client_lost_ack_reconciles_without_republishing(home, monkeypatch):
    home.stage()
    grant = home.grant()
    install = control._install
    calls = []
    def lost_ack(path, *args, **kwargs):
        calls.append(path)
        install(path, *args, **kwargs)
        raise OSError("fixture lost original acknowledgement")
    monkeypatch.setattr(control, "_install", lost_ack)
    with pytest.raises(OSError):
        home.client(grant, apply=True)
    assert home.client()["state"] == "FILE_APPLIED"
    assert home.client(apply=True)["state"] == "FILE_APPLIED"
    assert calls == [home.paths.home_launcher]
    assert home.system.restarts == 0


def test_home_stage_partial_payload_resumes_same_intent(home, monkeypatch):
    original = control._write_once
    def interrupted(area, name, raw):
        if name == "launcher-after.sh":
            raise OSError("fixture interrupted stage")
        return original(area, name, raw)
    monkeypatch.setattr(control, "_write_once", interrupted)
    with pytest.raises(OSError):
        home.stage()
    intent = (control._home_area(home.paths) / "intent.json").read_bytes()
    monkeypatch.setattr(control, "_write_once", original)
    assert home.stage()["state"] == "STAGED"
    assert (control._home_area(home.paths) / "intent.json").read_bytes() == intent


@pytest.mark.parametrize("target", ["credential", "launcher", "unit"])
def test_home_equal_bytes_new_inode_is_not_adopted(home, target):
    home.stage()
    grant = home.grant()
    home.client(grant, apply=True)
    path = {"credential": home.paths.home_credential, "launcher": home.paths.home_launcher,
            "unit": home.paths.home_unit_file}[target]
    temporary = path.with_suffix(".fixture-replaced")
    temporary.write_bytes(path.read_bytes())
    _own(temporary, path.stat().st_mode & 0o777)
    os.replace(temporary, path)
    with pytest.raises(ValueError):
        home.client(restart=True)
    assert home.system.restarts == 0


def test_home_authfile_equal_bytes_new_inode_refuses_first_publication(home):
    home.stage()
    path = home.paths.server_authfile
    replacement = path.with_suffix(".fixture")
    replacement.write_bytes(path.read_bytes())
    _own(replacement, 0o600)
    os.replace(replacement, path)
    with pytest.raises(ValueError, match="preimage"):
        home.server_apply()


def test_home_active_ssh_stream_refuses_transition_without_restart_intent(home):
    home.stage()
    home.client(home.grant(), apply=True)
    home.system.streams = True
    with pytest.raises(ValueError, match="active consumer"):
        home.client(restart=True)
    assert not (control._home_area(home.paths) / "restart-intent.json").exists()
    assert home.system.restarts == 0


def test_home_restart_lost_ack_uses_original_observation_without_second_command(home, monkeypatch):
    home.stage()
    home.client(home.grant(), apply=True)
    original = home.system.restart_home
    def lost_ack():
        original()
        raise subprocess.TimeoutExpired("fixture original systemctl", 1)
    monkeypatch.setattr(home.system, "restart_home", lost_ack)
    assert home.client(restart=True)["command_result"]["observed_return"] is False
    assert home.client()["state"] == "STARTED"
    assert home.client(restart=True)["state"] == "STARTED"
    assert home.system.restarts == 1


def test_home_failed_restart_has_no_automatic_retry(home, monkeypatch):
    home.stage()
    home.client(home.grant(), apply=True)
    calls = []
    def refused():
        calls.append("original")
        return {"returncode": 1}
    monkeypatch.setattr(home.system, "restart_home", refused)
    assert home.client(restart=True)["command_result"]["returncode"] == 1
    assert home.client()["state"] == "RESTART_UNRESOLVED"
    assert home.client(restart=True)["state"] == "RESTART_UNRESOLVED"
    assert calls == ["original"]


def test_home_foreign_or_missing_role_listener_refuses_server_grant(home):
    home.stage()
    raw = home.paths.server_authfile.read_bytes()
    home.server._listeners.pop()
    with pytest.raises(ValueError, match="original role listeners"):
        home.server_apply()
    assert home.paths.server_authfile.read_bytes() == raw


def test_home_busy_original_purpose_refuses_publication(home):
    home.stage()
    with control._PurposeLock(home.paths, server=True):
        with pytest.raises(ValueError, match="busy"):
            home.server_apply()


def test_home_foreign_local_listener_refuses_launcher_publication(home):
    home.stage()
    grant = home.grant()
    home.system.extra_listeners = [{"address": "127.0.0.2:50142", "pid": 9999}]
    with pytest.raises(ValueError, match="port appeared"):
        home.client(grant, apply=True)
    assert home.paths.home_launcher.read_bytes() == control.HOME_LAUNCHER


@pytest.mark.parametrize("value", [
    "CHISEL_AUTH=home:$(id)\nCHISEL_FP=" + FINGERPRINT,
    "CHISEL_AUTH=" + AUTH + "\nCHISEL_AUTH=" + AUTH + "\nCHISEL_FP=" + FINGERPRINT,
    "CHISEL_AUTH=" + AUTH + "\nCHISEL_FP=" + FINGERPRINT + "\nEXTRA=value",
])
def test_home_credential_shell_syntax_and_ambiguous_keys_are_refused(home, value):
    home.paths.home_credential.write_text(value)
    with pytest.raises(ValueError) as error:
        home.stage()
    assert AUTH not in str(error.value)


@pytest.mark.parametrize("semantic", ["normal_remote_destination_acl", "simultaneous_home_forwards"])
def test_home_requires_forward_semantics_beyond_reverse_qualification(home, semantic):
    record = json.loads(home.h.qualification_path.read_bytes())
    record["semantics"][semantic] = False
    home.h.write_qualification(record)
    with pytest.raises(ValueError, match="semantics"):
        home.stage()


def test_home_cli_has_no_endpoint_identity_or_lifecycle_selector():
    choices = control.build_parser()._subparsers._group_actions[0].choices
    for name in ("stage-home", "apply-home-server", "reconcile-home-server",
                 "apply-home-client", "reconcile-home-client", "restart-home-client"):
        options = {option for action in choices[name]._actions for option in action.option_strings}
        assert not options & {"--unit", "--uid", "--host", "--port", "--auth", "--identity",
                              "--credential", "--command", "--key", "--remote", "--retry"}


def test_home_foreign_candidate_before_publication_intent_cannot_be_adopted(home):
    home.stage()
    grant = home.grant()
    home.paths.home_launcher.write_bytes(control.HOME_CANDIDATE)
    _own(home.paths.home_launcher, 0o755)
    with pytest.raises(ValueError, match="without original client publication intent"):
        home.client(grant, apply=True)
    assert not (control._home_area(home.paths) / "client-receipt.json").exists()
    assert home.system.restarts == 0


def test_home_lost_ack_nonexecutable_candidate_is_not_adopted_or_restarted(home, monkeypatch):
    home.stage()
    grant = home.grant()
    install = control._install
    def lost_ack(path, *args, **kwargs):
        install(path, *args, **kwargs)
        os.chmod(path, 0o644)
        raise OSError("fixture lost acknowledgement with metadata drift")
    monkeypatch.setattr(control, "_install", lost_ack)
    with pytest.raises(OSError):
        home.client(grant, apply=True)
    with pytest.raises(ValueError, match="candidate executable custody"):
        home.client(restart=True)
    assert not (control._home_area(home.paths) / "client-receipt.json").exists()
    assert home.system.restarts == 0


def test_home_owner_resolves_the_closed_existing_account_by_name(monkeypatch):
    requested = []
    def named_account(name):
        requested.append(name)
        return SimpleNamespace(pw_name=name, pw_uid=os.geteuid(), pw_gid=os.getegid())
    monkeypatch.setattr(control.pwd, "getpwnam", named_account)
    assert control._home_owner(control.Paths()) == {
        "name": "longr", "uid": os.geteuid(), "gid": os.getegid()}
    assert requested == ["longr"]


def test_home_missing_named_account_refuses_staging(home, monkeypatch):
    before = home.paths.home_launcher.read_bytes()
    def absent(_name):
        raise KeyError
    monkeypatch.setattr(control.pwd, "getpwnam", absent)
    with pytest.raises(ValueError, match="account unavailable"):
        home.stage()
    assert home.paths.home_launcher.read_bytes() == before
    assert not (control._home_area(home.paths) / "intent.json").exists()
    assert home.system.restarts == 0


@pytest.mark.parametrize("changed", ["uid", "gid"])
def test_home_named_account_change_refuses_existing_stage(home, monkeypatch, changed):
    home.stage()
    grant = home.grant()
    before = home.paths.home_launcher.read_bytes()
    account = control.pwd.getpwnam(home.paths.home_user)
    changed_account = SimpleNamespace(
        pw_name=account.pw_name,
        pw_uid=account.pw_uid + (changed == "uid"),
        pw_gid=account.pw_gid + (changed == "gid"))
    monkeypatch.setattr(control.pwd, "getpwnam", lambda _name: changed_account)
    with pytest.raises(ValueError, match="credential custody refused"):
        home.client(grant, apply=True)
    assert home.paths.home_launcher.read_bytes() == before
    assert not (control._home_area(home.paths) / "client-intent.json").exists()
    assert home.system.restarts == 0

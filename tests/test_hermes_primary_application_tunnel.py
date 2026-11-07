"""Closed role aliases through the original finite transport owner.

Real sealed files, source/manifest hashes, locks and publication/reconciliation;
only OS daemon/process observations are substituted. No real account or tunnel.
"""
import json
import os
from pathlib import Path
import subprocess

import pytest

from ops.executive_os import application_tunnel_control as control
from ops.executive_os import os_tunnel_entry as entry
from tests.test_application_tunnel_control import (
    FakeSystem, FINGERPRINT, INCUMBENT, _own, harness, sealed_root,
)


class RoleSystem(FakeSystem):
    role_aliases = False

    def process_matches(self, pid, expected):
        if pid == self.unit.get("main_pid"):
            return self.unit.get("argv") == expected
        for loaded, info in self._launchd.values():
            if loaded and type(pid) is int and pid > 0 and info.get("pid") == pid:
                remotes = entry.APPLICATION_ROLE_TARGETS if self.role_aliases else (control.REVERSE_TARGET,)
                return expected[0].endswith("/chisel") and expected[1:] == [
                    "client", "--fingerprint", FINGERPRINT, "--keepalive", "20s", control.SERVER, *remotes]
        return False


def original(harness, *, start=False):
    harness.stage()
    receipt = harness.server_receipt()
    system = RoleSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    control.apply_client(paths=harness.paths, system=system)
    if start:
        control.start_client(server_receipt=receipt, paths=harness.paths, system=system)
    return receipt, system


def role_stage(harness, receipt, system):
    qualification = harness.qualification()
    qualification["schema"] = control.ROLE_QUALIFICATION_SCHEMA
    qualification["semantics"]["simultaneous_closed_role_remotes"] = True
    harness.write_qualification(qualification)
    return harness.stage(role_aliases=True, predecessor_server_receipt=receipt, system=system)


def role_server(harness, system):
    bundle = control._stage_directory(harness.paths, True) / "server-bundle.json"
    result = control.apply_server(bundle_path=bundle, expected_digest=control.digest(bundle.read_bytes()),
                                  paths=harness.paths, system=system)
    receipt = harness.root / "role-server-receipt.json"
    receipt.write_bytes(control.canonical(result))
    _own(receipt, 0o600)
    return receipt


def test_role_compiler_uses_one_original_identity_and_exact_three_remotes():
    config = {"schema": entry.APPLICATION_ROLE_SCHEMA, "binary_sha256": "b" * 64,
              "server_fingerprint": FINGERPRINT}
    credential = b"mastermind-fabric-app:" + b"s" * 48
    binary, argv, env = entry.application_launch_spec(config, credential)
    assert argv == [binary, "client", "--fingerprint", FINGERPRINT, "--keepalive", "20s",
                    control.SERVER, *entry.APPLICATION_ROLE_TARGETS]
    assert env["AUTH"].encode() == credential and credential.decode() not in json.dumps(argv)
    assert control.operation_identity() == control.operation_identity(False)
    assert control.operation_identity(True) != control.operation_identity()
    for key in ("host", "port", "remotes", "credential", "label"):
        with pytest.raises(ValueError):
            entry.application_launch_spec({**config, key: "arbitrary"}, credential)
    with pytest.raises(ValueError):
        control._remotes("true")


def test_role_successor_preserves_credential_inode_and_original_journals(harness):
    receipt, system = original(harness, start=True)
    identity = control._capture_preimage(harness.paths.credential)
    first_stage = (harness.paths.operation_root / "stage/stage.json").read_bytes()
    first_server = (harness.paths.server_operation_root / "operation/server-receipt.json").read_bytes()
    staged = role_stage(harness, receipt, system)
    assert staged["operation_id"] == control.operation_identity(True)
    with pytest.raises(ValueError, match="stop the original"):
        control.apply_client(role_aliases=True, paths=harness.paths, system=system)
    control.stop_client(paths=harness.paths, system=system)
    server = role_server(harness, system)
    result = control.apply_client(role_aliases=True, server_receipt=server, paths=harness.paths, system=system)
    assert result["targets"]["credential"] == "ALREADY_APPLIED"
    assert control._capture_preimage(harness.paths.credential) == identity
    system.role_aliases = True
    started = control.start_client(role_aliases=True, server_receipt=server, paths=harness.paths, system=system)
    assert started["state"] == "STARTED" and started["provider_effects_settled"] is False
    assert control.start_client(role_aliases=True, server_receipt=server,
                               paths=harness.paths, system=system)["state"] == "ALREADY_STARTED"
    assert control.reconcile(role_aliases=True, paths=harness.paths, system=system)["service_state"] == "STARTED"
    assert system.calls == [("bootstrap", str(harness.paths.plist)), ("bootout", control.LABEL),
                            ("bootstrap", str(harness.paths.plist))]
    assert (harness.paths.operation_root / "stage/stage.json").read_bytes() == first_stage
    assert (harness.paths.server_operation_root / "operation/server-receipt.json").read_bytes() == first_server
    entries = json.loads(harness.paths.server_authfile.read_bytes())
    assert all(entries[key] == value for key, value in INCUMBENT.items())
    auth = harness.paths.credential.read_text()
    assert entries[auth] == list(entry.APPLICATION_ROLE_REGEXES)
    assert json.loads(server.read_bytes())["preserved_entries"] == len(INCUMBENT)


def test_role_client_stage_requires_no_server_filesystem(harness):
    receipt, system = original(harness)
    harness.paths.server_operation_root.rename(harness.paths.server_operation_root.with_name("server-held-away"))
    harness.paths.server_authfile.rename(harness.paths.server_authfile.with_name("users-held-away.json"))
    assert role_stage(harness, receipt, system)["state"] == "STAGED"
    assert control.reconcile(role_aliases=True, paths=harness.paths, system=system)["targets"] == {
        "config": "NOT_APPLIED", "credential": "NOT_APPLIED", "plist": "NOT_APPLIED"}


def test_role_successor_accepts_actual_predecessor_cli_receipt(harness, capsys):
    _, system = original(harness)
    bundle = control._stage_directory(harness.paths) / "server-bundle.json"
    assert control.main(["reconcile-server", "--bundle", str(bundle), "--expected-digest",
        control.digest(bundle.read_bytes())], paths=harness.paths, system=system) == 0
    carried = capsys.readouterr().out
    assert carried.endswith("\n")
    receipt = harness.root / "carried-original-cli-receipt.json"
    receipt.write_text(carried)
    _own(receipt, 0o600)
    role_stage(harness, receipt, system)
    assert json.loads(role_server(harness, system).read_bytes())["state"] == "GRANT_FILE_APPLIED"


def test_unknown_original_start_never_authorizes_role_successor(harness):
    receipt, system = original(harness)
    system.autoload = False
    with pytest.raises(ValueError, match="outcome is unknown"):
        control.start_client(server_receipt=receipt, paths=harness.paths, system=system)
    with pytest.raises(ValueError, match="lifecycle is unresolved"):
        role_stage(harness, receipt, system)
    assert len(system.calls) == 1
    assert not (control._stage_directory(harness.paths, True) / "intent.json").exists()


def test_known_absence_reconciles_original_uncertain_stop_without_replay(harness, monkeypatch):
    receipt, system = original(harness, start=True)
    bootout = system.launchctl_bootout

    def lost_ack(label):
        bootout(label)
        raise subprocess.TimeoutExpired("fixture-original-stop", 1)

    monkeypatch.setattr(system, "launchctl_bootout", lost_ack)
    with pytest.raises(ValueError, match="outcome is unknown"):
        control.stop_client(paths=harness.paths, system=system)
    old = harness.paths.operation_root / "stage/operation/stop-receipt.json"
    assert json.loads(old.read_bytes())["state"] == "STOP_UNKNOWN"
    role_stage(harness, receipt, system)
    control.apply_client(role_aliases=True, paths=harness.paths, system=system)
    assert sum(kind == "bootout" for kind, _ in system.calls) == 1
    assert json.loads(old.read_bytes())["state"] == "STOP_UNKNOWN"


def test_role_credential_replacement_with_equal_bytes_is_not_adopted(harness):
    receipt, system = original(harness)
    role_stage(harness, receipt, system)
    path = harness.paths.credential
    replacement = path.with_name("fixture-foreign.auth")
    replacement.write_bytes(path.read_bytes())
    _own(replacement, 0o400)
    os.replace(replacement, path)
    with pytest.raises(ValueError, match="credential identity changed"):
        control.apply_client(role_aliases=True, paths=harness.paths, system=system)
    assert not (control._stage_directory(harness.paths, True) / "operation").exists()


def test_role_partial_client_publication_recovers_from_original_v2_intent(harness, monkeypatch):
    receipt, system = original(harness)
    role_stage(harness, receipt, system)
    real_install = control._install
    credential_identity = control._capture_preimage(harness.paths.credential)

    # The fixture source already contains both contracts; only the installed
    # config changes. Interrupt after that publication and before its receipt.
    def after_config(path, *args, **kwargs):
        assert Path(path) != harness.paths.credential
        value = real_install(path, *args, **kwargs)
        if Path(path) == harness.paths.config:
            raise OSError("fixture loses config publication acknowledgement")
        return value

    monkeypatch.setattr(control, "_install", after_config)
    with pytest.raises(OSError):
        control.apply_client(role_aliases=True, paths=harness.paths, system=system)
    assert json.loads(harness.paths.config.read_bytes())["schema"] == entry.APPLICATION_ROLE_SCHEMA
    assert control.reconcile(role_aliases=True, paths=harness.paths, system=system)["targets"]["config"] == "COMMITTED_RECEIPT_MISSING"
    # Re-staging the SAME immutable operation must not recapture v1 live targets.
    assert harness.stage(role_aliases=True, system=system)["state"] == "STAGED"
    monkeypatch.setattr(control, "_install", lambda *args, **kwargs: pytest.fail("duplicate publication"))
    result = control.apply_client(role_aliases=True, paths=harness.paths, system=system)
    assert result["installed"] is True
    assert control._capture_preimage(harness.paths.credential) == credential_identity


def test_role_server_lost_ack_reconciles_original_acl_once(harness, monkeypatch):
    receipt, system = original(harness)
    role_stage(harness, receipt, system)
    real_install = control._install
    calls = []

    def lost_ack(path, *args, **kwargs):
        calls.append(Path(path))
        real_install(path, *args, **kwargs)
        raise OSError("fixture original server acknowledgement lost")

    monkeypatch.setattr(control, "_install", lost_ack)
    with pytest.raises(OSError):
        role_server(harness, system)
    bundle = control._stage_directory(harness.paths, True) / "server-bundle.json"
    result = control.reconcile_server(bundle_path=bundle, expected_digest=control.digest(bundle.read_bytes()),
                                      paths=harness.paths, system=system)
    assert result["state"] == "GRANT_FILE_APPLIED" and result["tunnel_proven"] is False
    assert calls == [harness.paths.server_authfile]


@pytest.mark.parametrize("count", [0, 1, 3])
def test_role_server_partial_listeners_do_not_claim_tunnel_proof(harness, count):
    receipt, system = original(harness)
    role_stage(harness, receipt, system)
    role_server(harness, system)
    system._listeners = [{"address": remote.removeprefix("R:"), "pid": 4242}
                         for remote in entry.APPLICATION_ROLE_REVERSES[:count]]
    bundle = control._stage_directory(harness.paths, True) / "server-bundle.json"
    args = dict(bundle_path=bundle, expected_digest=control.digest(bundle.read_bytes()),
                paths=harness.paths, system=system)
    assert control.reconcile_server(**args)["tunnel_proven"] is False
    system._listeners.append({"address": "0.0.0.0:50142", "pid": 4242})
    with pytest.raises(ValueError, match="another owner"):
        control.reconcile_server(**args)


@pytest.mark.parametrize("remote", entry.APPLICATION_ROLE_TARGETS[1:])
def test_role_only_orphan_blocks_same_purpose_client(harness, remote):
    receipt, system = original(harness)
    role_stage(harness, receipt, system)
    control.apply_client(role_aliases=True, paths=harness.paths, system=system)
    server = role_server(harness, system)
    system._processes = [{"pid": 9001, "argv": ["/fixture/chisel", "client", remote]}]
    with pytest.raises(ValueError, match="concurrent same-purpose"):
        control.start_client(role_aliases=True, server_receipt=server, paths=harness.paths, system=system)
    assert system.calls == []


def test_role_successor_rejects_other_alias_grants_and_credential_rotation(harness):
    receipt, system = original(harness)
    role_stage(harness, receipt, system)
    with pytest.raises(ValueError, match="cannot replace the credential"):
        harness.stage(role_aliases=True, credential_path=receipt, system=system)
    entries = json.loads(harness.paths.server_authfile.read_bytes())
    entries["other:fixture"] = [entry.APPLICATION_ROLE_REGEXES[1]]
    with pytest.raises(ValueError, match="existing grant"):
        control._merge_authfile(control.canonical(entries), harness.paths.credential.read_text(), role_aliases=True)


def test_role_stage_cannot_move_into_original_slot(harness):
    receipt, system = original(harness)
    role_stage(harness, receipt, system)
    old = control._stage_directory(harness.paths)
    old.rename(old.with_name("retained-original"))
    control._stage_directory(harness.paths, True).rename(old)
    with control.publication.private(old) as area:
        with pytest.raises(ValueError, match="stage contract path"):
            control._load_stage(area, harness.paths)

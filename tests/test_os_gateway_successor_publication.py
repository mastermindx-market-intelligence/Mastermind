"""Real gateway transaction/receipt effects in disposable custody fixtures.

Host identity, launchd and installed-source observations are synthetic at the
existing fixture boundary. No production config, provider or service is used.
The compiler, receipt admission, archives, flock, CAS writes and reconciliation
run unchanged against real temporary files.
"""
from __future__ import annotations

import dataclasses
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from ops.executive_os import autonomy_control as control
from tests import test_os_gateway_publication_owner as incumbent
from tests.test_os_gateway_publication_owner import gateway, gateway_tmp_path

OLD_SHA = incumbent.SHA
NEW_SHA = "d" * 40


def replace_fixture(path, raw, mode=None):
    """Synthetic fixture preparation or an explicit modeled outside mutation."""
    selected_mode = stat.S_IMODE(path.stat().st_mode) if mode is None else mode
    path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(selected_mode)


def move_and_replace(path):
    raw = path.read_bytes()
    mode = stat.S_IMODE(path.stat().st_mode)
    path.rename(path.with_name(path.name + ".retained-original"))
    incumbent._write_sealed(path, raw, mode)


def add_existing_mounts(s):
    from integrations.business_mcp_auth.contracts import load_resource_policy
    from ops.executive_os.workspace_owner_enrollment import compile_control_room_action_bindings
    from integrations.mastermind_workspace_app.contract import CONTROL_ROOM_ACTIONS

    value = json.loads(s.mcp_bytes)
    workspace = value["workspace"]
    workspace["bindings"] = compile_control_room_action_bindings(
        load_resource_policy(workspace["policy"]), workspace["bindings"], {
            name: {action: (b"TESTDATA action: " + action.encode() if slot["enabled"] else None)
                   for action in CONTROL_ROOM_ACTIONS}
            for name, slot in workspace["bindings"]["profiles"].items()
        },
    )
    subjects = workspace["policy"]["allowed_subject_digests"]
    value["steward"] = {
        "policy": incumbent._policy(policy_id="steward-dormant", subjects=subjects,
            resource="https://mcp.mastermind-x.com/mcp/steward/v1", scopes=["mastermind.steward.read"]),
        "content_policy": incumbent._policy(policy_id="content", subjects=subjects,
            resource="https://mcp.mastermind-x.com/workspace/window/current",
            scopes=["mastermind.workspace.content.read"]),
        "content_profiles": {"schema": "mastermind.executive_content_profiles.v1", "profiles": {
            "web": {"enabled": False, "profile": None}, "mac": {"enabled": False, "profile": None}}},
        "allowed_origin": "https://mcp.mastermind-x.com",
    }
    s.mcp_bytes = control._encoded_json(value)
    replace_fixture(control.OS_GATEWAY_MCP_CONFIG, s.mcp_bytes)


def prepare_successor(s, monkeypatch, new_sha=NEW_SHA):
    """Model a new genuine installed release plus its stopped staged Studio seat.

    Only fixture setup changes source selectors; the production publication
    must preserve these Control/worker bytes and observe the real staged files.
    """
    prior = control.OS_GATEWAY_RECEIPT.read_bytes()
    monkeypatch.setattr(incumbent, "SHA", new_sha)
    staged = incumbent._stage_release(s.tmp_path / incumbent.SERVICE_ROOT,
                                     mcp_document=None, workspace_policy=None)
    studio_manifest = s.studio["base"] / "manifest.json"
    document = json.loads(studio_manifest.read_bytes())
    document["source"] = os.fspath(staged["source"])
    replace_fixture(studio_manifest, control._encoded_json(document))
    config = json.loads(control.CONTROL_CONFIG.read_bytes())
    config["proof_base_sha"] = new_sha
    replace_fixture(control.CONTROL_CONFIG, control._encoded_json(config))
    s.mcp_bytes = control.OS_GATEWAY_MCP_CONFIG.read_bytes()
    s.plist_bytes = control.OS_GATEWAY_MCP_PLIST.read_bytes()
    s.bundle = s.host.qualify_launch_publication(new_sha, incumbent.TREE_SHA)[2]
    request = s.request(
        prior_grant_absent=False,
        prior_grant_sha256=incumbent.digest(control.OS_GATEWAY_COMMISSION_GRANT.read_bytes()),
        predecessor_receipt_sha256=incumbent.digest(prior),
    )
    return request, prior


@pytest.fixture
def successor(gateway, monkeypatch):
    add_existing_mounts(gateway)
    gateway.publish()
    request, prior = prepare_successor(gateway, monkeypatch)
    return gateway, request, prior


def publish(s, request):
    return control.execute_gateway_publication(s.host, request, now=incumbent.NOW)


def history(request):
    return control.ProductionGatewayPublicationHost._gateway_receipt_history_path(
        request.predecessor_receipt_sha256)


def target_bytes(s):
    return {path: path.read_bytes() for path in (*s.target_paths(), control.OS_GATEWAY_RECEIPT)}


def assert_unchanged(s, before):
    assert target_bytes(s) == before
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_successor_archives_exact_predecessor_before_first_target_and_preserves_mounts(successor, monkeypatch):
    s, request, prior = successor
    untouched = {p: p.read_bytes() for p in (control.CONTROL_CONFIG, control.WORKER_CONFIG)}
    old_mcp = json.loads(s.mcp_bytes)
    assert old_mcp["workspace"]["bindings"]["schema"].endswith(".v3")
    old_identity = control.OS_GATEWAY_RECEIPT.stat().st_ino
    write_grant = s.host._publish_gateway_grant
    seen = []

    def first_effect(transaction, preparation):
        manifest = s.host._manifest()
        assert manifest["gateway_predecessor_receipt_sha256"] == incumbent.digest(prior)
        assert (control.AUTONOMY_TRANSACTION / control._GATEWAY_RECEIPT_ARCHIVE).read_bytes() == prior
        assert history(request).read_bytes() == prior
        assert control.OS_GATEWAY_RECEIPT.read_bytes() == prior
        assert control.OS_GATEWAY_RECEIPT.stat().st_ino == old_identity
        seen.append("retained-before-grant")
        return write_grant(transaction, preparation)

    monkeypatch.setattr(s.host, "_publish_gateway_grant", first_effect)
    result = publish(s, request)
    assert result.state == "PUBLISHED" and result.replayed is False
    assert seen == ["retained-before-grant"]
    current = json.loads(control.OS_GATEWAY_MCP_CONFIG.read_bytes())
    assert current["release_sha"] == NEW_SHA
    assert {k: v for k, v in current.items() if k != "release_sha"} == {
        k: v for k, v in old_mcp.items() if k != "release_sha"}
    assert all(p.read_bytes() == raw for p, raw in untouched.items())
    assert history(request).read_bytes() == prior
    assert stat.S_IMODE(history(request).stat().st_mode) == 0o444
    receipt = json.loads(control.OS_GATEWAY_RECEIPT.read_bytes())
    assert receipt["schema_version"] == control.OS_GATEWAY_SUCCESSOR_RECEIPT_SCHEMA
    assert receipt["predecessor_receipt_sha256"] == incumbent.digest(prior)
    assert receipt["expected_sha"] == NEW_SHA
    assert receipt["transaction_id"] == result.transaction_id
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_v2_receipt_can_be_next_exact_predecessor_without_rewriting_history(successor, monkeypatch):
    s, request, prior = successor
    publish(s, request)
    first_history = history(request)
    stamp = first_history.stat()
    next_request, second_receipt = prepare_successor(s, monkeypatch, "e" * 40)
    publish(s, next_request)
    assert first_history.read_bytes() == prior
    assert (first_history.stat().st_ino, first_history.stat().st_mtime_ns) == (stamp.st_ino, stamp.st_mtime_ns)
    assert history(next_request).read_bytes() == second_receipt
    assert json.loads(control.OS_GATEWAY_RECEIPT.read_bytes())["predecessor_receipt_sha256"] == incumbent.digest(second_receipt)


@pytest.mark.parametrize("changes", [
    {"predecessor_receipt_sha256": None},
    {"predecessor_receipt_sha256": "0" * 64},
    {"predecessor_receipt_sha256": True},
    {"predecessor_receipt_sha256": "not-a-digest"},
    {"prior_grant_absent": True},
    {"prior_grant_sha256": None},
    {"prior_grant_sha256": "0" * 64},
    {"prior_mcp_config_sha256": "0" * 64},
    {"prior_mcp_plist_sha256": "0" * 64},
    {"expected_sha": OLD_SHA},
])
def test_successor_requires_explicit_exact_predecessor_and_every_current_postimage(successor, changes):
    s, request, _prior = successor
    before = target_bytes(s)
    with pytest.raises(control.GatewayPublicationError):
        publish(s, dataclasses.replace(request, **changes))
    assert_unchanged(s, before)
    assert not history(request).exists()


@pytest.mark.parametrize("field,value", [
    ("schema_version", "foreign"), ("state", "UNKNOWN"), ("operation", "ARM"),
    ("transaction_id", "not-an-original-id"), ("observed_at", "not-a-time"),
    ("tool_version", "foreign"), ("expected_sha", "e" * 40),
    ("release_bundle_digest", "f" * 64), ("prior_commission_grant_present", 1),
    ("extra", "not-in-schema"), ("predecessor_receipt_sha256", "f" * 64),
])
def test_predecessor_receipt_semantics_are_not_replaced_by_its_supplied_hash(successor, field, value):
    s, request, prior = successor
    forged = dict(json.loads(prior), **{field: value})
    raw = control._encoded_json(forged)
    replace_fixture(control.OS_GATEWAY_RECEIPT, raw)
    request = dataclasses.replace(request, predecessor_receipt_sha256=incumbent.digest(raw))
    before = target_bytes(s)
    with pytest.raises(control.GatewayPublicationError):
        publish(s, request)
    assert_unchanged(s, before)


@pytest.mark.parametrize("mode", [0o400, 0o600, 0o644, 0o666])
def test_wrong_predecessor_custody_refuses_before_intent(successor, mode):
    s, request, _prior = successor
    control.OS_GATEWAY_RECEIPT.chmod(mode)
    before = target_bytes(s)
    with pytest.raises(control.GatewayPublicationError):
        publish(s, request)
    assert_unchanged(s, before)


@pytest.mark.parametrize("case", ["symlink", "hardlink", "acl"])
def test_predecessor_namespace_and_acl_custody_cannot_be_replaced_by_the_digest(successor, monkeypatch, case):
    s, request, _prior = successor
    path = control.OS_GATEWAY_RECEIPT
    if case == "symlink":
        saved = path.with_name("retained-predecessor.json")
        path.rename(saved)
        path.symlink_to(saved)
    elif case == "hardlink":
        os.link(path, path.with_name("extra-link.json"))
    else:
        original = control._has_acl
        monkeypatch.setattr(control, "_has_acl", lambda value: value == path or original(value))
    before = target_bytes(s)
    with pytest.raises(control.GatewayPublicationError):
        publish(s, request)
    assert_unchanged(s, before)


def test_absent_predecessor_cannot_fall_back_to_first_publication(successor):
    s, request, _prior = successor
    control.OS_GATEWAY_RECEIPT.unlink()
    before = {p: p.read_bytes() for p in s.target_paths()}
    with pytest.raises(control.GatewayPublicationError):
        publish(s, request)
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert not control.OS_GATEWAY_RECEIPT.exists()
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_existing_archive_is_not_overwritten_or_treated_as_replay(successor):
    s, request, prior = successor
    incumbent._write_sealed(history(request), prior)
    before = target_bytes(s)
    inode = history(request).stat().st_ino
    with pytest.raises(control.GatewayPublicationError):
        publish(s, request)
    assert_unchanged(s, before)
    assert history(request).read_bytes() == prior and history(request).stat().st_ino == inode


@pytest.mark.parametrize("when", ["qualification", "intent", "before-receipt"])
def test_same_bytes_new_inode_cannot_satisfy_predecessor_cas(successor, monkeypatch, when):
    s, request, prior = successor
    before = target_bytes(s)
    if when == "qualification":
        original = s.host.qualify_gateway_predecessor
        def changed(*args):
            move_and_replace(control.OS_GATEWAY_RECEIPT)
            return original(*args)
        monkeypatch.setattr(s.host, "qualify_gateway_predecessor", changed)
        error = control.GatewayPublicationError
    elif when == "intent":
        original = s.host._recheck_gateway_preimages
        def changed(*args):
            move_and_replace(control.OS_GATEWAY_RECEIPT)
            return original(*args)
        monkeypatch.setattr(s.host, "_recheck_gateway_preimages", changed)
        error = control.TransactionEffectUnknown
    else:
        monkeypatch.setattr(s.host, "_qualify_published_gateway",
                            lambda manifest: move_and_replace(control.OS_GATEWAY_RECEIPT))
        error = control.TransactionEffectUnknown
    with pytest.raises(error):
        publish(s, request)
    assert control.OS_GATEWAY_RECEIPT.read_bytes() == prior
    if when == "qualification":
        assert_unchanged(s, before)
    else:
        assert control.AUTONOMY_TRANSACTION.exists()
        assert (control.AUTONOMY_TRANSACTION / control._GATEWAY_RECEIPT_ARCHIVE).read_bytes() == prior
        if when == "intent":
            assert target_bytes(s) == before
        else:
            assert history(request).read_bytes() == prior


def test_receipt_disappearance_after_grant_keeps_partial_effect_unknown(successor, monkeypatch):
    s, request, prior = successor
    original = s.host._publish_gateway_grant
    def changed(*args):
        original(*args)
        control.OS_GATEWAY_RECEIPT.unlink()
    monkeypatch.setattr(s.host, "_publish_gateway_grant", changed)
    with pytest.raises(control.TransactionEffectUnknown):
        publish(s, request)
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == s.mcp_bytes
    assert control.OS_GATEWAY_MCP_PLIST.read_bytes() == s.plist_bytes
    assert history(request).read_bytes() == prior
    assert control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_RECEIPT.exists()


def test_same_bytes_archive_replacement_after_grant_is_not_terminal_proof(successor, monkeypatch):
    s, request, _prior = successor
    original = s.host._publish_gateway_grant
    def changed(*args):
        original(*args)
        move_and_replace(history(request))
    monkeypatch.setattr(s.host, "_publish_gateway_grant", changed)
    with pytest.raises(control.TransactionEffectUnknown):
        publish(s, request)
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == s.mcp_bytes
    assert control.AUTONOMY_TRANSACTION.exists()


def test_predecessor_namespace_change_during_final_cas_read_is_not_overwritten(successor, monkeypatch):
    s, request, prior = successor
    original_read = control._read_root_file
    original_write = s.host.write_gateway_receipt
    armed = False
    def race(path, **kwargs):
        nonlocal armed
        result = original_read(path, **kwargs)
        if armed and path == control.OS_GATEWAY_RECEIPT:
            armed = False
            move_and_replace(path)
        return result
    def final_write(*args):
        nonlocal armed
        armed = True
        return original_write(*args)
    monkeypatch.setattr(control, "_read_root_file", race)
    monkeypatch.setattr(s.host, "write_gateway_receipt", final_write)
    with pytest.raises(control.TransactionEffectUnknown):
        publish(s, request)
    assert control.OS_GATEWAY_RECEIPT.read_bytes() == prior
    assert control.AUTONOMY_TRANSACTION.exists()


def test_predecessor_replacement_during_final_metadata_check_is_not_overwritten(successor, monkeypatch):
    s, request, prior = successor
    original = control._receipt_metadata
    def race(path):
        result = original(path)
        if path == control.OS_GATEWAY_RECEIPT:
            move_and_replace(path)
        return result
    monkeypatch.setattr(control, "_receipt_metadata", race)
    with pytest.raises(control.TransactionEffectUnknown):
        publish(s, request)
    assert control.OS_GATEWAY_RECEIPT.read_bytes() == prior
    assert control.AUTONOMY_TRANSACTION.exists()


def lose_terminal_ack(s, request, monkeypatch):
    original = s.host.write_gateway_receipt
    def lost(*args):
        original(*args)
        raise RuntimeError("TESTDATA lost write acknowledgement")
    monkeypatch.setattr(s.host, "write_gateway_receipt", lost)
    with pytest.raises(control.TransactionEffectUnknown):
        publish(s, request)
    manifest = s.host._manifest()
    s.teardown()
    return manifest


def test_lost_successor_receipt_ack_is_proven_without_rewriting_either_receipt(successor, monkeypatch):
    s, request, prior = successor
    manifest = lose_terminal_ack(s, request, monkeypatch)
    current = control.OS_GATEWAY_RECEIPT.read_bytes()
    inode = control.OS_GATEWAY_RECEIPT.stat().st_ino
    fresh = s.fresh_host(monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError("reconciliation must never publish or reissue proof")
    monkeypatch.setattr(fresh, "write_gateway_receipt", forbidden)
    monkeypatch.setattr(fresh, "_retain_gateway_predecessor", forbidden)
    result = s.reconcile(host=fresh, transaction_id=manifest["transaction_id"])
    assert result == manifest["transaction_id"]
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert control.OS_GATEWAY_RECEIPT.read_bytes() == current
    assert control.OS_GATEWAY_RECEIPT.stat().st_ino == inode
    assert history(request).read_bytes() == prior


@pytest.mark.parametrize("which,mutation", [
    ("history", "missing"), ("history", "bytes"), ("history", "mode"), ("history", "same-bytes"),
    ("transaction", "missing"), ("transaction", "bytes"),
    ("current", "missing"), ("current", "predecessor"),
])
def test_lost_ack_with_missing_or_drifted_proof_stays_unknown(successor, monkeypatch, which, mutation):
    s, request, prior = successor
    manifest = lose_terminal_ack(s, request, monkeypatch)
    path = {"history": history(request), "transaction": control.AUTONOMY_TRANSACTION / control._GATEWAY_RECEIPT_ARCHIVE,
            "current": control.OS_GATEWAY_RECEIPT}[which]
    if mutation == "missing":
        path.unlink()
    elif mutation == "mode":
        path.chmod(0o644)
    elif mutation == "same-bytes":
        move_and_replace(path)
    else:
        replace_fixture(path, prior if mutation == "predecessor" else b"not-original\n")
    fresh = s.fresh_host(monkeypatch)
    try:
        with pytest.raises((control.TransactionEffectUnknown, control.GatewayPublicationError)):
            s.reconcile(host=fresh, transaction_id=manifest["transaction_id"])
        assert control.AUTONOMY_TRANSACTION.exists()
    finally:
        if fresh._transaction_owner_fd is not None:
            fresh._release_transaction_owner()


def test_lost_archive_ack_preserves_original_intent_and_no_target_effect(successor, monkeypatch):
    s, request, prior = successor
    before = target_bytes(s)
    original = s.host._retain_gateway_predecessor
    def lost(*args):
        original(*args)
        raise OSError("TESTDATA lost archive acknowledgement")
    monkeypatch.setattr(s.host, "_retain_gateway_predecessor", lost)
    with pytest.raises(control.TransactionEffectUnknown):
        publish(s, request)
    assert target_bytes(s) == before
    assert history(request).read_bytes() == prior
    assert control.AUTONOMY_TRANSACTION.exists()
    with pytest.raises(control.GatewayPublicationError):
        publish(s, request)
    assert target_bytes(s) == before


def test_archive_write_without_retained_identity_cannot_be_recreated_or_adopted(successor, monkeypatch):
    s, request, prior = successor
    before = target_bytes(s)
    original = s.host._persist_phase
    def lost(transaction, phase, **kwargs):
        if phase == "PREDECESSOR_RECEIPT_RETAINED":
            raise OSError("TESTDATA archive exists but phase acknowledgement was lost")
        return original(transaction, phase, **kwargs)
    monkeypatch.setattr(s.host, "_persist_phase", lost)
    with pytest.raises(control.TransactionEffectUnknown):
        publish(s, request)
    manifest = s.host._manifest()
    assert manifest["phase"] == "LOCKED" and manifest["gateway_predecessor_archive_identity"] is None
    assert history(request).read_bytes() == prior
    assert target_bytes(s) == before
    with pytest.raises(control.TransactionEffectUnknown):
        s.reconcile(transaction_id=manifest["transaction_id"])
    assert target_bytes(s) == before and history(request).read_bytes() == prior
    assert control.AUTONOMY_TRANSACTION.exists()
    with pytest.raises(control.GatewayPublicationError):
        publish(s, request)
    assert target_bytes(s) == before


def test_successor_cli_uses_existing_typed_dispatcher(successor, capsys):
    s, request, _prior = successor
    argv = ["publish-os-gateway", "--expected-sha", request.expected_sha,
            "--expected-bundle-digest", request.bundle_digest,
            "--expected-mcp-config-sha256", request.prior_mcp_config_sha256,
            "--expected-mcp-plist-sha256", request.prior_mcp_plist_sha256,
            "--expected-grant-sha256", request.prior_grant_sha256,
            "--expected-predecessor-receipt-sha256", request.predecessor_receipt_sha256]
    assert control.main(argv, host=s.host, now=lambda: incumbent.NOW) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["code"] == "os_gateway_published" and output["replayed"] is False
    assert request.predecessor_receipt_sha256 not in json.dumps(output)


def test_v2_publication_passes_existing_gateway_restart_preflight(successor, monkeypatch):
    from ops.executive_os import gateway_refresh_preflight
    s, request, _prior = successor
    incumbent._normal_gateway_qualifier_fixture(s, monkeypatch)
    publish(s, request)
    value = gateway_refresh_preflight.qualify_gateway_refresh(NEW_SHA)
    assert value["release_sha"] == NEW_SHA
    assert value["config_sha256"] == incumbent.digest(control.OS_GATEWAY_MCP_CONFIG.read_bytes())
    assert json.loads(control.OS_GATEWAY_RECEIPT.read_bytes())["schema_version"] == control.OS_GATEWAY_SUCCESSOR_RECEIPT_SCHEMA


def test_shell_successor_flag_is_closed_and_never_a_reconcile_selector(tmp_path):
    source = (Path(__file__).parents[1] / "ops/executive_os/service-control.sh").read_text()
    function = source.split("os_gateway_args() {", 1)[1].split("\ndispatch_os_gateway()", 1)[0]
    script = tmp_path / "parse-only.sh"
    script.write_text("os_gateway_args() {" + function + '\nos_gateway_args "$@"\n')
    base = ["publish-os-gateway", "--expected-sha", NEW_SHA, "--expected-bundle-digest", "1" * 64,
            "--expected-mcp-config-sha256", "2" * 64, "--expected-mcp-plist-sha256", "3" * 64]
    flag = ["--expected-predecessor-receipt-sha256", "4" * 64]
    valid = base + ["--expected-grant-sha256", "5" * 64] + flag
    assert subprocess.run(["/bin/bash", str(script), *valid], capture_output=True, timeout=5).returncode == 0
    invalid = [base + ["--expected-grant-absent"] + flag, valid + flag,
               valid[:-1] + ["not-a-sha"],
               ["reconcile-os-gateway", "--expected-sha", NEW_SHA, "--expected-bundle-digest", "1" * 64,
                "--transaction-id", "autonomy-" + "2" * 12, *flag]]
    for argv in invalid:
        assert subprocess.run(["/bin/bash", str(script), *argv], capture_output=True, timeout=5).returncode != 0
        # The contradictory grant expectation is refused by the real owner
        # before intent (covered above); argparse owns the other closed cases.
        if "--expected-grant-absent" not in argv:
            with pytest.raises(SystemExit):
                control._parser().parse_args(argv)

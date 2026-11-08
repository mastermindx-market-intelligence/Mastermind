"""Conditional gateway source adoption in the incumbent disposable owner fixture.

Root/launchd/source identities remain the incumbent explicit TESTDATA premises.
No installed receipt, config, service, credential or provider is accessed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from ops.executive_os import autonomy_control as control
from ops.executive_os import mcp_component_update as component
from ops.executive_os import os_gateway_publication as compiler
from tests import test_os_gateway_publication as pure
from tests import test_os_gateway_publication_owner as owner
from tests.test_os_gateway_publication_owner import gateway, gateway_tmp_path
from tests.test_mcp_component_update import _coo_block, _mission_document, PRINCIPAL_PROFILE
from tests.os_gateway_policy_mount_fixtures import replace_fixture


def registry_at(root, *, enabled=True, schema_digest=None):
    value = json.loads((Path(__file__).resolve().parents[1] /
        'config/executive_claude_principal_capabilities.json').read_bytes())
    value['profiles'][PRINCIPAL_PROFILE]['enabled'] = enabled
    if schema_digest is not None:
        value['mcp_servers']['mastermind-executive-coo-v1']['tool_schema_digest'] = schema_digest
    path = root / 'config/executive_claude_principal_capabilities.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.chmod(0o600)
    path.write_text(json.dumps(value))
    path.chmod(0o444)
    return ExecutionCapabilityRegistry.load(path, source_root=root).profiles[PRINCIPAL_PROFILE].profile_digest


def add_mission(s, digest):
    value = json.loads(s.mcp_bytes)
    coo = _coo_block(value)
    row = _mission_document(digest)['coo']['missions'][0]
    from integrations.mastermind_executive_app.coo_binding import _digest
    row['principal_binding_digest'] = _digest(coo['binding']['binding'])
    coo['missions'] = [row]
    value['coo'] = coo
    s.mcp_bytes = control._encoded_json(value)
    replace_fixture(control.OS_GATEWAY_MCP_CONFIG, s.mcp_bytes)
    leaf = s.tmp_path / owner.SERVICE_ROOT / 'mcp-auth/coo'
    leaf.mkdir(mode=0o700)
    return value


def fixture_registry_custody(monkeypatch, s):
    # TESTDATA: this owner fixture already models root/service identities.
    # Preserve actual owned ancestor inode/time observations; no real Root
    # enrollment is claimed for this disposable release under an agent tree.
    from control_plane import executive_installed_peer as installed
    def observe(path, budget):
        budget.check()
        path = Path(path)
        assert path.is_relative_to(s.release)
        return tuple((str(parent), parent.stat().st_ino, parent.stat().st_mtime_ns)
                     for parent in path.parents if parent.is_relative_to(s.release))
    monkeypatch.setattr(installed, '_observe_ancestors', observe)


def test_actual_owner_publication_derives_target_profile_without_changing_authority(gateway, monkeypatch):
    s = gateway
    fixture_registry_custody(monkeypatch, s)
    target_digest = registry_at(s.release)
    prior = add_mission(s, 'a' * 64)
    before = copy.deepcopy(prior)
    outcome = s.publish()
    assert outcome.state == 'PUBLISHED'
    actual = json.loads(control.OS_GATEWAY_MCP_CONFIG.read_bytes())
    assert actual['coo']['missions'][0]['capability_profile_digest'] == target_digest
    before['coo']['missions'][0]['capability_profile_digest'] = target_digest
    assert actual['coo'] == before['coo']
    assert actual['workspace'] == prior['workspace']
    assert actual['policies'] == prior['policies']
    assert 'selected_child_target' not in actual
    receipt = json.loads(control.OS_GATEWAY_RECEIPT.read_bytes())
    assert receipt['target_mcp_config_sha256'] == owner.digest(control.OS_GATEWAY_MCP_CONFIG.read_bytes())
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_compiler_legacy_and_no_mission_map_are_byte_exact():
    old = pure.compile_candidate()
    fresh = compiler.compile_gateway_candidates(pure.prior_mcp_bytes(), pure.prior_plist_bytes(),
        expected_release_sha=pure.NEW_RELEASE, expected_bundle_digest=pure.BUNDLE_DIGEST,
        qualified_publication_inputs=pure.qualified_inputs(), capability_profile_digests={})
    assert fresh == old


@pytest.mark.parametrize('bad', [{}, {'foreign': 'b'*64},
    {PRINCIPAL_PROFILE: 'B'*64}, {PRINCIPAL_PROFILE: 'b'*63},
    {PRINCIPAL_PROFILE: 'b'*64, 'extra': 'c'*64}])
def test_profile_map_must_match_exact_preserved_missions(bad):
    prior = pure.prior_mcp_document()
    prior['coo'] = _coo_block(prior)
    prior['coo']['missions'] = _mission_document('a'*64)['coo']['missions']
    from integrations.mastermind_executive_app.coo_binding import _digest
    prior['coo']['missions'][0]['principal_binding_digest'] = _digest(prior['coo']['binding']['binding'])
    with pytest.raises(ValueError):
        compiler.compile_gateway_candidates(pure.prior_mcp_bytes(prior), pure.prior_plist_bytes(),
            expected_release_sha=pure.NEW_RELEASE, expected_bundle_digest=pure.BUNDLE_DIGEST,
            qualified_publication_inputs=pure.qualified_inputs(), capability_profile_digests=bad)


def test_disabled_target_profile_refuses_before_intent_or_target_change(gateway, monkeypatch):
    s = gateway
    fixture_registry_custody(monkeypatch, s)
    registry_at(s.release, enabled=False)
    add_mission(s, 'a'*64)
    before = [path.read_bytes() if path.exists() else None for path in s.target_paths()]
    with pytest.raises(control.GatewayPublicationError, match='gateway_capability_profiles_invalid'):
        s.publish()
    assert [path.read_bytes() if path.exists() else None for path in s.target_paths()] == before
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_RECEIPT.exists()


def test_registry_ancestor_drift_refuses_exact_existing_loader(monkeypatch, tmp_path):
    registry_at(tmp_path / pure.NEW_RELEASE)
    from control_plane import executive_installed_peer as installed
    monkeypatch.setattr(installed, '_SERVICE_RELEASES', str(tmp_path))
    observations = iter([('first',), ('changed',)])
    monkeypatch.setattr(installed, '_observe_ancestors', lambda *_: next(observations))
    with pytest.raises(component.UpdateRefused, match='ANCESTORS_CHANGED'):
        component.derive_sealed_capability_profile_digests(pure.NEW_RELEASE, (PRINCIPAL_PROFILE,), object())


def test_successor_joins_old_receipt_before_derivation_and_recovers_frozen_map(gateway, monkeypatch):
    from tests.test_os_gateway_successor_publication import prepare_successor, lose_terminal_ack, history
    s = gateway
    fixture_registry_custody(monkeypatch, s)
    old_digest = registry_at(s.release)
    add_mission(s, old_digest)
    s.publish()
    request, old_receipt = prepare_successor(s, monkeypatch)
    target_digest = registry_at(s.release, schema_digest='f'*64)
    assert target_digest != old_digest
    before = json.loads(s.mcp_bytes)
    observed = []
    qualify = s.host._qualify_gateway_predecessor_release
    derive = s.host.derive_capability_profile_digests
    def qualify_first(*args):
        result = qualify(*args)
        observed.append('old-receipt-qualified')
        return result
    def derive_after(sha, ids):
        assert observed == ['old-receipt-qualified']
        assert sha == request.expected_sha and ids == (PRINCIPAL_PROFILE,)
        observed.append('target-derived')
        return derive(sha, ids)
    monkeypatch.setattr(s.host, '_qualify_gateway_predecessor_release', qualify_first)
    monkeypatch.setattr(s.host, 'derive_capability_profile_digests', derive_after)
    manifest = lose_terminal_ack(s, request, monkeypatch)
    assert observed == ['old-receipt-qualified', 'target-derived', 'old-receipt-qualified']
    raw = control.OS_GATEWAY_MCP_CONFIG.read_bytes()
    current = json.loads(raw)
    before['coo']['missions'][0]['capability_profile_digest'] = target_digest
    assert current['coo'] == before['coo']
    assert manifest['gateway_target_mcp_config_sha256'] == owner.digest(raw)
    assert history(request).read_bytes() == old_receipt
    fresh = s.fresh_host(monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError('reconciliation must not rederive or replace the frozen original')
    monkeypatch.setattr(fresh, 'derive_capability_profile_digests', forbidden)
    monkeypatch.setattr(fresh, 'write_gateway_receipt', forbidden)
    assert s.reconcile(host=fresh, transaction_id=manifest['transaction_id']) == manifest['transaction_id']
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == raw
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_wrong_predecessor_source_refuses_before_derivation(gateway, monkeypatch):
    from tests.test_os_gateway_successor_publication import prepare_successor, publish
    s = gateway
    s.publish()
    request, _ = prepare_successor(s, monkeypatch)
    def refuse(*args):
        raise control.GatewayPublicationError('gateway_receipt_invalid')
    def forbidden(*args):
        raise AssertionError('cannot derive before predecessor source qualifies')
    monkeypatch.setattr(s.host, '_qualify_gateway_predecessor_release', refuse)
    monkeypatch.setattr(s.host, 'derive_capability_profile_digests', forbidden)
    before = [path.read_bytes() for path in s.target_paths()]
    with pytest.raises(control.GatewayPublicationError, match='gateway_receipt_invalid'):
        publish(s, request)
    assert [path.read_bytes() for path in s.target_paths()] == before
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_digest_amendment_preserves_closed_selected_child_publication_bytes():
    from control_plane.coo_principal_host import build_selected_child_publication, selected_child_command_id
    prior = pure.prior_mcp_document()
    prior['coo'] = _coo_block(prior)
    prior['coo']['missions'] = _mission_document('a'*64)['coo']['missions']
    from integrations.mastermind_executive_app.coo_binding import _digest
    prior['coo']['missions'][0]['principal_binding_digest'] = _digest(prior['coo']['binding']['binding'])
    root, child = 'JOB-101', 'JOB-102'
    prior['selected_child_target'] = build_selected_child_publication(
        work_ref=prior['coo']['missions'][0]['work_ref'], root_job_id=root,
        children=[dict(command_id=selected_child_command_id(root, child, 1),
            attempt_ordinal=1, root_job_id=root, parent_job_id=root, job_id=child,
            plan_attempt_id='attempt-fixture', plan_digest='plan-fixture', plan_step_id='step-fixture',
            repair_round=0, expected_current_attempt_id=None)],
        source=dict(schema='mastermind.executive.selected_child_source.v1',
            plan_attempt_id='attempt-fixture', plan_digest='plan-fixture', policy_sha='c'*64,
            reservation_digest='d'*64, observation_state='SAME', observation_source_identity='fixture'))
    frozen = compiler.canonical(prior)
    result = compiler.compile_gateway_candidates(pure.prior_mcp_bytes(prior), pure.prior_plist_bytes(),
        expected_release_sha=pure.NEW_RELEASE, expected_bundle_digest=pure.BUNDLE_DIGEST,
        qualified_publication_inputs=pure.qualified_inputs(),
        capability_profile_digests={PRINCIPAL_PROFILE:'b'*64})
    assert compiler.canonical(prior) == frozen
    assert compiler.canonical(result.mcp_document()['selected_child_target']) == compiler.canonical(prior['selected_child_target'])

@pytest.mark.parametrize("mode", ["legacy", "empty-map", "mission-map"])
def test_cold_compiler_preserves_purity_without_transactional_imports(mode):
    # A separate interpreter prevents this file's owner fixtures from warming
    # transactional CLI imports and hiding application-owned import-time I/O.
    import subprocess
    import sys
    import textwrap

    prior = pure.prior_mcp_document()
    digests = None if mode == "legacy" else {}
    if mode == "mission-map":
        prior["coo"] = _coo_block(prior)
        prior["coo"]["missions"] = _mission_document("a" * 64)["coo"]["missions"]
        from integrations.mastermind_executive_app.coo_binding import _digest
        prior["coo"]["missions"][0]["principal_binding_digest"] = _digest(
            prior["coo"]["binding"]["binding"])
        digests = {PRINCIPAL_PROFILE: "b" * 64}
    script = r'''
    import importlib
    import json
    import sys
    import pytest
    from tests import test_os_gateway_publication as pure

    payload = json.load(sys.stdin)
    for name in ("integrations.studio_direct_mcp.private_service",
                 "integrations.executive_mcp.schemas",
                 "integrations.business_mcp_auth.contracts",
                 "control_plane.executive_peer_identity"):
        importlib.import_module(name)
    transactional = ("ops.executive_os.mcp_component_update",
                     "ops.executive_os.gateway_refresh_preflight")
    before = {name: name in sys.modules for name in transactional}
    assert not any(before.values()), before
    calls = []
    patch = pytest.MonkeyPatch()
    try:
        pure._guard_io(patch, calls, stat_too=True)
        candidate = pure.m.compile_gateway_candidates(
            pure.prior_mcp_bytes(payload["prior"]), pure.prior_plist_bytes(),
            expected_release_sha=pure.NEW_RELEASE,
            expected_bundle_digest=pure.BUNDLE_DIGEST,
            qualified_publication_inputs=pure.qualified_inputs(),
            capability_profile_digests=payload["digests"])
        classification = pure.m.classify_postimages(
            candidate, {a.path: a.content for a in candidate.artifacts},
            publication_before_bytes=b"{}\n")
        manifest = candidate.operation_manifest()
        observed = tuple(calls)
        after = {name: name in sys.modules for name in transactional}
    finally:
        patch.undo()
    print(json.dumps({"calls": observed, "loaded_before": before, "loaded_after": after}))
    assert observed == (), observed
    assert not any(after.values()), after
    assert classification["state"] == "MATCHED"
    assert manifest["operation"] == "OS_GATEWAY_PUBLICATION"
    if payload["digests"]:
        for mission in candidate.mcp_document()["coo"]["missions"]:
            assert mission["capability_profile_digest"] == payload["digests"][mission["capability_profile_id"]]
    '''
    result = subprocess.run(
        [sys.executable, "-B", "-c", textwrap.dedent(script)],
        cwd=Path(__file__).resolve().parents[1],
        input=json.dumps({"prior": prior, "digests": digests}),
        text=True, capture_output=True, timeout=60, check=False)
    assert result.returncode == 0, (result.stdout, result.stderr)
    observed = json.loads(result.stdout)
    assert observed["calls"] == []
    assert not any(observed["loaded_before"].values())
    assert not any(observed["loaded_after"].values())

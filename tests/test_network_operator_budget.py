"""Offline Network policy boundary; private SQLite, no live grants or providers."""
import copy
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import types
import io
import tarfile
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/native_fabric/quota_continuity/source"
CANDIDATE = ROOT / "ops/native_fabric/quota_continuity/candidate/fabric_operator_owner.py"
NETWORK = "01a12a2a-d7e1-77b1-9262-ab593179dd13"
DENIAL = "network_paid_dispatch_budget_unqualified"
PROPOSAL = ROOT / 'integrations/session_bridge/network_budget_admission'


@pytest.fixture(scope='module', autouse=True)
def materialized_proposal(tmp_path_factory):
    """Apply exact reviewed deltas only in a disposable source/build copy."""
    global SOURCE, CANDIDATE
    manifest = json.loads((PROPOSAL / 'manifest.json').read_text())
    tree = tmp_path_factory.mktemp('network-prospective-source')
    quota = 'ops/native_fabric/quota_continuity'
    active_paths = (
        quota + '/source/fabric_operator_owner.py',
        quota + '/candidate/fabric_operator_owner.py',
        quota + '/candidate/fabric_task.py',
        quota + '/rollout/build_review_stage.py',
        quota + '/rollout/native-manifest.json',
        quota + '/rollout/native-source-inventory.json',
        'tests/executive_identity_review.py',
        'tests/executive_fabric_release_identity_review.py',
        'tests/test_executive_a2_identity_review.py',
    )
    active_preimages = {
        path: (ROOT / path).read_bytes() if (ROOT / path).exists() else None
        for path in active_paths
    }
    provenance = json.loads(subprocess.check_output([
        'git', '-C', str(ROOT), 'show',
        f"{manifest['base']}:{quota}/candidate/paid_pyyaml_provenance.json",
    ]))
    archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', manifest['base'],
        quota, 'ops/native_fabric/grok47/overlay', provenance['lock_path']])
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(tree, filter='data')
    # Compare prospective output with its own immutable generation.
    baseline = json.loads((tree / quota / 'rollout/native-manifest.json').read_text())
    for target, row in manifest['files'].items():
        original = tree / row['base_source']
        assert hashlib.sha256(original.read_bytes()).hexdigest() == row['preimage_sha256']
        destination = tree / target
        if target != row['base_source']:
            assert not destination.exists()
            destination.write_bytes(original.read_bytes())
        patch = PROPOSAL / row['patch']
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == row['patch_sha256']
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=tree, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=tree, check=True)
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == row['postimage_sha256']
    SOURCE = tree / quota / 'source'
    CANDIDATE = tree / quota / 'candidate/fabric_operator_owner.py'
    # The unchanged builder verifies original preimages and writes only this copy.
    subprocess.run([sys.executable, str(tree / quota / 'rollout/build_review_stage.py'),
                    '--output', str(tree / quota / 'rollout')], cwd=tree, check=True)
    staged = json.loads((tree / quota / 'rollout/native-manifest.json').read_text())
    assert len(baseline) == len(staged) == 102
    assert sorted(k for k in set(baseline) | set(staged) if baseline.get(k) != staged.get(k)) == ['ext/fabric_operator_owner.py', 'ext/fabric_task.py']
    try:
        yield tree
    finally:
        # The historical fixture must leave the current generation and D8 owner intact.
        for path, before in active_preimages.items():
            after = (ROOT / path).read_bytes() if (ROOT / path).exists() else None
            assert after == before, path


def load_owner(path):
    spec = importlib.util.spec_from_file_location("_offline_network_owner_" + path.parent.name, path)
    module = importlib.util.module_from_spec(spec)
    before = list(sys.path)
    try:
        sys.path.insert(0, str(SOURCE))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = before
    return module


@pytest.fixture
def modules():
    return load_owner(SOURCE / "fabric_operator_owner.py"), load_owner(CANDIDATE)


def seed(module, tmp_path, root=NETWORK):
    here = tmp_path / "private-owner"
    (here / "broker").mkdir(parents=True)
    (here / "broker/leases.lock").touch(mode=0o600)
    (here / "state/remote_sub").mkdir(parents=True)
    owner = module.OperatorOwner(here=here, clock=lambda: 1000.)
    lease = dict(id="inert-lease", orchestrator_id=root, pool="glm-frontier", account="inert-account",
                 task_class="remote-glm", model="glm-5.3", host="ubuntu1", pid=123,
                 granted_at=990., ttl=180, last_heartbeat=999., state="held", renewable=1)
    with sqlite3.connect(owner.db) as con:
        columns = ', '.join(k + ' ' + ('REAL' if type(v) is float else 'INTEGER' if type(v) is int else 'TEXT') for k,v in lease.items())
        con.execute('CREATE TABLE leases (' + columns + ')')
        con.execute('INSERT INTO leases VALUES (' + ','.join('?' for _ in lease) + ')', tuple(lease.values()))
    launch = dict(root=root, run_id="inert-operator", lease_id="inert-lease", pool="glm-frontier", model="glm-5.3",
                  account="inert-account", host="ubuntu1", support_sha256='a'*64,
                  packet_sha256=hashlib.sha256(b'inert packet').hexdigest(), task_class="domain_orchestration")
    owner.authorize_root(root, 3, 2200.)
    cap = owner.issue(launch, 2)
    request = dict(schema="mastermind.fabric_operator_child_request.v1", root=root, parent="inert-operator",
                   run_id="inert-child", task_class="mechanical", task_complexity="C0_MECHANICAL", packet="Inert offline fixture")
    return owner, cap, request


def rows(owner):
    with sqlite3.connect(owner.db) as con:
        return con.execute('SELECT * FROM operator_child_authorizations ORDER BY run_id').fetchall()


def test_network_new_dispatch_refuses_before_reservation_packet_or_process(modules, tmp_path):
    old, new = modules
    owner, cap, request = seed(new, tmp_path)
    called = []
    def forbidden(*a, **k):
        called.append(True)
        raise AssertionError('No process boundary may be entered')
    with pytest.raises(new.DelegationRefused, match='^' + DENIAL + '$'):
        owner.dispatch(cap['token'], request, popen=forbidden)
    assert not called and rows(owner) == []
    assert list((owner.here / 'state/remote_sub').iterdir()) == []
    assert owner.describe(cap['token'])['child_budget_remaining'] == 2


@pytest.mark.parametrize('field,value', [('root','inert-foreign-root'),('parent','inert-foreign-parent')])
def test_labels_cannot_retarget_an_authenticated_network_grant(modules, tmp_path, field, value):
    old, new = modules
    owner, cap, request = seed(new, tmp_path)
    with pytest.raises(new.DelegationRefused):
        owner.reserve(cap['token'], dict(request, **{field:value}))
    assert rows(owner) == []


def test_unknown_token_is_not_budget_authority(modules, tmp_path):
    old, new = modules
    owner, cap, request = seed(new, tmp_path)
    with pytest.raises(new.DelegationRefused):
        owner.reserve('0'*64, request)
    assert rows(owner) == []


@pytest.mark.parametrize('kind', ['reservation', 'log', 'result', 'symlink'])
def test_existing_or_uncertain_operation_keeps_original_disposition(modules, tmp_path, kind):
    old, new = modules
    owner, cap, request = seed(old, tmp_path)
    if kind == 'reservation':
        owner.reserve(cap['token'], request)
    else:
        p = owner.here / 'state/remote_sub' / (request['run_id'] + ('.log' if kind == 'symlink' else '.' + kind))
        if kind == 'symlink': p.symlink_to(owner.here / 'missing')
        else: p.write_text('inert retained original')
    initial = rows(owner)
    resumed = new.OperatorOwner(here=owner.here, clock=lambda:1000.)
    with pytest.raises(new.DelegationRefused, match='^RUN_EXISTS$'):
        resumed.reserve(cap['token'], request)
    assert rows(owner) == initial


def test_new_network_reservation_denied_after_prior_reservation_is_preserved(modules, tmp_path):
    old, new = modules
    owner, cap, request = seed(old, tmp_path)
    owner.reserve(cap['token'], request)
    initial = rows(owner)
    resumed = new.OperatorOwner(here=owner.here, clock=lambda:1000.)
    with pytest.raises(new.DelegationRefused, match='^' + DENIAL + '$'):
        resumed.reserve(cap['token'], dict(request, run_id='inert-second-child'))
    assert rows(owner) == initial


def test_existing_authorization_claim_remains_valid(modules, tmp_path):
    old, new = modules
    owner, cap, request = seed(old, tmp_path)
    owner.reserve(cap['token'], request)
    initial = rows(owner)
    with owner.transaction() as con:
        grant = new.validate_child_admission(con, request['run_id'], NETWORK, now=1000.)
    assert grant['root'] == NETWORK and rows(owner) == initial


def test_existing_network_terminal_result_and_ack_remain_readable(modules, tmp_path, monkeypatch):
    old, new = modules
    owner, cap, request = seed(old, tmp_path)
    owner.reserve(cap['token'], request)
    resumed = new.OperatorOwner(here=owner.here, clock=lambda:1000.)
    body = b'inert retained terminal output'
    status = dict(run_id=request['run_id'],root_id=NETWORK,parent_run_id='inert-operator',state='TERMINAL',rc=0,result_available=True)
    # Fake ONLY existing retained-result transport; no live ledger/output access.
    monkeypatch.setitem(sys.modules, 'fabric_task', types.SimpleNamespace(inspect_run=lambda rid:copy.deepcopy(status), read_result=lambda rid,**kwargs:body))
    assert resumed.observe(cap['token'], 'status', request['run_id']) == status
    result = resumed.observe(cap['token'], 'result', request['run_id'])
    digest = hashlib.sha256(body).hexdigest()
    assert result['content'] == body.decode() and result['sha256'] == digest
    ack = resumed.acknowledge(cap['token'], request['run_id'], digest)
    assert ack['consumption_acknowledged'] is True and ack['acceptance_recorded'] is False
    assert resumed.returns(cap['token'])['children'] == []


def test_unrelated_authenticated_root_still_dispatches_through_original_adapter(modules, tmp_path):
    old, new = modules
    owner, cap, request = seed(new, tmp_path, root='inert-unrelated-root')
    calls = []
    def inert_process(argv, **kwargs):
        calls.append((argv, kwargs)); return types.SimpleNamespace(pid=321)
    result = owner.dispatch(cap['token'], request, popen=inert_process)
    assert result['state'] == 'SUBMITTED_TO_EXISTING_ADAPTER'
    assert result['root'] == 'inert-unrelated-root' and len(calls) == 1 and len(rows(owner)) == 1
    argv = calls[0][0]
    assert argv[argv.index('--root')+1] == 'inert-unrelated-root'
    assert argv[argv.index('--parent')+1] == 'inert-operator'


def test_unrelated_unknown_dispatch_is_not_refunded_or_replayed(modules, tmp_path):
    old, new = modules
    owner, cap, request = seed(new, tmp_path, root='inert-unrelated-root')
    def broken(*a, **k): raise OSError('inert response loss')
    result = owner.dispatch(cap['token'], request, popen=broken)
    assert result['state'] == 'DISPATCH_UNVERIFIED' and result['retry_authorized'] is False
    assert len(rows(owner)) == 1
    with pytest.raises(new.DelegationRefused, match='^RUN_EXISTS$'):
        owner.reserve(cap['token'], request)


@pytest.mark.parametrize('explicit,environment,expected', [
    (None, {'CODEX_THREAD_ID': NETWORK}, NETWORK),
    ('inert-foreign-root', {'CODEX_THREAD_ID': NETWORK}, 'inert-foreign-root'),
    (None, {}, None),
])
def test_top_level_root_resolution_is_only_transport_metadata(explicit, environment, expected):
    """Document the remaining gap without calling the manual adapter or router."""
    tree = ast.parse((ROOT / 'ops/native_fabric/quota_continuity/candidate/fabric_task.py').read_text())
    names = {'validate_run_id', 'resolve_request_root'}
    selected = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    import re
    scope = {'re': re, 'RUN_ID_RE': re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'), 'FabricTaskError': RuntimeError}
    exec(compile(selected, '<pure-root-resolution-source>', 'exec'), scope)
    assert scope['resolve_request_root'](explicit, environment) == expected


def manual_api(monkeypatch, tmp_path):
    """Load actual request owner with unavailable historical reconcilers inert."""
    monkeypatch.syspath_prepend(str(SOURCE))
    monkeypatch.syspath_prepend(str(CANDIDATE.parent))
    for name in ('a04_terminal_reconcile', 'native_completion_reconcile',
                 'native_prestart_reconcile', 'native_preexec_reconcile',
                 'native_host_review_controller_reconcile'):
        module = types.ModuleType(name)
        module.RUN = module.RUN_ID = 'inert-unavailable-historical-run'
        module.KNOWN_RUNS = ()
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location('_offline_network_manual', CANDIDATE.parent / 'fabric_task.py')
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    monkeypatch.setattr(api, 'HERE', tmp_path)
    monkeypatch.setattr(api.os, 'environ', {})
    return api


def manual_request(api, root=NETWORK, run='inert-manual-child'):
    return api.request(run, 'mechanical', cwd='~', packet=None,
                       stdin_bytes=b'Inert offline request', root_id=root,
                       parent_run_id='inert-parent', task_complexity='C0_MECHANICAL')


@pytest.mark.parametrize('inherited', [False, True])
def test_named_manual_network_root_refuses_before_route_lease_or_packet(monkeypatch, tmp_path, inherited):
    api = manual_api(monkeypatch, tmp_path)
    if inherited:
        monkeypatch.setitem(api.os.environ, 'CODEX_THREAD_ID', NETWORK)
    reached = []
    def forbidden(*args, **kwargs):
        reached.append(True)
        raise AssertionError('Routing/provider boundary must not be reached')
    monkeypatch.setattr(api.pick, 'format_pick', forbidden)
    monkeypatch.setattr(api.pick, 'launch_policy', forbidden)
    monkeypatch.setattr(api.subprocess, 'run', forbidden)
    with pytest.raises(api.FabricTaskError, match='^NETWORK_PAID_DISPATCH_BUDGET_UNQUALIFIED$'):
        manual_request(api, root=None if inherited else NETWORK)
    assert not reached
    assert not (tmp_path / 'state').exists()


@pytest.mark.parametrize('suffix', ['.log', '.remote.stdout', '.request.json', '.request.packet'])
def test_named_manual_network_preserves_existing_run_before_policy_refusal(monkeypatch, tmp_path, suffix):
    api = manual_api(monkeypatch, tmp_path)
    directory = tmp_path / ('lanes' if suffix == '.remote.stdout' else 'state/remote_sub')
    directory.mkdir(parents=True)
    original = directory / ('inert-manual-child' + suffix)
    original.write_text('inert original unknown operation')
    with pytest.raises(api.FabricTaskError, match='^REQUEST_RUN_ALREADY_EXISTS_RECONCILE_ORIGINAL$'):
        manual_request(api)
    assert list(directory.iterdir()) == [original]
    assert original.read_text() == 'inert original unknown operation'


@pytest.mark.parametrize('root', ['inert-unrelated-root', None])
def test_manual_non_network_metadata_retains_original_route_without_spend_attestation(monkeypatch, tmp_path, root):
    api = manual_api(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(api.pick, 'format_pick', lambda *a, **kw: 'POOL=glm MODEL=inert-model HOST=inert MODE=glm')
    monkeypatch.setattr(api.pick, 'launch_policy', lambda *a, **kw: {'allowed': True})
    def inert_transport(argv, **kwargs):
        calls.append((argv, kwargs))
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr(api.subprocess, 'run', inert_transport)
    assert manual_request(api, root=root) == 0 and len(calls) == 1
    # This compatibility result is NOT a budget or authentic-root admission.
    retained = json.loads((tmp_path / 'state/remote_sub/inert-manual-child.request.json').read_text())
    assert retained['root_id'] == root



def test_only_exact_network_owner_deadline_sites_are_qualified():
    from tests.test_executive_a2_identity_review import scan
    from tests.executive_identity_review import reviewed_literal_spans
    path = 'ops/native_fabric/quota_continuity/candidate/fabric_operator_owner.py'
    source = CANDIDATE.read_text()
    # Explicit prospective review DATA only, never active production exemptions.
    from tests.executive_fabric_release_identity_review import REVIEWED_FILES
    manifest = json.loads((PROPOSAL / 'manifest.json').read_text())
    record = manifest['prospective_identity_review']
    old_record = REVIEWED_FILES.get(path)
    assert old_record is None
    REVIEWED_FILES[path] = {'sha256': record['sha256'], 'sites': tuple(tuple(row) for row in record['sites'])}
    try:
        assert len(reviewed_literal_spans(path, source)) == 2
        assert scan(source, path=path) == []
        assert scan(source + '\n# source drift\n', path=path) == ['660', '660']
        assert '457' in scan(source + '\npeer_uid = 457\n', path=path)
        assert scan(source, path='control_plane/foreign_network_owner.py') == ['660', '660']
    finally:
        del REVIEWED_FILES[path]



def test_prospective_fixture_data_assembles_with_unchanged_real_compilers(materialized_proposal, tmp_path, monkeypatch):
    from tests import test_paid_provider_entry_linux as actual
    monkeypatch.setattr(actual, 'ROOT', materialized_proposal)
    actual.test_compiled_fixture_data_assembles_against_real_wire_and_compilers(tmp_path, monkeypatch, current_core=False)


def test_prior_reservation_survives_but_later_start_stays_held(modules, tmp_path, monkeypatch):
    old, new = modules
    owner, cap, request = seed(old, tmp_path)
    owner.reserve(cap['token'], request)
    with owner.transaction() as connection:
        assert new.validate_child_admission(connection, request['run_id'], NETWORK, now=1000.)['root'] == NETWORK
    packet = owner.here / 'state/remote_sub' / (request['run_id'] + '.operator-packet')
    packet.write_text(request['packet'] + old.CHILD_SUFFIX)
    before_rows, before_packet = rows(owner), packet.read_bytes()
    api = manual_api(monkeypatch, owner.here)
    monkeypatch.setitem(api.os.environ, 'FABRIC_OPERATOR_CHILD_ID', request['run_id'])
    reached = []
    def forbidden(*args, **kwargs):
        reached.append(True)
        raise AssertionError('New paid start must stay held')
    monkeypatch.setattr(api.pick, 'format_pick', forbidden)
    monkeypatch.setattr(api.subprocess, 'run', forbidden)
    with pytest.raises(api.FabricTaskError, match='^NETWORK_PAID_DISPATCH_BUDGET_UNQUALIFIED$'):
        api.request(request['run_id'], request['task_class'], cwd='~', packet=packet,
                    stdin_bytes=None, root_id=NETWORK, parent_run_id=request['parent'],
                    task_complexity=request['task_complexity'])
    assert not reached and rows(owner) == before_rows and packet.read_bytes() == before_packet
    assert list(packet.parent.iterdir()) == [packet]
    assert new.OperatorOwner(here=owner.here, clock=lambda:1000.).describe(cap['token'])['child_budget_remaining'] == 1


def test_actual_materialized_manual_bytes_retain_only_inherited_d8_findings(materialized_proposal):
    import difflib
    from tests.test_executive_a2_identity_review import scan
    from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff
    manifest = json.loads((PROPOSAL / 'manifest.json').read_text())
    path = 'ops/native_fabric/quota_continuity/candidate/fabric_task.py'
    original = subprocess.check_output([
        'git', '-C', str(ROOT), 'show',
        f"{manifest['base']}:{manifest['files'][path]['base_source']}",
    ]).decode('utf-8')
    prospective = (materialized_proposal / path).read_text()
    assert hashlib.sha256(prospective.encode()).hexdigest() == manifest['files'][path]['postimage_sha256']
    assert hashlib.sha256(original.encode()).hexdigest() == manifest['files'][path]['preimage_sha256']
    assert scan(prospective, path=path) == scan(original, path=path)
    diff = 'diff --git a/' + path + ' b/' + path + '\n' + ''.join(difflib.unified_diff(original.splitlines(keepends=True), prospective.splitlines(keepends=True), fromfile='a/' + path, tofile='b/' + path, n=0))
    assert _scan_added_identity_diff(diff, source_postimages={path: prospective}) == []
    dirty = prospective + '\npeer_uid = 457\n'
    assert hashlib.sha256(dirty.encode()).hexdigest() != manifest['files'][path]['postimage_sha256']
    assert '457' in scan(dirty, path=path)


def test_prospective_payloads_pass_the_existing_anonymous_read_fence(materialized_proposal, monkeypatch):
    from tests import test_no_anonymous_macro_reads as fence
    monkeypatch.setattr(fence, '_ROOT', materialized_proposal)
    fence.test_no_anonymous_macro_reads_in_executable_or_config_surfaces(
        fence.violations.__wrapped__())

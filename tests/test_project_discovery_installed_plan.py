"""Actual CREATE/default/Event DATA -> installed collector -> -I Plan child.

Reuses the existing temporary Git/Runtime/auth fixture, retaining its declared
source-snapshot and GitHub identity seams. The physical_plan override is
explicitly removed: these tests execute the real installed child boundary.
No live host, provider, credentials, Git remote or service is contacted.
"""
import json
import subprocess
import types
from pathlib import Path
import sys

import pytest

from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.mastermind_workspace_app.contract import principal_frame
from tests.test_project_journey_canonical_create import joined
from tests.test_project_creation_source_owner import owner, env, isolated_git_env
from tests.test_installed_source_git_identity import identity


def _qualified_source_python():
    from ops.executive_os.capacity_source_contract import PYTHON_BINARY
    configured = Path(PYTHON_BINARY)
    selected = configured if configured.is_file() else Path(sys.executable)
    # The CI interpreter is eligible only after its REAL isolated import
    # succeeds. A selected runtime failure is not repaired by another route.
    subprocess.run([str(selected), '-I', '-B', '-c',
        'import yaml; assert yaml.safe_load("a: 1") == {"a": 1}'],
        capture_output=True, check=True, timeout=10)
    return selected


def test_linux_source_child_uses_actual_isolated_python_when_configured_path_absent(monkeypatch, tmp_path):
    from ops.executive_os import capacity_source_contract
    monkeypatch.setattr(capacity_source_contract, 'PYTHON_BINARY', tmp_path / 'absent-configured-python')
    assert _qualified_source_python() == Path(sys.executable)


def test_selected_source_runtime_failure_does_not_fall_back(monkeypatch, tmp_path):
    from ops.executive_os import capacity_source_contract
    selected = tmp_path / 'selected-python'
    selected.write_text('#!/bin/sh\nexit 7\n')
    selected.chmod(0o700)
    monkeypatch.setattr(capacity_source_contract, 'PYTHON_BINARY', selected)
    with pytest.raises(subprocess.CalledProcessError) as failure:
        _qualified_source_python()
    assert failure.value.returncode == 7
    assert failure.value.cmd[0] == str(selected)


def test_portable_fixture_clock_keeps_age_without_inter_read_jitter(monkeypatch):
    from tests import fresh_conversation_full_cache as fixture
    from scripts import chairman_control_room as clock_owner
    nanoseconds = [0]

    def interrupted_observation():
        # Each physical observation is separated by a scheduling-sized gap.
        nanoseconds[0] += 3_000_000
        return nanoseconds[0]

    monkeypatch.setattr(fixture, 'time', types.SimpleNamespace(
        time_ns=interrupted_observation, monotonic_ns=interrupted_observation))
    anchor = fixture.fixture_clock_sample()
    current = fixture.fixture_clock_sample()
    assert clock_owner._valid_clock_sample(anchor), anchor
    assert clock_owner._valid_clock_sample(current), current
    # The coherent fixture still pays elapsed time; it is not a frozen clock.
    assert clock_owner._source_elapsed(anchor, current) == 3


def actual_child(j, monkeypatch, *, after=lambda: None):
    collector = j['collector']
    monkeypatch.setattr(collector, '_python', _qualified_source_python())
    monkeypatch.setattr(collector, 'read_project_plan',
        types.MethodType(InstalledBootPacketCollector.read_project_plan, collector))
    original = collector._runner
    children = []
    # joined deliberately supplies a synthetic Mastermind source seal while
    # capturing the REAL Macro C tree. Retain that existing source-snapshot
    # seam consistently at the generation check; never replace the Macro
    # generation or the physical Plan/child implementation.
    snapshot = collector._snapshot_pair
    generation = collector._generation_pair
    source_seals = []

    def capture(*args, **options):
        value = snapshot(*args, **options)
        source_seals.append(value[2])
        return value

    def current_generation(*args, **options):
        value = generation(*args, **options)
        assert source_seals
        return value[0], value[1], source_seals[-1], value[3]

    monkeypatch.setattr(collector, '_snapshot_pair', capture)
    monkeypatch.setattr(collector, '_generation_pair', current_generation)

    def runner(argv, **options):
        result = original(argv, **options)
        if any(str(item).endswith(('/scripts/agentos_project_plan_entry.py', '/scripts/agentos_project_discovery_entry.py')) for item in argv):
            children.append(list(map(str, argv)))
            after()
        return result

    monkeypatch.setattr(collector, '_runner', runner)
    return collector, children


def test_real_current_n_plan_uses_installed_collector_and_pinned_c_child(joined, monkeypatch):
    j = joined
    collector, children = actual_child(j, monkeypatch)
    before = j['runtime'].events.list_events()
    body, view, generation = j['data'].read_plan(principal_frame(j['workspace']),
        operation='project_plan', selection={'work_ref': j['args']['work_ref']})
    assert body['availability'] == 'AVAILABLE', {'reasons': body.get('reason_codes'), 'child_argv': children}
    assert body['source']['commit'] == j['current']
    assert body['selection'] == {'work_ref': j['args']['work_ref']}
    assert view.code_commit == j['code'] and view.data_commit == j['current']
    assert len(generation) == 64 and len(children) == 1
    argv = children[0]
    assert argv[1:3] == ['-I', '-B']
    assert argv[argv.index('--code-root') + 1] == str(j['code_root'])
    assert argv[argv.index('--code-commit') + 1] == j['code']
    assert argv[argv.index('--expected-macro-sha') + 1] == j['current']
    assert argv[argv.index('--macro-root') + 1] != str(j['code_root'])
    assert '--continuity' in argv
    assert j['runtime'].events.list_events() == before and j['runtime'].jobs.list_jobs() == []


def test_actual_bound_view_rejects_foreign_work_before_plan_child(joined, monkeypatch):
    j = joined
    collector, children = actual_child(j, monkeypatch)
    view = j['data'].view(j['workspace'], work_ref=j['args']['work_ref'])
    with view.capture_scope():
        with collector.canonical_project_data_scope(view, work_ref=j['args']['work_ref']):
            with pytest.raises(ValueError, match='CANONICAL_DATA_UNAVAILABLE'):
                collector.read_project_plan(work_ref='WS:FOREIGN')
    assert children == []


def test_actual_late_latest_grant_withdrawal_withholds_completed_child(joined, monkeypatch):
    j = joined
    slot = j['document']['profiles'][j['document']['primary_profile']]
    collector, children = actual_child(j, monkeypatch,
        after=lambda: slot.update(project_canonical_data_read=None))
    with pytest.raises(Exception):
        j['data'].read_plan(principal_frame(j['workspace']),
            operation='project_plan', selection={'work_ref': j['args']['work_ref']})
    assert len(children) == 1
    assert j['runtime'].jobs.list_jobs() == []


def test_actual_installed_discovery_compiles_current_n_record_with_c_owner(joined, monkeypatch):
    j = joined
    collector, children = actual_child(j, monkeypatch)
    view = j['data'].view(j['workspace'], work_ref=j['args']['work_ref'])
    before = j['runtime'].events.list_events()
    with view.capture_scope():
        with collector.canonical_project_data_scope(view, work_ref=j['args']['work_ref']):
            record = collector.read_project_discovery(work_ref=j['args']['work_ref'],
                observed_at_ms=view.witness()['canonical_observed_at_ms'])
    assert record['selection'] == {'work_ref': j['args']['work_ref']}
    assert record['source']['commit'] == j['current']
    assert record['code_source']['commit'] == j['code']
    assert record['agent_os_state']['workstreams'][0]['key'] == j['args']['work_ref'][3:]
    assert record['agent_os_state']['workstreams'][0]['title'] == 'Mastermind OS delivery'
    assert len(children) == 1
    assert j['runtime'].events.list_events() == before
    assert j['runtime'].jobs.list_jobs() == []


def test_actual_discovery_capture_uses_original_create_and_installed_current_record(joined, monkeypatch):
    from integrations.mastermind_workspace_app.project_discovery import InstalledProjectDiscovery
    from control_plane.installed_project_discovery_binding import read_installed_project_discovery
    j = joined
    actual_child(j, monkeypatch)
    owner = InstalledProjectDiscovery(j['data'])
    before = j['runtime'].events.list_events()
    capture = read_installed_project_discovery(owner.installed_binding(), principal_frame(j['workspace']), runtime=j['runtime'])
    try:
        body = capture.document()
        assert body['coverage']['returned'] == 1
        entry = body['entries'][0]
        assert entry['creation_publication']['selection']['action'] == 'publish_project_proposal'
        assert entry['record']['selection'] == {'work_ref': j['args']['work_ref']}
        assert entry['record']['source']['commit'] == j['current']
        assert entry['data_observation']['executable_macro_commit'] == j['code']
        assert entry['data_observation']['canonical_data_commit'] == j['current']
        assert j['runtime'].events.list_events() == before
    finally:
        capture.close()



@pytest.fixture
def full_joined(owner, identity, tmp_path, monkeypatch):
    # A real previously published canonical project establishes configured C.
    # The commissioned second CREATE remains absent at C and appears at N.
    import copy
    from tests.test_workspace_project_git_publisher import git
    baseline = owner['service'].prepare(copy.deepcopy(owner['request']), owner['who'])
    selected = {key:baseline['selection'][key] for key in ('action','request_id','work_ref')}
    proposal = owner['service'].submit(lookup=dict(schema='mastermind.workspace_source_operation_lookup.v1',**selected),
        preview_witness=baseline['preview_witness'],principal=owner['who'])
    integrator = tmp_path/'prior-default'
    git(tmp_path,'clone',str(owner['env'].origin),str(integrator))
    git(integrator,'fetch','origin',proposal['receipt']['proposal']['head_branch'])
    git(integrator,'merge','--no-ff','--no-edit','FETCH_HEAD');git(integrator,'push','origin','main')
    original_lookup = dict(schema='mastermind.workspace_source_operation_lookup.v1',**selected)
    assert owner['service'].reconcile(original_lookup,owner['who'])['receipt']['kind']=='SOURCE_OBSERVED'
    # Materialize the actual prior protected default before capturing C.
    git(owner['env'].clone,'fetch','origin','main');git(owner['env'].clone,'merge','--ff-only','origin/main')
    return joined.__wrapped__(owner,identity,tmp_path,monkeypatch)


def discovery_service(j, monkeypatch):
    from tests.test_workspace_read_service import cache_fixture
    from integrations.mastermind_workspace_app.project_discovery import InstalledProjectDiscovery
    from control_plane.workspace_read_service import WorkspaceReadService
    from integrations.mastermind_workspace_app.contract import workspace_authorizers
    from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
    from tests.test_fabric_result_projection import _bound_reader
    if j.get('full_c'):
        from tests.fresh_conversation_full_cache import CanonicalFixtureCache
        captured = CanonicalFixtureCache(j['code_root'],j['tmp_path']/'genuine-cache',
            mastermind_revision=j['factory'].service.config.proof_base_sha)
        current, cache = [captured.owner], captured.cache
    else:
        current, clocks, cache = cache_fixture(j['tmp_path'])
        current[0].state_cache['doc']['sources'] = {'macro_sha': j['code']}
    _, authorize = workspace_authorizers(policy=j['factory'].workspace_policy,
        load_bindings=lambda:legacy_workspace_document(j['document'],j['factory'].workspace_policy))
    keeper, namespace, binding, bounded = _bound_reader(j['runtime'])
    read = WorkspaceReadService(cache=cache, runtime=j['runtime'], authorize=authorize, armed={},runtime_identity={},
        bounded_runtime=lambda runtime:bounded,
        project_discovery=InstalledProjectDiscovery(j['data']).installed_binding())
    return read, current, (keeper, binding)


def test_actual_create_default_reload_programs_and_explicit_runtime_mission(full_joined, monkeypatch):
    import asyncio, copy, json
    from common.executive_workspace_contract import FRAME_SCHEMA, FRAME_SCHEMA_V2
    from tests.test_project_planning_factory import invocation
    from tests.test_fabric_result_projection import _release
    j = full_joined
    j['full_c'] = True
    actual_child(j, monkeypatch)
    # Existing real admitted planner root; no target/session is made by READ.
    created = asyncio.run(invocation(j['factory'], j['args'], lambda:j['factory'].submit(**j['args'])))
    read, current, lease = discovery_service(j, monkeypatch)
    original = copy.deepcopy(current[0].state_cache['doc'])
    try:
        request = dict(schema=FRAME_SCHEMA,operation='programs',selection=None,principal=principal_frame(j['workspace']))
        response = asyncio.run(read.handle_frame(request))
        assert response['ok'], response
        body = response['result']
        assert body['schema'] == 'mastermind.workspace_programs.v2'
        assert body['control_room'] == original
        project = body['canonical_projects'][0]
        assert project['work_ref'] == j['args']['work_ref']
        assert project['control_room']['work'][0]['agent_os']['title'] == 'Mastermind OS delivery'
        card = project['control_room']['autonomy']['responsibilities'][0]
        assert card['root_job_id'] == created['job_id'], card
        mission_request = dict(schema=FRAME_SCHEMA_V2,operation='mission_v3',
            selection=dict(work_ref=j['args']['work_ref'],root_job_id=created['job_id']),principal=principal_frame(j['workspace']))
        mission = asyncio.run(read.handle_frame(mission_request))
        assert mission['ok'], mission
        assert mission['result']['mission']['root_job_id'] == created['job_id']
        assert mission['result']['source']['owner_observation']['schema'] == 'mastermind.workspace_source_observation.v2'
        assert current[0].state_cache['doc'] == original and current[0].state_compose_seq == 0
        # Keep actual producer DTOs for exact frontend decoder/consumer proof.
        target = __import__('os').environ.get('MMOS_DISCOVERY_FIXTURE_OUTPUT')
        if target:
            from pathlib import Path
            Path(target).write_text(json.dumps(dict(programs=body,mission=mission['result']),ensure_ascii=False,sort_keys=True))

        # Same actual root, distinct closed native origin. No legacy coercion.
        import dataclasses
        from control_plane.project_discovery_direct_origin import validate_direct_origin
        from control_plane.project_discovery_projection import runtime_metadata
        rt = read._bounded_runtime(j['runtime'])
        principal_scope = project['source_observation']['project_data']['creation_publication']['principal_scope']
        creation = project['source_observation']['project_data']['creation_publication']
        metadata, receipt = runtime_metadata(rt, {j['args']['work_ref']}, creation_publications={j['args']['work_ref']: creation})
        assert metadata['rows'][0]['job_id'] == created['job_id']
        foreign = copy.deepcopy(creation); foreign['principal_scope'] = 'f'*64
        assert runtime_metadata(rt, {j['args']['work_ref']}, creation_publications={j['args']['work_ref']: foreign})[0]['rows'] == []
        event = next(item for item in j['runtime'].events.list_events(job_id=created['job_id']) if item.event_type == 'JOB_CREATED')
        job = j['runtime'].jobs.get_job(created['job_id'])
        material = j['runtime'].jobs.direct_native_provenance(created['job_id'])
        validate_direct_origin(job, event, material)
        for mutation in ('actor', 'work', 'unknown', 'planning', 'schema', 'source'):
            payload = copy.deepcopy(event.payload)
            provenance = payload['provenance']
            if mutation == 'actor': provenance['actor'] = 'bad actor'
            if mutation == 'work': provenance['workstream'] = 'WS:FOREIGN'
            if mutation == 'unknown': provenance['unexpected'] = True
            if mutation == 'planning': provenance['project_planning_sha256'] = 'f'*64
            if mutation == 'schema': provenance['schema'] = 'mastermind.ceo_intent.v1'
            if mutation == 'source': provenance['grounding']['macro_sha'] = 'f'*40
            with pytest.raises(ValueError):
                validate_direct_origin(job, dataclasses.replace(event,payload=payload), material)
        # Explicit unknown root refuses before Fabric acquisition; readonly
        # observations add no Jobs, attempts, provider calls or owner Events.
        event_count = len(j['runtime'].events.list_events())
        unknown = copy.deepcopy(mission_request); unknown['selection']['root_job_id'] = 'JOB-99999'
        assert asyncio.run(read.handle_frame(unknown))['status'] == 404
        assert len(j['runtime'].events.list_events()) == event_count
        old_code = current[0].state_cache['doc']['sources']['macro_sha']
        current[0].state_cache['doc']['sources']['macro_sha'] = 'f'*40
        assert asyncio.run(read.handle_frame(request))['result']['availability'] == 'UNAVAILABLE'
        current[0].state_cache['doc']['sources']['macro_sha'] = old_code
        slot = j['document']['profiles'][j['document']['primary_profile']]
        previous = slot['project_canonical_data_read']; slot['project_canonical_data_read'] = None
        without_latest = asyncio.run(read.handle_frame(request))['result']
        assert without_latest['availability'] == 'AVAILABLE' and without_latest['schema'] == 'mastermind.workspace_programs.v1', without_latest
        assert without_latest['control_room'] == original
        slot['project_canonical_data_read'] = previous
        assert len(j['runtime'].events.list_events()) == event_count
        # Late Workspace READ revocation after the actual child must withhold
        # its finished body; no source event or Runtime operation is added.
        old_read = read.authorize
        allowed = [True]
        def enrolled(frame): return allowed[0] and old_read(frame)
        enrolled.binding_digest = lambda frame: old_read.binding_digest(frame) if allowed[0] else None
        read.authorize = enrolled
        original_runner = j['collector']._runner
        def late_runner(argv, **options):
            result = original_runner(argv, **options)
            if any(str(item).endswith('/scripts/agentos_project_discovery_entry.py') for item in argv):
                allowed[0] = False
            return result
        monkeypatch.setattr(j['collector'], '_runner', late_runner)
        assert asyncio.run(read.handle_frame(request))['status'] == 403
        assert len(j['runtime'].events.list_events()) == event_count
    finally:
        _release(*lease)


def test_actual_fixed_child_reads_code_from_c_when_shallow_n_lacks_c_object(joined, tmp_path):
    from tests.test_workspace_project_git_publisher import git
    j = joined
    root = tmp_path / 'shallow-data'
    git(tmp_path, 'clone', '--depth=1', j['o']['env'].origin.as_uri(), str(root))
    absent = subprocess.run(['git', '-C', str(root), 'cat-file', '-e', j['code'] + '^{commit}'], capture_output=True)
    assert absent.returncode != 0
    argv = [str(_qualified_source_python()), '-I', '-B',
        str(Path(__file__).parents[1] / 'scripts/agentos_project_plan_entry.py'),
        '--macro-root', str(root), '--expected-macro-sha', j['current'],
        '--code-root', str(j['code_root']), '--code-commit', j['code'],
        '--work-ref', j['args']['work_ref'], '--continuity', '--timeout', '10']
    result = subprocess.run(argv, capture_output=True, timeout=15)
    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert body['availability'] == 'AVAILABLE' and body['source']['commit'] == j['current']
    # A wrong pinned-C coordinate is not repaired by executing equivalent N.
    argv[argv.index('--code-commit') + 1] = j['current']
    changed = subprocess.run(argv, capture_output=True, timeout=15)
    assert changed.returncode == 0 and json.loads(changed.stdout)['availability'] == 'UNAVAILABLE'

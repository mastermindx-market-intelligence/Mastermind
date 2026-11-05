"""Actual CREATE/default/Event DATA -> installed collector -> -I Plan child.

Reuses the existing temporary Git/Runtime/auth fixture, retaining its declared
source-snapshot and GitHub identity seams. The physical_plan override is
explicitly removed: these tests execute the real installed child boundary.
No live host, provider, credentials, Git remote or service is contacted.
"""
import types
from pathlib import Path
import sys
import json
import subprocess

import pytest

from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.mastermind_workspace_app.contract import principal_frame
from tests.test_project_journey_canonical_create import joined
from tests.test_project_creation_source_owner import owner, env, isolated_git_env
from tests.test_installed_source_git_identity import identity


def actual_child(j, monkeypatch, *, after=lambda: None):
    collector = j['collector']
    from ops.executive_os.capacity_source_contract import PYTHON_BINARY
    # Existing provisioned CF1 source runtime owns PyYAML under -I. The
    # separate HTTP/JWT fixture venv intentionally does not provide it.
    monkeypatch.setattr(collector, '_python', Path(PYTHON_BINARY) if Path(PYTHON_BINARY).exists() else Path(sys.executable))
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
        if any(str(item).endswith('/scripts/agentos_project_plan_entry.py') for item in argv):
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


def test_actual_fixed_child_reads_code_from_c_when_shallow_n_lacks_c_object(joined, tmp_path):
    from ops.executive_os.capacity_source_contract import PYTHON_BINARY
    from tests.test_workspace_project_git_publisher import git
    j = joined
    root = tmp_path / 'shallow-data'
    git(tmp_path, 'clone', '--depth=1', j['o']['env'].origin.as_uri(), str(root))
    absent = subprocess.run(['git', '-C', str(root), 'cat-file', '-e', j['code'] + '^{commit}'], capture_output=True)
    assert absent.returncode != 0
    argv = [str(PYTHON_BINARY if Path(PYTHON_BINARY).exists() else sys.executable), '-I', '-B',
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

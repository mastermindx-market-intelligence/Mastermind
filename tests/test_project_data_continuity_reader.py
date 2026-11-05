"""Actual finite C/N reader capture, disposable Git and real inert Events."""
from dataclasses import replace
from pathlib import Path
import pytest

from tests import test_project_canonical_data as prior
from tests.test_project_canonical_data import env,isolated_git_env,old,actual_owner
from tests.test_agentos_project_knowledge_recipe import earlier_decision,preference_decision
from control_plane.project_canonical_data import CanonicalDataUnavailable


@pytest.fixture
def ready(env,tmp_path,request):
    files={'research/notes.md':'Selected original project notes.\n',
        'agentos/decisions/DEC-EARLIER-CALL.md':earlier_decision().replace('ALPHA','DEMO')}
    owner=actual_owner.__wrapped__(tmp_path/'closure-owner')
    root=Path(owner.__file__).parents[1]
    files['scripts/agentos_project_plan_contract.py']=(root/'scripts/agentos_project_plan_contract.py').read_text()
    for path,raw in files.items():
        target=env.seed/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(raw)
    return prior.ready.__wrapped__(env,tmp_path,request)


def commit(f):
    old.git(f.env.seed,'add','-A');old.git(f.env.seed,'commit','-m','Disposable canonical change')
    old.git(f.env.seed,'push','origin','main')


def unrelated(f):
    path=f.env.seed/'docs'/'unrelated.md';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('Unrelated canonical documentation.\n');commit(f)


def test_actual_reader_issues_nominal_continuity_without_a_publication(ready):
    f=ready;unrelated(f);view=f.observe();catalogue=view.read_knowledge_catalogue(work_ref=old.WORK_REF)
    witness=view.witness();proof=witness['data_continuity']
    assert catalogue['availability']=='AVAILABLE'
    assert proof['work_ref']==old.WORK_REF and proof['principal_scope']==f.actual_scope
    assert proof['executable_macro_commit']==f.base and proof['canonical_data_commit']==view.data_commit
    assert proof['reader_closure_sha256']==witness['reader_closure_sha256']
    assert len(proof['selected_data_closure_sha256'])==64
    assert witness['source_operation'] is None and witness['publication_recorded_at_ms'] is None
    assert all(event.payload.get('kind')!='SOURCE_OBSERVED' for event in f.runtime.store.list_events())
    assert f.pr.create_calls==0


@pytest.mark.parametrize('change',['workstream','artifact','artifact_delete','artifact_rename','artifact_mode',
    'record_add','record_delete','record_rename','preference_add'])
def test_unproved_selected_data_membership_bytes_and_modes_refuse(ready,change):
    f=ready;root=f.env.seed
    if change=='workstream':
        path=root/'agentos/workstreams/WS-DEMO.md';path.write_text(path.read_text()+'\nChanged selected body.\n')
    elif change=='artifact':(root/'research/notes.md').write_text('Changed selected bytes.\n')
    elif change=='artifact_delete':(root/'research/notes.md').unlink()
    elif change=='artifact_rename':(root/'research/notes.md').rename(root/'research/renamed.md')
    elif change=='artifact_mode':(root/'research/notes.md').chmod(0o755)
    elif change=='record_add':
        (root/'agentos/decisions/DEC-NEW-ASSOCIATED.md').write_text(earlier_decision().replace('EARLIER-CALL','NEW-ASSOCIATED').replace('ALPHA','DEMO'))
    elif change=='record_delete':(root/'agentos/decisions/DEC-EARLIER-CALL.md').unlink()
    elif change=='record_rename':(root/'agentos/decisions/DEC-EARLIER-CALL.md').rename(root/'agentos/decisions/DEC-RENAMED.md')
    elif change=='preference_add':
        (root/'agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-DEMO.md').write_text(preference_decision('Literal preference','f'*64).replace('ALPHA','DEMO'))
    commit(f)
    with pytest.raises(CanonicalDataUnavailable):f.observe()
    assert f.pr.create_calls==0


@pytest.mark.parametrize('gate',['read','data','default','deadline'])
def test_continuity_acquisition_keeps_current_auth_default_and_original_deadline(ready,monkeypatch,gate):
    f=ready;unrelated(f)
    from control_plane import agentos_project_knowledge as reader
    from control_plane import project_canonical_data as data
    capture=reader.capture_selected_project_data_closure
    def changed(**kwargs):
        value=capture(**kwargs)
        if gate in {'read','data'}:setattr(f.state,gate,False)
        elif gate=='default':
            (f.env.seed/'docs/unrelated.md').write_text('Concurrent default movement.\n');commit(f)
        else:monkeypatch.setattr(data.time,'monotonic',lambda:kwargs['deadline']+.01)
        return value
    monkeypatch.setattr(reader,'capture_selected_project_data_closure',changed)
    with pytest.raises(CanonicalDataUnavailable):f.observe()


def test_wire_dict_or_foreign_nominal_owner_cannot_replace_issued_continuity(ready):
    f=ready;unrelated(f);view=f.observe()
    for proof in (view.witness()['data_continuity'],replace(view._continuity,_owner=object())):
        with pytest.raises(CanonicalDataUnavailable):replace(view,_continuity=proof).check()


def test_continuity_does_not_renew_a_capture_or_survive_default_change(ready):
    f=ready;unrelated(f);view=f.observe();deadline=view._operation.read_deadline
    with view.capture_scope() as capture:
        assert capture.operation.read_deadline<=deadline
        view.witness()
    assert view._operation.read_deadline==deadline
    (f.env.seed/'docs/unrelated.md').write_text('Later default.\n');commit(f)
    with pytest.raises(CanonicalDataUnavailable):view.check()


def test_identical_tree_on_unrelated_history_is_not_continuity(ready):
    f=ready
    old.git(f.env.seed,'checkout','--orphan','foreign-history')
    old.git(f.env.seed,'commit','-m','Same selected tree but unrelated ancestry')
    old.git(f.env.seed,'push','--force','origin','HEAD:main')
    with pytest.raises(CanonicalDataUnavailable):f.observe()


def test_partial_artifact_inventory_cannot_hide_an_omitted_member_change(ready):
    f=ready;ws=f.env.seed/'agentos/workstreams/WS-DEMO.md'
    extra=[]
    for number in range(33):
        path='research/selected-'+str(number)+('.txt' if number==32 else '.md');extra.append('- '+path)
        (f.env.seed/path).write_text('Selected artifact '+str(number)+'\n')
    ws.write_text(ws.read_text().replace('- research/notes.md','\n'.join(extra)))
    commit(f)
    # Configure C at the complete declared workstream, whose public reader has
    # only a partial first32 inventory; N changes only the omitted33rd member.
    base=old.rev_parse(f.env.seed,'HEAD');old.git(f.env.clone,'fetch','origin','main')
    old.git(f.env.clone,'checkout','--detach',base)
    f.publisher._canonical_data.code_commit=base
    (f.env.seed/'research/selected-32.txt').write_text('Changed unproved omitted bytes.\n');commit(f)
    with pytest.raises(CanonicalDataUnavailable):f.observe()


@pytest.mark.parametrize('entry',['../../private.md','mastermind:research/foreign.md'])
def test_invalid_or_unsupported_selected_reference_cannot_issue_continuity(ready,entry):
    f=ready;ws=f.env.seed/'agentos/workstreams/WS-DEMO.md'
    ws.write_text(ws.read_text().replace('research/notes.md',entry));commit(f)
    base=old.rev_parse(f.env.seed,'HEAD');old.git(f.env.clone,'fetch','origin','main')
    old.git(f.env.clone,'checkout','--detach',base);f.publisher._canonical_data.code_commit=base
    unrelated(f)
    with pytest.raises(CanonicalDataUnavailable):f.observe()

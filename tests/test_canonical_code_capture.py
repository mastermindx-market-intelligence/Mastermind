"""Per-view immutable CODE verification reuse, with current seal fences."""
from types import SimpleNamespace
import pytest
from tests.test_project_canonical_data import ready,env,isolated_git_env
from tests.test_installed_knowledge_data_materialization import installed
from integrations.executive_mcp.installed import _CANONICAL_CODE_CAPTURE,_installed_child_env
from tests.test_workspace_project_git_publisher import git


def configured(f,tmp_path):
    # Same installed composition as the signed journey: immutable CODE clone
    # is separate from the publisher clone whose fetch may add Git objects.
    code=tmp_path/'configured-code';git(tmp_path,'clone',str(f.env.origin),str(code))
    f.publisher._canonical_data.code_root=code
    return installed(SimpleNamespace(env=SimpleNamespace(clone=code)),tmp_path)


def take(collector,view):
    env=_installed_child_env(code_root=collector._code_root,macro_root=collector._macro_root)
    return collector._take_canonical_code_capture(view,env,deadline=view._operation.read_deadline)


def test_same_view_reuses_only_immutable_snapshot_once_with_original_deadline(ready,tmp_path):
    f=ready;collector=configured(f,tmp_path);capture=collector._capture_canonical_code();view=f.observe()
    collector._bind_canonical_code_capture(capture,view);deadline=view._operation.read_deadline
    with view.capture_scope():
        retained=take(collector,view)
        assert retained.macro_snapshot is capture.macro_snapshot
        assert retained.observations==capture.observations and take(collector,view) is None
    assert view._operation.read_deadline==deadline


@pytest.mark.parametrize('change',['source_body','macro_body','macro_mode','macro_new_path'])
def test_current_generation_refuses_mutation_after_verified_capture(ready,tmp_path,change):
    f=ready;collector=configured(f,tmp_path);capture=collector._capture_canonical_code();view=f.observe()
    collector._bind_canonical_code_capture(capture,view)
    if change=='source_body':(collector._source_root/'README.md').write_text('Changed current source.\n')
    elif change=='macro_body':(collector._macro_root/'scripts/agentos.py').write_text('Changed current Macro.\n')
    elif change=='macro_mode':(collector._macro_root/'scripts/agentos.py').chmod(0o755)
    else:
        path=collector._macro_root/'agentos/decisions/DEC-NEW.md';path.parent.mkdir(exist_ok=True)
        path.write_text('New untracked current record.\n')
    with pytest.raises(ValueError):take(collector,view)
    assert _CANONICAL_CODE_CAPTURE not in view._verified_facts


@pytest.mark.parametrize('forgery',['foreign_view','foreign_collector','dict','changed_binding','changed_principal'])
def test_snapshot_cannot_transfer_to_another_view_collector_or_binding(ready,tmp_path,forgery):
    f=ready;collector=configured(f,tmp_path);capture=collector._capture_canonical_code();view=f.observe()
    collector._bind_canonical_code_capture(capture,view)
    if forgery=='foreign_view':
        foreign=f.observe();foreign._verified_facts[_CANONICAL_CODE_CAPTURE]=view._verified_facts[_CANONICAL_CODE_CAPTURE]
        view=foreign
    elif forgery=='foreign_collector':
        collector=replace_capture_owner(collector,tmp_path/'foreign',f)
    elif forgery=='dict':view._verified_facts[_CANONICAL_CODE_CAPTURE]={'observations':capture.observations}
    elif forgery=='changed_principal':
        original=view._operation.principal
        view._operation.principal=type(original)(original.subject)
    else:collector._runner=lambda *args,**kwargs:None
    with pytest.raises(ValueError):take(collector,view)


def replace_capture_owner(collector,path,f):
    path.mkdir()
    return installed(f,path)


def test_discard_and_expiry_never_renew_or_transfer_snapshot(ready,tmp_path,monkeypatch):
    f=ready;collector=configured(f,tmp_path);capture=collector._capture_canonical_code();view=f.observe()
    collector._bind_canonical_code_capture(capture,view);collector._discard_canonical_code_capture(view)
    assert take(collector,view) is None
    collector._bind_canonical_code_capture(capture,view)
    from control_plane import project_canonical_data
    deadline=view._operation.read_deadline
    monkeypatch.setattr(project_canonical_data.time,'monotonic',lambda:deadline+.01)
    with pytest.raises(ValueError):take(collector,view)
    assert view._operation.read_deadline==deadline

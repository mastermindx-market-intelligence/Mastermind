"""Actual existing File publisher/Events/Git/nominal DATA view, no new grant.

Reuses the original fixture's explicit PR, principal/permission and physical
premises. File bytes and SourceObserved lineage are genuine disposable source.
No provider, installed service, private user file or Runtime Job is invoked.
"""
import pytest
from tests import test_project_canonical_data as source_fixture
from tests.test_project_canonical_data import env, isolated_git_env, actual_owner
from control_plane.project_plan_canonical_basis import capture_current_project_files
from tests.test_workspace_plan_adoption_git_publisher import old


@pytest.fixture
def ready(env, tmp_path, request, monkeypatch):
    # Match a newly created project's empty artifacts. The original fixture
    # intentionally declares an unresolved legacy research/notes.md reference;
    # keep that negative below rather than pretending it is a readable file.
    original = source_fixture.canonical_workstream
    monkeypatch.setattr(source_fixture, 'canonical_workstream', lambda:
        original().replace('artifacts:\n- research/notes.md', 'artifacts: []'))
    return source_fixture.ready.__wrapped__(env, tmp_path, request)


def test_actual_file_publication_captures_exact_untrusted_body(ready):
    f = ready
    f.land()
    view = f.observe()
    captured = capture_current_project_files(view, work_ref=old.WORK_REF)
    value = captured.material()
    image = next(image for image in f.recipe['postimages'] if image['path'] != old.CANONICAL_PATH)
    assert value['authority'] == 'UNTRUSTED_PROJECT_DATA'
    assert value['work_ref'] == old.WORK_REF
    assert value['executable_macro_commit'] == f.base
    assert value['canonical_data_commit'] == view.data_commit != f.base
    file = next(item for item in value['files'] if item['source']['path'] == image['path'])
    assert file['content_utf8'] == image['content_utf8']
    assert file['source']['content_sha256'] == image['content_sha256']
    assert view.witness()['source_operation']['selection']['action'] == 'add_project_file'
    value['files'].clear()
    assert captured.material()['files']  # Detached DATA, never a mutable proof.


def test_no_file_configured_project_and_foreign_or_forged_view(ready):
    view = ready.observe()
    value = capture_current_project_files(view, work_ref=old.WORK_REF).material()
    assert value['files'] == []
    with pytest.raises(ValueError):
        capture_current_project_files(view, work_ref='WS:FOREIGN')
    with pytest.raises(ValueError):
        capture_current_project_files({'files': []}, work_ref=old.WORK_REF)


@pytest.mark.parametrize('field', ['read', 'data'])
def test_current_grants_are_not_cached(ready, field):
    f = ready
    f.land()
    captured = capture_current_project_files(f.observe(), work_ref=old.WORK_REF)
    setattr(f.state, field, False)
    with pytest.raises(ValueError):
        captured.material()


def test_original_view_identity_and_expiry_remain_required(ready, monkeypatch):
    view = ready.observe()
    captured = capture_current_project_files(view, work_ref=old.WORK_REF)
    original = view._deadline
    object.__setattr__(view, '_deadline', original + 1)
    with pytest.raises(ValueError):
        captured.material()
    object.__setattr__(view, '_deadline', original)
    import time
    monkeypatch.setattr(time, 'monotonic', lambda: original + .001)
    with pytest.raises(ValueError):
        captured.material()


def test_declared_unreadable_file_is_not_silently_dropped(env, tmp_path, request):
    f = source_fixture.ready.__wrapped__(env, tmp_path, request)
    f.land()
    with pytest.raises(ValueError, match='PROJECT_PLANNING_FILE_CONTEXT_UNAVAILABLE'):
        capture_current_project_files(f.observe(), work_ref=old.WORK_REF)

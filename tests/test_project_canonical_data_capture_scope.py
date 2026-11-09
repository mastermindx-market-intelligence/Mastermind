"""Request-local capture reuse; real Git/Events with inert auth/PR seams.

No test dispatches the sibling's live signed journey or alters its worktree.
"""
from copy import deepcopy
import pytest
from tests.test_project_canonical_data import ready,env,isolated_git_env,old
from control_plane.project_canonical_data import CanonicalDataUnavailable
from control_plane.workspace_source_operations import SourceOperationEvents


def test_nested_capture_reuses_only_immutable_facts_and_keeps_full_boundaries(ready,monkeypatch):
 f=ready;f.land();view=f.observe();mode=view._owner
 counters=dict(full=0,default=0,blob=0)
 full,remote,blob=mode.check,f.publisher._remote_branch_commit,f.publisher._read_blob_at
 def checked(*args,**kwargs):counters['full']+=1;return full(*args,**kwargs)
 def observed(*args,**kwargs):counters['default']+=1;return remote(*args,**kwargs)
 def captured(*args,**kwargs):counters['blob']+=1;return blob(*args,**kwargs)
 monkeypatch.setattr(mode,'check',checked)
 monkeypatch.setattr(f.publisher,'_remote_branch_commit',observed)
 monkeypatch.setattr(f.publisher,'_read_blob_at',captured)
 original_deadline=view._operation.read_deadline
 with view.capture_scope() as capture:
  assert capture.operation is not view._operation
  assert capture.operation.read_deadline<=original_deadline
  with view.capture_scope():
   for _ in range(20):view.check();view.witness()
 assert counters==dict(full=2,default=2,blob=0),counters
 assert view._operation.read_deadline==original_deadline
 # A later logical capture needs its own fresh full fences; no stale scope.
 with view.capture_scope():view.check()
 assert counters==dict(full=4,default=4,blob=0),counters


@pytest.mark.parametrize('gate',['read','data'])
def test_capture_still_rechecks_current_permissions(ready,gate):
 f=ready;f.land();view=f.observe()
 with pytest.raises(CanonicalDataUnavailable):
  with view.capture_scope():
   setattr(f.state,gate,False)
   view.check()
 with pytest.raises(CanonicalDataUnavailable):view.check()


def test_capture_rechecks_default_before_returning_a_result(ready):
 f=ready;f.land();view=f.observe()
 with pytest.raises(CanonicalDataUnavailable):
  with view.capture_scope():
   changed=f.env.seed/'docs/external-change.md';changed.parent.mkdir(exist_ok=True);changed.write_text('External actor changed canonical default.\n')
   old.git(f.env.seed,'add','docs/external-change.md');old.git(f.env.seed,'commit','-m','External source change');old.git(f.env.seed,'push','origin','main')
   view.check()  # Private capture may finish, but post-fence must refuse it.


def test_capture_does_not_cache_actual_event_observations(ready,monkeypatch):
 f=ready;f.land();view=f.observe();read=SourceOperationEvents.read_status
 def changed(self,*args,**kwargs):
  value=deepcopy(read(self,*args,**kwargs))
  value['receipt']['recorded_at_ms']+=1
  return value
 with pytest.raises(CanonicalDataUnavailable):
  with view.capture_scope():
   monkeypatch.setattr(SourceOperationEvents,'read_status',changed)
   view.check()


def test_capture_does_not_cache_configured_code_identity(ready):
 f=ready;f.land();view=f.observe()
 with pytest.raises(CanonicalDataUnavailable):
  with view.capture_scope():
   (f.env.clone/'scripts/agentos.py').write_text('Changed configured source.\n')
   view.check()


def test_capture_never_renews_expired_original_or_shorter_caller_deadline(ready,monkeypatch):
 from control_plane import project_canonical_data as data
 f=ready;f.land();view=f.observe();original=view._operation.read_deadline
 with pytest.raises(CanonicalDataUnavailable):
  with view.capture_scope() as capture:
   with monkeypatch.context() as clock:
    clock.setattr(data.time,'monotonic',lambda:original+.01)
    view.check()
 assert view._operation.read_deadline==original
 with pytest.raises(CanonicalDataUnavailable):
  with view.capture_scope(deadline=data.time.monotonic()+2.0) as capture:
   assert capture.operation.read_deadline<original
   with monkeypatch.context() as clock:
    clock.setattr(data.time,'monotonic',lambda:capture.operation.read_deadline+.01)
    capture.remaining()
 assert view._operation.read_deadline==original


def test_capture_does_not_disable_checks_for_a_different_view(ready,monkeypatch):
 f=ready;f.land();first=f.observe();second=f.observe();mode=first._owner
 full=mode.check;calls=[]
 def observed(view,**kwargs):calls.append(view);return full(view,**kwargs)
 monkeypatch.setattr(mode,'check',observed)
 with first.capture_scope():second.check()
 assert calls==[first,second,first]

def test_capture_keeps_seam_identity_refusal_closed(ready,monkeypatch):
 f=ready;f.land();view=f.observe()
 with pytest.raises(CanonicalDataUnavailable,match='^CANONICAL_DATA_UNAVAILABLE$'):
  with view.capture_scope():
   monkeypatch.setattr(f.publisher,'_qualify_publisher',lambda _:True)
   view.check()

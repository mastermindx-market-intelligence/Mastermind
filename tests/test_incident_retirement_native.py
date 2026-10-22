"""Native no-replace and ACL resource boundaries; no installed-host effects."""
import errno
import os
import sys
from types import SimpleNamespace as S

import pytest

from control_plane import executive_incident_socket_retirement as r
from ops.executive_os.capacity_host_artifacts import CapacityHostArtifactError


@pytest.mark.skipif(sys.platform != 'darwin', reason='actual Darwin RENAME_EXCL')
def test_native_descriptor_relative_rename_preserves_inode_and_refuses_occupied_leaf(tmp_path):
    source, retained = tmp_path/'source', tmp_path/'retained'
    source.write_bytes(b'original inode')
    before = source.stat()
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        r._rename_exclusive(fd, source.name, fd, retained.name)
        assert not source.exists()
        after = retained.stat()
        assert (after.st_dev, after.st_ino, after.st_mode, after.st_uid,
                after.st_gid, after.st_nlink, after.st_size, after.st_mtime_ns,
                after.st_flags) == (before.st_dev, before.st_ino, before.st_mode,
                before.st_uid, before.st_gid, before.st_nlink, before.st_size,
                before.st_mtime_ns, before.st_flags)
        source.write_bytes(b'new generation')
        with pytest.raises(CapacityHostArtifactError, match='DESTINATION_EXISTS'):
            r._rename_exclusive(fd, source.name, fd, retained.name)
        assert retained.read_bytes() == b'original inode'
        assert source.read_bytes() == b'new generation'
    finally:
        os.close(fd)


class NativeCall:
    def __init__(self, callback): self.callback = callback
    def __call__(self, *args): return self.callback(*args)


@pytest.fixture
def acl(monkeypatch):
    state = S(pointer=None, error=errno.ENOENT, free_rc=0, allocated=False,
              calls=[], freed=[], fail_return_fence=False)
    def acquire(path, kind):
        state.calls.append((path, kind)); state.allocated = True
        r.ctypes.set_errno(state.error)
        return state.pointer
    def free(pointer):
        state.freed.append(pointer)
        return state.free_rc
    native = S(acl_get_link_np=NativeCall(acquire), acl_free=NativeCall(free))
    monkeypatch.setattr(r.ctypes, 'CDLL', lambda *a, **kw: native)
    monkeypatch.setattr(r, '_parent', lambda handles: None)
    class Budget:
        def check(self, **kwargs):
            if state.allocated and state.fail_return_fence: raise TimeoutError('original deadline')
    state.handles = S(budget=Budget())
    return state


def test_retained_acl_query_is_the_fixed_nofollow_path_and_native_type(acl):
    r._require_no_retained_acl(acl.handles)
    assert acl.calls == [((r.namespace._DIRECTORIES[-1]+'/'+r._RETAINED).encode('ascii'),
                          r.namespace.ACL_TYPE_EXTENDED)]
    assert acl.freed == []


@pytest.mark.parametrize('pointer,error', [(99, 0), (99, errno.ENOENT),
                                           (None, 0), (None, errno.EACCES)])
def test_acl_presence_or_unavailable_observation_refuses_and_frees(acl, pointer, error):
    acl.pointer, acl.error = pointer, error
    with pytest.raises(r.SocketRetirementError, match='RETAINED_ACL_UNPROVEN'):
        r._require_no_retained_acl(acl.handles)
    assert acl.freed == ([pointer] if pointer else [])


def test_return_side_deadline_never_leaks_allocated_acl(acl):
    acl.pointer, acl.fail_return_fence = 99, True
    with pytest.raises(TimeoutError, match='original deadline'):
        r._require_no_retained_acl(acl.handles)
    assert acl.freed == [99]


def test_acl_free_failure_is_not_success(acl):
    acl.pointer, acl.free_rc = 99, -1
    with pytest.raises(r.SocketRetirementError, match='CLEANUP_UNPROVEN'):
        r._require_no_retained_acl(acl.handles)
    assert acl.freed == [99]


def test_missing_native_acl_api_has_no_fallback(acl, monkeypatch):
    monkeypatch.setattr(r.ctypes, 'CDLL', lambda *a, **kw: S())
    with pytest.raises(AttributeError): r._require_no_retained_acl(acl.handles)
    assert not acl.calls and not acl.freed

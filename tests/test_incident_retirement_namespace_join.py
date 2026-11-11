"""Real retained-namespace validation joined to retirement; only native leaves fake.

Unlike the separate paid primitive leaf, these cases retain the unchanged actual
namespace acquisition, alias, socket shape, three-view identity and sticky failure
logic. No installed path, FD, subprocess or socket is touched.
"""
import errno
import stat
from types import SimpleNamespace as S

import pytest

from control_plane import executive_incident_socket_retirement as r
from tests import test_namespace_observation as namespace_fixture

M = namespace_fixture.M


@pytest.fixture
def joined(monkeypatch):
    world = namespace_fixture.NamespaceTests()
    world.setUp()
    world.socket = world.info(200)
    world.retained = None
    world.renames = []
    world.synced = []
    world.corrupt_after_move = {}
    monkeypatch.setattr(r, 'namespace', M)
    def relative(name, *, dir_fd, follow_symlinks):
        assert name == r._RETAINED
        assert world.fd_paths[dir_fd] == M._DIRECTORIES[-1]
        assert follow_symlinks is False
        if world.retained is None: raise FileNotFoundError(errno.ENOENT, 'inert absent')
        return world.retained
    monkeypatch.setattr(r, 'os', S(stat=relative, fsync=lambda fd: world.synced.append(fd)))
    def rename(source_parent, source, target_parent, target):
        assert source_parent == target_parent and world.fd_paths[source_parent] == M._DIRECTORIES[-1]
        assert (source, target) == (M._LEAF, r._RETAINED)
        assert world.retained is None and world.socket is not None
        world.renames.append((source_parent, source, target_parent, target))
        world.retained = S(**(vars(world.socket) | {'st_ctime_ns': 21} | world.corrupt_after_move))
        world.socket = None
    monkeypatch.setattr(r, '_rename_exclusive', rename)
    monkeypatch.setattr(r, '_require_no_retained_acl', lambda handles: None)
    world.handles = world.acquire()
    try:
        yield world
    finally:
        if not world.handles.closed: M._release_namespace(world.handles)
        assert world.fd_paths == {}
        world.doCleanups()


def test_real_namespace_join_preserves_inode_and_keeps_occupied_slot_sticky(joined):
    candidate = r._candidate(joined.handles)
    identity = r._retire(joined.handles, candidate)
    r._recheck_retained(joined.handles, identity)
    assert joined.socket is None and joined.retained.st_ino == 200
    assert joined.retained.st_ctime_ns == 21
    assert len(joined.renames) == len(joined.synced) == 1
    with pytest.raises(r.SocketRetirementError, match='RETAINED_SOCKET_OCCUPIED'):
        r._candidate(joined.handles)
    assert len(joined.renames) == 1 and joined.retained.st_ino == 200


@pytest.mark.parametrize('changes', [
    {'st_mode':stat.S_IFREG|0o660}, {'st_mode':stat.S_IFLNK|0o660},
    {'st_mode':stat.S_IFSOCK|0o666}, {'st_uid':0}, {'st_gid':0},
    {'st_nlink':2}, {'st_flags':2},
])
def test_real_incumbent_shape_and_flags_refuse_without_move(joined, changes):
    joined.socket = S(**(vars(joined.socket)|changes))
    with pytest.raises((r.SocketRetirementError, M.NamespaceObservationError)):
        r._candidate(joined.handles)
    assert not joined.renames and joined.retained is None and joined.socket is not None


@pytest.mark.parametrize('field,value', [('st_ino',201), ('st_mtime_ns',22), ('st_ctime_ns',22)])
def test_generation_change_between_candidate_and_move_refuses(joined, field, value):
    candidate = r._candidate(joined.handles)
    joined.socket = S(**(vars(joined.socket)|{field:value}))
    with pytest.raises(r.SocketRetirementError, match='GENERATION_DRIFT'):
        r._retire(joined.handles, candidate)
    assert not joined.renames and joined.retained is None


def test_retained_slot_race_before_move_preserves_both_nodes(joined):
    candidate = r._candidate(joined.handles)
    joined.retained = joined.info(999)
    with pytest.raises(r.SocketRetirementError, match='RETAINED_SOCKET_OCCUPIED'):
        r._retire(joined.handles, candidate)
    assert not joined.renames and joined.socket.st_ino == 200 and joined.retained.st_ino == 999


@pytest.mark.parametrize('changes', [
    {'st_ino':201}, {'st_dev':2}, {'st_mode':stat.S_IFREG|0o660},
    {'st_uid':0}, {'st_gid':0}, {'st_nlink':2}, {'st_size':1},
    {'st_mtime_ns':22}, {'st_flags':2},
])
def test_post_move_mismatch_retains_actual_node_without_rollback_or_retry(joined, changes):
    candidate = r._candidate(joined.handles)
    joined.corrupt_after_move = changes
    with pytest.raises(r.SocketRetirementError, match='RETAINED_SOCKET_MISMATCH'):
        r._retire(joined.handles, candidate)
    assert len(joined.renames) == 1 and joined.socket is None and joined.retained is not None
    with pytest.raises(r.SocketRetirementError, match='RETAINED_SOCKET_OCCUPIED'):
        r._candidate(joined.handles)
    assert len(joined.renames) == 1


def test_namespace_replacement_invalidates_original_handles_before_move(joined):
    candidate = r._candidate(joined.handles)
    parent = M._DIRECTORIES[-1]
    original = joined.infos[parent]
    joined.infos[parent] = S(**(vars(original)|{'st_ino':999}))
    with pytest.raises(M.NamespaceObservationError, match='REPLACED'):
        r._retire(joined.handles, candidate)
    joined.infos[parent] = original
    with pytest.raises(M.NamespaceObservationError, match='CONTEXT_UNAVAILABLE'):
        r._retire(joined.handles, candidate)
    assert not joined.renames


def test_generic_absence_gate_still_rejects_a_valid_incumbent_socket(joined):
    with pytest.raises(M.NamespaceObservationError, match='SOCKET_PREEXISTS'):
        M._require_socket_absent(joined.handles)
    assert joined.socket.st_ino == 200 and not joined.renames


def test_canonical_reappearance_after_move_is_refused_and_retained_node_kept(joined, monkeypatch):
    candidate = r._candidate(joined.handles)
    original = r._rename_exclusive
    def rename(*args):
        original(*args)
        joined.socket = joined.info(999)
    monkeypatch.setattr(r, '_rename_exclusive', rename)
    with pytest.raises(M.NamespaceObservationError, match='SOCKET_PREEXISTS'):
        r._retire(joined.handles, candidate)
    assert len(joined.renames) == 1 and joined.socket.st_ino == 999 and joined.retained.st_ino == 200

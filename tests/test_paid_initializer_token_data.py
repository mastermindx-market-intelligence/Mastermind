"""Inert private DATA fixtures only; no live helper or credential access."""
import fcntl
import hashlib
import json
import os
import pickle
from pathlib import Path
import sys
from unittest import mock

import pytest

from ops.native_fabric.quota_continuity.candidate import paid_initializer_token_data as data

# Public synthetic values, never a real credential.
INERT_TOKEN = "a" * 32
RAW = ('export GLM_SHIM_TOKEN="' + INERT_TOKEN + '"\n').encode()


def test_private_shape_and_serialization_are_non_echo():
    value = data.parse_helper_data(RAW)
    assert repr(value) == str(value) == "<PrivateTokenData>"
    for operation in (json.dumps, pickle.dumps):
        with pytest.raises(TypeError) as caught:
            operation(value)
        assert INERT_TOKEN not in str(caught.value)
    with pytest.raises(AttributeError):
        value._token = b"other"
    assert not hasattr(value, "token") and not hasattr(value, "__dict__")


@pytest.mark.parametrize("bad", [
    None, True, RAW.decode(), bytearray(RAW), b"", RAW[:-1], RAW+b"\n",
    RAW.replace(b"\n", b"\r\n"), b"\xef\xbb\xbf"+RAW, b" "+RAW,
    RAW.replace(b"a", b"A"), RAW.replace(b'"', b"'"),
    RAW.replace(b"a"*32, b"$(touch NEVER)"),
    RAW.replace(b"a"*32, b"`touch NEVER`"),
    RAW.replace(b"a"*32, b"${INERT}"),
    RAW.replace(b"a"*32, b"<(echo NEVER)"),
    RAW.replace(b"GLM_SHIM_TOKEN", b"OTHER_TOKEN"),
    RAW+b"exit 0\n", RAW+b"# comment\n", RAW.replace(b"\n", b";\n"),
    b"function x(){ :; }; "+RAW, RAW+b"\xff", b"a"*65537,
])
def test_executable_or_noncanonical_helper_refused(bad):
    with pytest.raises(data.TokenDataRefused) as caught:
        data.parse_helper_data(bad)
    assert str(caught.value) == "paid_helper_data_refused"
    assert caught.value.__suppress_context__


def test_private_environment_is_explicit_immutable_and_non_echo():
    before = dict(os.environ)
    value = data.parse_helper_data(RAW)
    env = value.child_environment({"HOME": "/inert", "PATH": "/usr/bin"})
    assert env["GLM_SHIM_TOKEN"] == INERT_TOKEN
    assert repr(env) == str(env) == "<PrivateEnvironment>"
    assert INERT_TOKEN not in repr(env.items())
    for operation in (json.dumps, pickle.dumps):
        with pytest.raises(TypeError):
            operation(env)
    with pytest.raises(TypeError):
        env["GLM_SHIM_TOKEN"] = "other"
    with pytest.raises(TypeError):
        env._values["GLM_SHIM_TOKEN"] = "other"
    assert dict(os.environ) == before
    value.verify_environment(env)


@pytest.mark.parametrize("base", [
    {"GLM_SHIM_TOKEN": "b"*32}, {"KEY": "bad\0value"}, {"BAD KEY": "x"},
    {"KEY": 1}, {"KEY": "x"*65536}, {"BASH_ENV": "/not-run"},
    {"ENV": "/not-run"}, {"BASH_FUNC_x%%": "() { :; }"},
    {"LD_PRELOAD": "/not-run"}, {"PYTHONHOME": "/not-used"},
    {"PYTHONEXECUTABLE": "/not-used"}, {"__PYVENV_LAUNCHER__": "/not-used"},
])
def test_private_environment_drift_refuses_without_repair(base):
    with pytest.raises(data.TokenDataRefused):
        data.parse_helper_data(RAW).child_environment(base)


@pytest.mark.parametrize("environment", [{}, {"GLM_SHIM_TOKEN": ""},
    {"GLM_SHIM_TOKEN": "b"*32}, {"GLM_SHIM_TOKEN": 1}])
def test_post_hook_missing_or_changed_token_refuses(environment):
    value = data.parse_helper_data(RAW)
    with pytest.raises(data.TokenDataRefused):
        value.verify_environment(environment)
    assert environment.get("GLM_SHIM_TOKEN") != INERT_TOKEN


@pytest.fixture
def origin(tmp_path):
    path = tmp_path/"synthetic-private-helper"
    path.write_bytes(RAW); path.chmod(0o600)
    fd = os.open(path, os.O_RDONLY)
    info = os.fstat(fd)
    expected = dict(sha256=hashlib.sha256(RAW).hexdigest(), size=len(RAW),
                    uid=info.st_uid, gid=info.st_gid, mode=0o600)
    try:
        yield path, fd, expected
    finally:
        os.close(fd)


def test_actual_posix_origin_read_preserves_offset(origin):
    _path, fd, expected = origin
    os.lseek(fd, 3, os.SEEK_SET)
    raw, identity = data._read_origin(fd, expected)
    assert hashlib.sha256(raw).hexdigest() == expected["sha256"]
    assert len(identity) == 9 and os.lseek(fd, 0, os.SEEK_CUR) == 3


@pytest.mark.parametrize("flags", [os.O_RDWR, os.O_WRONLY])
def test_actual_write_capable_origin_fd_refuses(origin, flags):
    path, _fd, expected = origin
    fd = os.open(path, flags)
    try:
        with pytest.raises(data.TokenDataRefused):
            data._read_origin(fd, expected)
    finally:
        os.close(fd)


@pytest.mark.parametrize("field", ["uid", "gid", "size", "mode", "sha256"])
def test_origin_mismatch_refuses(origin, field):
    _path, fd, expected = origin
    changed = dict(expected)
    changed[field] = "0"*64 if field == "sha256" else changed[field]+1
    with pytest.raises(data.TokenDataRefused):
        data._read_origin(fd, changed)


def test_actual_origin_multiple_links_refuse(origin, tmp_path):
    path, fd, expected = origin
    os.link(path, tmp_path/"other-link")
    with pytest.raises(data.TokenDataRefused):
        data._read_origin(fd, expected)


def test_actual_origin_changed_during_copy_refuses(origin):
    path, fd, expected = origin
    original = os.pread
    def changed(read_fd, size, offset):
        raw = original(read_fd, size, offset)
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns+1000000))
        return raw
    with mock.patch.object(os, "pread", side_effect=changed):
        with pytest.raises(data.TokenDataRefused):
            data._read_origin(fd, expected)


def test_snapshot_identity_mismatch_refuses_before_seal_use(origin, tmp_path):
    _path, fd, expected = origin
    other = tmp_path/"same-inert-bytes-different-object"
    other.write_bytes(RAW);other.chmod(0o600)
    other_fd = os.open(other, os.O_RDONLY)
    try:
        with pytest.raises(data.TokenDataRefused):
            data._check_snapshot(other_fd, expected["sha256"], expected["size"],
                                 data._identity(os.fstat(fd)))
    finally:os.close(other_fd)


@pytest.mark.parametrize("field,value", [
    ("uid", True), ("uid", 0), ("uid", 2**31), ("gid", False),
    ("mode", True), ("mode", 0o644), ("size", True), ("size", 0),
    ("sha256", "A"*64), ("sha256", "0"*63),
])
def test_expected_fingerprint_inputs_remain_closed(origin, field, value):
    expected = dict(origin[2]); expected[field] = value
    with pytest.raises(data.TokenDataRefused):data._expected(expected)
    expected = dict(origin[2], path="not-an-origin-authority")
    with pytest.raises(data.TokenDataRefused):data._expected(expected)


def test_arbitrary_mapping_error_cannot_echo_private_value():
    from collections.abc import Mapping
    class Broken(Mapping):
        def __getitem__(self,key): raise RuntimeError(INERT_TOKEN)
        def __iter__(self): raise RuntimeError(INERT_TOKEN)
        def __len__(self): return 1
    with pytest.raises(data.TokenDataRefused) as caught:
        data.parse_helper_data(RAW).child_environment(Broken())
    assert INERT_TOKEN not in str(caught.value)
    assert caught.value.__suppress_context__


def test_unsupported_platform_has_no_snapshot_fallback(origin):
    _path, fd, expected = origin
    with mock.patch.object(data.sys, "platform", "unsupported"):
        with pytest.raises(data.TokenDataRefused):
            with data.freeze_helper_data(fd, expected=expected):
                pytest.fail("unsupported snapshot yielded")
    os.fstat(fd)


@pytest.mark.skipif(sys.platform != "linux" or not hasattr(os, "memfd_create"),
                    reason="actual Linux memfd/seals, no synthetic substitute")
class TestLinuxFrozenData:
    def test_real_seals_custody_private_env_and_cleanup(self, origin):
        _path, fd, expected = origin
        if not expected["uid"] or not expected["gid"]:
            pytest.skip("positive-account helper profile requires nonroot fixture owner")
        os.lseek(fd, 2, os.SEEK_SET)
        with data.freeze_helper_data(fd, expected=expected) as frozen:
            snapshot = frozen.snapshot_fd
            origin_dup = frozen._origin
            assert not os.get_inheritable(snapshot) and not os.get_inheritable(origin_dup)
            required = fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
            assert fcntl.fcntl(snapshot, fcntl.F_GET_SEALS)&required == required
            assert set(frozen.fingerprint) == {"schema_version","sha256","size","uid","gid","mode"}
            assert INERT_TOKEN not in repr(frozen.fingerprint)
            env = frozen.private_data.child_environment({"HOME":"/inert"})
            frozen.private_data.verify_environment(env)
            frozen.check()
            assert os.lseek(fd, 0, os.SEEK_CUR) == 2
        for owned in (snapshot, origin_dup):
            with pytest.raises(OSError): os.fstat(owned)
        os.fstat(fd)
        with pytest.raises(data.TokenDataRefused): frozen.check()
        with pytest.raises(data.TokenDataRefused): frozen.private_data
        with pytest.raises(data.TokenDataRefused): frozen.snapshot_fd
        frozen.close()

    def test_late_origin_change_refuses_and_closes(self, origin):
        path, fd, expected = origin
        if not expected["uid"] or not expected["gid"]:
            pytest.skip("positive-account helper profile requires nonroot fixture owner")
        with pytest.raises(data.TokenDataRefused):
            with data.freeze_helper_data(fd, expected=expected) as frozen:
                owned = (frozen.snapshot_fd, frozen._origin)
                path.write_bytes(RAW.replace(b"a", b"b"))
                frozen.check()
        for value in owned:
            with pytest.raises(OSError): os.fstat(value)
        os.fstat(fd)

    def test_body_failure_repeatedly_disposes_private_fds(self, origin):
        _path, fd, expected = origin
        if not expected["uid"] or not expected["gid"]:
            pytest.skip("positive-account helper profile requires nonroot fixture owner")
        for _ in range(12):
            with pytest.raises(RuntimeError, match="inert body"):
                with data.freeze_helper_data(fd, expected=expected) as frozen:
                    owned = (frozen.snapshot_fd, frozen._origin)
                    raise RuntimeError("inert body")
            for value in owned:
                with pytest.raises(OSError): os.fstat(value)


    @pytest.mark.parametrize("operation", ["write", "shrink", "grow"])
    def test_denied_mutation_never_rebaselines_snapshot_custody(self, origin, operation):
        """Linux can update times on a denied write; immutable bytes != identity."""
        _path, fd, expected = origin
        if not expected["uid"] or not expected["gid"]:
            pytest.skip("positive-account helper profile requires nonroot fixture owner")
        context=data.freeze_helper_data(fd, expected=expected)
        frozen=context.__enter__()
        snapshot=frozen.snapshot_fd;owned=(snapshot,frozen._origin)
        before=frozen._snapshot_identity
        try:
            attempt={"write":lambda:os.write(snapshot,b"x"),
                     "shrink":lambda:os.ftruncate(snapshot,len(RAW)-1),
                     "grow":lambda:os.ftruncate(snapshot,len(RAW)+1)}[operation]
            with pytest.raises(OSError):attempt()
            assert os.pread(snapshot,len(RAW)+1,0)==RAW
            drift=data._identity(os.fstat(snapshot))!=before
            assert frozen._snapshot_identity==before  # no silent rebaseline
            if drift:
                with pytest.raises(data.TokenDataRefused):frozen.check()
            else:frozen.check()
        except BaseException:
            context.__exit__(*sys.exc_info())
            raise
        else:
            if drift:
                # Exit also rechecks custody and closes both owned FDs even
                # when a denied syscall changed only snapshot timestamps.
                with pytest.raises(data.TokenDataRefused):context.__exit__(None,None,None)
            else:context.__exit__(None,None,None)
        for value in owned:
            with pytest.raises(OSError):os.fstat(value)
        os.fstat(fd)

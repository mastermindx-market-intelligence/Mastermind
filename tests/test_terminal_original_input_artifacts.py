"""Tests for the terminal original input filesystem custody helper.

Tests import the actual control_plane helper module. The identity-drift test
uses a monkeypatched boundary UID because no real second UID is available in
this environment; that limitation is stated in its docstring.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from control_plane import terminal_original_input_artifacts as toi

CMD = "cmd-001"
ISSUER = "a" * 64
FINGERPRINT = "b" * 64
PAYLOAD = b"terminal private original input\nline2\n"
CANARY = b"CANARY-7f3a-private-original"


def make_helper(root):
    return toi.TerminalOriginalInputArtifacts(root)


def key_dir(root, cmd=CMD, issuer=ISSUER):
    return root / toi.PRIVATE_SUBDIR / toi._stable_key(cmd, issuer)


def artifact_path(root, cmd=CMD, issuer=ISSUER):
    return key_dir(root, cmd, issuer) / toi.ARTIFACT_FILENAME


def prepare(h, cmd=CMD, issuer=ISSUER, fp=FINGERPRINT, payload=PAYLOAD):
    return h.prepare(
        command_id=cmd, issuer_scope_sha256=issuer, fingerprint_sha256=fp, payload=payload
    )


def read(h, digest, cmd=CMD, issuer=ISSUER, fp=FINGERPRINT):
    return h.read(
        command_id=cmd,
        issuer_scope_sha256=issuer,
        fingerprint_sha256=fp,
        expected_artifact_sha256=digest,
    )


def code_of(exc_info):
    assert isinstance(exc_info.value, toi.TerminalInputError)
    return exc_info.value.code


def expect(err_ctx, code):
    assert code_of(err_ctx) == code


def test_prepare_roundtrip_receipt_shape_and_layout(tmp_path):
    root_mode = os.stat(tmp_path).st_mode
    h = make_helper(tmp_path)
    ref = prepare(h)
    assert ref.schema == toi.REFERENCE_SCHEMA
    assert ref.input_ref.startswith("terminal-input:")
    assert ref.payload_sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    blob = artifact_path(tmp_path).read_bytes()
    header_blob, _, payload = blob.partition(b"\n")
    assert payload == PAYLOAD
    assert ref.artifact_sha256 == hashlib.sha256(blob).hexdigest()
    header = json.loads(header_blob.decode("ascii"))
    assert set(header) == {
        "schema",
        "command_id",
        "issuer_scope_sha256",
        "fingerprint_sha256",
        "payload_sha256",
    }
    assert read(h, ref.artifact_sha256) == PAYLOAD
    st = os.stat(artifact_path(tmp_path), follow_symlinks=False)
    assert stat.S_ISREG(st.st_mode) and st.st_nlink == 1
    assert (st.st_mode & 0o7777) == 0o600 and st.st_uid == os.geteuid()
    for d in (tmp_path / toi.PRIVATE_SUBDIR, key_dir(tmp_path)):
        assert (os.stat(d).st_mode & 0o7777) == 0o700
    assert os.stat(tmp_path).st_mode == root_mode  # caller root never chmodded
    public = json.dumps(ref.to_dict())
    assert set(ref.to_dict()) == {"schema", "input_ref", "artifact_sha256", "payload_sha256"}
    assert PAYLOAD.decode("utf-8", "replace") not in public and str(tmp_path) not in public


def test_reconcile_same_identity_retains_inode_bytes_and_receipt(tmp_path):
    h = make_helper(tmp_path)
    ref1 = prepare(h)
    path = artifact_path(tmp_path)
    before = os.stat(path, follow_symlinks=False)
    original = path.read_bytes()
    assert prepare(h) == ref1  # read-only reconciliation, same receipt
    after = os.stat(path, follow_symlinks=False)
    assert (after.st_dev, after.st_ino, after.st_mtime_ns) == (
        before.st_dev,
        before.st_ino,
        before.st_mtime_ns,
    )
    assert path.read_bytes() == original and after.st_nlink == 1


def test_directory_key_excludes_payload_and_fingerprint(tmp_path):
    h = make_helper(tmp_path)
    key = toi._stable_key(CMD, ISSUER)
    assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
    assert prepare(h).input_ref == f"terminal-input:{key}"
    with pytest.raises(toi.TerminalInputError) as exc:
        prepare(h, fp="c" * 64, payload=b"other")  # must conflict, never re-key
    expect(exc, toi.TERMINAL_INPUT_CONFLICT)
    assert os.listdir(tmp_path / toi.PRIVATE_SUBDIR) == [key]
    assert os.listdir(key_dir(tmp_path)) == [toi.ARTIFACT_FILENAME]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"payload": b""},
        {"payload": b"x" * (toi.MAX_PAYLOAD_BYTES + 1)},
        {"payload": "text"},
        {"payload": bytearray(b"bytes-like")},
        {"cmd": ""},
        {"cmd": "has space"},
        {"cmd": ".leading-dot"},
        {"cmd": "x" * 129},
        {"issuer": "A" * 64},
        {"issuer": "a" * 63},
        {"fp": "z" * 64},
    ],
)
def test_invalid_scalars_rejected_without_writes(tmp_path, kwargs):
    h = make_helper(tmp_path)
    with pytest.raises(toi.TerminalInputError) as exc:
        prepare(h, **kwargs)
    expect(exc, toi.TERMINAL_INPUT_INVALID)
    assert not (tmp_path / toi.PRIVATE_SUBDIR).exists()


@pytest.mark.parametrize(
    "mutate,expected_code",
    [
        ("empty", toi.TERMINAL_INPUT_UNAVAILABLE),
        ("truncate_header", toi.TERMINAL_INPUT_UNAVAILABLE),
        ("truncate_payload", toi.TERMINAL_INPUT_UNAVAILABLE),
        ("payload_flip", toi.TERMINAL_INPUT_UNAVAILABLE),
        ("append", toi.TERMINAL_INPUT_UNAVAILABLE),
        ("header_command", toi.TERMINAL_INPUT_CONFLICT),
    ],
)
def test_damaged_file_refuses_and_leaves_original_with_no_replacement(tmp_path, mutate, expected_code):
    h = make_helper(tmp_path)
    prepare(h)
    path = artifact_path(tmp_path)
    blob = path.read_bytes()
    header_len = blob.index(b"\n") + 1
    damaged = {
        "empty": b"",
        "truncate_header": blob[: header_len - 8],
        "truncate_payload": blob[:-3],
        "payload_flip": blob[: len(blob) - 1] + bytes([blob[-1] ^ 0x01]),
        "append": blob + b"x",
        "header_command": blob.replace(b'"cmd-001"', b'"cmd-002"', 1),
    }[mutate]
    with open(path, "wb") as fh:
        fh.write(damaged)
    inode = os.stat(path).st_ino
    with pytest.raises(toi.TerminalInputError) as exc:
        prepare(h)
    with pytest.raises(toi.TerminalInputError) as exc_read:
        read(h, "f" * 64)
    expect(exc, expected_code)
    assert code_of(exc_read) in (toi.TERMINAL_INPUT_CONFLICT, toi.TERMINAL_INPUT_UNAVAILABLE)
    assert os.stat(path).st_ino == inode  # original retained, never rewritten
    assert path.read_bytes() == damaged
    assert os.listdir(key_dir(tmp_path)) == [toi.ARTIFACT_FILENAME]  # no replacement path


def test_issuer_separation_and_foreign_expected_digest_denied(tmp_path):
    h = make_helper(tmp_path)
    ref_a = prepare(h, issuer=ISSUER, payload=PAYLOAD)
    payload_b = b"issuer b private"
    ref_b = prepare(h, issuer="9" * 64, fp="d" * 64, payload=payload_b)
    assert ref_a.input_ref != ref_b.input_ref
    # Directory enumeration order carries no issuer-custody meaning.
    assert sorted(os.listdir(tmp_path / toi.PRIVATE_SUBDIR)) == sorted([
        toi._stable_key(CMD, ISSUER),
        toi._stable_key(CMD, "9" * 64),
    ])
    with pytest.raises(toi.TerminalInputError) as exc:
        read(h, ref_b.artifact_sha256)  # issuer A identity, B's digest
    expect(exc, toi.TERMINAL_INPUT_CONFLICT)
    with pytest.raises(toi.TerminalInputError) as exc2:
        read(h, ref_a.artifact_sha256, issuer="9" * 64, fp="d" * 64)
    expect(exc2, toi.TERMINAL_INPUT_CONFLICT)
    assert read(h, ref_b.artifact_sha256, issuer="9" * 64, fp="d" * 64) == payload_b


def test_symlink_hardlink_and_wrong_mode_rejected(tmp_path):
    h = make_helper(tmp_path)
    ref = prepare(h)
    path = artifact_path(tmp_path)
    os.chmod(path, 0o644)
    with pytest.raises(toi.TerminalInputError) as exc_mode:
        read(h, ref.artifact_sha256)
    expect(exc_mode, toi.TERMINAL_INPUT_UNAVAILABLE)
    os.chmod(path, 0o600)
    os.chmod(key_dir(tmp_path), 0o755)
    with pytest.raises(toi.TerminalInputError) as exc_dir:
        read(h, ref.artifact_sha256)
    expect(exc_dir, toi.TERMINAL_INPUT_UNAVAILABLE)
    os.chmod(key_dir(tmp_path), 0o700)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(path.read_bytes())
    os.chmod(outside, 0o600)
    os.unlink(path)
    os.symlink(outside, path)
    with pytest.raises(toi.TerminalInputError) as exc_link:
        read(h, ref.artifact_sha256)
    expect(exc_link, toi.TERMINAL_INPUT_UNAVAILABLE)
    os.unlink(path)
    with open(path, "wb") as fh:
        fh.write(outside.read_bytes())
    os.chmod(path, 0o600)
    os.link(path, key_dir(tmp_path) / "hard.bin")
    with pytest.raises(toi.TerminalInputError) as exc_hard:
        read(h, ref.artifact_sha256)
    expect(exc_hard, toi.TERMINAL_INPUT_UNAVAILABLE)


def test_symlinked_private_subdir_rejected(tmp_path):
    h = make_helper(tmp_path)
    prepare(h)
    real = tmp_path / toi.PRIVATE_SUBDIR
    outside = tmp_path / "outside-root"
    outside.mkdir(mode=0o700)
    os.rename(real, tmp_path / "moved-aside")
    os.symlink(outside, real)
    with pytest.raises(toi.TerminalInputError) as exc:
        prepare(h)
    expect(exc, toi.TERMINAL_INPUT_UNAVAILABLE)
    assert os.listdir(outside) == []


def _plain_file(p):
    f = p / "not-a-dir"
    f.write_bytes(b"x")
    return f


def _group_writable(p):
    d = p / "unsafe-root"
    d.mkdir(mode=0o700)
    os.chmod(d, 0o770)
    return d


def _symlinked_root(p):
    d = p / "real-root"
    d.mkdir(mode=0o700)
    link = p / "link-root"
    os.symlink(d, link)
    return link


@pytest.mark.parametrize(
    "root_factory,expected_code",
    [
        (lambda p: p / "missing", toi.TERMINAL_INPUT_UNAVAILABLE),
        (_plain_file, toi.TERMINAL_INPUT_UNAVAILABLE),
        (_group_writable, toi.TERMINAL_INPUT_UNAVAILABLE),
        (_symlinked_root, toi.TERMINAL_INPUT_INVALID),
    ],
)
def test_unsafe_or_unavailable_roots_rejected(tmp_path, root_factory, expected_code):
    target = root_factory(tmp_path)
    with pytest.raises(toi.TerminalInputError) as exc:
        h = toi.TerminalOriginalInputArtifacts(target)
        prepare(h)
    expect(exc, expected_code)


def test_relative_root_bad_digest_and_absent_read(tmp_path):
    with pytest.raises(toi.TerminalInputError) as exc:
        toi.TerminalOriginalInputArtifacts(Path("relative/root"))
    expect(exc, toi.TERMINAL_INPUT_INVALID)
    h = make_helper(tmp_path)
    ref = prepare(h)
    for bad in ("F" * 64, "f" * 63, "not-hex"):
        with pytest.raises(toi.TerminalInputError) as exc_digest:
            read(h, bad)
        expect(exc_digest, toi.TERMINAL_INPUT_INVALID)
    with pytest.raises(toi.TerminalInputError) as exc_missing:
        read(h, "0" * 64, cmd="never-prepared")
    expect(exc_missing, toi.TERMINAL_INPUT_UNAVAILABLE)
    assert not (tmp_path / toi.PRIVATE_SUBDIR / toi._stable_key("never-prepared", ISSUER)).exists()
    assert read(h, ref.artifact_sha256) == PAYLOAD


def test_root_replaced_after_prepare_is_unavailable(tmp_path):
    h = make_helper(tmp_path)
    ref = prepare(h)
    os.rename(tmp_path, tmp_path.with_name(tmp_path.name + "-moved"))
    with pytest.raises(toi.TerminalInputError) as exc:
        read(h, ref.artifact_sha256)
    expect(exc, toi.TERMINAL_INPUT_UNAVAILABLE)


def test_private_canary_absent_from_receipts_and_error_strings(tmp_path):
    h = make_helper(tmp_path)
    ref = prepare(h, payload=CANARY)
    surfaces = [
        json.dumps(ref.to_dict()),
        repr(ref),
        str(ref),
        repr(ref.to_dict()),
    ]
    with pytest.raises(toi.TerminalInputError) as exc:
        prepare(h, payload=CANARY + b"-changed")
    with pytest.raises(toi.TerminalInputError) as exc2:
        prepare(h, payload=CANARY, fp="c" * 64)
    for e in (exc, exc2):
        assert e.value.code in (
            toi.TERMINAL_INPUT_INVALID,
            toi.TERMINAL_INPUT_CONFLICT,
            toi.TERMINAL_INPUT_UNAVAILABLE,
        )
        surfaces.extend([str(e.value), repr(e.value)])
    for surface in surfaces:
        assert CANARY.decode() not in surface and str(tmp_path) not in surface


def test_identity_drift_monkeypatched_uid_rejected(tmp_path):
    """No real second UID is available here; boundary identity drift is
    simulated by monkeypatching the helper's boundary UID source (labelled
    honestly as simulation, not a real cross-UID test)."""
    h = make_helper(tmp_path)
    ref = prepare(h, payload=b"plain")
    original = toi._current_uid
    toi._current_uid = lambda: original() + 4242
    try:
        with pytest.raises(toi.TerminalInputError) as exc:
            read(h, ref.artifact_sha256)
        expect(exc, toi.TERMINAL_INPUT_UNAVAILABLE)
        with pytest.raises(toi.TerminalInputError) as exc2:
            prepare(h, payload=b"plain")
        expect(exc2, toi.TERMINAL_INPUT_UNAVAILABLE)
    finally:
        toi._current_uid = original
    assert read(h, ref.artifact_sha256) == b"plain"  # restored boundary identity


def test_no_lookup_api_from_public_reference(tmp_path):
    h = make_helper(tmp_path)
    ref = prepare(h)
    forbidden = {"resolve", "lookup", "open_ref", "from_ref", "get", "get_by_ref", "list", "search"}
    assert not ({n for n in dir(h) if not n.startswith("_")} & forbidden)
    assert not ({n for n in vars(toi) if not n.startswith("_")} & forbidden)
    params = set(inspect.signature(h.read).parameters)
    assert params == {
        "command_id",
        "issuer_scope_sha256",
        "fingerprint_sha256",
        "expected_artifact_sha256",
    }
    with pytest.raises(TypeError):
        h.read(
            input_ref=ref.input_ref,
            command_id=CMD,
            issuer_scope_sha256=ISSUER,
            fingerprint_sha256=FINGERPRINT,
            expected_artifact_sha256=ref.artifact_sha256,
        )

"""Per-connection AEAD qualification; ownership is simulated, file IO is real."""
import io
import os
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from control_plane import executive_installed_peer as peer
from ops.executive_os import control_aead_profile as profile
from test_executive_control_aead_profile import simulated_custody


@pytest.fixture
def installed_profile(tmp_path, monkeypatch):
    release, artifact, uid = simulated_custody(tmp_path, monkeypatch)
    details = profile.materialize_bundle(artifact, release, operator_uid=uid)
    # Simulate only root custody/ancestor paths. Actual descriptor identities,
    # directory walks, no-follow checks, modes and per-file ACL checks remain.
    fake_os = SimpleNamespace(**vars(os))
    def owned(info):
        return SimpleNamespace(**{name: getattr(info, name) for name in (
            'st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size',
            'st_mtime_ns', 'st_ctime_ns')}, st_uid=0, st_gid=0)
    fake_os.lstat = lambda path: owned(os.lstat(path))
    fake_os.fstat = lambda fd: owned(os.fstat(fd))
    monkeypatch.setattr(peer, 'os', fake_os)
    monkeypatch.setattr(peer, '_observe_ancestors', lambda *a: ())
    monkeypatch.setattr(peer, 'has_macos_acl', lambda *a, **k: False)
    raw = {'proof_base_sha': release.name, 'control_uid': 450,
           'reply_events': {'armed': True}}
    return raw, str(release), Path(details['root'])


def test_only_one_full_verification_per_connection_with_fresh_race_checks(installed_profile, monkeypatch):
    raw, release, root = installed_profile
    calls = []
    real = profile.verify_profile
    def verify(*a, **k):
        calls.append(True)
        return real(*a, **k)
    monkeypatch.setattr(profile, 'verify_profile', verify)
    budget = peer._Budget(25)
    first = peer._observe_control_aead(raw, release, budget)
    for _ in range(2):
        assert peer._observe_control_aead(raw, release, budget, first) == first
    assert len(calls) == 1
    peer._observe_control_aead(raw, release, peer._Budget(25))
    assert len(calls) == 2  # Another connection cannot inherit the observation.


@pytest.mark.parametrize('change', ['bytes', 'replace', 'extra', 'remove', 'symlink', 'hardlink', 'mode', 'acl', 'lock', 'manifest'])
def test_race_check_refuses_profile_drift(installed_profile, monkeypatch, change):
    raw, release, root = installed_profile
    budget = peer._Budget(25)
    first = peer._observe_control_aead(raw, release, budget)
    target = root / 'packages/cffi/__init__.py'
    directory_write = change in {'replace', 'extra', 'remove', 'symlink', 'hardlink'}
    if directory_write: target.parent.chmod(0o755)  # Fixture mutation only.
    if change == 'bytes':
        target.chmod(0o644); target.write_bytes(b'tampered'); target.chmod(0o444)
    elif change == 'replace':
        data = target.read_bytes(); target.unlink(); target.write_bytes(data); target.chmod(0o444)
    elif change == 'extra': (target.parent / 'extra.py').write_bytes(b'')
    elif change == 'remove': target.unlink()
    elif change == 'symlink': target.unlink(); target.symlink_to(root / profile.MANIFEST)
    elif change == 'hardlink': os.link(target, target.parent / 'alias.py')
    elif change == 'mode': target.chmod(0o644)
    elif change == 'acl':
        monkeypatch.setattr(peer, 'has_macos_acl', lambda path, **k: str(path) == str(target))
    elif change == 'lock':
        with (Path(release) / profile.LOCK_RELATIVE).open('ab') as stream: stream.write(b'# changed\n')
    elif change == 'manifest':
        manifest = root / profile.MANIFEST
        manifest.chmod(0o644); manifest.write_bytes(b'changed'); manifest.chmod(0o444)
    if directory_write: target.parent.chmod(0o555)
    with pytest.raises((peer.PeerIdentityError, OSError)):
        peer._observe_control_aead(raw, release, budget, first)


def test_mutation_during_full_verification_refuses(installed_profile, monkeypatch):
    raw, release, root = installed_profile
    real = profile.verify_profile
    def racing(*a, **k):
        result = real(*a, **k)
        leaf = root / 'packages/cffi/__init__.py'
        leaf.chmod(0o644); leaf.write_bytes(b'changed'); leaf.chmod(0o444)
        return result
    monkeypatch.setattr(profile, 'verify_profile', racing)
    with pytest.raises(peer.PeerIdentityError, match='CLOSURE_CHANGED'):
        peer._observe_control_aead(raw, release, peer._Budget(25))


@pytest.mark.parametrize('operation', ['read', 'decompress', 'hash'])
def test_deadline_expiry_stops_multichunk_work(tmp_path, monkeypatch, operation):
    now = [0.0]
    monkeypatch.setattr(peer, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    budget = peer._Budget(25)
    checked = []
    def check():
        checked.append(True)
        if len(checked) == 3: now[0] = 26.0
        budget.check()
    data = b'x' * (4 * 1024 * 1024)
    with pytest.raises(peer.PeerIdentityError, match='BUDGET_EXCEEDED'):
        if operation == 'read':
            path = tmp_path / 'public'; path.write_bytes(data); path.chmod(0o444)
            profile.secure_data(path, uid=os.geteuid(), check=check)
        elif operation == 'hash': profile.digest(data, check=check)
        else:
            blob = io.BytesIO()
            with zipfile.ZipFile(blob, 'w', zipfile.ZIP_DEFLATED) as z: z.writestr('data', data)
            with zipfile.ZipFile(blob) as z: profile._archive_data(z, z.infolist()[0], check=check)
    assert len(checked) == 3


def test_expired_profile_budget_is_preserved_by_projection(monkeypatch):
    import json
    raw = {'proof_base_sha': 'a' * 40, 'control_uid': 450,
           'python_runtime_provenance_digest': 'b' * 64, 'reply_events': {'armed': True}}
    monkeypatch.setattr(peer, '_observe_ancestors', lambda *a: ())
    monkeypatch.setattr(peer, '_read_trusted_bytes', lambda *a, **k: (json.dumps(raw).encode(), None))
    def expired(*a): raise peer.PeerIdentityError('SERVICE_QUALIFICATION_BUDGET_EXCEEDED')
    monkeypatch.setattr(peer, '_observe_control_aead', expired)
    with pytest.raises(peer.PeerIdentityError, match='BUDGET_EXCEEDED'):
        peer._verify_control_projection(peer._Budget(25))

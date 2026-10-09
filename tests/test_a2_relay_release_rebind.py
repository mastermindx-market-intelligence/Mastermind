"""A2 existing-enrollment rebind: real files and transaction fault boundaries."""
import asyncio
import json
import os
from pathlib import Path

import pytest

from ops.executive_os import a2_agent_relay_enrollment as a2

BOT = 'U0BT71H4FQE'
OLD = '9' * 40
NEW = '7' * 40


def test_rebind_parser_is_non_enrolling():
    p = a2.build_parser()
    assert p.parse_args(['rebind-release', '--expected-bot-user-id', BOT]).command == 'rebind-release'
    for flag in ['--enable-w3c', '--token', '--config', '--plist']:
        with pytest.raises(a2.A2EnrollmentError):
            p.parse_args(['rebind-release', '--expected-bot-user-id', BOT, flag])


def test_rebind_owner_exists():
    assert callable(getattr(a2, '_rebind', None))


@pytest.fixture
def host(monkeypatch, tmp_path):
    root = tmp_path / 'Library' / 'Application Support' / 'MastermindExecutive'
    config = root / 'config'
    locks = root / 'locks'
    plists = tmp_path / 'Library' / 'LaunchDaemons'
    for directory in (config, locks, plists):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700 if directory == locks else 0o755)
    uid, gid = os.getuid(), os.getgid()
    for key, val in {'SYSTEM_ROOT': root, 'SYSTEM_RELEASE_ROOT': root/'releases',
                     'CONFIG_PATH': config/'agent-relay.json', 'TOKEN_PATH': config/'agent-relay.token',
                     'PLIST_PATH': plists/'com.mastermind.executive.agent-relay.plist',
                     'A2_REBIND_LOCK_DIR': locks, 'A2_REBIND_LOCK_PATH': locks/'a2-agent-relay-rebind.lock',
                     'RELAY_UID': uid, 'RELAY_GID': gid, 'PLIST_UID': uid, 'PLIST_GID': gid,
                     'REBIND_ROOT_UID': uid, 'REBIND_ROOT_GID': gid}.items():
        monkeypatch.setattr(a2, key, val)
    # Only privileged host eligibility and account lookup are mirrored. All
    # real directory, file, flock, CAS, rendering and rollback code is exercised.
    monkeypatch.setattr(a2, '_assert_host_prepared', lambda: NEW)
    monkeypatch.setattr(a2, '_assert_disarmed', lambda: None)
    monkeypatch.setattr(a2.os, 'getgrouplist', lambda *args: [gid])
    async def forbidden(**kwargs):
        raise AssertionError('rebind called provider')
    monkeypatch.setattr(a2, 'qualify_token', forbidden)
    a2.TOKEN_PATH.write_bytes(b'INERT-TEST-ONLY-NOT-A-CREDENTIAL')
    a2.TOKEN_PATH.chmod(0o400)
    def seed(scopes=a2.SHARED_A2_SCOPES, w3c=False, sha=OLD):
        a2.CONFIG_PATH.chmod(0o600) if a2.CONFIG_PATH.exists() else None
        a2.CONFIG_PATH.write_bytes(a2._canonical_json_bytes(a2.build_config_document(
            bot_user_id=BOT, release_sha=sha, scopes=scopes, w3c_enabled=w3c)))
        a2.CONFIG_PATH.chmod(0o400)
        a2.PLIST_PATH.write_bytes(a2.render_plist(bot_user_id=BOT, release_sha=sha, w3c_enabled=w3c))
        a2.PLIST_PATH.chmod(0o644)
    seed()
    return seed


def rebind():
    return asyncio.run(a2._rebind(bot_user_id=BOT))


def pair():
    return (a2.PLIST_PATH.read_bytes(), a2.CONFIG_PATH.read_bytes())


@pytest.mark.parametrize('scopes', [a2.DEDICATED_A2_SCOPES, a2.SHARED_A2_SCOPES])
@pytest.mark.parametrize('w3c', [False, True])
def test_rebind_preserves_policy_and_unread_token(host, monkeypatch, scopes, w3c):
    host(scopes, w3c)
    token_info = a2.TOKEN_PATH.stat()
    before = json.loads(a2.CONFIG_PATH.read_bytes())
    original_read = os.read
    def no_token_read(fd, count):
        assert os.fstat(fd).st_ino != token_info.st_ino
        return original_read(fd, count)
    monkeypatch.setattr(os, 'read', no_token_read)
    result = rebind()
    assert result['action'] == 'rebound'
    after = json.loads(a2.CONFIG_PATH.read_bytes())
    assert after == {**before, 'release_sha': NEW}
    assert a2.PLIST_PATH.read_bytes() == a2.render_plist(bot_user_id=BOT, release_sha=NEW, w3c_enabled=w3c)
    assert a2.TOKEN_PATH.stat() == token_info
    inodes = (a2.CONFIG_PATH.stat().st_ino, a2.PLIST_PATH.stat().st_ino)
    assert rebind()['action'] == 'already-current'
    assert inodes == (a2.CONFIG_PATH.stat().st_ino, a2.PLIST_PATH.stat().st_ino)


@pytest.mark.parametrize('which', ['config', 'plist', 'token'])
@pytest.mark.parametrize('fault', ['missing', 'symlink', 'hardlink', 'mode', 'acl'])
def test_rebind_refuses_unsafe_existing_files(host, monkeypatch, tmp_path, which, fault):
    path = getattr(a2, which.upper()+'_PATH')
    others = {p: p.read_bytes() for p in (a2.CONFIG_PATH, a2.PLIST_PATH) if p != path}
    if fault == 'missing':
        path.unlink()
    elif fault == 'symlink':
        real = tmp_path / 'foreign'
        path.rename(real)
        path.symlink_to(real)
    elif fault == 'hardlink':
        os.link(path, tmp_path/'alias')
    elif fault == 'mode':
        path.chmod(0o666)
    else:
        real = a2.c1_enrollment.c1_runtime._path_has_acl
        monkeypatch.setattr(a2.c1_enrollment.c1_runtime, '_path_has_acl',
                            lambda p, **kw: p == path or real(p, **kw))
    with pytest.raises(a2.A2EnrollmentError):
        rebind()
    for p, raw in others.items():
        assert p.read_bytes() == raw
    if fault == 'missing':
        assert not path.exists()


@pytest.mark.parametrize('key,value', [('slack_bot_user_id', 'U0DIFFERENT'), ('slack_scopes', ['chat:write']),
                                    ('w3c_enabled', 'false'), ('release_sha', 'invalid'),
                                    ('allowed_peer_uids', [0])])
def test_noncanonical_policy_refuses_before_write(host, key, value):
    doc = json.loads(a2.CONFIG_PATH.read_bytes());doc[key] = value
    a2.CONFIG_PATH.chmod(0o600);a2.CONFIG_PATH.write_bytes(a2._canonical_json_bytes(doc));a2.CONFIG_PATH.chmod(0o400)
    before = pair()
    with pytest.raises(a2.A2EnrollmentError, match='STATE_REFUSED'):
        rebind()
    assert pair() == before


def test_mixed_generation_refused_not_automatically_recovered(host):
    a2.PLIST_PATH.write_bytes(a2.render_plist(bot_user_id=BOT, release_sha=NEW))
    before = pair()
    with pytest.raises(a2.A2EnrollmentError, match='STATE_REFUSED'):
        rebind()
    assert pair() == before


def test_busy_lock_excludes_second_transaction(host):
    binding = a2._open_bound_config_directory()
    try:
        with a2._A2Rebind(binding):
            before = pair()
            with pytest.raises(a2.A2EnrollmentError, match='BUSY'):
                rebind()
            assert pair() == before
    finally:
        os.close(binding.descriptor)


@pytest.mark.parametrize('fail_at', [1, 2])
def test_acknowledged_write_failure_restores_owned_pair(host, monkeypatch, fail_at):
    before = pair()
    real = os.replace
    calls = []
    def fail_once(*args, **kwargs):
        calls.append(args)
        if len(calls) == fail_at:
            raise OSError('injected before rename')
        return real(*args, **kwargs)
    monkeypatch.setattr(os, 'replace', fail_once)
    with pytest.raises(a2.A2EnrollmentError, match='WRITE_REFUSED'):
        rebind()
    assert pair() == before
    assert not list(a2.CONFIG_PATH.parent.glob('*.rebind-*'))
    assert not list(a2.PLIST_PATH.parent.glob('*.rebind-*'))


def test_lost_rename_response_is_uncertain_not_overwritten(host, monkeypatch):
    real = os.replace
    calls = []
    def lose(*args, **kwargs):
        calls.append(args)
        real(*args, **kwargs)
        raise OSError('response lost after rename')
    monkeypatch.setattr(os, 'replace', lose)
    with pytest.raises(a2.A2EnrollmentError, match='EFFECT_UNCERTAIN'):
        rebind()
    assert len(calls) == 1
    assert json.loads(a2.CONFIG_PATH.read_bytes())['release_sha'] == OLD
    assert a2.PLIST_PATH.read_bytes() == a2.render_plist(bot_user_id=BOT, release_sha=NEW)


@pytest.mark.parametrize('target', ['token', 'lock', 'config', 'directory'])
def test_concurrent_drift_after_first_write_is_never_overwritten(host, monkeypatch, target):
    real = os.replace
    calls = []
    foreign = b'foreign concurrent writer bytes'
    def drift(*args, **kwargs):
        real(*args, **kwargs);calls.append(args)
        if len(calls) == 1:
            path = {'token': a2.TOKEN_PATH, 'lock': a2.A2_REBIND_LOCK_PATH,
                    'config': a2.CONFIG_PATH, 'directory': a2.CONFIG_PATH.parent}[target]
            if target == 'directory':
                path.rename(path.with_name('old-config'))
                path.mkdir(mode=0o755)
            else:
                path.unlink();path.write_bytes(foreign)
                path.chmod(0o600 if target == 'lock' else 0o400)
    monkeypatch.setattr(os, 'replace', drift)
    with pytest.raises(a2.A2EnrollmentError, match='EFFECT_UNCERTAIN'):
        rebind()
    assert len(calls) == 1
    if target != 'directory':
        path = {'token': a2.TOKEN_PATH, 'lock': a2.A2_REBIND_LOCK_PATH, 'config': a2.CONFIG_PATH}[target]
        assert path.read_bytes() == foreign


def test_service_becomes_loaded_before_publication_refuses(host, monkeypatch):
    before = pair()
    def loaded():
        raise a2.A2EnrollmentError('A2_ENROLLMENT_HOST_REFUSED')
    monkeypatch.setattr(a2, '_assert_disarmed', loaded)
    with pytest.raises(a2.A2EnrollmentError):
        rebind()
    assert pair() == before


def test_second_failure_with_rollback_failure_preserves_mixed_state(host, monkeypatch):
    real = os.replace
    calls = []
    def fail(*args, **kwargs):
        calls.append(args)
        if len(calls) >= 2:
            raise OSError('cannot rename')
        return real(*args, **kwargs)
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(a2.A2EnrollmentError, match='MIXED_GENERATION'):
        rebind()
    assert len(calls) == 3


def test_no_staging_write_to_token_or_c1(host, monkeypatch):
    real = os.open
    def constrained(path, flags, *args, **kwargs):
        if (flags & (os.O_WRONLY | os.O_RDWR) and 'rebind.lock' not in str(path)
                and str(path) != '/dev/null'):
            assert '.rebind-' in str(path)
            assert str(path).startswith(('.agent-relay.json.', '.com.mastermind.executive.agent-relay.plist.'))
        return real(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', constrained)
    assert rebind()['action'] == 'rebound'


def test_sibling_drift_during_staging_refuses_first_rename(host, monkeypatch):
    real_sync = os.fsync
    foreign = b'foreign config during staging'
    changed = []
    original_plist = a2.PLIST_PATH.read_bytes()
    def sync(fd):
        real_sync(fd)
        info = os.fstat(fd)
        # Staged public plist, not lock/directory/token.
        if not changed and info.st_size > 1000 and (info.st_mode & 0o777) == 0o644:
            changed.append(True)
            a2.CONFIG_PATH.unlink();a2.CONFIG_PATH.write_bytes(foreign);a2.CONFIG_PATH.chmod(0o400)
    monkeypatch.setattr(os, 'fsync', sync)
    with pytest.raises(a2.A2EnrollmentError, match='EFFECT_UNCERTAIN'):
        rebind()
    assert changed
    assert a2.PLIST_PATH.read_bytes() == original_plist
    assert a2.CONFIG_PATH.read_bytes() == foreign


def test_sibling_drift_during_rollback_is_never_overwritten(host, monkeypatch):
    real_replace = os.replace
    calls = []
    foreign = b'foreign config while restoring plist'
    def replace(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise OSError('second publication failed')
        real_replace(*args, **kwargs)
        if len(calls) == 3:
            a2.CONFIG_PATH.unlink();a2.CONFIG_PATH.write_bytes(foreign);a2.CONFIG_PATH.chmod(0o400)
    monkeypatch.setattr(os, 'replace', replace)
    with pytest.raises(a2.A2EnrollmentError, match='EFFECT_UNCERTAIN'):
        rebind()
    assert len(calls) == 3
    assert a2.CONFIG_PATH.read_bytes() == foreign


@pytest.mark.parametrize('target', ['lock', 'token'])
def test_unsafe_namespace_before_any_write(host, target):
    if target == 'lock':
        a2.A2_REBIND_LOCK_DIR.chmod(0o755)
    else:
        a2.TOKEN_PATH.unlink();os.mkfifo(a2.TOKEN_PATH, 0o400)
    before = pair()
    with pytest.raises(a2.A2EnrollmentError):
        rebind()
    assert pair() == before


def test_failure_after_acknowledged_second_rename_can_restore_exact_pair(host, monkeypatch):
    before = pair()
    real_sync = os.fsync
    parent_info = a2.CONFIG_PATH.parent.stat()
    failed = []
    def sync(fd):
        info = os.fstat(fd)
        if (not failed and info.st_ino == parent_info.st_ino
                and json.loads(a2.CONFIG_PATH.read_bytes())['release_sha'] == NEW):
            failed.append(True)
            raise OSError('publication directory fsync failed')
        real_sync(fd)
    monkeypatch.setattr(os, 'fsync', sync)
    with pytest.raises(a2.A2EnrollmentError, match='WRITE_REFUSED'):
        rebind()
    assert failed
    assert pair() == before

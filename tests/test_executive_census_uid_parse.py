"""Closed ps identity parsing, in-memory sensor output only.

These tests call the actual incumbent census entrypoint. They never invoke ps,
lsof, a process census, a lock, a migration, SQLite, a provider or a real host
account lookup. Module-local OS/platform stand-ins preserve unrelated tests.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_backup as subject


@pytest.fixture
def census(monkeypatch, tmp_path):
    state = SimpleNamespace(platform='darwin', control_uid=450, pid=123, sensor_pid=124,
                            extra='', ps_status=0, ps_error='', calls=[], lsof='valid',
                            own_uids=None, child_uids=None, omit=None, duplicate=None)
    database, lock, barrier = (tmp_path / name for name in ('db.sqlite3', 'service.lock', 'upgrade.json'))
    descriptor = 9
    # No global os/sys mutation: only the subject's module bindings change.
    monkeypatch.setattr(subject, 'os', SimpleNamespace(
        getresuid=lambda: (state.control_uid,) * 3,
        getuid=lambda: state.control_uid, geteuid=lambda: state.control_uid,
        getpid=lambda: state.pid,
        path=SimpleNamespace(lexists=lambda path: Path(path) in (database, lock, barrier))))
    monkeypatch.setattr(subject, 'sys', state, raising=False)

    def observe(argv):
        state.calls.append(tuple(argv))
        if argv[0] == '/bin/ps':
            assert argv == ['/bin/ps', '-axo', 'pid=,svuid=,ruid=,uid=,comm=']
            own = state.own_uids or (str(state.control_uid),) * 3
            child = state.child_uids or (str(state.control_uid),) * 3
            rows = {'own': f'{state.pid} {" ".join(own)} python-upgrader\n',
                    'child': f'{state.sensor_pid} {" ".join(child)} /bin/ps\n'}
            text = ''.join(row for key, row in rows.items() if key != state.omit)
            if state.duplicate:
                text += rows[state.duplicate]
            return state.ps_status, text + state.extra, state.ps_error, state.sensor_pid
        assert argv == ['/usr/sbin/lsof', '-w', '-nP', '-F', 'pufn', '--',
                        str(database), str(lock), str(barrier)]
        path = database if state.lsof == 'foreign' else lock
        return 1, f'p{state.pid}\nu{state.control_uid}\nf{descriptor}u\nn{path}\n', '', 125

    monkeypatch.setattr(subject, '_run_census_command', observe)
    state.invoke = lambda: subject._default_upgrade_census(database, lock, barrier, descriptor)
    return state


@pytest.mark.parametrize('uid', ['-1', '-2', '-2147483648'])
def test_darwin_signed_foreign_identity_is_parsed_not_ignored(census, uid):
    census.extra = f'771 {uid} {uid} {uid} inert-executable\n'
    result = census.invoke()
    assert result['processes'] == []
    assert result['control_uids'] == [450]
    assert result['process_sensor']['upgrader_observed']
    assert result['process_sensor']['sensor_child_observed']
    assert len(census.calls) == 2


@pytest.mark.parametrize('platform', ['darwin', 'linux'])
@pytest.mark.parametrize('uid', ['0', '451', '2147483647', '2147483648', '4294967294', '4294967295'])
def test_unsigned_full_uint32_identity_remains_supported(census, platform, uid):
    census.platform = platform
    census.extra = f'771 {uid} {uid} {uid} inert-executable\n'
    assert census.invoke()['processes'] == []


@pytest.mark.parametrize('position', [0, 1, 2])
@pytest.mark.parametrize('uid, canonical', [('-1', 4294967295), ('-2', 4294967294),
                                         ('-2147483648', 2147483648)])
def test_signed_control_alias_in_any_uid_column_still_refuses(census, position, uid, canonical):
    census.control_uid = canonical
    fields = ['451', '451', '451']
    fields[position] = uid
    census.extra = f'771 {" ".join(fields)} actual-control-writer\n'
    with pytest.raises(subject.RestoreSafetyError, match='another control-UID'):
        census.invoke()
    assert len(census.calls) == 1


@pytest.mark.parametrize('uid', ['-0', '-01', '+450', '４５０', '²', '0x1c2', '450x',
                                '4294967296', '-2147483649', '-4294966846',
                                '4294967746', '9' * 5000])
def test_malformed_or_out_of_range_uid_never_drops_a_row(census, uid):
    census.extra = f'771 {uid} 451 451 inert-executable\n'
    with pytest.raises(subject.RestoreSafetyError, match='process census is malformed'):
        census.invoke()
    assert len(census.calls) == 1


@pytest.mark.parametrize('uid', ['-1', '-2', '-2147483648'])
def test_non_darwin_signed_uid_is_not_admitted(census, uid):
    census.platform = 'linux'
    census.extra = f'771 {uid} 451 451 inert-executable\n'
    with pytest.raises(subject.RestoreSafetyError, match='process census is malformed'):
        census.invoke()


@pytest.mark.parametrize('pid', ['-1', '+771', '７７１', '²', '0', '2147483648', '9' * 5000])
def test_signed_unicode_or_out_of_range_pid_refuses(census, pid):
    census.extra = f'{pid} 451 451 451 inert-executable\n'
    with pytest.raises(subject.RestoreSafetyError, match='process census is malformed'):
        census.invoke()
    assert len(census.calls) == 1


@pytest.mark.parametrize('which', ['own', 'child'])
def test_required_sentinels_remain_mandatory(census, which):
    census.omit = which
    with pytest.raises(subject.RestoreSafetyError, match='required sentinel'):
        census.invoke()


@pytest.mark.parametrize('which', ['own', 'child'])
def test_duplicate_sentinels_still_refuse(census, which):
    census.duplicate = which
    with pytest.raises(subject.RestoreSafetyError, match='sentinel is malformed'):
        census.invoke()


@pytest.mark.parametrize('which', ['own_uids', 'child_uids'])
def test_sentinel_without_exact_control_membership_refuses(census, which):
    setattr(census, which, ('-2', '-2', '-2'))
    with pytest.raises(subject.RestoreSafetyError, match='sentinel is malformed'):
        census.invoke()


@pytest.mark.parametrize('status, error', [(1, ''), (0, 'sensor uncertainty')])
def test_sensor_failure_remains_closed(census, status, error):
    census.ps_status, census.ps_error = status, error
    with pytest.raises(subject.RestoreSafetyError, match='process census failed closed'):
        census.invoke()
    assert len(census.calls) == 1


def test_foreign_open_runtime_file_still_refuses(census):
    census.lsof = 'foreign'
    with pytest.raises(subject.RestoreSafetyError, match='another open runtime file'):
        census.invoke()


@pytest.mark.parametrize('pid', ['1', '2147483647'])
def test_positive_pid_range_boundaries_remain_supported(census, pid):
    census.extra = f'{pid} 451 451 451 inert-executable\n'
    assert census.invoke()['processes'] == []

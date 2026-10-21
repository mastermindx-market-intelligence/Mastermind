"""Execute the source parser/functions with inert identity and mutation boundaries."""
from pathlib import Path
import os
import shlex
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ops/executive_os/bootstrap-host.sh'


def source():
    return SOURCE.read_text()


def function(name):
    text = source()
    start = text.index(name + '() {\n')
    end = text.index('\n}\n', start) + 3
    return text[start:end]


def run(script, *args):
    return subprocess.run(['/bin/bash', '-c', 'set -euo pipefail\n' + script, 'test', *args],
                          capture_output=True, text=True, timeout=15,
                          env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})


DEFAULTS = '''
CONTROL_USER=_mastermind_exec
CONTROL_GROUP=_mastermind_exec
WORKER_USER=_mastermind_worker
WORKER_GROUP=_mastermind_worker
OPS_GROUP=_mastermind_ops
CONTROL_UID=450 CONTROL_GID=450 WORKER_UID=451 WORKER_GID=451 OPS_GID=453
CONTROL_HOME=/var/db/mastermind-executive/control/home
PERSONAL_PRO_SLOT_IDS=(codex-pro-01 codex-pro-02 codex-pro-03)
SECONDARY_WORKER_ID=paid-test-01
SECONDARY_WORKER_USER=_mastermind_paid_test
SECONDARY_WORKER_GROUP=_mastermind_paid_test
SECONDARY_WORKER_UID=470
SECONDARY_WORKER_GID=471
slot_field() {
  case "$2" in
    worker_user|worker_group) echo "_mastermind_codex_${1##*-}" ;;
    worker_uid|worker_gid) echo "$((453 + 10#${1##*-}))" ;;
    *) return 65 ;;
  esac
}
'''


def test_script_has_valid_bash_syntax():
    result = subprocess.run(['/bin/bash', '-n', str(SOURCE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('args,expected', [
    (['--secondary-worker-id', 'paid-test-01', '--secondary-worker-user', '_mastermind_paid_test',
      '--secondary-worker-group', '_mastermind_paid_test', '--secondary-worker-uid', '470',
      '--secondary-worker-gid', '471'], 0),
    (['--operator-user', 'operator'], 0),
    (['--secondary-worker-id'], 64),
    (['--secondary-worker-id', 'a', '--secondary-worker-id', 'b'], 64),
    (['--secondary-worker-id', 'a', '--operator-user', 'operator'], 64),
    (['--unknown', 'value'], 64),
])
def test_parser_selects_one_mode_and_rejects_ambiguous_input(args, expected, tmp_path):
    prefix = source().split('[ "$(/usr/bin/id -u)" -eq 0 ]', 1)[0]
    parser = tmp_path / 'parser.sh'
    parser.write_text(prefix + '\n[ "$SECONDARY_MODE" != true ] || [ "$ORDINARY_OPTIONS" = false ] || usage\n')
    result = subprocess.run(['/bin/bash', str(parser), *args], capture_output=True, text=True,
                            env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=15)
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize('changes', [
    '',
    'SECONDARY_WORKER_USER=_mastermind_other SECONDARY_WORKER_GID=472',
])
def test_separately_named_identity_is_valid(changes):
    result = run(DEFAULTS + function('secondary_refuse') + function('validate_secondary_worker') +
                 '\n' + changes + '\nvalidate_secondary_worker\n')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('changes', [
    'SECONDARY_WORKER_ID=""', 'SECONDARY_WORKER_USER=""', 'SECONDARY_WORKER_GROUP=""',
    'SECONDARY_WORKER_UID=""', 'SECONDARY_WORKER_GID=""',
    'SECONDARY_WORKER_ID=codex-01', 'SECONDARY_WORKER_ID=codex-pro-02',
    'SECONDARY_WORKER_USER=_mastermind_exec', 'SECONDARY_WORKER_GROUP=_mastermind_ops',
    'SECONDARY_WORKER_USER=_mastermind_codex_01', 'SECONDARY_WORKER_GROUP=_mastermind_codex_03',
    'SECONDARY_WORKER_UID=451', 'SECONDARY_WORKER_GID=450', 'SECONDARY_WORKER_UID=455',
    'SECONDARY_WORKER_GID=453', 'SECONDARY_WORKER_GID=457',
    'SECONDARY_WORKER_USER=_mastermind_agent_relay', 'SECONDARY_WORKER_UID=0470', 'SECONDARY_WORKER_GID=501',
    'SECONDARY_WORKER_ID=../escape', 'SECONDARY_WORKER_ID=UPPER',
    'SECONDARY_WORKER_USER=chriswong', 'SECONDARY_WORKER_GROUP=_mastermind_',
    'SECONDARY_WORKER_ID=' + 'a'*65, 'SECONDARY_WORKER_USER=_mastermind_' + 'a'*25,
])
def test_invalid_or_reserved_identity_refuses(changes):
    result = run(DEFAULTS + function('secondary_refuse') + function('validate_secondary_worker') +
                 '\n' + changes + '\nvalidate_secondary_worker\n')
    assert result.returncode == 65, (changes, result.stdout, result.stderr)


@pytest.mark.parametrize('kind,metadata,acl_rc,allow_missing,expected', [
    ('dir', '470:471:700', 0, 'false', 0),
    ('dir', '0:0:700', 0, 'false', 65),
    ('dir', '470:471:755', 0, 'false', 65),
    ('dir', '470:471:700', 65, 'false', 65),
    ('symlink', '470:471:700', 0, 'false', 65),
    ('file', '470:471:700', 0, 'false', 65),
    ('missing', '470:471:700', 0, 'false', 65),
    ('missing', '470:471:700', 0, 'true', 0),
])
def test_directory_preflight_refuses_unsafe_paths(tmp_path, kind, metadata, acl_rc, allow_missing, expected):
    target = tmp_path / 'node'
    if kind == 'dir':
        target.mkdir()
    elif kind == 'file':
        target.write_text('untouched')
    elif kind == 'symlink':
        target.symlink_to(tmp_path, target_is_directory=True)
    actual = function('require_secondary_directory').replace('/usr/bin/stat', 'fixture_stat')
    script = function('secondary_refuse') + actual + f'''
fixture_stat() {{ printf '%s\\n' {shlex.quote(metadata)}; }}
require_native_no_acl() {{ return {acl_rc}; }}
require_secondary_directory {shlex.quote(str(target))} '470:471:700' {allow_missing}
'''
    result = run(script)
    assert result.returncode == expected, result.stderr
    if kind == 'file':
        assert target.read_text() == 'untouched'


@pytest.mark.parametrize('failure', ['', 'new_identity', 'directory', 'user', 'group', 'membership', 'control_auth', 'orphan_primary_gid'])
def test_secondary_effects_follow_all_preflights_and_touch_only_new_identity(failure):
    # Canonical path resolution is replaced with fixed values. No host paths are inspected.
    actual = function('bootstrap_secondary_worker')
    actual = actual.replace('$(cd -P /var/db/mastermind-executive && /bin/pwd -P)', '/private/var/db/mastermind-executive')
    actual = actual.replace('$(cd -P /var/log/mastermind-executive && /bin/pwd -P)', '/private/var/log/mastermind-executive')
    actual = actual.replace('/usr/bin/dscl', 'fixture_dscl').replace('/usr/sbin/dseditgroup', 'fixture_dseditgroup')
    script = DEFAULTS + function('secondary_refuse') + function('validate_secondary_worker') + function('sorted_words') + actual + f'''
require_secondary_directory() {{ [ {shlex.quote(failure or 'none')} != directory ] || secondary_refuse directory; }}
secondary_record_exists() {{
  if [ "$2" = _mastermind_paid_test ]; then
    case {shlex.quote(failure or 'none')} in orphan_primary_gid|new_identity) return 1 ;; esac
  fi
  return 0
}}
numeric_owners() {{
  case {shlex.quote(failure or 'none')} in
    orphan_primary_gid) echo _unexpected_primary_user ;;
    new_identity) : ;;
    *) echo _mastermind_paid_test ;;
  esac
}}
assert_authentication_disabled() {{ [ {shlex.quote(failure or 'none')} != control_auth ] || secondary_refuse "Control authentication"; }}
fixture_dscl() {{ :; }}
read_attribute() {{ [ "$2" != PrimaryGroupID ] || echo 450; }}
fixture_dseditgroup() {{ printf 'EFFECT member %s %s %s %s %s %s %s\\n' "$@"; }}
assert_exact_members() {{ [ {shlex.quote(failure or 'none')} != membership ] || secondary_refuse membership; printf 'MEMBERS %s %s %s %s\\n' "$@"; }}
ensure_group() {{
  if [ "${{3:-false}}" = true ]; then [ {shlex.quote(failure or 'none')} != group ] || secondary_refuse group;
  else printf 'EFFECT group %s %s\\n' "$@"; fi
}}
ensure_user() {{
  if [ "${{5:-false}}" = true ]; then [ {shlex.quote(failure or 'none')} != user ] || secondary_refuse user;
  else printf 'EFFECT user %s %s %s %s\\n' "$@"; fi
}}
assert_numeric_owner() {{ :; }}
ensure_secondary_directory() {{ printf 'EFFECT dir %s %s %s %s %s\\n' "$@"; }}
bootstrap_secondary_worker
'''
    result = run(script)
    if failure not in ('', 'new_identity'):
        assert result.returncode == 65
        assert 'EFFECT' not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert 'EFFECT user _mastermind_paid_test 470 471 /private/var/db/mastermind-executive/workers/paid-test-01/provider-home' in result.stdout
        assert 'EFFECT group _mastermind_paid_test 471' in result.stdout
        assert 'MEMBERS _mastermind_paid_test 471 _mastermind_paid_test ' in result.stdout
        assert result.stdout.count('EFFECT dir ') == 7
        assert '/var/log/' not in result.stdout
        assert 'EFFECT member -o edit -a _mastermind_exec -t user _mastermind_paid_test' in result.stdout
        assert 'MEMBERS _mastermind_paid_test 471 _mastermind_paid_test _mastermind_exec' in result.stdout
        assert 'EFFECT user _mastermind_exec ' not in result.stdout
        assert '/jobs/workspaces 450 471 0710 450:471:710' in result.stdout
        assert '_mastermind_worker' not in result.stdout
        assert '/workers/codex-01' not in result.stdout


def test_existing_identity_preflight_cannot_create_records():
    for name, params in [('ensure_group', '_mastermind_paid_test 471 true'),
                         ('ensure_user', '_mastermind_paid_test 470 471 /synthetic/home true')]:
        actual = function(name).replace('/usr/bin/dscl', 'fixture_dscl')
        result = run(actual + '''
ensure_numeric_unused() { :; }
fixture_dscl() {
  if [ "$2" = -read ]; then return 1; fi
  printf 'MUTATION\\n'; return 1
}
''' + name + ' ' + params + '\n')
        assert result.returncode == 0, result.stderr
        assert 'MUTATION' not in result.stdout


def test_bootstrap_and_installer_use_identical_native_reader():
    installer = ROOT / 'ops/executive_os/install.sh'
    if not installer.exists():
        pytest.skip('whole source integrator supplies installer alongside bootstrap')
    def reader(text):
        return text.split("<<'MASTERMIND_NATIVE_ACL_RUBY'\n", 1)[1].split('\nMASTERMIND_NATIVE_ACL_RUBY\n', 1)[0]
    assert reader(source()) == reader(installer.read_text())

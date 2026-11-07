"""Process-local fail-closed boundary for these inert broker fixtures only."""
from contextlib import contextmanager
import hashlib
import os
import pwd
from pathlib import Path
import sys
from unittest import mock

_active = 0
_unexpected = []
_expected = None
_patches = []
_child_scripts = set()
_syntax_commands = set()
_prelaunch_shell_commands = set()
_protected = set()
_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
_CREDENTIAL_ROOTS = tuple(str(_HOME / name) + os.sep for name in
    ('.glm', '.minimax', '.bailian', '.qwen', '.anthropic'))
_CREDENTIAL_FILES = {str(_HOME / '.codex/auth.json'),
                     str(_HOME / '.claude/.credentials.json')}
_ADVERSE_CACHE = str(Path(__file__).resolve().parents[1] / 'source/quota_cache.json')


class OfflineAccessError(RuntimeError):
    pass


def _deny(kind):
    target = _expected if _expected is not None else _unexpected
    target.append(kind)  # never retain URLs, headers, credential values or argv
    raise OfflineAccessError('offline fixture blocked ' + kind)


def _audit(event, args):
    if not _active:
        return
    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo',
                 'socket.bind', 'urllib.Request'}:
        _deny('network')
    if event == 'subprocess.Popen':
        executable, argv = args[:2]
        if tuple(argv) in _syntax_commands or tuple(argv) in _prelaunch_shell_commands:
            return
        if not (isinstance(argv, (list, tuple)) and len(argv) >= 3
                and argv[0] == sys.executable and argv[1] == '-c'
                and hashlib.sha256(argv[2].encode()).hexdigest() in _child_scripts):
            _deny('unguarded_subprocess')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.abspath(os.fsdecode(args[0]))
        if path == _ADVERSE_CACHE:
            _deny('adverse_cache')
        if path in _protected or path in _CREDENTIAL_FILES or path.startswith(_CREDENTIAL_ROOTS):
            _deny('credential_open')


sys.addaudithook(_audit)


def acquire():
    global _active
    _active += 1  # guard is active before importing any incumbent status owner
    if _active == 1:
        try:
            for name in ('GLM_CONFIG', 'MINIMAX_CONFIG', 'BAILIAN_CONFIG'):
                value = os.environ.get(name)
                if value:
                    _protected.add(os.path.abspath(value))
            # Snapshot enrichment is not the subject of quota-row tests. Keep
            # all actual broker, process-receipt and SQLite behavior real.
            before = list(sys.path)
            try:
                import pool_status
            finally:
                sys.path[:] = before
            patch = mock.patch.object(pool_status, 'build_status', return_value={'pools': {}})
            patch.start()
            _patches.append(patch)
        except BaseException:
            _active -= 1
            raise


def release():
    global _active
    assert _active > 0
    _active -= 1
    if not _active:
        while _patches:
            _patches.pop().stop()
        if _unexpected:
            raise AssertionError('offline fixture attempted forbidden effects: ' + repr(_unexpected))


@contextmanager
def expect_blocked(kind, count=1):
    """Only synthetic negative cases may acknowledge pre-effect guard denials."""
    global _expected
    assert _active and _expected is None
    seen = []
    _expected = seen
    try:
        yield
    finally:
        _expected = None
        assert seen == [kind] * count, (kind, seen)


@contextmanager
def protect_fixture_credential(path):
    key = os.path.abspath(path)
    _protected.add(key)
    try:
        yield
    finally:
        _protected.remove(key)


def guarded_python_child(code):
    """Keep the existing real restart test, with the same boundary in its child."""
    helper = str(Path(__file__).resolve().parent)
    wrapped = ('import sys\nsys.path.insert(0, ' + repr(helper) + ')\n'
               'sys.path[:0] = ' + repr([str(Path(helper).parent / 'candidate'), str(Path(helper).parent / 'source')]) + '\n'
               'from _offline_boundary import acquire, release\nacquire()\n'
               'try:\n    exec(compile(' + repr(code) + ', "<broker-fixture>", "exec"))\n'
               'finally:\n    release()\n')
    _child_scripts.add(hashlib.sha256(wrapped.encode()).hexdigest())
    return wrapped


def guarded_python_file(path, args):
    """Execute one exact local fixture CLI with the child boundary installed."""
    code = ('import runpy, sys\nsys.argv = ' + repr([str(path), *map(str, args)])
            + '\nrunpy.run_path(' + repr(str(path)) + ', run_name="__main__")\n')
    return [sys.executable, '-c', guarded_python_child(code)]


def guarded_bash_syntax(path):
    """Allow syntax parsing only; this command cannot execute shell statements."""
    argv = ('/bin/bash', '-n', str(path))
    _syntax_commands.add(argv)
    return list(argv)


def guarded_prelaunch_shell(path, args):
    """Exact copied source, future-bound fixture, isolated PATH with no transport.

    This only admits the two owned prelaunch fixtures. Their Python shim enters
    this boundary before running any helper, and no network CLI is on PATH.
    """
    path = Path(path)
    assert path.name in {'remote_sub.sh', 'qwen_exec.sh'} and not path.is_symlink()
    original = Path(__file__).resolve().parents[1] / 'candidate' / path.name
    assert path.read_bytes() == original.read_bytes()
    argv = ('/bin/bash', str(path), *map(str, args))
    _prelaunch_shell_commands.add(argv)
    return list(argv)


def guarded_qwen_key_reentry(mode):
    """Real source functions with builtin-only stand-ins and no command PATH.

    The selected credential and time-helper entries are counters, not Python
    invocations. Actual UTC parsing/clock behavior is qualified separately.
    Only these closed rollback/absence scenarios can register this command.
    """
    assert mode in {'wait_rollback', 'pick_rollback', 'wait_invalid', 'absent'}
    source = (Path(__file__).resolve().parents[1] / 'candidate/qwen_exec.sh').read_text()
    functions = []
    for name in ('qwen_not_before_check', 'pick_and_check', 'acquire_key'):
        start = source.index(name + '() {\n')
        end = source.index('\n}\n', start) + 3
        functions.append(source[start:end])
    # No external command is available: all commands in the extracted path
    # are Bash builtins or these explicit stand-ins. Unexpected helper entry
    # terminates with97, and no full wrapper/provider entry is sourced.
    fixture = r'''
set -eu
MODE="$1"
WORKDIR="$PWD"
KEYS=fixture-keys
POOL_ACCOUNT=fixture-account
LANE_LEASED=0
KEY_WAIT=2 KEY_WAITED=0 KEY_POLL=1 KEY_SLEEP_MAX=1
NAME='' PICK_ERR='' ROLLED=0 PICKS=0 CREDENTIALS=0 CLOCKS=0
export POOL_CALLER_NOT_BEFORE=2026-10-23T00:47:19.721Z
if [ "$MODE" = absent ]; then unset POOL_CALLER_NOT_BEFORE; fi
dirname() { printf '%s\n' "${1%/*}"; }
head() { local line=''; IFS= read -r line < "$3" || :; printf '%s\n' "$line"; }
tr() { local line=''; IFS= read -r line || :; printf '%s' "$line"; }
log() { :; }
sleep() { ROLLED=1; }
python3() {
  case "${1##*/}:$2" in
    commission_deadline.py:not-before)
      CLOCKS=$((CLOCKS + 1))
      [ "$POOL_CALLER_NOT_BEFORE" = 2026-10-23T00:47:19.721Z ] || exit 97
      if [ "$ROLLED" = 1 ]; then
        if [ "$MODE" = wait_invalid ]; then return 2; fi
        return 75
      fi
      return 0 ;;
    fixture-keys:pick)
      PICKS=$((PICKS + 1))
      if [ "$MODE" = pick_rollback ]; then
        ROLLED=1
      elif [ "$PICKS" = 1 ]; then
        return 1
      fi
      printf '%s\n' fixture-account; return 0 ;;
    fixture-keys:check-key) CREDENTIALS=$((CREDENTIALS + 1)); return 0 ;;
    fixture-keys:next_usable_in) printf '%s\n' 1; return 0 ;;
    fixture-keys:release) return 0 ;;
    *) exit 97 ;;
  esac
}
trap 'printf "PICKS=%s CREDENTIALS=%s CLOCKS=%s WAITED=%s\n" "$PICKS" "$CREDENTIALS" "$CLOCKS" "$KEY_WAITED"' EXIT
'''
    program = fixture + '\n'.join(functions) + '\nacquire_key\n'
    argv = ('/bin/bash', '-c', program,
            str(Path(__file__).resolve().parents[1] / 'candidate/qwen_exec.sh'), mode)
    _prelaunch_shell_commands.add(argv)
    return list(argv)

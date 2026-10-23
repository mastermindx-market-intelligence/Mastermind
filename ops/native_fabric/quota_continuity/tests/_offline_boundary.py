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

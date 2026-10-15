"""Real-process falsifiers and staged-only proof for the #1272 reader repair."""
import functools
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest

from control_plane.ceo_boot_packet import bounded_subprocess_runner
from ops.fabric_launch import agentos as a
from ops.fabric_launch import install
from ops.fabric_launch.context import LaunchInputError

ROOT = Path(__file__).resolve().parents[1]


def raw_bundle():
    return (json.dumps({
        'schema': 'context_bundle.v1', 'target': {'workstream': 'WS:FIXTURE'},
        'no_answer_reason': None, 'sections': [], 'degraded': ['keep me'],
        'excluded': [], 'omitted_due_to_budget': ['keep this too'],
        'repo_sha': 'fixture-source', 'generated_at': '2026-10-09T00:00:00Z',
    }, ensure_ascii=False, indent=2) + '\n').encode()


def owner(tmp_path, text):
    root = tmp_path / 'owner'
    (root / 'scripts').mkdir(parents=True)
    (root / 'scripts' / 'agentos.py').write_text(text)
    return root


def fast_real_run(argv, **kwargs):
    """Shorten only the deadline; execute the real old or new process interface."""
    kwargs['timeout'] = 0.25
    if 'stdout' in kwargs:
        return subprocess.run(argv, **kwargs)
    return bounded_subprocess_runner(argv, **kwargs)


def test_actual_helper_import_never_writes_bytecode(tmp_path, monkeypatch):
    monkeypatch.delenv('PYTHONDONTWRITEBYTECODE', raising=False)
    root = owner(tmp_path, 'import helper\nimport sys\nsys.stdout.buffer.write(' + repr(raw_bundle()) + ')\n')
    (root / 'scripts' / 'helper.py').write_text('VALUE=1\n')
    before = set(root.rglob('*'))
    result, _ = a.read_context('FIXTURE', 800, owner_root=root)
    assert result == raw_bundle()
    assert set(root.rglob('*')) == before, 'read helper wrote import bytecode'


@pytest.mark.parametrize('leader_waits', [False, True], ids=['leader-exits', 'reader-times-out'])
def test_descendant_does_not_survive_read(tmp_path, leader_waits):
    marker = tmp_path / 'descendant-survived'
    child = 'import time,pathlib;time.sleep(0.7);pathlib.Path(' + repr(str(marker)) + ').write_text("bad")'
    text = ('import subprocess,sys,time\n'
            'subprocess.Popen([sys.executable,"-c",' + repr(child) + '],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n'
            'sys.stdout.buffer.write(' + repr(raw_bundle()) + ');sys.stdout.flush()\n')
    text += 'time.sleep(1.4)\n' if leader_waits else ''
    root = owner(tmp_path, text)
    if leader_waits:
        with pytest.raises(LaunchInputError, match='READ_TIMEOUT'):
            a.read_context('FIXTURE', 800, owner_root=root, run=fast_real_run)
    else:
        result, _ = a.read_context('FIXTURE', 800, owner_root=root, run=fast_real_run)
        assert result == raw_bundle()
    time.sleep(0.9)
    assert not marker.exists(), 'descendant continued after reader returned'


@pytest.mark.parametrize('fd', [1, 2], ids=['stdout', 'stderr'])
def test_streaming_output_is_capped_before_deadline(tmp_path, fd):
    text = ('import os,time\n'
            'os.write(' + str(fd) + ',b"x"*(' + str(a.MAX_BUNDLE_BYTES) + '+4096))\n'
            'time.sleep(1.2)\n')
    root = owner(tmp_path, text)
    with pytest.raises(LaunchInputError, match='OUTPUT_LIMIT'):
        a.read_context('FIXTURE', 800, owner_root=root, run=fast_real_run)


def test_invalid_utf8_on_stderr_cannot_be_ignored(tmp_path):
    root = owner(tmp_path, 'import sys\nsys.stdout.buffer.write(' + repr(raw_bundle()) + ')\nsys.stderr.buffer.write(b"\\xff")\n')
    with pytest.raises(LaunchInputError, match='INVALID_UTF8'):
        a.read_context('FIXTURE', 800, owner_root=root)


def test_cleanup_uncertainty_is_opaque_and_never_retried(tmp_path):
    root = owner(tmp_path, '# fixture\n')
    calls = []
    def uncertain(*args, **kwargs):
        calls.append(args)
        raise RuntimeError('private-diagnostic-must-not-escape')
    with pytest.raises(LaunchInputError, match='READ_UNCERTAIN') as caught:
        a.read_context('FIXTURE', owner_root=root, run=uncertain)
    assert len(calls) == 1
    assert 'private-diagnostic' not in str(caught.value)


def test_injected_timeout_is_not_proof_of_settled_processes(tmp_path):
    root = owner(tmp_path, '# fixture\n')
    def unowned_timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 0.1)
    with pytest.raises(LaunchInputError, match='READ_UNCERTAIN'):
        a.read_context('FIXTURE', owner_root=root, run=unowned_timeout)


@pytest.mark.parametrize('raw', [b'{', b'{"schema":"wrong"}', b''])
def test_real_partial_or_malformed_output_is_never_returned(tmp_path, raw):
    root = owner(tmp_path, 'import sys\nsys.stdout.buffer.write(' + repr(raw) + ')\n')
    with pytest.raises(LaunchInputError):
        a.read_context('FIXTURE', 800, owner_root=root)


def test_complete_runner_import_closure_is_in_staged_content(tmp_path):
    needed = {'control_plane/ceo_boot_packet.py', 'control_plane/strategic_state.py'}
    assert needed <= install.EXACT_FILES, 'installer omits bounded-runner import closure'
    repo = tmp_path / 'fixture-repo'
    repo.mkdir()
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        name = path.relative_to(ROOT).as_posix()
        if name not in install.EXACT_FILES and not name.startswith(install.PREFIXES):
            continue
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE, timeout=10)
    git('init', '-q')
    git('add', '.')
    git('-c', 'user.name=Hermetic Fixture', '-c', 'user.email=fixture@invalid', 'commit', '-qm', 'fixture only')
    commit = git('rev-parse', 'HEAD').decode().strip()
    release = tmp_path / 'staged'
    manifest = install.stage(repo, commit, release)
    assert needed <= set(manifest['files'])
    before = {str(p.relative_to(release)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in release.rglob('*') if p.is_file()}
    root = owner(tmp_path, 'import sys\nsys.stdout.buffer.write(' + repr(raw_bundle()) + ')\n')
    output = tmp_path / 'context.json'
    code = ('import sys,functools;sys.path.insert(0,' + repr(str(release)) + ');'
            'from ops.fabric_launch import cli,agentos;'
            'cli.read_context=functools.partial(agentos.read_context,owner_root=' + repr(str(root)) + ');'
            'raise SystemExit(cli.main(["context","--workstream","FIXTURE","--budget","800","--output",' + repr(str(output)) + ']))')
    result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code],
                            cwd=tmp_path, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    assert output.read_bytes() == raw_bundle()
    receipt = json.loads(result.stdout)
    assert receipt['execution_authority'] is False
    assert receipt['degraded_count'] == receipt['omitted_count'] == 1
    after = {str(p.relative_to(release)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in release.rglob('*') if p.is_file()}
    assert after == before, 'staged-only read mutated its immutable release'


def test_unexpected_read_error_must_settle_owned_process_group(tmp_path, monkeypatch):
    """A failed read must not skip group teardown of a real live descendant.

    RED-first against the incumbent runner. The test owns and forcibly cleans
    its synthetic private process group even if the regression assertion fails.
    """
    from control_plane import ceo_boot_packet as boot

    marker = tmp_path / "descendant-survived-read-failure"
    quiet_child = (
        "import time,pathlib;time.sleep(0.65);"
        f"pathlib.Path({str(marker)!r}).write_text('escaped')"
    )
    code = (
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'-c'," + repr(quiet_child)
        + "],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "sys.stdout.write('ready\\n');sys.stdout.flush()\n"
        "time.sleep(2)\n"
    )
    real_popen = boot.subprocess.Popen
    real_read = boot.os.read
    owned = []

    def traced_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        owned.append(process)
        return process

    def injected_read(fd, size):
        if owned and fd in {owned[0].stdout.fileno(), owned[0].stderr.fileno()}:
            raise OSError("synthetic after-start read failure")
        return real_read(fd, size)

    monkeypatch.setattr(boot.subprocess, "Popen", traced_popen)
    monkeypatch.setattr(boot.os, "read", injected_read)
    try:
        with pytest.raises(OSError, match="after-start read failure"):
            boot.bounded_subprocess_runner(
                [sys.executable, "-B", "-c", code],
                cwd=tmp_path, timeout=1.5, max_bytes=4096,
            )
        assert len(owned) == 1
        assert owned[0].poll() is not None, "unexpected read error left process leader alive"
        assert boot._process_group_presence(owned[0].pid) is False, (
            "unexpected read error skipped descendant group teardown"
        )
    finally:
        if owned:
            # Defensive test cleanup even on the intended red pre-fix failure.
            try:
                os.killpg(owned[0].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            owned[0].wait(timeout=4)
    time.sleep(0.8)
    assert not marker.exists(), "a synthetic quiet descendant survived read failure"

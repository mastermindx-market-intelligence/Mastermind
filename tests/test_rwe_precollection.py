"""The RWE adapter composes existing child custody without inventing a runner."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

import pytest

from scripts import ci_parallel_shard as fan, ci_pytest as ci, rwe_env as rwe
from tests.test_ci_prepartition import _fixture, _running
from tests.test_rwe_shadow_shards import _arguments


ROOT = Path(__file__).resolve().parents[1]
PARALLEL_RECORD = "parallel_shard=3/6 modules=4 included_sha256=" + "a" * 64 + " workers=0 processes=4"


@pytest.mark.parametrize("exit_code", [0, 7])
def test_parallel_request_binds_exact_interpreter_mode_and_shard_receipt(tmp_path, monkeypatch, exit_code):
    args, env_dir = _arguments(tmp_path, monkeypatch)
    args.processes = 4
    calls = []
    def completed(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, exit_code,
            "discovered=9 excluded=0 running=9\n" + PARALLEL_RECORD + "\n", "")
    monkeypatch.setattr(rwe, "_stream_gate", completed)
    assert rwe.cmd_gate(args) == exit_code
    assert calls == [([sys.executable, "-u", "-m", "scripts.ci_parallel_shard",
                      "--jobs", "6", "--index", "2", "--processes", "4"],
                     {"cwd": ROOT.resolve(), "supervised_controller": True})]
    proof = json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text())["proof"]
    assert "gate" not in proof
    shard = proof["shard"]
    assert shard["exit"] == exit_code and shard["plan_observation"] == "matched"
    assert (shard["workers"], shard["processes"], shard["selected_modules"]) == (0, 4, 4)
    assert shard["requested_processes"] == 4
    assert shard["command"].endswith("--index 2 --processes 4")


@pytest.mark.parametrize("record", [
    "", PARALLEL_RECORD.replace(" processes=4", ""),
    PARALLEL_RECORD.replace(" processes=4", " processes=0"),
    PARALLEL_RECORD.replace(" processes=4", " processes=3"),
    PARALLEL_RECORD.replace("workers=0", "workers=4"),
    PARALLEL_RECORD + "\n" + PARALLEL_RECORD,
    PARALLEL_RECORD.replace("3/6", "2/6"),
    PARALLEL_RECORD.replace("modules=4", "modules=0"),
    PARALLEL_RECORD.replace("modules=4", "modules=1"),
    PARALLEL_RECORD.replace("modules=4", "modules=2"),
    PARALLEL_RECORD.replace("modules=4", "modules=3"),
    PARALLEL_RECORD.replace("modules=4", "modules=10"),
])
def test_parallel_zero_exit_cannot_adopt_missing_or_foreign_plan(tmp_path, monkeypatch, record):
    args, env_dir = _arguments(tmp_path, monkeypatch)
    args.processes = 4
    monkeypatch.setattr(rwe, "_stream_gate", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, "discovered=9 excluded=0 running=9\n" + record + "\n", ""))
    assert rwe.cmd_gate(args) == 2
    proof = json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text())["proof"]
    assert "gate" not in proof
    assert proof["shard"]["plan_observation"] == "invalid"
    assert proof["shard"]["requested_processes"] == 4
    assert "workers" not in proof["shard"] and "processes" not in proof["shard"]


def test_serial_request_cannot_adopt_parallel_declaration(tmp_path, monkeypatch):
    args, env_dir = _arguments(tmp_path, monkeypatch)
    monkeypatch.setattr(rwe, "_stream_gate", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, "discovered=9 excluded=0 running=9\n" + PARALLEL_RECORD + "\n", ""))
    assert rwe.cmd_gate(args) == 2
    assert json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text())["proof"]["shard"]["plan_observation"] == "invalid"


@pytest.mark.parametrize("processes,index,subset", [
    (True, 2, None), (1, 2, None), (3, 2, None), (5, 2, None),
    ("4", 2, None), (4, None, None), (4, 2, "tests/test_a.py"),
])
def test_parallel_scope_refuses_before_any_interpreter_or_process(tmp_path, monkeypatch, processes, index, subset):
    import argparse
    args = argparse.Namespace(root=str(ROOT), env=str(tmp_path), subset=subset,
                              shard_index=index, processes=processes)
    monkeypatch.setattr(rwe, "_venv_python", lambda env: pytest.fail("interpreter was probed"))
    monkeypatch.setattr(rwe, "_stream_gate", lambda *a, **k: pytest.fail("child was launched"))
    assert rwe.cmd_gate(args) == 2


def test_supervised_mode_refuses_thread_before_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(rwe.subprocess, "Popen", lambda *a, **k: pytest.fail("child was launched"))
    errors = []
    def invoke():
        try:
            rwe._stream_gate([sys.executable], cwd=tmp_path, supervised_controller=True)
        except BaseException as error:
            errors.append(error)
    worker = threading.Thread(target=invoke)
    worker.start()
    worker.join(2)
    assert not worker.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], rwe.EnvError)


def _project(tmp_path, selected_source):
    candidates = tuple(f"tests/test_rwe_nested_{i}.py" for i in range(600))
    outer = ci.partition_modules(candidates, jobs=6)
    selected = tuple(group[0] for group in ci.partition_modules(outer[2], jobs=4, inner=True))
    other = tuple(group[0] for index, group in enumerate(outer) if index != 2)
    files = {path: "def test_ok(): assert True\n" for path in (*selected, *other)}
    files[selected[0]] = selected_source
    root, output, env = _fixture(tmp_path, files)
    for name in ("ci_parallel_shard.py", "rwe_env.py"):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    (root / ".github/workflows").mkdir(parents=True)
    shutil.copyfile(ROOT / ".github/workflows/ci.yml", root / ".github/workflows/ci.yml")
    (root / "ci").mkdir()
    (root / "ci/pytest_exclusions.toml").write_text("version = 1\nexclude = []\n")
    subprocess.run(["git", "add", "scripts", ".github", "ci"], cwd=root,
                   capture_output=True, check=True)
    subprocess.run(["git", "-c", "user.name=CI fixture", "-c", "user.email=ci@example.invalid",
                    "commit", "-qm", "existing RWE adapter"], cwd=root,
                   capture_output=True, check=True)
    assert set(fan.shard_plan(root, jobs=6, index=2)[1]) == set(selected)
    environment = root / "environment"
    environment.mkdir()
    # Realization may already have a receipt. Cancellation must leave it intact.
    prior = {"schema": rwe.SCHEMA, "definition": {"lock_path": None},
             "proof": {"realized": True}, "degraded": []}
    original = json.dumps(prior, sort_keys=True).encode()
    (environment / rwe.RECEIPT_FILENAME).write_bytes(original)
    env["PYTEST_ADDOPTS"] = "-s"
    return root, environment, env, original


def _launcher(root, mode):
    source = r'''
import io, os, signal, sys, time
from pathlib import Path
from scripts import rwe_env as rwe
root = Path.cwd()
mode = sys.argv[1]
rwe._venv_python = lambda _: Path(sys.executable)
rwe.require_supported_interpreter = lambda _: None
rwe.vendor_present = lambda _: True
# These tests exercise the actual scheduler and receipt boundary; environment
# realization provenance is a separate existing RWE qualification.
rwe.cmd_receipt = lambda _: 0
def ready():
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if list((root / "seen").glob("child-*")) and list((root / "seen").glob("grandchild-*")):
            return
        time.sleep(0.02)
    raise AssertionError("real nested child and descendant did not become ready")
original_popen = rwe.subprocess.Popen
def owned_popen(*args, **kwargs):
    process = original_popen(*args, **kwargs)
    (root / "seen/controller").write_text(str(process.pid))
    if mode == "launch":
        os.kill(os.getpid(), signal.SIGTERM)
    return process
rwe.subprocess.Popen = owned_popen
if mode == "blocked-output":
    original_write = rwe.os.write
    def observed_write(descriptor, data):
        try:
            return original_write(descriptor, data)
        except BlockingIOError:
            (root / "seen/output-full").write_text("yes")
            raise
    rwe.os.write = observed_write
if mode in ("observer", "cleanup-read"):
    class Refused(io.StringIO):
        def write(self, text):
            ready()
            raise OSError("owned RWE observer failed")
    rwe.sys.stdout = Refused()
    if mode == "cleanup-read":
        def refused_drain(*args, **kwargs):
            raise OSError("owned cleanup reader failed")
        rwe.select.select = refused_drain
elif mode == "caught-signal":
    class SignalWhileCaught(io.StringIO):
        def write(self, text):
            ready()
            try:
                raise ValueError("observer internal control flow")
            except ValueError:
                os.kill(os.getpid(), signal.SIGTERM)
            return super().write(text)
    rwe.sys.stdout = SignalWhileCaught()
elif mode == "selector":
    def refused_selector():
        ready()
        raise OSError("owned RWE selector setup failed")
    rwe.selectors.DefaultSelector = refused_selector
handlers = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
try:
    code = rwe.main(["gate", "--env", str(root / "environment"),
        "--root", str(root), "--shard-index", "2", "--processes", "4"])
finally:
    assert all(signal.getsignal(number) == handler for number, handler in handlers.items())
    (root / "seen/handlers-restored").write_text("yes")
raise SystemExit(code)
'''
    path = root / "wrapper.py"
    path.write_text(source)
    return [sys.executable, "-u", str(path), mode]


@pytest.mark.parametrize("fault", ["success", "import-exit", "killed-case"])
def test_real_parallel_gate_preserves_completion_and_original_failure(tmp_path, fault):
    source = {
        "success": "def test_ok(): assert True\n",
        "import-exit": "import os\nos._exit(0)\n",
        "killed-case": "import os,signal\ndef test_killed(): os.kill(os.getpid(), signal.SIGKILL)\n",
    }[fault]
    root, environment, env, original = _project(tmp_path, source)
    completed = subprocess.run(_launcher(root, "normal"), cwd=root, env=env,
                               capture_output=True, text=True, timeout=30)
    proof = json.loads((environment / rwe.RECEIPT_FILENAME).read_text())["proof"]
    assert "gate" not in proof
    shard = proof["shard"]
    assert shard["plan_observation"] == "matched"
    assert shard["processes"] == 4 and shard["selected_modules"] == 4
    assert completed.stdout.count("CI_CHILD_RESULT ") == 4, completed.stdout + completed.stderr
    assert (completed.returncode == 0) == (fault == "success")
    assert shard["exit"] == completed.returncode


@pytest.mark.parametrize("mode", ["observer", "selector", "interrupt", "terminate",
                                  "caught-signal", "cleanup-read"])
@pytest.mark.parametrize("parent_exits", [False, True], ids=["held-pipe", "parent-exits"])
def test_nested_cancellation_preserves_original_failure_and_drains_owned_children(tmp_path, mode, parent_exits):
    source = (
        "from pathlib import Path\nimport os,signal,subprocess,sys,time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "child = subprocess.Popen([sys.executable, '-c', \"import os,signal,time;from pathlib import Path;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "Path('seen/grandchild-'+str(os.getpid())).write_text(str(os.getpid()));time.sleep(60)\"])\n"
        "Path('seen/child-'+str(os.getpid())).write_text(str(os.getpid()))\n"
        "def test_wait_for_controller(): time.sleep(60)\n"
    )
    if parent_exits:
        source = source.replace("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n", "")
        source = source.replace('time.sleep(60)"])',
            'time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)')
    root, environment, env, original = _project(tmp_path, source)
    process = subprocess.Popen(_launcher(root, mode), cwd=root, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    owned = []
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            children = list((root / "seen").glob("child-*"))
            grandchildren = list((root / "seen").glob("grandchild-*"))
            if children and grandchildren:
                break
            assert process.poll() is None
            time.sleep(0.02)
        assert len(children) == len(grandchildren) == 1
        owned = [int(path.read_text()) for path in (*children, *grandchildren)]
        controller = int((root / "seen/controller").read_text())
        if mode in ("interrupt", "terminate"):
            first = signal.SIGINT if mode == "interrupt" else signal.SIGTERM
            process.send_signal(first)
            time.sleep(0.1)
            process.send_signal(signal.SIGTERM if first == signal.SIGINT else signal.SIGINT)
        text, _ = process.communicate(timeout=15)
        if mode in ("interrupt", "terminate"):
            assert process.returncode == 128 + first, text
        elif mode == "caught-signal":
            assert process.returncode == 128 + signal.SIGTERM, text
        else:
            assert process.returncode != 0, text
            assert ("owned RWE observer failed" if mode in ("observer", "cleanup-read")
                    else "owned RWE selector setup failed") in text
        if mode == "cleanup-read":
            assert "controller cleanup unconfirmed" in text
        assert (root / "seen/handlers-restored").read_text() == "yes"
        assert (environment / rwe.RECEIPT_FILENAME).read_bytes() == original
        assert not _running(controller)
        deadline = time.monotonic() + 2
        while any(_running(pid) for pid in owned) and time.monotonic() < deadline:
            time.sleep(0.02)
        live = [pid for pid in owned if _running(pid)]
        states = subprocess.run(["ps", "-p", ",".join(map(str, owned)), "-o", "pid,ppid,pgid,stat,args"],
                                capture_output=True, text=True).stdout
        stacks = root / "seen/controller-stacks"
        assert not live, text + "\n" + states + (stacks.read_text() if stacks.exists() else "")
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                for path in (root / "seen").glob("child-*"):
                    try:
                        os.killpg(int(path.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.kill()
                process.communicate(timeout=5)
        # A failing assertion must not leave this disposable fixture's known
        # process groups alive after its wrapper has already exited.
        for path in (root / "seen").glob("child-*"):
            try:
                os.killpg(int(path.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        controller_file = root / "seen/controller"
        if controller_file.exists():
            controller = int(controller_file.read_text())
            if _running(controller):
                try:
                    os.kill(controller, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_signal_after_spawn_before_handle_registration_still_reaps_controller(tmp_path):
    root, environment, env, original = _project(tmp_path, "def test_ok(): assert True\n")
    completed = subprocess.run(_launcher(root, "launch"), cwd=root, env=env,
                               capture_output=True, text=True, timeout=15)
    assert completed.returncode == 128 + signal.SIGTERM, completed.stdout + completed.stderr
    assert (environment / rwe.RECEIPT_FILENAME).read_bytes() == original
    controller = int((root / "seen/controller").read_text())
    assert not _running(controller)


@pytest.mark.parametrize("close_pipes", [False, True])
def test_controller_reap_waits_beyond_pipe_eof_but_has_one_cleanup_deadline(tmp_path, monkeypatch, close_pipes):
    ready = tmp_path / "ready"
    source = (
        "import os,signal,time\nfrom pathlib import Path\n"
        + ("def stop(*_): time.sleep(0.3); raise SystemExit(0)\n"
           "signal.signal(signal.SIGTERM, stop)\n" if close_pipes
           else "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n")
        + f"Path({str(ready)!r}).write_text('ready')\n"
        + ("os.close(1);os.close(2)\n" if close_pipes else "")
        + "time.sleep(60)\n"
    )
    process = subprocess.Popen([sys.executable, "-u", "-c", source],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.01)
        assert ready.exists()
        monkeypatch.setattr(rwe, "_CONTROLLER_CLEANUP_SECONDS", 0.8)
        started = time.monotonic()
        confirmed = rwe._stop_gate_controller(process)
        elapsed = time.monotonic() - started
        assert process.poll() is not None
        assert confirmed is close_pipes
        assert 0.25 <= elapsed < 1.8
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        process.stdout.close()
        process.stderr.close()

@pytest.mark.parametrize("signal_number", [signal.SIGINT, signal.SIGTERM])
def test_signal_during_normal_stream_close_cannot_return_completed_observation(tmp_path, monkeypatch, signal_number):
    original = subprocess.Popen
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    processes = []

    class SignalOnClose:
        def __init__(self, stream):
            self.stream = stream
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def close(self):
            self.stream.close()
            os.kill(os.getpid(), signal_number)

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        process.stdout = SignalOnClose(process.stdout)
        processes.append(process)
        return process

    monkeypatch.setattr(rwe.subprocess, "Popen", launch)
    with pytest.raises(rwe._GateInterrupted) as captured:
        rwe._stream_gate([sys.executable, "-c", "print('completed')"],
                         cwd=tmp_path, supervised_controller=True)
    assert captured.value.signum == signal_number
    assert len(processes) == 1 and processes[0].poll() == 0
    assert all(signal.getsignal(number) == handler for number, handler in previous.items())


def test_stream_close_error_restores_handlers_and_preserves_original_observer_failure(tmp_path, monkeypatch):
    original = subprocess.Popen
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    processes = []

    class FailedClose:
        def __init__(self, stream):
            self.stream = stream
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def close(self):
            self.stream.close()
            raise OSError("owned stream close failed")

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        process.stdout = FailedClose(process.stdout)
        processes.append(process)
        return process

    def refuse(*args, **kwargs):
        raise OSError("original observer failure")

    monkeypatch.setattr(rwe.subprocess, "Popen", launch)
    monkeypatch.setattr(rwe, "_observe_gate", refuse)
    with pytest.raises(OSError) as captured:
        rwe._stream_gate([sys.executable, "-c", "import time;time.sleep(60)"],
                         cwd=tmp_path, supervised_controller=True)
    assert str(captured.value) == "original observer failure"
    assert "rwe_env gate: stream close failed during cleanup" in captured.value.__notes__
    assert len(processes) == 1 and processes[0].poll() is not None
    assert all(signal.getsignal(number) == handler for number, handler in previous.items())

@pytest.mark.parametrize("signal_number", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("combine_streams", [False, True], ids=["separate", "combined"])
def test_unread_wrapper_output_cannot_block_nested_cancellation(tmp_path, signal_number, combine_streams):
    source = (
        "from pathlib import Path\nimport os,signal,subprocess,sys,time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "child = subprocess.Popen([sys.executable, '-c', \"import os,signal,time;from pathlib import Path;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "Path('seen/grandchild-'+str(os.getpid())).write_text(str(os.getpid()));time.sleep(60)\"])\n"
        "Path('seen/child-'+str(os.getpid())).write_text(str(os.getpid()))\n"
        "def test_flood_output():\n"
        "    while True: print('CI_MODULE ' + 'x' * 65536, flush=True)\n"
    )
    root, environment, env, original = _project(tmp_path, source)
    process = subprocess.Popen(_launcher(root, "blocked-output"), cwd=root, env=env,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT if combine_streams else subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            children = list((root / "seen").glob("child-*"))
            grandchildren = list((root / "seen").glob("grandchild-*"))
            if ((root / "seen/output-full").exists()
                    and len(children) == len(grandchildren) == 1):
                break
            assert process.poll() is None
            time.sleep(0.02)
        assert (root / "seen/output-full").exists()
        assert len(children) == len(grandchildren) == 1
        owned = [int(path.read_text()) for path in (*children, *grandchildren)]
        controller = int((root / "seen/controller").read_text())
        process.send_signal(signal_number)
        # Deliberately do not read either output pipe until exit and child
        # custody have been checked. Reading could accidentally rescue a writer.
        deadline = time.monotonic() + 15
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert process.poll() == 128 + signal_number
        assert not _running(controller)
        assert all(not _running(pid) for pid in owned)
        assert (environment / rwe.RECEIPT_FILENAME).read_bytes() == original
        output, errors = process.communicate(timeout=2)
        if not combine_streams:
            assert "gate interrupted" in errors
        # A full combined pipe may drop the bounded best-effort diagnostic;
        # returning the original signal code must not depend on its consumer.
    finally:
        for path in (root / "seen").glob("child-*"):
            try:
                os.killpg(int(path.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        controller_file = root / "seen/controller"
        if controller_file.exists() and _running(int(controller_file.read_text())):
            try:
                os.kill(int(controller_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=3)


def test_cancellable_output_preserves_unicode_partial_writes_and_descriptor_flags(tmp_path, monkeypatch):
    original_write = os.write
    attempts = []
    text = "before\nafter: 雪 λ 🐍\n"
    path = tmp_path / "forwarded"
    with path.open("w+", encoding="utf-8") as destination:
        descriptor = destination.fileno()
        assert os.get_blocking(descriptor)
        def partial_write(fd, data):
            assert fd == descriptor and not os.get_blocking(fd)
            attempts.append(len(data))
            if len(attempts) == 1:
                raise BlockingIOError()
            return original_write(fd, data[:3])
        monkeypatch.setattr(rwe.os, "write", partial_write)
        with rwe._gate_output_writer(destination, lambda: None) as forward:
            forward(text)
        assert os.get_blocking(descriptor)
        destination.seek(0)
        assert destination.read() == text
        assert len(attempts) > 3

    with path.open("w", encoding="utf-8") as destination:
        descriptor = destination.fileno()
        def cancelled():
            raise rwe._GateInterrupted(signal.SIGINT)
        with pytest.raises(rwe._GateInterrupted):
            with rwe._gate_output_writer(destination, cancelled) as forward:
                forward("never")
        assert os.get_blocking(descriptor)


@pytest.mark.parametrize("signal_error", [
    pytest.param(PermissionError, id="refused"),
    pytest.param(OSError, id="failed"),
    pytest.param(ProcessLookupError, id="absent"),
])
def test_refused_controller_signal_is_not_retried_and_cannot_complete_receipt(
    tmp_path, monkeypatch, signal_error,
):
    args, environment = _arguments(tmp_path, monkeypatch)
    args.processes = 4
    original = json.dumps({"schema": rwe.SCHEMA, "definition": {"lock_path": None},
                           "proof": {"realized": True}, "degraded": []}).encode()
    (environment / rwe.RECEIPT_FILENAME).write_bytes(original)
    calls = []

    class Controller:
        stdout = stderr = None
        returncode = None
        def poll(self):
            return self.returncode
        def send_signal(self, number):
            calls.append(("signal", number))
            raise signal_error(1, "injected controller signal refusal")
        def kill(self):
            calls.append(("kill", signal.SIGKILL))
            self.returncode = -signal.SIGKILL
        def wait(self, timeout):
            if self.returncode is None:
                time.sleep(min(0.005, max(0.0, timeout)))
                raise subprocess.TimeoutExpired("owned controller", timeout)
            return self.returncode

    controller = Controller()
    monkeypatch.setattr(rwe.subprocess, "Popen", lambda *a, **k: controller)
    def interrupted(*a, **k):
        raise rwe._GateInterrupted(signal.SIGINT)
    monkeypatch.setattr(rwe, "_observe_gate", interrupted)
    monkeypatch.setattr(rwe, "_CONTROLLER_CLEANUP_SECONDS", 0.05)
    handlers = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    started = time.monotonic()
    with pytest.raises(rwe._GateInterrupted) as captured:
        rwe.cmd_gate(args)
    assert captured.value.signum == signal.SIGINT
    assert "rwe_env gate: controller cleanup unconfirmed" in captured.value.__notes__
    assert calls == [("signal", signal.SIGTERM)]
    assert controller.returncode is None
    assert time.monotonic() - started < 0.5
    assert (environment / rwe.RECEIPT_FILENAME).read_bytes() == original
    assert all(signal.getsignal(number) == handler for number, handler in handlers.items())

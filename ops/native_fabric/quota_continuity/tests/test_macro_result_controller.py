"""Full current-controller proofs for canonical new-Macro results.

The current ControllerDeadline stages source followed by candidate bytes.
Only inert executables and the host registry are adapted; production helpers,
controller source, and task readers execute unchanged. This qualifies local
controller wiring, not a real Macro mint or provider.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import unittest
from unittest import mock


BASE_COMMIT = "c9cbee5569ba50e30e28715d930809061a169517"
HOST = "ubuntu0"
FROZEN_MACRO_COMMIT = "a" * 40  # Inert argv only; no git or mint helper executes.
RESULT_BYTES = b"CANONICAL MACRO RESULT\nfinite offline controller fixture\n"
DIAGNOSTIC_BYTES = b"OFFLINE WORKER DIAGNOSTIC; no final result\n"
SESSION_SUFFIXES = ("session-created.json", "session-retained.json")


NATIVE = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "macro_result_deadline_fixture", NATIVE / "tests/test_commission_deadline.py")
assert _spec is not None and _spec.loader is not None
deadline_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deadline_fixture)


# Inserted before the existing inert fixture's broker/SSH/SCP/rsync dispatch.
# Every command not handled here still uses that reviewed fixture. Unknown
# commands fall through to its forbidden-operation tripwire. No remote command
# is evaluated, and no uploaded support code or production mint helper runs.
MACRO_TRANSPORT = r'''
macro = json.loads((root / 'macro-result-case.json').read_text())
rid = macro['run_id']
session_suffixes = ('session-created.json', 'session-retained.json')
if name == 'ssh':
    command = args[-1]
    if (macro.get('mode') == 'glm' and args[:-1] == [
            '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'inert-transport']):
        manifest_path = root / 'ext/state/remote_sub' / (rid + '.support.json')
        if manifest_path.is_file():
            import shlex
            files = json.loads(manifest_path.read_text())
            support = hashlib.sha256(json.dumps(
                {'schema': 'remote-support-code.v1', 'files': files},
                sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            owner = shlex.quote(str(root / 'physical-owner'))
            rpath = (f'export PATH={owner}/venv/bin:'
                     '$HOME/.local/bin:/opt/homebrew/bin:$PATH')
            host_env = (f'source {owner}/ext/HOST_ENV.sh 2>/dev/null; '
                        f'export PATH={owner}/venv/bin:$PATH')
            expected = (f'{rpath}; {host_env}; python3 '
                        f'{owner}/support-releases/{support}/ext/glm_keys.py '
                        'account-ready fixture-account')
            if command == expected:
                record('account_ready', support_digest=support, account='fixture-account')
                print('1')
                raise SystemExit(0)
    cwd_probe = (
        "python3 -c 'import os,sys; p=bytes.fromhex(sys.argv[1]).decode(\"utf-8\"); "
        "sys.exit(0 if os.path.isdir(os.path.expanduser(p)) else 78)' "
        "'7e2f6c616e65732f7265706f732f6d6163726f'"
    )
    if args == ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                'inert-transport', cwd_probe]:
        record('cwd_preflight')
        ready = root / 'remote-home/lanes/repos/macro'
        raise SystemExit(0 if ready.is_dir() else 78)
    if 'nohup env ' in command:
        child = re.search(r"REMOTE_SUB_CHILD_TIMEOUT='([0-9]+)'", command)
        budget = re.search(r"REMOTE_SUB_COMMISSION_BUDGET_SECONDS='([0-9]+)'", command)
        record('launch', child_timeout=int(child.group(1)) if child else None,
               remote_budget=int(budget.group(1)) if budget else None,
               original_macro_commit=("FABRIC_NEW_MACRO_COMMIT='" + macro['commit'] + "'") in command,
               original_run=("REMOTE_SUB_RUN_ID='" + rid + "'") in command,
               original_host="LANE_REMOTE_HOST='ubuntu0'" in command)
        raise SystemExit(macro['launch_rc'])
    if '__REMOTE_SUB_PENDING__' in command:
        record('poll', worker_rc=macro['worker_rc'])
        print(macro['worker_rc'])
        raise SystemExit(0)
    if command.startswith('test -f '):
        for suffix in session_suffixes:
            if command.endswith('/' + rid + '.' + suffix):
                record('session_probe', suffix=suffix)
                raise SystemExit(0 if macro['sessions'] else 1)
elif name == 'rsync' and args != ['--version']:
    source, destination = args[-2:]
    target = Path(destination)
    # Destination containment is a fixture tripwire, not a production policy.
    try:
        target.relative_to(root)
    except ValueError:
        record('forbidden', command='rsync_outside_fixture')
        raise SystemExit(125)
    for suffix in session_suffixes:
        if source.endswith('/' + rid + '.' + suffix):
            record('session_collect', suffix=suffix, destination=destination)
            if macro['session_failure'] == suffix:
                raise SystemExit(23)
            payload = (root / 'remote-receipts' / (rid + '.' + suffix)).read_bytes()
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(payload)
            raise SystemExit(0)
    if source.endswith('/ext/lanes_' + rid + '.stdout'):
        before = None
        try:
            info = target.lstat()
            before = {'mode': info.st_mode & 0o777, 'nlink': info.st_nlink,
                      'uid': info.st_uid, 'regular': (info.st_mode & 0o170000) == 0o100000}
        except FileNotFoundError:
            pass
        record('stdout_collect', source=source, destination=destination, before=before)
        raw = (root / 'remote-stdout').read_bytes()
        if macro['stdout_failure']:
            raw = raw[:7]  # A real partial destination must never become a result.
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
        raise SystemExit(23 if macro['stdout_failure'] else 0)
    record('forbidden', command='unexpected_rsync_carrier', source=source)
    raise SystemExit(125)
elif name == 'ledger':
    record('ledger', argv=args)
    raise SystemExit(0)
'''


# These two faults live in the inert interpreter, not in production source.
# The support helper executes normally before the fixture returns reserved rc76.
# The reservation cut runs the actual stdin body to completion before pausing.
FIXTURE_FAULTS = r'''
import json, time
_fixture_root = Path(os.environ['DEADLINE_FIXTURE_ROOT'])
_fixture_case = json.loads((_fixture_root / 'macro-result-case.json').read_text())
_fixture_rid = _fixture_case['run_id']
def fixture_record(stage, **extra):
    row = dict(stage=stage, monotonic_ns=time.monotonic_ns(), pid=os.getpid(), **extra)
    with (_fixture_root / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')

_support_argv = [str(_fixture_root / 'ext/remote_sub_helpers.py'), 'support-meta',
                 str(_fixture_root / 'ext'),
                 str(_fixture_root / 'ext/state/remote_sub' / (_fixture_rid + '.support.json'))]
if (_fixture_case.get('fixture_fault') == 'support-meta-unproven'
        and args[:4] == _support_argv and len(args) > 4):
    original_argv = list(args)
    sys.argv = args
    runpy.run_path(args[0], run_name='__main__')
    fixture_record('fixture_support_meta_unproven', argv=original_argv)
    raise SystemExit(76)

def fixture_after_stdin():
    if _fixture_case.get('fixture_fault') != 'after-reservation':
        return
    expected = ['-',
                str(_fixture_root / 'ext/state/remote_sub' / (_fixture_rid + '.log')),
                _fixture_rid, _fixture_case['fixture_host'], _fixture_case['mode'],
                _fixture_case['model'], _fixture_case['fixture_packet'],
                _fixture_case['fixture_cwd'], str(_fixture_root / 'ext'),
                _fixture_case['commit']]
    if args != expected:
        return
    # Publish a complete fixture-only handshake after production has fsynced
    # and closed its reservation. No log or policy record is manufactured here.
    record = dict(schema='offline.reservation_barrier.v1', run_id=_fixture_rid,
                  controller_pid=os.getppid(), writer_pid=os.getpid(),
                  process_group=os.getpgrp(), argv=list(args))
    ready = _fixture_root / 'reservation-ready.json'
    temporary = _fixture_root / 'reservation-ready.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(record, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, ready, follow_symlinks=False)
    temporary.unlink()
    import signal
    while True:
        signal.pause()
'''


# The existing wrapper continues to run the real helper via runpy. Trace only
# the proposed helper entry points, so tests can prove ordering without mocking
# either helper's implementation or hard-coding its receipt format.
HELPER_TRACE = r'''
if len(args) > 1 and Path(args[0]).name == 'remote_sub_helpers.py' and args[1] in (
        'macro-result-prepare', 'macro-result-publish'):
    import json, time
    row = {'stage': 'macro_prepare' if args[1] == 'macro-result-prepare' else 'macro_publish',
           'monotonic_ns': time.monotonic_ns(), 'argv': args[2:]}
    with (Path(os.environ['DEADLINE_FIXTURE_ROOT']) / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
'''


READ_ACTUAL_TASK = r'''
import base64, json, sys
from pathlib import Path
here = Path(sys.argv[1])
sys.path.insert(0, str(here))
import fabric_task as task
assert Path(task.__file__).resolve() == here / 'fabric_task.py'
assert task.HERE == here
rid = sys.argv[2]
status = task.inspect_run(rid)
try:
    raw = task.read_result(rid, max_bytes=8192)
except (task.FabricTaskError, ValueError, OSError) as error:
    result = {'available': False, 'error_type': type(error).__name__, 'error': str(error)}
else:
    result = {'available': True, 'bytes_b64': base64.b64encode(raw).decode('ascii')}
print(json.dumps({'status': status, 'result': result}, sort_keys=True))
'''


class MacroResultControllerTests(unittest.TestCase):
    def setUp(self):
        # Compose the fixture instead of inheriting its unrelated deadline tests.
        self.harness = deadline_fixture.ControllerDeadline(
            "test_plain_prelaunch_evidence_is_verified_and_ordered_before_launch")
        # DirectoryChain must see trusted ancestry. The existing harness's
        # default repository directory may be below a shared writable volume.
        fixture_parent = os.environ.get("NATIVE_ROLLOUT_TEST_ROOT", str(Path.home()))
        with mock.patch.dict(os.environ, {"NATIVE_ROLLOUT_TEST_ROOT": fixture_parent}):
            self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        self.root, self.ext, self.bin = self.harness.root, self.harness.ext, self.harness.bin
        (self.ext / "lanes").mkdir(mode=0o700, exist_ok=True)
        self.custom_parent = self.root / "custom output"
        self.custom_parent.mkdir(mode=0o700)
        self.custom = self.custom_parent / "answer.txt"
        self.remote_receipts = self.root / "remote-receipts"
        self.remote_receipts.mkdir(mode=0o700)
        (self.root / "remote-home/lanes/repos/macro").mkdir(parents=True, mode=0o700)

        registry_path = self.ext / "hosts.json"
        registry = json.loads(registry_path.read_text())
        registry[HOST] = registry.pop("fixture")
        # Deliberately unbound: no physical_lane_root and no support for bound
        # new-Macro is claimed by this fixture.
        self.assertNotIn("physical_lane_root", registry[HOST])
        registry_path.write_text(json.dumps(registry))
        registry_path.chmod(0o600)

        boundary = "if name == 'broker':\n"
        self.assertEqual(deadline_fixture.FIXTURE.count(boundary), 1)
        carrier = deadline_fixture.FIXTURE.replace(boundary, MACRO_TRANSPORT + "\n" + boundary)
        for name in ("ssh", "scp", "rsync", "broker", "ledger", "claude", "codex", "curl", "node"):
            deadline_fixture.write(self.bin / name, "#!" + sys.executable + "\n" + carrier,
                                   executable=True)
        boundary = "args=sys.argv[1:]\nif args[0]=='-c':"
        self.assertEqual(deadline_fixture.PYTHON_FIXTURE.count(boundary), 1)
        interpreter = deadline_fixture.PYTHON_FIXTURE.replace(
            boundary, "args=sys.argv[1:]\n" + FIXTURE_FAULTS + HELPER_TRACE + "\nif args[0]=='-c':")
        stdin_body = "    exec(compile(sys.stdin.read(),'<fixture stdin>','exec'),{'__name__':'__main__'})\n"
        self.assertEqual(interpreter.count(stdin_body), 1)
        interpreter = interpreter.replace(stdin_body, stdin_body + "    fixture_after_stdin()\n")
        deadline_fixture.write(self.bin / "fixture-python", "#!" + sys.executable + "\n" + interpreter,
                               executable=True)

        self.production_hashes = {}
        for name in ("remote_sub.sh", "remote_sub_helpers.py", "fabric_task.py"):
            expected = (NATIVE / "candidate" / name).read_bytes()
            self.assertEqual((self.ext / name).read_bytes(), expected)
            self.production_hashes[name] = hashlib.sha256(expected).hexdigest()

    def canonical(self, rid):
        return self.ext / "lanes" / (rid + ".remote.stdout")

    def log_path(self, rid):
        return self.ext / "state/remote_sub" / (rid + ".log")

    def stages(self, result):
        return [row["stage"] for row in result["events"]]

    def run_macro(self, rid, *, custom=False, worker_rc=0, stdout_failure=False,
                  sessions=False, session_failure=None, launch_rc=0,
                  mode="minimax", model="fixture-model", escalation_reason=None):
        self.assertNotIn("/", rid)
        config = dict(run_id=rid, commit=FROZEN_MACRO_COMMIT, worker_rc=worker_rc,
                      stdout_failure=stdout_failure, sessions=sessions,
                      session_failure=session_failure, launch_rc=launch_rc,
                      mode=mode, model=model)
        config.update(fixture_fault=getattr(self, "fixture_fault", None), fixture_host=HOST,
                      fixture_packet=str(self.harness.packet), fixture_cwd="~/lanes/repos/macro")
        (self.root / "macro-result-case.json").write_text(json.dumps(config))
        raw = RESULT_BYTES if worker_rc == 0 else DIAGNOSTIC_BYTES
        (self.root / "remote-stdout").write_bytes(raw)
        original_receipts = {}
        if sessions:
            for suffix in SESSION_SUFFIXES:
                # Small discovery receipts only; no private session content.
                schema = ("mastermind.local_session_created.v1" if suffix.startswith("session-created")
                          else "mastermind.local_session_retained.v1")
                row = dict(schema=schema, run_id=rid, root_id="offline-root",
                           parent_id="offline-parent", host=HOST, provider=mode,
                           home_path="/inert/private-session-not-probed", command_rc=worker_rc)
                content = (json.dumps(row, sort_keys=True) + "\n").encode()
                (self.remote_receipts / (rid + "." + suffix)).write_bytes(content)
                original_receipts[suffix] = content
        budget = 25
        origin = time.monotonic_ns() + budget * 1_000_000_000
        env = {
            "PATH": str(self.bin) + ":/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(self.harness.tmp), "DEADLINE_FIXTURE_ROOT": str(self.root),
            "DEADLINE_FIXTURE_CASE": "macro-result", "DEADLINE_FIXTURE_BROKER_DELAY": "0",
            "REMOTE_SUB_MAX_SECS": str(budget), "REMOTE_SUB_POLL_SECS": "1",
            "REMOTE_SUB_ADMISSION_RETRY_SECS": "1", "REMOTE_SUB_ADMISSION_WAIT_SECS": "0",
            "REMOTE_SUB_PYTHON": str(self.bin / "fixture-python"),
            "REMOTE_SUB_BROKER_CMD": str(self.bin / "broker"),
            "REMOTE_SUB_LEDGER_CMD": str(self.bin / "ledger"),
            "REMOTE_SUB_SSH_CMD": str(self.bin / "ssh"),
            "REMOTE_SUB_SCP_CMD": str(self.bin / "scp"),
            "REMOTE_SUB_RSYNC_CMD": str(self.bin / "rsync"),
            "POOL_ORCHESTRATOR_ID": "offline-root", "POOL_PARENT_RUN_ID": "offline-parent",
            "POOL_TASK_CLASS": "domain_orchestration", "POOL_TASK_COMPLEXITY": "C0_MECHANICAL",
            "POOL_COMMISSION_REMAINING_SECONDS": str(budget),
            "POOL_COMMISSION_DEADLINE_NS": str(origin),
            "POOL_LEDGER_PATH": str(self.root / "inert-reader-ledger.jsonl"),
        }
        if escalation_reason is not None:
            env["POOL_ESCALATION_REASON"] = escalation_reason
        command = ["/bin/bash", str(self.ext / "remote_sub.sh"), HOST, mode,
                   str(self.harness.packet), "~/lanes/repos/macro", model,
                   "--run-id", rid, "--new-macro-worktree", FROZEN_MACRO_COMMIT]
        if custom:
            command.extend(["--out", str(self.custom)])
        proc = subprocess.Popen(command, cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
        try:
            if config["fixture_fault"] == "after-reservation":
                stdout, stderr = self.crash_after_reservation(proc, rid)
            else:
                stdout, stderr = proc.communicate(timeout=35)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                stdout, stderr = proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate(timeout=3)
            self.fail("Offline fixture exceeded its bound: " + stderr)
        event_path = self.root / "events.jsonl"
        events = [json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
        self.assertNotIn("forbidden", [row["stage"] for row in events], stderr)
        for name, expected in self.production_hashes.items():
            self.assertEqual(hashlib.sha256((self.ext / name).read_bytes()).hexdigest(), expected)
        log = self.log_path(rid).read_text() if self.log_path(rid).exists() else ""
        return dict(run_id=rid, returncode=proc.returncode, stdout=stdout, stderr=stderr,
                    log=log, events=events, original_receipts=original_receipts)

    def crash_after_reservation(self, proc, rid):
        # Keep this Popen's group leader unreaped until after the signal, so its
        # PID cannot be recycled into an unrelated process group. Do not poll.
        ready = self.root / "reservation-ready.json"
        cutoff = time.monotonic() + 10
        try:
            while not ready.exists() and time.monotonic() < cutoff:
                time.sleep(0.01)
            self.assertTrue(ready.is_file(), "Real reservation did not reach the fixture barrier")
            record = json.loads(ready.read_text())
            self.assertEqual(record["schema"], "offline.reservation_barrier.v1")
            self.assertEqual(record["run_id"], rid)
            self.assertEqual(record["controller_pid"], proc.pid)
            self.assertEqual(record["process_group"], proc.pid)
            self.assertNotEqual(record["writer_pid"], proc.pid)
            self.assertEqual(os.getpgid(proc.pid), proc.pid)
        finally:
            # This is only the session/group created by this fixture's own
            # start_new_session=True Popen. Always consume it, even on failure.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate(timeout=5)
        return stdout, stderr

    def read_actual(self, rid):
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
               "POOL_LEDGER_PATH": str(self.root / "inert-reader-ledger.jsonl")}
        response = subprocess.run([sys.executable, "-I", "-B", "-c", READ_ACTUAL_TASK,
                                   str(self.ext), rid], cwd=self.root, env=env,
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
        return json.loads(response.stdout)

    def assert_unavailable(self, result, *, expected_state=None):
        read = self.read_actual(result["run_id"])
        self.assertIs(read["status"]["result_available"], False, read)
        self.assertIs(read["result"]["available"], False, read)
        self.assertIsNot(read["status"].get("accepted"), True, read)
        self.assertIsNot(read["status"].get("retry_allowed"), True, read)
        if expected_state is not None:
            self.assertEqual(read["status"]["state"], expected_state, read)
        return read

    def assert_original_dispatch(self, result):
        events, stages = result["events"], self.stages(result)
        self.assertEqual(stages.count("macro_prepare"), 1, result["stderr"])
        self.assertEqual(stages.count("acquire"), 1, result["stderr"])
        self.assertEqual(stages.count("launch"), 1, result["stderr"])
        self.assertLess(stages.index("macro_prepare"), stages.index("acquire"))
        self.assertEqual(stages.count("cwd_preflight"), 1)
        self.assertLess(stages.index("macro_prepare"), stages.index("cwd_preflight"))
        self.assertLess(stages.index("cwd_preflight"), stages.index("acquire"))
        launch = next(row for row in events if row["stage"] == "launch")
        self.assertTrue(launch["original_macro_commit"])
        self.assertTrue(launch["original_run"])
        self.assertTrue(launch["original_host"])

    def assert_success(self, result, *, custom=False):
        self.assertEqual(result["returncode"], 0, result["stderr"])
        self.assert_original_dispatch(result)
        stages = self.stages(result)
        self.assertEqual(stages.count("stdout_collect"), 1)
        self.assertEqual(stages.count("macro_publish"), 1)
        self.assertLess(stages.index("poll"), stages.index("stdout_collect"))
        self.assertLess(stages.index("stdout_collect"), stages.index("macro_publish"))
        transfer = next(row for row in result["events"] if row["stage"] == "stdout_collect")
        target = self.canonical(result["run_id"])
        self.assertNotEqual(Path(transfer["destination"]), target)
        self.assertNotEqual(Path(transfer["destination"]), self.custom)
        self.assertEqual(transfer["before"],
                         dict(mode=0o600, nlink=1, uid=os.getuid(), regular=True), transfer)
        for path in ([target, self.custom] if custom else [target]):
            self.assertEqual(path.read_bytes(), RESULT_BYTES)
            info = path.lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual((info.st_mode & 0o777, info.st_nlink), (0o600, 2))
        read = self.read_actual(result["run_id"])
        self.assertEqual((read["status"]["state"], read["status"]["rc"], read["status"]["signal"]),
                         ("TERMINAL", 0, "ok"), read)
        self.assertIs(read["status"]["result_available"], True)
        self.assertIs(read["result"]["available"], True)
        self.assertEqual(base64.b64decode(read["result"]["bytes_b64"]), RESULT_BYTES)
        self.assertIsNot(read["status"].get("accepted"), True)
        self.assertIn("release", stages)

    def collision_case(self, rid, *, existing_custom=False, custom=False):
        prior = self.custom if existing_custom else self.canonical(rid)
        prior.write_bytes(b"PREEXISTING OWNER BYTES\n")
        prior.chmod(0o600)
        identity = (prior.lstat().st_dev, prior.lstat().st_ino, prior.lstat().st_mode)
        result = self.run_macro(rid, custom=custom)
        self.assertEqual(result["returncode"], 78, result["stderr"])
        self.assertEqual(prior.read_bytes(), b"PREEXISTING OWNER BYTES\n")
        self.assertEqual((prior.lstat().st_dev, prior.lstat().st_ino, prior.lstat().st_mode), identity)
        for stage in ("acquire", "scp", "support_publish", "launch", "stdout_collect", "macro_publish"):
            self.assertNotIn(stage, self.stages(result), result["stderr"])

    def test_default_output_is_published_from_private_capture_and_readable(self):
        self.assert_success(self.run_macro("macro-default-success"))

    def test_custom_output_keeps_canonical_result_and_exact_private_mirror(self):
        self.assert_success(self.run_macro("macro-custom-success", custom=True), custom=True)

    def test_qwen_policy_path_data_preserves_actual_plain_launch_binding(self):
        self.custom = self.custom_parent / "FAILED EFFECT_UNKNOWN CONTROLLER_PROCESS_UNPROVEN answer.txt"
        result = self.run_macro("macro-qwen-policy-data", custom=True,
                                mode="qwen", model="qwen3.8-flash")
        self.assert_success(result, custom=True)
        events = [line.split("] ", 1)[1] for line in result["log"].splitlines()]
        bindings = [json.loads(event[len("LAUNCH_BINDING "):]) for event in events
                    if event.startswith("LAUNCH_BINDING ")]
        self.assertEqual(len(bindings), 1)
        self.assertEqual((bindings[0]["mode"], bindings[0]["pool"],
                          bindings[0]["acquisition_pool"]),
                         ("qwen", "bailian", "bailian"))
        self.assertEqual(sum(event.startswith("TRANSPORT_VERIFIED ") for event in events), 1)

    def test_glm_policy_path_data_preserves_frontier_acquisition_and_account_readiness(self):
        self.custom = self.custom_parent / "FAILED CONTROLLER_PROCESS_UNPROVEN EFFECT_UNKNOWN answer.txt"
        result = self.run_macro("macro-glm-policy-data", custom=True,
                                mode="glm", model="glm-5.3", escalation_reason=(
            "Offline regression requires the requested GLM acquisition tuple; "
            "all carriers and the worker are inert."))
        self.assert_success(result, custom=True)
        events = [line.split("] ", 1)[1] for line in result["log"].splitlines()]
        bindings = [json.loads(event[len("LAUNCH_BINDING "):]) for event in events
                    if event.startswith("LAUNCH_BINDING ")]
        self.assertEqual(len(bindings), 1)
        binding = bindings[0]
        self.assertEqual((binding["schema"], binding["mode"], binding["pool"],
                          binding["acquisition_pool"], binding["requested_model"]),
                         ("mastermind.fabric_plain_launch_binding.v3", "glm", "glm",
                          "glm-frontier", "glm-5.3"))
        self.assertEqual(binding["transport"]["acquisition_pool"], "glm-frontier")
        self.assertIsNone(binding["transport"]["lane_root"])
        receipt = json.loads((self.ext / "state/remote_sub" /
                             (result["run_id"] + ".transport-verified.json")).read_text())
        self.assertEqual(receipt["schema"], "mastermind.transport_verification.v3")
        self.assertEqual(receipt["acquisition_pool"], "glm-frontier")
        self.assertIsNone(receipt["lane_root"])
        self.assertEqual(len(receipt["files"]), 37)
        self.assertEqual(receipt["packet_sha256"], hashlib.sha256(self.harness.packet.read_bytes()).hexdigest())
        stages = self.stages(result)
        self.assertEqual(stages.count("account_ready"), 1)
        self.assertLess(stages.index("account_ready"), stages.index("launch"))

    def test_preexisting_canonical_refuses_before_lease_for_default_output(self):
        self.collision_case("macro-default-collision")

    def test_preexisting_canonical_refuses_before_lease_for_custom_output(self):
        self.collision_case("macro-canonical-collision", custom=True)

    def test_preexisting_custom_refuses_before_lease_without_overwrite(self):
        self.collision_case("macro-custom-collision", existing_custom=True, custom=True)

    def test_nonzero_worker_keeps_diagnostic_collection_but_reader_refuses_result(self):
        result = self.run_macro("macro-worker-nonzero", custom=True, worker_rc=17)
        self.assertEqual(result["returncode"], 17, result["stderr"])
        self.assert_original_dispatch(result)
        self.assertNotIn("macro_publish", self.stages(result))
        self.assertEqual(self.custom.read_bytes(), DIAGNOSTIC_BYTES)
        self.assertFalse(self.canonical(result["run_id"]).exists())
        self.assertIn("release", self.stages(result))
        read = self.assert_unavailable(result)
        self.assertEqual(read["status"]["rc"], 17, read)

    def test_partial_rsync_failure_never_publishes_or_exposes_result(self):
        result = self.run_macro("macro-rsync-failure", custom=True, stdout_failure=True)
        self.assertEqual(result["returncode"], 76, result["stderr"])
        self.assert_original_dispatch(result)
        self.assertNotIn("macro_publish", self.stages(result))
        self.assertFalse(self.canonical(result["run_id"]).exists())
        self.assertFalse(self.custom.exists())
        self.assertIn("RESULT_UNAVAILABLE", result["log"])
        self.assertIn("release", self.stages(result))
        self.assertNotIn("remote_cleanup", self.stages(result))
        self.assert_unavailable(result, expected_state="RESULT_UNAVAILABLE")

    def test_session_receipts_survive_current_collection_before_publication(self):
        result = self.run_macro("macro-session-preserved", custom=True, sessions=True)
        self.assert_success(result, custom=True)
        collection_index = self.stages(result).index("stdout_collect")
        for suffix, raw in result["original_receipts"].items():
            path = self.log_path(result["run_id"]).with_name(result["run_id"] + "." + suffix)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual((self.remote_receipts / path.name).read_bytes(), raw)
            event_index = next(index for index, event in enumerate(result["events"])
                               if event["stage"] == "session_collect" and event["suffix"] == suffix)
            self.assertLess(event_index, collection_index)
            self.assertIn("SESSION_INDEX_SAVED file=" + path.name, result["log"])

    def test_session_copy_failure_preserves_remote_receipt_and_worker_success(self):
        result = self.run_macro("macro-session-copy-failure", custom=True, sessions=True,
                                session_failure="session-created.json")
        self.assert_success(result, custom=True)
        rid = result["run_id"]
        state = self.log_path(rid).parent
        self.assertFalse((state / (rid + ".session-created.json")).exists())
        self.assertEqual((state / (rid + ".session-retained.json")).read_bytes(),
                         result["original_receipts"]["session-retained.json"])
        for suffix, raw in result["original_receipts"].items():
            self.assertEqual((self.remote_receipts / (rid + "." + suffix)).read_bytes(), raw)
        self.assertIn("SESSION_INDEX_COPY_FAILED remote_index_retained=1", result["log"])

    def test_support_meta_subshell_rc76_preserves_the_acquired_lease(self):
        self.fixture_fault = "support-meta-unproven"
        result = self.run_macro("macro-support-meta-unproven")
        self.assertEqual(result["returncode"], 3, result["stderr"])
        stages = self.stages(result)
        for stage in ("macro_prepare", "acquire", "granted", "fixture_support_meta_unproven"):
            self.assertEqual(stages.count(stage), 1, result["stderr"])
        self.assertLess(stages.index("macro_prepare"), stages.index("acquire"))
        self.assertLess(stages.index("granted"), stages.index("fixture_support_meta_unproven"))
        rid = result["run_id"]
        support = self.log_path(rid).with_name(rid + ".support.json")
        self.assertTrue(support.is_file(), "The real support-meta helper must run before injected rc76")
        fault = next(row for row in result["events"]
                     if row["stage"] == "fixture_support_meta_unproven")
        self.assertEqual(fault["argv"][:4], [str(self.ext / "remote_sub_helpers.py"),
                         "support-meta", str(self.ext), str(support)])
        owned_prefix = " [remote_sub id=" + rid + " host=" + HOST + "] "
        events = [line.split(owned_prefix, 1)[1] for line in result["log"].splitlines()
                  if owned_prefix in line]
        self.assertEqual(events.count("CONTROLLER_PROCESS_UNPROVEN stage=support-meta rc=76"), 1)
        self.assertIn("SUPPORT_HASH_FAILED", events)
        self.assertIn("LEASE_PRESERVED effect_unknown=1 lease=0123456789ab", events)
        for stage in ("scp", "support_publish", "launch", "poll", "stdout_collect",
                      "macro_publish", "release", "remote_cleanup"):
            self.assertNotIn(stage, stages, result["stderr"])
        self.assertFalse(self.canonical(rid).exists())
        self.assert_unavailable(result, expected_state="EFFECT_UNKNOWN")

    def test_real_reservation_crash_before_policy_never_reads_a_canonical_tripwire(self):
        self.fixture_fault = "after-reservation"
        result = self.run_macro("macro-reservation-crash")
        self.assertEqual(result["returncode"], -signal.SIGKILL, result["stderr"])
        rid = result["run_id"]
        self.assertRegex(result["log"], (
            r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z "
            r"\[remote_sub id=" + rid + " host=" + HOST + r"\] "
            r"MACRO_RESULT_REQUIRED schema=1\n\Z"))
        for stage in ("macro_prepare", "cwd_preflight", "acquire", "granted", "scp",
                      "support_publish", "launch", "stdout_collect", "macro_publish", "release"):
            self.assertNotIn(stage, self.stages(result), result["stderr"])
        log_bytes = self.log_path(rid).read_bytes()
        info = self.log_path(rid).lstat()
        self.assertEqual((info.st_mode & 0o777, info.st_nlink), (0o600, 1))
        target = self.canonical(rid)
        self.assertFalse(target.exists())
        # Only after our controller group was killed and consumed, place an
        # inert file where a legacy fallback would look. Readers must refuse it.
        tripwire = b"UNPUBLISHED CANONICAL TRIPWIRE\n"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(tripwire)
        identity = (target.lstat().st_dev, target.lstat().st_ino, target.lstat().st_mode)
        self.assert_unavailable(result)
        self.assertEqual(self.log_path(rid).read_bytes(), log_bytes)
        self.assertEqual(target.read_bytes(), tripwire)
        self.assertEqual((target.lstat().st_dev, target.lstat().st_ino, target.lstat().st_mode), identity)

    def test_observed_uncertain_worker_retains_custody_and_has_no_result(self):
        result = self.run_macro("macro-worker-uncertain", custom=True, worker_rc=76, sessions=True)
        self.assertEqual(result["returncode"], 76, result["stderr"])
        self.assert_original_dispatch(result)
        self.assertEqual(self.custom.read_bytes(), DIAGNOSTIC_BYTES)
        self.assertNotIn("macro_publish", self.stages(result))
        self.assertNotIn("release", self.stages(result))
        self.assertNotIn("remote_cleanup", self.stages(result))
        self.assertIn("LEASE_PRESERVED effect_unknown=1", result["log"])
        self.assert_unavailable(result, expected_state="EFFECT_UNKNOWN")

    def test_lost_launch_acknowledgment_never_retries_or_publishes(self):
        result = self.run_macro("macro-launch-uncertain", custom=True, launch_rc=255)
        self.assertEqual(result["returncode"], 255, result["stderr"])
        self.assert_original_dispatch(result)
        for stage in ("poll", "stdout_collect", "macro_publish", "release", "remote_cleanup"):
            self.assertNotIn(stage, self.stages(result))
        self.assertFalse(self.canonical(result["run_id"]).exists())
        self.assertFalse(self.custom.exists())
        self.assertIn("LEASE_PRESERVED effect_unknown=1", result["log"])
        self.assert_unavailable(result, expected_state="EFFECT_UNKNOWN")


if __name__ == "__main__":
    unittest.main(verbosity=2)

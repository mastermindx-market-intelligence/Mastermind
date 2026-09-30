"""Hermetic five-service observation tests; no native service is queried."""
import copy
from dataclasses import asdict, replace
import hashlib
import json
import plistlib
import stat
import traceback
from types import SimpleNamespace

import pytest

from control_plane import executive_release_observation as o


class World:
    """Synthetic OS facts below real parsing, joins, digests and sequencing."""
    def __init__(self, monkeypatch):
        self.module = o
        self.entry = o._observe_release
        self.error = o.ReleaseObservationError
        self.now = 1_000_000_000
        self.deadline = 20_000_000_000
        self.boot = "11111111-1111-4111-8111-111111111111"
        self.release = "a" * 40
        self.tree = "b" * 40
        self.states = {role: "RUNNING" for role in o._ROLES}
        self.states["broker"] = "LOADED_IDLE"
        self.instances = {100 + i: [500 + i, 20 + i] for i in range(5)}
        self.commands = {role: 0 for role in o._ROLES}
        self.process_calls = {}
        self.native_calls, self.write_calls, self.runtime_calls = [], [], []
        self.faults = {}
        self.edge = None
        self.drift = None
        self.boot_reads = 0
        self.rechecking = False
        self.artifacts = {}
        self.argvs = {}
        self.identities = {}
        self._make_artifacts()
        monkeypatch.setattr(o.sys, "platform", "darwin")
        monkeypatch.setattr(o.time, "monotonic_ns", lambda: self.now)
        monkeypatch.setattr(o, "_command", self.command)
        monkeypatch.setattr(o, "_artifact", self.artifact)
        monkeypatch.setattr(o.peer, "_observe_process_instance", self.process)
        monkeypatch.setattr(o.peer, "_verify_release", self.verify_release)
        monkeypatch.setattr(o.peer, "_verify_python_runtime", lambda budget: SimpleNamespace(launcher_digest="c" * 64, dylib_digest="d" * 64, main_digest="e" * 64))
        monkeypatch.setattr(o.peer, "_verify_network_closure", lambda budget: SimpleNamespace(aggregate="f" * 64))
        for name in ("_recheck_release", "_recheck_python_runtime", "_recheck_network_closure"):
            monkeypatch.setattr(o.peer, name, lambda before, budget: budget.check())
        original_recheck = o._recheck_content
        def recheck(snapshot, budget):
            self.rechecking = True
            self.hit("final_content")
            return original_recheck(snapshot, budget)
        monkeypatch.setattr(o, "_recheck_content", recheck)
        original_digest = o._digest
        def digest(domain, value):
            if domain == o._TARGET_DOMAIN:
                self.hit("return")
            return original_digest(domain, value)
        monkeypatch.setattr(o, "_digest", digest)

    def _make_artifacts(self):
        def substitute(value):
            if isinstance(value, str):
                return value.replace("{release}", o._RELEASES + self.release)
            if isinstance(value, list):
                return [substitute(x) for x in value]
            if isinstance(value, dict):
                return {key: substitute(x) for key, x in value.items()}
            return value
        for spec in o._SPECS:
            document = substitute(copy.deepcopy(o._profile(spec)))
            self.argvs[spec.role] = tuple(document["ProgramArguments"])
            self.artifacts[spec.plist] = plistlib.dumps(document)
            config = {
                "control": {"proof_base_sha": self.release, "control_uid": 450},
                "worker": {"schema_version": "mastermind.executive_worker_broker_config/v4", "worker_id": "codex-01", "worker_user": "_mastermind_worker", "worker_uid": 451, "worker_gid": 451, "control_uid": 450},
                "relay": {"schema": o._RELAY_CONFIG_SCHEMA, "relay_version": self.release},
                "gateway": {"schema": o.peer._GATEWAY_CONFIG_SCHEMA, "release_sha": self.release, "service_uid": 458, "executive_mcp_profile": "release_control_v1"},
                "broker": {"schema": "mastermind.executive_privileged_broker_config.v1", "release_root": o._RELEASES + self.release},
            }[spec.role]
            self.artifacts[spec.config] = json.dumps(config).encode()
        self.manifest_path = o._RELEASES + self.release + "/.executive-release-manifest.json"
        self.artifacts[self.manifest_path] = json.dumps({"tree_sha": self.tree}).encode()
        for index, path in enumerate(self.artifacts):
            self.identities[path] = (1, 1000 + index, 10)

    def artifact(self, path, mode, gid, budget):
        self.native_calls.append(("artifact", path))
        raw = self.artifacts[path]
        identity = self.identities[path]
        if self.rechecking and self.drift == "file_identity":
            identity = (*identity[:-1], identity[-1] + 1)
        if self.rechecking and self.drift == "manifest" and path == self.manifest_path:
            raw += b" "
        return o._Artifact(path, mode, gid, raw, identity, ((1, 2, 3),))

    def verify_release(self, topology, release, budget):
        assert topology.wrapper_relative == o._SPECS[0].wrapper
        return SimpleNamespace(manifest_digest=hashlib.sha256(self.artifacts[self.manifest_path]).hexdigest(),
                               digests=tuple((s.wrapper, "file", 0o444, 0, 0, 100, str(i + 1) * 64) for i, s in enumerate(o._SPECS)))

    def hit(self, edge):
        if self.edge == edge:
            self.now = self.deadline

    def command(self, argv, budget):
        self.native_calls.append(("command", argv))
        if argv == o.peer._SYSCTL_OSRELEASE_ARGV:
            return 0, b"25.5.0\n", b""
        if argv == o.peer._SYSCTL_BOOT_ID_ARGV:
            self.boot_reads += 1
            if self.boot_reads % 2 == 0:
                self.hit("final_boot")
            value = "22222222-2222-4222-8222-222222222222" if self.drift == "boot" and self.boot_reads % 2 == 0 else self.boot
            return 0, (value + "\n").encode(), b""
        spec = next(s for s in o._SPECS if argv == ("/bin/launchctl", "print", s.service))
        self.commands[spec.role] += 1
        if spec.role == "broker" and not self.rechecking:
            self.hit("fifth_role")
        if self.drift == "clock_rollback":
            self.now = 0
        state = self.states[spec.role]
        if self.rechecking and self.drift == "state":
            state = "UNLOADED"
        failure = self.faults.get(spec.role)
        missing = ('Could not find service "' + spec.label + '" in domain for system\n').encode()
        if failure in ("permission", "timeout", "generic_not_found_text", "wrong_label", "wrong_domain", "huge_output"):
            return {
                "permission": (1, b"", b"Operation not permitted\n"),
                "timeout": (1, b"", b"timed out\n"),
                "generic_not_found_text": (1, b"", missing),
                "wrong_label": (113, b"", missing.replace(spec.label.encode(), b"untrusted")),
                "wrong_domain": (113, b"", missing.replace(b"system", b"gui/501")),
                "huge_output": (0, b"X" * 65537, b""),
            }[failure]
        if state == "UNLOADED":
            return 113, b"", missing
        pid = 100 + o._ROLES.index(spec.role)
        fields = {"path": spec.plist, "type": "LaunchDaemon", "domain": "system", "username": spec.username,
                  "group": spec.group, "program": self.argvs[spec.role][0], "working directory": o._RELEASES + self.release,
                  "state": "running" if state == "RUNNING" else "not running"}
        if state == "RUNNING" and failure != "nested_only_pid":
            fields["pid"] = str(pid)
        lines = [spec.service + " = {"] + ["\t" + k + " = " + v for k, v in fields.items()]
        if failure == "duplicate_root_pid":
            lines.append("\tpid = " + str(pid))
        if failure == "nested_only_pid":
            lines.extend(["\tdiagnostics = {", "\t\tpid = " + str(pid), "\t}"])
        lines.append("\targuments = {")
        lines.extend("\t\t" + arg for arg in self.argvs[spec.role])
        lines.extend(["\t}", "}"])
        return 0, ("\n".join(lines) + "\n").encode(), b""

    def process(self, pid):
        self.native_calls.append(("process", pid))
        count = self.process_calls[pid] = self.process_calls.get(pid, 0) + 1
        if count >= 3:
            self.hit("final_process")
        unique, version = self.instances[pid]
        if self.rechecking and self.drift == "process_instance":
            unique += 1
        return o.peer._ProcessInstanceObservation(unique, version)

    def capture(self):
        self.rechecking = False
        return self.entry(deadline_monotonic_ns=self.deadline)

    def advance(self, ns):
        self.now += ns

    def change_instance(self, role, field):
        self.instances[100 + o._ROLES.index(role)][0 if field == "unique_id" else 1] += 1

    def set_state(self, role, state):
        self.states[role] = state

    def command_fault(self, role, failure):
        self.faults[role] = failure

    def expire_at(self, edge):
        self.edge = edge

    def drift_during_capture(self, fault):
        self.drift = fault
        if fault == "release":
            spec = o._SPECS[1]
            doc = plistlib.loads(self.artifacts[spec.plist])
            raw = plistlib.dumps(doc).replace(self.release.encode(), b"c" * 40)
            self.artifacts[spec.plist] = raw

    def content_payloads(self, result):
        return [asdict(record.content) for record in result.roles]

    def replace_then_restore_content(self, role):
        path = next(s.config for s in o._SPECS if s.role == role)
        self.identities[path] = (*self.identities[path][:-1], 100)


@pytest.fixture
def world(monkeypatch):
    return World(monkeypatch)


def test_all_roles_success(world):
    result = world.capture()
    assert tuple(x.role for x in result.roles) == o._ROLES
    assert len(result.target_observation_digest) == 64


@pytest.mark.parametrize("role", o._ROLES)
@pytest.mark.parametrize("state", ("RUNNING", "LOADED_IDLE", "UNLOADED"))
def test_all_role_state_combinations(world, role, state):
    world.set_state(role, state)
    result = world.capture().roles[o._ROLES.index(role)]
    assert result.state == state
    assert (result.pid is not None) is (state == "RUNNING")


@pytest.mark.parametrize("role", o._ROLES)
def test_plist_extra_key_refuses(world, role):
    spec = o._SPECS[o._ROLES.index(role)]
    doc = plistlib.loads(world.artifacts[spec.plist])
    doc["Unreviewed"] = "value"
    world.artifacts[spec.plist] = plistlib.dumps(doc)
    with pytest.raises(o.ReleaseObservationError):
        world.capture()


@pytest.mark.parametrize("role", o._ROLES)
def test_changed_service_account_refuses(world, role):
    spec = o._SPECS[o._ROLES.index(role)]
    doc = plistlib.loads(world.artifacts[spec.plist])
    doc["UserName"] = "arbitrary-user"
    world.artifacts[spec.plist] = plistlib.dumps(doc)
    with pytest.raises(o.ReleaseObservationError):
        world.capture()


@pytest.mark.parametrize("role,field", [("control", "control_uid"), ("worker", "worker_uid"), ("gateway", "service_uid")])
def test_boolean_account_id_refuses(world, role, field):
    path = o._SPECS[o._ROLES.index(role)].config
    doc = json.loads(world.artifacts[path])
    doc[field] = True
    world.artifacts[path] = json.dumps(doc).encode()
    with pytest.raises(o.ReleaseObservationError):
        world.capture()


@pytest.mark.parametrize("field,bad", [("unique_id", True), ("pidversion", False), ("unique_id", 0), ("unique_id", 2**64), ("pidversion", 2**31)])
def test_kernel_instance_type_and_range(world, field, bad):
    world.instances[100][0 if field == "unique_id" else 1] = bad
    with pytest.raises(o.ReleaseObservationError):
        world.capture()


@pytest.mark.parametrize("role", o._ROLES)
def test_content_changes_change_digest(world, role):
    before = world.capture()
    path = o._SPECS[o._ROLES.index(role)].config
    world.artifacts[path] += b" "
    after = world.capture()
    for a, b in zip(before.roles, after.roles, strict=True):
        assert (a.service_generation_digest != b.service_generation_digest) is (a.role == role)
    assert before.target_observation_digest != after.target_observation_digest


def test_existing_peer_roles_unchanged(world):
    world.capture()
    assert set(o.peer._LAUNCHD_ROLES) == {"control", "gateway"}


def test_direct_command_selector_is_closed(monkeypatch):
    monkeypatch.setattr(o.time, "monotonic_ns", lambda: 1)
    monkeypatch.setattr(o.subprocess, "Popen", lambda *a, **k: pytest.fail("native process started"))
    with pytest.raises(o.ReleaseObservationError, match="COMMAND_REFUSED"):
        o._command(("/bin/sh", "-c", "false"), o._Budget(100))


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate", "reordered"])
def test_closed_internal_role_set(world, change):
    roles = world.capture().roles
    bad = {"missing": roles[:-1], "extra": roles + (roles[-1],),
           "duplicate": (roles[0], roles[0], *roles[2:]),
           "reordered": tuple(reversed(roles))}[change]
    with pytest.raises(o.ReleaseObservationError):
        o._validate_roles(bad)


def test_first_refusal_survives_finally_expiry(monkeypatch):
    now = [1]
    monkeypatch.setattr(o.time, "monotonic_ns", lambda: now[0])
    budget = o._Budget(10)
    primary = o.ReleaseObservationError("PRIMARY_REFUSAL")
    def operation():
        try:
            raise primary
        finally:
            now[0] = 10
            budget.check()
    with pytest.raises(o.ReleaseObservationError) as caught:
        budget.call(operation)
    assert caught.value is primary


def test_return_fence_applies_inside_foreign_exception_handler(world):
    try:
        raise RuntimeError("caller's unrelated exception")
    except RuntimeError:
        world.expire_at("return")
        with pytest.raises(o.ReleaseObservationError, match="DEADLINE_EXCEEDED"):
            world.capture()


@pytest.mark.parametrize("boot", ["00000000-0000-0000-0000-000000000000", "invalid", "a" * 129])
def test_bad_boot_refuses(world, boot):
    world.boot = boot
    with pytest.raises(o.ReleaseObservationError):
        world.capture()


class CommandRig:
    def __init__(self, monkeypatch, out=b"25.5.0\n", err=b"", read_error=None, cleanup_error=None):
        self.now = 1_000_000_000
        self.rc = None
        self.killed = False
        self.waits = []
        self.closed = []
        self.payload = {10: [out, b""], 11: [err, b""]}
        self.map = {}
        self.read_error = read_error
        self.cleanup_error = cleanup_error
        self.stdout = self.stream(10)
        self.stderr = self.stream(11)
        self.selector = SimpleNamespace(register=self.register, get_map=lambda: self.map,
            select=lambda seconds: [(next(iter(self.map.values())), 1)],
            unregister=lambda stream: self.map.pop(stream.fileno()),
            close=lambda: self.closed.append("selector"))
        monkeypatch.setattr(o.time, "monotonic_ns", lambda: self.now)
        monkeypatch.setattr(o.subprocess, "Popen", self.popen)
        monkeypatch.setattr(o.selectors, "DefaultSelector", lambda: self.selector)
        monkeypatch.setattr(o.os, "set_blocking", lambda *args: None)
        monkeypatch.setattr(o.os, "read", self.read)

    def stream(self, fd):
        return SimpleNamespace(fileno=lambda: fd, close=lambda: self.closed.append(fd))

    def popen(self, argv, **kwargs):
        assert argv in o._COMMANDS
        assert kwargs["stdin"] == o.subprocess.DEVNULL
        assert kwargs["close_fds"] is True
        assert kwargs["env"] == o.peer._LAUNCHD_ENVIRONMENT
        return self

    def register(self, stream, event, index):
        self.map[stream.fileno()] = SimpleNamespace(fileobj=stream, data=index)

    def read(self, fd, count):
        if self.read_error is not None:
            raise self.read_error
        return self.payload[fd].pop(0)

    def poll(self):
        return self.rc

    def wait(self, timeout):
        self.waits.append(timeout)
        self.rc = 0 if self.rc is None else self.rc
        if self.cleanup_error and self.killed:
            raise self.cleanup_error
        return self.rc

    def kill(self):
        self.killed = True
        self.rc = -9
        if self.cleanup_error:
            raise self.cleanup_error


def test_real_command_bridge_bounds_and_closes_both_streams(monkeypatch):
    rig = CommandRig(monkeypatch)
    assert o._command(o.peer._SYSCTL_OSRELEASE_ARGV, o._Budget(2_000_000_000)) == (0, b"25.5.0\n", b"")
    assert rig.waits[0] <= 1
    assert sorted(map(str, rig.closed)) == ["10", "11", "selector"]


def test_command_first_refusal_survives_failed_cleanup(monkeypatch):
    primary = o.ReleaseObservationError("PRIMARY_REFUSAL")
    rig = CommandRig(monkeypatch, read_error=primary, cleanup_error=OSError("cleanup failed"))
    with pytest.raises(o.ReleaseObservationError) as caught:
        o._command(o.peer._SYSCTL_OSRELEASE_ARGV, o._Budget(2_000_000_000))
    assert caught.value is primary
    assert rig.killed
    assert sorted(map(str, rig.closed)) == ["10", "11", "selector"]


def test_command_output_overflow_kills_owned_child(monkeypatch):
    rig = CommandRig(monkeypatch, out=b"x" * 65537)
    with pytest.raises(o.ReleaseObservationError, match="OUTPUT_TOO_LARGE"):
        o._command(o.peer._SYSCTL_OSRELEASE_ARGV, o._Budget(2_000_000_000))
    assert rig.killed
    assert len(rig.closed) == 3


def _trusted_read_rig(monkeypatch):
    """Keep the inherited read/close bodies real; replace only native seams."""
    info = SimpleNamespace(st_mode=stat.S_IFREG | 0o444, st_nlink=1,
                           st_gid=0, st_size=1)
    monkeypatch.setattr(o.peer, "_open_trusted", lambda *a, **k: (44, info, info))
    monkeypatch.setattr(o.peer, "_object_identity", lambda info: (1,))
    monkeypatch.setattr(o.peer, "_lstat", lambda path: info)
    monkeypatch.setattr(o.os, "fstat", lambda fd: info)


@pytest.mark.parametrize("outer_handler", [False, True])
@pytest.mark.parametrize("event", ["rollback", "expiry"])
def test_sampled_budget_violation_survives_clock_recovery(world, monkeypatch, outer_handler, event):
    _trusted_read_rig(monkeypatch)
    closed = []
    monkeypatch.setattr(o.os, "close", closed.append)
    calls = []
    original = o._content_snapshot
    original_time = world.now
    def read(fd, size):
        calls.append(fd)
        world.now = ((original_time - 1 if event == "rollback" else world.deadline)
                     if len(calls) == 1 else original_time)
        return b"x" if len(calls) == 1 else b""
    monkeypatch.setattr(o.os, "read", read)
    def content(budget):
        budget.call(o.peer._read_trusted_bytes, "/fixed", budget=budget,
                    maximum=10, expected_mode=0o444, expected_gid=0)
        return original(budget)
    monkeypatch.setattr(o, "_content_snapshot", content)
    code = "CLOCK_ROLLBACK" if event == "rollback" else "DEADLINE_EXCEEDED"
    def capture():
        with pytest.raises(o.ReleaseObservationError, match=code):
            world.capture()
    if outer_handler:
        try:
            raise RuntimeError("unrelated ambient exception")
        except RuntimeError:
            capture()
    else:
        capture()
    assert closed == [44]


@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_real_read_budget_failure_precedes_descriptor_cleanup(world, monkeypatch, cleanup_failure):
    _trusted_read_rig(monkeypatch)
    close_attempts = []
    def read(fd, size):
        world.now = world.deadline
        return b"x"
    def close(fd):
        close_attempts.append(fd)
        if cleanup_failure:
            raise OSError("SYNTHETIC_CLOSE_DETAIL")
    monkeypatch.setattr(o.os, "read", read)
    monkeypatch.setattr(o.os, "close", close)
    def content(budget):
        budget.call(o.peer._read_trusted_bytes, "/fixed", budget=budget,
                    maximum=10, expected_mode=0o444, expected_gid=0)
    monkeypatch.setattr(o, "_content_snapshot", content)
    with pytest.raises(o.ReleaseObservationError, match="DEADLINE_EXCEEDED") as caught:
        world.capture()
    assert close_attempts == [44]
    assert "SYNTHETIC_CLOSE_DETAIL" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("ambient_typed", [False, True])
def test_native_conversion_hides_context_without_adopting_ambient_refusal(world, monkeypatch, ambient_typed):
    def fail(*args, **kwargs):
        raise OSError("SYNTHETIC_PRIVATE_NATIVE_DETAIL")
    monkeypatch.setattr(o, "_command", fail)
    ambient = o.ReleaseObservationError("UNRELATED_TYPED_ERROR")
    def capture():
        with pytest.raises(o.ReleaseObservationError) as caught:
            world.capture()
        assert caught.value.code == "RELEASE_OBSERVATION_UNAVAILABLE"
        assert caught.value is not ambient
        formatted = "".join(traceback.format_exception(caught.value))
        assert "SYNTHETIC_PRIVATE_NATIVE_DETAIL" not in formatted
        assert "UNRELATED_TYPED_ERROR" not in formatted
    if ambient_typed:
        try:
            raise ambient
        except o.ReleaseObservationError:
            capture()
    else:
        capture()


def test_first_typed_refusal_identity_survives_real_descriptor_close_failure(world, monkeypatch):
    _trusted_read_rig(monkeypatch)
    primary = o.ReleaseObservationError("RELEASE_OBSERVATION_DEADLINE_EXCEEDED")
    def read(fd, size):
        raise primary
    def close(fd):
        raise OSError("SYNTHETIC_CLEANUP_DETAIL")
    monkeypatch.setattr(o.os, "read", read)
    monkeypatch.setattr(o.os, "close", close)
    def content(budget):
        budget.call(o.peer._read_trusted_bytes, "/fixed", budget=budget,
                    maximum=10, expected_mode=0o444, expected_gid=0)
    monkeypatch.setattr(o, "_content_snapshot", content)
    with pytest.raises(o.ReleaseObservationError) as caught:
        world.capture()
    assert caught.value is primary
    assert "SYNTHETIC_CLEANUP_DETAIL" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("endpoint", [101, 2**53 + 1, 2**63 - 1])
def test_current_peer_receives_exact_original_deadline(monkeypatch, endpoint):
    monkeypatch.setattr(o.time, "monotonic_ns", lambda: 100)
    budget = o._Budget(endpoint)
    assert type(budget.caller_deadline) is int
    assert budget.caller_deadline == endpoint
    assert budget.call(lambda: budget.caller_deadline) == endpoint


@pytest.mark.parametrize("layers", [1, 2, 4, 8])
@pytest.mark.parametrize("typed_cleanup", [False, True])
def test_nested_cleanup_preserves_first_refusal_at_every_boundary(monkeypatch, layers, typed_cleanup):
    monkeypatch.setattr(o.time, "monotonic_ns", lambda: 1)
    budget = o._Budget(100)
    primary = o.ReleaseObservationError("RELEASE_OBSERVATION_OUTPUT_TOO_LARGE")
    secondary = (o.ReleaseObservationError("RELEASE_OBSERVATION_COMMAND_TIMEOUT")
                 if typed_cleanup else RuntimeError("SYNTHETIC_SECONDARY_DETAIL"))
    def operation():
        try:
            try:
                raise primary
            finally:
                raise secondary
        finally:
            raise OSError("SYNTHETIC_DESCRIPTOR_DETAIL")
    def nested(depth):
        if depth == 0:
            return operation()
        return budget.call(nested, depth - 1)
    with pytest.raises(o.ReleaseObservationError) as caught:
        nested(layers)
    assert caught.value is primary
    rendered = "".join(traceback.format_exception(caught.value))
    assert "SYNTHETIC_" not in rendered
    assert "COMMAND_TIMEOUT" not in rendered


def test_failed_observation_cannot_resume_but_new_budget_is_independent(monkeypatch):
    now = [1]
    monkeypatch.setattr(o.time, "monotonic_ns", lambda: now[0])
    budget = o._Budget(100)
    primary = o.ReleaseObservationError("RELEASE_OBSERVATION_OUTPUT_TOO_LARGE")
    def refuse():
        raise primary
    with pytest.raises(o.ReleaseObservationError) as first:
        budget.call(refuse)
    assert first.value is primary
    invoked = []
    now[0] = 100
    with pytest.raises(o.ReleaseObservationError) as later:
        budget.call(lambda: invoked.append("must not execute"))
    assert later.value is primary
    assert invoked == []
    independent = o._Budget(200)
    assert independent.call(lambda: "fresh observation") == "fresh observation"


def test_current_peer_positive_trusted_read_uses_observer_budget(monkeypatch):
    monkeypatch.setattr(o.time, "monotonic_ns", lambda: 1)
    _trusted_read_rig(monkeypatch)
    chunks = iter([b"x", b""])
    closed = []
    monkeypatch.setattr(o.os, "read", lambda fd, size: next(chunks))
    monkeypatch.setattr(o.os, "close", closed.append)
    budget = o._Budget(2**53 + 1)
    data, info = budget.call(o.peer._read_trusted_bytes, "/fixed", budget=budget,
                             maximum=10, expected_mode=0o444, expected_gid=0)
    assert data == b"x"
    assert info.st_size == 1
    assert closed == [44]


@pytest.mark.parametrize("replacement", [None, True, 99, 102])
def test_peer_deadline_protocol_cannot_replace_or_disable_endpoint(monkeypatch, replacement):
    monkeypatch.setattr(o.time, "monotonic_ns", lambda: 1)
    budget = o._Budget(101)
    budget.caller_deadline = 101
    with pytest.raises(o.ReleaseObservationError, match="DEADLINE_INVALID"):
        budget.caller_deadline = replacement
    assert budget.caller_deadline == budget.endpoint == 101

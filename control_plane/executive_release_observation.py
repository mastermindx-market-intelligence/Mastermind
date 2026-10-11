"""Private read-only release observation; no publication or effect authority.

Native calls are fenced by one endpoint, but synchronous kernel/filesystem
operations cannot be preempted. Drift is checked at observed boundaries; this
is not a continuous history monitor and cannot prove an unobserved transition.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
import re
import selectors
import subprocess
import sys
import time

from control_plane import executive_installed_peer as peer
from control_plane.executive_release_contract import canonical_release_bytes

__all__ = ()
_ROLES = ("control", "worker", "relay", "gateway", "broker")
_CONTENT_DOMAIN = b"MMX_EXECUTIVE_RELEASE_SERVICE_CONTENT_V1\0"
_TARGET_DOMAIN = b"MMX_EXECUTIVE_RELEASE_TARGET_OBSERVATION_V1\0"
_EXECUTABLE_DOMAIN = b"MMX_EXECUTIVE_RELEASE_EXECUTABLE_CLOSURE_V1\0"
_ROOT = "/Library/Application Support/MastermindExecutive"
_RELEASES = _ROOT + "/releases/"
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class ReleaseObservationError(ValueError):
    """A closed nonsecret refusal; underlying exception text is never exposed."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _refuse(code="RELEASE_OBSERVATION_UNAVAILABLE"):
    raise ReleaseObservationError(code) from None


def _first_refusal(error, ambient):
    """Recover our primary refusal if an inherited finally replaced it.

    Follow only the actual exception context, stopping at the caller's active
    exception. Never adopt a refusal belonging to an unrelated outer handler.
    This does not turn failed descriptor cleanup into proven closure.
    """
    seen = set()
    primary = None
    while error is not None and error is not ambient and id(error) not in seen:
        if len(seen) >= 64:
            break
        seen.add(id(error))
        if isinstance(error, ReleaseObservationError):
            primary = error
        error = error.__context__
    return primary


def _digest(domain, value):
    return hashlib.sha256(domain + canonical_release_bytes(value)).hexdigest()


class _Budget:
    def __init__(self, endpoint):
        if type(endpoint) is not int or not 0 < endpoint < 2**63:
            _refuse("RELEASE_OBSERVATION_DEADLINE_INVALID")
        self.endpoint = endpoint
        self.primary_refusal = None
        self.started = self.last = time.monotonic_ns()
        self.violation = None
        self.check(force=True)

    @property
    def caller_deadline(self):
        # Current trusted-reader helpers fence the original absolute endpoint.
        return self.endpoint

    @caller_deadline.setter
    def caller_deadline(self, value):
        # Permit protocol adapters to assert the same endpoint, never replace it.
        if type(value) is not int or value != self.endpoint:
            _refuse("RELEASE_OBSERVATION_DEADLINE_INVALID")

    def check(self, _code=None, *, force=False):
        now = time.monotonic_ns()
        code = ("RELEASE_OBSERVATION_CLOCK_ROLLBACK" if now < self.last else
                "RELEASE_OBSERVATION_DEADLINE_EXCEEDED" if now >= self.endpoint else None)
        self.last = max(now, self.last)
        if code and self.violation is None:
            self.violation = ReleaseObservationError(code)
        # Existing descriptor helpers call check() from finally. Do not replace
        # their first failure with a cleanup deadline. Entry and return fences
        # are force=True even when invoked from a caller's exception handler.
        # Latch every invalid sample: an ambient handler may defer raising, but
        # a recovered clock can never make a successful boundary valid again.
        refusal = self.primary_refusal or self.violation
        if refusal is not None and (force or sys.exception() is None):
            raise refusal from None
        return max(0, self.endpoint - now) / 1_000_000_000

    def remaining(self):
        return self.check(force=True)

    def call(self, function, *args, **kwargs):
        self.check(force=True)
        ambient = sys.exception()
        try:
            result = function(*args, **kwargs)
        except Exception as error:
            if self.primary_refusal is None:
                self.primary_refusal = _first_refusal(error, ambient)
            if self.primary_refusal is not None:
                # Re-raising rewires __context__; retain the recovered object
                # before that happens so outer boundaries cannot reorder it.
                raise self.primary_refusal from None
            raise
        self.check(force=True)
        return result


@dataclass(frozen=True, slots=True)
class _Spec:
    role: str
    label: str
    username: str
    group: str
    uid: int
    config: str
    config_gid: int
    config_mode: int
    wrapper: str

    @property
    def plist(self):
        return "/Library/LaunchDaemons/" + self.label + ".plist"

    @property
    def service(self):
        return "system/" + self.label


_SPECS = (
    _Spec("control", "com.mastermind.executive.control", "_mastermind_exec", "_mastermind_exec", 450, _ROOT + "/config/control.json", 450, 0o440, "scripts/executive_os_phase1c_control_wrapper.py"),
    _Spec("worker", "com.mastermind.executive.worker.codex", "_mastermind_worker", "_mastermind_worker", 451, _ROOT + "/config/worker-codex.json", 451, 0o440, "scripts/executive_os_phase1c_worker.py"),
    _Spec("relay", "com.mastermind.executive.sol-state-relay", "_mastermind_sol_relay", "_mastermind_sol_relay", 452, _ROOT + "/config/sol-state-relay.json", 452, 0o440, "scripts/c1_sol_state_relay.py"),
    _Spec("gateway", "com.mastermind.executive.mcp", "_mastermind_executive_mcp", "_mastermind_executive_mcp", 458, _ROOT + "/config/executive-mcp.json", 0, 0o644, "ops/executive_os/executive_mcp_entry.py"),
    _Spec("broker", "com.mastermind.executive.privileged", "root", "wheel", 0, _ROOT + "/config/privileged-broker.json", 0, 0o400, "scripts/executive_os_privileged_broker.py"),
)
_COMMANDS = (peer._SYSCTL_OSRELEASE_ARGV, peer._SYSCTL_BOOT_ID_ARGV) + tuple(
    ("/bin/launchctl", "print", spec.service) for spec in _SPECS)


@dataclass(frozen=True, slots=True)
class _InstalledContent:
    schema: str
    role: str
    service_label: str
    service_uid: int
    plist_path: str
    config_path: str
    executable_path: str
    wrapper_relative: str
    release_commit: str
    release_tree: str
    installed_manifest_digest: str
    configuration_digest: str
    plist_digest: str
    wrapper_digest: str
    executable_closure_digest: str


@dataclass(frozen=True, slots=True)
class _RoleObservation:
    role: str
    state: str
    service_generation_digest: str
    content: _InstalledContent
    evidence: str
    pid: int | None = None
    unique_id: int | None = None
    pidversion: int | None = None


@dataclass(frozen=True, slots=True)
class _Freshness:
    started_monotonic_ns: int
    completed_monotonic_ns: int
    deadline_monotonic_ns: int


@dataclass(frozen=True, slots=True)
class _ReleaseObservation:
    boot_id: str
    roles: tuple[_RoleObservation, ...]
    target_observation_digest: str
    freshness: _Freshness


def _command(argv, budget):
    """Closed read-only commands, bounded pipes and owned-child cleanup."""
    if type(argv) is not tuple or argv not in _COMMANDS:
        _refuse("RELEASE_OBSERVATION_COMMAND_REFUSED")
    budget.check(force=True)
    end = min(budget.endpoint, time.monotonic_ns() + 3_000_000_000)
    process = None
    selector = None
    failure = None
    result = None
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=peer._LAUNCHD_ENVIRONMENT, close_fds=True)
        selector = selectors.DefaultSelector()
        output = [bytearray(), bytearray()]
        for index, stream in enumerate((process.stdout, process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, index)
        while selector.get_map():
            budget.check(force=True)
            remaining = (end - time.monotonic_ns()) / 1_000_000_000
            if remaining <= 0:
                _refuse("RELEASE_OBSERVATION_COMMAND_TIMEOUT")
            for key, _ in selector.select(min(remaining, .05)):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    output[key.data].extend(chunk)
                    if sum(map(len, output)) > 65536:
                        _refuse("RELEASE_OBSERVATION_OUTPUT_TOO_LARGE")
        remaining = min(budget.remaining(), (end - time.monotonic_ns()) / 1_000_000_000)
        if remaining <= 0:
            _refuse("RELEASE_OBSERVATION_COMMAND_TIMEOUT")
        result = (process.wait(timeout=remaining), bytes(output[0]), bytes(output[1]))
    except BaseException as error:
        failure = error
    finally:
        cleanup = []
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=.5)
            except BaseException as error:
                cleanup.append(error)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException as error:
                        cleanup.append(error)
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                cleanup.append(error)
        if failure is None and cleanup:
            failure = cleanup[0]
    if failure is not None:
        raise failure
    budget.check(force=True)
    return result


def _line(argv, budget):
    rc, out, err = budget.call(_command, argv, budget)
    if type(rc) is not int or rc != 0 or type(err) is not bytes or err or type(out) is not bytes or not out.endswith(b"\n"):
        _refuse()
    try:
        value = out[:-1].decode("ascii")
    except UnicodeError:
        _refuse()
    if not value or len(value) > 128 or "\n" in value or "\r" in value:
        _refuse()
    return value


def _boot(budget):
    value = _line(peer._SYSCTL_BOOT_ID_ARGV, budget).lower()
    if peer._LAUNCHD_UUID_PATTERN.fullmatch(value) is None or value == "00000000-0000-0000-0000-000000000000":
        _refuse("RELEASE_OBSERVATION_BOOT_UNQUALIFIED")
    return value


@dataclass(frozen=True, slots=True)
class _Artifact:
    path: str
    mode: int
    gid: int
    raw: bytes
    identity: tuple
    ancestors: tuple

    @property
    def digest(self):
        return hashlib.sha256(self.raw).hexdigest()


def _artifact(path, mode, gid, budget):
    ancestors = budget.call(peer._observe_ancestors, path, budget)
    raw, info = budget.call(peer._read_trusted_bytes, path, budget=budget,
                            maximum=peer._MAX_READ_BYTES, expected_mode=mode,
                            expected_gid=gid)
    if budget.call(peer._observe_ancestors, path, budget) != ancestors:
        _refuse("RELEASE_OBSERVATION_CONTENT_DRIFT")
    return _Artifact(path, mode, gid, raw, peer._object_identity(info), ancestors)


def _profile(spec):
    return (peer._EXPECTED_PLIST_PROFILES[spec.role] if spec.role in ("control", "gateway")
            else _EXTRA_PROFILES[spec.role])


def _config_join(spec, document, release):
    if spec.role == "control":
        valid = document.get("proof_base_sha") == release and type(document.get("control_uid")) is int and document["control_uid"] == 450
    elif spec.role == "worker":
        valid = (document.get("schema_version") in ("mastermind.executive_worker_broker_config/v4", "mastermind.executive_worker_broker_config/v5")
                 and document.get("worker_id") == "codex-01" and document.get("worker_user") == spec.username
                 and all(type(document.get(k)) is int and document[k] == v for k, v in (("worker_uid", 451), ("worker_gid", 451), ("control_uid", 450))))
    elif spec.role == "relay":
        valid = document.get("relay_version") == release and document.get("schema") == _RELAY_CONFIG_SCHEMA
    elif spec.role == "gateway":
        valid = (document.get("schema") == peer._GATEWAY_CONFIG_SCHEMA and document.get("release_sha") == release
                 and type(document.get("service_uid")) is int and document["service_uid"] == 458
                 and document.get("executive_mcp_profile") in peer._GATEWAY_MCP_PROFILES)
    else:
        valid = document.get("schema") == "mastermind.executive_privileged_broker_config.v1" and document.get("release_root") == _RELEASES + release
    if not valid:
        _refuse("RELEASE_OBSERVATION_CONFIG_JOIN_REFUSED")


@dataclass(frozen=True, slots=True)
class _ContentSnapshot:
    contents: tuple
    argvs: tuple
    artifacts: tuple
    release: object
    runtime: object
    network: object


def _content_snapshot(budget):
    artifacts, plists, configs, releases = [], [], [], []
    for spec in _SPECS:
        plist = budget.call(_artifact, spec.plist, 0o644, 0, budget)
        document = peer._load_strict_plist(plist.raw, code="SERVICE_PLIST_MALFORMED")
        found = []
        if not peer._profile_matches(_profile(spec), document, found) or len(found) != 1:
            _refuse("RELEASE_OBSERVATION_PLIST_REFUSED")
        release = found[0]
        if _HEX40.fullmatch(release) is None or release == "0" * 40:
            _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
        config = budget.call(_artifact, spec.config, spec.config_mode, spec.config_gid, budget)
        _config_join(spec, peer._load_strict_json(config.raw, code="SERVICE_CONFIG_MALFORMED"), release)
        artifacts.extend((plist, config))
        plists.append((plist, tuple(document["ProgramArguments"])))
        configs.append(config)
        releases.append(release)
    if len(set(releases)) != 1:
        _refuse("RELEASE_OBSERVATION_MIXED_CONTENT")
    release = budget.call(peer._verify_release, peer._ROLE_TOPOLOGIES["control"], releases[0], budget)
    manifest = budget.call(_artifact, _RELEASES + releases[0] + "/.executive-release-manifest.json", 0o444, 0, budget)
    if manifest.digest != release.manifest_digest:
        _refuse("RELEASE_OBSERVATION_CONTENT_DRIFT")
    tree = peer._load_strict_json(manifest.raw, code="SERVICE_MANIFEST_MALFORMED")["tree_sha"]
    if type(tree) is not str or _HEX40.fullmatch(tree) is None or tree == "0" * 40:
        _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
    artifacts.append(manifest)
    runtime = budget.call(peer._verify_python_runtime, budget)
    network = budget.call(peer._verify_network_closure, budget)
    wrapper_rows = {row[0]: row for row in release.digests}
    contents = []
    for spec, (plist, argv), config in zip(_SPECS, plists, configs, strict=True):
        row = wrapper_rows.get(spec.wrapper)
        if row is None or row[1] != "file" or _HEX64.fullmatch(str(row[6])) is None:
            _refuse("RELEASE_OBSERVATION_WRAPPER_REFUSED")
        closure = {"python_launcher": runtime.launcher_digest, "python_dylib": runtime.dylib_digest, "python_main": runtime.main_digest}
        if spec.role == "gateway":
            closure["network"] = network.aggregate
        contents.append(_InstalledContent("mastermind.executive_release_service_content/v1",
            spec.role, spec.label, spec.uid, spec.plist, spec.config, argv[0], spec.wrapper,
            releases[0], tree, manifest.digest, config.digest, plist.digest, row[6], _digest(_EXECUTABLE_DOMAIN, closure)))
    return _ContentSnapshot(tuple(contents), tuple(x[1] for x in plists), tuple(artifacts), release, runtime, network)


def _recheck_content(snapshot, budget):
    for before in snapshot.artifacts:
        if budget.call(_artifact, before.path, before.mode, before.gid, budget) != before:
            _refuse("RELEASE_OBSERVATION_CONTENT_DRIFT")
    budget.call(peer._recheck_release, snapshot.release, budget)
    budget.call(peer._recheck_python_runtime, snapshot.runtime, budget)
    budget.call(peer._recheck_network_closure, snapshot.network, budget)


def _parse_service(spec, rc, raw, stderr, argv, release):
    if type(rc) is not int or type(raw) is not bytes or type(stderr) is not bytes or len(raw) + len(stderr) > 65536:
        _refuse("RELEASE_OBSERVATION_SERVICE_REFUSED")
    absent = ('Could not find service "' + spec.label + '" in domain for system\n').encode("ascii")
    absent_prefixed = b"Bad request.\n" + absent
    if rc == 113 and not raw and stderr in (absent, absent_prefixed):
        return "UNLOADED", None
    if rc != 0 or stderr:
        _refuse("RELEASE_OBSERVATION_SERVICE_UNAVAILABLE")
    lines = peer._launchd_lines(raw)
    fields, seen, arguments, stack = {}, set(), [], []
    closed = False
    args_closed = False
    for index, line in enumerate(lines):
        depth, body = peer._launchd_indent(line)
        if depth > 8 or body[:1] == " " or (body and not peer._launchd_is_safe_text(body)):
            _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
        if index == 0:
            if depth or body != spec.service + " = {":
                _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
            stack.append((0, False))
            continue
        if closed or not stack:
            _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
        if not body:
            continue
        if body == "}":
            if depth != stack[-1][0]:
                _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
            _, is_args = stack.pop()
            args_closed |= is_args
            closed = not stack
            continue
        if depth != stack[-1][0] + 1:
            _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
        if stack[-1][1]:
            if any(x in body for x in ("{", "}", " = ", " => ")) or body.strip() != body or len(arguments) >= 64:
                _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
            arguments.append(body)
            continue
        opener = body.endswith(" = {")
        if depth != 1:
            nested_key = body[:-4] if opener else body.partition(" = ")[0]
            if spec is _SPECS[-1] and nested_key in ("username", "group"):
                _refuse("RELEASE_OBSERVATION_SERVICE_BINDING_REFUSED")
            if opener:
                stack.append((depth, False))
            elif "{" in body or "}" in body:
                _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
            continue
        key = body[:-4] if opener else body.partition(" = ")[0]
        if peer._LAUNCHD_KEY_PATTERN.fullmatch(key) is None or key in seen:
            _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
        seen.add(key)
        if opener:
            stack.append((depth, key == "arguments"))
        else:
            _, sep, value = body.partition(" = ")
            if not sep or value.strip() != value or not peer._launchd_is_safe_text(value):
                _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
            fields[key] = value
    if not closed or stack or not args_closed or tuple(arguments) != argv:
        _refuse("RELEASE_OBSERVATION_SERVICE_MALFORMED")
    # launchd omits the default root/wheel identity for this fixed broker.
    # Its root-owned fixed plist was already profile-qualified by
    # _content_snapshot and is rechecked before returning any observation.
    # A structured/malformed identity key is present in `seen`, not omitted.
    broker_identity_omitted = (
        spec is _SPECS[-1] and spec.role == "broker"
        and (spec.username, spec.group, spec.uid) == ("root", "wheel", 0)
        and "username" not in seen and "group" not in seen
    )
    expected = {"path": spec.plist, "type": "LaunchDaemon", "domain": "system",
                "program": argv[0], "working directory": _RELEASES + release}
    if not broker_identity_omitted:
        expected["username"] = spec.username
        expected["group"] = spec.group
    if any(fields.get(key) != value for key, value in expected.items()):
        _refuse("RELEASE_OBSERVATION_SERVICE_BINDING_REFUSED")
    if fields.get("state") == "not running" and "pid" not in seen:
        return "LOADED_IDLE", None
    pid = fields.get("pid", "")
    if fields.get("state") != "running" or re.fullmatch(r"[1-9][0-9]{0,9}", pid) is None or int(pid) > 2**31 - 1:
        _refuse("RELEASE_OBSERVATION_SERVICE_STATE_REFUSED")
    return "RUNNING", int(pid)


def _instance(pid, budget):
    result = budget.call(peer._observe_process_instance, pid)
    if (type(result.unique_id) is not int or not 0 < result.unique_id < 2**64
            or type(result.pidversion) is not int or not 0 < result.pidversion < 2**31):
        _refuse("RELEASE_OBSERVATION_PROCESS_REFUSED")
    return result.unique_id, result.pidversion


def _service(spec, content, argv, budget):
    rc, raw, stderr = budget.call(_command, ("/bin/launchctl", "print", spec.service), budget)
    state, pid = _parse_service(spec, rc, raw, stderr, argv, content.release_commit)
    unique, version = budget.call(_instance, pid, budget) if state == "RUNNING" else (None, None)
    return _RoleObservation(spec.role, state, _digest(_CONTENT_DOMAIN, asdict(content)), content,
                           "launchctl-exact-not-found-113" if state == "UNLOADED" else "launchctl-qualified-loaded-job",
                           pid, unique, version)


def _validate_roles(roles):
    if type(roles) is not tuple or tuple(x.role for x in roles) != _ROLES:
        _refuse("RELEASE_OBSERVATION_ROLE_SET_REFUSED")
    contexts = set()
    for spec, record in zip(_SPECS, roles, strict=True):
        content = record.content
        if type(record) is not _RoleObservation or type(content) is not _InstalledContent:
            _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
        if (content.role != spec.role or content.service_label != spec.label or type(content.service_uid) is not int
                or content.service_uid != spec.uid or content.plist_path != spec.plist or content.config_path != spec.config
                or content.wrapper_relative != spec.wrapper or content.schema != "mastermind.executive_release_service_content/v1"):
            _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
        launcher = peer._NETWORK_RUNTIME_LAUNCHER if spec.role == "gateway" else peer._PYTHON_LAUNCHER
        if content.executable_path != launcher:
            _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
        for name in ("release_commit", "release_tree"):
            value = getattr(content, name)
            if type(value) is not str or _HEX40.fullmatch(value) is None or value == "0" * 40:
                _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
        for name in ("installed_manifest_digest", "configuration_digest", "plist_digest", "wrapper_digest", "executable_closure_digest"):
            value = getattr(content, name)
            if type(value) is not str or _HEX64.fullmatch(value) is None or value == "0" * 64:
                _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
        if record.service_generation_digest != _digest(_CONTENT_DOMAIN, asdict(content)):
            _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
        contexts.add((content.release_commit, content.release_tree, content.installed_manifest_digest))
        if record.state == "RUNNING":
            if any(type(x) is not int or x <= 0 for x in (record.pid, record.unique_id, record.pidversion)):
                _refuse("RELEASE_OBSERVATION_PROCESS_REFUSED")
            if record.pid >= 2**31 or record.unique_id >= 2**64 or record.pidversion >= 2**31:
                _refuse("RELEASE_OBSERVATION_PROCESS_REFUSED")
        elif record.state not in ("LOADED_IDLE", "UNLOADED") or any(x is not None for x in (record.pid, record.unique_id, record.pidversion)):
            _refuse("RELEASE_OBSERVATION_SERVICE_STATE_REFUSED")
        expected_evidence = "launchctl-exact-not-found-113" if record.state == "UNLOADED" else "launchctl-qualified-loaded-job"
        if record.evidence != expected_evidence:
            _refuse("RELEASE_OBSERVATION_SERVICE_STATE_REFUSED")
    if len(contexts) != 1:
        _refuse("RELEASE_OBSERVATION_MIXED_CONTENT")


def _observe_release(*, deadline_monotonic_ns):
    """One qualified five-role snapshot; only a private absolute endpoint enters."""
    try:
        budget = _Budget(deadline_monotonic_ns)
        if sys.platform != "darwin":
            _refuse("RELEASE_OBSERVATION_PLATFORM_UNSUPPORTED")
        if peer._LAUNCHD_KERNEL_PATTERN.fullmatch(_line(peer._SYSCTL_OSRELEASE_ARGV, budget)) is None:
            _refuse("RELEASE_OBSERVATION_PLATFORM_UNSUPPORTED")
        boot = budget.call(_boot, budget)
        snapshot = budget.call(_content_snapshot, budget)
        if len(snapshot.contents) != 5 or len(snapshot.argvs) != 5:
            _refuse("RELEASE_OBSERVATION_ROLE_SET_REFUSED")
        roles = tuple(budget.call(_service, spec, content, argv, budget)
                      for spec, content, argv in zip(_SPECS, snapshot.contents, snapshot.argvs, strict=True))
        _validate_roles(roles)
        budget.call(_recheck_content, snapshot, budget)
        for spec, content, argv, first in zip(_SPECS, snapshot.contents, snapshot.argvs, roles, strict=True):
            if budget.call(_service, spec, content, argv, budget) != first:
                _refuse("RELEASE_OBSERVATION_SERVICE_DRIFT")
        for record in roles:
            if record.state == "RUNNING" and budget.call(_instance, record.pid, budget) != (record.unique_id, record.pidversion):
                _refuse("RELEASE_OBSERVATION_PROCESS_DRIFT")
        if budget.call(_boot, budget) != boot:
            _refuse("RELEASE_OBSERVATION_BOOT_DRIFT")
        rows = []
        for record in roles:
            row = {"role": record.role, "state": record.state, "service_generation_digest": record.service_generation_digest}
            if record.state == "RUNNING":
                row.update(pid=record.pid, unique_id=record.unique_id, pidversion=record.pidversion)
            rows.append(row)
        target = _digest(_TARGET_DOMAIN, {"schema": "mastermind.executive_release_target_observation/v1", "boot_id": boot, "roles": rows})
        budget.check(force=True)
        completed = budget.last
        return _ReleaseObservation(boot, roles, target, _Freshness(budget.started, completed, budget.endpoint))
    except ReleaseObservationError as error:
        raise error from None
    except Exception:
        _refuse()


# Exact installer-derived private profiles; these are not caller-selectable.
_RELAY_CONFIG_SCHEMA = 'mastermind.sol_state_relay_config.v1'
_EXTRA_PROFILES = {'broker': {'AbandonProcessGroup': False,
            'EnvironmentVariables': {'HOME': '/var/empty',
                                     'LANG': 'C',
                                     'LC_ALL': 'C',
                                     'NO_COLOR': '1',
                                     'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                                     'PYTHONUNBUFFERED': '1',
                                     'TZ': 'UTC'},
            'ExitTimeOut': 15,
            'GroupName': 'wheel',
            'HardResourceLimits': {'Core': 0, 'FileSize': 67108864},
            'Label': 'com.mastermind.executive.privileged',
            'ProcessType': 'Background',
            'ProgramArguments': ['/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12',
                                 '-I',
                                 '-S',
                                 '-B',
                                 '{release}/scripts/executive_os_privileged_broker.py',
                                 'serve',
                                 '--config',
                                 '/Library/Application '
                                 'Support/MastermindExecutive/config/privileged-broker.json'],
            'Sockets': {'PrivilegedActions': {'SockPassive': True,
                                              'SockPathGroup': 453,
                                              'SockPathMode': 432,
                                              'SockPathName': '/var/run/mastermind-executive/privileged.sock',
                                              'SockPathOwner': 450,
                                              'SockType': 'stream'}},
            'StandardErrorPath': '/var/log/mastermind-executive/privileged/stderr.log',
            'StandardOutPath': '/var/log/mastermind-executive/privileged/stdout.log',
            'ThrottleInterval': 10,
            'Umask': 63,
            'UserName': 'root',
            'WorkingDirectory': '{release}'},
 'relay': {'AbandonProcessGroup': False,
           'EnvironmentVariables': {'HOME': '/var/db/mastermind-executive/sol-state-relay/home',
                                    'LANG': 'C.UTF-8',
                                    'LC_ALL': 'C.UTF-8',
                                    'NO_COLOR': '1',
                                    'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                                    'PYTHONUNBUFFERED': '1',
                                    'TZ': 'UTC'},
           'ExitTimeOut': 15,
           'GroupName': '_mastermind_sol_relay',
           'HardResourceLimits': {'Core': 0, 'FileSize': 16777216},
           'KeepAlive': True,
           'Label': 'com.mastermind.executive.sol-state-relay',
           'ProcessType': 'Background',
           'ProgramArguments': ['/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12',
                                '-I',
                                '-S',
                                '-B',
                                '{release}/scripts/c1_sol_state_relay.py',
                                '--config',
                                '/Library/Application '
                                'Support/MastermindExecutive/config/sol-state-relay.json'],
           'RunAtLoad': True,
           'StandardErrorPath': '/var/log/mastermind-executive/sol-state-relay/stderr.log',
           'StandardOutPath': '/var/log/mastermind-executive/sol-state-relay/stdout.log',
           'ThrottleInterval': 10,
           'Umask': 63,
           'UserName': '_mastermind_sol_relay',
           'WorkingDirectory': '{release}'},
 'worker': {'AbandonProcessGroup': False,
            'EnvironmentVariables': {'HOME': '/var/db/mastermind-executive/workers/codex-01/provider-home',
                                     'LANG': 'C.UTF-8',
                                     'LC_ALL': 'C.UTF-8',
                                     'NO_COLOR': '1',
                                     'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                                     'PYTHONUNBUFFERED': '1',
                                     'TZ': 'UTC'},
            'ExitTimeOut': 15,
            'GroupName': '_mastermind_worker',
            'HardResourceLimits': {'Core': 0, 'FileSize': 67108864},
            'InitGroups': False,
            'KeepAlive': True,
            'Label': 'com.mastermind.executive.worker.codex',
            'ProcessType': 'Interactive',
            'ProgramArguments': ['/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12',
                                 '-I',
                                 '-S',
                                 '-B',
                                 '{release}/scripts/executive_os_phase1c_worker.py',
                                 'serve',
                                 '--config',
                                 '/Library/Application '
                                 'Support/MastermindExecutive/config/worker-codex.json'],
            'RunAtLoad': True,
            'Sockets': {'WorkerBroker': {'SockPassive': True,
                                         'SockPathGroup': 450,
                                         'SockPathMode': 384,
                                         'SockPathName': '/var/run/mastermind-executive/worker.sock',
                                         'SockPathOwner': 450,
                                         'SockType': 'stream'}},
            'StandardErrorPath': '/var/log/mastermind-executive/worker/stderr.log',
            'StandardOutPath': '/var/log/mastermind-executive/worker/stdout.log',
            'ThrottleInterval': 10,
            'Umask': 63,
            'UserName': '_mastermind_worker',
            'WorkingDirectory': '{release}'}}

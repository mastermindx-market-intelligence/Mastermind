"""Fixed Chrome-user Workbench lifecycle beneath the existing private-service owner.

Stage consumes a qualified sealed runtime and an enrolled configuration. It does
not provision source, dependencies, credentials, leases, grants or browser consent.
Every launch/signal/unregistration is issued at most once per recorded attempt.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import pwd
import re
import secrets
import stat
import time

try:
    from . import private_service as owner
except ImportError:  # Existing direct private_service.py invocation.
    import private_service as owner

LABEL = "com.mastermind.workbench-browser"
PLAN_SCHEMA = "mastermind.workbench_host_plan.v1"
MANIFEST_SCHEMA = "mastermind.workbench_host_install.v1"
STATE_SCHEMA = "mastermind.workbench_host_lifecycle.v1"
STAGE_SCHEMA = "mastermind.workbench_host_stage.v1"
PHASES = {"IDLE", "BOOTSTRAP_ISSUED", "KICKSTART_ISSUED", "RUNNING",
          "STOP_ISSUED", "CLEAN_EXIT", "BOOTOUT_ISSUED", "STOPPED", "HOLD"}
STATE_KEYS = {"schema", "install_sha256", "attempt_id", "phase", "boot_session_id",
              "process", "runs", "exit_code", "error"}
PLAN_KEYS = {"schema", "service_uid", "release_sha", "runtime", "config",
             "config_sha256", "persistent", "dependencies", "plist", "previous_install_sha256"}
PROCESS_KEYS = {"pid", "process_start_identity", "service_uid", "boot_session_id"}
START_WAIT_SECONDS = 60.0


class LifecycleError(RuntimeError):
    pass


def _fail(code):
    raise LifecycleError(code)


def _encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def _hash(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _hex(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


@dataclasses.dataclass(frozen=True)
class Target:
    uid: int
    home: Path

    @property
    def base(self): return self.home / ".local/share/mastermind-workbench-browser"
    @property
    def state_dir(self): return self.base / "state"
    @property
    def logs(self): return self.base / "logs"
    @property
    def candidate(self): return self.base / "staged-config.json"
    @property
    def config(self): return self.base / "config.json"
    @property
    def manifest(self): return self.base / "install.json"
    @property
    def lifecycle(self): return self.state_dir / "lifecycle.json"
    @property
    def journal(self): return self.state_dir / "stage.json"
    @property
    def lock(self): return self.state_dir / "lifecycle.lock"
    @property
    def plist(self): return self.home / "Library/LaunchAgents" / (LABEL + ".plist")
    @property
    def domain(self): return "gui/" + str(self.uid)
    @property
    def launch_target(self): return self.domain + "/" + LABEL


def target():
    uid = os.getuid()
    home = Path(pwd.getpwuid(uid).pw_dir)
    if uid < 501 or uid != os.geteuid() or home != owner._user_root():
        _fail("WORKBENCH_CHROME_USER_REQUIRED")
    return Target(uid, home)


def _guard(path, *, private_parent=True):
    owner._assert_dest_safe(path)
    from control_plane.fs_security import has_macos_acl
    current = path.parent
    home = owner._user_root()
    while True:
        info = current.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o022
                or (private_parent and current == path.parent and stat.S_IMODE(info.st_mode) & 0o077)
                or has_macos_acl(current, expected_identity=info)):
            _fail("WORKBENCH_PATH_CUSTODY_REFUSED")
        if current == home:
            break
        current = current.parent


def _bytes(path, *, optional=False, maximum=512 * 1024, private_parent=True):
    _guard(path, private_parent=private_parent)
    if optional and not path.exists() and not path.is_symlink():
        return None
    from integrations.workbench_action_mcp.tunnel import _acquire_regular_file_bytes
    from control_plane.fs_security import has_macos_acl
    info = path.lstat()
    if has_macos_acl(path, expected_identity=info):
        _fail("WORKBENCH_FILE_ACL_REFUSED")
    return _acquire_regular_file_bytes(str(path), maximum=maximum, required_imode=0o600)


def _decode(raw):
    def closed(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                _fail("WORKBENCH_DUPLICATE_FIELD")
            value[key] = item
        return value
    def invalid(_value): _fail("WORKBENCH_NONFINITE_FIELD")
    value = json.loads(raw, object_pairs_hook=closed, parse_constant=invalid)
    if type(value) is not dict:
        _fail("WORKBENCH_DOCUMENT_REFUSED")
    return value


def _read(path, *, optional=False):
    raw = _bytes(path, optional=optional)
    return None if raw is None else _decode(raw)


def _write(path, raw, *, private_parent=True):
    _guard(path, private_parent=private_parent)
    _bytes(path, optional=True, private_parent=private_parent)
    owner._atomic_write_bytes(path, raw, mode=0o600)
    # Lifecycle publication must not swallow an unavailable directory barrier.
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _prepare_directories(t):
    for directory in (t.base, t.state_dir, t.logs):
        if not directory.exists() and not directory.is_symlink():
            owner._ensure_secure_dir(directory)
        _guard(directory / "custody-probe")
    if not t.plist.parent.exists():
        owner._ensure_secure_dir(t.plist.parent)
    _guard(t.plist, private_parent=False)


def _read_state(t, *, optional=True):
    value = _read(t.lifecycle, optional=optional)
    if value is None:
        return None
    if (set(value) != STATE_KEYS or value["schema"] != STATE_SCHEMA
            or not _hex(value["install_sha256"]) or value["phase"] not in PHASES
            or (value["attempt_id"] is not None and not _hex(value["attempt_id"]))
            or (value["boot_session_id"] is not None and
                (type(value["boot_session_id"]) is not str or not value["boot_session_id"]))
            or (value["runs"] is not None and (type(value["runs"]) is not int or value["runs"] < 0))
            or (value["exit_code"] is not None and type(value["exit_code"]) is not int)
            or (value["error"] is not None and (type(value["error"]) is not str or len(value["error"]) > 96))):
        _fail("WORKBENCH_LIFECYCLE_RECORD_REFUSED")
    process = value["process"]
    if process is not None and (
            type(process) is not dict or set(process) != PROCESS_KEYS
            or type(process["pid"]) is not int or process["pid"] <= 0
            or type(process["service_uid"]) is not int or process["service_uid"] != t.uid
            or type(process["process_start_identity"]) is not str or not process["process_start_identity"]
            or process["boot_session_id"] != value["boot_session_id"]):
        _fail("WORKBENCH_LIFECYCLE_PROCESS_REFUSED")
    if value["phase"] not in {"IDLE", "STOPPED"} and value["attempt_id"] is None:
        _fail("WORKBENCH_ATTEMPT_ID_REQUIRED")
    return value


def _state(install_sha, **changes):
    value = dict(schema=STATE_SCHEMA, install_sha256=install_sha, attempt_id=None,
                 phase="IDLE", boot_session_id=None, process=None, runs=None,
                 exit_code=None, error=None)
    value.update(changes)
    return value


def _save(t, state, **changes):
    state = dict(state, **changes)
    _write(t.lifecycle, _encoded(state))
    return state


def _config_parts(document, qualified):
    from integrations.workbench_action_mcp.service import (
        BrowserLinkServiceConfig, parse_service_config, _secure_json,
        _secure_action_key, _open_safe_directory, SERVICE_SCHEMA_V3, SERVICE_SCHEMA_V4, SERVICE_SCHEMA_V5,
        MAX_CONFIG_BYTES, MAX_POLICY_BYTES,
    )
    from integrations.workbench_action_mcp.readiness import config_fingerprint
    if len(_encoded(document)) > MAX_CONFIG_BYTES:
        _fail("WORKBENCH_CONFIG_SIZE_REFUSED")
    config = parse_service_config(document)
    source = qualified["source"]["release_sha"]
    from ops.executive_os import company_mcp_edge as runtime_owner
    if (config.schema not in {SERVICE_SCHEMA_V3, SERVICE_SCHEMA_V4, SERVICE_SCHEMA_V5}
            or type(config.browser) is not BrowserLinkServiceConfig
            or config.browser.source_root != str(runtime_owner.SYSTEM / "releases" / source)
            or config.browser.python_executable != qualified["python_executable"]):
        _fail("WORKBENCH_CONFIG_RUNTIME_BINDING_REFUSED")
    persistent = {}
    for name in ("project_root", "artifact_directory", "audit_directory", "browser_fabric_audit_directory"):
        path = getattr(config, name)
        descriptor = _open_safe_directory(path)
        try:
            info = os.fstat(descriptor)
            persistent[name] = {"path": path, "device": info.st_dev, "inode": info.st_ino,
                                "uid": info.st_uid, "mode": stat.S_IMODE(info.st_mode)}
        finally:
            os.close(descriptor)
    key = _secure_action_key(config.action_key_file)
    persistent["action_key"] = {"path": config.action_key_file, "sha256": hashlib.sha256(key).hexdigest()}
    dependencies = {}
    for name, path in (
        ("policy", config.policy_file), ("browser_policy", config.browser_fabric_policy_file),
        ("profiles", config.browser.profiles_file), ("routes", config.browser_fabric_routes_file),
        ("credentials", config.browser_fabric_credentials_file),
    ):
        if path is not None:
            value = _secure_json(path, maximum=MAX_POLICY_BYTES if name in {"policy", "browser_policy"} else 256 * 1024,
                                 owner_only=name == "credentials")
            dependencies[name] = {"path": path, "sha256": _hash(value)}
    return config, config_fingerprint(config), persistent, dependencies


def _plist(t, config, release_sha):
    from ops.executive_os.workbench_mcp_runtime import launch_argv
    from control_plane.fs_security import has_macos_acl
    if t.logs.exists():
        for name in ("service.stdout.log", "service.stderr.log"):
            path = t.logs / name
            _guard(path)
            if path.exists() or path.is_symlink():
                info = path.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != t.uid or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or has_macos_acl(path, expected_identity=info)):
                    _fail("WORKBENCH_LOG_CUSTODY_REFUSED")
    return {
        "Label": LABEL, "ProgramArguments": launch_argv(release_sha, t.uid),
        "RunAtLoad": False, "KeepAlive": False,
        "ExitTimeOut": math.ceil(2 * config.close_timeout_seconds + 90),
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "HOME": str(t.home)},
        "WorkingDirectory": str(t.base), "Umask": 0o077,
        "StandardOutPath": str(t.logs / "service.stdout.log"),
        "StandardErrorPath": str(t.logs / "service.stderr.log"),
    }


def _qualify_plan(t, plan):
    from ops.executive_os.workbench_mcp_runtime import verify
    if (type(plan) is not dict or set(plan) != PLAN_KEYS or plan["schema"] != PLAN_SCHEMA
            or type(plan["service_uid"]) is not int or plan["service_uid"] != t.uid
            or (plan["previous_install_sha256"] is not None and not _hex(plan["previous_install_sha256"]))):
        _fail("WORKBENCH_INSTALL_PLAN_REFUSED")
    runtime = verify(plan["release_sha"], t.uid)
    if plan["runtime"] != runtime:
        _fail("WORKBENCH_RUNTIME_RECEIPT_CHANGED")
    config, fingerprint, persistent, dependencies = _config_parts(plan["config"], runtime)
    if (plan["config_sha256"] != fingerprint or plan["persistent"] != persistent
            or plan["dependencies"] != dependencies or plan["plist"] != _plist(t, config, plan["release_sha"])):
        _fail("WORKBENCH_INSTALL_BINDING_CHANGED")
    return config


def _manifest(plan):
    return {"schema": MANIFEST_SCHEMA, "plan": plan, "install_sha256": _hash(plan)}


def _qualify_manifest(t, manifest):
    if (type(manifest) is not dict or set(manifest) != {"schema", "plan", "install_sha256"}
            or manifest["schema"] != MANIFEST_SCHEMA or manifest["install_sha256"] != _hash(manifest["plan"])):
        _fail("WORKBENCH_INSTALL_MANIFEST_REFUSED")
    return _qualify_plan(t, manifest["plan"])


def _payloads(t, manifest, state):
    if manifest is None:
        return {t.config: None, t.plist: None, t.manifest: None, t.lifecycle: None}
    plan = manifest["plan"]
    return {
        t.config: _encoded(plan["config"]),
        t.plist: plistlib.dumps(plan["plist"], sort_keys=True),
        t.manifest: _encoded(manifest), t.lifecycle: _encoded(state) if state is not None else None,
    }


def _verify_install(t, expected=None):
    manifest = _read(t.manifest)
    config = _qualify_manifest(t, manifest)
    if expected is not None and manifest["install_sha256"] != expected:
        _fail("WORKBENCH_INSTALL_COMPARE_AND_SWAP_REFUSED")
    for path, data in _payloads(t, manifest, None).items():
        if path == t.lifecycle:
            continue
        if _bytes(path, private_parent=path != t.plist) != data:
            _fail("WORKBENCH_INSTALLED_BYTES_CHANGED")
    return manifest, config


def parse_observation(result, t):
    absent = (f'Bad request.\nCould not find service "{LABEL}" '
              f'in domain for user gui: {t.uid}\n')
    if result.returncode == 113 and result.stdout == "" and result.stderr == absent:
        return None
    lines = result.stdout.splitlines()
    if (result.returncode != 0 or result.stderr or len(lines) < 2
            or lines[0] != t.launch_target + " = {" or lines[-1] != "}"):
        _fail("WORKBENCH_LAUNCHD_OBSERVATION_UNKNOWN")
    fields = {}
    for key in ("path", "state", "pid", "runs", "last exit code", "last terminating signal"):
        matches = [line.split(" = ", 1)[1] for line in lines[1:-1] if line.startswith("\t" + key + " = ")]
        if len(matches) > 1:
            _fail("WORKBENCH_LAUNCHD_OBSERVATION_UNKNOWN")
        fields[key] = matches[0] if matches else None
    if (fields["path"] != str(t.plist) or fields["state"] not in {"running", "waiting"}
            or fields["runs"] is None or not fields["runs"].isdigit()
            or (fields["pid"] is not None and (not fields["pid"].isdigit() or int(fields["pid"]) <= 0))
            or ((fields["state"] == "running") != (fields["pid"] is not None))):
        _fail("WORKBENCH_LAUNCHD_OBSERVATION_UNKNOWN")
    exit_text = fields["last exit code"]
    exit_code = int(exit_text) if type(exit_text) is str and re.fullmatch("[0-9]+", exit_text) else None
    return {
        "state": fields["state"], "pid": int(fields["pid"]) if fields["pid"] else None,
        "runs": int(fields["runs"]), "exit_code": exit_code,
        "never_exited": exit_text == "(never exited)",
        "signal": fields["last terminating signal"],
    }


def _observe(t):
    try:
        return parse_observation(owner._run(
            ["/bin/launchctl", "print", t.launch_target], check=False, timeout=5), t)
    except LifecycleError:
        raise
    except Exception as error:
        raise LifecycleError("WORKBENCH_LAUNCHD_OBSERVATION_UNKNOWN") from error


def _inspector():
    from control_plane.codex_worker import ProcessInspector
    return ProcessInspector()


def _boot():
    value = _inspector().boot_session_id()
    if not value or value.startswith("adapter-"):
        _fail("WORKBENCH_BOOT_IDENTITY_UNKNOWN")
    return value


def _process(t, pid):
    observed = _inspector().inspect(pid)
    if observed.effective_uid != t.uid or observed.real_uid != t.uid:
        _fail("WORKBENCH_PROCESS_UID_CHANGED")
    return {"pid": pid, "process_start_identity": observed.start_identity,
            "service_uid": t.uid, "boot_session_id": _boot()}


def _process_absent(t, original):
    if _boot() != original["boot_session_id"]:
        return False
    try:
        os.kill(original["pid"], 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    try:
        return _process(t, original["pid"]) != original
    except Exception:
        return False


def _probe(t, config, plan, process, *, timeout=2.0):
    import asyncio
    import httpx
    from integrations.workbench_action_mcp.readiness import MEDIA_TYPE, verify_snapshot
    from integrations.workbench_action_mcp.acquisition import projection, document_fingerprint
    from integrations.workbench_action_mcp.service import _secure_action_key
    key = _secure_action_key(config.action_key_file)
    if hashlib.sha256(key).hexdigest() != plan["persistent"]["action_key"]["sha256"]:
        return None
    expected_acquisition = document_fingerprint(projection(
        plan["config_sha256"], plan["persistent"], plan["dependencies"]))
    nonce = secrets.token_hex(32)
    async def acquire():
        async with asyncio.timeout(timeout):
            # This fixed URL is plain HTTP on 127.0.0.1. Avoid building a
            # system CA store inside the small absolute readiness budget.
            transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False, verify=False)
            async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                                         timeout=timeout) as client:
                async with client.stream(
                    "GET", "http://127.0.0.1:" + str(config.bind_port) + "/readyz?nonce=" + nonce,
                    headers={"Host": config.incoming_authority, "Accept": MEDIA_TYPE,
                             "Accept-Encoding": "identity"},
                ) as response:
                    if (response.status_code not in {200, 503}
                            or response.headers.get("content-type") != "application/json"
                            or response.headers.get("content-encoding", "identity") != "identity"):
                        return None
                    raw = bytearray()
                    async for chunk in response.aiter_raw():
                        raw.extend(chunk)
                        if len(raw) > 4096:
                            return None
                    observed = _decode(bytes(raw))
                    if not verify_snapshot(
                            observed, key=key, nonce=nonce, process=process,
                            host_id=config.host_id, config_sha256=plan["config_sha256"],
                            acquisition_sha256=expected_acquisition):
                        return None
                    if (response.status_code == 200) != observed["ready"]:
                        return None
                    return observed["ready"]
    try:
        return asyncio.run(acquire())
    except (TimeoutError, OSError, ValueError, httpx.HTTPError):
        return None


def _journal(t):
    value = _read(t.journal, optional=True)
    if value is None:
        return None
    if (set(value) != {"schema", "phase", "plan", "previous_manifest", "previous_state"}
            or value["schema"] != STAGE_SCHEMA or value["phase"] not in {"PREPARED", "APPLIED"}):
        _fail("WORKBENCH_STAGE_RECORD_REFUSED")
    _qualify_plan(t, value["plan"])
    prior = value["previous_manifest"]
    if prior is None:
        if value["plan"]["previous_install_sha256"] is not None or value["previous_state"] is not None:
            _fail("WORKBENCH_STAGE_PREIMAGE_REFUSED")
    else:
        _qualify_manifest(t, prior)
        state = value["previous_state"]
        if (prior["install_sha256"] != value["plan"]["previous_install_sha256"]
                or type(state) is not dict or set(state) != STATE_KEYS
                or state["schema"] != STATE_SCHEMA or state["phase"] not in {"IDLE", "STOPPED"}
                or state["install_sha256"] != prior["install_sha256"]
                or prior["plan"]["persistent"] != value["plan"]["persistent"]):
            _fail("WORKBENCH_STAGE_PREIMAGE_REFUSED")
    return value


def preview(release_sha):
    t = target()
    from ops.executive_os.workbench_mcp_runtime import verify
    runtime = verify(release_sha, t.uid)
    document = _read(t.candidate)
    config, fingerprint, persistent, dependencies = _config_parts(document, runtime)
    pending = _journal(t) if t.journal.parent.exists() else None
    if pending is not None and pending["phase"] == "PREPARED":
        if (pending["plan"]["release_sha"] != release_sha or pending["plan"]["config"] != document
                or _observe(t) is not None):
            _fail("WORKBENCH_ORIGINAL_STAGE_REQUIRED")
        return pending["plan"]
    prior = _read(t.manifest, optional=True)
    prior_state = _read_state(t) if t.state_dir.exists() else None
    if prior is not None:
        _verify_install(t)
    plan = {
        "schema": PLAN_SCHEMA, "service_uid": t.uid, "release_sha": release_sha,
        "runtime": runtime, "config": document, "config_sha256": fingerprint,
        "persistent": persistent, "dependencies": dependencies, "plist": _plist(t, config, release_sha),
        "previous_install_sha256": prior["install_sha256"] if prior else None,
    }
    if prior is not None and all(plan[k] == prior["plan"][k] for k in PLAN_KEYS - {"previous_install_sha256"}):
        return prior["plan"]
    if _observe(t) is not None:
        _fail("WORKBENCH_STAGE_REQUIRES_UNREGISTERED_SERVICE")
    if prior is not None and (
            prior_state is None or prior_state["install_sha256"] != prior["install_sha256"]
            or prior_state["phase"] not in {"IDLE", "STOPPED"} or prior["plan"]["persistent"] != persistent):
        _fail("WORKBENCH_STAGE_PRESERVES_ORIGINAL_STATE")
    if prior is None and prior_state is not None:
        _fail("WORKBENCH_ORPHAN_LIFECYCLE_RECORD")
    return plan


def stage(release_sha, expected_plan_sha256):
    t = target()
    _prepare_directories(t)
    with owner._owned_lifecycle_mutex(t.lock, subject="Workbench"):
        plan = preview(release_sha)
        if not _hex(expected_plan_sha256) or _hash(plan) != expected_plan_sha256:
            _fail("WORKBENCH_PLAN_COMPARE_AND_SWAP_REFUSED")
        existing = _read(t.manifest, optional=True)
        if existing == _manifest(plan):
            _verify_install(t)
            pending = _journal(t)
            if pending is None or pending["phase"] == "APPLIED":
                return {"status": "UNCHANGED", "install_sha256": _hash(plan)}
        journal = _journal(t)
        if journal is None or journal["phase"] == "APPLIED":
            journal = {
                "schema": STAGE_SCHEMA, "phase": "PREPARED", "plan": plan,
                "previous_manifest": existing, "previous_state": _read_state(t),
            }
            _write(t.journal, _encoded(journal))
        if journal["plan"] != plan or _observe(t) is not None:
            _fail("WORKBENCH_ORIGINAL_STAGE_REQUIRED")
        new_manifest = _manifest(plan)
        new_state = _state(new_manifest["install_sha256"])
        previous = _payloads(t, journal["previous_manifest"], journal["previous_state"])
        following = _payloads(t, new_manifest, new_state)
        # Qualify every destination before the first write. A recovered stage may
        # contain only its original preimage or exact intended output.
        for path in following:
            actual = _bytes(path, optional=True, private_parent=path != t.plist)
            if actual != previous[path] and actual != following[path]:
                _fail("WORKBENCH_STAGE_DESTINATION_CHANGED")
        for path in (t.config, t.plist, t.lifecycle, t.manifest):
            if _bytes(path, optional=True, private_parent=path != t.plist) != following[path]:
                _write(path, following[path], private_parent=path != t.plist)
        _verify_install(t)
        _write(t.journal, _encoded(dict(journal, phase="APPLIED")))
        return {"status": "STAGED", "install_sha256": new_manifest["install_sha256"]}


def _result(state, observation, *, ready=None):
    return {
        "schema": STATE_SCHEMA, "install_sha256": state["install_sha256"],
        "phase": state["phase"], "attempt_id": state["attempt_id"],
        "registration": "absent" if observation is None else observation["state"],
        "runtime_ready": ready, "fleet_observation": "unobserved",
        "exit_code": state["exit_code"], "hold": state["error"],
    }


def _matching_running(t, state, observed):
    if observed is None or observed["state"] != "running" or observed["runs"] != state["runs"]:
        return False
    return state["process"] is not None and _process(t, observed["pid"]) == state["process"]


def _classify_original_exit(t, state, observed):
    """Read-only projection of the original attempt; never derives a new launch."""
    if state["phase"] in {"IDLE", "STOPPED", "HOLD", "CLEAN_EXIT", "BOOTOUT_ISSUED"}:
        return state
    if state["process"] is None:
        return state
    if (_boot() != state["boot_session_id"] or observed is None
            or observed["runs"] != state["runs"]):
        return dict(state, phase="HOLD", error="WORKBENCH_SHUTDOWN_IDENTITY_UNKNOWN")
    if observed["state"] == "running":
        if _matching_running(t, state, observed):
            return state
        return dict(state, phase="HOLD", error="WORKBENCH_SHUTDOWN_IDENTITY_UNKNOWN")
    if not _process_absent(t, state["process"]):
        return state
    code = observed["exit_code"]
    if code == 0 and observed["signal"] is None and not observed["never_exited"]:
        return dict(state, phase="CLEAN_EXIT", exit_code=0, error=None)
    reason = {
        2: "WORKBENCH_CONFIGURATION_REFUSED",
        3: "WORKBENCH_PHYSICAL_DRAIN_INCOMPLETE",
        4: "WORKBENCH_CLEANUP_UNCERTAIN",
    }.get(code, "WORKBENCH_SHUTDOWN_UNQUALIFIED")
    if observed["signal"] is not None or observed["never_exited"]:
        reason = "WORKBENCH_SHUTDOWN_UNQUALIFIED"
    return dict(state, phase="HOLD", exit_code=code, error=reason)


def _await_ready(t, manifest, config, state):
    deadline = time.monotonic() + START_WAIT_SECONDS
    while True:
        observed = _observe(t)
        if observed is not None and observed["state"] == "running":
            process = _process(t, observed["pid"])
            if (process["boot_session_id"] != state["boot_session_id"] or observed["runs"] != 1
                    or (state["process"] is not None and state["process"] != process)):
                state = _save(t, state, phase="HOLD", error="WORKBENCH_START_IDENTITY_CHANGED")
                return _result(state, observed)
            if state["process"] is None:
                state = _save(t, state, process=process, runs=observed["runs"])
            ready = _probe(t, config, manifest["plan"], process,
                           timeout=max(0.001, min(2.0, deadline - time.monotonic())))
            after = _observe(t)
            if ready is True and _matching_running(t, state, after):
                state = _save(t, state, phase="RUNNING", error=None)
                return _result(state, after, ready=True)
        if observed is not None and observed["state"] == "waiting" and observed["runs"] > 0:
            classified = _classify_original_exit(t, state, observed)
            if classified == state:
                classified = dict(state, phase="HOLD", exit_code=None, error="WORKBENCH_START_EXIT_UNQUALIFIED")
            state = _save(t, classified)
            return _result(state, observed)
        if time.monotonic() >= deadline:
            state = _save(t, state, error="WORKBENCH_READINESS_UNKNOWN")
            return _result(state, observed)
        time.sleep(0.2)


def start(expected_install_sha256):
    t = target()
    with owner._owned_lifecycle_mutex(t.lock, subject="Workbench"):
        manifest, config = _verify_install(t, expected_install_sha256)
        state = _read_state(t, optional=False)
        if state["install_sha256"] != manifest["install_sha256"]:
            _fail("WORKBENCH_LIFECYCLE_INSTALL_CHANGED")
        observed = _observe(t)
        classified = _classify_original_exit(t, state, observed)
        if classified != state:
            state = _save(t, classified)
        if state["phase"] == "RUNNING":
            if not _matching_running(t, state, observed):
                return _result(state, observed)
            ready = _probe(t, config, manifest["plan"], state["process"])
            if not _matching_running(t, state, _observe(t)):
                ready = None
            return _result(state, observed, ready=ready)
        if state["phase"] in {"BOOTSTRAP_ISSUED", "KICKSTART_ISSUED"}:
            # Observe the original attempt; never repeat either modifying call.
            return _await_ready(t, manifest, config, state)
        if state["phase"] not in {"IDLE", "STOPPED"}:
            return _result(state, observed)
        if observed is not None:
            _fail("WORKBENCH_UNOWNED_REGISTRATION")
        state = _save(t, _state(manifest["install_sha256"]), phase="BOOTSTRAP_ISSUED",
                      attempt_id=secrets.token_hex(32), boot_session_id=_boot())
        try:
            result = owner._run(["/bin/launchctl", "bootstrap", t.domain, str(t.plist)], check=False, timeout=10)
            observed = _observe(t)
        except Exception:
            state = _save(t, state, error="WORKBENCH_BOOTSTRAP_UNKNOWN")
            return _result(state, None)
        if (result.returncode != 0 or observed is None or observed["state"] != "waiting"
                or observed["runs"] != 0 or not observed["never_exited"] or observed["signal"] is not None):
            state = _save(t, state, error="WORKBENCH_BOOTSTRAP_UNKNOWN")
            return _result(state, observed)
        state = _save(t, state, phase="KICKSTART_ISSUED")
        try:
            result = owner._run(["/bin/launchctl", "kickstart", t.launch_target], check=False, timeout=10)
        except Exception:
            state = _save(t, state, error="WORKBENCH_KICKSTART_UNKNOWN")
            return _result(state, observed)
        if result.returncode != 0:
            state = _save(t, state, error="WORKBENCH_KICKSTART_UNKNOWN")
            return _result(state, observed)
        return _await_ready(t, manifest, config, state)


def inspect():
    t = target()
    manifest, config = _verify_install(t)
    state = _read_state(t, optional=False)
    if state["install_sha256"] != manifest["install_sha256"]:
        _fail("WORKBENCH_LIFECYCLE_INSTALL_CHANGED")
    observed = _observe(t)
    state = _classify_original_exit(t, state, observed)
    ready = None
    if _matching_running(t, state, observed):
        ready = _probe(t, config, manifest["plan"], state["process"])
        if not _matching_running(t, state, _observe(t)):
            ready = None
    return _result(state, observed, ready=ready)


def _bootout(t, state):
    observed = _observe(t)
    if state["phase"] == "CLEAN_EXIT":
        if (state["process"] is None or _boot() != state["boot_session_id"]
                or observed is None or observed["state"] != "waiting"
                or observed["runs"] != state["runs"] or observed["exit_code"] != 0
                or observed["signal"] is not None or observed["never_exited"]
                or not _process_absent(t, state["process"])):
            state = _save(t, state, phase="HOLD", error="WORKBENCH_RETIREMENT_IDENTITY_CHANGED")
            return _result(state, observed)
        state = _save(t, state, phase="BOOTOUT_ISSUED")
        try:
            owner._run(["/bin/launchctl", "bootout", t.launch_target], check=False, timeout=10)
        except Exception:
            state = _save(t, state, error="WORKBENCH_BOOTOUT_UNKNOWN")
    observed = _observe(t)
    if observed is None:
        state = _save(t, state, phase="STOPPED", error=None)
    elif (_boot() != state["boot_session_id"] or observed["state"] != "waiting"
          or observed["runs"] != state["runs"] or observed["exit_code"] != 0
          or observed["signal"] is not None or observed["never_exited"]):
        state = _save(t, state, phase="HOLD", error="WORKBENCH_RETIREMENT_IDENTITY_CHANGED")
    else:
        state = _save(t, state, error="WORKBENCH_BOOTOUT_UNKNOWN")
    return _result(state, observed)


def stop(expected_install_sha256):
    t = target()
    with owner._owned_lifecycle_mutex(t.lock, subject="Workbench"):
        manifest, config = _verify_install(t, expected_install_sha256)
        state = _read_state(t, optional=False)
        if state["install_sha256"] != manifest["install_sha256"]:
            _fail("WORKBENCH_LIFECYCLE_INSTALL_CHANGED")
        observed = _observe(t)
        classified = _classify_original_exit(t, state, observed)
        if classified != state:
            state = _save(t, classified)
        if state["phase"] in {"IDLE", "STOPPED", "HOLD"}:
            return _result(state, observed)
        if state["phase"] in {"CLEAN_EXIT", "BOOTOUT_ISSUED"}:
            return _bootout(t, state)
        if state["process"] is None or _boot() != state["boot_session_id"]:
            state = _save(t, state, phase="HOLD", error="WORKBENCH_ORIGINAL_PROCESS_UNKNOWN")
            return _result(state, observed)
        if state["phase"] != "STOP_ISSUED":
            if not _matching_running(t, state, observed):
                state = _save(t, state, phase="HOLD", error="WORKBENCH_ORIGINAL_PROCESS_UNKNOWN")
                return _result(state, observed)
            state = _save(t, state, phase="STOP_ISSUED", error=None)
            try:
                signal_result = owner._run(
                    ["/bin/launchctl", "kill", "SIGTERM", t.launch_target], check=False, timeout=10)
                if signal_result.returncode != 0:
                    state = _save(t, state, error="WORKBENCH_SIGNAL_UNKNOWN")
            except Exception:
                state = _save(t, state, error="WORKBENCH_SIGNAL_UNKNOWN")
        deadline = time.monotonic() + manifest["plan"]["plist"]["ExitTimeOut"]
        while True:
            observed = _observe(t)
            if (observed is not None and observed["state"] == "waiting"
                    and observed["runs"] == state["runs"] and _process_absent(t, state["process"])):
                code = observed["exit_code"]
                if code == 0 and observed["signal"] is None and not observed["never_exited"]:
                    state = _save(t, state, phase="CLEAN_EXIT", exit_code=0, error=None)
                    return _bootout(t, state)
                state = _save(t, state, phase="HOLD", exit_code=code, error={
                    2: "WORKBENCH_CONFIGURATION_REFUSED",
                    3: "WORKBENCH_PHYSICAL_DRAIN_INCOMPLETE",
                    4: "WORKBENCH_CLEANUP_UNCERTAIN",
                }.get(code, "WORKBENCH_SHUTDOWN_UNQUALIFIED"))
                return _result(state, observed)
            if (observed is None or _boot() != state["boot_session_id"]
                    or (observed["state"] == "running" and not _matching_running(t, state, observed))):
                state = _save(t, state, phase="HOLD", error="WORKBENCH_SHUTDOWN_IDENTITY_UNKNOWN")
                return _result(state, observed)
            if time.monotonic() >= deadline:
                state = _save(t, state, error="WORKBENCH_SHUTDOWN_PENDING")
                return _result(state, observed)
            time.sleep(0.2)


def _command(args):
    try:
        if args.cmd == "workbench-preview":
            plan = preview(args.release)
            result = {"status": "PREVIEW", "plan_sha256": _hash(plan), "plan": plan}
        elif args.cmd == "workbench-stage":
            result = stage(args.release, args.expected_plan_sha256)
        elif args.cmd == "workbench-start":
            result = start(args.expected_install_sha256)
        elif args.cmd == "workbench-stop":
            result = stop(args.expected_install_sha256)
        else:
            result = inspect()
        print(json.dumps(result, sort_keys=True))
        if args.cmd == "workbench-start":
            return 0 if result.get("phase") == "RUNNING" and result.get("runtime_ready") is True else 1
        if args.cmd == "workbench-stop":
            return 0 if result.get("phase") in {"IDLE", "STOPPED"} and result.get("registration") == "absent" else 1
        return 0
    except (LifecycleError, OSError, ValueError) as error:
        code = str(error) if isinstance(error, LifecycleError) else "WORKBENCH_LIFECYCLE_REFUSED"
        print(json.dumps({"status": "HOLD", "code": code}, sort_keys=True))
        return 1


def add_commands(subparsers):
    for name in ("preview", "stage", "start", "inspect", "stop"):
        parser = subparsers.add_parser("workbench-" + name)
        if name in {"preview", "stage"}:
            parser.add_argument("--release", required=True)
        if name == "stage":
            parser.add_argument("--expected-plan-sha256", required=True)
        if name in {"start", "stop"}:
            parser.add_argument("--expected-install-sha256", required=True)
        parser.set_defaults(func=_command)

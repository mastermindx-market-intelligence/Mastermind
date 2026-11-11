"""Host/profile coordinates for the incumbent browser bridge.

This is a stateless projection of the existing deployment inventory. SSH uses
operator-configured aliases and fixed pinned helpers; no daemon or new keys.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import stat
import subprocess
import sys
import time

SCHEMA = "mastermind.browser_deployments.v2"
EXTENSION_ID = "kmpbpccecbofdnhpcmjogofgmdodpnko"
HOST_RE = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
MAX_OUTPUT = 921600


class RouteError(ValueError):
    def __init__(self, code, *, possible=False):
        super().__init__(code)
        self.code, self.possible = code, possible


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def read_owned(path, maximum=262144):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_size > maximum:
            raise RouteError("ROUTING_FILE_UNSAFE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        if len(raw) > maximum or (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise RouteError("ROUTING_FILE_CHANGED")
        return raw
    finally:
        os.close(fd)


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))


def absolute(value):
    return isinstance(value, str) and len(value) <= 4096 and Path(value).is_absolute() and ".." not in Path(value).parts and not re.search(r"[\x00\r\n]", value)


def validate(document):
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or set(document) != {"schema", "local_host_ref", "hosts", "profiles"}:
        raise RouteError("ROUTING_SCHEMA_INVALID")
    if not HOST_RE.fullmatch(str(document["local_host_ref"])):
        raise RouteError("ROUTING_HOST_INVALID")
    hosts, profiles = document["hosts"], document["profiles"]
    if not isinstance(hosts, list) or not 1 <= len(hosts) <= 16 or not isinstance(profiles, list) or len(profiles) > 64:
        raise RouteError("ROUTING_LIMIT")
    names = set()
    for host in hosts:
        required = {"host_ref", "label", "transport"}
        if not isinstance(host, dict) or not required <= set(host) or set(host) - required - {"ssh_alias", "python_executable", "source_root", "bindings_path", "manifest_sha256"}:
            raise RouteError("ROUTING_HOST_INVALID")
        ref = host["host_ref"]
        if not isinstance(ref, str) or not HOST_RE.fullmatch(ref) or ref in names or not isinstance(host["label"], str) or not 1 <= len(host["label"]) <= 120:
            raise RouteError("ROUTING_HOST_INVALID")
        names.add(ref)
        if host["transport"] == "local":
            if ref != document["local_host_ref"] or set(host) != required:
                raise RouteError("ROUTING_LOCAL_HOST_INVALID")
        elif host["transport"] == "ssh":
            if ref == document["local_host_ref"] or set(host) != required | {"ssh_alias", "python_executable", "source_root", "bindings_path", "manifest_sha256"}:
                raise RouteError("ROUTING_REMOTE_HOST_INVALID")
            if not HOST_RE.fullmatch(str(host["ssh_alias"])) or not re.fullmatch(r"[0-9a-f]{64}", str(host["manifest_sha256"])):
                raise RouteError("ROUTING_REMOTE_HOST_INVALID")
            if not all(absolute(host[k]) for k in ("python_executable", "source_root", "bindings_path")):
                raise RouteError("ROUTING_REMOTE_HOST_INVALID")
        else:
            raise RouteError("ROUTING_TRANSPORT_INVALID")
    if document["local_host_ref"] not in names:
        raise RouteError("ROUTING_LOCAL_HOST_INVALID")
    seen, aliases = set(), set()
    required = {"host_ref", "browser_id", "alias", "label", "manager", "profile_directory", "profile_name", "account_hint",
        "data_directory", "extension_path", "native_host_manifest", "chrome_executable", "upload_roots"}
    for row in profiles:
        if not isinstance(row, dict) or not required <= set(row) or set(row) - required - {"launch_environment"}:
            raise RouteError("ROUTING_PROFILE_INVALID")
        if row["host_ref"] not in names or row["manager"] != "chrome" or not re.fullmatch(r"[0-9a-f]{64}", str(row["browser_id"])):
            raise RouteError("ROUTING_PROFILE_INVALID")
        if not HOST_RE.fullmatch(str(row["alias"])) or not re.fullmatch(r"Default|Profile [0-9]+", str(row["profile_directory"])):
            raise RouteError("ROUTING_PROFILE_INVALID")
        if any(not isinstance(row[k], str) or len(row[k]) > 160 or re.search(r"[\x00\r\n]", row[k]) for k in ("label", "profile_name", "account_hint")):
            raise RouteError("ROUTING_PROFILE_INVALID")
        if not all(absolute(row[k]) for k in ("data_directory", "extension_path", "native_host_manifest", "chrome_executable")):
            raise RouteError("ROUTING_PROFILE_INVALID")
        if not isinstance(row["upload_roots"], list) or not 1 <= len(row["upload_roots"]) <= 16 or not all(absolute(p) for p in row["upload_roots"]):
            raise RouteError("ROUTING_PROFILE_INVALID")
        environment = row.get("launch_environment", {})
        if not isinstance(environment, dict) or set(environment) - {"DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY"}:
            raise RouteError("ROUTING_ENVIRONMENT_INVALID")
        if any(not isinstance(v, str) or len(v) > 512 or re.search(r"[\x00\r\n]", v) for v in environment.values()):
            raise RouteError("ROUTING_ENVIRONMENT_INVALID")
        key, alias = (row["host_ref"], row["browser_id"]), (row["host_ref"], row["alias"])
        if key in seen or alias in aliases:
            raise RouteError("ROUTING_PROFILE_AMBIGUOUS")
        seen.add(key); aliases.add(alias)
    return document


def load(path):
    document = decode(read_owned(path))
    return validate(document) if isinstance(document, dict) and document.get("schema") == SCHEMA else None


def resolve(document, browser_id, host_ref=None):
    rows = [r for r in document["profiles"] if r["browser_id"] == browser_id and (host_ref is None or r["host_ref"] == host_ref)]
    if not rows:
        raise RouteError("BROWSER_NOT_REGISTERED")
    if len(rows) != 1:
        raise RouteError("BROWSER_HOST_REQUIRED")
    row = rows[0]
    return row, next(h for h in document["hosts"] if h["host_ref"] == row["host_ref"])


def registration(row):
    """Read only the known extension ID's registration, never page/account data."""
    profile = Path(row["data_directory"]) / row["profile_directory"]
    if not profile.is_dir() or profile.is_symlink():
        return {"installed": False, "activation": "PROFILE_DIRECTORY_MISSING"}
    entry = None
    for name in ("Secure Preferences", "Preferences"):
        try:
            document = decode(read_owned(profile / name, 20000000))
            entry = document.get("extensions", {}).get("settings", {}).get(EXTENSION_ID)
            if entry:
                break
        except FileNotFoundError:
            continue
        except (ValueError, OSError):
            return {"installed": None, "activation": "PROFILE_REGISTRATION_UNAVAILABLE"}
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        return {"installed": False, "activation": "CHROME_LOAD_REQUIRED"}
    path = Path(entry["path"])
    if not path.is_absolute():
        path = profile / "Extensions" / path
    try:
        config = read_owned(path / "instance_config.js", 16384).decode()
        match = re.search(r"Object\.freeze\((\{.*\})\)\s*;?\s*$", config, re.S)
        identity = decode(match.group(1)) if match else {}
        version = decode(read_owned(path / "manifest.json", 32768)).get("version")
    except (OSError, ValueError):
        return {"installed": None, "activation": "LOADED_EXTENSION_UNVERIFIED", "loaded_path": str(path)}
    if identity.get("instanceId") != row["browser_id"]:
        return {"installed": False, "activation": "PROFILE_IDENTITY_MISMATCH", "loaded_path": str(path)}
    disabled = bool(entry.get("disable_reasons")) or entry.get("state") == 0
    return {"installed": True, "activation": "EXTENSION_DISABLED" if disabled else "LOADED",
        "loaded_path": str(path), "loaded_version": version}


def describe(row, host):
    result = {k: row[k] for k in ("host_ref", "browser_id", "alias", "label", "manager", "profile_directory", "profile_name", "account_hint")}
    result.update(host_label=host["label"], browser_ref=row["host_ref"]+"/"+row["alias"], connectivity="NOT_CHECKED", installed=None)
    if host["transport"] == "local":
        result.update(registration(row))
        result["launchable"] = result.get("activation") == "LOADED" and os.access(row["chrome_executable"], os.X_OK)
    else:
        result["launchable"] = None
    return result


def validate_upload(row, files, extra_roots=()):
    if not isinstance(files, list) or not 1 <= len(files) <= 16:
        raise RouteError("UPLOAD_FILE_INVALID")
    roots = [Path(p).resolve(strict=True) for p in [*row["upload_roots"], *extra_roots] if Path(p).is_dir()]
    verified = []
    for name in files:
        if not absolute(name):
            raise RouteError("UPLOAD_FILE_INVALID")
        path = Path(name).resolve(strict=True)
        info = path.stat()
        if not any(path.is_relative_to(root) for root in roots) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 536870912 or not os.access(path, os.R_OK):
            raise RouteError("UPLOAD_FILE_OUTSIDE_ROOTS")
        verified.append({"path":str(path),"name": path.name, "bytes": info.st_size, "host_ref": row["host_ref"]})
    return verified


def launch(row):
    state = registration(row)
    if state.get("activation") != "LOADED":
        raise RouteError(state.get("activation", "CHROME_LOAD_REQUIRED"))
    executable = Path(row["chrome_executable"])
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RouteError("CHROME_EXECUTABLE_UNAVAILABLE")
    environment = {"HOME": str(Path.home()), "PATH": "/usr/bin:/bin", **row.get("launch_environment", {})}
    if sys.platform.startswith("linux") and not (environment.get("DISPLAY") or environment.get("WAYLAND_DISPLAY")):
        raise RouteError("BROWSER_GUI_ENVIRONMENT_REQUIRED")
    command = [str(executable), "--user-data-dir="+row["data_directory"],
        "--profile-directory="+row["profile_directory"], "--new-window", "about:blank"]
    if sys.platform.startswith("linux") and environment.get("WAYLAND_DISPLAY"):
        command.insert(1, "--ozone-platform=wayland")
    # No debugging flags, new profile, permission changes or automatic retry.
    with open(os.devnull, "wb") as sink:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=sink, stderr=sink,
            env=environment, close_fds=True, start_new_session=True)
    return {"state": "OBSERVED", "operation": "launch", "effect": "APPLIED", "process_id": process.pid,
        "host_ref": row["host_ref"], "browser_id": row["browser_id"], "profile_directory": row["profile_directory"],
        "connectivity": "LAUNCH_REQUESTED", "launch_verified": False, "next_action": "status", "retry_allowed": False}


# This bootstrap verifies the complete immutable source before importing it.
# All coordinates below come from the host-owned inventory, never tool arguments.
REMOTE_BOOT = r'''import sys,json,hashlib,os,stat,re
from pathlib import Path
root,expected,bindings,host,profile=sys.argv[1:]
def owned(p):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  s=os.fstat(fd)
  if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_mode&0o022 or s.st_size>5000000:raise SystemExit(74)
  with os.fdopen(fd,"rb",closefd=False) as f:raw=f.read(5000001)
  a=os.fstat(fd)
  if len(raw)>5000000 or (s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(a.st_size,a.st_mtime_ns,a.st_ctime_ns):raise SystemExit(74)
  return raw
 finally:os.close(fd)
r=Path(root)
if r.is_symlink():raise SystemExit(73)
raw=owned(r/"BUILD.json")
if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit(72)
m=json.loads(raw)
if m.get("schema")!="mastermind.browser_direct_build.v1" or not re.fullmatch("[0-9a-f]{40}",m.get("source_commit","")) or not 1<=len(m.get("files",{}))<=300:raise SystemExit(74)
for name,digest in m["files"].items():
 p=r/name
 if Path(name).is_absolute() or ".." in Path(name).parts or p.is_symlink():raise SystemExit(73)
 if hashlib.sha256(owned(p)).hexdigest()!=digest:raise SystemExit(74)
sys.path.insert(0,root)
from integrations.hermes_harness import browser_routes as routes
d=routes.load(Path(bindings))
if d is None or d["local_host_ref"]!=host:raise SystemExit(75)
print(json.dumps({"state":"REMOTE_READY","host_ref":host,"source_commit":m["source_commit"]}),flush=True)
from integrations.hermes_harness.browser_bridge import main
raise SystemExit(main(["--bindings",bindings,"--profile",profile,"--local-only"]))
'''


def remote_call(host, envelope, profile_ref, *, timeout=31):
    command = [host["python_executable"], "-I", "-B", "-c", REMOTE_BOOT,
        host["source_root"], host["manifest_sha256"], host["bindings_path"], host["host_ref"], profile_ref]
    argv = ["/usr/bin/ssh", "-T", "-oBatchMode=yes", "-oStrictHostKeyChecking=yes", "-oUpdateHostKeys=no",
        "-oForwardAgent=no", "-oClearAllForwardings=yes", "-oControlMaster=no", "-oControlPath=none",
        "-oConnectionAttempts=1", "-oConnectTimeout=5", "-oServerAliveInterval=5", "-oServerAliveCountMax=1",
        host["ssh_alias"], shlex.join(command)]
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    except OSError:
        raise RouteError("REMOTE_SSH_UNAVAILABLE") from None
    start = time.monotonic(); sent = False
    try:
        ready = bytearray()
        while b"\n" not in ready:
            left = 7 - (time.monotonic() - start)
            if left <= 0 or not select.select([process.stdout], [], [], left)[0]:
                raise RouteError("REMOTE_HOST_UNAVAILABLE")
            chunk = os.read(process.stdout.fileno(), 1)
            if not chunk:
                try:
                    _, error = process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    raise RouteError("REMOTE_HELPER_UNAVAILABLE") from None
                error = error[:8192].decode("utf-8", "replace")
                if process.returncode in {72,73,74}:
                    raise RouteError("REMOTE_SOURCE_MISMATCH")
                if process.returncode == 75:
                    raise RouteError("REMOTE_HOST_IDENTITY_MISMATCH")
                if re.search(r"host key verification failed|REMOTE HOST IDENTIFICATION HAS CHANGED", error, re.I):
                    raise RouteError("REMOTE_HOST_KEY_REJECTED")
                if "Permission denied" in error:
                    raise RouteError("REMOTE_AUTHENTICATION_REQUIRED")
                if re.search(r"timed out|no route to host|connection refused|could not resolve", error, re.I):
                    raise RouteError("REMOTE_HOST_UNAVAILABLE")
                raise RouteError("REMOTE_HELPER_UNAVAILABLE")
            if len(ready) >= 4096:
                raise RouteError("REMOTE_HELPER_UNAVAILABLE")
            ready.extend(chunk)
        hello = decode(ready)
        if not isinstance(hello, dict) or hello.get("state") != "REMOTE_READY" or hello.get("host_ref") != host["host_ref"]:
            raise RouteError("REMOTE_HOST_IDENTITY_MISMATCH")
        payload = (json.dumps(envelope, separators=(",", ":"), allow_nan=False)+"\n").encode()
        if timeout-(time.monotonic()-start)<22:
            raise RouteError("REMOTE_BUDGET_EXHAUSTED")
        # From this point, an interrupted write may have delivered the action.
        sent = True
        stdout, stderr = process.communicate(payload, timeout=max(1, timeout-(time.monotonic()-start)))
        if process.returncode or len(stdout) > MAX_OUTPUT or stderr:
            raise RouteError("REMOTE_RESULT_UNAVAILABLE", possible=True)
        result = decode(stdout)
        if not isinstance(result, dict):
            raise RouteError("REMOTE_RESULT_INVALID", possible=True)
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        if isinstance(error, RouteError):
            raise
        raise RouteError("REMOTE_EFFECT_UNKNOWN" if sent else "REMOTE_HOST_UNAVAILABLE", possible=sent) from None
    finally:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        for stream in (process.stdin,process.stdout,process.stderr):
            if stream is not None:stream.close()


"""Fixed-file installation for the existing storage owner; never an enrollment grant.

No network entrypoint, cleanup, service action, preview invocation or retry.
Call only under separately authorized current host/source custody. Existing
transport can carry these exact reviewed bytes; arbitrary targets are refused.
"""
from __future__ import annotations

import fcntl
import base64
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import socket
import stat
import sys
import uuid

TARGETS = {"linux-preview": ("linux", "linux_cache_preview.py", ("preview", "retain_preview")),
           "m2-driver": ("darwin", "fleet_remote_sweep.py", ("run", "preview_linux_caches"))}
LIMIT = 32768
ABSENT = "ABSENT"


class InstallHeld(ValueError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(s):
    return (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _owned(s, uid, directory=False):
    if (s.st_uid != uid or s.st_mode & 0o022
            or (directory and not stat.S_ISDIR(s.st_mode))):
        raise InstallHeld("owner_or_mode")


def _directory(path, uid):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise InstallHeld("directory_identity")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        _owned(os.fstat(fd), uid, True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read(fd, name, uid):
    try:
        item = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(item)
        _owned(before, uid)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > LIMIT:
            raise InstallHeld("file_identity")
        raw = os.read(item, LIMIT + 1)
        named = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if len(raw) != before.st_size or _identity(before) != _identity(os.fstat(item)) or _identity(before) != _identity(named):
            raise InstallHeld("file_changed")
        return raw
    finally:
        os.close(item)


def _write_new(fd, name, raw):
    item = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    with os.fdopen(item, "wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    os.fsync(fd)


def _import_only(raw, role, filename):
    if type(raw) is not bytes or len(raw) > LIMIT:
        raise InstallHeld("payload_bound")
    # Accepted source is SHA-bound by the caller's release packet. Importing it
    # verifies the actual module; __main__ is never used, no preview/sweep called.
    namespace = {"__name__": "mastermind_storage_install_check", "__file__": filename}
    exec(compile(raw, filename, "exec"), namespace)
    if not all(callable(namespace.get(name)) for name in TARGETS[role][2]):
        raise InstallHeld("module_contract")
    return namespace


def _scope(role, binding, home, uid, platform, account, hostname):
    if role not in TARGETS or uid == 0 or platform != TARGETS[role][0]:
        raise InstallHeld("platform_or_role")
    if (type(binding) is not dict or set(binding) != {"account", "hostnames"}
            or binding["account"] != account or type(binding["hostnames"]) is not list
            or not binding["hostnames"] or len(binding["hostnames"]) > 8
            or any(type(v) is not str or not v for v in binding["hostnames"])
            or hostname not in binding["hostnames"]):
        raise InstallHeld("host_account_binding")
    home_fd = _directory(home, uid)
    os.close(home_fd)


def enrolled_binding(host, registry_bytes, ssh_config_bytes):
    """Resolve semantic host through public enrolled config, without ssh -G/I/O.

    Only literal, self-contained SSH Host blocks are supported here. Dynamic
    Include/Match configuration is unknown, never resolved by a subprocess.
    This records addressing/current-source evidence, not maintenance authority.
    """
    if host not in {"ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3", "ubuntu4"}:
        raise InstallHeld("host_not_enrolled")
    if len(registry_bytes) > 1024 * 1024 or len(ssh_config_bytes) > 65536:
        raise InstallHeld("public_config_bound")
    row = json.loads(registry_bytes)[host]
    alias = row.get("ssh_alias")
    names = row.get("hostnames")
    if (row.get("platform") != "linux" or type(alias) is not str
            or not alias or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in alias)
            or type(names) is not list or not names or len(names) > 8
            or any(type(n) is not str or not n for n in names)):
        raise InstallHeld("host_not_enrolled")
    selected, options, literal = False, {}, False
    for line in ssh_config_bytes.decode().splitlines():
        parts = shlex.split(line, comments=True)
        if not parts:
            continue
        key = parts[0].lower()
        if key in {"include", "match"}:
            raise InstallHeld("dynamic_ssh_config_unknown")
        if key == "host":
            if any(p.startswith("!") for p in parts[1:]):
                raise InstallHeld("dynamic_ssh_config_unknown")
            selected = any(fnmatch.fnmatchcase(alias, p) for p in parts[1:])
            literal |= alias in parts[1:]
        elif selected and key in {"hostname", "user", "port"}:
            if len(parts) != 2:
                raise InstallHeld("ssh_binding_unknown")
            options.setdefault(key, parts[1])  # SSH's first-value semantics.
    account = options.get("user")
    address = options.get("hostname")
    if (not literal or not account or not address or account == "root"
            or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in account + address)
            or options.get("port", "22") != "22"):
        raise InstallHeld("ssh_binding_unknown")
    return {"host": host, "alias": alias, "address": address,
            "binding": {"account": account, "hostnames": names},
            "registry_sha256": digest(registry_bytes), "ssh_config_sha256": digest(ssh_config_bytes),
            "maintenance_authorized": False}


def transport_plan(driver, host, registry_bytes, ssh_config_bytes, *, kind,
                   payload=None, expected_before=None, operation_id=None,
                   expected_installer_sha=None):
    """Prepare ONE existing-transport argv; never dispatch it or discover a host.

    Missing remote preimage stays unknown: install planning requires its actual
    separately observed SHA/ABSENT; inspect planning makes no such assertion.
    """
    binding = enrolled_binding(host, registry_bytes, ssh_config_bytes)
    if kind not in {"inspect", "install", "preview"}:
        raise InstallHeld("operation_kind")
    request = {"binding": binding["binding"], "role": "linux-preview"}
    if kind == "install":
        if expected_before is None or payload is None or operation_id is None:
            raise InstallHeld("remote_preimage_unknown")
        request.update(payload=base64.b64encode(payload).decode(), expected_before=expected_before,
                       expected_after=digest(payload), operation_id=operation_id)
    if kind == "preview":
        original = shlex.split(driver.linux_cache_preview_command())
        code = ("import pwd,os,socket\nb=" + repr(binding["binding"]) + "\n"
                "if pwd.getpwuid(os.getuid()).pw_name!=b['account'] or socket.gethostname() not in b['hostnames']: raise SystemExit(78)\n"
                + original[2])
        command = shlex.join(["python3", "-c", code, original[3]])
    else:
        # The pin comes from the already-qualified release packet, never from
        # hashing a newly read file and trusting that same fresh value.
        if (type(expected_installer_sha) is not str or len(expected_installer_sha) != 64
                or any(c not in "0123456789abcdef" for c in expected_installer_sha)):
            raise InstallHeld("installer_source_pin")
        parent_fd = _directory(Path(__file__).parent, os.getuid())
        try:
            source = _read(parent_fd, Path(__file__).name, os.getuid())
        finally:
            os.close(parent_fd)
        if source is None or digest(source) != expected_installer_sha:
            raise InstallHeld("installer_source_pin")
        code = ("import base64,hashlib,json\nraw=base64.b64decode(" + repr(base64.b64encode(source).decode()) + ")\n"
                "if hashlib.sha256(raw).hexdigest()!=" + repr(expected_installer_sha) + ": raise SystemExit(78)\n"
                "n={'__name__':'mastermind_install_transport','__file__':'preview_install.py'}\nexec(compile(raw,'preview_install.py','exec'),n)\n"
                "r=json.loads(" + repr(json.dumps(request)) + ")\n")
        if kind == "inspect":
            code += "result=n['inspect_target'](**r)\n"
        else:
            code += "r['payload']=base64.b64decode(r['payload']);result=n['install'](**r)\n"
        code += "print(json.dumps(result,sort_keys=True))\n"
        command = shlex.join(["python3", "-c", code])
    return {"kind": kind, "target": binding, "argv": driver.SSH + [binding["alias"], command],
            "timeout": 20, "dispatch_authorized": False, "remote_preimage": expected_before}


def _prior_install_hold(fd, uid):
    count = 0
    with os.scandir(fd) as entries:
        for entry in entries:
            count += 1
            if count > 20000:
                raise InstallHeld("install_history_unknown")
            if not (entry.name.startswith("preview-install-") and entry.name.endswith(".json")):
                continue
            before = json.loads(_read(fd, entry.name, uid))
            terminal = _read(fd, entry.name + ".verified", uid)
            unknown = _read(fd, entry.name + ".unknown", uid)
            if (unknown is not None or terminal is None or json.loads(terminal) != dict(before, state="VERIFIED")):
                raise InstallHeld("prior_install_unknown_no_replay")
            # A written terminal artifact alone cannot prove its final fence or
            # directory fsync succeeded. This installer is deliberately one-shot:
            # ALL prior records need fresh owner reconciliation before a new ID.
            raise InstallHeld("prior_install_record_requires_reconciliation")


def inspect_target(role, binding, *, home=None, uid=None, platform=None, account=None, hostname=None):
    """Fixed target preimage only; no directories/files created or module imported."""
    home = Path.home() if home is None else Path(home)
    uid = os.getuid() if uid is None else uid
    _scope(role, binding, home, uid, sys.platform if platform is None else platform,
           pwd.getpwuid(uid).pw_name if account is None else account,
           socket.gethostname() if hostname is None else hostname)
    fd = _directory(home / ".local/lib/mastermind/storage-cleanup", uid)
    try:
        raw = _read(fd, TARGETS[role][1], uid)
        return {"role": role, "preimage": ABSENT if raw is None else digest(raw)}
    finally:
        os.close(fd)


def install(role, binding, payload, expected_before, expected_after, operation_id, *,
            home=None, uid=None, platform=None, account=None, hostname=None):
    """One fixed-file CAS operation. An existing receipt is never replayed.

    PREPARED/UNKNOWN must be reconciled by the same owner; no automatic rollback.
    Fixture keyword injection is Python-only, not an alternate host grant.
    """
    home = Path.home() if home is None else Path(home)
    uid = os.getuid() if uid is None else uid
    _scope(role, binding, home, uid, sys.platform if platform is None else platform,
           pwd.getpwuid(uid).pw_name if account is None else account,
           socket.gethostname() if hostname is None else hostname)
    if (type(operation_id) is not str or uuid.UUID(operation_id).hex != operation_id
            or type(expected_before) is not str
            or (expected_before != ABSENT and (len(expected_before) != 64 or any(c not in "0123456789abcdef" for c in expected_before)))
            or type(payload) is not bytes or digest(payload) != expected_after):
        raise InstallHeld("source_or_operation_binding")
    name = TARGETS[role][1]
    module = _import_only(payload, role, str(home / ".local/lib/mastermind/storage-cleanup" / name))
    toolkit = home / ".local/lib/mastermind/storage-cleanup"
    state = home / ".local/state/mastermind/storage-cleanup"
    directory = _directory(toolkit, uid)
    state_fd = lock_fd = active_fd = None
    driver_lock = False
    effect_started = False
    receipt_name = "preview-install-" + operation_id + ".json"
    stage_name = "." + name + ".stage-" + operation_id
    backup_name = name + ".before-" + operation_id
    try:
        state_fd = _directory(state, uid)
        if role == "linux-preview":
            active = (home / "lanes/ext/active").resolve(strict=True)
            active_fd = module["_directory"](active, uid)
            lock_fd = os.open(".admission.lock", os.O_RDWR | os.O_NOFOLLOW, dir_fd=active_fd)
            lock = os.fstat(lock_fd)
            _owned(lock, uid)
            if not stat.S_ISREG(lock.st_mode) or lock.st_nlink != 1:
                raise InstallHeld("lock_identity")
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            active_before = os.fstat(active_fd)
            def current():
                module["_admission_current"](home, active, active_fd, active_before, lock_fd, lock, uid)
            current()
        else:
            # Existing driver lock, no stale-lock deletion or PID inference.
            lock_fd = os.open("fleet-remote-sweep.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              0o600, dir_fd=state_fd)
            driver_lock = True
            os.write(lock_fd, json.dumps({"pid": os.getpid()}).encode())
            os.fsync(lock_fd)
            def current():
                if _identity(os.fstat(lock_fd)) != _identity(os.stat("fleet-remote-sweep.lock", dir_fd=state_fd, follow_symlinks=False)):
                    raise InstallHeld("lock_identity")
        def namespace():
            for path, held in ((toolkit, directory), (state, state_fd)):
                check = _directory(path, uid)
                try:
                    if _identity(os.fstat(check))[:4] != _identity(os.fstat(held))[:4]:
                        raise InstallHeld("directory_identity")
                finally:
                    os.close(check)
            current()
        namespace()
        _prior_install_hold(state_fd, uid)
        before = _read(directory, name, uid)
        if (ABSENT if before is None else digest(before)) != expected_before:
            raise InstallHeld("preimage_changed")
        if before == payload:
            raise InstallHeld("already_installed_no_replay")
        receipt = {"schema": "mastermind.storage_preview_install.v1", "operation_id": operation_id,
                   "role": role, "before": expected_before, "after": expected_after,
                   "state": "PREPARED", "backup": backup_name if before is not None else None}
        # Existing operation IDs, including incomplete/unknown, stop before effect.
        _write_new(state_fd, receipt_name, json.dumps(receipt, sort_keys=True).encode())
        if before is not None:
            _write_new(directory, backup_name, before)
        _write_new(directory, stage_name, payload)
        namespace()
        if _read(directory, name, uid) != before:
            raise InstallHeld("preimage_changed")
        effect_started = True
        if before is None:
            # Atomic no-replace when the qualified preimage was ABSENT.
            os.link(stage_name, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.unlink(stage_name, dir_fd=directory)
        else:
            os.replace(stage_name, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        namespace()
        installed = _read(directory, name, uid)
        if installed != payload:
            raise InstallHeld("postimage_changed")
        _import_only(installed, role, str(toolkit / name))
        namespace()
        receipt["state"] = "VERIFIED"
        # Never overwrite the write-ahead receipt: a separate terminal artifact
        # preserves PREPARED across a crash or postimage failure.
        _write_new(state_fd, receipt_name + ".verified", json.dumps(receipt, sort_keys=True).encode())
        namespace()
        return receipt
    except BaseException as exc:
        if effect_started:
            # A late fence can fail after terminal bytes were written. Preserve
            # that evidence, but an UNKNOWN companion dominates it on reopen.
            try:
                _write_new(state_fd, receipt_name + ".unknown", b'{"state":"UNKNOWN"}')
            except OSError:
                pass  # The caller's same-operation UNKNOWN still forbids replay.
            raise InstallHeld("install_effect_unknown_no_replay") from exc
        raise
    finally:
        if driver_lock:
            # Release only this exact original lock; replacement remains held.
            try:
                if _identity(os.fstat(lock_fd)) == _identity(os.stat("fleet-remote-sweep.lock", dir_fd=state_fd, follow_symlinks=False)):
                    os.unlink("fleet-remote-sweep.lock", dir_fd=state_fd)
            except OSError:
                pass
        for fd in (lock_fd, active_fd, state_fd, directory):
            if fd is not None:
                os.close(fd)

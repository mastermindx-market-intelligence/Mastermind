"""Typed persistent Workbench Browser SDK under the incumbent sealed runtime owner.

No Browser grants, service lifecycle, Company control, or credential issuance lives
here. Provisioning publishes a new immutable dependency generation; serving uses
only the current Chrome user's fixed Workbench configuration.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
from datetime import datetime, timezone
from uuid import uuid4

from ops.executive_os import company_mcp_edge as owner

SCHEMA = owner.WORKBENCH_SCHEMA
RECEIPT = owner.WORKBENCH_RECEIPT
LOCK_RELATIVE = owner.WORKBENCH_LOCK_RELATIVE
ENTRY_RELATIVE = "ops/executive_os/workbench_mcp_runtime.py"
BINDING_KEYS = {"schema", "release_sha", "service_uid", "entry_sha256", "receipt_sha256"}
BASE_KEYS = {"runtime_root", "python_binary", "python_binary_sha256",
             "python_framework_sha256", "python_version", "team_identifier"}
BOOTSTRAP = ("import sys;sys.path.insert(0,sys.argv.pop(1));"
             "from ops.executive_os.workbench_mcp_runtime import main;"
             "raise SystemExit(main())")


def _identity(release_sha, service_uid):
    if (type(release_sha) is not str or re.fullmatch("[0-9a-f]{40}", release_sha) is None
            or type(service_uid) is not int or service_uid < 501):
        raise owner.EdgeError("Workbench runtime identity differs")
    source = owner.SYSTEM / "releases" / release_sha
    runtime = owner.SYSTEM / "workbench-mcp-runtimes" / str(service_uid) / release_sha
    binding = owner.SYSTEM / "config/workbench-browser-runtimes" / str(service_uid) / (release_sha + ".json")
    return source, runtime, binding


def _read(path):
    owner.sealed(path)
    if stat.S_IMODE(path.stat().st_mode) != 0o444 or path.stat().st_size > 65536:
        raise owner.EdgeError("Workbench runtime receipt custody differs")
    def closed(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise owner.EdgeError("Workbench runtime duplicate field")
            result[key] = value
        return result
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=closed)
    except (ValueError, UnicodeError) as error:
        raise owner.EdgeError("Workbench runtime receipt invalid") from error
    if type(value) is not dict:
        raise owner.EdgeError("Workbench runtime receipt invalid")
    return value


def _binding(source, runtime, service_uid):
    return dict(schema=SCHEMA, release_sha=source.name, service_uid=service_uid,
                entry_sha256=owner.digest(source / ENTRY_RELATIVE),
                receipt_sha256=owner.digest(runtime / RECEIPT))


def verify(release_sha, service_uid, *, binding=None):
    source, runtime, binding_path = _identity(release_sha, service_uid)
    evidence = owner._source_evidence_at(source, LOCK_RELATIVE)
    config = _read(binding_path) if binding is None else binding
    if (type(config) is not dict or set(config) != BINDING_KEYS
            or config["schema"] != SCHEMA or config["release_sha"] != release_sha
            or type(config["service_uid"]) is not int or config["service_uid"] != service_uid
            or any(type(config[k]) is not str or re.fullmatch("[0-9a-f]{64}", config[k]) is None
                   for k in ("entry_sha256", "receipt_sha256"))
            or config["entry_sha256"] != owner.digest(source / ENTRY_RELATIVE)):
        raise owner.EdgeError("Workbench runtime binding differs")
    owner.sealed(runtime, directory=True)
    if (runtime / owner.INCOMPLETE).exists() or (runtime / owner.INCOMPLETE).is_symlink():
        raise owner.EdgeError("Workbench runtime is incomplete")
    raw = _read(runtime / RECEIPT)
    if (set(raw) != {"schema", "source", "base", "service_uid", "inventory_sha256",
                    "inventory_entries", "pip_check_passed"}
            or raw["schema"] != SCHEMA or raw["source"] != evidence
            or type(raw["service_uid"]) is not int or raw["service_uid"] != service_uid
            or raw["pip_check_passed"] is not True
            or owner.digest(runtime / RECEIPT) != config["receipt_sha256"]):
        raise owner.EdgeError("Workbench runtime receipt binding differs")
    owner.verify_base(raw["base"])
    entries = owner.inventory(runtime, kind="workbench-browser")
    if (raw["inventory_sha256"] != hashlib.sha256(owner.encoded(entries)).hexdigest()
            or type(raw["inventory_entries"]) is not int or raw["inventory_entries"] != len(entries)):
        raise owner.EdgeError("Workbench runtime inventory differs")
    return {
        "schema": SCHEMA, "release_sha": release_sha, "service_uid": service_uid,
        "source": evidence, "runtime_root": str(runtime),
        "python_executable": str(runtime / "bin/python3.12"),
        "entry_sha256": config["entry_sha256"], "receipt_sha256": config["receipt_sha256"],
        "inventory_sha256": raw["inventory_sha256"], "base": raw["base"],
    }


def _directory(path):
    if not path.exists() and not path.is_symlink():
        path.mkdir(mode=0o755)
        path.chmod(0o755)
        owner.fsync_directory(path.parent)
    owner.sealed(path, directory=True)
    if stat.S_IMODE(path.stat().st_mode) != 0o755:
        raise owner.EdgeError("Workbench runtime parent traversal differs")


def _archive_incomplete(runtime, service_uid):
    owner.sealed(runtime, directory=True)
    marker = runtime / owner.INCOMPLETE
    if marker.exists() or marker.is_symlink():
        owner.sealed(marker)
    elif stat.S_IMODE(runtime.stat().st_mode) != 0o700 or any(runtime.iterdir()):
        raise owner.EdgeError("Workbench recovery requires incomplete evidence")
    archive = owner.SYSTEM / "workbench-mcp-runtime-archive"
    _directory(archive)
    archive = archive / str(service_uid)
    _directory(archive)
    target = archive / (runtime.name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        + "-" + uuid4().hex)
    before = runtime.lstat()
    if target.exists() or target.is_symlink():
        raise owner.EdgeError("Workbench recovery target exists")
    if (runtime.lstat().st_dev, runtime.lstat().st_ino) != (before.st_dev, before.st_ino):
        raise owner.EdgeError("Workbench recovery source changed")
    runtime.rename(target)
    owner.fsync_directory(runtime.parent)
    owner.fsync_directory(archive)
    return {"schema": SCHEMA, "recovery": "ARCHIVED_INCOMPLETE", "archive": str(target)}


def provision(release_sha, service_uid, *, recover_incomplete=False):
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise owner.EdgeError("Workbench runtime provisioner requires root on macOS")
    source, runtime, binding_path = _identity(release_sha, service_uid)
    if source != owner.SOURCE:
        raise owner.EdgeError("Workbench provisioner must run from the selected sealed release")
    # Resolve a real user; this grants no access to that user's browser or files.
    user = pwd.getpwuid(service_uid)
    if not user.pw_dir.startswith("/Users/") or user.pw_uid != service_uid:
        raise owner.EdgeError("Workbench runtime requires the enrolled Chrome user")
    evidence = owner._source_evidence_at(source, LOCK_RELATIVE)
    owner.run(["/bin/bash", source / "ops/executive_os/provision-python-runtime.sh", "--verify-only"])
    prior_umask = os.umask(0o077)
    try:
        for parent in (runtime.parent.parent, runtime.parent,
                       binding_path.parent.parent, binding_path.parent):
            _directory(parent)
        lock = runtime.parent / ".provision.lock"
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            def qualify_lock():
                info, named = os.fstat(descriptor), lock.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                        or info.st_nlink != 1 or info.st_size != 0
                        or stat.S_IMODE(info.st_mode) != 0o600
                        or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)):
                    raise owner.EdgeError("Workbench runtime provision lock differs")
            qualify_lock()
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            qualify_lock()
            if binding_path.exists() or binding_path.is_symlink():
                if recover_incomplete:
                    raise owner.EdgeError("Workbench recovery refuses a published binding")
                return verify(release_sha, service_uid)
            if recover_incomplete:
                return _archive_incomplete(runtime, service_uid)
            if runtime.exists() or runtime.is_symlink():
                binding = _binding(source, runtime, service_uid)
                result = verify(release_sha, service_uid, binding=binding)
                owner.publish(binding_path, binding)
                return result
            owner._materialize_sdk(runtime, evidence, {"service_uid": service_uid},
                                   kind="workbench-browser")
            binding = _binding(source, runtime, service_uid)
            result = verify(release_sha, service_uid, binding=binding)
            owner.publish(binding_path, binding)
            return result
        finally:
            os.close(descriptor)
    finally:
        os.umask(prior_umask)


def configuration_path(service_uid):
    if service_uid != os.geteuid():
        raise owner.EdgeError("Workbench serving requires the Chrome user")
    user = pwd.getpwuid(service_uid)
    return Path(user.pw_dir) / ".local/share/mastermind-workbench-browser/config.json"


def launch_argv(release_sha, service_uid):
    source, _, _ = _identity(release_sha, service_uid)
    return [str(owner.BASE_PYTHON), "-I", "-S", "-B", "-c", BOOTSTRAP,
            str(source), "serve", "--release", release_sha]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("provision", "recover-incomplete", "verify", "serve", "sdk-serve",
                                            "lifecycle", "sdk-lifecycle"))
    parser.add_argument("--release", required=True)
    parser.add_argument("--service-uid", type=int)
    parser.add_argument("--operation", choices=("preview", "stage", "start", "inspect", "stop"))
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--expected-install-sha256")
    args = parser.parse_args(argv)
    lifecycle_args = []
    if args.command in {"lifecycle", "sdk-lifecycle"}:
        if args.operation is None or args.service_uid is not None:
            parser.error("lifecycle requires one operation for the current Chrome user")
        lifecycle_args = ["workbench-" + args.operation]
        if args.operation in {"preview", "stage"}:
            lifecycle_args += ["--release", args.release]
        if args.operation == "stage":
            if args.expected_plan_sha256 is None or args.expected_install_sha256 is not None:
                parser.error("stage requires only the reviewed plan digest")
            lifecycle_args += ["--expected-plan-sha256", args.expected_plan_sha256]
        elif args.operation in {"start", "stop"}:
            if args.expected_install_sha256 is None or args.expected_plan_sha256 is not None:
                parser.error("start/stop require only the installed generation digest")
            lifecycle_args += ["--expected-install-sha256", args.expected_install_sha256]
        elif args.expected_plan_sha256 is not None or args.expected_install_sha256 is not None:
            parser.error("preview/inspect do not accept effect digests")
    elif any(value is not None for value in (args.operation, args.expected_plan_sha256, args.expected_install_sha256)):
        parser.error("lifecycle options require the lifecycle command")
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        raise owner.EdgeError("Workbench runtime requires isolated Python without site or bytecode")
    uid = os.geteuid() if args.service_uid is None else args.service_uid
    if args.command in {"provision", "recover-incomplete"}:
        result = provision(args.release, uid, recover_incomplete=args.command == "recover-incomplete")
        print(json.dumps(result, sort_keys=True))
        return 0
    qualified = verify(args.release, uid)
    if args.command == "verify":
        print(json.dumps(qualified, sort_keys=True))
        return 0
    if args.service_uid is not None or uid < 501:
        raise owner.EdgeError("Workbench serve cannot select another user")
    source, runtime, _ = _identity(args.release, uid)
    if source != owner.SOURCE:
        raise owner.EdgeError("Workbench serving source differs")
    python = runtime / "bin/python3.12"
    if args.command in {"serve", "lifecycle"}:
        if Path(sys.executable).absolute() != owner.BASE_PYTHON:
            raise owner.EdgeError("Workbench bootstrap interpreter differs")
        next_args = ["sdk-" + args.command, "--release", args.release]
        if args.command == "lifecycle":
            next_args += ["--operation", args.operation]
            if args.expected_plan_sha256 is not None:
                next_args += ["--expected-plan-sha256", args.expected_plan_sha256]
            if args.expected_install_sha256 is not None:
                next_args += ["--expected-install-sha256", args.expected_install_sha256]
        os.execve(python, [str(python), "-I", "-S", "-B", "-c", BOOTSTRAP,
                          str(source), *next_args], owner.ENV)
    if (Path(sys.executable).absolute() != python
            or Path(sys.base_prefix) != owner.BASE_PYTHON.parents[1]):
        raise owner.EdgeError("Workbench SDK interpreter differs")
    # -S avoids every site hook; the immutable inventory was checked above.
    site_packages = runtime / "lib/python3.12/site-packages"
    owner.sealed(site_packages, directory=True)
    sys.path.insert(1, str(site_packages))
    if args.command == "sdk-lifecycle":
        from integrations.studio_direct_mcp.private_service import main as lifecycle_main
        return lifecycle_main(lifecycle_args)
    from integrations.studio_direct_mcp.workbench_host_service import target, _verify_install
    from integrations.workbench_action_mcp.acquisition import projection
    manifest, _ = _verify_install(target())
    plan = manifest["plan"]
    if plan["release_sha"] != args.release:
        raise owner.EdgeError("Workbench installed service generation differs")
    from integrations.workbench_action_mcp.service import run_configured_service
    return run_configured_service(
        str(configuration_path(uid)), expected_browser_source=str(source),
        expected_browser_python=str(python),
        expected_acquisition=projection(plan["config_sha256"], plan["persistent"], plan["dependencies"]),
    )


if __name__ == "__main__":
    raise SystemExit(main())

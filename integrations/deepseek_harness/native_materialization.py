"""Finite native artifact subroutine of the existing package/installer owner.

No service, account, profile, enrollment, selector, receipt or provider is
created here. Interrupted private siblings remain with their original names.
"""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess

from control_plane import native_provider_attestation as att
from ops.executive_os import control_aead_profile as custody
from ops.executive_os.capacity_host_artifacts import _rename_exclusive


class NativeMaterializationPending(ValueError):
    """Private preparation is retained; consult the original per-target facts."""


class NativeMaterializationUnknown(RuntimeError):
    """A namespace publication was attempted; reconcile the original targets."""


def _path(value):
    path = att._deepseek_path(str(value))
    if path == Path("/") or any(ord(c) < 32 or ord(c) == 127 for c in str(path)):
        raise ValueError("native materialization coordinate refused")
    return path


def _stage(path):
    name = "." + path.name + ".native-materialization.stage"
    if len(os.fsencode(name)) > 255:
        raise ValueError("native materialization stage name exceeds its bound")
    return path.parent / name


def _entry(path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _stable(info):
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode


def _identity(info):
    return att._identity(info)


def _same_location(left, right):
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


@contextlib.contextmanager
def _operator_object(path, uid, *, directory):
    """Hold every original ancestor; no untrusted path component is followed."""
    path = _path(path)
    descriptors, links = [], []
    try:
        base = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptors.append(base)
        for index, name in enumerate(path.parts[1:]):
            leaf = index == len(path.parts) - 2
            before = os.stat(name, dir_fd=base, follow_symlinks=False)
            is_directory = directory if leaf else True
            if not (stat.S_ISDIR(before.st_mode) if is_directory else stat.S_ISREG(before.st_mode)):
                raise ValueError("operator artifact path is redirected or special")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if is_directory:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=base)
            descriptors.append(child)
            if _identity(os.fstat(child)) != _identity(before):
                raise ValueError("operator artifact changed while opening")
            links.append((base, name, child, before, leaf))
            base = child
        before = os.fstat(base)
        if before.st_uid != uid or (not directory and before.st_nlink != 1):
            raise ValueError("operator artifact ownership differs")
        if att.has_macos_acl(path, expected_identity=before, descriptor=base):
            raise ValueError("operator artifact has an ACL")
        def current():
            for parent, name, held, expected, leaf in links:
                compare = _identity if leaf else _stable
                if (compare(os.fstat(held)) != compare(expected)
                        or compare(os.stat(name, dir_fd=parent, follow_symlinks=False)) != compare(expected)):
                    raise ValueError("operator artifact or original ancestor changed")
        current()
        yield base, before, current
        current()
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _read_child(fd, root, name, uid, *, maximum, mode):
    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != uid or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != mode or not 0 < before.st_size <= maximum):
        raise ValueError("operator artifact member custody refused")
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
    try:
        if (_identity(os.fstat(child)) != _identity(before)
                or att.has_macos_acl(root/name, expected_identity=before, descriptor=child)):
            raise ValueError("operator artifact member changed")
        raw = att._read(child, maximum)
        if (len(raw) != before.st_size or _identity(os.fstat(child)) != _identity(before)
                or _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(before)):
            raise ValueError("operator artifact member changed during read")
        return raw
    finally:
        os.close(child)


def _manifest(raw):
    value = json.loads(raw, object_pairs_hook=att._pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite manifest")))
    if (type(value) is not dict or set(value) != {"schema", "donor_sha", "files", "installed"}
            or value["schema"] != "mastermind.dsh_attended_package_closure.v1"
            or value["donor_sha"] != att.DSH_DONOR_SHA or value["installed"] is not False
            or type(value["files"]) is not dict or not 0 < len(value["files"]) < att._DSH_ENTRIES):
        raise ValueError("native package manifest refused")
    for name, row in value["files"].items():
        path = PurePosixPath(name)
        if (not name or name in (".", "package-manifest.json") or str(path) != name
                or path.is_absolute() or ".." in path.parts
                or len(os.fsencode(name)) > att._DSH_PATH_BYTES
                or any(ord(c) < 32 or ord(c) == 127 for c in name) or type(row) is not dict):
            raise ValueError("native package member path refused")
        if set(row) == {"symlink"}:
            target = row["symlink"]
            if (type(target) is not str or not target or Path(target).is_absolute()
                    or len(os.fsencode(target)) > att._DSH_PATH_BYTES or "\x00" in target):
                raise ValueError("native package link refused")
        elif (set(row) != {"sha256", "mode"} or not att._deepseek_digest(row["sha256"])
                or type(row["mode"]) is not int or row["mode"] not in (0o444, 0o555)):
            raise ValueError("native package file contract refused")
    return value


def _layout(config, original):
    if (config.get("state") is not None or config.get("state_owner") != "original-worker"
            or config.get("release") != original["deepseek_release"]
            or config.get("node") != original["deepseek_node_binary"]
            or config.get("node_sha256") != original["native_realm_enrollment"]["provider_binary_sha256"]):
        raise ValueError("native package differs from original Worker coordinates")
    return config


def _candidate(candidate, uid, accepted, original):
    with _operator_object(candidate, uid, directory=True) as (fd, before, current):
        if stat.S_IMODE(before.st_mode) != 0o755:
            raise ValueError("native package candidate root mode differs")
        raw = _read_child(fd, candidate, "package-manifest.json", uid,
                          maximum=att._DSH_MANIFEST_BYTES, mode=0o444)
        if hashlib.sha256(raw).hexdigest() != accepted["package_manifest_sha256"]:
            raise ValueError("native package differs from protected build")
        manifest = _manifest(raw)
        config_raw = _read_child(fd, candidate, "app.json", uid, maximum=65536, mode=0o444)
        if hashlib.sha256(config_raw).hexdigest() != accepted["app_config_sha256"]:
            raise ValueError("native app config differs from protected build")
        config = _layout(json.loads(config_raw, object_pairs_hook=att._pairs), original)
        if "com.mastermind.deepseek.web.plist" in manifest["files"]:
            raise ValueError("native Worker package cannot install another service owner")
        current()
        return raw, manifest, config, _identity(before)


def _copy_file(source_fd, target_fd, before, expected_digest):
    copied, digest = 0, hashlib.sha256()
    while True:
        block = os.read(source_fd, min(1024 * 1024, before.st_size + 1 - copied))
        if not block:
            break
        copied += len(block)
        if copied > before.st_size:
            raise ValueError("operator artifact grew during copy")
        digest.update(block)
        view = memoryview(block)
        while view:
            written = os.write(target_fd, view)
            if written <= 0:
                raise OSError("native artifact short write")
            view = view[written:]
    if copied != before.st_size or digest.hexdigest() != expected_digest:
        raise ValueError("native artifact bytes differ from accepted input")
    os.fchown(target_fd, att._ROOT_UID, 0)
    os.fsync(target_fd)


def _copy_package(candidate, stage, uid, raw, manifest, root_identity, target_fd):
    expected = {**manifest["files"], "package-manifest.json":
        {"sha256": hashlib.sha256(raw).hexdigest(), "mode": 0o444}}
    seen, entries = set(), {}
    count, size = 0, 0
    def walk(source_fd, target_fd, path, relative, depth):
        nonlocal count, size
        before = os.fstat(source_fd)
        if (depth > att._DSH_DEPTH or before.st_uid != uid
                or stat.S_IMODE(before.st_mode) != 0o755
                or att.has_macos_acl(path, expected_identity=before, descriptor=source_fd)):
            raise ValueError("native package directory custody refused")
        count += 1
        entries[relative or "."] = {"kind": "directory"}
        names = []
        with os.scandir(source_fd) as stream:
            for entry in stream:
                names.append(entry.name)
                if len(names) + count > att._DSH_ENTRIES:
                    raise ValueError("native package exceeds entry bound")
        for name in sorted(names):
            rel = name if not relative else relative + "/" + name
            if len(os.fsencode(rel)) > att._DSH_PATH_BYTES:
                raise ValueError("native package exceeds path bound")
            info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
            child_path = path/name
            if info.st_uid != uid:
                raise ValueError("native package member belongs to another owner")
            if stat.S_ISLNK(info.st_mode):
                count += 1
                target = os.readlink(name, dir_fd=source_fd)
                if (expected.get(rel) != {"symlink": target} or info.st_nlink != 1
                        or att.has_macos_acl(child_path, expected_identity=info, allow_symlink=True)):
                    raise ValueError("native package link differs")
                os.symlink(target, name, dir_fd=target_fd)
                os.chown(name, att._ROOT_UID, 0, dir_fd=target_fd, follow_symlinks=False)
                seen.add(rel)
                entries[rel] = {"kind": "symlink", "target": target}
            else:
                directory = stat.S_ISDIR(info.st_mode)
                if not directory and not stat.S_ISREG(info.st_mode):
                    raise ValueError("native package contains a special object")
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
                source_child = os.open(name, flags | (os.O_DIRECTORY if directory else 0), dir_fd=source_fd)
                try:
                    if (_identity(os.fstat(source_child)) != _identity(info)
                            or att.has_macos_acl(child_path, expected_identity=info, descriptor=source_child)):
                        raise ValueError("native package member changed while opening")
                    if directory:
                        os.mkdir(name, mode=0o700, dir_fd=target_fd)
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=target_fd)
                        try:
                            walk(source_child, child, child_path, rel, depth+1)
                            os.fchown(child, att._ROOT_UID, 0)
                            os.fchmod(child, 0o755)
                            os.fsync(child)
                        finally:
                            os.close(child)
                    else:
                        count += 1
                        row = expected.get(rel)
                        size += info.st_size
                        if (row is None or set(row) != {"sha256", "mode"} or info.st_nlink != 1
                                or stat.S_IMODE(info.st_mode) != row["mode"] or size > att._DSH_BYTES):
                            raise ValueError("native package file custody or budget differs")
                        child = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                        0o600, dir_fd=target_fd)
                        try:
                            _copy_file(source_child, child, info, row["sha256"])
                            os.fchmod(child, row["mode"])
                            os.fsync(child)
                        finally:
                            os.close(child)
                        seen.add(rel)
                        entries[rel] = {"kind": "file"}
                    if _identity(os.fstat(source_child)) != _identity(info):
                        raise ValueError("native package member changed during copy")
                finally:
                    os.close(source_child)
            if (count > att._DSH_ENTRIES
                    or _identity(os.stat(name, dir_fd=source_fd, follow_symlinks=False)) != _identity(info)):
                raise ValueError("native package member changed or exceeded bound")
        if _identity(os.fstat(source_fd)) != _identity(before):
            raise ValueError("native package directory changed during copy")
    with _operator_object(candidate, uid, directory=True) as (source_fd, before, current):
        if _identity(before) != root_identity:
            raise ValueError("native package candidate root moved")
        walk(source_fd, target_fd, candidate, "", 0)
        if seen != set(expected):
            raise ValueError("native package closure has missing or extra members")
        att._deepseek_links(entries, stage)
        current()
        os.fchown(target_fd, att._ROOT_UID, 0)
        os.fchmod(target_fd, 0o755)
        os.fsync(target_fd)


def _node(path, digest):
    observation = att._file_observation(path, content=True)
    if observation["sha256"] != digest or observation["identity"]["mode"] != 0o555:
        raise ValueError("root native Node differs from original enrollment")
    result = subprocess.run(["/usr/bin/otool", "-L", str(path)], check=True,
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15,
        env={"PATH": "/usr/bin:/bin", "HOME": "/var/empty", "LANG": "C"})
    lines = result.stdout.splitlines()
    dependencies = [line.strip().split(" (", 1)[0] for line in lines[1:]]
    if (not dependencies or any(not item.startswith(("/usr/lib/", "/System/Library/"))
                                for item in dependencies)):
        raise ValueError("native Node requires system-only Mach-O dependencies")
    # This inspects the signed image; it does not execute the candidate Node.
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(path)], check=True,
        capture_output=True, stdin=subprocess.DEVNULL, timeout=30,
        env={"PATH": "/usr/bin:/bin", "HOME": "/var/empty", "LANG": "C"})
    if att._runtime_identity(path) != observation["identity"]:
        raise ValueError("native Node changed during qualification")
    return {"path": str(path), "sha256": digest, "identity": observation["identity"],
            "dependencies": dependencies, "node_executed": False}


def _package(path, original, source_repo, source_sha, *, stage=False):
    from .package_attended import qualify_native_worker_package
    before = att._deepseek_tree(path, content=True)
    raw, manifest = att._deepseek_manifest(path)
    files = dict(before["files"])
    files.pop("package-manifest.json", None)
    if (files != manifest["files"] or "com.mastermind.deepseek.web.plist" in files):
        raise ValueError("root native package closure differs")
    _layout(json.loads((path/"app.json").read_bytes(), object_pairs_hook=att._pairs), original)
    kwargs = {"_installation_root": Path(original["deepseek_release"])} if stage else {}
    qualified = qualify_native_worker_package(
        release=path, source_repo=source_repo, source_sha=source_sha, **kwargs)
    expected_schema = ("mastermind.dsh_native_worker_stage_qualification/v1" if stage
                       else "mastermind.dsh_native_worker_qualification/v1")
    if (qualified["schema"] != expected_schema
            or qualified["package_manifest_sha256"] != hashlib.sha256(raw).hexdigest()
            or att._deepseek_tree(path)["identity_sha256"] != before["identity_sha256"]):
        raise ValueError("root native package changed during qualification")
    return {"path": str(path), "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "identity_sha256": before["identity_sha256"], "qualification": qualified}


def _coordinates(original, config_path, source_repo):
    node, package = _path(original["deepseek_node_binary"]), _path(original["deepseek_release"])
    reserved = (node, package, _stage(node), _stage(package))
    if any(_same_location(left, right) for index, left in enumerate(reserved)
           for right in reserved[index+1:]):
        raise ValueError("native immutable destinations or reserved stages overlap")
    protected = [Path(config_path), Path(source_repo), Path(__file__).resolve().parents[2]]
    protected += [_path(original[k]) for k in
        ("provider_home", "workspace_root", "run_root", "deepseek_attestation_receipt")
        if isinstance(original.get(k), str)]
    if any(_same_location(target, state) for target in reserved for state in protected):
        raise ValueError("native immutable destination overlaps an original owner")
    return {"node": node, "package": package}


def native_materialization(*, worker_config, worker_config_sha256, source_repo, source_sha,
        native_package=None, native_node=None, operator_uid=None, reconcile=False):
    """Existing installer substep; root materialization remains unselected."""
    from .package_attended import _original_native_worker_input, protected_build
    from ops.executive_os.install_source_policy import validate_acceptance_source
    if os.geteuid() != att._ROOT_UID:
        raise ValueError("native materialization requires root")
    original, enrollment, slot, config_current = _original_native_worker_input(
        worker_config, worker_config_sha256)
    source_repo = _path(source_repo)
    tree = validate_acceptance_source(source_repo=source_repo, expected_sha=source_sha)
    accepted_raw, accepted = protected_build(source_repo, source_sha)
    targets = _coordinates(original, worker_config, source_repo)
    stages = {key: _stage(path) for key, path in targets.items()}
    digest = enrollment["provider_binary_sha256"]
    result = {"schema": "mastermind.native_deepseek_materialization/v1",
        "source_sha": source_sha, "source_tree": tree, "worker_config_sha256": worker_config_sha256,
        "targets": {key: {"path": str(path), "stage": str(stages[key]), "effect_state": "NONE"}
                    for key, path in targets.items()},
        "selection_changed": False, "services_changed": False, "configs_changed": False,
        "receipt_changed": False, "provider_calls": 0, "worker_observation": "NOT_OBSERVED",
        "account_eligibility": "NOT_OBSERVED"}
    def current():
        config_current()
        if (validate_acceptance_source(source_repo=source_repo, expected_sha=source_sha) != tree
                or protected_build(source_repo, source_sha)[0] != accepted_raw):
            raise ValueError("native materialization source changed")
    candidate = node_candidate = None
    if reconcile:
        if any(x is not None for x in (native_package, native_node, operator_uid)):
            raise ValueError("reconciliation cannot replace original materialization inputs")
    else:
        if type(operator_uid) is not int or operator_uid <= 0:
            raise ValueError("original operator input owner required")
        candidate, node_candidate = _path(native_package), _path(native_node)
        if any(_same_location(target, source) for target in targets.values()
               for source in (candidate, node_candidate)):
            raise ValueError("native input overlaps immutable destination")
        raw, manifest, config, root_identity = _candidate(candidate, operator_uid, accepted, original)
        with _operator_object(node_candidate, operator_uid, directory=False) as (fd, info, check):
            if not 0 < info.st_size <= 256*1024*1024 or not info.st_mode & 0o111:
                raise ValueError("native Node candidate is not bounded executable input")
            value, consumed = hashlib.sha256(), 0
            while block := os.read(fd, min(1024*1024, info.st_size + 1 - consumed)):
                consumed += len(block)
                if consumed > info.st_size:
                    raise ValueError("native Node candidate grew during observation")
                value.update(block)
            if consumed != info.st_size or value.hexdigest() != digest:
                raise ValueError("native Node candidate differs from original enrollment")
            check()
            node_identity = _identity(info)
    current()
    phase = "preparation"
    prepared = False
    result["parent_preparation_attempted"] = []
    try:
        parents = sorted({p.parent for p in targets.values()}, key=str)
        for parent in parents:
            if _entry(parent) is None:
                if reconcile:
                    custody.sealed_directory(parent.parent)
                    continue
                custody.sealed_directory(parent.parent)
                result["parent_preparation_attempted"].append(str(parent))
                prepared = True
                custody.create_profile_parent(parent)
            custody.sealed_directory(parent, mode=0o755)
        with contextlib.ExitStack() as stack:
            held = {}
            for parent in parents:
                if _entry(parent) is not None:
                    representative = next(p for p in targets.values() if p.parent == parent)
                    held[parent] = stack.enter_context(att._deepseek_publication_parent(representative))
            if reconcile:
                observations = {}
                for key, target in targets.items():
                    occupant, pending = _entry(target), _entry(stages[key])
                    observations[key] = (None if occupant is None else _identity(occupant),
                                         None if pending is None else _identity(pending))
                    row = result["targets"][key]
                    if pending is not None:
                        row["state"] = "CONFLICTING_OCCUPANTS" if occupant is not None else "PRIVATE_STAGE_PRESENT"
                    elif occupant is None:
                        row["state"] = "NOT_PUBLISHED"
                    else:
                        row["observation"] = (_node(target, digest) if key == "node" else
                            _package(target, original, source_repo, source_sha))
                        row["state"] = "PRESENT_QUALIFIED"
                current()
                for key, target in targets.items():
                    now, pending = _entry(target), _entry(stages[key])
                    if observations[key] != (None if now is None else _identity(now),
                                              None if pending is None else _identity(pending)):
                        raise ValueError("original materialization targets changed during reconciliation")
                    row = result["targets"][key]
                    if row["state"] == "PRESENT_QUALIFIED":
                        if key == "node":
                            if att._runtime_identity(target) != row["observation"]["identity"]:
                                raise ValueError("original Node changed at reconciliation boundary")
                        elif att._deepseek_tree(target)["identity_sha256"] != row["observation"]["identity_sha256"]:
                            raise ValueError("original package changed at reconciliation boundary")
                result["state"] = "RECONCILED"
                return result
            # Refuse any retained private sibling before another artifact effect.
            for key, stage in stages.items():
                if _entry(stage) is not None:
                    result["targets"][key]["state"] = "PRIVATE_STAGE_PRESENT"
                    raise NativeMaterializationPending("original native private stage requires reconciliation")
            for key in ("node", "package"):
                phase = "preparation"
                target, stage = targets[key], stages[key]
                parent_fd, parent_current = held[target.parent]
                row = result["targets"][key]
                if _entry(target) is not None:
                    row["observation"] = (_node(target, digest) if key == "node" else
                        _package(target, original, source_repo, source_sha))
                    row["state"] = "PRESENT_QUALIFIED"
                    continue
                current()
                parent_current()
                if key == "node":
                    fd = os.open(stage.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent_fd)
                    prepared = True
                    created = os.fstat(fd)
                    stage_birth = created.st_dev, created.st_ino
                    try:
                        with _operator_object(node_candidate, operator_uid, directory=False) as (source_fd, info, check):
                            if _identity(info) != node_identity:
                                raise ValueError("original native Node input moved")
                            _copy_file(source_fd, fd, info, digest)
                            check()
                        os.fchmod(fd, 0o555)
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                    row["prepared"] = _node(stage, digest)
                else:
                    os.mkdir(stage.name, mode=0o700, dir_fd=parent_fd)
                    prepared = True
                    created = os.stat(stage.name, dir_fd=parent_fd, follow_symlinks=False)
                    stage_fd = os.open(stage.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                       dir_fd=parent_fd)
                    try:
                        if (_identity(os.fstat(stage_fd)) != _identity(created)
                                or created.st_uid != att._ROOT_UID
                                or att.has_macos_acl(stage, expected_identity=created, descriptor=stage_fd)):
                            raise ValueError("original package stage changed before copying")
                        stage_birth = created.st_dev, created.st_ino
                        _copy_package(candidate, stage, operator_uid, raw, manifest, root_identity, stage_fd)
                    finally:
                        os.close(stage_fd)
                    parent_current()
                    row["prepared"] = _package(stage, original, source_repo, source_sha, stage=True)
                staged = os.stat(stage.name, dir_fd=parent_fd, follow_symlinks=False)
                if (staged.st_dev, staged.st_ino) != stage_birth:
                    raise ValueError("original private stage was replaced")
                row["state"] = "PRIVATE_STAGE_QUALIFIED"
                current()
                parent_current()
                if (_entry(target) is not None
                        or _identity(os.stat(stage.name, dir_fd=parent_fd, follow_symlinks=False)) != _identity(staged)):
                    raise ValueError("original native destination or stage changed before publication")
                if key == "node":
                    if att._runtime_identity(stage) != row["prepared"]["identity"]:
                        raise ValueError("native Node changed at publication boundary")
                elif att._deepseek_tree(stage)["identity_sha256"] != row["prepared"]["identity_sha256"]:
                    raise ValueError("native package changed at publication boundary")
                phase = "publication"
                row["effect_state"] = "EFFECT_UNKNOWN"
                _rename_exclusive(parent_fd, stage.name, parent_fd, target.name)
                os.fsync(parent_fd)
                final = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
                if ((final.st_dev, final.st_ino) != (staged.st_dev, staged.st_ino)
                        or _entry(stage) is not None):
                    raise ValueError("native publication postimage differs")
                row["observation"] = (_node(target, digest) if key == "node" else
                    _package(target, original, source_repo, source_sha))
                row["effect_state"] = "APPLIED"
                row["state"] = "PUBLISHED_QUALIFIED"
            phase = "postcondition"
            current()
            # A later source callback cannot replace either already-qualified target.
            for key, target in targets.items():
                row = result["targets"][key]
                latest = (_node(target, digest) if key == "node" else
                    _package(target, original, source_repo, source_sha))
                if latest != row["observation"] or _entry(stages[key]) is not None:
                    raise ValueError("native materialization changed at final boundary")
            result["state"] = "UNSELECTED_MATERIALIZED"
            return result
    except Exception as exc:
        unknown = (phase == "publication" or phase == "postcondition" and
                   any(row["effect_state"] in ("APPLIED", "EFFECT_UNKNOWN") for row in result["targets"].values()))
        result["state"] = "EFFECT_UNKNOWN" if unknown else "PREPARATION_RETAINED" if prepared else "REFUSED"
        cls = NativeMaterializationUnknown if unknown else NativeMaterializationPending
        error = exc if isinstance(exc, cls) else cls("original native materialization requires reconciliation")
        error.evidence = result
        raise error from (None if error is exc else exc)

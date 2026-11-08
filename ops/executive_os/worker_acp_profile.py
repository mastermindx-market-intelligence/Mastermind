"""Sealed ACP dependency profile, published only by the existing installer.

This fixed Worker profile reuses the incumbent custody primitives. It creates no
listener, account, enrollment, mutable selector, credential or lifecycle owner.
"""
from __future__ import annotations
import argparse
import dataclasses
import email
import importlib
import importlib.metadata
import io
import os
from pathlib import Path
import platform
import re
import stat
import sys
import zipfile

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ops.executive_os import control_aead_profile as custody
from control_plane.executive_installed_peer import (
    _PYTHON_BASE, _PYTHON_LAUNCHER, _PYTHON_VERSION, _PYTHON_LAUNCHER_SHA256,
)
from ops.executive_os.worker_acp_contract import (
    IMPORT_ROOTS, MAX_BYTES, MAX_FILES, VERSIONS, WorkerAcpContractError,
    allowed_profile_path, canonical, manifest_bytes, normalize, parse_lock, parse_manifest,
)

SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
LOCK_RELATIVE = "requirements/executive-worker-acp-macos-arm64-py312.lock"
MANIFEST = ".worker-acp-closure.json"
LOCK_FILE_MODE = 0o644
_METADATA_NAMES = {
    "agent-client-protocol": "agent-client-protocol", "annotated-types": "annotated-types",
    "pydantic": "pydantic", "pydantic-core": "pydantic_core",
    "typing-extensions": "typing_extensions", "typing-inspection": "typing-inspection",
}
_IMPORT_PATHS = {
    "agent-client-protocol": "acp", "annotated-types": "annotated_types",
    "pydantic": "pydantic", "pydantic-core": "pydantic_core",
    "typing-extensions": "typing_extensions.py", "typing-inspection": "typing_inspection",
}
_TAGS = {name: ("cp312-cp312-macosx_11_0_arm64" if name == "pydantic-core" else "py3-none-any")
         for name in VERSIONS}
_WHEELS = {name: name.replace("-", "_") + "-" + version + "-" + _TAGS[name] + ".whl"
           for name, version in VERSIONS.items()}
_SEAL = object()


class WorkerAcpProfileError(ValueError):
    pass


def refuse():
    raise WorkerAcpProfileError("sealed native Worker ACP profile unavailable")


def _check(check):
    if check is not None:
        check()


def _member(archive, info, *, check=None):
    if not 0 <= info.file_size <= MAX_BYTES:
        refuse()
    chunks, count = [], 0
    with archive.open(info) as member:
        while True:
            _check(check)
            block = member.read(min(1024 * 1024, MAX_BYTES + 1 - count))
            _check(check)
            if not block:
                break
            count += len(block)
            if count > MAX_BYTES or count > info.file_size:
                refuse()
            chunks.append(block)
    if count != info.file_size:
        refuse()
    return b"".join(chunks)


def wheel_files(name, data, lock, *, check=None):
    matched = [distribution for distribution, filename in _WHEELS.items() if name == filename]
    if len(matched) != 1 or type(data) is not bytes or not 0 < len(data) <= MAX_BYTES:
        refuse()
    distribution = matched[0]
    if (lock[distribution]["version"] != VERSIONS[distribution]
            or custody.digest(data, check=check) not in lock[distribution]["hashes"]):
        refuse()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            infos = wheel.infolist()
            if not 1 <= len(infos) <= MAX_FILES or len({i.filename for i in infos}) != len(infos):
                refuse()
            files = {}
            permitted_roots = {_IMPORT_PATHS[distribution],
                distribution.replace("-", "_") + "-" + VERSIONS[distribution] + ".dist-info"}
            for info in infos:
                _check(check)
                if info.is_dir():
                    continue
                if (not allowed_profile_path(info.filename)
                        or info.filename.split("/")[0] not in permitted_roots
                        or stat.S_ISLNK(info.external_attr >> 16)):
                    refuse()
                files[info.filename] = _member(wheel, info, check=check)
                if sum(map(len, files.values())) > 2 * MAX_BYTES:
                    refuse()
            stem = distribution.replace("-", "_") + "-" + VERSIONS[distribution] + ".dist-info/"
            if stem + "WHEEL" not in files or stem + "METADATA" not in files:
                refuse()
            wheel_meta = email.message_from_bytes(files[stem + "WHEEL"])
            package_meta = email.message_from_bytes(files[stem + "METADATA"])
            if (wheel_meta.get_all("Tag") != [_TAGS[distribution]]
                    or package_meta.get_all("Name") != [_METADATA_NAMES[distribution]]
                    or package_meta.get_all("Version") != [VERSIONS[distribution]]):
                refuse()
            return distribution, files
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, EOFError):
        refuse()


def bundle_files(data, lock_bytes, *, check=None):
    _check(check)
    lock = parse_lock(lock_bytes)
    if type(data) is not bytes or not 0 < len(data) <= 2 * MAX_BYTES:
        refuse()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            infos = bundle.infolist()
            if (len(infos) != len(VERSIONS)
                    or any(i.is_dir() or stat.S_ISLNK(i.external_attr >> 16) for i in infos)):
                refuse()
            wheels, packages, distributions = {}, {}, set()
            for info in infos:
                if "/" in info.filename or "\\" in info.filename or info.filename in wheels:
                    refuse()
                payload = _member(bundle, info, check=check)
                distribution, files = wheel_files(info.filename, payload, lock, check=check)
                if distribution in distributions or set(packages) & set(files):
                    refuse()
                distributions.add(distribution)
                wheels[info.filename] = payload
                packages.update(files)
            if distributions != set(VERSIONS):
                refuse()
            entries = [{"path": p, "bytes": len(data), "sha256": custody.digest(data, check=check),
                        "mode": 0o555 if p.endswith(".so") else 0o444}
                       for p, data in sorted(packages.items())]
            return wheels, packages, manifest_bytes(custody.digest(lock_bytes), entries)
    except (zipfile.BadZipFile, RuntimeError, EOFError):
        refuse()


def build_bundle(wheels, lock_bytes):
    lock = parse_lock(lock_bytes)
    if len(wheels) != len(VERSIONS):
        refuse()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(map(Path, wheels)):
            before = path.lstat()
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or not 0 < before.st_size <= MAX_BYTES):
                refuse()
            data = custody.secure_data(path, uid=before.st_uid,
                mode=stat.S_IMODE(before.st_mode), maximum=MAX_BYTES)
            wheel_files(path.name, data, lock)
            info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100444 << 16
            archive.writestr(info, data)
    result = output.getvalue()
    bundle_files(result, lock_bytes)
    return result


def profile_root(lock_bytes):
    return SYSTEM_ROOT / "worker-acp-dependencies" / custody.digest(lock_bytes)


def _lock(release_root, *, check=None):
    release_root = Path(release_root)
    custody.sealed_directory(release_root, check=check)
    custody.sealed_directory((release_root / LOCK_RELATIVE).parent, check=check)
    data = custody.secure_data(release_root / LOCK_RELATIVE, mode=LOCK_FILE_MODE, maximum=32768, check=check)
    parse_lock(data)
    return data


def verify_profile(release_root, *, check=None):
    lock_bytes = _lock(release_root, check=check)
    root = profile_root(lock_bytes)
    custody.sealed_directory(root, mode=0o555, check=check)
    for name in ("packages", "wheels"):
        custody.sealed_directory(root / name, mode=0o555, check=check)
    wheel_paths = list((root / "wheels").iterdir())
    if len(wheel_paths) != len(VERSIONS):
        refuse()
    contents = io.BytesIO()
    with zipfile.ZipFile(contents, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(wheel_paths):
            archive.writestr(path.name, custody.secure_data(path, maximum=MAX_BYTES, check=check))
    _, packages, expected = bundle_files(contents.getvalue(), lock_bytes, check=check)
    manifest = custody.secure_data(root / MANIFEST, maximum=4 * 1024 * 1024, check=check)
    parse_manifest(manifest, custody.digest(lock_bytes))
    if manifest != expected:
        refuse()
    actual = set()
    directories = {parent.as_posix() for name in packages
                   for parent in Path(name).parents if parent != Path(".")}
    for path in (root / "packages").rglob("*"):
        _check(check)
        relative = path.relative_to(root / "packages").as_posix()
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            if relative not in directories:
                refuse()
            custody.sealed_directory(path, mode=0o555, check=check)
            continue
        if relative not in packages:
            refuse()
        actual.add(relative)
        payload = custody.secure_data(path, mode=0o555 if relative.endswith(".so") else 0o444,
                                      maximum=MAX_BYTES, check=check)
        if payload != packages[relative]:
            refuse()
    if (actual != set(packages)
            or {p.name for p in root.iterdir()} != {"packages", "wheels", MANIFEST}):
        refuse()
    _check(check)
    return {"root": str(root), "packages": str(root / "packages"),
            "source_sha": Path(release_root).name, "lock_sha256": custody.digest(lock_bytes),
            "manifest_sha256": custody.digest(manifest)}


def materialize_bundle(bundle, release_root, *, operator_uid, expected_digest):
    """Installer subroutine. Same-lock occupants are verified, never replaced."""
    if os.geteuid() != 0:
        refuse()
    lock_bytes = _lock(release_root)
    data = custody.secure_data(bundle, uid=operator_uid, mode=0o600, maximum=2 * MAX_BYTES)
    if (type(expected_digest) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
            or custody.digest(data) != expected_digest):
        refuse()
    wheels, packages, manifest = bundle_files(data, lock_bytes)
    root = profile_root(lock_bytes)
    if root.exists():
        return verify_profile(release_root)
    custody.sealed_directory(root.parent.parent)
    custody.create_profile_parent(root.parent)
    custody.sealed_directory(root.parent, mode=0o755)
    stage = root.parent / (".stage-" + os.urandom(16).hex())
    stage.mkdir(mode=0o700)
    # The existing installer serializes this act. Interrupted stages remain
    # available to that original owner; neither a replacement nor cleanup occurs.
    (stage / "wheels").mkdir()
    (stage / "packages").mkdir()
    for name, data in wheels.items():
        path = stage / "wheels" / name
        path.write_bytes(data)
        path.chmod(0o444)
    for name, data in packages.items():
        path = stage / "packages" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o555 if name.endswith(".so") else 0o444)
    (stage / MANIFEST).write_bytes(manifest)
    (stage / MANIFEST).chmod(0o444)
    for path in sorted(stage.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o555)
    stage.chmod(0o555)
    from ops.executive_os.capacity_host_artifacts import _rename_exclusive
    parent_fd = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _rename_exclusive(parent_fd, stage.name, parent_fd, root.name)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return verify_profile(release_root)


def _snapshot(release_root):
    """Retained source identity, no repeated wheel extraction or import."""
    from control_plane.native_provider_attestation import _file_observation, _sdk_tree
    lock_bytes = _lock(release_root)
    root = profile_root(lock_bytes)
    return canonical({
        "lock": _file_observation(Path(release_root) / LOCK_RELATIVE),
        "tree": _sdk_tree(root),
        "manifest": _file_observation(root / MANIFEST),
    })


def _covered_modules():
    return tuple((name, module) for name, module in tuple(sys.modules.items())
                 if name.split(".")[0] in IMPORT_ROOTS)


def _baseline_path():
    return (str(_ROOT), _PYTHON_BASE + "/lib/python312.zip",
            _PYTHON_BASE + "/lib/python3.12", _PYTHON_BASE + "/lib/python3.12/lib-dynload")


def _origins(package_root, original_modules=()):
    for name, module in original_modules:
        if sys.modules.get(name) is not module:
            refuse()
    for name, module in _covered_modules():
        origin = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        if (type(origin) is not str or spec is None or spec.origin != origin
                or package_root not in Path(origin).resolve(strict=True).parents):
            refuse()
        paths = getattr(module, "__path__", None)
        locations = spec.submodule_search_locations
        if paths is None:
            if locations is not None:
                refuse()
        elif (Path(origin).name != "__init__.py"
                or tuple(paths) != (str(Path(origin).parent),)
                or locations is None or tuple(locations) != tuple(paths)):
            refuse()


def _require_python():
    # Same exact executable already qualified by provision-python-runtime.sh.
    if (platform.python_version() != _PYTHON_VERSION or platform.system() != "Darwin"
            or platform.machine() != "arm64" or sys.executable != _PYTHON_LAUNCHER
            or not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode
            or custody.digest(custody.secure_data(_PYTHON_LAUNCHER, mode=0o755, maximum=MAX_BYTES))
               != _PYTHON_LAUNCHER_SHA256):
        refuse()


@dataclasses.dataclass(frozen=True, repr=False)
class NativeWorkerAcpRuntime:
    _release_root: Path
    _observation: bytes
    _identity: bytes
    _original_modules: tuple
    _import_path: tuple
    _seal: object

    def require_current(self):
        if self._seal is not _SEAL:
            refuse()
        _require_python()
        import json
        observed = json.loads(self._observation)
        if (self._release_root != _ROOT
                or _snapshot(self._release_root) != self._identity
                or observed["source_sha"] != self._release_root.name):
            refuse()
        package_root = Path(observed["packages"])
        if (tuple(sys.path) != self._import_path
                or self._import_path != (str(package_root), *_baseline_path())):
            refuse()
        _origins(package_root, self._original_modules)


def observe_for_native_worker(installation, *, release_root):
    from control_plane.native_provider_attestation import NativeDeepSeekInstallation
    release_root = Path(release_root)
    if (release_root != _ROOT or release_root != release_root.resolve(strict=True)
            or not isinstance(installation, NativeDeepSeekInstallation)
            or re.fullmatch(r"[0-9a-f]{40}", release_root.name) is None
            or installation.source_sha != release_root.name):
        refuse()
    installation.require_current()
    before = _snapshot(release_root)
    observation = verify_profile(release_root)
    if _snapshot(release_root) != before:
        refuse()
    installation.require_current()
    return observation, before


def activate_for_native_worker(installation, *, release_root, worker_uid):
    if (type(worker_uid) is not int or worker_uid <= 0
            or os.geteuid() != worker_uid or os.getuid() != worker_uid):
        refuse()
    _require_python()
    observation, identity = observe_for_native_worker(installation, release_root=release_root)
    package_root = Path(observation["packages"])
    _origins(package_root)
    if tuple(sys.path) not in (_baseline_path(), (str(package_root), *_baseline_path())):
        refuse()
    added = str(package_root) not in sys.path
    if added:
        sys.path.insert(0, str(package_root))
    try:
        for name in sorted(IMPORT_ROOTS):
            importlib.import_module(name)
        _origins(package_root)
        for name, expected in VERSIONS.items():
            if importlib.metadata.version(name) != expected:
                refuse()
        if _snapshot(Path(release_root)) != identity:
            refuse()
        installation.require_current()
        modules = _covered_modules()
        result = NativeWorkerAcpRuntime(Path(release_root), canonical(observation), identity,
                                       modules, tuple(sys.path), _SEAL)
        result.require_current()
        return result
    except BaseException:
        if added and str(package_root) in sys.path:
            sys.path.remove(str(package_root))
        raise


def committed_lock(source_repo, expected_sha):
    from ops.executive_os.install_source_policy import _git
    if type(expected_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        refuse()
    if _git(Path(source_repo), "rev-parse", "HEAD").stdout.strip() != expected_sha:
        refuse()
    result = _git(Path(source_repo), "show", expected_sha + ":" + LOCK_RELATIVE)
    data = result.stdout.encode()
    parse_lock(data)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build-bundle", "check-bundle", "materialize", "verify"))
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--wheel", action="append", type=Path, default=[])
    parser.add_argument("--operator-uid", type=int)
    parser.add_argument("--expected-sha")
    parser.add_argument("--expected-digest")
    args = parser.parse_args(argv)
    if args.operation == "build-bundle":
        if args.bundle is None or args.bundle.exists():
            refuse()
        data = build_bundle(args.wheel, (args.release_root / LOCK_RELATIVE).read_bytes())
        with args.bundle.open("xb") as output:
            output.write(data)
        args.bundle.chmod(0o600)
        print(canonical({"bundle_sha256": custody.digest(data)}).decode(), end="")
    elif args.operation == "check-bundle":
        if args.bundle is None or args.operator_uid is None:
            refuse()
        lock = committed_lock(args.release_root, args.expected_sha)
        data = custody.secure_data(args.bundle, uid=args.operator_uid, mode=0o600, maximum=2 * MAX_BYTES)
        bundle_files(data, lock)
        print(custody.digest(data))
    elif args.operation == "materialize":
        if args.bundle is None or args.operator_uid is None or args.expected_digest is None:
            refuse()
        print(canonical(materialize_bundle(args.bundle, args.release_root,
            operator_uid=args.operator_uid, expected_digest=args.expected_digest)).decode(), end="")
    else:
        print(canonical(verify_profile(args.release_root)).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Publish and select native code artifacts; never admit, retry or settle work.

This is an OFFLINE ROLLOUT CANDIDATE. A reviewed manifest is an input, not a
claim that this file discovers the full dependency closure. Runtime state stays
with the incumbent kit. Publication and selection use an artifact lock only.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

SCHEMA = "native-code-generation.v1"
POINTER_SCHEMA = "native-code-selection.v1"
STORE_NAME = "native-code-releases"
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
ENTRYPOINTS = {"pool": "pool", "task": "ext/fabric_task.py",
              "remote": "ext/remote_sub.sh"}

# Fixed references to existing owners. No target contents are read or copied.
# The final native closure audit may require additions to this REVIEWED list.
EXT_BINDINGS = frozenset({
    "active", "lanes", "slots", "state", "broker", "lane_bin",
    "hosts.json", "bailian_policy.json", "bailian_usage.json",
    "GROK_EXHAUSTED", "glm_window_state.json", "glm_shim", "go_shim",
    "codex_glm", "codex_go", "codex_minimax", "quota_cache.json",
    "glm_capabilities.json",
})
ROOT_BINDINGS = frozenset({
    "orch", "codex_bailian", "minimax_claude_home", "glm_claude_home",
    "go_claude_home",
})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs)


def require(path, kind, mode=None):
    path = Path(path)
    observed = path.lstat()
    if not kind(observed.st_mode):
        raise ValueError("unexpected file kind: " + str(path))
    if observed.st_uid != os.geteuid():
        raise ValueError("unexpected source owner: " + str(path))
    if mode is not None and stat.S_IMODE(observed.st_mode) != mode:
        raise ValueError("unexpected file mode: " + str(path))
    return observed


def regular_bytes(path, limit=MAX_FILE, *, bind_path=True):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        observed = os.fstat(fd)
        if not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid():
            raise ValueError("owned regular file required: " + str(path))
        if not 0 <= observed.st_size <= limit:
            raise ValueError("file exceeds publication bound")
        with os.fdopen(os.dup(fd), "rb") as handle:
            raw = handle.read(limit + 1)
        if len(raw) != observed.st_size or len(raw) > limit:
            raise ValueError("source changed while reading")
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                    value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if (identity(os.fstat(fd)) != identity(observed)
                or (bind_path and identity(path.lstat()) != identity(observed))):
            raise ValueError("source identity changed while reading")
        return raw
    finally:
        os.close(fd)


def file_name(relative):
    if relative == "pool":
        return
    parts = relative.split("/") if isinstance(relative, str) else []
    if (len(parts) != 2 or parts[0] != "ext" or not NAME.fullmatch(parts[1])
            or not (parts[1].endswith((".py", ".sh"))
                    or parts[1] in {"yes", "host_pull_probe.template",
                        "paid_pyyaml_6_0_3.zip", "paid_pyyaml_provenance.json"})
            or parts[1] in EXT_BINDINGS):
        raise ValueError("manifest must explicitly name flat code files")
    # Deliberately no ext/pools.yaml: its presence invokes the *remote-support*
    # policy-schema verifier. Native generations use the existing ../orch owner.


def manifest_files(value):
    if type(value) is not dict or not 3 <= len(value) <= 256:
        raise ValueError("invalid explicit code manifest")
    for relative, wanted in value.items():
        file_name(relative)
        if type(wanted) is not str or not HEX.fullmatch(wanted):
            raise ValueError("invalid code hash")
    if not set(ENTRYPOINTS.values()).issubset(value):
        raise ValueError("all three native ingress artifacts are required")
    return dict(value)


def bindings(stable_ext):
    stable_ext = Path(stable_ext)
    result = {"ext/" + n: str(stable_ext / n) for n in EXT_BINDINGS}
    result.update({n: str(stable_ext.parent / n) for n in ROOT_BINDINGS})
    return result


def descriptor(files, stable_ext):
    return {"schema": SCHEMA, "files": manifest_files(files),
            "stable_ext": str(stable_ext), "links": bindings(stable_ext),
            "entrypoints": ENTRYPOINTS}


def store_path(stable_ext, create=False):
    stable_ext = Path(stable_ext).resolve(strict=True)
    require(stable_ext, stat.S_ISDIR)
    store = stable_ext.parent / STORE_NAME
    if create:
        try:
            store.mkdir(mode=0o700)
        except FileExistsError:
            pass
    require(store, stat.S_ISDIR, 0o700)
    return store


def check_store(store):
    store = Path(store)
    if not store.is_absolute() or store.resolve(strict=True) != store:
        raise ValueError("canonical store path required")
    require(store, stat.S_ISDIR, 0o700)
    if store.name != STORE_NAME:
        raise ValueError("unexpected native store name")
    return store


@contextlib.contextmanager
def publication_lock(store):
    store = check_store(store)
    fd = os.open(store / ".publication.lock",
                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        observed = os.fstat(fd)
        if (not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid()
                or stat.S_IMODE(observed.st_mode) != 0o600):
            raise ValueError("invalid publication lock")
        # Publication is finite; fail promptly rather than hold a controller.
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("native publication already in progress") from exc
        yield
    finally:
        os.close(fd)


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_bytes(path, raw, mode):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=".native-stage-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def verify(store, generation):
    store = check_store(store)
    if type(generation) is not str or not HEX.fullmatch(generation):
        raise ValueError("invalid generation identity")
    root = store / generation
    require(root, stat.S_ISDIR, 0o555)
    require(root / "ext", stat.S_ISDIR, 0o555)
    require(root / "RELEASE.json", stat.S_ISREG, 0o444)
    meta = unique_json(regular_bytes(root / "RELEASE.json"))
    if type(meta) is not dict or set(meta) != {
            "schema", "files", "stable_ext", "links", "entrypoints", "digest"}:
        raise ValueError("invalid release metadata")
    stable_ext = (store.parent / "ext").resolve(strict=True)
    expected = descriptor(meta["files"], stable_ext)
    wanted = digest(canonical(expected))
    if wanted != generation or meta != dict(expected, digest=wanted):
        raise ValueError("generation identity or binding mismatch")
    if {p.name for p in root.iterdir()} != {"ext", "pool", "RELEASE.json", *ROOT_BINDINGS}:
        raise ValueError("unexpected generation contents")
    expected_ext = {n.split("/")[1] for n in meta["files"] if n.startswith("ext/")}
    if {p.name for p in (root / "ext").iterdir()} != expected_ext | EXT_BINDINGS:
        raise ValueError("unexpected generation ext contents")
    for relative, wanted in meta["files"].items():
        require(root / relative, stat.S_ISREG, 0o555)
        if digest(regular_bytes(root / relative)) != wanted:
            raise ValueError("generation code digest mismatch: " + relative)
    for relative, target in meta["links"].items():
        require(root / relative, stat.S_ISLNK)
        if os.readlink(root / relative) != target:
            raise ValueError("generation state binding mismatch: " + relative)
    return root, meta


def discard_unpublished(root):
    # Only a stage made by this process. Never visit/chmod a state-link target.
    require(root, stat.S_ISDIR)
    root.chmod(0o700)
    if (root / "ext").exists():
        require(root / "ext", stat.S_ISDIR)
        (root / "ext").chmod(0o700)
    shutil.rmtree(root)


def publish(source_root, stable_ext, files):
    stable_ext = Path(stable_ext).resolve(strict=True)
    if stable_ext.name != "ext":
        raise ValueError("native stable directory must be named ext")
    store = store_path(stable_ext, create=True)
    source_root = Path(source_root).resolve(strict=True)
    require(source_root, stat.S_ISDIR)
    if (source_root == stable_ext or source_root.is_relative_to(stable_ext)
            or source_root == store or source_root.is_relative_to(store)
            or stable_ext.is_relative_to(source_root) or store.is_relative_to(source_root)):
        raise ValueError("source staging must be outside the live kit and store")
    require(source_root / "ext", stat.S_ISDIR)
    files = manifest_files(files)
    # Keep the exact bytes read and hashed; copying does not reopen sources.
    payloads = {name: regular_bytes(source_root / name) for name in files}
    if sum(map(len, payloads.values())) > MAX_TOTAL:
        raise ValueError("generation exceeds publication bound")
    if any(digest(raw) != files[name] for name, raw in payloads.items()):
        raise ValueError("staged source disagrees with reviewed manifest")
    expected = descriptor(files, stable_ext)
    generation = digest(canonical(expected))
    with publication_lock(store):
        final = store / generation
        if os.path.lexists(final):
            verify(store, generation)
            return final
        staged = Path(tempfile.mkdtemp(prefix=".unpublished-", dir=store))
        renamed = False
        try:
            (staged / "ext").mkdir(mode=0o700)
            for name, raw in payloads.items():
                target = staged / name
                with target.open("xb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fchmod(handle.fileno(), 0o555)
                    os.fsync(handle.fileno())
                if digest(regular_bytes(target)) != files[name]:
                    raise ValueError("copied source digest mismatch")
            for name, target in expected["links"].items():
                os.symlink(target, staged / name)
            atomic_bytes(staged / "RELEASE.json",
                         canonical(dict(expected, digest=generation)) + b"\n", 0o444)
            (staged / "ext").chmod(0o555)
            fsync_directory(staged / "ext")
            fsync_directory(staged)
            # Darwin permits the rename while this owned stage is writable.
            # Selection never exposes the directory until sealing verifies.
            os.rename(staged, final)
            renamed = True
            final.chmod(0o555)
            fsync_directory(store)
            verify(store, generation)
            return final
        finally:
            if not renamed and staged.exists():
                discard_unpublished(staged)
            # A failed post-rename seal is retained and fails verify. Do not
            # repair/delete a published identity another reader may have seen.


def current(store):
    store = check_store(store)
    path = store / "CURRENT.json"
    if not os.path.lexists(path):
        return None
    require(path, stat.S_ISREG, 0o600)
    # A concurrent atomic selection may rename the pathname after this open.
    # Its old regular inode is still a complete, valid single selection.
    value = unique_json(regular_bytes(path, 4096, bind_path=False))
    if (type(value) is not dict or set(value) != {"schema", "generation", "sequence", "previous"}
            or value["schema"] != POINTER_SCHEMA or type(value["sequence"]) is not int
            or value["sequence"] < 1 or not isinstance(value["generation"], str)
            or not HEX.fullmatch(value["generation"])
            or (value["previous"] is not None and
                (not isinstance(value["previous"], str) or not HEX.fullmatch(value["previous"])))):
        raise ValueError("invalid native selection")
    return value


def _select_locked(store, generation, expected):
    verify(store, generation)
    old = current(store)
    if (old["generation"] if old else None) != expected:
        raise ValueError("native selection compare-and-swap refused")
    value = {"schema": POINTER_SCHEMA, "generation": generation,
             "previous": expected, "sequence": old["sequence"] + 1 if old else 1}
    atomic_bytes(Path(store) / "CURRENT.json", canonical(value) + b"\n", 0o600)
    return value


def select(store, generation, expected):
    store = check_store(store)
    with publication_lock(store):
        return _select_locked(store, generation, expected)


def launch(store, entry, args):
    store = check_store(store)
    selected = current(store)  # Read ONCE, then use an immutable real directory.
    if selected is None:
        raise ValueError("no native generation selected")
    root, _ = verify(store, selected["generation"])
    if entry not in ENTRYPOINTS:
        raise ValueError("unknown native entrypoint")
    target = root / ENTRYPOINTS[entry]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["FABRIC_NATIVE_CODE_GENERATION"] = selected["generation"]
    # Every selected script derives HERE from its immutable absolute filename.
    # Do not export a generation override into later explicitly legacy callers:
    # old flat remote_sub source + inherited new HERE would itself mix code.
    override = env.pop("REMOTE_SUB_HERE", None)
    if override and Path(override).resolve() != root / "ext":
        raise ValueError("source-directory override conflicts with selected generation")
    interpreter = sys.executable if entry == "task" else "/bin/bash"
    os.execve(interpreter, [interpreter, str(target), *args], env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pub = commands.add_parser("publish")
    pub.add_argument("--source", type=Path, required=True)
    pub.add_argument("--stable-ext", type=Path, required=True)
    pub.add_argument("--manifest", type=Path, required=True)
    for command in ("verify", "select"):
        sub = commands.add_parser(command)
        sub.add_argument("--store", type=Path, required=True)
        sub.add_argument("--generation", required=True)
        if command == "select":
            sub.add_argument("--expect", required=True, help="exact prior digest, or absent")
    run = commands.add_parser("exec")
    run.add_argument("--store", type=Path, required=True)
    run.add_argument("--entry", choices=ENTRYPOINTS, required=True)
    run.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "publish":
        print(publish(args.source, args.stable_ext, unique_json(regular_bytes(args.manifest))))
    elif args.command == "verify":
        root, meta = verify(args.store, args.generation)
        print(json.dumps({"path": str(root), "digest": meta["digest"]}))
    elif args.command == "select":
        print(json.dumps(select(args.store, args.generation,
                                None if args.expect == "absent" else args.expect)))
    else:
        launch(args.store, args.entry, args.args[1:] if args.args[:1] == ["--"] else args.args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("NATIVE_GENERATION_REFUSED: " + str(exc), file=sys.stderr)
        raise SystemExit(78)

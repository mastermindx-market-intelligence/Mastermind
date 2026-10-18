"""Map declared immutable-native aliases back to their existing state owners.

This is a path adapter, not a relaxed file reader. It does not follow arbitrary
symlinks, read state/credentials, create directories, or own lifecycle state.
The caller must perform its existing strict custody check on the returned path.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "native-code-generation.v1"
STORE_NAME = "native-code-releases"
HEX = re.compile(r"[0-9a-f]{64}\Z")
EXT_NAMES = frozenset({
    "active", "lanes", "slots", "state", "broker", "lane_bin",
    "hosts.json", "bailian_policy.json", "bailian_usage.json",
    "GROK_EXHAUSTED", "glm_window_state.json", "glm_shim", "go_shim",
    "codex_glm", "codex_go", "codex_minimax", "quota_cache.json",
    "glm_capabilities.json",
})
ROOT_NAMES = frozenset({
    "orch", "codex_bailian", "minimax_claude_home", "glm_claude_home",
    "go_claude_home",
})


def _require(path, predicate, mode=None):
    info = path.lstat()
    if (not predicate(info.st_mode) or info.st_uid != os.geteuid()
            or (mode is not None and stat.S_IMODE(info.st_mode) != mode)):
        raise ValueError("native state binding custody mismatch")
    return info


def _json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o444 or before.st_size > 128 * 1024):
            raise ValueError("native state binding metadata custody")
        with os.fdopen(os.dup(fd), "rb") as handle:
            data = handle.read(128 * 1024 + 1)
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_uid, value.st_mode,
                    value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if (len(data) != before.st_size or identity(before) != identity(os.fstat(fd))
                or identity(before) != identity(path.lstat())):
            raise ValueError("native state binding metadata changed")
        def unique(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("native state binding duplicate metadata key")
                result[key] = value
            return result
        return json.loads(data, object_pairs_hook=unique)
    finally:
        os.close(fd)


def owner_path(path, code_here):
    """Return an exact original-owner prefix plus the unchanged remainder.

    Flat and remote-support source retain their existing path semantics. A
    claimed native generation with missing/corrupt metadata fails closed. The
    returned path is NOT resolve()d: state-internal symlinks remain visible to
    O_NOFOLLOW, lstat, and DirectoryChain in the incumbent caller.
    """
    path = Path(path)
    here = Path(code_here)
    # Callers pass their __file__-derived fixed code directory. Do not accept a
    # mutable current symlink as an implicit native-generation identity.
    if (here.name != "ext" or here.parent.parent.name != STORE_NAME):
        return path
    root = here.parent
    store = root.parent
    if (not here.is_absolute() or here.resolve(strict=True) != here
            or not HEX.fullmatch(root.name)):
        raise ValueError("native state binding code identity")
    _require(store, stat.S_ISDIR, 0o700)
    _require(root, stat.S_ISDIR, 0o555)
    _require(here, stat.S_ISDIR, 0o555)
    meta = _json(root / "RELEASE.json")
    if (type(meta) is not dict or set(meta) != {
            "schema", "files", "stable_ext", "links", "entrypoints", "digest"}
            or meta["schema"] != SCHEMA or meta["digest"] != root.name):
        raise ValueError("native state binding metadata shape")
    material = {key: value for key, value in meta.items() if key != "digest"}
    observed = hashlib.sha256(json.dumps(material, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if observed != root.name:
        raise ValueError("native state binding generation digest")
    stable_ext = store.parent / "ext"
    _require(stable_ext, stat.S_ISDIR)
    if stable_ext.resolve(strict=True) != stable_ext or meta["stable_ext"] != str(stable_ext):
        raise ValueError("native state binding original owner")
    expected = {"ext/" + name: str(stable_ext / name) for name in EXT_NAMES}
    expected.update({name: str(stable_ext.parent / name) for name in ROOT_NAMES})
    if meta["links"] != expected:
        raise ValueError("native state binding fixed alias map")
    for alias, target in expected.items():
        link = root / alias
        _require(link, stat.S_ISLNK)
        if os.readlink(link) != target:
            raise ValueError("native state binding visible alias changed")
    # Unrelated paths, relative paths and paths with traversal remain untouched
    # so that the original caller's validity rules retain their force.
    if not path.is_absolute() or ".." in path.parts:
        return path
    for alias, target in expected.items():
        prefix = root / alias
        try:
            tail = path.relative_to(prefix)
        except ValueError:
            continue
        return Path(target) / tail
    return path

"""Closed ACP dependency data for the original native Worker installer."""
from __future__ import annotations
import json
import re
from pathlib import PurePosixPath

SCHEMA = "mastermind.executive_worker_acp_closure/v1"
VERSIONS = {
    "agent-client-protocol": "0.12.1", "annotated-types": "0.8.0",
    "pydantic": "2.13.4", "pydantic-core": "2.46.4",
    "typing-extensions": "4.16.0", "typing-inspection": "0.4.4",
}
IMPORT_ROOTS = frozenset({"acp", "annotated_types", "pydantic", "pydantic_core",
                          "typing_extensions", "typing_inspection"})
MAX_BYTES = 32 * 1024 * 1024
MAX_FILES = 8192
SHA = re.compile(r"[0-9a-f]{64}")


class WorkerAcpContractError(ValueError):
    pass


def refuse():
    raise WorkerAcpContractError("native Worker ACP dependency contract unavailable")


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode()


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(data):
    if type(data) is not bytes or not 0 < len(data) <= 32768:
        refuse()
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        refuse()
    result, current = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removesuffix("\\").strip()
        package = re.fullmatch(r"([a-z][a-z-]+)==([0-9.]+)", line)
        if package:
            name, version = package.groups()
            if name in result or VERSIONS.get(name) != version:
                refuse()
            result[name] = {"version": version, "hashes": []}
            current = name
        else:
            matched = re.fullmatch(r"--hash=sha256:([0-9a-f]{64})", line)
            if matched is None or current is None or result[current]["hashes"]:
                refuse()
            result[current]["hashes"].append(matched.group(1))
    if set(result) != set(VERSIONS) or any(len(row["hashes"]) != 1 for row in result.values()):
        refuse()
    return {name: {"version": row["version"], "hashes": tuple(row["hashes"])}
            for name, row in result.items()}


def allowed_profile_path(value):
    if (type(value) is not str or not value or len(value) > 512 or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        return False
    path = PurePosixPath(value)
    if (path.is_absolute() or value != path.as_posix()
            or any(part in ("", ".", "..") for part in value.split("/"))
            or any(part == "__pycache__" or part in ("sitecustomize.py", "usercustomize.py")
                   or part.endswith((".pth", ".pyc", ".pyo")) for part in path.parts)):
        return False
    roots = (IMPORT_ROOTS - {"typing_extensions"}) | {
        name.replace("-", "_") + "-" + version + ".dist-info"
        for name, version in VERSIONS.items()
    }
    return ((len(path.parts) >= 2 and path.parts[0] in roots)
            or value == "typing_extensions.py")


def manifest_bytes(lock_sha256, entries):
    if (type(lock_sha256) is not str or SHA.fullmatch(lock_sha256) is None
            or type(entries) is not list or not 1 <= len(entries) <= MAX_FILES):
        refuse()
    paths = []
    for entry in entries:
        if (type(entry) is not dict or set(entry) != {"path", "bytes", "sha256", "mode"}
                or not allowed_profile_path(entry["path"])
                or type(entry["bytes"]) is not int or not 0 <= entry["bytes"] <= MAX_BYTES
                or type(entry["mode"]) is not int or entry["mode"] not in (0o444, 0o555)
                or type(entry["sha256"]) is not str or SHA.fullmatch(entry["sha256"]) is None):
            refuse()
        paths.append(entry["path"])
    if (paths != sorted(paths) or len(set(paths)) != len(paths)
            or sum(entry["bytes"] for entry in entries) > 2 * MAX_BYTES):
        refuse()
    return canonical({"schema": SCHEMA, "lock_sha256": lock_sha256, "files": entries})


def parse_manifest(data, expected_lock_sha256):
    if type(data) is not bytes or not 0 < len(data) <= 4 * 1024 * 1024:
        refuse()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                refuse()
            result[key] = value
        return result
    try:
        obj = json.loads(data, object_pairs_hook=pairs)
        if (type(obj) is not dict or set(obj) != {"schema", "lock_sha256", "files"}
                or obj["schema"] != SCHEMA or obj["lock_sha256"] != expected_lock_sha256
                or manifest_bytes(obj["lock_sha256"], obj["files"]) != data):
            refuse()
        return obj
    except (UnicodeError, TypeError, KeyError, json.JSONDecodeError):
        refuse()

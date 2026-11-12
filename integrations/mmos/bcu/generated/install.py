#!/usr/bin/env python3
"""BCU staged install: merge our mcpServers entries into a provider-home .claude.json.

Generic script — works on any home passed via --home. Refuses to run without an
explicit --home path ending in '.claude.json'. Verifies the staged preimage
sha256 before editing (PREIMAGE_MISMATCH abort), writes a timestamped backup
with mode 0600 next to the file, merges ONLY the staged keys, and records:

* postimage.sha256 — sha256 of the edited file (0600), so re-runs are idempotent
* added-keys.json  — exactly which keys THIS install added vs modified, next to
  the postimage; rollback uses it to never touch pre-existing keys

Every write goes through a temp file in the destination directory plus
os.replace, and the destination's hash is re-checked immediately before the
replace (PREIMAGE_MISMATCH abort when the file changed since first read).

--copy-server SRC_DIR: copy the computer-use server runtime (server.py,
deny.json, and runtime.json when present) from SRC_DIR into the MCP server root
(--mcp-root, default /Users/chriswong/.t3/mcp) under mmos-computer-use/ with
mode 0600, BEFORE registering the entry that points at that copy. Without the
flag the entry is registered as staged and a missing target only draws a
warning. The manifest records whether this install created the server
directory, so rollback --remove-server deletes it only then.
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EXIT_BAD_HOME = 2
EXIT_HOME_NOT_FOUND = 3
EXIT_STAGING_MISSING = 4
EXIT_PREIMAGE_MISMATCH = 5
EXIT_INVALID_JSON = 6
EXIT_COPY_SRC_MISSING = 7

BACKUP_GLOB = ".claude.json.bak-pre-bcu-*"
MCP_ROOT_DEFAULT = "/Users/chriswong/.t3/mcp"
SERVER_DIR_NAME = "mmos-computer-use"
SERVER_FILES = ("server.py", "deny.json", "runtime.json")


class PreimageMismatch(Exception):
    pass


def fail(code, message):
    print(message, file=sys.stderr)
    sys.exit(code)


def parse_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--home", required=True,
                        help="path to the provider-home .claude.json to operate on")
    parser.add_argument("--staging-dir", default=None,
                        help="staged tree root (default: directory containing this script)")
    parser.add_argument("--copy-server", default=None, metavar="SRC_DIR",
                        help="copy the computer-use server runtime from SRC_DIR into the "
                             "MCP server root (mode 0600) before registering the entry")
    parser.add_argument("--mcp-root", default=None, metavar="DIR",
                        help="MCP server root (default: " + MCP_ROOT_DEFAULT + ")")
    parser.add_argument("--refresh-preimage", action="store_true",
                        help="operator-only: do not install; print which staged keys are "
                             "present/changed and re-record the CURRENT file hash as the "
                             "staged preimage")
    return parser.parse_args()


def resolve_home(raw):
    if not raw or not raw.endswith(".claude.json"):
        fail(EXIT_BAD_HOME,
             "BAD_HOME_PATH: --home must be an explicit path ending in '.claude.json'")
    path = Path(raw)
    if not path.is_file():
        fail(EXIT_HOME_NOT_FOUND, "HOME_NOT_FOUND: " + str(path))
    return path


def staging_paths(staging_dir, home_path):
    base = Path(staging_dir) if staging_dir else Path(__file__).resolve().parent
    home_name = home_path.parent.name
    stem = base / home_name
    return (stem / "entries.json", stem / "preimage.sha256",
            stem / "postimage.sha256", stem / "added-keys.json")


def load_entries(entries_path):
    if not entries_path.is_file():
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: " + str(entries_path))
    entries = json.loads(entries_path.read_text(encoding="utf-8"))
    if not isinstance(entries, dict) or not entries:
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: entries.json is not a non-empty object")
    return entries


def load_preimage(preimage_path):
    if not preimage_path.is_file():
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: " + str(preimage_path))
    return preimage_path.read_text(encoding="utf-8").strip().split()[0]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path, data, mode, expect_sha=None):
    """Write data to a temp file in path's directory, apply mode, and — when
    expect_sha is given — re-check the destination hash immediately before
    replacing (PreimageMismatch if it changed since the caller's first read).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix=path.name + ".tmp-bcu-",
                                         dir=path.parent, delete=False) as handle:
            tmp_name = handle.name
            handle.write(data)
        os.chmod(tmp_name, mode)
        if expect_sha is not None:
            current = sha256_file(path) if path.exists() else None
            if current != expect_sha:
                raise PreimageMismatch(str(path) + " changed since first read")
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if tmp_name is not None and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_json_bytes(raw, label):
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        fail(EXIT_INVALID_JSON, "INVALID_JSON: " + label + ": " + str(exc))


def backup_path_for(home_path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = home_path.parent / (home_path.name + ".bak-pre-bcu-" + stamp)
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = home_path.parent / (home_path.name + ".bak-pre-bcu-" + stamp + "-" + str(counter))
    return candidate


def resolve_entries(entries, mcp_root):
    """Return staged entries with the computer-use entry's args pointed at the
    effective MCP server root."""
    resolved = {}
    target_args = [str(mcp_root / SERVER_DIR_NAME / "server.py")]
    for key, value in entries.items():
        if key == SERVER_DIR_NAME and isinstance(value, dict):
            value = dict(value)
            value["args"] = target_args
        resolved[key] = value
    return resolved


def copy_server_files(src_dir, target_dir):
    """Copy the computer-use server runtime into target_dir with mode 0600."""
    if not src_dir.is_dir() or not (src_dir / "server.py").is_file():
        fail(EXIT_COPY_SRC_MISSING,
             "COPY_SERVER_SRC_MISSING: " + str(src_dir) + " (needs server.py)")
    for name in SERVER_FILES:
        source = src_dir / name
        if source.is_file():
            atomic_write(target_dir / name, source.read_bytes(), 0o600)
        elif name == "runtime.json":
            print("WARNING RUNTIME_JSON_ABSENT: no runtime.json in " + str(src_dir)
                  + "; copied server.py and deny.json only", file=sys.stderr)


def refresh_preimage(home, entries, preimage_path, postimage_path, added_keys_path):
    """Operator-only: record the CURRENT hash as the preimage after reporting
    which staged keys are already present and which differ from the staged
    values. Clears the stale postimage and added-keys manifest."""
    current_sha = sha256_file(home)
    data = load_json_bytes(home.read_bytes(), str(home))
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    present = [key for key in entries if isinstance(servers, dict) and key in servers]
    matching = [key for key in present if servers[key] == entries[key]]
    changed = [key for key in present if key not in matching]
    absent = [key for key in entries if key not in present]
    print("REFRESH_PREIMAGE " + str(home))
    print("STAGED_KEYS_PRESENT " + (" ".join(sorted(present)) or "(none)"))
    print("STAGED_KEYS_MATCHING " + (" ".join(sorted(matching)) or "(none)"))
    print("STAGED_KEYS_CHANGED " + (" ".join(sorted(changed)) or "(none)"))
    print("STAGED_KEYS_ABSENT " + (" ".join(sorted(absent)) or "(none)"))
    atomic_write(preimage_path, (current_sha + "\n").encode("utf-8"), 0o600)
    if postimage_path.is_file():
        postimage_path.unlink()
    if added_keys_path.is_file():
        added_keys_path.unlink()
    print("PREIMAGE_NOW " + current_sha)


def main():
    args = parse_args("Install BCU MCP registration entries into a provider-home .claude.json")
    home = resolve_home(args.home)
    entries_path, preimage_path, postimage_path, added_keys_path = staging_paths(
        args.staging_dir, home)
    entries = load_entries(entries_path)
    mcp_root = Path(args.mcp_root) if args.mcp_root else Path(MCP_ROOT_DEFAULT)
    server_dir = mcp_root / SERVER_DIR_NAME
    if not args.copy_server and not (server_dir / "server.py").is_file():
        print("WARNING SERVER_TARGET_MISSING: " + str(server_dir / "server.py")
              + " does not exist; the registered entry fails to start until the server "
                "files are copied there (--copy-server)", file=sys.stderr)
    if args.refresh_preimage:
        refresh_preimage(home, entries, preimage_path, postimage_path, added_keys_path)
        return
    preimage = load_preimage(preimage_path)
    original_bytes = home.read_bytes()
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    home_mode = stat.S_IMODE(os.stat(home).st_mode)
    if postimage_path.is_file() and original_sha == postimage_path.read_text(encoding="utf-8").strip():
        if args.copy_server:
            copy_server_files(Path(args.copy_server), server_dir)
        print("ALREADY_INSTALLED")
        return
    if original_sha != preimage:
        fail(EXIT_PREIMAGE_MISMATCH,
             "PREIMAGE_MISMATCH: current sha256 " + original_sha
             + " != staged preimage " + preimage + " for " + str(home))
    data = load_json_bytes(original_bytes, str(home))
    if not isinstance(data, dict):
        fail(EXIT_INVALID_JSON, "INVALID_JSON: " + str(home) + " is not a JSON object")
    servers = data.get("mcpServers")
    if servers is None:
        servers = {}
        data["mcpServers"] = servers
    if not isinstance(servers, dict):
        fail(EXIT_INVALID_JSON, "INVALID_JSON: mcpServers is not an object in " + str(home))
    resolved = resolve_entries(entries, mcp_root)
    servers_before = dict(servers)
    added = sorted(key for key in resolved if key not in servers)
    modified = sorted(key for key in resolved
                      if key in servers and servers[key] != resolved[key])
    if not added and not modified:
        print("ALREADY_INSTALLED")
        return
    server_dir_created = False
    if args.copy_server:
        server_dir_created = not server_dir.exists()
        copy_server_files(Path(args.copy_server), server_dir)
    backup = None
    try:
        backup = backup_path_for(home)
        atomic_write(backup, original_bytes, 0o600)
        for key, value in resolved.items():
            servers[key] = value
        new_bytes = (json.dumps(data, indent=2) + "\n").encode("utf-8")
        atomic_write(home, new_bytes, home_mode, expect_sha=original_sha)
    except PreimageMismatch as exc:
        # The backup we just wrote holds the stale bytes we first read; remove
        # it so no later rollback can restore a pre-race snapshot.
        if backup is not None and backup.exists():
            backup.unlink()
        fail(EXIT_PREIMAGE_MISMATCH, "PREIMAGE_MISMATCH: " + str(exc))
    atomic_write(postimage_path, (sha256_file(home) + "\n").encode("utf-8"), 0o600)
    manifest = {
        "added": added,
        "modified": modified,
        "previous_values": {key: servers_before[key] for key in modified},
        "mcp_server_dir": str(server_dir) if args.copy_server else None,
        "mcp_server_dir_created": server_dir_created,
    }
    atomic_write(added_keys_path, (json.dumps(manifest, indent=2) + "\n").encode("utf-8"), 0o600)
    print("INSTALLED " + " ".join(sorted(added + modified)))
    print("BACKUP " + backup.name)


if __name__ == "__main__":
    main()

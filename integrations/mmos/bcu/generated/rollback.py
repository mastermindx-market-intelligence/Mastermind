#!/usr/bin/env python3
"""BCU staged rollback: restore a provider-home .claude.json after a BCU install.

Generic script — works on any home passed via --home. Restores the newest
`.claude.json.bak-pre-bcu-*` backup next to the file. With NO backup it
REFUSES (exit 7) unless the install's added-keys.json manifest is present, in
which case it removes ONLY the keys that manifest records as added by this
install — never keys that pre-existed or were merely modified. Performs no
preimage check: rollback must work regardless of intermediate edits.

--remove-server: additionally deletes the MCP server directory that a
--copy-server install created, ONLY when the manifest records that this
install created it (SERVER_DIR_KEPT otherwise).

Every write goes through a temp file in the destination directory plus
os.replace, with the destination hash re-checked immediately before replacing
(CHANGED_SINCE_READ abort when the file changed since first read).
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

EXIT_BAD_HOME = 2
EXIT_HOME_NOT_FOUND = 3
EXIT_STAGING_MISSING = 4
EXIT_INVALID_JSON = 6
EXIT_NO_BACKUP = 7
EXIT_CHANGED_SINCE_READ = 8

BACKUP_GLOB = ".claude.json.bak-pre-bcu-*"


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
    parser.add_argument("--remove-server", action="store_true",
                        help="also delete the MCP server directory when the manifest "
                             "records that this install created it")
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
    return stem / "entries.json", stem / "postimage.sha256", stem / "added-keys.json"


def load_entries(entries_path):
    if not entries_path.is_file():
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: " + str(entries_path))
    entries = json.loads(entries_path.read_text(encoding="utf-8"))
    if not isinstance(entries, dict) or not entries:
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: entries.json is not a non-empty object")
    return entries


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


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(EXIT_INVALID_JSON, "INVALID_JSON: " + str(path) + ": " + str(exc))


def clear_staging_records(postimage_path, added_keys_path):
    if postimage_path.is_file():
        postimage_path.unlink()
    if added_keys_path.is_file():
        added_keys_path.unlink()


def maybe_remove_server_dir(manifest, remove_server):
    """Delete the copied server directory only when this install created it."""
    if not remove_server:
        return
    if not isinstance(manifest, dict):
        print("SERVER_DIR_KEPT no added-keys.json manifest")
        return
    server_dir = manifest.get("mcp_server_dir")
    created = manifest.get("mcp_server_dir_created")
    if not created or not server_dir:
        print("SERVER_DIR_KEPT manifest does not record this install as creator")
        return
    target = Path(server_dir)
    if not target.exists():
        print("SERVER_DIR_KEPT directory already absent: " + server_dir)
        return
    shutil.rmtree(target)
    print("SERVER_DIR_REMOVED " + server_dir)


def main():
    args = parse_args("Roll back a BCU staged install on a provider-home .claude.json")
    home = resolve_home(args.home)
    entries_path, postimage_path, added_keys_path = staging_paths(args.staging_dir, home)
    entries = load_entries(entries_path)
    manifest = None
    if added_keys_path.is_file():
        manifest = load_json(added_keys_path)
    original_sha = sha256_file(home)
    home_mode = stat.S_IMODE(os.stat(home).st_mode)
    backups = sorted(home.parent.glob(BACKUP_GLOB))
    removed = None
    if backups:
        newest = backups[-1]
        new_bytes = newest.read_bytes()
    else:
        if not isinstance(manifest, dict):
            fail(EXIT_NO_BACKUP,
                 "NO_BACKUP: no " + BACKUP_GLOB + " backup and no added-keys.json manifest "
                 "for " + str(home) + "; refusing to delete staged keys (rollback must "
                 "never delete keys that pre-existed this install)")
        added = manifest.get("added") if isinstance(manifest.get("added"), list) else []
        previous = manifest.get("previous_values")
        if not isinstance(previous, dict):
            previous = {}
        data = load_json(home)
        if not isinstance(data, dict):
            fail(EXIT_INVALID_JSON, "INVALID_JSON: " + str(home) + " is not a JSON object")
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            fail(EXIT_INVALID_JSON, "INVALID_JSON: mcpServers is not an object in " + str(home))
        removed = [key for key in sorted(added) if key in servers]
        restored = [key for key in sorted(previous) if key in servers]
        if not removed and not restored:
            print("NOTHING_TO_ROLLBACK")
            maybe_remove_server_dir(manifest, args.remove_server)
            clear_staging_records(postimage_path, added_keys_path)
            return
        for key in removed:
            del servers[key]
        for key in restored:
            servers[key] = previous[key]
        new_bytes = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    try:
        atomic_write(home, new_bytes, home_mode, expect_sha=original_sha)
    except PreimageMismatch as exc:
        fail(EXIT_CHANGED_SINCE_READ, "CHANGED_SINCE_READ: " + str(exc))
    clear_staging_records(postimage_path, added_keys_path)
    maybe_remove_server_dir(manifest, args.remove_server)
    if removed is None:
        print("ROLLED_BACK_FROM " + backups[-1].name)
    else:
        print("ROLLED_BACK_KEYS " + " ".join(removed))
        if restored:
            print("RESTORED_KEYS " + " ".join(restored))


if __name__ == "__main__":
    main()

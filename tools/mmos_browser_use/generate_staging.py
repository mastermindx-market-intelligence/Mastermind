#!/usr/bin/env python3
"""BCU staged-install generator (lane BCU, browser + computer use).

Produces the committed staged install tree under integrations/mmos/bcu/generated/:

    generated/
      MANIFEST.json
      install.py            generic staged-install scripts (any home via --home)
      rollback.py
      verify.py
      <home>/entries.json     exact JSON fragment to merge into mcpServers
      <home>/preimage.sha256  sha256 of the home .claude.json at generation time

Two modes:

* default (no --home): stage the five known T3 provider homes. The
  `mmx-browser` entry is staged for `fabric-unified-router-worker` only (the
  other four homes already carry it); the `mmos-computer-use` entry is staged
  for all five.
* --home PATH: stage an arbitrary .claude.json (used for tests and ad-hoc
  targets). Refuses paths not ending in '.claude.json'. Emits the
  `mmos-computer-use` entry always; `mmx-browser` only with --mmx-browser.

Only reads mcpServers registration names/commands and hashes of the target
files; prints nothing else from them. Writes only inside --out (default:
integrations/mmos/bcu/generated/). Zero dependencies beyond the stdlib.

Guard: with the default --out, a run REFUSES (exit 6) when the committed
generated/ tree already exists, naming the files it would overwrite. Pass
--force to overwrite it, or --out elsewhere to stage into a fresh directory.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "integrations" / "mmos" / "bcu" / "generated"
PROVIDERS_ROOT = Path("/Users/chriswong/.t3/providers")

STANDARD_HOMES = [
    "experiential-claude",
    "fabric-anthropic-oauth",
    "fabric-experiential",
    "fabric-unified-router",
    "fabric-unified-router-worker",
]
WORKER_HOME = "fabric-unified-router-worker"

MMX_BROWSER_ENTRY = {
    "command": "/Users/chriswong/.local/share/mastermind-runtime/node/bin/node",
    "args": ["/Users/chriswong/.t3/mcp/mmx-browser/server.js"],
    "type": "stdio",
}
MMOS_COMPUTER_USE_ENTRY = {
    "command": "/usr/bin/python3",
    "args": ["/Users/chriswong/.t3/mcp/mmos-computer-use/server.py"],
    "type": "stdio",
}

EXIT_BAD_HOME = 2
EXIT_HOME_NOT_FOUND = 3
EXIT_IO = 4
EXIT_GENERATED_TREE_EXISTS = 6

SCRIPT_INSTALL = r'''#!/usr/bin/env python3
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
'''

SCRIPT_ROLLBACK = r'''#!/usr/bin/env python3
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
'''

SCRIPT_VERIFY = r'''#!/usr/bin/env python3
"""BCU staged verify: report our registration entries' presence in a home .claude.json.

Generic script — works on any home passed via --home. Prints one VERIFY line
per staged entry (PRESENT / ABSENT / PRESENT_MISMATCH) plus the current
sha256 of the file. Exits 0 only when every staged entry is present and equal.

--mcp-root DIR compares against the entry pointing at DIR/mmos-computer-use/
(as written by an install run with the same --mcp-root).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

EXIT_BAD_HOME = 2
EXIT_HOME_NOT_FOUND = 3
EXIT_STAGING_MISSING = 4
EXIT_INVALID_JSON = 6

MCP_ROOT_DEFAULT = "/Users/chriswong/.t3/mcp"
SERVER_DIR_NAME = "mmos-computer-use"


def fail(code, message):
    print(message, file=sys.stderr)
    sys.exit(code)


def parse_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--home", required=True,
                        help="path to the provider-home .claude.json to inspect")
    parser.add_argument("--staging-dir", default=None,
                        help="staged tree root (default: directory containing this script)")
    parser.add_argument("--mcp-root", default=None, metavar="DIR",
                        help="MCP server root used by the install being verified "
                             "(default: " + MCP_ROOT_DEFAULT + ")")
    return parser.parse_args()


def resolve_home(raw):
    if not raw or not raw.endswith(".claude.json"):
        fail(EXIT_BAD_HOME,
             "BAD_HOME_PATH: --home must be an explicit path ending in '.claude.json'")
    path = Path(raw)
    if not path.is_file():
        fail(EXIT_HOME_NOT_FOUND, "HOME_NOT_FOUND: " + str(path))
    return path


def load_entries(entries_path):
    if not entries_path.is_file():
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: " + str(entries_path))
    entries = json.loads(entries_path.read_text(encoding="utf-8"))
    if not isinstance(entries, dict) or not entries:
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: entries.json is not a non-empty object")
    return entries


def resolve_entries(entries, mcp_root):
    resolved = {}
    target_args = [str(mcp_root / SERVER_DIR_NAME / "server.py")]
    for key, value in entries.items():
        if key == SERVER_DIR_NAME and isinstance(value, dict):
            value = dict(value)
            value["args"] = target_args
        resolved[key] = value
    return resolved


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    args = parse_args("Verify BCU registration entries in a provider-home .claude.json")
    home = resolve_home(args.home)
    base = Path(args.staging_dir) if args.staging_dir else Path(__file__).resolve().parent
    entries = load_entries(base / home.parent.name / "entries.json")
    mcp_root = Path(args.mcp_root) if args.mcp_root else Path(MCP_ROOT_DEFAULT)
    entries = resolve_entries(entries, mcp_root)
    try:
        data = json.loads(home.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(EXIT_INVALID_JSON, "INVALID_JSON: " + str(home) + ": " + str(exc))
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        servers = {}
    ok = True
    for key in sorted(entries):
        expected = entries[key]
        actual = servers.get(key)
        if actual is None:
            print("VERIFY " + key + " ABSENT")
            ok = False
        elif actual == expected:
            print("VERIFY " + key + " PRESENT")
        else:
            print("VERIFY " + key + " PRESENT_MISMATCH")
            ok = False
    print("SHA256 " + sha256_file(home))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
'''

SCRIPTS = {
    "install.py": SCRIPT_INSTALL,
    "rollback.py": SCRIPT_ROLLBACK,
    "verify.py": SCRIPT_VERIFY,
}


def entries_for(home_name, with_mmx_browser):
    entries = {"mmos-computer-use": dict(MMOS_COMPUTER_USE_ENTRY)}
    if with_mmx_browser:
        entries["mmx-browser"] = dict(MMX_BROWSER_ENTRY)
    return entries


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_staged_target(out_dir, home_name, claude_json_path, entries):
    home_dir = out_dir / home_name
    home_dir.mkdir(parents=True, exist_ok=True)
    (home_dir / "entries.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    (home_dir / "preimage.sha256").write_text(sha256_file(claude_json_path) + "\n", encoding="utf-8")
    postimage = home_dir / "postimage.sha256"
    if postimage.is_file():
        postimage.unlink()
    return {
        "claude_json": str(claude_json_path),
        "sha256": sha256_file(claude_json_path),
        "entries": sorted(entries),
    }


def validate_home_argument(home_raw):
    """Validate the --home argument; returns (path, home_name) or exits nonzero.

    Runs before any output directory is created, so a refused run writes nothing.
    """
    if not home_raw or not home_raw.endswith(".claude.json"):
        print("BAD_HOME_PATH: --home must be an explicit path ending in '.claude.json'",
              file=sys.stderr)
        sys.exit(EXIT_BAD_HOME)
    home_path = Path(home_raw)
    if not home_path.is_file():
        print("HOME_NOT_FOUND: " + str(home_path), file=sys.stderr)
        sys.exit(EXIT_HOME_NOT_FOUND)
    home_name = home_path.parent.name
    if not home_name:
        print("BAD_HOME_PATH: --home must live inside its home directory", file=sys.stderr)
        sys.exit(EXIT_BAD_HOME)
    return home_path, home_name


def stage_home_argument(home_path, home_name, with_mmx_browser, out_dir):
    entries = entries_for(home_name, with_mmx_browser)
    info = write_staged_target(out_dir, home_name, home_path, entries)
    out_dir.joinpath("install.py").write_text(SCRIPT_INSTALL, encoding="utf-8")
    out_dir.joinpath("rollback.py").write_text(SCRIPT_ROLLBACK, encoding="utf-8")
    out_dir.joinpath("verify.py").write_text(SCRIPT_VERIFY, encoding="utf-8")
    for name in SCRIPTS:
        os.chmod(out_dir / name, 0o755)
    write_manifest(out_dir, {home_name: info})
    return home_name


def stage_standard_homes(out_dir):
    targets = {}
    for home_name in STANDARD_HOMES:
        claude_json = PROVIDERS_ROOT / home_name / ".claude.json"
        if not claude_json.is_file():
            print("HOME_NOT_FOUND: " + str(claude_json), file=sys.stderr)
            sys.exit(EXIT_HOME_NOT_FOUND)
        with_mmx = home_name == WORKER_HOME
        targets[home_name] = write_staged_target(
            out_dir, home_name, claude_json, entries_for(home_name, with_mmx))
    for name, source in SCRIPTS.items():
        out_dir.joinpath(name).write_text(source, encoding="utf-8")
        os.chmod(out_dir / name, 0o755)
    write_manifest(out_dir, targets)


def check_default_out_guard(out_dir, force=False):
    """Return the files a default-out run would overwrite, or None to proceed.

    Only the default --out is guarded: an explicit --out elsewhere is the
    operator's own directory. --force overrides the refusal.
    """
    if force:
        return None
    out_dir = Path(out_dir)
    if out_dir.resolve() != Path(DEFAULT_OUT).resolve():
        return None
    if not out_dir.is_dir():
        return None
    existing = sorted(path.name for path in out_dir.iterdir() if path.is_file())
    return existing or None


def write_manifest(out_dir, targets):
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "tools/mmos_browser_use/generate_staging.py",
        "targets": targets,
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=None,
                        help="output staged tree (default: integrations/mmos/bcu/generated)")
    parser.add_argument("--home", default=None,
                        help="stage an explicit .claude.json instead of the five standard homes")
    parser.add_argument("--mmx-browser", action="store_true",
                        help="with --home: also stage the mmx-browser entry (test/aux use)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite the committed generated/ tree when --out is default")
    args = parser.parse_args()
    if args.home is not None:
        home_path, home_name = validate_home_argument(args.home)
    out_dir = Path(args.out) if args.out else DEFAULT_OUT
    blocked = check_default_out_guard(out_dir, force=args.force)
    if blocked is not None:
        print("GENERATED_TREE_EXISTS: " + str(out_dir) + " already exists; refusing to "
              "overwrite the committed tree. Would overwrite: " + " ".join(blocked)
              + ". Pass --force to overwrite, or --out elsewhere.", file=sys.stderr)
        sys.exit(EXIT_GENERATED_TREE_EXISTS)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.home is not None:
        stage_home_argument(home_path, home_name, args.mmx_browser, out_dir)
        print("STAGED " + home_name + " -> " + str(out_dir))
    else:
        if args.mmx_browser:
            print("--mmx-browser is only valid together with --home", file=sys.stderr)
            sys.exit(EXIT_BAD_HOME)
        stage_standard_homes(out_dir)
        print("STAGED 5 standard homes -> " + str(out_dir))


if __name__ == "__main__":
    main()

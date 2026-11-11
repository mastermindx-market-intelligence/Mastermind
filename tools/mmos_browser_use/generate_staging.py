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
    "command": "python3",
    "args": ["/Users/chriswong/.t3/mcp/mmos-computer-use/server.py"],
    "type": "stdio",
}

EXIT_BAD_HOME = 2
EXIT_HOME_NOT_FOUND = 3
EXIT_IO = 4

SCRIPT_INSTALL = r'''#!/usr/bin/env python3
"""BCU staged install: merge our mcpServers entries into a provider-home .claude.json.

Generic script — works on any home passed via --home. Refuses to run without an
explicit --home path ending in '.claude.json'. Verifies the staged preimage
sha256 before editing (PREIMAGE_MISMATCH abort), writes a timestamped backup
next to the file, merges ONLY the staged keys, and records a postimage sha so
re-runs are idempotent. Never removes or rewrites keys it does not own.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_BAD_HOME = 2
EXIT_HOME_NOT_FOUND = 3
EXIT_STAGING_MISSING = 4
EXIT_PREIMAGE_MISMATCH = 5
EXIT_INVALID_JSON = 6

BACKUP_GLOB = ".claude.json.bak-pre-bcu-*"


def fail(code, message):
    print(message, file=sys.stderr)
    sys.exit(code)


def parse_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--home", required=True,
                        help="path to the provider-home .claude.json to operate on")
    parser.add_argument("--staging-dir", default=None,
                        help="staged tree root (default: directory containing this script)")
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
    return stem / "entries.json", stem / "preimage.sha256", stem / "postimage.sha256"


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


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(EXIT_INVALID_JSON, "INVALID_JSON: " + str(path) + ": " + str(exc))


def backup_path_for(home_path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = home_path.parent / (home_path.name + ".bak-pre-bcu-" + stamp)
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = home_path.parent / (home_path.name + ".bak-pre-bcu-" + stamp + "-" + str(counter))
    return candidate


def main():
    args = parse_args("Install BCU MCP registration entries into a provider-home .claude.json")
    home = resolve_home(args.home)
    entries_path, preimage_path, postimage_path = staging_paths(args.staging_dir, home)
    entries = load_entries(entries_path)
    preimage = load_preimage(preimage_path)
    current_sha = sha256_file(home)
    if postimage_path.is_file() and current_sha == postimage_path.read_text(encoding="utf-8").strip():
        print("ALREADY_INSTALLED")
        return
    if current_sha != preimage:
        fail(EXIT_PREIMAGE_MISMATCH,
             "PREIMAGE_MISMATCH: current sha256 " + current_sha
             + " != staged preimage " + preimage + " for " + str(home))
    data = load_json(home)
    if not isinstance(data, dict):
        fail(EXIT_INVALID_JSON, "INVALID_JSON: " + str(home) + " is not a JSON object")
    servers = data.get("mcpServers")
    if servers is None:
        servers = {}
        data["mcpServers"] = servers
    if not isinstance(servers, dict):
        fail(EXIT_INVALID_JSON, "INVALID_JSON: mcpServers is not an object in " + str(home))
    changed = {key: value for key, value in entries.items() if servers.get(key) != value}
    if not changed:
        print("ALREADY_INSTALLED")
        return
    backup = backup_path_for(home)
    backup.write_bytes(home.read_bytes())
    for key, value in changed.items():
        servers[key] = value
    home.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    postimage_path.parent.mkdir(parents=True, exist_ok=True)
    postimage_path.write_text(sha256_file(home) + "\n", encoding="utf-8")
    print("INSTALLED " + " ".join(sorted(changed)))
    print("BACKUP " + backup.name)


if __name__ == "__main__":
    main()
'''

SCRIPT_ROLLBACK = r'''#!/usr/bin/env python3
"""BCU staged rollback: restore a provider-home .claude.json after a BCU install.

Generic script — works on any home passed via --home. Restores the newest
`.claude.json.bak-pre-bcu-*` backup next to the file; with no backup present it
removes ONLY our staged keys from mcpServers and leaves every other key
untouched. Performs no preimage check: rollback must work regardless of
intermediate edits.
"""
import argparse
import json
import sys
from pathlib import Path

EXIT_BAD_HOME = 2
EXIT_HOME_NOT_FOUND = 3
EXIT_STAGING_MISSING = 4
EXIT_INVALID_JSON = 6

BACKUP_GLOB = ".claude.json.bak-pre-bcu-*"


def fail(code, message):
    print(message, file=sys.stderr)
    sys.exit(code)


def parse_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--home", required=True,
                        help="path to the provider-home .claude.json to operate on")
    parser.add_argument("--staging-dir", default=None,
                        help="staged tree root (default: directory containing this script)")
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
    return stem / "entries.json", stem / "postimage.sha256"


def load_entries(entries_path):
    if not entries_path.is_file():
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: " + str(entries_path))
    entries = json.loads(entries_path.read_text(encoding="utf-8"))
    if not isinstance(entries, dict) or not entries:
        fail(EXIT_STAGING_MISSING, "STAGING_MISSING: entries.json is not a non-empty object")
    return entries


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(EXIT_INVALID_JSON, "INVALID_JSON: " + str(path) + ": " + str(exc))


def clear_postimage(postimage_path):
    if postimage_path.is_file():
        postimage_path.unlink()


def main():
    args = parse_args("Roll back a BCU staged install on a provider-home .claude.json")
    home = resolve_home(args.home)
    entries_path, postimage_path = staging_paths(args.staging_dir, home)
    entries = load_entries(entries_path)
    backups = sorted(home.parent.glob(BACKUP_GLOB))
    if backups:
        newest = backups[-1]
        home.write_bytes(newest.read_bytes())
        clear_postimage(postimage_path)
        print("ROLLED_BACK_FROM " + newest.name)
        return
    data = load_json(home)
    if not isinstance(data, dict):
        fail(EXIT_INVALID_JSON, "INVALID_JSON: " + str(home) + " is not a JSON object")
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        fail(EXIT_INVALID_JSON, "INVALID_JSON: mcpServers is not an object in " + str(home))
    removed = [key for key in entries if key in servers]
    for key in removed:
        del servers[key]
    if not removed:
        print("NOTHING_TO_ROLLBACK")
        clear_postimage(postimage_path)
        return
    home.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    clear_postimage(postimage_path)
    print("ROLLED_BACK_KEYS " + " ".join(sorted(removed)))


if __name__ == "__main__":
    main()
'''

SCRIPT_VERIFY = r'''#!/usr/bin/env python3
"""BCU staged verify: report our registration entries' presence in a home .claude.json.

Generic script — works on any home passed via --home. Prints one VERIFY line
per staged entry (PRESENT / ABSENT / PRESENT_MISMATCH) plus the current
sha256 of the file. Exits 0 only when every staged entry is present and equal.
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


def fail(code, message):
    print(message, file=sys.stderr)
    sys.exit(code)


def parse_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--home", required=True,
                        help="path to the provider-home .claude.json to inspect")
    parser.add_argument("--staging-dir", default=None,
                        help="staged tree root (default: directory containing this script)")
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
    args = parser.parse_args()
    if args.home is not None:
        home_path, home_name = validate_home_argument(args.home)
    out_dir = Path(args.out) if args.out else DEFAULT_OUT
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

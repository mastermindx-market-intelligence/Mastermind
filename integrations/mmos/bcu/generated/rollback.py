#!/usr/bin/env python3
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

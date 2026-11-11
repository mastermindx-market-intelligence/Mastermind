#!/usr/bin/env python3
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

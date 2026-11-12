#!/usr/bin/env python3
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

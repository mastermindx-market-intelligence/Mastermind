#!/usr/bin/env python3
"""Make, check or append one route B authorized_keys line on the Paper host.

  keyline.py make   --profile read|design --from <ip> --pubkey <file> --runtime <dir> --label <name>
  keyline.py check  --line-file <file> --runtime <dir>
  keyline.py append --line-file <file> --authorized-keys <file> --backup-dir <new dir> [--apply]

Every line has exactly: restrict, one literal from= address, and a forced command that
is one of the runtime's fixed gate scripts. `restrict` turns off pty, agent, X11 and
port forwarding and ~/.ssh/rc. `append` never rewrites or reorders existing lines: it
copies the file to a new backup directory, then appends one line. Without --apply it
only prints what it would do. It prints public key fingerprints and sha256 only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import shutil
import sys
from pathlib import Path

LABEL = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
KEY = re.compile(r"^ssh-ed25519 (AAAAC3NzaC1lZDI1NTE5[A-Za-z0-9+/]{48,}={0,2})(?: [^\n]*)?$")
LINE = re.compile(
    r'^restrict,from="(?P<ip>[0-9a-fA-F:.]+)",command="(?P<cmd>/[A-Za-z0-9._/-]+/bin/paper-mcp-(?P<profile>read|design))"'
    r" ssh-ed25519 (?P<b64>[A-Za-z0-9+/]+={0,2}) mmos-paper-(?P=profile)-(?P<label>[a-z0-9][a-z0-9-]{0,40})$"
)


def fingerprint(b64: str) -> str:
    raw = base64.b64decode(b64, validate=True)
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")


def literal_ip(value: str) -> str:
    ip = ipaddress.ip_address(value)  # raises on wildcards, CIDR, hostnames, lists
    if ip.is_unspecified or ip.is_multicast:
        raise ValueError("from= must be one host address")
    return str(ip)


def check_line(line: str, runtime: Path | None = None) -> dict:
    m = LINE.match(line)
    if not m:
        raise ValueError("LINE_SHAPE_REFUSED")
    literal_ip(m["ip"])
    raw = base64.b64decode(m["b64"], validate=True)
    if raw[:15] != b"\x00\x00\x00\x0bssh-ed25519" or len(raw) != 51:
        raise ValueError("KEY_BLOB_REFUSED")
    if runtime is not None:
        expected = str(runtime / "bin" / f"paper-mcp-{m['profile']}")
        if m["cmd"] != expected:
            raise ValueError("COMMAND_NOT_THIS_RUNTIME")
        gate = Path(expected)
        if not gate.is_file() or gate.is_symlink() or gate.stat().st_mode & 0o022:
            raise ValueError("GATE_MISSING_OR_WRITABLE")
    return {"profile": m["profile"], "from": m["ip"], "label": m["label"],
            "command": m["cmd"], "key_fingerprint": fingerprint(m["b64"])}


def make(profile: str, ip: str, pubkey: str, runtime: Path, label: str) -> str:
    if profile not in ("read", "design"):
        raise ValueError("profile must be read or design")
    if not LABEL.match(label):
        raise ValueError("label must be lowercase letters, digits and hyphens")
    m = KEY.match(pubkey.strip())
    if not m or "\n" in pubkey.strip():
        raise ValueError("pubkey must be one ssh-ed25519 public key line")
    line = (f'restrict,from="{literal_ip(ip)}",command="{runtime}/bin/paper-mcp-{profile}"'
            f" ssh-ed25519 {m[1]} mmos-paper-{profile}-{label}")
    check_line(line, runtime)
    return line


def append(line: str, ak: Path, backup_dir: Path, apply: bool) -> dict:
    info = check_line(line)
    existing = ak.read_bytes() if ak.exists() else b""
    if line.encode() in existing.splitlines():
        raise ValueError("LINE_ALREADY_PRESENT")
    for old in existing.decode(errors="replace").splitlines():
        found = re.search(r"(?:^|\s)ssh-ed25519\s+([A-Za-z0-9+/]+={0,2})(?:\s|$)", old)
        try:
            same = bool(found) and fingerprint(found[1]) == info["key_fingerprint"]
        except ValueError:
            same = False
        if same:
            raise ValueError("KEY_ALREADY_AUTHORIZED")
    plan = {"authorized_keys": str(ak), "preimage_sha256": hashlib.sha256(existing).hexdigest(),
            "backup": str(backup_dir / "authorized_keys"), **info}
    if not apply:
        return {"state": "DRY_RUN", **plan}
    if backup_dir.exists():
        raise ValueError("BACKUP_DIR_EXISTS")
    backup_dir.mkdir(mode=0o700, parents=True)
    if ak.exists():
        shutil.copy2(ak, backup_dir / "authorized_keys")
    sep = b"" if not existing or existing.endswith(b"\n") else b"\n"
    fd = os.open(ak, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "ab") as fh:
        fh.write(sep + line.encode() + b"\n")
    after = ak.read_bytes()
    if not after.startswith(existing):
        raise ValueError("PREFIX_CHANGED_DURING_APPEND")
    return {"state": "APPENDED", **plan, "postimage_sha256": hashlib.sha256(after).hexdigest()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("--profile", required=True)
    mk.add_argument("--from", dest="ip", required=True)
    mk.add_argument("--pubkey", required=True)
    mk.add_argument("--runtime", required=True)
    mk.add_argument("--label", required=True)
    ck = sub.add_parser("check")
    ck.add_argument("--line-file", required=True)
    ck.add_argument("--runtime")
    apd = sub.add_parser("append")
    apd.add_argument("--line-file", required=True)
    apd.add_argument("--authorized-keys", required=True)
    apd.add_argument("--backup-dir", required=True)
    apd.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "make":
            print(make(a.profile, a.ip, Path(a.pubkey).read_text(), Path(a.runtime), a.label))
        elif a.cmd == "check":
            line = Path(a.line_file).read_text().strip()
            print(json.dumps(check_line(line, Path(a.runtime) if a.runtime else None)))
        else:
            line = Path(a.line_file).read_text().strip()
            print(json.dumps(append(line, Path(a.authorized_keys), Path(a.backup_dir), a.apply)))
    except (ValueError, OSError) as exc:
        print(json.dumps({"state": "REFUSED", "reason": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

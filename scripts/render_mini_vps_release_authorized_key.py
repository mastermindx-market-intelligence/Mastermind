#!/usr/bin/env python3
"""Render one restricted authorized_keys entry for a mini-to-M2 release relay key."""
from __future__ import annotations

import argparse
import base64
import binascii
import re
import struct
import sys
from pathlib import Path


_KEY_TYPE = "ssh-ed25519"
_LABEL = re.compile(r"^mini[1-9][0-9]*$")
_RELAY = "/Library/Application Support/MastermindExecutive/bin/mmx-vps-release-relay"


class RenderError(ValueError):
    pass


def _read_public_key(path: Path) -> str:
    try:
        raw = path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise RenderError("public key is unavailable") from exc
    if len(raw.encode("ascii")) > 4096 or "\x00" in raw:
        raise RenderError("public key is outside the bounded format")
    lines = raw.splitlines()
    if len(lines) != 1:
        raise RenderError("public key must contain exactly one line")
    fields = lines[0].split()
    if len(fields) < 2 or fields[0] != _KEY_TYPE:
        raise RenderError("only one ssh-ed25519 public key is accepted")
    payload = fields[1]
    try:
        decoded = base64.b64decode(payload.encode("ascii"), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RenderError("public key payload is invalid base64") from exc
    try:
        type_len = struct.unpack(">I", decoded[:4])[0]
        type_end = 4 + type_len
        wire_type = decoded[4:type_end]
        key_len = struct.unpack(">I", decoded[type_end:type_end + 4])[0]
        key_start = type_end + 4
        key_end = key_start + key_len
    except (struct.error, ValueError) as exc:
        raise RenderError("public key payload is not a valid OpenSSH blob") from exc
    if wire_type != b"ssh-ed25519" or key_len != 32 or key_end != len(decoded):
        raise RenderError("public key payload is not an Ed25519 OpenSSH key blob")
    return payload


def render(public_key: Path, label: str) -> str:
    if _LABEL.fullmatch(label) is None:
        raise RenderError("label must be a mini fleet identity such as mini4")
    payload = _read_public_key(public_key)
    forced = f'restrict,command="{_RELAY} {label}"'
    return f"{forced} {_KEY_TYPE} {payload} mastermind-release-{label}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-key-file", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    try:
        line = render(args.public_key_file.expanduser().resolve(), args.label)
    except RenderError as exc:
        print(f"release authorized-key render refused: {exc}", file=sys.stderr)
        return 2
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

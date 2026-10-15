"""Command line for launch artifacts, observations and exact prepared prompts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ops.fabric_launch.context import (LaunchInputError, MAX_PACKET_BYTES, canonical,
    parse, prepare, verify_packet, augment_plain_prompt, digest)
from ops.fabric_launch.observe import observe, ENDPOINTS
from ops.fabric_launch.agentos import read_context


def read_regular(path, maximum=MAX_PACKET_BYTES):
    path = Path(path)
    # macOS has fixed OS-owned /tmp and /var aliases; preserve normal CLI use.
    for alias, physical in (("/tmp", "/private/tmp"), ("/var", "/private/var")):
        prefix = Path(alias)
        if prefix.is_symlink() and str(prefix.resolve()) == physical:
            try:
                tail = path.relative_to(prefix)
            except ValueError:
                continue
            path = Path(physical) / tail
    # Refuse links in the path, not just in the final component.
    for item in [path, *path.parents]:
        if item.is_symlink():
            raise LaunchInputError("INPUT_SYMLINK_REFUSED")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
            raise LaunchInputError("INPUT_FILE_INVALID")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(data) != before.st_size or identity(before) != identity(after):
            raise LaunchInputError("INPUT_FILE_CHANGED")
        return data
    finally:
        os.close(fd)


def write_exclusive(path, data):
    path = Path(path)
    for parent in path.parents:
        if parent.is_symlink():
            raise LaunchInputError("OUTPUT_PARENT_SYMLINK_REFUSED")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if read_regular(path, max(MAX_PACKET_BYTES, len(data))) != data:
        raise LaunchInputError("OUTPUT_READBACK_MISMATCH")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("input"); p.add_argument("--output", required=True)
    p = sub.add_parser("render")
    p.add_argument("packet")
    p = sub.add_parser("doctor")
    p.add_argument("--mission-ref", required=True); p.add_argument("--workspace", required=True)
    p.add_argument("--repository"); p.add_argument("--service", action="append", choices=sorted(ENDPOINTS), default=[])
    p.add_argument("--output", required=True)
    p = sub.add_parser("context")
    p.add_argument("--workstream", required=True); p.add_argument("--budget", type=int, default=4000)
    p.add_argument("--output", required=True)
    p = sub.add_parser("augment")
    p.add_argument("input"); p.add_argument("--task-class", default="")
    p.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            packet = prepare(parse(read_regular(args.input)))
            write_exclusive(args.output, canonical(packet) + b"\n")
            print(json.dumps({"state": packet["state"], "role": packet["role"],
                              "packet_sha256": packet["packet_sha256"],
                              "commission_sha256": packet["commission_sha256"]}, sort_keys=True))
        elif args.command == "render":
            packet = verify_packet(parse(read_regular(args.packet), MAX_PACKET_BYTES))
            sys.stdout.write(packet["instructions_markdown"])
        elif args.command == "doctor":
            result = observe(args.mission_ref, args.workspace, repository=args.repository, services=args.service)
            write_exclusive(args.output, canonical(result) + b"\n")
            print(json.dumps({"scope_ref": result["scope_ref"],
                              "callable": [r["tool"] for r in result["items"] if r["state"] == "CALLABLE"],
                              "authority_granted": False}, sort_keys=True))
        elif args.command == "context":
            raw, receipt = read_context(args.workstream, args.budget)
            write_exclusive(args.output, raw)
            print(json.dumps(receipt, sort_keys=True))
        else:
            prompt, receipt = augment_plain_prompt(read_regular(args.input, 512 * 1024).decode(), args.task_class)
            write_exclusive(args.output, prompt.encode())
            print(json.dumps(receipt, sort_keys=True))
        return 0
    except (LaunchInputError, OSError, ValueError, UnicodeError) as exc:
        # Non-LaunchInputError messages may contain file paths or provider responses.
        code = str(exc) if isinstance(exc, LaunchInputError) else type(exc).__name__
        print("FABRIC_LAUNCH_REFUSED " + code, file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())

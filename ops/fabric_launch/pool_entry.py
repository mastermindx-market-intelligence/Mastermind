"""Thin prompt-method delivery before the incumbent pool launcher.

No provider/host selection, credential access, lease, retry or result lifecycle.
The original dispatcher and its exact arguments remain the execution authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ops.fabric_launch.context import (PACKET_SCHEMA, MAX_PACKET_BYTES, BOOT_KERNEL,
    LaunchInputError, canonical, digest, parse, verify_packet, augment_plain_prompt)
from ops.fabric_launch.cli import read_regular, write_exclusive


def positional_indices(args):
    """Locate the existing remote packet argument without selecting a route."""
    result = []
    i = 0
    while i < len(args):
        item = args[i]
        if item in ("--out", "--max-age"):
            if i + 1 >= len(args):
                raise LaunchInputError("REMOTE_OPTION_VALUE_MISSING")
            i += 2
        elif item in ("--dry-run", "--refresh"):
            i += 1
        elif item.startswith("-"):
            raise LaunchInputError("REMOTE_OPTION_UNSUPPORTED")
        else:
            result.append(i)
            i += 1
    if len(result) not in (4, 5):
        raise LaunchInputError("REMOTE_POSITIONALS_INVALID")
    return result


def materialize(raw, task_class, *, expected_scope=None):
    """Methods do not authenticate an observation or grant a tool capability."""
    source = raw.decode("utf-8")
    packet = None
    if source.lstrip().startswith("{"):
        try:
            candidate = parse(raw, MAX_PACKET_BYTES)
        except LaunchInputError:
            if PACKET_SCHEMA in source:
                raise
        else:
            if candidate.get("schema") == PACKET_SCHEMA:
                packet = verify_packet(candidate)
    if packet is None:
        return augment_plain_prompt(source, task_class)
    if expected_scope is None or packet["input"]["observations"]["scope_ref"] not in expected_scope:
        raise LaunchInputError("OBSERVED_EXECUTION_SCOPE_MISMATCH")
    text = packet["instructions_markdown"]
    return text, {"delivery_mode": "compiled_commission", "native_skill_attested": False,
                  "role": packet["role"], "packet_sha256": packet["packet_sha256"],
                  "delivered_sha256": digest(text.encode()),
                  "project_context": "EXPLICIT_ATTRIBUTED_INPUT",
                  "state": "PREPARED_NOT_ADMITTED"}


def execution_scopes(kit, host, cwd):
    if host == "auto":
        # Placement belongs to the existing dispatcher. Never preselect a different
        # host merely to make a supplied positive tool observation appear valid.
        return set()
    if host == "local":
        names = [socket.gethostname()]
    else:
        hosts = parse(read_regular(Path(kit) / "ext/hosts.json", 1024 * 1024), 1024 * 1024)
        entry = hosts.get(host, {})
        names = entry.get("hostnames", [])
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise LaunchInputError("HOST_OBSERVATION_SCOPE_INVALID")
    return {"local:" + n + ":" + cwd for n in names}


def invoke(kit, kind, args, *, task_class, call=subprocess.call):
    kit = Path(kit).resolve(strict=True)
    args = list(args)
    if kind == "remote":
        positions = positional_indices(args)
        host, mode, packet_path, cwd = (args[i] for i in positions[:4])
        raw = read_regular(packet_path, 512 * 1024)
        scopes = execution_scopes(kit, host, cwd)
    elif kind == "run":
        if len(args) not in (2, 3, 4):
            raise LaunchInputError("RUN_POSITIONALS_INVALID")
        mode, raw = args[0], args[1].encode()
        cwd = args[2] if len(args) > 2 else os.getcwd()
        scopes = execution_scopes(kit, "local", cwd)
    else:
        raise LaunchInputError("POOL_OPERATION_UNSUPPORTED")
    prompt, receipt = materialize(raw, task_class, expected_scope=scopes)
    print("FABRIC_BOOT_INPUT " + json.dumps(receipt, sort_keys=True, separators=(",", ":")),
          file=sys.stderr, flush=True)
    if kind == "run":
        args[1] = prompt
        # sub.sh remains the provider/project/host admission owner.
        return call(["bash", str(kit / "ext/sub.sh"), *args])
    if "--dry-run" in args:
        return call(["bash", str(kit / "ext/remote_sub.sh"), *args])
    # Keep compiled task artifacts alongside the original dispatcher's evidence,
    # never in a new registry. Only this invocation's two exclusive files exist.
    parent = kit / "ext/state/remote_sub"
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="boot-", dir=parent))
    target = folder / "packet.txt"
    evidence = folder / "input-receipt.json"
    write_exclusive(target, prompt.encode())
    write_exclusive(evidence, canonical(receipt) + b"\n")
    args[positions[2]] = str(target)
    rc = 78
    try:
        # No loop, alternative model, host, account or fallback is introduced.
        rc = call(["bash", str(kit / "ext/remote_sub.sh"), *args])
        return rc
    finally:
        if rc == 0:
            # Delete only the exact files we created; never recursive cleanup.
            target.unlink(missing_ok=True)
            evidence.unlink(missing_ok=True)
            try:
                folder.rmdir()
            except OSError:
                pass
        else:
            print("FABRIC_BOOT_INPUT_RETAINED " + str(folder), file=sys.stderr, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", required=True)
    parser.add_argument("kind", choices=("run", "remote"))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    child = None
    previous = {}
    def run_original(command):
        nonlocal child
        child = subprocess.Popen(command)
        def forward(signum, _frame):
            # Preserve the original process/carrier. An interrupted provider effect
            # is reconciled by the incumbent dispatcher, never replayed here.
            if child.poll() is None:
                child.send_signal(signum)
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, forward)
        try:
            return child.wait()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    try:
        return invoke(args.kit, args.kind, args.args,
                      task_class=os.environ.get("POOL_TASK_CLASS", ""), call=run_original)
    except (LaunchInputError, OSError, ValueError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, LaunchInputError) else type(exc).__name__
        print("FABRIC_BOOT_REFUSED " + code, file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())

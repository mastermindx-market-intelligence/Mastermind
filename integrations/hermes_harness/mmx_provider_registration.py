"""Guarded switch of the registered mmx-browser server path (runbook step 4).

After the versioned-pin migration, ``mcpServers.mmx-browser.args`` in each
provider home's ``.claude.json`` must be repointed from the flat
``<mmx>/server.js`` to ``<mmx>/current/server.js`` — the literal symlink path,
so later migrations only re-point ``current`` and never touch these files
again. Four homes carry the entry (``experiential-claude``,
``fabric-experiential``, ``fabric-unified-router``, ``fabric-anthropic-oauth``);
``fabric-unified-router-worker`` has none and must stay that way.

Running sessions rewrite ``.claude.json``, so a hand edit can lose a race in
either direction, and no source writer ever registered mmx-browser in these
files (the repo's only other ``.claude.json`` writer is the subscription
worker's sandboxed onboarding stub). This command therefore:

* checks EVERY file before the first write — each entry must be exactly the
  expected old path (or already exactly the new one); one wrong, missing,
  unreadable or unparsable file refuses the whole run, naming the home and a
  code, never quoting file contents;
* writes through the owned CAS writer: a file that changed since its check
  refuses that file alone (``WRITE_RACE``) and keeps the session's bytes, and
  each write leaves a ``.claude.json.previous.<16hex>`` backup;
* reads every switched file back after a short wait, so a session that
  rewrites the file after our write is reported (``READBACK_RACE_*``), not
  silently believed;
* prints file names and status codes only — never contents.

A race is reported, not retried in a loop: re-run the command once the racing
session is idle; an already-switched home is a no-op, so re-runs are safe.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import time

from .browser_routes import decode
from .install_browser import digest, json_bytes, read_owned, write_owned

SERVER_KEY = "mmx-browser"
FILE_NAME = ".claude.json"
DEFAULT_HOMES = ("experiential-claude", "fabric-experiential",
                 "fabric-unified-router", "fabric-anthropic-oauth")
DEFAULT_WORKER_HOME = "fabric-unified-router-worker"


class SwitchRefusal(RuntimeError):
    """A pre-write check failed. Carries a home name and a code — never
    file contents; ``detail`` is a path this command itself derived."""

    def __init__(self, code, detail="", home=None):
        self.code = code
        self.home = home
        self.detail = detail
        message = code + (": " + detail if detail else "")
        super().__init__(message)


def _read_home(providers_root, home):
    """Read and strictly parse one home's .claude.json, or refuse."""
    path = providers_root / home / FILE_NAME
    if not path.parent.is_dir():
        raise SwitchRefusal("HOME_MISSING", str(path.parent), home)
    if not path.is_file():
        raise SwitchRefusal("FILE_MISSING", str(path), home)
    try:
        prior_raw = read_owned(path)
        mode = stat.S_IMODE(path.stat().st_mode)
    except Exception as error:
        raise SwitchRefusal("FILE_UNREADABLE", str(path), home) from error
    try:
        document = decode(prior_raw)
    except Exception as error:
        raise SwitchRefusal("JSON_INVALID", str(path), home) from error
    if not isinstance(document, dict):
        raise SwitchRefusal("JSON_INVALID", str(path), home)
    return path, prior_raw, mode, document


def _entry_args(document):
    """None = no mmx-browser entry; False = entry present but malformed;
    anything else = the entry's raw args value (classification decides)."""
    servers = document.get("mcpServers")
    if not isinstance(servers, dict) or SERVER_KEY not in servers:
        return None
    entry = servers[SERVER_KEY]
    if not isinstance(entry, dict) or "args" not in entry:
        return False
    return entry["args"]


def _classify(args, old_real, new_real):
    """PLANNED / ALREADY_SWITCHED / ARGS_INVALID by realpath, so a symlinked
    root and its resolved spelling are the same target."""
    if not isinstance(args, list) or not args or not all(
            isinstance(value, str) and value for value in args):
        return "ARGS_INVALID"
    reals = [os.path.realpath(value) for value in args]
    if reals[-1] == new_real:
        return "ARGS_INVALID" if old_real in reals[:-1] else "ALREADY_SWITCHED"
    if reals[-1] == old_real and reals.count(old_real) == 1:
        return "PLANNED"
    return "ARGS_INVALID"


def _readback_status(args, old_real, new_real):
    reals = [os.path.realpath(value) for value in args] if (
        isinstance(args, list) and args
        and all(isinstance(value, str) and value for value in args)) else []
    if reals and reals[-1] == new_real and old_real not in reals[:-1]:
        return "SWITCHED"
    if reals and reals[-1] == old_real:
        return "READBACK_RACE_REVERTED"
    return "READBACK_RACE_UNKNOWN"


def switch(providers_root, mmx_root, *, homes=DEFAULT_HOMES,
           worker_home=DEFAULT_WORKER_HOME, readback_wait=2.0, pause=time.sleep):
    """Check every provider home, then switch each planned .claude.json.

    Returns a receipt naming homes and status codes only. Raises
    SwitchRefusal before any write when any check fails.
    """
    providers_root = Path(providers_root).expanduser()
    mmx_root = Path(mmx_root).expanduser()
    if not providers_root.is_absolute() or not mmx_root.is_absolute():
        raise SwitchRefusal("ROOTS_NOT_ABSOLUTE",
                            "both roots must be absolute; nothing defaults to a real root")
    if not providers_root.is_dir():
        raise SwitchRefusal("PROVIDERS_ROOT_MISSING", str(providers_root))
    new_target = mmx_root / "current" / "server.js"
    if not new_target.is_file():
        # migrate (runbook step 4) must have delivered the versioned pin and
        # re-pointed `current` before any spawn is aimed at it
        raise SwitchRefusal("NEW_TARGET_MISSING", str(new_target))
    old_real = os.path.realpath(mmx_root / "server.js")
    new_real = os.path.realpath(new_target)
    new_value = str(new_target)

    # phase 1 — every file checked before the first write
    planned = []
    for home in homes:
        path, prior_raw, mode, document = _read_home(providers_root, home)
        args = _entry_args(document)
        if args is None:
            raise SwitchRefusal("ENTRY_MISSING", str(path), home)
        if args is False:
            raise SwitchRefusal("ARGS_INVALID", str(path), home)
        state = _classify(args, old_real, new_real)
        if state == "ARGS_INVALID":
            raise SwitchRefusal("ARGS_INVALID",
                                str(path) + " — the registered " + SERVER_KEY
                                + " args are not exactly the expected old server path", home)
        planned.append(dict(home=home, path=path, prior_raw=prior_raw, mode=mode,
                            document=document, args=args, state=state))

    # the worker home carries no entry and is never written; an entry there
    # refuses the whole run, and an unreadable file proves nothing safe
    worker_path = providers_root / worker_home / FILE_NAME
    if worker_path.is_file():
        _, _, _, document = _read_home(providers_root, worker_home)
        if _entry_args(document) is not None:
            raise SwitchRefusal("WORKER_HAS_ENTRY", str(worker_path), worker_home)

    # phase 2 — CAS writes; a file changed since its check refuses alone
    rows = []
    for row in planned:
        if row["state"] == "ALREADY_SWITCHED":
            rows.append(dict(home=row["home"], status="ALREADY_SWITCHED"))
            continue
        entry = row["document"]["mcpServers"][SERVER_KEY]
        entry["args"] = list(row["args"][:-1]) + [new_value]
        try:
            write_owned(row["path"], json_bytes(row["document"]), row["mode"],
                        expected=digest(row["prior_raw"]))
        except Exception:
            rows.append(dict(home=row["home"], status="WRITE_RACE"))
            continue
        rows.append(dict(home=row["home"], status="SWITCHED"))

    # phase 3 — after a short wait, read every switched file back: a running
    # session may have rewritten it in the meantime
    pause(readback_wait)
    for out in rows:
        if out["status"] != "SWITCHED":
            continue
        path = providers_root / out["home"] / FILE_NAME
        try:
            args = _entry_args(decode(read_owned(path)))
        except Exception:
            args = None
        out["status"] = _readback_status(args, old_real, new_real)

    raced = any(row["status"] not in ("SWITCHED", "ALREADY_SWITCHED") for row in rows)
    return dict(state="PROVIDER_ARGS_SWITCHED_WITH_RACES" if raced else "PROVIDER_ARGS_SWITCHED",
                homes=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mmx_provider_registration",
        description="Guarded switch of the registered mmx-browser server path "
                    "in provider-home .claude.json files (runbook step 4).")
    parser.add_argument("--providers-root", required=True, type=Path,
                        help="the providers directory holding the homes (absolute)")
    parser.add_argument("--mmx-root", required=True, type=Path,
                        help="the mmx-browser pin root, already migrated (absolute)")
    parser.add_argument("--readback-wait", type=float, default=2.0,
                        help="seconds to wait before reading the switched files back")
    arguments = parser.parse_args(argv)
    try:
        receipt = switch(arguments.providers_root, arguments.mmx_root,
                         readback_wait=arguments.readback_wait)
    except SwitchRefusal as refusal:
        print("switch refused: " + str(refusal), file=sys.stderr)
        return 1
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["state"] == "PROVIDER_ARGS_SWITCHED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

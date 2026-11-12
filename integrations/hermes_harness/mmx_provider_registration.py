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
* changes one value and nothing else (class rule): the JSON-encoded old path
  must occur EXACTLY ONCE in the raw bytes — otherwise ``OLD_VALUE_NOT_UNIQUE``
  refuses the whole run before any write — only that span is replaced, the
  result must re-parse to exactly the intended one-value change, and the file
  is never re-serialised, so key order, non-ASCII text, float spellings, the
  trailing-newline state and the file mode all survive byte for byte;
* writes through the owned CAS writer: a file that changed since its check
  refuses that file alone (``WRITE_RACE``) and keeps the session's bytes, and
  each write leaves a ``.claude.json.previous.<16hex>`` backup; a write error
  that is NOT a digest mismatch is reported as what it is (``WRITE_FAILED``
  with the errno name), never as a race;
* reads every switched file back after a short wait, so a session that
  rewrites the file after our write is reported (``READBACK_RACE_*``), not
  silently believed;
* prints file names and status codes only — never contents.

A race is reported, not retried in a loop: re-run the command once the racing
session is idle; an already-switched home is a no-op, so re-runs are safe.
"""
from __future__ import annotations

import argparse
import copy
import errno
import json
import os
from pathlib import Path
import stat
import sys
import time

from .browser_routes import decode
from .install_browser import digest, read_owned, write_owned

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


def _encoded_value(value):
    """The JSON encoding of one string value, as the raw file holds it."""
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _planned_replacement(prior_raw, document, old_literal, new_value, path, home):
    """CLASS RULE: a change to one value in a settings file other programs
    own leaves every byte outside that value as it was.

    The JSON-encoded old value must occur EXACTLY ONCE in the raw bytes
    (zero or several occurrences both refuse the whole run, before any write
    in any home — several occurrences mean no span can be replaced without
    guessing which one was meant). Only that span is replaced. The result
    must re-parse to exactly the first parse with that one value changed.
    Nothing is ever re-serialised: key order, non-ASCII text, float
    spellings, the trailing-newline state and the mode all survive."""
    needle = _encoded_value(old_literal)
    occurrences = prior_raw.count(needle)
    if occurrences != 1:
        raise SwitchRefusal(
            "OLD_VALUE_NOT_UNIQUE",
            str(path) + " — the JSON-encoded old server path occurs " + str(occurrences)
            + " times in the raw bytes; exactly one occurrence is required to replace"
            " it safely, so the whole run is refused before any write", home)
    post_raw = prior_raw.replace(needle, _encoded_value(new_value))
    try:
        reparsed = decode(post_raw)
    except Exception as error:
        raise SwitchRefusal("REPLACED_JSON_INVALID", str(path), home) from error
    intended = copy.deepcopy(document)
    entry = intended["mcpServers"][SERVER_KEY]
    entry["args"] = list(entry["args"][:-1]) + [new_value]
    if reparsed != intended:
        raise SwitchRefusal(
            "REPLACE_VERIFY_FAILED",
            str(path) + " — the byte replacement did not re-parse to exactly the"
            " intended one-value change; nothing is written", home)
    return post_raw


# write_owned's digest-mismatch refusals — a file that changed since phase 1
# read it. Every other write error is reported as what it is (item c).
_CAS_REFUSALS = ("existing file differs; no overwrite",
                 "destination changed during installation",
                 "installation readback failed")


def _write_failure(row, error):
    code = (errno.errorcode.get(error.errno)
            if isinstance(error, OSError) and error.errno is not None else None)
    return dict(home=row["home"], status="WRITE_FAILED",
                detail=code or type(error).__name__)


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

    # phase 1 — every file checked, and every planned replacement computed
    # and verified in raw bytes, before the first write
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
        post_raw = (_planned_replacement(prior_raw, document, args[-1],
                                         new_value, path, home)
                    if state == "PLANNED" else None)
        planned.append(dict(home=home, path=path, prior_raw=prior_raw, mode=mode,
                            document=document, args=args, state=state,
                            post_raw=post_raw))

    # the worker home carries no entry and is never written; an entry there
    # refuses the whole run, and an unreadable file proves nothing safe
    worker_path = providers_root / worker_home / FILE_NAME
    if worker_path.is_file():
        _, _, _, document = _read_home(providers_root, worker_home)
        if _entry_args(document) is not None:
            raise SwitchRefusal("WORKER_HAS_ENTRY", str(worker_path), worker_home)

    # phase 2 — CAS writes of the byte-preserving replacement computed in
    # phase 1; a file changed since its check refuses alone (WRITE_RACE) and
    # keeps the session's bytes, any other write error reports what it is
    rows = []
    for row in planned:
        if row["state"] == "ALREADY_SWITCHED":
            rows.append(dict(home=row["home"], status="ALREADY_SWITCHED"))
            continue
        try:
            write_owned(row["path"], row["post_raw"], row["mode"],
                        expected=digest(row["prior_raw"]))
        except OSError as error:
            rows.append(_write_failure(row, error))
            continue
        except RuntimeError as error:
            if any(marker in str(error) for marker in _CAS_REFUSALS):
                rows.append(dict(home=row["home"], status="WRITE_RACE"))
            else:
                rows.append(_write_failure(row, error))
            continue
        except Exception as error:
            rows.append(_write_failure(row, error))
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

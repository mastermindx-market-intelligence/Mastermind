"""Guarded writer for the mmx-browser versioned runtime pin (BR-COMPATFIX).

Ruling-15 class rule applied to the pin migration and switch (runbook
step 4): a running bridge server captured ``runtime.json`` at startup,
re-verifies the pinned closure before every dispatch, and was spawned from
the ``server.js`` its pin resolved — editing either under a running server
fails every live session (the first install attempt's 31-server
``NATIVE_SOURCE_CLOSURE_STALE`` outage). This writer therefore:

* has no default target at all — every command requires ``--mmx-root``
  explicitly;
* never edits the flat live pin files (``$MMX/runtime.json``,
  ``$MMX/server.js``): running servers keep resolving them;
* never writes inside the folder ``$MMX/current`` resolves to — that folder
  is loaded by every server spawned since the last switch;
* treats a delivered ``runtimes/<commit>/runtime.json`` as a permanent
  delivery mark (ruling 19): it is never overwritten, demoted or re-derived
  away, because a delivered folder may be live even when ``current`` points
  elsewhere;
* switches only by an atomic symlink replace, so running servers keep their
  already-resolved files and only the next spawn sees the new pin.

One O_EXCL delivery lock (``$MMX/.deliver.lock``) covers every process that
writes delivery marks under a given ``$MMX``: the check-then-write of a
delivery is exclusive, and a migrate holds the same lock across both of its
deliveries and the repoint. A lock left behind by a crashed holder refuses
later writes until it is reconciled — fail closed, never overwrite a mark
that may be live (ruling 19).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from integrations.hermes_harness.install_browser import digest, json_bytes, read_owned, write_owned

COMMIT_RE = re.compile(r"[0-9a-f]{40}")
RUNTIME_SCHEMA = "mastermind.browser.mcp_runtime/v1"
BUILD_SCHEMA = "mastermind.browser_direct_build.v1"


def _check_commit(commit):
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise RuntimeError("invalid release commit for a versioned runtime pin: " + str(commit))
    return commit


def live_versioned_root(mmx_root):
    """The folder ``$MMX/current`` resolves to (the live versioned pin), or None."""
    current = Path(mmx_root).expanduser() / "current"
    if current.is_symlink() or current.exists():
        return current.resolve()
    return None


def _refuse_live_folder(mmx_root, target):
    live = live_versioned_root(mmx_root)
    if live is None:
        return
    resolved = Path(target).expanduser().resolve()
    if resolved == live or resolved.is_relative_to(live):
        raise RuntimeError("pin writer refused: " + str(target) + " is inside the live versioned pin folder "
                           + str(live) + " that running mmx-browser servers have loaded; a live pin folder is never written")


def _refuse_delivered(mmx_root, commit, what):
    """An existing delivery is permanent (ruling 19): refuse, never overwrite
    — a delivered folder may be the one running servers loaded."""
    target = Path(mmx_root).expanduser() / "runtimes" / commit
    pin = target / "runtime.json"
    if pin.exists() or pin.is_symlink() or (target / "server.js").exists():
        raise RuntimeError(what + ": " + str(pin) + " is already delivered; a delivery mark is "
                           "permanent (ruling 19) and a delivered pin folder may be live — it is never overwritten")


class _DeliveryLock:
    """One O_EXCL lock across every process writing delivery marks under $MMX.

    The lock file's existence IS the held lock: a second process (or a later
    run after a crash) refuses instead of waiting, because a delivery mark is
    permanent and a half-written delivery may already be live. The holder
    removes it on exit; a foreign or stale lock is never removed here.
    """

    def __init__(self, mmx_root):
        self._path = Path(mmx_root).expanduser() / ".deliver.lock"
        self._fd = None

    def __enter__(self):
        try:
            self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise RuntimeError(
                "pin writer refused: the delivery lock " + str(self._path)
                + " is held by another process or was left by a crashed one;"
                " one lock covers every delivery-mark writer under this root —"
                " reconcile the lock before writing again") from None
        return self

    def __exit__(self, *exc):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            # missing_ok: a human reconciling a crashed holder may have removed
            # the lock mid-write; that must not mask the body's own exception
            # (e.g. a delivery refusal) with a FileNotFoundError (LOW-1).
            self._path.unlink(missing_ok=True)
        return False


def _deliver_locked(mmx_root, commit, runtime_document, server_bytes):
    """The delivery check-and-write; the caller holds the delivery lock."""
    _refuse_delivered(mmx_root, commit, "pin writer refused")
    target = Path(mmx_root).expanduser() / "runtimes" / commit
    _refuse_live_folder(mmx_root, target)
    content = runtime_document if isinstance(runtime_document, bytes) else json_bytes(runtime_document)
    write_owned(target / "server.js", server_bytes, 0o600)
    write_owned(target / "runtime.json", content, 0o600)
    return target


def deliver(mmx_root, commit, runtime_document, server_bytes):
    """Write ``runtimes/<commit>/{runtime.json,server.js}`` exactly once.

    An existing delivery is permanent (ruling 19): it is refused, never
    overwritten — a delivered folder may be the one running servers loaded.
    The check and both writes happen under the cross-process delivery lock.
    """
    _check_commit(commit)
    with _DeliveryLock(mmx_root):
        return _deliver_locked(mmx_root, commit, runtime_document, server_bytes)


def _repoint_current(mmx, target):
    """Atomic symlink replace: running servers keep their resolved files."""
    current = mmx / "current"
    temporary = mmx / "current.tmp"
    if temporary.is_symlink() or temporary.exists():
        temporary.unlink()
    temporary.symlink_to(target, target_is_directory=True)
    os.replace(temporary, current)
    return current


def switch(mmx_root, commit):
    """Repoint ``$MMX/current`` at a delivered versioned pin.

    Running servers keep their already-resolved files; only the next spawn
    sees the new pin. The rollback is the same call with the old commit.
    """
    _check_commit(commit)
    mmx = Path(mmx_root).expanduser()
    target = mmx / "runtimes" / commit
    if not (target / "runtime.json").is_file() or not (target / "server.js").is_file():
        raise RuntimeError("pin switch refused: " + str(target) + " is not a delivered runtime pin "
                           "(runtime.json and server.js required)")
    current = mmx / "current"
    if current.exists() and not current.is_symlink():
        raise RuntimeError("pin switch refused: " + str(current) + " exists and is not a symlink — reconcile it manually")
    previous = os.readlink(current) if current.is_symlink() else None
    _repoint_current(mmx, target)
    return {"state": "PIN_SWITCHED", "mmx_root": str(mmx), "current": str(current),
            "target": str(target), "previous": previous}


def migrate(mmx_root, old_commit, new_commit, build_manifest, new_source_root=None):
    """One-time migration to versioned runtimes; ``current`` ends on OLD.

    Delivers ``runtimes/<OLD>`` from the verbatim flat pin, ``runtimes/<NEW>``
    from the flat pin updated to the new release (commit, source root and the
    closure hashes the build manifest pins), then points ``current`` at OLD —
    zero behavior change; the switch is a separate explicit act. The flat pin
    files are never edited, so running servers are untouched throughout.
    """
    _check_commit(old_commit)
    _check_commit(new_commit)
    if old_commit == new_commit:
        raise RuntimeError("pin migration refused: old and new commits are identical")
    mmx = Path(mmx_root).expanduser()
    flat_pin = mmx / "runtime.json"
    flat_server = mmx / "server.js"
    if not flat_pin.is_file() or not flat_server.is_file():
        raise RuntimeError("pin migration refused: " + str(mmx) + " has no flat runtime.json/server.js to migrate")
    current = mmx / "current"
    if current.is_symlink() or current.exists():
        raise RuntimeError("pin migration refused: " + str(current) + " already exists — the migration is one-time; "
                           "use the switch command")
    try:
        document = json.loads(read_owned(flat_pin))
    except (OSError, ValueError, RuntimeError) as error:
        raise RuntimeError("flat runtime pin is unreadable; refusing to migrate it: " + str(flat_pin)) from error
    if not isinstance(document, dict) or document.get("schema") != RUNTIME_SCHEMA:
        raise RuntimeError("flat runtime pin is not a " + RUNTIME_SCHEMA + " document: " + str(flat_pin))
    if document.get("release_commit") != old_commit:
        raise RuntimeError("flat pin is not the old release " + old_commit + ": " + str(flat_pin))
    source_root = document.get("source_root")
    if not isinstance(source_root, str) or not source_root:
        raise RuntimeError("flat pin names no source_root: " + str(flat_pin))
    releases_parent = Path(source_root).parent
    if new_source_root is not None:
        new_root = Path(new_source_root).expanduser()
    elif Path(source_root).resolve() == (releases_parent / old_commit).resolve():
        new_root = releases_parent / new_commit
    else:
        raise RuntimeError("flat pin source_root does not sit at <releases>/" + old_commit
                           + "; pass the new source root explicitly: " + source_root)
    try:
        manifest = json.loads(read_owned(build_manifest))
    except (OSError, ValueError, RuntimeError) as error:
        raise RuntimeError("build manifest is unreadable: " + str(build_manifest)) from error
    if (not isinstance(manifest, dict) or manifest.get("schema") != BUILD_SCHEMA
            or manifest.get("source_commit") != new_commit or not isinstance(manifest.get("files"), dict)):
        raise RuntimeError("build manifest does not name the new commit " + new_commit + ": " + str(build_manifest))
    # Plan 48 (BR-MICRO2 item 1): an apply that can refuse does so before its
    # first write — both versioned targets are fully checked (not delivered,
    # not the live folder; the manifest was validated above) before
    # runtimes/<OLD> is created, so a refusal leaves the whole tree unchanged
    # instead of half-migrated. The checks and both deliveries share ONE
    # delivery lock, so no other process can deliver between the check and
    # the writes (ruling 19 fold-in).
    with _DeliveryLock(mmx_root):
        for commit in (old_commit, new_commit):
            _refuse_delivered(mmx_root, commit, "pin migration refused")
            _refuse_live_folder(mmx_root, mmx / "runtimes" / commit)
        server_bytes = read_owned(flat_server)
        # runtimes/<OLD>: the verbatim live pin — the exact rollback target.
        _deliver_locked(mmx_root, old_commit, document, server_bytes)
        # runtimes/<NEW>: the flat pin moved to the new release; only the hashes
        # the manifest actually pins are updated, everything else is preserved.
        updated = dict(document)
        updated["release_commit"] = new_commit
        updated["source_root"] = str(new_root)
        files = manifest["files"]
        if isinstance(updated.get("source_files"), dict):
            updated["source_files"] = {name: files[name] if name in files else sha
                                       for name, sha in updated["source_files"].items()}
        _deliver_locked(mmx_root, new_commit, updated, server_bytes)
        target = mmx / "runtimes" / old_commit
        _repoint_current(mmx, target)
    return {"state": "PIN_MIGRATED", "mmx_root": str(mmx), "current": str(current),
            "old": str(target), "new": str(mmx / "runtimes" / new_commit),
            "flat_pin_sha256": digest(read_owned(flat_pin)),
            "behavior_change": "none — current points at the old release until an explicit switch"}


def main():
    parser = argparse.ArgumentParser(description="Guarded mmx-browser versioned runtime pin writer.")
    commands = parser.add_subparsers(dest="command", required=True)
    migrate_parser = commands.add_parser("migrate",
        help="one-time migration to versioned runtimes; current ends on the old commit (no behavior change)")
    migrate_parser.add_argument("--mmx-root", type=Path, required=True,
        help="the mmx-browser pin folder (no default: a default target that is a folder a running program has loaded is refused)")
    migrate_parser.add_argument("--old-commit", required=True, help="the flat pin's current release commit")
    migrate_parser.add_argument("--new-commit", required=True, help="the release being installed")
    migrate_parser.add_argument("--build-manifest", type=Path, required=True,
        help="the new release's BUILD.json (must name the new commit)")
    migrate_parser.add_argument("--new-source-root", type=Path,
        help="explicit new release source root (default: the flat pin's <releases> parent plus the new commit)")
    switch_parser = commands.add_parser("switch",
        help="atomically repoint current at a delivered versioned pin; the rollback is the same call with the old commit")
    switch_parser.add_argument("--mmx-root", type=Path, required=True,
        help="the mmx-browser pin folder (no default)")
    switch_parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if args.command == "migrate":
        result = migrate(args.mmx_root, args.old_commit, args.new_commit, args.build_manifest,
                         new_source_root=args.new_source_root)
    else:
        result = switch(args.mmx_root, args.commit)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

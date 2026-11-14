#!/usr/bin/env python3
"""Archive-snapshot / plan / execute rollback + install tool for the
installed Mastermind OS desktop app (``Mastermind OS.app``).

Dry-run is the DEFAULT. ``plan`` and a bare ``execute``/``install`` only
print the exact steps; mutations happen solely under ``execute --to
<receipt-or-dir> --execute`` or ``install --from <built .app> --execute``.
The tool never kills, quits or launches the app: quitting the running
application is printed as a HUMAN step and a live app running from the
current bundle refuses the mutation. The previous bundle is always preserved
(moved, never deleted) under ``<archive-root>/rollback-tmp-<ts>`` (execute)
or ``<archive-root>/install-tmp-<ts>`` (install).

``install --from`` places a freshly built ``.app`` at the install location:
it snapshots the current bundle first (same idempotent ``snapshot``), then
moves the current bundle aside and copies the source in, requiring the
re-observed install receipt digest to equal the source bundle's digest. The
source is a build product, NOT an archive entry, so it is not subject to the
``--archive-root`` containment rule — but it must be an existing ``.app``
that is neither the install target itself nor nested inside it (or vice
versa).

Archive layout (created by ``snapshot``)::

    <archive-root>/<build_identity>-<source_revision[:12]>/
        Mastermind OS.app/          # bit copy of the installed bundle
        receipt.json                # mastermind.installed_receipt/v1
        receipt.digest              # one line: sha256:<hex>

``snapshot`` is idempotent: an identical receipt digest does not copy again.
``plan``/``execute`` verify the archived bundle still matches its stored
receipt digest before anything moves, and refuse ``--to`` targets that
resolve outside ``--archive-root`` (path traversal).

Exit codes:
    0 success (snapshot done/already archived, plan printed, execute/install
      verified)
    1 operational error (missing bundle/archive, ambiguous archive)
    2 malformed arguments (including install --from that is not an existing
      .app, or is/nests the install target)
    3 execute/install refused: --execute not provided (dry-run only)
    4 execute/install refused: running app is (or may be) from the current
      bundle
    5 execute/plan refused: archive receipt digest verification failed
    6 refused: --to target resolves outside --archive-root
    7 executed but the re-observed install does not match (kept old bundle)
    8 EFFECT_UNKNOWN: move/copy failed midway and rollback of the move failed
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.mmos_installed_receipt import (  # noqa: E402
    SCHEMA as RECEIPT_SCHEMA,
    observe_bundle,
)

DEFAULT_BUNDLE = "/Applications/Mastermind OS.app"
DEFAULT_ARCHIVE_ROOT = "~/.mastermind/mmos_bundles/"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ARGS = 2
EXIT_REFUSED_DRY_RUN = 3
EXIT_REFUSED_RUNNING = 4
EXIT_VERIFY_FAILED = 5
EXIT_REFUSED_TARGET = 6
EXIT_INSTALLED_MISMATCH = 7
EXIT_EFFECT_UNKNOWN = 8


class TargetRefused(Exception):
    """--to target resolves outside the archive root (path traversal)."""


class VerifyFailed(Exception):
    """Archived bundle does not match its stored receipt digest."""


@dataclass
class ArchiveTarget:
    archive_dir: Path
    receipt: dict
    bundle_dir: Path

    @property
    def digest(self) -> str:
        return str(self.receipt["receipt_digest"])


def _utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sanitize(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    return cleaned[:120] or "unknown"


# ---------------------------------------------------------------------------
# target resolution / verification
# ---------------------------------------------------------------------------

def resolve_archive_target(to_raw: str, archive_root: Path) -> ArchiveTarget:
    """Resolve --to (receipt file or archive dir) and enforce containment."""
    archive_real = os.path.realpath(archive_root)
    to_path = Path(to_raw).expanduser()
    receipt_file = to_path if to_path.name.endswith(".json") else to_path / "receipt.json"
    dir_real = os.path.realpath(receipt_file.parent)
    inside = dir_real == archive_real or dir_real.startswith(archive_real + os.sep)
    if not inside:
        raise TargetRefused(
            f"--to {to_raw!r} resolves to {dir_real!r}, outside archive root {archive_real!r}"
        )
    if not receipt_file.is_file():
        raise FileNotFoundError(f"archive receipt not found: {receipt_file}")
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    if receipt.get("schema") != RECEIPT_SCHEMA or "receipt_digest" not in receipt:
        raise VerifyFailed(f"archive receipt is not a {RECEIPT_SCHEMA} document: {receipt_file}")
    apps = sorted(p for p in Path(dir_real).iterdir() if p.suffix == ".app") \
        if Path(dir_real).is_dir() else []
    bundle_dir = None
    for app in apps:
        if app.name == "Mastermind OS.app":
            bundle_dir = app
            break
    if bundle_dir is None and len(apps) == 1:
        bundle_dir = apps[0]
    if bundle_dir is None:
        raise FileNotFoundError(
            f"archive directory does not contain exactly one .app bundle: {dir_real}"
        )
    return ArchiveTarget(archive_dir=Path(dir_real), receipt=receipt, bundle_dir=bundle_dir)


def verify_archive(target: ArchiveTarget) -> dict:
    """Re-observe the archived bundle; its digest must equal the stored one."""
    fresh = observe_bundle(target.bundle_dir)
    if not fresh["bundle_exists"]:
        raise VerifyFailed(f"archived bundle is missing: {target.bundle_dir}")
    if fresh["receipt_digest"] != target.digest:
        raise VerifyFailed(
            "archived bundle no longer matches its stored receipt digest "
            f"(stored={target.digest}, observed={fresh['receipt_digest']}) — "
            "the archive is tampered or corrupt; refusing."
        )
    return fresh


# ---------------------------------------------------------------------------
# plan rendering
# ---------------------------------------------------------------------------

def render_plan(
    *,
    current_path: Path,
    current_digest: str,
    target: ArchiveTarget,
    archive_root: Path,
) -> str:
    revision = target.receipt["source_revision"]["value"]
    identity = target.receipt["build_identity"]["value"]
    install_parent = current_path.parent
    tmp_dir = archive_root / f"rollback-tmp-<{_utc_stamp()}>"
    steps = [
        "ROLLBACK PLAN — dry-run; NOTHING has been changed.",
        f"  Current bundle : {current_path}",
        f"    receipt digest: {current_digest}",
        f"  Target archive : {target.archive_dir}",
        f"    source_revision={revision}  build_identity={identity}",
        f"    stored digest : {target.digest}",
        "  0. HUMAN STEP (this tool never automates it): quit the running "
        "Mastermind OS app (Mastermind OS menu → Quit Mastermind OS, or Cmd-Q).",
        "  1. Verify the archive: re-observe the archived bundle and require "
        f"digest == {target.digest}. [plan check: PASS]",
        f"  2. Move the current bundle {current_path} → {tmp_dir / current_path.name} "
        "(reversible move; nothing is deleted).",
        f"  3. Copy the archived bundle {target.bundle_dir} → {install_parent}.",
        f"  4. Re-run scripts/mmos_installed_receipt.py --bundle {current_path} "
        f"and require digest == {target.digest}.",
        "  5. HUMAN STEP: relaunch Mastermind OS and confirm the Build details "
        "panel (Source revision / Build identity) equals the receipt, plus one "
        "real user-path action.",
    ]
    return "\n".join(steps)


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------

def cmd_snapshot(bundle: Path, archive_root: Path) -> int:
    receipt = observe_bundle(bundle)
    if not receipt["bundle_exists"]:
        print(f"mmos_rollback.py: bundle not found: {bundle}", file=sys.stderr)
        return EXIT_ERROR
    digest = receipt["receipt_digest"]
    revision = (receipt["source_revision"]["value"] or "")[:12] or "unknown"
    identity = _sanitize(receipt["build_identity"]["value"] or "unknown")
    name = f"{identity}-{revision}"
    dest = archive_root / name
    if dest.exists():
        stored = _read_digest(dest)
        if stored == digest:
            print(f"already archived (identical receipt digest {digest}): {dest}")
            return EXIT_OK
        dest = archive_root / f"{name}--{digest.removeprefix('sha256:')[:8]}"
    archive_root.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp-{os.getpid()}-{_utc_stamp()}")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(bundle, tmp / bundle.name, symlinks=True)
    (tmp / "receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    (tmp / "receipt.digest").write_text(digest + "\n", encoding="utf-8")
    os.rename(tmp, dest)
    print(f"archived {bundle} -> {dest}")
    print(f"receipt digest: {digest}")
    return EXIT_OK


def _read_digest(dest: Path) -> str | None:
    try:
        return (dest / "receipt.digest").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _current_receipt(bundle: Path) -> dict | None:
    receipt = observe_bundle(bundle)
    if not receipt["bundle_exists"]:
        print(
            f"mmos_rollback.py: current bundle not found: {bundle} — nothing to roll back.",
            file=sys.stderr,
        )
        return None
    return receipt


def _refuse_running(receipt: dict) -> bool:
    running = receipt.get("running_app", {})
    state = running.get("from_this_bundle")
    if state is True:
        print(
            "EXECUTE REFUSED: a live process was observed running from the current "
            f"bundle (pids {running.get('pids')}). HUMAN STEP: quit the Mastermind OS "
            "app (Cmd-Q or Mastermind OS menu → Quit), then re-run. This tool never "
            "kills or quits it.",
        )
        return True
    if state is None:
        print(
            "EXECUTE REFUSED: whether the app is running from the current bundle is "
            f"unknown ({running.get('detail')}). HUMAN STEP: make sure the app is quit "
            "(Cmd-Q), then re-run while detection is unambiguous.",
        )
        return True
    return False


def _prepare(bundle: Path, archive_root: Path, to_raw: str) -> tuple[ArchiveTarget, dict] | int:
    """Shared plan/execute prelude: resolve --to, observe current, verify archive."""
    try:
        target = resolve_archive_target(to_raw, archive_root)
    except TargetRefused as error:
        print(f"mmos_rollback.py: refused: {error}", file=sys.stderr)
        return EXIT_REFUSED_TARGET
    except FileNotFoundError as error:
        print(f"mmos_rollback.py: {error}", file=sys.stderr)
        return EXIT_ERROR
    except (VerifyFailed, json.JSONDecodeError) as error:
        print(f"mmos_rollback.py: {error}", file=sys.stderr)
        return EXIT_VERIFY_FAILED
    current = _current_receipt(bundle)
    if current is None:
        return EXIT_ERROR
    try:
        verify_archive(target)
    except VerifyFailed as error:
        print(f"mmos_rollback.py: {error}", file=sys.stderr)
        return EXIT_VERIFY_FAILED
    return target, current


def cmd_plan(bundle: Path, archive_root: Path, to_raw: str) -> int:
    prepared = _prepare(bundle, archive_root, to_raw)
    if isinstance(prepared, int):
        return prepared
    target, current = prepared
    print(render_plan(
        current_path=Path(current["bundle_path"]),
        current_digest=current["receipt_digest"],
        target=target,
        archive_root=archive_root,
    ))
    return EXIT_OK


def cmd_execute(bundle: Path, archive_root: Path, to_raw: str, execute: bool) -> int:
    prepared = _prepare(bundle, archive_root, to_raw)
    if isinstance(prepared, int):
        return prepared
    target, current = prepared
    plan = render_plan(
        current_path=Path(current["bundle_path"]),
        current_digest=current["receipt_digest"],
        target=target,
        archive_root=archive_root,
    )
    if not execute:
        print(plan)
        print()
        print(
            "EXECUTE REFUSED: --execute was not provided; this was a dry-run. "
            "Re-run with --execute to apply the plan above."
        )
        return EXIT_REFUSED_DRY_RUN
    if _refuse_running(current):
        return EXIT_REFUSED_RUNNING

    tmp_dir = archive_root / f"rollback-tmp-{_utc_stamp()}"
    tmp_dir.mkdir(parents=True, exist_ok=False)
    moved_current = tmp_dir / bundle.name
    try:
        os.rename(bundle, moved_current)
    except OSError:
        shutil.move(str(bundle), str(moved_current))
    try:
        shutil.copytree(target.bundle_dir, bundle, symlinks=True)
    except OSError as error:
        print(f"mmos_rollback.py: copying archived bundle failed: {error}", file=sys.stderr)
        try:
            os.rename(moved_current, bundle)
        except OSError as restore_error:
            print(
                "EFFECT_UNKNOWN: restore of the moved current bundle failed "
                f"({restore_error}); the previous bundle is preserved at "
                f"{moved_current} and nothing was installed. Reconcile manually.",
                file=sys.stderr,
            )
            return EXIT_EFFECT_UNKNOWN
        print(
            "mmos_rollback.py: no changes applied; the current bundle was restored "
            "in place.",
            file=sys.stderr,
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return EXIT_ERROR

    fresh = observe_bundle(bundle)
    print(f"previous bundle preserved at: {moved_current}")
    if fresh["receipt_digest"] == target.digest:
        print(f"installed bundle {bundle} now matches archived digest {target.digest}")
        print(
            "remaining HUMAN steps: relaunch Mastermind OS, confirm the Build details "
            "panel (Source revision / Build identity) equals the receipt, and perform "
            "one real user-path action."
        )
        return EXIT_OK
    print(
        "EXECUTED BUT MISMATCH: the re-observed install digest "
        f"{fresh['receipt_digest']} != archived {target.digest}. The previous bundle "
        f"is preserved at {moved_current}.",
        file=sys.stderr,
    )
    return EXIT_INSTALLED_MISMATCH


# ---------------------------------------------------------------------------
# install (place a freshly built .app at the install location)
# ---------------------------------------------------------------------------

def _refuse_self_install(bundle: Path, source: Path) -> bool:
    """Refuse --from that is (or nests with) the install target itself."""
    bundle_real = os.path.realpath(bundle)
    source_real = os.path.realpath(source)
    nested = (
        source_real == bundle_real
        or source_real.startswith(bundle_real + os.sep)
        or bundle_real.startswith(source_real + os.sep)
    )
    if nested:
        print(
            "mmos_rollback.py: refused: --from must be a separate bundle, not the "
            f"install target itself or nested with it ({source_real} vs {bundle_real})",
            file=sys.stderr,
        )
        return True
    return False


def render_install_plan(
    *,
    install_path: Path,
    current: dict | None,
    source: dict,
    archive_root: Path,
) -> str:
    revision = source["source_revision"]["value"]
    identity = source["build_identity"]["value"]
    tmp_dir = archive_root / f"install-tmp-<{_utc_stamp()}>"
    steps = [
        "INSTALL PLAN — dry-run; NOTHING has been changed.",
        f"  Install target : {install_path}",
    ]
    if current is not None:
        steps += [
            f"    current digest: {current['receipt_digest']}",
            "    current source_revision="
            f"{current['source_revision']['value']}  build_identity="
            f"{current['build_identity']['value']}",
        ]
    else:
        steps.append("    no bundle is currently installed at this path (fresh install)")
    steps += [
        f"  Source bundle  : {source['bundle_path']}",
        f"    source_revision={revision}  build_identity={identity}",
        f"    source digest : {source['receipt_digest']}",
        "  0. HUMAN STEP (this tool never automates it): quit the running "
        "Mastermind OS app (Mastermind OS menu → Quit Mastermind OS, or Cmd-Q).",
    ]
    if current is not None:
        steps += [
            "  1. Snapshot the current bundle into the archive (idempotent by "
            "receipt digest) so the rollback anchor exists before anything moves.",
            f"  2. Move the current bundle {install_path} → {tmp_dir / install_path.name} "
            "(reversible move; nothing is deleted).",
        ]
    else:
        steps.append("  1-2. No current bundle to snapshot or move aside.")
    steps += [
        f"  3. Copy the source bundle {source['bundle_path']} → {install_path}.",
        f"  4. Re-run scripts/mmos_installed_receipt.py --bundle {install_path} "
        f"and require digest == {source['receipt_digest']}.",
        "  5. HUMAN STEP: relaunch Mastermind OS and confirm the Build details "
        "panel (Source revision / Build identity) equals the receipt, plus one "
        "real user-path action.",
    ]
    return "\n".join(steps)


def cmd_install(bundle: Path, archive_root: Path, from_raw: str, execute: bool) -> int:
    source_path = Path(from_raw).expanduser()
    if source_path.suffix != ".app" or not source_path.is_dir():
        print(
            f"mmos_rollback.py: --from must be an existing .app bundle: {source_path}",
            file=sys.stderr,
        )
        return EXIT_ARGS
    if _refuse_self_install(bundle, source_path):
        return EXIT_ARGS
    source = observe_bundle(source_path)
    if not source["bundle_exists"]:
        print(f"mmos_rollback.py: source bundle not found: {source_path}", file=sys.stderr)
        return EXIT_ERROR
    current = observe_bundle(bundle)
    has_current = current["bundle_exists"]
    plan = render_install_plan(
        install_path=bundle,
        current=current if has_current else None,
        source=source,
        archive_root=archive_root,
    )
    if not execute:
        print(plan)
        print()
        print(
            "INSTALL REFUSED: --execute was not provided; this was a dry-run. "
            "Re-run with --execute to apply the plan above."
        )
        return EXIT_REFUSED_DRY_RUN
    if has_current:
        if _refuse_running(current):
            return EXIT_REFUSED_RUNNING
        rc = cmd_snapshot(bundle, archive_root)
        if rc != EXIT_OK:
            return rc
    else:
        print(
            "note: no bundle currently installed at the target; "
            "skipping snapshot and move-aside."
        )

    tmp_dir = archive_root / f"install-tmp-{_utc_stamp()}"
    moved_current = None
    if has_current:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        moved_current = tmp_dir / bundle.name
        try:
            os.rename(bundle, moved_current)
        except OSError:
            shutil.move(str(bundle), str(moved_current))
    try:
        shutil.copytree(source_path, bundle, symlinks=True)
    except OSError as error:
        print(f"mmos_rollback.py: copying source bundle failed: {error}", file=sys.stderr)
        shutil.rmtree(bundle, ignore_errors=True)  # remove any partial copy we created
        if has_current:
            try:
                os.rename(moved_current, bundle)
            except OSError as restore_error:
                print(
                    "EFFECT_UNKNOWN: restore of the moved current bundle failed "
                    f"({restore_error}); the previous bundle is preserved at "
                    f"{moved_current} and nothing was installed. Reconcile manually.",
                    file=sys.stderr,
                )
                return EXIT_EFFECT_UNKNOWN
            print(
                "mmos_rollback.py: no changes applied; the current bundle was restored "
                "in place.",
                file=sys.stderr,
            )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return EXIT_ERROR

    fresh = observe_bundle(bundle)
    if has_current:
        print(f"previous bundle preserved at: {moved_current}")
    if fresh["receipt_digest"] == source["receipt_digest"]:
        print(f"installed bundle {bundle} matches source digest {source['receipt_digest']}")
        print(
            "remaining HUMAN steps: relaunch Mastermind OS, confirm the Build details "
            "panel (Source revision / Build identity) equals the receipt, and perform "
            "one real user-path action."
        )
        return EXIT_OK
    mismatch = (
        f"EXECUTED BUT MISMATCH: the re-observed install digest "
        f"{fresh['receipt_digest']} != source {source['receipt_digest']}."
    )
    if has_current:
        mismatch += f" The previous bundle is preserved at {moved_current}."
    print(mismatch, file=sys.stderr)
    return EXIT_INSTALLED_MISMATCH


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmos_rollback.py",
        description="Installed Mastermind OS bundle archive/rollback tool. "
                    "Dry-run by default; --execute is required for any mutation.",
    )
    parser.add_argument("--bundle", default=DEFAULT_BUNDLE,
                        help=f"installed bundle (default: {DEFAULT_BUNDLE})")
    parser.add_argument("--archive-root", default=DEFAULT_ARCHIVE_ROOT,
                        help=f"bundle archive root (default: {DEFAULT_ARCHIVE_ROOT})")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="copy the current bundle + receipt into the archive "
                                    "(idempotent by receipt digest)")
    plan = sub.add_parser("plan", help="print the exact rollback steps (no changes)")
    plan.add_argument("--to", required=True,
                      help="archive directory (or its receipt.json) to roll back to")
    execute = sub.add_parser("execute", help="perform the rollback (dry-run without --execute)")
    execute.add_argument("--to", required=True,
                         help="archive directory (or its receipt.json) to roll back to")
    execute.add_argument("--execute", action="store_true",
                         help="actually apply the plan (required for any mutation)")
    install = sub.add_parser("install", help="install a freshly built .app at --bundle "
                                             "(dry-run without --execute)")
    install.add_argument("--from", required=True, dest="from_dir", metavar="BUILT_APP",
                         help="source .app bundle from a build (not an archive entry)")
    install.add_argument("--execute", action="store_true",
                         help="actually apply the install (required for any mutation)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.bundle or not args.bundle.strip():
        print("mmos_rollback.py: --bundle must be a non-empty path", file=sys.stderr)
        return EXIT_ARGS
    bundle = Path(args.bundle).expanduser()
    archive_root = Path(args.archive_root).expanduser()
    if args.command == "snapshot":
        return cmd_snapshot(bundle, archive_root)
    if args.command == "plan":
        return cmd_plan(bundle, archive_root, args.to)
    if args.command == "execute":
        return cmd_execute(bundle, archive_root, args.to, args.execute)
    if args.command == "install":
        return cmd_install(bundle, archive_root, args.from_dir, args.execute)
    print(f"mmos_rollback.py: unknown command {args.command!r}", file=sys.stderr)
    return EXIT_ARGS


if __name__ == "__main__":
    sys.exit(main())

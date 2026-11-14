"""FTR-2: reversible, secret-safe install of the launchd policy trio.

For each of the five seats, and only after identity re-verification against
the operator-qualified private manifest:

1. Capture a secure PREIMAGE backup (private dir, 0600) with a sidecar
   recording pre/post digests, mode, and plan pins.
2. Apply exactly three policy keys (RunAtLoad=true, unconditional
   KeepAlive=true, ThrottleInterval>=10), preserving every other key and the
   original file mode.
3. Write atomically (parse-back + same-directory rename + fsync), then reload
   through launchd owner actions only (bootout when loaded, bootstrap back).
4. On bootstrap failure: roll the preimage back atomically, bootstrap the
   restored file, and emit an alert. A seat is never left mutated without its
   job loaded unless even the rollback failed, which is a hard alert.

The batch is transactional (B5): mutations are fully derived before the
first write, and a failure on any seat rolls every previously installed seat
back through its validated preimage CAS, so no earlier seat stays altered
because a later one failed.

Deliberate stop semantics live here too: because KeepAlive is unconditional,
a plain SIGTERM (or any exit, including exit 0) is followed by a launchd
restart. The ONLY sanctioned deliberate stop is
``launchctl bootout gui/<uid>/<label>``; restore with
``launchctl bootstrap gui/<uid> <plist>``. The runbook documents this; no
code path here stops a job except the reload step, which immediately
bootstraps the mutated plist back.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from fabric_tunnel_common import (
    IdentityRejected,
    PLAN_COMMIT,
    PolicyRefused,
    TUNNEL_LABELS,
    ActionRefused,
    Alert,
    atomic_write_bytes,
    backups_dir,
    evidence_line,
    parse_plist_bytes,
    plist_relpath,
    require_parent_safe,
    serialize_plist,
    sha256_bytes,
    subprocess_runner,
)
from fabric_tunnel_identity import (
    assert_current_bytes_match_manifest,
    load_manifest,
    policy_changes,
    scan_family,
    seat_identity_drift_problems,
)

Runner = Any  # Runner protocol from fabric_tunnel_common; tests inject fakes
_BOOTSTRAP_NOT_LOADED_CODES = {37, 36, 5}  # ESRCH/ENOENT-style "not loaded" variants
# Rollback default for a plist whose backup sidecar predates the recorded
# mode: the qualified operator plist mode, matching install-time artifacts.
PLIST_DEFAULT_FILE_MODE = 0o644


@dataclass
class InstallResult:
    label: str
    status: str  # "installed" | "already_compliant" | "rolled_back" | "failed" |
    # "batch_rolled_back" | "batch_rollback_failed" | "not_attempted"
    changes: dict[str, Any] = field(default_factory=dict)
    backup_sidecar: str = ""
    alerts: list[Alert] = field(default_factory=list)

    def as_evidence(self) -> str:
        return evidence_line(
            self.label,
            {
                "status": self.status,
                "changes": sorted(self.changes),
                "backup_sidecar": self.backup_sidecar,
                "alerts": [alert.code for alert in self.alerts],
            },
        )


@dataclass(frozen=True)
class _SeatPlan:
    """A fully derived, not-yet-applied policy-trio mutation for one seat.

    Deriving ALL plans before ANY write means a derivation refusal can never
    leave part of the batch mutated (B5). ``expected_pre_sha256`` /
    ``expected_pre_mode`` are the EXACT qualified predecessor from the
    manifest; ``_execute_plan`` re-asserts them immediately before the
    mutation so a concurrent external writer that landed after the batch
    preflight can never be overwritten (single mutation owner via CAS on the
    qualified bytes — no second lifecycle or lock plane)."""
    label: str
    changes: dict[str, Any]
    post_raw: bytes
    pre_mode: int
    seat_uid: int
    plist_path: Path
    expected_pre_sha256: str
    expected_pre_mode: int


# ---------------------------------------------------------------------------
# Secure preimage backups.
# ---------------------------------------------------------------------------


def _write_backup(home: Path, label: str, pre_raw: bytes, post_raw: bytes, mode: int, now: float) -> Path:
    directory = backups_dir(home) / label
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    stem = f"{int(now)}-{sha256_bytes(pre_raw)[:12]}"
    plist_backup = directory / f"{stem}.plist"
    sidecar = directory / f"{stem}.json"
    payload = {
        "schema": "mastermind.subagent-fabric-tunnels.preimage-backup.v1",
        "label": label,
        "plan_commit": PLAN_COMMIT,
        "plist_relpath": plist_relpath(label),
        "pre_sha256": sha256_bytes(pre_raw),
        "post_sha256": sha256_bytes(post_raw),
        "mode": mode & 0o7777,
        "created_at": now,
        "private": "never commit, never log contents",
    }
    atomic_write_bytes(plist_backup, pre_raw, 0o600)
    os.chmod(plist_backup, 0o600)
    atomic_write_bytes(
        sidecar, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"), 0o600
    )
    os.chmod(sidecar, 0o600)
    return sidecar


def _load_backup(home: Path, label: str) -> tuple[Path, dict[str, Any]] | None:
    directory = backups_dir(home) / label
    if not directory.is_dir():
        return None
    sidecars = sorted(directory.glob("*.json"))
    if not sidecars:
        return None
    newest = sidecars[-1]
    try:
        payload = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyRefused(f"{label}_backup_sidecar_unreadable ({exc.__class__.__name__})") from exc
    return newest, payload


# ---------------------------------------------------------------------------
# launchd reload with rollback.
# ---------------------------------------------------------------------------


def _bootout_if_loaded(runner: Any, uid: int, label: str) -> bool:
    from fabric_tunnel_common import launchctl_bootout_argv as argv_builder

    result = runner(argv_builder(uid, label))
    if result.returncode == 0:
        return True
    # launchd reports various codes for "job not loaded"; treat them as
    # already-stopped rather than a failure. Anything else surfaces.
    if result.returncode in _BOOTSTRAP_NOT_LOADED_CODES or "not loaded" in (result.stderr or ""):
        return False
    raise ActionRefused(f"{label}_bootout_failed rc={result.returncode}")


def _bootstrap(runner: Any, uid: int, plist_path: Path) -> None:
    from fabric_tunnel_common import launchctl_bootstrap_argv as argv_builder

    result = runner(argv_builder(uid, plist_path))
    if result.returncode != 0:
        raise ActionRefused(f"bootstrap_failed rc={result.returncode} label={plist_path.stem}")


# ---------------------------------------------------------------------------
# Install / verify / rollback.
# ---------------------------------------------------------------------------


def install_seats(
    home: Path,
    runner: Any,
    *,
    confirm: bool,
    now: float,
    uid: int | None = None,
    reload_jobs: bool = True,
) -> list[InstallResult]:
    """Extend the five plists with the FTR-2 policy trio, reversibly.

    Refuses (no mutation at all) when: no ``--confirm``, manifest missing or
    stale, any rogue family label exists, ANY seat drifted since
    qualification, or any seat fails identity re-verification.

    The batch is TRANSACTIONAL (B5): every mutation is fully derived before
    anything is written; if a later seat fails, every previously installed
    seat is rolled back through its validated preimage CAS and re-bootstrapped,
    and unattempted seats are reported ``not_attempted``. The operation only
    reports success when the batch ends entirely installed or entirely
    already-compliant; partial states are never silent.
    """
    if not confirm:
        raise PolicyRefused("install_requires_explicit_confirmation")
    home = Path(home)
    try:
        manifest = load_manifest(home, now=now)
    except IdentityRejected as rejected:
        raise PolicyRefused(f"manifest_unqualified ({rejected})") from rejected
    rogue = scan_family(home)
    if rogue:
        raise PolicyRefused(f"rogue_family_labels_present: {','.join(rogue)}")

    # Whole-batch preflight: refuse before touching anything if any seat
    # cannot be re-verified. Mutation is all-or-nothing per run.
    working: dict[str, dict[str, Any]] = {}
    for label in sorted(TUNNEL_LABELS):
        entry = manifest["seats"][label]
        seat_uid = int(entry["uid"]) if uid is None else uid
        working[label] = assert_current_bytes_match_manifest(home, manifest, label)
        if int(entry["uid"]) != seat_uid:
            raise PolicyRefused(f"{label}_uid_mismatch")
        # Bind directory identity across the upcoming writes: the LEXICAL
        # ancestor chain of the plist must still be symlink-free at install
        # time, not just at qualification time.
        try:
            require_parent_safe(
                home / entry["plist_relpath"], seat_uid, code=f"{label}_install_parent_unsafe"
            )
        except IdentityRejected as rejected:
            raise PolicyRefused(str(rejected)) from rejected
        # Pre-effect identity re-proof (every install effect, not merely the
        # attestation day boundary): the whole installed identity — argv,
        # executable path/digest/inode/owner/mode, parent and Cellar-allowance
        # pins, and any pinned poll-profile binding — must still match the
        # qualified manifest before ANY mutation or launchd reload.
        drift = seat_identity_drift_problems(home, manifest, label)
        if drift:
            raise PolicyRefused(f"{label}_install_identity_drift:{','.join(drift)}")

    # Derivation phase: build every plan before the first write.
    labels = sorted(TUNNEL_LABELS)
    plans: list[_SeatPlan | None] = []
    for label in labels:
        plans.append(_plan_one(manifest, working[label], label, home=home))

    results: dict[str, InstallResult] = {}
    completed: list[tuple[_SeatPlan, str]] = []
    batch_failed = False
    for label, plan in zip(labels, plans):
        if plan is None:
            results[label] = InstallResult(label=label, status="already_compliant")
            continue
        if batch_failed:
            results[label] = InstallResult(label=label, status="not_attempted")
            continue
        result = _execute_plan(home, runner, plan, now=now, reload_jobs=reload_jobs)
        results[label] = result
        if result.status == "installed":
            completed.append((plan, result.backup_sidecar))
        else:
            batch_failed = True

    if batch_failed and completed:
        # Roll every previously successful seat back to its exact qualified
        # preimage (validated against this run's post digest) so no earlier
        # seat stays altered because a later one failed. Completed seats are
        # LOADED with the new plist, so the restore must use the
        # bootout-then-bootstrap path (reload_only) — a bare bootstrap of an
        # already-bootstrapped job would fail with EEXIST on real launchd.
        for plan, _sidecar in completed:
            alert = _rollback_preimage(
                home,
                runner,
                plan.label,
                expected_post=sha256_bytes(plan.post_raw),
                now=now,
                reload_only=reload_jobs,
                reload=reload_jobs,
            )
            if alert is None:
                results[plan.label] = InstallResult(
                    label=plan.label,
                    status="batch_rolled_back",
                    changes=dict(plan.changes),
                    alerts=[Alert("batch_rolled_back", plan.label, "later seat failed; restored qualified preimage", acted=True)],
                )
            else:
                results[plan.label] = InstallResult(
                    label=plan.label,
                    status="batch_rollback_failed",
                    changes=dict(plan.changes),
                    alerts=[Alert("batch_rollback_failed", plan.label, alert.code, acted=True)],
                )
    return [results[label] for label in labels]


def _plan_one(
    manifest: Mapping[str, Any],
    observed: dict[str, Any],
    label: str,
    *,
    home: Path,
) -> _SeatPlan | None:
    """Derive one seat's policy-trio mutation without touching disk.

    Returns None when the seat is already compliant. Raises PolicyRefused for
    any mutation that cannot be proven policy-trio-only BEFORE any write."""
    entry = manifest["seats"][label]
    seat_uid = int(entry["uid"])
    plist_path = home / entry["plist_relpath"]
    changes = policy_changes(observed)
    if not changes:
        return None

    pre_mode = plist_path.stat().st_mode & 0o7777
    target = dict(observed)
    target.update(changes)
    post_raw = serialize_plist(target)
    # Prove the mutation is policy-trio-only before it touches disk.
    reparsed = parse_plist_bytes(post_raw, code=f"{label}_serialize_roundtrip")
    preserved = {k: v for k, v in observed.items() if k not in changes}
    reparsed_preserved = {k: v for k, v in reparsed.items() if k not in changes}
    if preserved != reparsed_preserved:
        raise PolicyRefused(f"{label}_mutation_not_policy_only")
    if any(k not in ("RunAtLoad", "KeepAlive", "ThrottleInterval") for k in changes):
        raise PolicyRefused(f"{label}_mutation_outside_policy_trio")
    return _SeatPlan(
        label=label,
        changes=changes,
        post_raw=post_raw,
        pre_mode=pre_mode,
        seat_uid=seat_uid,
        plist_path=plist_path,
        expected_pre_sha256=str(entry["plist_sha256"]),
        expected_pre_mode=int(entry.get("plist_mode", pre_mode)) & 0o7777,
    )


def _execute_plan(
    home: Path,
    runner: Any,
    plan: _SeatPlan,
    *,
    now: float,
    reload_jobs: bool,
) -> InstallResult:
    """Back up, write, and reload one derived plan, self-rolling back on
    reload failure. Never derives policy: that happened in :func:`_plan_one`.

    CAS custody re-bind (the batch preflight is NOT trusted across time):
    immediately before the mutation the on-disk bytes AND mode must still be
    the EXACT qualified predecessor pinned in the manifest. A concurrent
    external writer that landed after preflight makes this seat refuse — the
    intervening bytes are preserved untouched, no launchd action is taken,
    and the caller aborts/rolls back the rest of the batch. This CAS is the
    single mutation-owner enforcement; no second lifecycle or lock plane is
    introduced."""
    label = plan.label
    try:
        current_raw = plan.plist_path.read_bytes()
        current_mode = plan.plist_path.stat().st_mode & 0o7777
    except OSError as exc:
        return InstallResult(
            label=label, status="failed", changes=dict(plan.changes),
            alerts=[Alert("install_pre_mutation_read_failed", label, str(exc), acted=True)],
        )
    if (
        sha256_bytes(current_raw) != plan.expected_pre_sha256
        or current_mode != plan.expected_pre_mode
    ):
        return InstallResult(
            label=label, status="failed", changes=dict(plan.changes),
            alerts=[Alert("install_pre_mutation_drift_refused", label, "concurrent writer after preflight", acted=True)],
        )
    pre_raw = current_raw
    sidecar = _write_backup(home, label, pre_raw, plan.post_raw, plan.pre_mode, now)
    try:
        atomic_write_bytes(plan.plist_path, plan.post_raw, plan.pre_mode)
    except OSError as exc:
        # The atomic write leaves the original in place on failure; the batch
        # still aborts and earlier seats are rolled back by the caller.
        return InstallResult(
            label=label, status="failed", changes=dict(plan.changes),
            backup_sidecar=str(sidecar),
            alerts=[Alert("install_write_failed", label, str(exc), acted=True)],
        )

    if not reload_jobs:
        return InstallResult(label=label, status="installed", changes=dict(plan.changes), backup_sidecar=str(sidecar))

    try:
        _bootout_if_loaded(runner, plan.seat_uid, label)
        _bootstrap(runner, plan.seat_uid, plan.plist_path)
    except ActionRefused as exc:
        # Roll the preimage back and re-bootstrap the ORIGINAL plist so the
        # seat is never left mutated with its job unloaded.
        rollback_alert = _rollback_preimage(
            home, runner, label, expected_post=sha256_bytes(plan.post_raw), now=now
        )
        if rollback_alert is not None:
            return InstallResult(
                label=label, status="failed", changes=dict(plan.changes),
                backup_sidecar=str(sidecar),
                alerts=[Alert("install_failed_rollback_also_failed", label, str(exc), acted=True)],
            )
        return InstallResult(
            label=label, status="rolled_back", changes=dict(plan.changes),
            backup_sidecar=str(sidecar),
            alerts=[Alert("install_failed_rolled_back", label, str(exc), acted=True)],
        )
    return InstallResult(label=label, status="installed", changes=dict(plan.changes), backup_sidecar=str(sidecar))


def verify_install(home: Path, *, now: float) -> list[str]:
    """Readback evidence: for every seat, the live plist must contain the
    policy trio and every other key must still deep-equal the qualified
    preimage. stdout-safe (no env values)."""
    home = Path(home)
    manifest = load_manifest(home, now=now)
    lines: list[str] = []
    for label in sorted(TUNNEL_LABELS):
        entry = manifest["seats"][label]
        live = parse_plist_bytes(
            (home / entry["plist_relpath"]).read_bytes(), code=f"{label}_verify_read"
        )
        pre = entry["observed_plist"]
        changes = policy_changes(pre)
        problems: list[str] = []
        if live.get("RunAtLoad") is not True:
            problems.append("RunAtLoad!=true")
        if live.get("KeepAlive") is not True:
            problems.append("KeepAlive!=unconditional-true")
        throttle = live.get("ThrottleInterval")
        if not isinstance(throttle, int) or isinstance(throttle, bool) or throttle < 10:
            problems.append("ThrottleInterval<10")
        preserved_live = {k: v for k, v in live.items() if k not in changes}
        preserved_pre = {k: v for k, v in pre.items() if k not in changes}
        if preserved_live != preserved_pre:
            problems.append("non-policy-keys-changed")
        lines.append(
            evidence_line(
                label,
                {
                    "compliant": not problems,
                    "problems": problems or ["none"],
                    "plist_sha256": sha256_bytes((home / entry["plist_relpath"]).read_bytes())[:16],
                },
            )
        )
    return lines


def rollback_seat(
    home: Path,
    runner: Any,
    label: str,
    *,
    confirm: bool,
    now: float,
) -> Alert | None:
    """Restore the newest preimage backup for one seat (explicit, CAS-guarded).

    The current bytes must still hash to the backup's recorded post digest;
    any later drift refuses so an unrelated change is never overwritten.
    """
    if not confirm:
        raise PolicyRefused("rollback_requires_explicit_confirmation")
    home = Path(home)
    if label not in TUNNEL_LABELS:
        raise PolicyRefused("rollback_label_outside_allowlist")
    loaded = _load_backup(home, label)
    if loaded is None:
        return Alert("rollback_no_backup", label)
    sidecar, payload = loaded
    try:
        manifest = load_manifest(home, now=now)
    except IdentityRejected as rejected:
        raise PolicyRefused(f"manifest_unqualified ({rejected})") from rejected
    entry = manifest["seats"][label]
    plist_path = home / entry["plist_relpath"]
    current_raw = plist_path.read_bytes()
    if sha256_bytes(current_raw) != payload.get("post_sha256"):
        return Alert("rollback_cas_refused_current_drifted", label)
    pre_raw = (backups_dir(home) / label / (_backup_stem(sidecar) + ".plist")).read_bytes()
    if sha256_bytes(pre_raw) != payload.get("pre_sha256"):
        return Alert("rollback_backup_digest_mismatch", label)
    # Pre-effect identity re-proof (the CAS above already refused current
    # bytes that drifted from THIS backup's post digest; this refuses any
    # OTHER live drift — argv, executable path/digest/inode/owner/mode,
    # parent and Cellar-allowance pins, pinned poll-profile binding — before
    # the restore write and its launchd reload).
    drift = seat_identity_drift_problems(home, manifest, label)
    if drift:
        return Alert("rollback_identity_drift_refused", label, ",".join(drift))
    pre_mode = int(payload.get("mode", PLIST_DEFAULT_FILE_MODE))
    atomic_write_bytes(plist_path, pre_raw, pre_mode)
    alert = _rollback_preimage(home, runner, label, expected_post=None, now=now, reload_only=True)
    return alert


def _backup_stem(sidecar: Path) -> str:
    return sidecar.name[: -len(".json")]


def _rollback_preimage(
    home: Path,
    runner: Any,
    label: str,
    *,
    expected_post: str | None,
    now: float,
    reload_only: bool = False,
    reload: bool = True,
) -> Alert | None:
    """Internal rollback used by install failure paths: restore newest
    preimage (CAS against ``expected_post`` when provided) and, when
    ``reload`` is set, bootstrap it. ``reload=False`` is for ``reload_jobs=``
    False installs, where launchd was never touched."""
    loaded = _load_backup(home, label)
    if loaded is None:
        return Alert("rollback_no_backup", label, acted=True)
    sidecar, payload = loaded
    try:
        manifest = load_manifest(home, now=now)
    except IdentityRejected as rejected:
        return Alert("rollback_manifest_unqualified", label, str(rejected), acted=True)
    entry = manifest["seats"][label]
    plist_path = home / entry["plist_relpath"]
    seat_uid = int(entry["uid"])
    if expected_post is not None and sha256_bytes(plist_path.read_bytes()) != expected_post:
        return Alert("rollback_cas_refused_current_drifted", label, acted=True)
    pre_raw = (backups_dir(home) / label / (_backup_stem(sidecar) + ".plist")).read_bytes()
    if sha256_bytes(pre_raw) != payload.get("pre_sha256"):
        return Alert("rollback_backup_digest_mismatch", label, acted=True)
    atomic_write_bytes(plist_path, pre_raw, int(payload.get("mode", PLIST_DEFAULT_FILE_MODE)))
    if not reload:
        return None
    if reload_only:
        try:
            _bootout_if_loaded(runner, seat_uid, label)
            _bootstrap(runner, seat_uid, plist_path)
        except ActionRefused as exc:
            return Alert("rollback_rebootstrap_failed", label, str(exc), acted=True)
        return None
    try:
        _bootstrap(runner, seat_uid, plist_path)
    except ActionRefused as exc:
        return Alert("rollback_rebootstrap_failed", label, str(exc), acted=True)
    return None


# ---------------------------------------------------------------------------
# Operator facts file (B4). The closed schema is validated by
# fabric_tunnel_identity._validated_facts; this loader only enforces the file
# itself is a safe, private, regular JSON document.
# ---------------------------------------------------------------------------


def load_operator_facts(path_text: str | None) -> dict[str, Any]:
    """Load the operator-written qualification facts file, fail closed.

    The file must be a regular non-symlink JSON object, not group/world
    WRITABLE (it records private host paths), and is parsed only — never
    executed, never printed. An absent ``--facts-file`` means identity-only
    qualification; every omitted optional fact then surfaces as the matching
    ``*_unqualified`` health alert instead of a guessed default."""
    from fabric_tunnel_common import require_regular_file

    if not path_text:
        return {}
    path = Path(path_text).expanduser()
    require_regular_file(path, code="facts_file_unavailable")
    if path.stat().st_mode & 0o022:
        raise PolicyRefused("facts_file_writable_by_group_or_others")
    try:
        facts = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyRefused(f"facts_file_unreadable ({exc.__class__.__name__})") from exc
    if not isinstance(facts, dict):
        raise PolicyRefused("facts_file_shape_invalid")
    return facts


# CLI surface used by the runbook and the installed watchdog. Kept tiny:
# every subcommand is explicit, prints secret-safe evidence, and exits
# non-zero on any refusal so operators cannot miss one. ``qualify`` is the
# single sanctioned qualification entrypoint (B4); the runbook's first-install
# procedure is qualify --dry-run, qualify --confirm, install --confirm, verify.
def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse
    from fabric_tunnel_identity import qualify_install

    parser = argparse.ArgumentParser(description="Subagent Fabric tunnel launchd policy (FTR-2)")
    parser.add_argument("--home", default=os.path.expanduser("~"))
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "rollback", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--confirm", action="store_true")
        cmd.add_argument("--label", default=None)
        cmd.add_argument("--now", type=float, default=None)
    qualify_cmd = sub.add_parser("qualify")
    qualify_cmd.add_argument("--confirm", action="store_true")
    qualify_cmd.add_argument("--facts-file", default=None)
    qualify_cmd.add_argument("--dry-run", action="store_true")
    qualify_cmd.add_argument("--now", type=float, default=None)
    args = parser.parse_args(argv)
    home = Path(args.home).expanduser()
    runner = subprocess_runner
    now = args.now if args.now is not None else time.time()
    try:
        if args.command == "verify":
            for line in verify_install(home, now=now):
                print(line)
            return 0
        if args.command == "qualify":
            facts = load_operator_facts(args.facts_file)
            for line in qualify_install(
                home,
                uid=os.getuid(),
                facts=facts,
                operator_confirmed=args.confirm,
                now=now,
                dry_run=args.dry_run,
            ):
                print(line)
            return 0
        if args.command == "install":
            results = install_seats(home, runner, confirm=args.confirm, now=now)
            for result in results:
                print(result.as_evidence())
            return 0 if all(r.status in ("installed", "already_compliant") for r in results) else 4
        if args.command == "rollback":
            if not args.label:
                raise PolicyRefused("rollback_requires_label")
            alert = rollback_seat(home, runner, args.label, confirm=args.confirm, now=now)
            print(alert.as_dict() if alert else f"{args.label} status=rolled_back")
            return 0 if alert is None else 4
    except (PolicyRefused, ActionRefused, IdentityRejected) as refused:
        print(f"REFUSED {refused.__class__.__name__}: {refused}", file=os.sys.stderr)
        return 3
    parser.error("unreachable")

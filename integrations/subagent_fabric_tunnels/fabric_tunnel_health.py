"""FTR-3: bounded installed health loop for the five tunnel-client seats.

One invocation = one bounded pass. There is no daemon, queue, retry plane, or
broad process watcher here: the pass reads launchd state, the qualified
heartbeat paths, and host-pull facts, classifies, performs at most one
cooldown-bounded ``launchctl kickstart`` per seat, writes a private report,
and exits.

Classification must DISTINGUISH (plan requirement):
- missing PID on a qualified job            -> recoverable: plain kickstart
- fresh PID + heartbeat older than 300 s    -> recoverable: kickstart -k
- fresh PID + fresh heartbeat               -> healthy, no action
- stale host-pull telemetry                 -> alert only, never a restart
- selected generation != qualified pinned   -> drift alert; repin is REFUSED
  (CURRENT.json is never selected or rewritten by this integration)
- installed generation missing the
  qualified stdin/ARG_MAX repair digests    -> repair_missing alert, never
  an automatic selection, publish, or repin

Anything unqualified (no operator manifest, missing heartbeat path, unknown
label, forbidden label) produces an explicit alert and NO recovery action.

Two durability contracts keep this pass safe beyond the manifest's one-day
attestation bound (B1) and the heartbeat's first-party proof requirement (B6):

- A stale manifest no longer disables recovery. ``run_pass`` re-proves every
  seat's installed identity, program digest/argv, and qualified heartbeat
  path from LIVE host state each pass (``revalidate_stale_identity``) and
  raises a persistent ``manifest_stale_revalidated`` alert. A seat whose live
  identity no longer matches the pinned manifest is ALERT ONLY (no
  kickstart) until a human requalifies. Mutation paths still refuse stale
  manifests outright.
- A stale heartbeat only triggers a forced restart when the operator
  qualified that seat's heartbeat with an explicit first-party kind and proof
  note. Without that attestation the mtime of an arbitrary file is never
  treated as the tunnel-client/control-plane last-seen signal: the outcome is
  ``stale_heartbeat_unproven_alert_only`` stating the exact required host
  proof. (Missing-PID recovery is unaffected: it is proven by launchd
  itself, not by any heartbeat file.)
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import time
from pathlib import Path
from typing import Any, Mapping

from fabric_tunnel_common import (
    DEFAULT_STALE_TELEMETRY_SECONDS,
    FORBIDDEN_LABELS,
    KICKSTART_COOLDOWN_SECONDS,
    KICKSTART_ESCALATION_LIMIT,
    KICK_LEDGER_SCHEMA,
    MANIFEST_MAX_AGE_SECONDS,
    MASTER_SHA,
    MAX_TELEMETRY_FILES,
    PLAN_COMMIT,
    STALE_HEARTBEAT_SECONDS,
    WATCHDOG_START_INTERVAL_SECONDS,
    TUNNEL_LABELS,
    WATCHDOG_LABEL,
    ActionRefused,
    Alert,
    IdentityRejected,
    PassReport,
    PolicyRefused,
    atomic_write_bytes,
    backups_dir,
    evidence_line,
    kick_ledger_path,
    last_pass_path,
    launchctl_kickstart_argv,
    launchctl_print_argv,
    parse_print_pid,
    plist_relpath,
    private_state_root,
    require_regular_file,
    sha256_bytes,
    state_dir,
    subprocess_runner,
    watchdog_dir,
)
from fabric_tunnel_identity import (
    load_manifest,
    manifest_is_stale,
    revalidate_stale_identity,
    scan_family,
    telemetry_relative_path_reject_reason,
    unqualified_health_alerts,
)

# Health states, one per distinguishable outcome the plan names.
ST_HEALTHY = "healthy"
ST_MISSING_PID = "missing_pid"
ST_STALE_HEARTBEAT = "stale_heartbeat"
ST_STALE_HEARTBEAT_UNPROVEN = "stale_heartbeat_unproven_alert_only"
ST_HEARTBEAT_UNQUALIFIED = "heartbeat_unqualified"
ST_HEARTBEAT_MISSING = "heartbeat_missing"
ST_UNQUALIFIED = "unqualified"
ST_COOLDOWN = "kickstart_suppressed_cooldown"
ST_ESCALATED = "kickstart_escalated_alert"
ST_IDENTITY_SUSPECT = "identity_suspect_alert_only"

GEN_CONSISTENT = "store_consistent"
GEN_DRIFT = "selected_generation_drift"
GEN_MISSING = "selected_generation_missing"
GEN_STORE_UNQUALIFIED = "native_store_unqualified"
REPAIR_MISSING = "stdin_argmax_repair_missing"
REPAIR_UNQUALIFIED = "stdin_argmax_repair_unqualified"
TELEMETRY_STALE = "host_pull_telemetry_stale"
TELEMETRY_UNQUALIFIED = "host_pull_telemetry_unqualified"


# ---------------------------------------------------------------------------
# Pure classification (unit-tested without any host).
# ---------------------------------------------------------------------------


def classify_seat(
    *,
    qualified: bool,
    pid: int | None,
    heartbeat_age: float | None,
    heartbeat_path_recorded: bool,
    heartbeat_attested: bool = False,
    last_kick_at: float | None,
    consecutive_kicks: int,
    fresh_heartbeat_witnessed_since_kick: bool,
    now: float,
) -> tuple[str, bool]:
    """Return (state, may_kickstart).

    ``may_kickstart`` is True only for the two qualified recovery states and
    only when the persisted cooldown and escalation ledger allow it.

    ``heartbeat_attested`` is the B6 first-party proof switch: it must be
    True (operator-qualified ``heartbeat_kind`` + proof note in the manifest)
    before a stale heartbeat may force-restart a live job. Without it, the
    mtime of an arbitrary file cannot prove the tunnel client is wedged, so
    the outcome is alert-only. Missing-PID recovery does not depend on the
    heartbeat file — launchd itself proves that state — so it stays
    recoverable either way.
    """
    if not qualified or not heartbeat_path_recorded:
        return ST_UNQUALIFIED, False
    if pid is None:
        if _cooldown_blocks(last_kick_at, now):
            return ST_COOLDOWN, False
        return ST_MISSING_PID, True
    if heartbeat_age is None:
        return ST_HEARTBEAT_MISSING, False
    if heartbeat_age > STALE_HEARTBEAT_SECONDS:
        if not heartbeat_attested:
            return ST_STALE_HEARTBEAT_UNPROVEN, False
        if consecutive_kicks >= KICKSTART_ESCALATION_LIMIT and not fresh_heartbeat_witnessed_since_kick:
            return ST_ESCALATED, False
        if _cooldown_blocks(last_kick_at, now):
            return ST_COOLDOWN, False
        return ST_STALE_HEARTBEAT, True
    return ST_HEALTHY, False


def _cooldown_blocks(last_kick_at: float | None, now: float) -> bool:
    return last_kick_at is not None and (now - last_kick_at) < KICKSTART_COOLDOWN_SECONDS


def classify_generation(
    *,
    manifest_host: Mapping[str, Any],
    selected_generation: str | None,
    installed_repair_digests: Mapping[str, str] | None,
    telemetry_age: float | None,
) -> list[Alert]:
    """Host-level classification. Every outcome here is an alert; this
    function cannot express a store mutation because it returns alerts only
    and never receives a store path to write to."""
    alerts: list[Alert] = []
    store = manifest_host.get("native_store_path")
    if not store:
        alerts.append(Alert(GEN_STORE_UNQUALIFIED, "host"))
    pinned = manifest_host.get("pinned_generation")
    if not pinned:
        alerts.append(Alert("pinned_generation_unqualified", "host"))
    elif selected_generation is None:
        alerts.append(Alert(GEN_MISSING, "host"))
    elif selected_generation != pinned:
        alerts.append(
            Alert(
                GEN_DRIFT,
                "host",
                f"selected={selected_generation} pinned={pinned}; repin refused; "
                "CURRENT.json never rewritten by this integration",
            )
        )
    repair = manifest_host.get("repair")
    if not isinstance(repair, dict) or not repair.get("files"):
        alerts.append(Alert(REPAIR_UNQUALIFIED, "host"))
    else:
        wanted = {str(rel): str(digest) for rel, digest in repair["files"].items()}
        observed = installed_repair_digests or {}
        missing = sorted(rel for rel, digest in wanted.items() if observed.get(rel) != digest)
        if missing:
            alerts.append(Alert(REPAIR_MISSING, "host", ",".join(missing)))
    # Telemetry is only qualified when BOTH the root dir and the closed
    # explicit file set were operator-qualified (B2). No fallback scan exists.
    telemetry_files = manifest_host.get("host_pull_telemetry_files")
    telemetry_qualified = (
        bool(manifest_host.get("host_pull_telemetry_dir"))
        and isinstance(telemetry_files, list)
        and bool(telemetry_files)
    )
    if telemetry_qualified:
        threshold = float(manifest_host.get("stale_telemetry_seconds") or DEFAULT_STALE_TELEMETRY_SECONDS)
        if telemetry_age is None:
            alerts.append(Alert(TELEMETRY_UNQUALIFIED, "host", "qualified telemetry unreadable or unqualified"))
        elif telemetry_age > threshold:
            alerts.append(Alert(TELEMETRY_STALE, "host", f"age={int(telemetry_age)}s oldest_required"))
    else:
        alerts.append(Alert(TELEMETRY_UNQUALIFIED, "host"))
    return alerts


# ---------------------------------------------------------------------------
# Host observation (all injected; hermetic tests fake every seam).
# ---------------------------------------------------------------------------


def read_job_pid(runner: Any, uid: int, label: str) -> int | None:
    result = runner(launchctl_print_argv(uid, label))
    if result.returncode != 0:
        return None  # job not loaded / domain missing -> missing PID
    return parse_print_pid(result.stdout)


def read_heartbeat_age(recorded_path: str, now: float) -> float | None:
    path = Path(recorded_path)
    try:
        st = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None  # symlink or special file is not a trustworthy heartbeat
    return max(0.0, now - st.st_mtime)


def read_selected_generation(native_store_path: str) -> str | None:
    """Read CURRENT.json (READ ONLY) from the native-code-releases store.

    Never written, never selected, never repointed here. Accepts the store
    layout used by ops/native_fabric/quota_continuity/rollout/native_generation.py
    (CURRENT.json holding {"generation": <hex64>}).
    """
    path = Path(native_store_path) / "CURRENT.json"
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        doc = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    generation = doc.get("generation")
    return generation if isinstance(generation, str) else None


def read_repair_digests(native_store_path: str, selected_generation: str | None, repair_files: list[str]) -> dict[str, str] | None:
    """Digest the selected generation's repair files, read-only."""
    if not selected_generation:
        return None
    root = Path(native_store_path) / selected_generation
    digests: dict[str, str] = {}
    for rel in repair_files:
        try:
            raw = (root / rel).read_bytes()
        except OSError:
            continue
        digests[rel] = sha256_bytes(raw)
    return digests


def read_telemetry_age(telemetry_dir: str, relative_files: Any, now: float) -> float | None:
    """Age of the OLDEST file in the operator-qualified closed telemetry set.

    Bounded by construction (B2): only the explicit qualified relative paths
    are ever read — never a recursive scan — so an unrelated freshly written
    file under the same root cannot mask stale host-pull telemetry and a
    large directory cannot make the minute watchdog unbounded. Any missing,
    symlinked, special-file, wrong-suffix, escaping, duplicated, over-count,
    or malformed entry rejects the WHOLE reading (returns None, which the
    caller surfaces as ``host_pull_telemetry_unqualified``); it never
    degrades to a partial freshness proof.
    """
    root = Path(telemetry_dir)
    files = list(relative_files or [])
    if not files or len(files) > MAX_TELEMETRY_FILES:
        return None
    if len(set(files)) != len(files):
        return None
    try:
        resolved_root = root.resolve()
    except OSError:
        return None
    oldest: float | None = None
    for rel in files:
        if telemetry_relative_path_reject_reason(rel):
            return None
        candidate = root / rel
        try:
            st = candidate.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            return None
        try:
            resolved = candidate.resolve()
        except OSError:
            return None
        if resolved_root not in resolved.parents:
            return None  # symlinked ancestor or other root escape
        oldest = st.st_mtime if oldest is None else min(oldest, st.st_mtime)
    if oldest is None:
        return None
    return max(0.0, now - oldest)


# ---------------------------------------------------------------------------
# Cooldown / escalation ledger (private, persisted, 0600).
# ---------------------------------------------------------------------------


def load_kick_ledger(home: Path) -> dict[str, Any]:
    path = kick_ledger_path(home)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {"schema": KICK_LEDGER_SCHEMA, "seats": {}}
    try:
        ledger = json.loads(raw)
    except ValueError:
        return {"schema": KICK_LEDGER_SCHEMA, "seats": {}}
    if not isinstance(ledger, dict) or ledger.get("schema") != KICK_LEDGER_SCHEMA:
        return {"schema": KICK_LEDGER_SCHEMA, "seats": {}}
    ledger.setdefault("seats", {})
    return ledger


def save_kick_ledger(home: Path, ledger: Mapping[str, Any]) -> None:
    path = kick_ledger_path(home)
    raw = json.dumps(dict(ledger), indent=2, sort_keys=True).encode("utf-8")
    atomic_write_bytes(path, raw, 0o600)
    os.chmod(path, 0o600)


def _record_kick(ledger: dict[str, Any], label: str, now: float) -> None:
    seats = ledger["seats"]
    entry = seats.get(label) or {}
    prior = entry.get("consecutive_kicks") or 0
    seats[label] = {
        "last_kick_at": now,
        "consecutive_kicks": prior + 1,
        "fresh_heartbeat_witnessed_since_kick": False,
    }


def _witness_recovery(ledger: dict[str, Any], label: str) -> None:
    entry = ledger["seats"].get(label)
    if isinstance(entry, dict):
        entry["consecutive_kicks"] = 0
        entry["fresh_heartbeat_witnessed_since_kick"] = True


# ---------------------------------------------------------------------------
# One bounded pass.
# ---------------------------------------------------------------------------


def run_pass(
    home: Path,
    runner: Any,
    *,
    now: float,
    recover: bool = True,
) -> PassReport:
    """Single bounded health pass over exactly the five qualified labels.

    The pass tolerates a manifest past its one-day attestation bound (B1):
    trust is then re-derived from live host state per seat, and any seat
    whose live identity no longer matches the pinned manifest is ALERT ONLY
    for this pass. Mutation paths never receive this leniency."""
    home = Path(home)
    report = PassReport(started_at=now)
    try:
        manifest = load_manifest(home, now=now, allow_stale_revalidation=True)
    except (PolicyRefused, IdentityRejected) as refused:
        report.alerts.append(Alert("not_qualified", "host", str(refused)))
        _finish(report, home, now)
        return report

    for alert in unqualified_health_alerts(home, manifest):
        report.alerts.append(alert)

    # B1: past the day boundary, re-prove installed identity, program
    # digest/argv, and the qualified heartbeat path from live host state.
    # Suspect seats get alert-only treatment; recovery for the others
    # continues so one tampered seat cannot disable the whole watchdog.
    suspect_labels: frozenset[str] = frozenset()
    manifest_stale = manifest_is_stale(manifest, now)
    if manifest_stale:
        report.alerts.append(
            Alert(
                "manifest_stale_revalidated",
                "host",
                "attestation age exceeded; per-seat identity+digest/argv+heartbeat revalidated from live host state this pass; requalify to renew",
            )
        )
        reval_alerts, suspect_labels = revalidate_stale_identity(home, manifest)
        report.alerts.extend(reval_alerts)

    # Host-pull facts (read-only). Absent qualification degrades to alerts.
    store = manifest.get("native_store_path")
    selected: str | None = None
    repair_digests: dict[str, str] | None = None
    telemetry_age: float | None = None
    if store:
        selected = read_selected_generation(store)
        repair = manifest.get("repair")
        files = sorted((repair or {}).get("files", {}))
        if files:
            repair_digests = read_repair_digests(store, selected, files)
    telemetry_files = manifest.get("host_pull_telemetry_files")
    if manifest.get("host_pull_telemetry_dir") and isinstance(telemetry_files, list) and telemetry_files:
        telemetry_age = read_telemetry_age(manifest["host_pull_telemetry_dir"], telemetry_files, now)
    report.generation = {
        "selected_generation": selected,
        "pinned_generation": manifest.get("pinned_generation"),
        "telemetry_age_seconds": None if telemetry_age is None else int(telemetry_age),
        "manifest_stale_revalidated": bool(manifest_stale),
    }
    for alert in classify_generation(
        manifest_host=manifest,
        selected_generation=selected,
        installed_repair_digests=repair_digests,
        telemetry_age=telemetry_age,
    ):
        report.alerts.append(alert)

    # Rogue family member: alert and refuse recovery for the whole pass.
    rogue = scan_family(home)
    if rogue:
        report.alerts.append(Alert("rogue_family_labels_present", "host", ",".join(rogue)))

    ledger = load_kick_ledger(home)
    seats: dict[str, Any] = {}
    for label in sorted(TUNNEL_LABELS):
        entry = manifest["seats"][label]
        seat_uid = int(entry["uid"])
        heartbeat_path = entry.get("heartbeat_path")
        heartbeat_attested = bool(entry.get("heartbeat_kind"))
        heartbeat_age = read_heartbeat_age(heartbeat_path, now) if heartbeat_path else None
        # A rogue family member suspends per-seat recovery for this pass:
        # identity of the family itself is in question, so no kickstarts.
        pid = read_job_pid(runner, seat_uid, label) if not rogue else None
        if label in suspect_labels:
            state, may_kick = ST_IDENTITY_SUSPECT, False
        else:
            state, may_kick = classify_seat(
                qualified=bool(heartbeat_path) and not rogue,
                pid=pid,
                heartbeat_age=heartbeat_age,
                heartbeat_path_recorded=bool(heartbeat_path),
                heartbeat_attested=heartbeat_attested,
                last_kick_at=(ledger["seats"].get(label) or {}).get("last_kick_at"),
                consecutive_kicks=int((ledger["seats"].get(label) or {}).get("consecutive_kicks") or 0),
                fresh_heartbeat_witnessed_since_kick=bool(
                    (ledger["seats"].get(label) or {}).get("fresh_heartbeat_witnessed_since_kick")
                ),
                now=now,
            )
        acted = False
        kick_forced = False
        if may_kick and recover and not rogue:
            try:
                kick_argv = launchctl_kickstart_argv(seat_uid, label, force=(state == ST_STALE_HEARTBEAT))
                result = runner(kick_argv)
                if result.returncode == 0:
                    acted = True
                    kick_forced = state == ST_STALE_HEARTBEAT
                    _record_kick(ledger, label, now)
                else:
                    report.alerts.append(
                        Alert("kickstart_failed", label, f"rc={result.returncode}", acted=True)
                    )
            except ActionRefused as refused:
                report.alerts.append(Alert("kickstart_refused", label, str(refused), acted=True))
        if state == ST_HEALTHY:
            _witness_recovery(ledger, label)
        seats[label] = {
            "pid": pid,
            "heartbeat_age_seconds": None if heartbeat_age is None else int(heartbeat_age),
            "state": state,
            "heartbeat_attested": heartbeat_attested,
            "kickstarted": acted,
            "kickstarted_forced": kick_forced,
        }
        report.alerts.extend(
            alert for alert in _seat_alerts(state, label) if alert.code not in {a.code for a in report.alerts if a.label == label}
        )
    save_kick_ledger(home, ledger)
    report.seats = seats
    _finish(report, home, now)
    return report


def _seat_alerts(state: str, label: str) -> list[Alert]:
    if state == ST_HEARTBEAT_MISSING:
        return [Alert(ST_HEARTBEAT_MISSING, label)]
    if state == ST_ESCALATED:
        return [Alert(ST_ESCALATED, label, "repeated kicks without a fresh heartbeat")]
    if state == ST_STALE_HEARTBEAT_UNPROVEN:
        return [
            Alert(
                ST_STALE_HEARTBEAT_UNPROVEN,
                label,
                "heartbeat mtime not proven first-party; required host proof: qualify the seat with "
                "heartbeat_kind + heartbeat_proof_note (operator-correlated tunnel-client control-plane "
                "last-seen) before forced restarts are enabled",
            )
        ]
    return []


def _finish(report: PassReport, home: Path, now: float) -> None:
    report.finished_at = now
    path = last_pass_path(home)
    raw = json.dumps(report.as_dict(), indent=2, sort_keys=True).encode("utf-8")
    atomic_write_bytes(path, raw, 0o600)
    os.chmod(path, 0o600)


# ---------------------------------------------------------------------------
# Watchdog LaunchAgent (the one NEW label this integration owns).
# ---------------------------------------------------------------------------

_WATCHDOG_MODULE_FILES = (
    "fabric_tunnel_common.py",
    "fabric_tunnel_identity.py",
    "fabric_tunnel_install.py",
    "fabric_tunnel_health.py",
)

WATCHDOG_BACKUP_SCHEMA = "mastermind.subagent-fabric-tunnels.watchdog-preimage.v1"


def _watchdog_backup_dir(home: Path, name: str) -> Path:
    directory = backups_dir(home) / WATCHDOG_LABEL / name.replace("/", "_")
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    return directory


def _backup_watchdog_target(
    home: Path,
    name: str,
    pre_raw: bytes | None,
    pre_mode: int | None,
    post_raw: bytes,
    now: float,
) -> Path:
    """Exact preimage backup for one watchdog target, written BEFORE the edit.

    ``pre_raw is None`` records that the target did not exist, so a rollback
    restores absence (unlinks) rather than guessing bytes. Backups stay in
    the private state root (0700 dirs, 0600 files), never in the repo."""
    directory = _watchdog_backup_dir(home, name)
    stem = f"{int(now * 1000)}-{sha256_bytes(pre_raw)[:12] if pre_raw is not None else 'absent'}"
    blob = directory / f"{stem}{Path(name).suffix or '.bin'}"
    sidecar = directory / f"{stem}.json"
    payload = {
        "schema": WATCHDOG_BACKUP_SCHEMA,
        "label": WATCHDOG_LABEL,
        "target": name,
        "plan_commit": PLAN_COMMIT,
        "pre_existed": pre_raw is not None,
        "pre_sha256": sha256_bytes(pre_raw) if pre_raw is not None else None,
        "post_sha256": sha256_bytes(post_raw),
        "mode": pre_mode,
        "created_at": now,
        "private": "never commit, never log contents",
    }
    if pre_raw is not None:
        atomic_write_bytes(blob, pre_raw, 0o600)
        os.chmod(blob, 0o600)
    atomic_write_bytes(sidecar, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"), 0o600)
    os.chmod(sidecar, 0o600)
    return sidecar


def _load_watchdog_backup(home: Path, name: str) -> tuple[Path, dict[str, Any]] | None:
    directory = _watchdog_backup_dir(home, name)
    sidecars = sorted(directory.glob("*.json"))
    if not sidecars:
        return None
    newest = sidecars[-1]
    try:
        payload = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyRefused(f"watchdog_backup_sidecar_unreadable ({exc.__class__.__name__})") from exc
    if payload.get("schema") != WATCHDOG_BACKUP_SCHEMA:
        raise PolicyRefused("watchdog_backup_schema_unknown")
    return newest, payload


def _watchdog_target_path(home: Path, name: str) -> Path:
    """Absolute path of one watchdog target by its qualified target name.

    Module names are bare filenames inside the private watchdog dir; the
    plist target is named by its home-relative relpath (contains a ``/``)."""
    if "/" in name:
        return home / name
    return watchdog_dir(home) / name


def _rollback_watchdog_install(home: Path, runner: Any, *, uid: int) -> list[Alert]:
    """Restore every watchdog target to its exact pre-install state — bytes
    and mode when the target existed, absence when it did not (CAS: digest
    verified against the sidecar) — then leave launchd consistent with the
    RESTORED disk (bootout always; bootstrap only a restored plist)."""
    from fabric_tunnel_install import _bootout_if_loaded, _bootstrap

    alerts: list[Alert] = []
    plist_name = plist_relpath(WATCHDOG_LABEL)
    pre_existed_by_name: dict[str, bool | None] = {}
    for name in (*_WATCHDOG_MODULE_FILES, plist_name):
        target = _watchdog_target_path(home, name)
        loaded = _load_watchdog_backup(home, name)
        if loaded is None:
            alerts.append(Alert("watchdog_rollback_no_backup", name, acted=True))
            pre_existed_by_name[name] = None
            continue
        sidecar, payload = loaded
        pre_existed_by_name[name] = bool(payload.get("pre_existed"))
        if not pre_existed_by_name[name]:
            try:
                target.unlink()
            except OSError:
                alerts.append(Alert("watchdog_rollback_unlink_failed", name, acted=True))
            continue
        blob = sidecar.parent / (sidecar.stem + (Path(name).suffix or ".bin"))
        try:
            pre_raw = blob.read_bytes()
        except OSError:
            alerts.append(Alert("watchdog_rollback_backup_unreadable", name, acted=True))
            continue
        if sha256_bytes(pre_raw) != payload.get("pre_sha256"):
            alerts.append(Alert("watchdog_rollback_backup_digest_mismatch", name, acted=True))
            continue
        mode = int(payload.get("mode") or (0o644 if name.endswith(".plist") else 0o600))
        atomic_write_bytes(target, pre_raw, mode)
        if target.read_bytes() != pre_raw:
            alerts.append(Alert("watchdog_rollback_readback_mismatch", name, acted=True))
    try:
        _bootout_if_loaded(runner, uid, WATCHDOG_LABEL)
        if pre_existed_by_name.get(plist_name):
            _bootstrap(runner, uid, _watchdog_target_path(home, plist_name))
    except ActionRefused as exc:
        alerts.append(Alert("watchdog_rollback_reload_failed", WATCHDOG_LABEL, str(exc), acted=True))
    return alerts


def install_watchdog_agent(
    home: Path,
    runner: Any,
    *,
    confirm: bool,
    now: float,
) -> str:
    """Install the health-loop LaunchAgent from repository-owned source.

    The agent runs ONE bounded pass per fire (StartInterval, no KeepAlive —
    a periodic job must not be resurrected into a tight loop). The python3
    interpreter is resolved from the host at install time, never hardcoded,
    and the run fails closed if none exists. The generated plist only ever
    references our own watchdog label and the five-seat allowlist; the
    Desktop Commander carrier is not referenced by any generated argv.

    Upgrade/overwrite safety (B3): every existing target (the four copied
    modules and the watchdog plist) is captured as an exact private preimage
    backup BEFORE any edit; a target that is already byte-identical is left
    untouched (idempotent readback, no backup churn); a symlinked or
    unsafe target refuses instead of being overwritten; every write is
    verified by read-back digest; and ANY post-write or launchd failure rolls
    ALL targets back to their exact preimage (or absence) and reloads the
    restored plist, then raises. Requires a fresh manifest: watchdog install
    is an install-time mutation and keeps the strict freshness contract."""
    if not confirm:
        raise PolicyRefused("watchdog_install_requires_explicit_confirmation")
    load_manifest(home, now=now)  # strict: install-time authorization is fresh
    from fabric_tunnel_install import _bootout_if_loaded, _bootstrap

    interpreter = shutil.which("python3")
    if not interpreter:
        raise PolicyRefused("python3_interpreter_unavailable")

    home = Path(home)
    module_dir = Path(__file__).resolve().parent
    target_dir = watchdog_dir(home)
    target_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(target_dir, 0o700)
    module_raws: dict[str, bytes] = {}
    for name in _WATCHDOG_MODULE_FILES:
        source = module_dir / name
        require_regular_file(source, code="watchdog_source_missing")
        module_raws[name] = source.read_bytes()

    log_dir = private_state_root(home) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(log_dir, 0o700)
    program = [
        interpreter,
        str(target_dir / "fabric_tunnel_health.py"),
        "pass",
        "--home",
        str(home),
    ]
    plist: dict[str, Any] = {
        "Label": WATCHDOG_LABEL,
        "ProgramArguments": program,
        "RunAtLoad": True,
        "StartInterval": WATCHDOG_START_INTERVAL_SECONDS,
        "ThrottleInterval": 10,
        "StandardOutPath": str(log_dir / "watchdog.out.log"),
        "StandardErrorPath": str(log_dir / "watchdog.err.log"),
    }
    assert "KeepAlive" not in plist  # periodic job: never resurrect-looped
    assert plist["Label"] not in FORBIDDEN_LABELS

    from fabric_tunnel_common import serialize_plist as _ser

    plist_path = home / plist_relpath(WATCHDOG_LABEL)
    plist_raw = _ser(plist)
    targets: list[tuple[str, Path, bytes, int]] = [
        (name, target_dir / name, module_raws[name], 0o600)
        for name in _WATCHDOG_MODULE_FILES
    ] + [(plist_relpath(WATCHDOG_LABEL), plist_path, plist_raw, 0o644)]

    # Capture exact preimages BEFORE any write; refuse unsafe targets.
    preimages: dict[str, tuple[bytes | None, int | None]] = {}
    for name, dest, _raw, _mode in targets:
        if dest.is_symlink() or dest.exists():
            try:
                require_regular_file(dest, code="watchdog_target_unsafe")
            except IdentityRejected as rejected:
                raise PolicyRefused(str(rejected)) from rejected
            st = dest.lstat()
            preimages[name] = (dest.read_bytes(), st.st_mode & 0o7777)
        else:
            preimages[name] = (None, None)

    # Chairman rule: back up any file before editing. Only targets about to
    # CHANGE get a backup; identical targets are skipped entirely.
    for name, _dest, raw, _mode in targets:
        if preimages[name][0] == raw:
            continue
        _backup_watchdog_target(home, name, preimages[name][0], preimages[name][1], raw, now)

    # Apply only changed targets, atomically, with read-back CAS.
    for name, dest, raw, mode in targets:
        if preimages[name][0] == raw:
            continue
        atomic_write_bytes(dest, raw, mode)
        os.chmod(dest, mode)
        if dest.read_bytes() != raw:
            alerts = _rollback_watchdog_install(home, runner, uid=os.getuid())
            raise ActionRefused(
                f"watchdog_install_post_write_mismatch_rolled_back alerts={[a.code for a in alerts]}"
            )

    try:
        _bootout_if_loaded(runner, os.getuid(), WATCHDOG_LABEL)
        _bootstrap(runner, os.getuid(), plist_path)
    except ActionRefused as exc:
        alerts = _rollback_watchdog_install(home, runner, uid=os.getuid())
        raise ActionRefused(
            f"watchdog_install_bootstrap_failed_rolled_back alerts={[a.code for a in alerts]} cause={exc}"
        ) from exc
    return str(plist_path)


# ---------------------------------------------------------------------------
# CLI. Subcommands: pass (health loop), and a read-only print of the last
# pass report. No secrets are ever printed; reports contain no argv bodies.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse

    parser = argparse.ArgumentParser(description="Subagent Fabric tunnel health loop (FTR-3)")
    sub = parser.add_subparsers(dest="command", required=True)
    pass_cmd = sub.add_parser("pass")
    pass_cmd.add_argument("--home", default=os.path.expanduser("~"))
    pass_cmd.add_argument("--observe-only", action="store_true")
    last_cmd = sub.add_parser("last-pass")
    last_cmd.add_argument("--home", default=os.path.expanduser("~"))
    args = parser.parse_args(argv)
    home = Path(args.home).expanduser()
    home = Path(home)
    if args.command == "last-pass":
        try:
            doc = json.loads(last_pass_path(home).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("last-pass unavailable")
            return 4
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    now = time.time()
    report = run_pass(home, subprocess_runner, now=now, recover=not args.observe_only)
    for label in sorted(report.seats):
        print(evidence_line(label, report.seats[label]))
    for alert in report.alerts:
        print(evidence_line("ALERT", alert.as_dict()))
    blocking = {
        "not_qualified",
        GEN_DRIFT,
        REPAIR_MISSING,
        ST_ESCALATED,
        ST_HEARTBEAT_MISSING,
        ST_STALE_HEARTBEAT_UNPROVEN,
        ST_IDENTITY_SUSPECT,
        "manifest_stale_revalidated",
        "seat_identity_tampered_alert_only",
        "seat_identity_rejected",
        TELEMETRY_STALE,
    }
    if any(alert.code in blocking for alert in report.alerts):
        return 4
    return 0

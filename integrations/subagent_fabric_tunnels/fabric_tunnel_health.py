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
    parse_plist_bytes,
    parse_print_pid,
    plist_relpath,
    private_state_root,
    require_parent_safe,
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
ST_LAUNCHD_UNCERTAIN = "launchd_state_uncertain_alert_only"
ST_LEDGER_REFUSED = "kick_ledger_refused_alert_only"

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

    The persisted escalation limit binds BOTH recovery routes identically
    (missing-PID and stale-heartbeat): after ``KICKSTART_ESCALATION_LIMIT``
    consecutive kicks without a witnessed fresh heartbeat, the seat is
    ESCALATED — alert-only — even once the cooldown has elapsed, and no
    fourth kick may occur until a fresh heartbeat is witnessed (the seat
    classified ``healthy``), which resets the persisted counter. Without
    this gate the missing-PID route could kick every cooldown forever.

    ``heartbeat_attested`` is the B6 first-party proof switch: it must be
    True (operator-qualified ``heartbeat_kind`` + proof note in the manifest)
    before a stale heartbeat may force-restart a live job. Without it, the
    mtime of an arbitrary file cannot prove the tunnel client is wedged, so
    the outcome is alert-only. Missing-PID recovery does not depend on the
    heartbeat file — launchd itself proves that state — so it stays
    recoverable either way (still under the same escalation gate).
    """
    if not qualified or not heartbeat_path_recorded:
        return ST_UNQUALIFIED, False
    escalated = (
        consecutive_kicks >= KICKSTART_ESCALATION_LIMIT
        and not fresh_heartbeat_witnessed_since_kick
    )
    if pid is None:
        if escalated:
            return ST_ESCALATED, False
        if _cooldown_blocks(last_kick_at, now):
            return ST_COOLDOWN, False
        return ST_MISSING_PID, True
    if heartbeat_age is None:
        return ST_HEARTBEAT_MISSING, False
    if heartbeat_age > STALE_HEARTBEAT_SECONDS:
        if not heartbeat_attested:
            return ST_STALE_HEARTBEAT_UNPROVEN, False
        if escalated:
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


class _PIDStateUnknown:
    """Singleton sentinel returned by :func:`read_job_pid` when launchd state
    is UNCERTAIN. This is NOT a missing PID: the print failed for a reason
    other than the specific known unloaded-job diagnostic (permission,
    transport, or domain ambiguity), so no recovery may be planned. Any
    recovery decision keyed on ``pid is None`` stays unreachable for this
    value because identity (``is``) checks against the sentinel come first."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "PID_STATE_UNKNOWN"


PID_STATE_UNKNOWN = _PIDStateUnknown()

# launchctl's SPECIFIC diagnostic for a job that is not loaded in the queried
# domain. Only this phrase (with a nonzero print rc) qualifies a print failure
# as a real missing/unloaded job; every other nonzero rc is ambiguous and
# must be alert-only, never a kickstart.
_LAUNCHCTL_UNLOADED_DIAGNOSTIC = "Could not find service"


def print_says_unloaded(result: Any) -> bool:
    """True only when a failed ``launchctl print`` carries the SPECIFIC known
    unloaded-job diagnostic. A bare nonzero rc is never sufficient."""
    if result.returncode == 0:
        return False
    haystack = "\n".join((result.stderr or "", result.stdout or ""))
    return _LAUNCHCTL_UNLOADED_DIAGNOSTIC in haystack


def read_job_pid(runner: Any, uid: int, label: str) -> int | None | _PIDStateUnknown:
    """Read one job's PID from launchd, failing closed on ambiguity.

    - rc 0: the job IS loaded; the ``launchctl print`` output is the
      qualified state document — a missing ``pid =`` line there is a real
      missing PID (loaded but not running).
    - nonzero rc WITH the specific ``Could not find service`` diagnostic:
      the known unloaded-job answer -> missing PID.
    - ANY other nonzero rc (permission, transport, domain ambiguity): the
      launchd state is UNKNOWN -> the :data:`PID_STATE_UNKNOWN` sentinel;
      callers must treat it as alert-only, never as absent, and never
      kickstart on it."""
    result = runner(launchctl_print_argv(uid, label))
    if result.returncode == 0:
        return parse_print_pid(result.stdout)
    if print_says_unloaded(result):
        return None  # specific qualified unloaded-job diagnostic
    return PID_STATE_UNKNOWN


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


def fresh_kick_ledger() -> dict[str, Any]:
    """The empty first-use ledger. ONLY for a genuinely absent ledger file —
    never as a fallback for a ledger that exists but cannot be trusted."""
    return {"schema": KICK_LEDGER_SCHEMA, "seats": {}}


def load_kick_ledger(home: Path) -> dict[str, Any]:
    """Load the persisted cooldown/escalation ledger, FAILING CLOSED.

    Distinguishing absent first-use from untrusted existing state is a
    safety contract: cooldown and escalation history is what bounds
    kickstarts, so a corrupt, unreadable, symlinked, non-regular, or
    permission-unsafe EXISTING ledger is never silently reset to empty
    (that would erase escalation and re-enable unbounded restarts). Every
    uncertain state raises :class:`PolicyRefused` with a stable code; the
    pass that hits one goes alert-only for ALL recovery instead of
    guessing. Only a genuinely absent file (first use) initializes."""
    path = kick_ledger_path(home)
    try:
        st = path.lstat()
    except FileNotFoundError:
        return fresh_kick_ledger()  # absent -> genuine first use
    except OSError as exc:
        raise PolicyRefused(f"kick_ledger_unreadable ({exc.strerror})") from exc
    if stat.S_ISLNK(st.st_mode):
        raise PolicyRefused("kick_ledger_symlinked")
    if not stat.S_ISREG(st.st_mode):
        raise PolicyRefused("kick_ledger_not_regular")
    if st.st_mode & 0o022:
        raise PolicyRefused(f"kick_ledger_unsafe_permissions {oct(st.st_mode & 0o777)}")
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return fresh_kick_ledger()  # removed between lstat and read: first use
    except OSError as exc:
        raise PolicyRefused(f"kick_ledger_unreadable ({exc.strerror})") from exc
    try:
        ledger = json.loads(raw)
    except ValueError as exc:
        raise PolicyRefused("kick_ledger_corrupt (invalid JSON)") from exc
    if not isinstance(ledger, dict) or ledger.get("schema") != KICK_LEDGER_SCHEMA:
        raise PolicyRefused("kick_ledger_schema_unknown")
    seats = ledger.get("seats")
    if not isinstance(seats, dict):
        raise PolicyRefused("kick_ledger_seats_shape_invalid")
    for label, entry in seats.items():
        if not isinstance(label, str) or not isinstance(entry, dict):
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label!r}")
        last_kick_at = entry.get("last_kick_at")
        if last_kick_at is not None and (
            isinstance(last_kick_at, bool) or not isinstance(last_kick_at, (int, float))
        ):
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_kick_at")
        kicks = entry.get("consecutive_kicks", 0)
        if isinstance(kicks, bool) or not isinstance(kicks, int) or kicks < 0:
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: consecutive_kicks")
        witnessed = entry.get("fresh_heartbeat_witnessed_since_kick", False)
        if not isinstance(witnessed, bool):
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: witness flag")
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

    # Cooldown/escalation ledger. An untrusted EXISTING ledger fails closed:
    # the whole pass goes alert-only (recovery cannot be bounded without the
    # persisted history) and the ledger is NOT rewritten, so corrupt or
    # tampered state can never be silently reset to empty.
    try:
        ledger = load_kick_ledger(home)
    except PolicyRefused as refused:
        report.alerts.append(Alert("kick_ledger_refused_recovery_alert_only", "host", str(refused)))
        ledger = None
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
        elif pid is PID_STATE_UNKNOWN:
            # launchd state could not be QUALIFIED (unexpected print error):
            # never treated as a missing PID, never recovered, alert only.
            state, may_kick = ST_LAUNCHD_UNCERTAIN, False
        elif ledger is None:
            # Untrusted ledger: classification still reports, but no
            # recovery — kick history cannot bound the kickstart.
            state, may_kick = ST_LEDGER_REFUSED, False
        else:
            seat_entry = ledger["seats"].get(label) or {}
            state, may_kick = classify_seat(
                qualified=bool(heartbeat_path) and not rogue,
                pid=pid,
                heartbeat_age=heartbeat_age,
                heartbeat_path_recorded=bool(heartbeat_path),
                heartbeat_attested=heartbeat_attested,
                last_kick_at=seat_entry.get("last_kick_at"),
                consecutive_kicks=int(seat_entry.get("consecutive_kicks") or 0),
                fresh_heartbeat_witnessed_since_kick=bool(
                    seat_entry.get("fresh_heartbeat_witnessed_since_kick")
                ),
                now=now,
            )
        acted = False
        kick_forced = False
        if may_kick and recover and not rogue and ledger is not None:
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
        if state == ST_HEALTHY and ledger is not None:
            _witness_recovery(ledger, label)
        seats[label] = {
            "pid": None if isinstance(pid, _PIDStateUnknown) else pid,
            "heartbeat_age_seconds": None if heartbeat_age is None else int(heartbeat_age),
            "state": state,
            "heartbeat_attested": heartbeat_attested,
            "kickstarted": acted,
            "kickstarted_forced": kick_forced,
        }
        report.alerts.extend(
            alert for alert in _seat_alerts(state, label) if alert.code not in {a.code for a in report.alerts if a.label == label}
        )
    if ledger is not None:
        save_kick_ledger(home, ledger)
    report.seats = seats
    _finish(report, home, now)
    return report


def _seat_alerts(state: str, label: str) -> list[Alert]:
    if state == ST_HEARTBEAT_MISSING:
        return [Alert(ST_HEARTBEAT_MISSING, label)]
    if state == ST_ESCALATED:
        return [Alert(ST_ESCALATED, label, "repeated kicks without a fresh heartbeat")]
    if state == ST_LAUNCHD_UNCERTAIN:
        return [
            Alert(
                ST_LAUNCHD_UNCERTAIN,
                label,
                "launchctl print failed without the specific unloaded-job diagnostic; "
                "state is NOT proven missing — alert only, no recovery this pass",
            )
        ]
    if state == ST_LEDGER_REFUSED:
        return [
            Alert(
                ST_LEDGER_REFUSED,
                label,
                "cooldown/escalation ledger is corrupt, unreadable, symlinked, or unsafe; "
                "existing history is preserved and NO recovery is performed until a human "
                "resolves the ledger (never auto-reset)",
            )
        ]
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


def _watchdog_target_path(home: Path, name: str) -> Path:
    """Absolute path of one watchdog target by its qualified target name.

    Module names are bare filenames inside the private watchdog dir; the
    plist target is named by its home-relative relpath (contains a ``/``)."""
    if "/" in name:
        return home / name
    return watchdog_dir(home) / name


def _rollback_watchdog_install(
    home: Path,
    runner: Any,
    *,
    uid: int,
    attempt_backups: Mapping[str, Path],
    mismatch_names: frozenset[str] = frozenset(),
    plist_mutated: bool = False,
) -> list[Alert]:
    """Restore EXACTLY the targets changed by the CURRENT attempt — bytes and
    mode when the target existed, absence when it did not — using THIS
    attempt's sidecars, never the newest sidecar of some earlier generation.

    Every restore is CAS-guarded against the recorded post digest of this
    attempt before any bytes are touched:
    - current == this attempt's post digest  -> restore preimage (or unlink);
    - current == the preimage already (write faulted before rename) ->
      nothing to do, target left untouched;
    - anything else is drift after our write -> for targets this attempt's
      own readback never verified (``mismatch_names`` — our known-wrong
      write is the certain last writer) the preimage is restored; for every
      other target the drift is treated as EXTERNAL, the intervening bytes
      are preserved, and a stable alert names the refusal.

    launchd is only reloaded (bootout; bootstrap only a restored pre-existing
    plist) when this attempt actually mutated the PLIST on disk, so a fault
    during an earlier module write never starts or stops any job, and the
    loaded job is never left inconsistent with untouched disk. Targets with
    no backup from this attempt (byte-identical, never touched) are left
    completely alone."""
    from fabric_tunnel_install import _bootout_if_loaded, _bootstrap

    alerts: list[Alert] = []
    plist_name = plist_relpath(WATCHDOG_LABEL)
    plist_pre_existed: bool | None = None
    for name, sidecar in attempt_backups.items():
        target = _watchdog_target_path(home, name)
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            alerts.append(Alert("watchdog_rollback_sidecar_unreadable", name, str(exc.__class__.__name__), acted=True))
            continue
        if payload.get("schema") != WATCHDOG_BACKUP_SCHEMA:
            alerts.append(Alert("watchdog_rollback_schema_unknown", name, acted=True))
            continue
        post_digest = payload.get("post_sha256")
        pre_existed = bool(payload.get("pre_existed"))
        if name == plist_name:
            plist_pre_existed = pre_existed
        try:
            current_raw = target.read_bytes()
        except FileNotFoundError:
            current_raw = None  # write faulted before rename, or already absent
        except OSError as exc:
            alerts.append(Alert("watchdog_rollback_target_unreadable", name, str(exc.strerror), acted=True))
            continue
        drifted = current_raw is not None and sha256_bytes(current_raw) != post_digest
        if drifted and name not in mismatch_names:
            if pre_existed and sha256_bytes(current_raw) == payload.get("pre_sha256"):
                continue  # never actually mutated: preimage already in place
            # External writer moved the target after our verified write:
            # intervening bytes win; rollback refuses to clobber them.
            alerts.append(Alert("watchdog_rollback_cas_refused_external_drift", name, acted=True))
            continue
        if not pre_existed:
            if current_raw is not None:
                try:
                    target.unlink()
                except OSError as exc:
                    alerts.append(Alert("watchdog_rollback_unlink_failed", name, str(exc.strerror), acted=True))
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
        restored_file_mode = 0o644 if name.endswith(".plist") else 0o600
        mode = int(payload.get("mode") or restored_file_mode)
        try:
            atomic_write_bytes(target, pre_raw, mode)
            if target.read_bytes() != pre_raw:
                alerts.append(Alert("watchdog_rollback_readback_mismatch", name, acted=True))
        except OSError as exc:
            alerts.append(Alert("watchdog_rollback_restore_failed", name, str(exc.strerror), acted=True))
    if plist_mutated and plist_name in attempt_backups:
        try:
            _bootout_if_loaded(runner, uid, WATCHDOG_LABEL)
            if plist_pre_existed:
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

    Upgrade/overwrite safety (B3, tightened): every target about to CHANGE
    (the four copied modules and the watchdog plist) is captured as an exact
    private preimage backup BEFORE any edit, tracked as THIS attempt's
    backup; a target that is already byte-identical is left untouched
    (idempotent readback, no backup churn, and rollback never resurrects a
    stale earlier generation into it); a symlinked or unsafe target refuses
    instead of being overwritten; the LEXICAL ancestor chains of both write
    roots are re-bound symlink-free at install time; every write is verified
    by read-back digest; and ANY fault — post-write mismatch, write or chmod
    exception, or launchd failure — rolls ALL targets changed by this
    attempt back to their exact preimage (or absence) under CAS against this
    attempt's post digests (external drift after our write is preserved, not
    clobbered), reloads launchd only when the plist itself changed, then
    raises. Requires a fresh manifest: watchdog install is an install-time
    mutation and keeps the strict freshness contract."""
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
    # Bind directory identity across the writes: both lexical ancestor
    # chains (LaunchAgents plist and private watchdog module dir) must be
    # symlink-free NOW, not merely at qualification time.
    try:
        require_parent_safe(home / plist_relpath(WATCHDOG_LABEL), os.getuid(), code="watchdog_plist_parent_unsafe")
        require_parent_safe(target_dir / "x", os.getuid(), code="watchdog_dir_parent_unsafe")
    except IdentityRejected as rejected:
        raise PolicyRefused(str(rejected)) from rejected
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
    plist_install_file_mode = 0o644
    targets: list[tuple[str, Path, bytes, int]] = [
        (name, target_dir / name, module_raws[name], 0o600)
        for name in _WATCHDOG_MODULE_FILES
    ] + [(plist_relpath(WATCHDOG_LABEL), plist_path, plist_raw, plist_install_file_mode)]

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
    # CHANGE get a backup; identical targets are skipped entirely. The
    # sidecar of EACH backup is remembered as THIS attempt's rollback source
    # — rollback must never fall back to a stale earlier generation's
    # sidecar for a target this attempt never touched.
    attempt_backups: dict[str, Path] = {}
    for name, _dest, raw, _mode in targets:
        if preimages[name][0] == raw:
            continue
        attempt_backups[name] = _backup_watchdog_target(
            home, name, preimages[name][0], preimages[name][1], raw, now
        )

    uid = os.getuid()
    mismatched: list[str] = []
    plist_mutated = False
    try:
        # Apply only changed targets, atomically, with read-back CAS. ANY
        # fault here — a write/chmod exception, or a read-back mismatch —
        # rolls back every target this attempt changed before raising.
        for name, dest, raw, mode in targets:
            if preimages[name][0] == raw:
                continue
            atomic_write_bytes(dest, raw, mode)
            if name == plist_relpath(WATCHDOG_LABEL):
                plist_mutated = True  # the rename landed: launchd was not yet touched
            os.chmod(dest, mode)
            if dest.read_bytes() != raw:
                mismatched.append(name)
                raise ActionRefused(f"post_write_mismatch name={name}")
    except ActionRefused as exc:
        alerts = _rollback_watchdog_install(
            home, runner, uid=uid, attempt_backups=attempt_backups,
            mismatch_names=frozenset(mismatched), plist_mutated=plist_mutated,
        )
        raise ActionRefused(
            f"watchdog_install_post_write_mismatch_rolled_back alerts={[a.code for a in alerts]} cause={exc}"
        ) from exc
    except OSError as exc:
        alerts = _rollback_watchdog_install(
            home, runner, uid=uid, attempt_backups=attempt_backups,
            mismatch_names=frozenset(mismatched), plist_mutated=plist_mutated,
        )
        raise ActionRefused(
            f"watchdog_install_write_fault_rolled_back alerts={[a.code for a in alerts]} cause={exc}"
        ) from exc

    try:
        _bootout_if_loaded(runner, uid, WATCHDOG_LABEL)
        _bootstrap(runner, uid, plist_path)
    except ActionRefused as exc:
        alerts = _rollback_watchdog_install(home, runner, uid=uid, attempt_backups=attempt_backups)
        raise ActionRefused(
            f"watchdog_install_bootstrap_failed_rolled_back alerts={[a.code for a in alerts]} cause={exc}"
        ) from exc
    return str(plist_path)


# ---------------------------------------------------------------------------
# Watchdog readback. The operator-facing counterpart of install: a read-only
# verification that the installed watchdog is exactly the shape this
# integration owns. Fail closed: any absence or mismatch raises, never
# degrades to a warning.
# ---------------------------------------------------------------------------


def verify_watchdog_install(home: Path) -> list[str]:
    """Read-only readback of the installed watchdog agent (no launchd calls).

    Verifies, on the live filesystem: the watchdog plist exists as a regular
    non-symlink file, parses, carries THIS integration's label and the
    bounded periodic shape (RunAtLoad, StartInterval, ThrottleInterval>=10,
    NO KeepAlive), references the private watchdog module and a ``pass``
    invocation, and that all four private module copies exist as regular
    0600 files. Any absence or mismatch raises :class:`PolicyRefused` with a
    stable code. stdout-safe: evidence lines carry digests and modes, never
    argv bodies or environment values."""
    home = Path(home)
    plist_path = home / plist_relpath(WATCHDOG_LABEL)
    require_regular_file(plist_path, code="watchdog_plist_unavailable")
    plist_doc = parse_plist_bytes(plist_path.read_bytes(), code="watchdog_plist_invalid")
    problems: list[str] = []
    if plist_doc.get("Label") != WATCHDOG_LABEL:
        problems.append("label_mismatch")
    if plist_doc.get("RunAtLoad") is not True:
        problems.append("run_at_load_not_true")
    if "KeepAlive" in plist_doc:
        problems.append("keep_alive_present_periodic_job_must_not_loop")
    if plist_doc.get("StartInterval") != WATCHDOG_START_INTERVAL_SECONDS:
        problems.append("start_interval_mismatch")
    throttle = plist_doc.get("ThrottleInterval")
    if not isinstance(throttle, int) or isinstance(throttle, bool) or throttle < 10:
        problems.append("throttle_below_10")
    argv = plist_doc.get("ProgramArguments")
    if not isinstance(argv, list) or len(argv) < 4:
        problems.append("argv_shape_invalid")
    elif not all(isinstance(element, str) for element in argv):
        problems.append("argv_element_invalid")
    else:
        if not any(element.endswith("fabric_tunnel_health.py") for element in argv):
            problems.append("argv_not_our_module")
        if "pass" not in argv:
            problems.append("argv_not_bounded_pass")
    if problems:
        raise PolicyRefused(f"watchdog_plist_not_ours ({','.join(problems)})")
    module_dir = watchdog_dir(home)
    for name in _WATCHDOG_MODULE_FILES:
        module_path = module_dir / name
        require_regular_file(module_path, code=f"watchdog_module_unavailable: {name}")
        mode = stat.S_IMODE(module_path.lstat().st_mode)
        if mode != 0o600:
            raise PolicyRefused(f"watchdog_module_mode_unsafe: {name} {oct(mode)}")
    return [
        evidence_line(
            WATCHDOG_LABEL,
            {
                "installed": True,
                "plist_sha256": sha256_bytes(plist_path.read_bytes())[:16],
                "plist_mode": oct(stat.S_IMODE(plist_path.lstat().st_mode)),
                "modules_present": len(_WATCHDOG_MODULE_FILES),
                "start_interval": plist_doc.get("StartInterval"),
            },
        )
    ]


# ---------------------------------------------------------------------------
# CLI. Subcommands: pass (health loop), last-pass (read-only report print),
# watchdog-install / watchdog-verify (the sanctioned operator entrypoints for
# the watchdog LaunchAgent). No secrets are ever printed; reports contain no
# argv bodies.
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
    install_cmd = sub.add_parser("watchdog-install")
    install_cmd.add_argument("--home", default=os.path.expanduser("~"))
    install_cmd.add_argument("--confirm", action="store_true")
    install_cmd.add_argument("--now", type=float, default=None)
    verify_cmd = sub.add_parser("watchdog-verify")
    verify_cmd.add_argument("--home", default=os.path.expanduser("~"))
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
    if args.command == "watchdog-verify":
        try:
            for line in verify_watchdog_install(home):
                print(line)
        except (PolicyRefused, IdentityRejected) as refused:
            print(f"REFUSED {refused.__class__.__name__}: {refused}", file=os.sys.stderr)
            return 4
        return 0
    if args.command == "watchdog-install":
        try:
            now = args.now if args.now is not None else time.time()
            plist_path = install_watchdog_agent(home, subprocess_runner, confirm=args.confirm, now=now)
        except (PolicyRefused, ActionRefused, IdentityRejected) as refused:
            print(f"REFUSED {refused.__class__.__name__}: {refused}", file=os.sys.stderr)
            return 3
        print(evidence_line("watchdog-install", {"plist": plist_path, "installed": True}))
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
        ST_LAUNCHD_UNCERTAIN,
        ST_LEDGER_REFUSED,
        "manifest_stale_revalidated",
        "seat_identity_tampered_alert_only",
        "seat_identity_rejected",
        TELEMETRY_STALE,
    }
    if any(alert.code in blocking for alert in report.alerts):
        return 4
    return 0

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
- A stale heartbeat only triggers a forced restart when the seat's evidence
  is the strictly typed first-party control-plane poll AND the operator
  qualified that seat with an explicit first-party kind and proof note. The
  legacy file mtime is DIAGNOSTIC ONLY: it can never establish health, never
  reset the attempt ladder, and never authorize a stale forced restart — not
  even with a full ``heartbeat_kind`` + ``heartbeat_proof_note``
  attestation, because an operator-correlated mtime is not first-party
  control-plane evidence. Its outcome is
  ``stale_heartbeat_unproven_alert_only`` stating the exact required host
  proof. (Missing-PID recovery is unaffected: it is proven by launchd
  itself, not by any heartbeat file.)

First-party CLI control-plane-poll mode (strictly typed): a seat qualified
with ``heartbeat_mode=first_party_cli_control_plane_poll`` gets its real
last-seen from the seat's OWN qualified tunnel-client binary — each pass
re-proves the pinned executable digest and the qualified profile/locator
paths, then invokes the EXACT read-only argv
``<pinned executable> health --url-file <pinned locator>
--require-control-plane-poll --json`` through the injectable bounded runner
(no shell, per-seat deadline, both output streams hard-capped). Only the
known-good rc0/ok/ok/ok shape with a finite positive Unix-seconds
``control_plane_poll.value`` is evidence; age is ``now - value``. Any other
payload — malformed, missing, oversized, false-flagged, non-positive,
future-beyond-skew, nonzero rc, timeout, drifted executable, changed
locator — is ``control_plane_poll_unproven_alert_only``: fail closed, never
a kick, and no URL, profile path, locator, or payload content is ever
printed. A stale verdict whose (value, stdout digest) is byte-identical to
the provenance recorded at the seat's last evidence-authorized kick is
REPLAYED consumed evidence: ``control_plane_poll_replayed_alert_only``, no
kick and no freshness witness. Recovery bounds (1800 s cooldown, 3-kick
escalation, no fourth kick) are identical to the file-mtime mode.
"""
from __future__ import annotations

import fcntl
import json
import math
import os
import re
import shutil
import stat
import time
from pathlib import Path
from typing import Any, Mapping

from fabric_tunnel_common import (
    CLI_POLL_FUTURE_SKEW_SECONDS,
    CLI_POLL_TIMEOUT_SECONDS,
    DEFAULT_STALE_TELEMETRY_SECONDS,
    FORBIDDEN_LABELS,
    HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL,
    HEARTBEAT_MODE_FILE_MTIME,
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
    DurabilityUnproven,
    IdentityRejected,
    PassReport,
    PolicyRefused,
    atomic_write_bytes,
    atomic_write_bytes_durable,
    backups_dir,
    build_control_plane_poll_argv,
    control_plane_poll_runner,
    evidence_line,
    kick_ledger_lock_path,
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
    validate_control_plane_poll_payload,
    verified_file_identity,
    watchdog_dir,
)
from fabric_tunnel_identity import (
    load_manifest,
    manifest_is_stale,
    revalidate_stale_identity,
    scan_family,
    seat_identity_drift_problems,
    telemetry_relative_path_reject_reason,
    unqualified_health_alerts,
    verified_poll_profile_binding,
)

# Health states, one per distinguishable outcome the plan names.
ST_HEALTHY = "healthy"
ST_MISSING_PID = "missing_pid"
ST_STALE_HEARTBEAT = "stale_heartbeat"
ST_STALE_HEARTBEAT_UNPROVEN = "stale_heartbeat_unproven_alert_only"
ST_HEARTBEAT_UNQUALIFIED = "heartbeat_unqualified"
ST_HEARTBEAT_MISSING = "heartbeat_missing"
ST_CLI_POLL_UNPROVEN = "control_plane_poll_unproven_alert_only"
ST_POLL_EVIDENCE_REPLAYED = "control_plane_poll_replayed_alert_only"
ST_UNQUALIFIED = "unqualified"
ST_COOLDOWN = "kickstart_suppressed_cooldown"
ST_ESCALATED = "kickstart_escalated_alert"
ST_IDENTITY_SUSPECT = "identity_suspect_alert_only"
ST_LAUNCHD_UNCERTAIN = "launchd_state_uncertain_alert_only"
ST_LEDGER_REFUSED = "kick_ledger_refused_alert_only"
# An unresolved effect on the seat: the action was invoked (or refused
# pre-spawn) and its outcome is not settled, so NOTHING may be retried for
# this seat until the original owner reconciles the ledger explicitly.
# An ACKNOWLEDGED outcome is held the same way: it is released only by a
# bound, strictly newer first-party recovery proof.
ST_PENDING_EFFECT = "pending_effect_held_alert_only"
# The legacy file-mtime heartbeat is DIAGNOSTIC ONLY: it can never establish
# health, never reset the attempt ladder, and never authorize a restart.
ST_MTIME_DIAGNOSTIC = "heartbeat_mtime_diagnostic_only"
# A pre-effect reservation could not be proven durable -> the effect was
# refused (it never ran) and the pass stopped writing.
ST_LEDGER_RESERVATION_FAILED = "kick_ledger_reservation_failed_alert_only"
# A settlement could not be proven durable -> the on-disk state is uncertain,
# the pass stopped writing and performing, and the CLI exits nonzero.
ST_LEDGER_SETTLEMENT_FAILED = "kick_ledger_settlement_failed"

# Pending-reservation states. Every one of them BLOCKS the seat: an
# unresolved effect is never retried automatically, not after a cooldown, and
# not because a healthy observation arrived.
PENDING_RESERVED = "reserved"          # invoked (or about to be), outcome unknown
# The command was ACKNOWLEDGED (rc 0). That is NOT a recovery witness and NOT
# a release: the reservation is RETAINED in the same ledger and keeps
# holding the seat until a bound, strictly newer first-party recovery proof
# releases it (see _recovery_release_admits).
PENDING_ACKNOWLEDGED = "acknowledged_awaiting_recovery"
PENDING_AMBIGUOUS = "ambiguous"        # nonzero/signal/timeout/OSError/interrupt
PENDING_NOT_APPLIED = "not_applied_held"  # proved NOT applied, still held
_PENDING_STATES: frozenset[str] = frozenset({
    PENDING_RESERVED,
    PENDING_ACKNOWLEDGED,
    PENDING_AMBIGUOUS,
    PENDING_NOT_APPLIED,
})
# The trigger that authorized the reservation. Bound into the record so a
# tampered or half-written pending row can never pass validation.
_PENDING_TRIGGERS: frozenset[str] = frozenset({"missing_pid", "stale_heartbeat"})

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


def operator_heartbeat_attested(kind: Any, note: Any) -> bool:
    """B6 attestation is POSITIVE operator-correlated evidence: BOTH the
    manifest's ``heartbeat_kind`` AND its ``heartbeat_proof_note`` must be
    present, string-typed, and non-blank. Kind-only, note-only, or a
    blank/whitespace note is NOT attestation — a tampered private manifest
    must never mint the proof switch that authorizes a stale forced kick
    from a half-written fact. This mirrors the qualification-time closed
    facts schema (``facts_heartbeat_kind_required`` /
    ``facts_heartbeat_proof_note_required``), re-checked at classification
    time so a hand-edited manifest cannot downgrade to kind-only.

    Review finding: heartbeat attestation based only on ``heartbeat_kind``
    (LOW, require both facts)."""
    return (
        isinstance(kind, str) and bool(kind.strip())
        and isinstance(note, str) and bool(note.strip())
    )


def classify_seat(
    *,
    qualified: bool,
    pid: int | None,
    heartbeat_age: float | None,
    heartbeat_path_recorded: bool,
    heartbeat_kind: Any = "",
    heartbeat_proof_note: Any = "",
    last_kick_at: float | None,
    consecutive_kicks: int,
    fresh_heartbeat_witnessed_since_kick: bool,
    now: float,
    heartbeat_mode: str = HEARTBEAT_MODE_FILE_MTIME,
    poll_refused_code: str | None = None,
    poll_replayed: bool = False,
    pending_effect: bool = False,
) -> tuple[str, bool]:
    """Return (state, may_kickstart).

    ``may_kickstart`` is True only for the two qualified recovery states and
    only when the persisted cooldown and escalation ledger allow it.

    The persisted escalation limit binds BOTH recovery routes identically
    (missing-PID and stale-heartbeat): after ``KICKSTART_ESCALATION_LIMIT``
    consumed attempts without a witnessed fresh heartbeat, the seat is
    ESCALATED — alert-only — even once the cooldown has elapsed, and no
    fourth attempt may occur until a fresh heartbeat is witnessed (the seat
    classified ``healthy``), which resets the persisted counter. Without
    this gate the missing-PID route could kick every cooldown forever.

    ``pending_effect`` is the durable PRE-EFFECT reservation state. While a
    reservation is unresolved the seat is held (``pending_effect_held``):
    no attempt may be made, whatever the cooldown says, and a healthy
    observation elsewhere can never erase it.

    LEGACY FILE MTIME IS DIAGNOSTIC ONLY (``heartbeat_mode`` ==
    ``file_mtime_attested``): the mtime of an arbitrary file can never
    establish HEALTHY, never reset the attempt ladder, and never authorize a
    stale-heartbeat forced restart — NOT EVEN with a full operator
    attestation (``heartbeat_kind`` + ``heartbeat_proof_note``). The
    attestation only proves that an operator once correlated the file; it
    does not turn an mtime into first-party control-plane evidence. Health
    and every heartbeat-derived action therefore come from the strictly
    typed ``first_party_cli_control_plane_poll`` mode. The independently
    qualified MISSING-PID recovery is unaffected: launchd itself proves that
    state, so it stays recoverable under the same identity and policy
    guards.

    ``heartbeat_attested`` remains the B6 first-party proof switch for the
    CLI-poll mode's forced restart: it is True ONLY when BOTH the
    operator-qualified ``heartbeat_kind`` and its ``heartbeat_proof_note``
    are present and non-blank in the manifest facts passed in
    (:func:`operator_heartbeat_attested`); kind-only or a blank note is
    never attestation.

    ``heartbeat_path_recorded`` is the qualified-evidence gate for EITHER
    mode: the file-mtime mode records a heartbeat path, the
    ``first_party_cli_control_plane_poll`` mode records the profile and its
    derived URL locator. For the CLI-poll mode, ``poll_refused_code`` (any
    per-pass evidence refusal) and ``poll_replayed`` (identical evidence to
    the last kick's recorded provenance) both fail closed to alert-only
    states BEFORE any staleness decision: replayed consumed evidence never
    authorizes a kick and never witnesses freshness, and an unproven poll is
    never guessed into either direction.
    """
    if not qualified or not heartbeat_path_recorded:
        return ST_UNQUALIFIED, False
    if pending_effect:
        return ST_PENDING_EFFECT, False
    heartbeat_attested = operator_heartbeat_attested(heartbeat_kind, heartbeat_proof_note)
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
    if heartbeat_mode == HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL:
        # CLI-poll evidence must be PROVEN this pass: any ambiguity or
        # replayed consumed evidence fails closed before any staleness
        # decision, never guessed into either direction.
        if poll_refused_code is not None:
            return ST_CLI_POLL_UNPROVEN, False
        if poll_replayed:
            return ST_POLL_EVIDENCE_REPLAYED, False
    if heartbeat_age is None:
        return ST_HEARTBEAT_MISSING, False
    if heartbeat_mode == HEARTBEAT_MODE_FILE_MTIME:
        # Diagnostic only. A stale mtime is reported as UNPROVEN (the file
        # mtime never proves a wedged client); a fresh mtime is reported as
        # a diagnostic observation, never as HEALTHY. Neither authorizes an
        # action, and neither resets the attempt ladder.
        if heartbeat_age > STALE_HEARTBEAT_SECONDS:
            return ST_STALE_HEARTBEAT_UNPROVEN, False
        return ST_MTIME_DIAGNOSTIC, False
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


# Stable 64-hex shape for ledger-recorded poll provenance digests.
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def cli_poll_evidence(
    label: str,
    entry: Mapping[str, Any],
    seat_uid: int,
    poll_runner: Any,
    *,
    now: float,
    home: Path,
    manifest: Mapping[str, Any],
) -> tuple[float | None, str | None, float | None, str | None]:
    """One bounded first-party CLI control-plane poll for one seat.

    Returns ``(age_seconds, refusal_code, accepted_value, stdout_digest)``.
    ``age_seconds`` is non-None ONLY for a fully accepted payload; every
    other outcome carries a stable ``refusal_code`` and authorizes nothing.

    Per-pass re-proof before the child is ever executed (all fail closed):
    - the executable is the manifest-PINNED path and still digests to the
      pinned value, read from ONE nofollow descriptor so the digest and the
      pinned dev/ino/owner/mode describe the SAME inode observation — an
      arbitrary, drifted, or in-place-replaced binary is never invoked;
    - the profile binding (``verified_poll_profile_binding``) re-proves
      bounded size, seat ownership, safe modes, non-hardlinked uniqueness,
      symlink-free lexical ancestors, the parsed ``health.url_file`` STILL
      equaling the pinned locator, and — on seats whose manifest pins the
      full binding (shared-executable seats) — the pinned profile/locator
      inode+digest identity and the pinned domain-separated tunnel-id digest;
      a swapped, rewritten, re-linked, or re-tunnelled profile refuses
      instead of steering the probe;
    - IMMEDIATELY before the spawn, the seat's ENTIRE pinned identity is
      re-proved from the LIVE filesystem against the qualified manifest via
      :func:`fabric_tunnel_identity.seat_identity_drift_problems` — the
      installed plist argv, the executable path/digest and pinned
      dev/ino/owner/mode, the pinned parent-directory identity, the pinned
      Homebrew Cellar-allowance identity, and the full pinned
      profile/locator/tunnel-id binding. This closes the gap where the
      per-field checks above each proved one pin while the executable's
      PARENT or Cellar ancestor had drifted (the poll path is exercised far
      more often than a kickstart, so it must re-prove at the same
      strength). Any drift, and any exception while re-proving, refuses
      with a stable secret-free code and NO probe runs — a poll refused
      here is an unproven poll, so no kick can be authorized from it.
      This narrows but does NOT close the group-member path-rename race
      between re-proof and spawn (the reviewer HIGH residual, HOLD_SECURITY).
    - the probe itself is the EXACT read-only argv through the injectable
      bounded runner: no shell, per-seat deadline, capped output streams.

    Refusal codes carry no URL, profile path, locator, or payload content.
    """
    executable = entry.get("executable")
    profile = entry.get("heartbeat_profile_file")
    locator = entry.get("heartbeat_url_locator")
    if not executable or not profile or not locator:
        return None, "heartbeat_poll_evidence_unqualified", None, None
    executable_path = Path(str(executable))
    try:
        require_regular_file(executable_path, code="cli_poll_executable")
        exec_identity = verified_file_identity(
            executable_path, seat_uid, code="cli_poll_executable"
        )
    except (IdentityRejected, OSError):
        return None, "cli_poll_executable_drift", None, None
    if exec_identity.sha256 != entry.get("executable_sha256"):
        return None, "cli_poll_executable_digest_changed", None, None
    if entry.get("executable_ino") is not None and (
        exec_identity.dev,
        exec_identity.ino,
    ) != (int(entry.get("executable_dev") or 0), int(entry["executable_ino"])):
        return None, "cli_poll_executable_identity_changed", None, None
    if entry.get("executable_owner_uid") is not None and (
        exec_identity.uid != int(entry["executable_owner_uid"])
    ):
        return None, "cli_poll_executable_identity_changed", None, None
    if entry.get("executable_mode") is not None and (
        exec_identity.mode != int(entry["executable_mode"])
    ):
        return None, "cli_poll_executable_identity_changed", None, None
    pinned_profile = entry.get("poll_profile")
    required_tunnel = bool(isinstance(pinned_profile, dict) and pinned_profile.get("tunnel_id_hash"))
    try:
        binding = verified_poll_profile_binding(
            label, str(profile), seat_uid, require_tunnel_id=required_tunnel
        )
    except (PolicyRefused, IdentityRejected):
        return None, "cli_poll_profile_unsafe", None, None
    if binding.locator != locator:
        return None, "cli_poll_profile_locator_changed", None, None
    if isinstance(pinned_profile, dict):
        if (
            binding.profile_path != pinned_profile.get("path")
            or (binding.profile_dev, binding.profile_ino)
            != (int(pinned_profile.get("dev") or 0), int(pinned_profile.get("ino") or 0))
            or binding.profile_sha256 != pinned_profile.get("sha256")
        ):
            return None, "cli_poll_profile_identity_changed", None, None
        if (
            (binding.locator_dev, binding.locator_ino)
            != (int(pinned_profile.get("locator_dev") or 0), int(pinned_profile.get("locator_ino") or 0))
            or binding.locator_sha256 != pinned_profile.get("locator_sha256")
        ):
            return None, "cli_poll_locator_identity_changed", None, None
        if required_tunnel and binding.tunnel_id_hash != pinned_profile.get("tunnel_id_hash"):
            return None, "cli_poll_profile_tunnel_id_changed", None, None
    try:
        argv = build_control_plane_poll_argv(str(executable), str(locator))
    except ActionRefused:
        return None, "cli_poll_argv_refused", None, None
    # Full-engine identity re-proof as the LAST observation before the ONLY
    # path-based Popen in this function. The per-field checks above each
    # compare one pinned value; this re-proves the whole pinned identity
    # (plist argv, executable path/digest/dev/ino/uid/mode, parent and
    # Cellar-allowance pins, profile/locator/tunnel-id binding) from the
    # live filesystem, the same engine that guards every kickstart.
    # Fail closed: drift refuses with a fixed secret-free code, and any
    # exception during re-proof (I/O error, time-of-check failure) refuses
    # identically — an exception is never guessed into "safe".
    try:
        drift = seat_identity_drift_problems(home, manifest, label)
    except Exception:
        return None, "cli_poll_identity_reproof_failed", None, None
    if drift:
        return None, "cli_poll_identity_drift", None, None
    try:
        result = poll_runner(argv, CLI_POLL_TIMEOUT_SECONDS)
    except (ActionRefused, OSError):
        return None, "cli_poll_spawn_refused", None, None
    verdict = validate_control_plane_poll_payload(
        result.stdout,
        result.stderr,
        result.returncode,
        now=now,
        timed_out=result.timed_out,
        truncated=result.truncated,
    )
    if not verdict.ok:
        return None, verdict.reason, None, None
    digest = sha256_bytes(result.stdout.encode("utf-8"))
    return verdict.age_seconds, None, verdict.value, digest


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


# The ledger file is opened NOFOLLOW and the opened inode is compared with
# the lstat result: a symlink or a swapped-in file can never be read as the
# ledger.
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def load_kick_ledger(home: Path) -> dict[str, Any]:
    """Load the persisted cooldown/escalation ledger, FAILING CLOSED.

    Distinguishing absent first-use from untrusted existing state is a
    safety contract: cooldown and escalation history is what bounds
    kickstarts, so a corrupt, unreadable, symlinked, non-regular, or
    permission-unsafe EXISTING ledger is never silently reset to empty
    (that would erase escalation and re-enable unbounded restarts). Every
    uncertain state raises :class:`PolicyRefused` with a stable code; the
    pass that hits one goes alert-only for ALL recovery instead of
    guessing. Only a genuinely absent file (first use) initializes.

    Two further fail-closed rules close the "empty ledger" escape hatch:

    - An EXISTING ledger that DISAPPEARS between the lstat and the read is
      NOT an empty ledger and NOT first use: it raises, because "the file I
      was going to bound this pass with vanished" is exactly the state in
      which a stale or wiped history must not be assumed away.
    - Every persisted number is validated as FINITE and NON-NEGATIVE. A NaN
      or infinite ``last_kick_at`` used to slip through and then defeated
      the cooldown comparison (``now - NaN < 1800`` is False), which is a
      fail-OPEN. Malformed counters and records raise instead of resetting.
    """
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
        fd = os.open(path, os.O_RDONLY | _CLOEXEC | _NOFOLLOW)
    except FileNotFoundError:
        # The ledger EXISTED at lstat and vanished before the read: this is
        # NOT an empty ledger and never a fresh start.
        raise PolicyRefused("kick_ledger_disappeared") from None
    except OSError as exc:
        raise PolicyRefused(f"kick_ledger_unreadable ({exc.strerror})") from exc
    try:
        fst = os.fstat(fd)
        if fst.st_dev != st.st_dev or fst.st_ino != st.st_ino:
            raise PolicyRefused("kick_ledger_replaced")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw_bytes = b"".join(chunks)
    except FileNotFoundError:
        raise PolicyRefused("kick_ledger_disappeared") from None
    except OSError as exc:
        raise PolicyRefused(f"kick_ledger_unreadable ({exc.strerror})") from exc
    finally:
        os.close(fd)
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyRefused("kick_ledger_corrupt (not UTF-8)") from exc
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
            isinstance(last_kick_at, bool)
            or not isinstance(last_kick_at, (int, float))
            or not math.isfinite(last_kick_at)
            or last_kick_at < 0
        ):
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_kick_at")
        kicks = entry.get("consecutive_kicks", 0)
        if isinstance(kicks, bool) or not isinstance(kicks, int) or kicks < 0:
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: consecutive_kicks")
        witnessed = entry.get("fresh_heartbeat_witnessed_since_kick", False)
        if not isinstance(witnessed, bool):
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: witness flag")
        # First-party CLI-poll provenance recorded at the last evidence-
        # authorized kick (absent for file-mtime kicks and legacy ledgers).
        kick_poll_value = entry.get("last_kick_poll_value")
        if kick_poll_value is not None and (
            isinstance(kick_poll_value, bool)
            or not isinstance(kick_poll_value, (int, float))
            or not math.isfinite(kick_poll_value)
            or kick_poll_value <= 0
        ):
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_kick_poll_value")
        kick_poll_digest = entry.get("last_kick_poll_digest")
        if kick_poll_digest is not None and (
            not isinstance(kick_poll_digest, str) or not _HEX64_RE.match(kick_poll_digest)
        ):
            raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_kick_poll_digest")
        _validate_pending_record(label, entry)
        _validate_recovery_record(label, entry)
    return ledger


def _validate_pending_record(label: str, entry: Mapping[str, Any]) -> None:
    """Validate one pending pre-effect reservation, fail closed.

    A pending record is only meaningful when it BINDS to the row it
    belongs to: the reservation timestamp must be the row's ``last_kick_at``
    and the reservation attempt must be the row's ``consecutive_kicks``. A
    record that does not bind is a tampered or half-written ledger, and it
    is refused rather than interpreted. The ``forced`` flag and the
    ``trigger`` are validated too, so a reservation can never be replayed
    with a different authorization."""
    pending = entry.get("pending")
    if pending is None:
        return
    if not isinstance(pending, dict):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending shape")
    state = pending.get("state")
    if not isinstance(state, str) or state not in _PENDING_STATES:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending state")
    if pending.get("label") != label:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending label")
    reserved_at = pending.get("reserved_at")
    if (
        isinstance(reserved_at, bool)
        or not isinstance(reserved_at, (int, float))
        or not math.isfinite(reserved_at)
        or reserved_at < 0
    ):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending reserved_at")
    attempt = pending.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending attempt")
    trigger = pending.get("trigger")
    if not isinstance(trigger, str) or trigger not in _PENDING_TRIGGERS:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending trigger")
    if not isinstance(pending.get("forced"), bool):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending forced")
    if not isinstance(pending.get("reason"), str):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending reason")
    # The pre-attempt first-party poll provenance bound to THIS
    # reservation: a later recovery proof has to strictly advance it.
    poll_value = pending.get("poll_value")
    if poll_value is not None and (
        isinstance(poll_value, bool)
        or not isinstance(poll_value, (int, float))
        or not math.isfinite(poll_value)
        or poll_value <= 0
    ):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending poll_value")
    poll_digest = pending.get("poll_digest")
    if poll_digest is not None and (
        not isinstance(poll_digest, str) or not _HEX64_RE.match(poll_digest)
    ):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending poll_digest")
    # The binding: the reservation must name THIS row's timestamp and count.
    if reserved_at != entry.get("last_kick_at"):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending timestamp binding")
    if attempt != entry.get("consecutive_kicks"):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending count binding")


def _validate_recovery_record(label: str, entry: Mapping[str, Any]) -> None:
    """Validate the recorded first-party recovery proof, fail closed.

    The recovery proof is the ONLY in-band evidence that may release an
    acknowledged reservation, so its timestamps are validated in STRICT
    ORDER: the recovery poll must be strictly later than the reservation it
    releases, and the release itself must not predate that reservation.
    The proof must ALSO have been fresh AT THAT RELEASE: its age is
    measured against the record's own ``at``, never against the current
    wallclock, so a legitimate historical proof never expires while a proof
    that was already stale when it was written is refused rather than
    interpreted."""
    record = entry.get("last_recovery")
    if record is None:
        return
    if not isinstance(record, dict):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_recovery shape")
    at = record.get("at")
    if (
        isinstance(at, bool)
        or not isinstance(at, (int, float))
        or not math.isfinite(at)
        or at < 0
    ):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_recovery at")
    reserved_at = record.get("reserved_at")
    if (
        isinstance(reserved_at, bool)
        or not isinstance(reserved_at, (int, float))
        or not math.isfinite(reserved_at)
        or reserved_at < 0
    ):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_recovery reserved_at")
    attempt = record.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_recovery attempt")
    poll_value = record.get("poll_value")
    if (
        isinstance(poll_value, bool)
        or not isinstance(poll_value, (int, float))
        or not math.isfinite(poll_value)
        or poll_value <= 0
    ):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_recovery poll_value")
    poll_digest = record.get("poll_digest")
    if not isinstance(poll_digest, str) or not _HEX64_RE.match(poll_digest):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_recovery poll_digest")
    if not poll_value > reserved_at:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_recovery order")
    if at < reserved_at:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: last_recovery release order")
    # The stored proof must have been FRESH AT ITS OWN RECORDED RELEASE
    # TIME. The age is measured against the record's OWN ``at`` — never
    # against the current wallclock — so a legitimate historical proof
    # stays valid indefinitely, while a proof that was ALREADY stale when
    # it was recorded is refused instead of interpreted. The skew rule and
    # the clamp are the incumbent ones: a value ahead of ``at`` within the
    # skew clamps to a fresh zero, and a value further ahead refuses.
    if poll_value - at > CLI_POLL_FUTURE_SKEW_SECONDS:
        raise PolicyRefused(
            f"kick_ledger_entry_invalid: {label}: last_recovery future skew"
        )
    recovery_age = at - poll_value
    if recovery_age < 0:
        recovery_age = 0.0
    if recovery_age > STALE_HEARTBEAT_SECONDS:
        raise PolicyRefused(
            f"kick_ledger_entry_invalid: {label}: last_recovery stale evidence"
        )


def save_kick_ledger(home: Path, ledger: Mapping[str, Any]) -> None:
    """Persist the ledger and PROVE it is durable.

    The kick ledger bounds every restart, so a merely READABLE copy is not
    enough: the write must fsync the file AND its parent directory, or it
    raises :class:`DurabilityUnproven` and the caller must not treat the
    state as durable (and must not perform the effect it was reserving).

    A refusal does NOT restore the previous bytes: the rename has already
    landed, so the visible ledger holds the NEW state while its
    crash-durability is unproven. Every state this ledger writes that
    HOLDS a seat is therefore written so that BOTH the previous and the
    new bytes hold the seat: a reservation is RETAINED through an
    acknowledgement and through every ambiguous, refused, interrupted or
    still-reserved outcome, and is never deleted by a write that might be
    unproven. The ONE write that removes a reservation is the qualified
    fresh-recovery release, and it is issued only after the release itself
    has been proven durable."""
    path = kick_ledger_path(home)
    raw = json.dumps(dict(ledger), indent=2, sort_keys=True).encode("utf-8")
    # The temp file is created 0600 and renamed into place, so the target
    # inherits the private mode; no separate chmod can fail after the
    # durable rename.
    atomic_write_bytes_durable(path, raw, 0o600)


# ---------------------------------------------------------------------------
# The exclusive ledger lock. One process at a time may write the ledger.
# ---------------------------------------------------------------------------


def acquire_kick_ledger_lock(home: Path) -> int:
    """Acquire the exclusive kick-ledger lock, or refuse.

    The lock is a dedicated, never-replaced inode ADJACENT to the ledger
    inside the same private state root (the existing ledger owner — no new
    registry, coordinator, or queue). It is qualified before it is used:
    regular file, not hardlinked, owned by this effective user, private
    mode, and provably NOT the inode of the JSON ledger (which is replaced
    by rename on every write, so a lock on that inode would be released by
    the ledger's own replacement).

    Contention fails closed: the caller goes alert-only and performs no
    effect. The lock is a process-level advisory lock (``flock``), so two
    passes in the same process contend exactly like two processes.
    """
    path = kick_ledger_lock_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PolicyRefused(f"kick_ledger_lock_unavailable ({exc.strerror})") from exc
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | _CLOEXEC | _NOFOLLOW, 0o600)
    except OSError as exc:
        raise PolicyRefused(f"kick_ledger_lock_unopenable ({exc.strerror})") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise PolicyRefused("kick_ledger_lock_not_regular")
        if st.st_nlink != 1:
            raise PolicyRefused("kick_ledger_lock_hardlinked")
        if st.st_uid != os.geteuid():
            raise PolicyRefused("kick_ledger_lock_not_owned")
        mode = stat.S_IMODE(st.st_mode)
        if mode & 0o077:
            raise PolicyRefused(f"kick_ledger_lock_unsafe_permissions {oct(mode)}")
        try:
            ledger_stat = kick_ledger_path(home).lstat()
        except FileNotFoundError:
            ledger_stat = None
        except OSError as exc:
            raise PolicyRefused(f"kick_ledger_lock_target_unreadable ({exc.strerror})") from exc
        if ledger_stat is not None and (
            ledger_stat.st_dev == st.st_dev and ledger_stat.st_ino == st.st_ino
        ):
            raise PolicyRefused("kick_ledger_lock_is_ledger_inode")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise PolicyRefused("kick_ledger_lock_contended") from exc
        # The locked path must still name the inode we hold: a replaced lock
        # path would let a second writer hold a different inode.
        try:
            current = os.lstat(path)
        except OSError as exc:
            raise PolicyRefused("kick_ledger_lock_vanished") from exc
        if current.st_dev != st.st_dev or current.st_ino != st.st_ino:
            raise PolicyRefused("kick_ledger_lock_replaced")
        return fd
    except BaseException:
        os.close(fd)
        raise


def release_kick_ledger_lock(fd: int) -> None:
    """Release the exclusive kick-ledger lock (best effort, never raises)."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def _reserve_kick(
    candidate: dict[str, Any],
    label: str,
    now: float,
    *,
    trigger: str,
    forced: bool,
    poll_value: float | None = None,
    poll_digest: str | None = None,
) -> None:
    """Consume ONE attempt and record the PRE-EFFECT reservation.

    This runs BEFORE the action is invoked and is persisted durably before
    the invocation, so the attempt count and the cooldown are consumed even
    when the action's outcome is never knowable. The pending record binds
    the row's timestamp, the row's attempt count, the trigger that
    authorized it, and whether it was a forced restart — a reservation that
    cannot be validated against its row is refused on the next load."""
    seats = candidate["seats"]
    entry = seats.get(label) or {}
    prior = entry.get("consecutive_kicks")
    if prior is None:
        prior = 0  # a seat with no recorded attempt yet
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: consecutive_kicks")
    attempt = prior + 1
    recorded: dict[str, Any] = {
        "last_kick_at": float(now),
        "consecutive_kicks": attempt,
        "fresh_heartbeat_witnessed_since_kick": False,
        "pending": {
            "state": PENDING_RESERVED,
            "label": label,
            "reserved_at": float(now),
            "attempt": attempt,
            "trigger": trigger,
            "forced": bool(forced),
            "reason": "",
            # The pre-attempt first-party poll provenance, bound to THIS
            # reservation: a later recovery proof must strictly ADVANCE
            # it, and must not be the same bytes.
            "poll_value": None if poll_value is None else float(poll_value),
            "poll_digest": None if poll_digest is None else str(poll_digest),
        },
    }
    if poll_value is not None:
        recorded["last_kick_poll_value"] = float(poll_value)
    if poll_digest is not None:
        recorded["last_kick_poll_digest"] = str(poll_digest)
    # The recorded recovery evidence survives the NEXT reservation: it is
    # the attribution for the released attempt and is never dropped.
    prior_recovery = entry.get("last_recovery")
    if isinstance(prior_recovery, dict):
        recorded["last_recovery"] = dict(prior_recovery)
    seats[label] = recorded


def _set_pending_state(
    candidate: dict[str, Any],
    label: str,
    state: str,
    reason: str,
) -> None:
    """Move an existing reservation to another pending state (in place)."""
    seats = candidate["seats"]
    entry = seats.get(label)
    if not isinstance(entry, dict):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: missing pending")
    pending = entry.get("pending")
    if not isinstance(pending, dict):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: missing pending")
    updated = dict(pending)
    updated["state"] = state
    updated["reason"] = reason
    entry["pending"] = updated


def _witness_recovery(ledger: dict[str, Any], label: str) -> None:
    """Record a witnessed recovery: reset the attempt ladder.

    Only a HEALTHY observation of a seat with NO pending reservation may
    reset the ladder. A pending reservation binds the row's attempt count,
    so a healthy observation can neither erase it nor refund the attempt it
    consumed."""
    entry = ledger["seats"].get(label)
    if isinstance(entry, dict):
        if isinstance(entry.get("pending"), dict):
            return  # an unresolved effect is never erased by a healthy sighting
        entry["consecutive_kicks"] = 0
        entry["fresh_heartbeat_witnessed_since_kick"] = True


def _qualified_fresh_observation_age(age: float | None) -> bool:
    """TRUE only for a FRESH, validated first-party observation.

    This is the SAME predicate the incumbent health classifier uses to call
    a seat HEALTHY: the observation's age must be a finite number inside the
    closed freshness window ``[0, STALE_HEARTBEAT_SECONDS]``. The age the
    caller supplies is the one the incumbent payload validator already
    derived — a within-skew future value clamps to a fresh zero and a
    beyond-skew value refuses outright — so this re-states the incumbent
    rule instead of interpreting the clock a second time.

    A stale observation is NOT a recovery witness, however new its
    timestamp is relative to the reservation it would release: a release is
    admitted only by evidence that is fresh AT THE OBSERVING PASS.
    """
    if age is None:
        return False
    if isinstance(age, bool) or not isinstance(age, (int, float)):
        return False
    if not math.isfinite(age):
        return False
    if age < 0.0 or age > STALE_HEARTBEAT_SECONDS:
        return False
    return True


def _recovery_release_admits(
    pending: Mapping[str, Any],
    *,
    label: str,
    poll_value: float | None,
    poll_digest: str | None,
    heartbeat_age: float | None,
) -> bool:
    """Decide whether ONE qualified first-party poll may release an
    ACKNOWLEDGED reservation.

    The release is the ONLY in-band way an attempt is refunded, so it is
    admitted only by evidence that is strictly NEWER than the reservation it
    releases AND FRESH at the observing pass:

    - the reservation must be in the ``acknowledged_awaiting_recovery``
      state. An ambiguous, refused, interrupted, or still-reserved outcome
      is NEVER released by an observation;
    - it must be bound to THIS seat;
    - the observation must be FRESH by the incumbent healthy rule — a
      finite age inside ``[0, STALE_HEARTBEAT_SECONDS]``. A newer-but-STALE
      observation is not a recovery witness and never refunds an attempt;
    - the poll must carry a finite positive timestamp and a 64-hex
      provenance digest;
    - the poll's timestamp must be STRICTLY later than the reservation;
    - it must STRICTLY ADVANCE any pre-attempt poll recorded with the
      reservation, and must not be the same bytes (a replay).

    A fresh-but-pre-attempt timestamp, a replayed payload, a wrong service,
    a file mtime, a present PID alone, and missing data all fail this test
    and therefore never reset the attempt ladder.
    """
    if pending.get("state") != PENDING_ACKNOWLEDGED:
        return False
    if pending.get("label") != label:
        return False
    if not _qualified_fresh_observation_age(heartbeat_age):
        return False  # the observation itself is not fresh: not a witness
    if poll_value is None or poll_digest is None:
        return False
    if isinstance(poll_value, bool) or not isinstance(poll_value, (int, float)):
        return False
    if not math.isfinite(poll_value) or poll_value <= 0:
        return False
    if not isinstance(poll_digest, str) or not _HEX64_RE.match(poll_digest):
        return False
    reserved_at = pending.get("reserved_at")
    if (
        isinstance(reserved_at, bool)
        or not isinstance(reserved_at, (int, float))
        or not math.isfinite(reserved_at)
    ):
        return False
    if not poll_value > reserved_at:
        return False  # not strictly later than the reservation
    prior_value = pending.get("poll_value")
    if prior_value is not None:
        if (
            isinstance(prior_value, bool)
            or not isinstance(prior_value, (int, float))
            or not math.isfinite(prior_value)
        ):
            return False
        if not poll_value > prior_value:
            return False  # does not advance the recorded pre-attempt poll
    prior_digest = pending.get("poll_digest")
    if prior_digest is not None:
        if not isinstance(prior_digest, str) or not _HEX64_RE.match(prior_digest):
            return False
        if poll_digest == prior_digest:
            return False  # byte-identical replay of the consumed evidence
    return True


def _release_acknowledged(
    candidate: dict[str, Any],
    label: str,
    *,
    now: float,
    poll_value: float,
    poll_digest: str,
    heartbeat_age: float | None,
) -> None:
    """Release ONE acknowledged reservation and refund its attempt.

    The reservation is removed and the attempt ladder is reset ONLY
    because the caller proved a bound, strictly newer first-party
    recovery (see :func:`_recovery_release_admits`). The recovery evidence
    — the reservation it releases, the attempt it refunds, the proof's
    timestamp and provenance — is kept in the SAME ledger so the release
    stays attributable. ``last_kick_at`` is preserved, so the 1800 s
    cooldown still runs from the released attempt.

    The SAME freshness predicate is enforced HERE, at the mutation
    boundary, BEFORE the reservation is dropped and the counters are
    changed: admission order alone is not a guarantee, because a stale
    observation that is merely newer than the reservation would otherwise
    refund an attempt and renew the ladder. A refusal here leaves the
    candidate untouched — the reservation, the attempt count, the cooldown
    anchor and the recorded recovery evidence all stay exactly as they
    were.
    """
    if not _qualified_fresh_observation_age(heartbeat_age):
        raise PolicyRefused(
            f"kick_ledger_entry_invalid: {label}: recovery evidence not fresh"
        )
    seats = candidate["seats"]
    entry = seats.get(label)
    if not isinstance(entry, dict):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: missing pending")
    pending = entry.get("pending")
    if not isinstance(pending, dict):
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: missing pending")
    if pending.get("state") != PENDING_ACKNOWLEDGED:
        raise PolicyRefused(f"kick_ledger_entry_invalid: {label}: pending state")
    attempt = pending.get("attempt")
    reserved_at = pending.get("reserved_at")
    updated = dict(entry)
    updated.pop("pending", None)
    updated["consecutive_kicks"] = 0
    updated["fresh_heartbeat_witnessed_since_kick"] = True
    updated["last_recovery"] = {
        "at": float(now),
        "attempt": int(attempt),
        "reserved_at": float(reserved_at),
        "poll_value": float(poll_value),
        "poll_digest": str(poll_digest),
    }
    seats[label] = updated


# ---------------------------------------------------------------------------
# One bounded pass.
# ---------------------------------------------------------------------------


class _LedgerWriteFailed(Exception):
    """A ledger write could not be proven durable (or was otherwise refused).

    ``phase`` names the step that failed: ``"reservation"`` means the effect
    NEVER RAN (the pre-effect record could not be proven durable, so the
    action was refused); ``"settlement"`` means the effect RAN and its
    outcome could not be recorded durably. The difference is the difference
    between "nothing happened" and "we do not know what happened"."""

    def __init__(self, phase: str, cause: BaseException):
        super().__init__(f"{phase}: {cause}")
        self.phase = phase
        self.cause = cause


class _LedgerSession:
    """The private kick-ledger owner for exactly ONE pass.

    It holds the exclusive ledger lock for the whole pass and owns every
    write to the ledger. A mutation is applied to a CANDIDATE copy and
    becomes the in-memory truth only after the durable write succeeded, so
    a failed write can never leave a falsely-settled state in memory for a
    later save to push onto the disk.
    """

    def __init__(self, home: Path, ledger: dict[str, Any], lock_fd: int):
        self.home = Path(home)
        self.ledger = ledger
        self.lock_fd = lock_fd
        self.aborted = False

    def entry(self, label: str) -> dict[str, Any]:
        entry = self.ledger["seats"].get(label)
        return entry if isinstance(entry, dict) else {}

    def pending(self, label: str) -> dict[str, Any] | None:
        pending = self.entry(label).get("pending")
        return pending if isinstance(pending, dict) else None

    def commit(self, mutate: Any) -> None:
        """Apply ``mutate`` to a candidate copy and persist it durably."""
        candidate = json.loads(json.dumps(self.ledger))
        mutate(candidate)
        save_kick_ledger(self.home, candidate)
        self.ledger.clear()
        self.ledger.update(candidate)


def _hold_pending(session: _LedgerSession, label: str, state: str, reason: str) -> None:
    """Persist an unresolved-effect marker for one seat (durably)."""
    try:
        session.commit(
            lambda candidate: _set_pending_state(candidate, label, state, reason)
        )
    except (OSError, DurabilityUnproven, PolicyRefused) as exc:
        raise _LedgerWriteFailed("settlement", exc) from exc


def _settle_pending(session: _LedgerSession, label: str) -> None:
    """Record the acknowledgement durably; the reservation is RETAINED.

    A rc0 means the command was ACKNOWLEDGED. That is NOT a recovery
    witness and NOT a release, so the reservation STAYS in the SAME ledger,
    in the ``acknowledged_awaiting_recovery`` state, and keeps holding the
    seat until a bound, strictly newer first-party recovery proof releases
    it (see :func:`_recovery_release_admits`).

    The transition is ONE durable write and it never deletes anything.
    A failed write leaves either the previous ``reserved`` bytes or the new
    ``acknowledged_awaiting_recovery`` bytes on disk, and BOTH hold the
    seat — so the readable next-pass ledger is conservative either way.

    The previous two-write shape could leave a disk with NO reservation at
    all: the removal write's ``os.replace`` landed and only the
    parent-directory fsync failed, so the readable next-pass ledger held
    nothing while memory and that pass still held the seat. A deletion can
    never be undone by a later, equally uncertain write, so the
    acknowledgement now only ever MOVES the reservation.
    """
    try:
        session.commit(
            lambda candidate: _set_pending_state(
                candidate, label, PENDING_ACKNOWLEDGED, "acknowledged_awaiting_recovery"
            )
        )
    except (OSError, DurabilityUnproven, PolicyRefused) as exc:
        raise _LedgerWriteFailed("settlement", exc) from exc


def _invoke_reserved_kick(
    session: _LedgerSession,
    label: str,
    runner: Any,
    seat_uid: int,
    *,
    forced: bool,
    trigger: str,
    now: float,
    poll_value: float | None,
    poll_digest: str | None,
    report: PassReport,
) -> tuple[bool, bool]:
    """Reserve, invoke, and settle one action. Returns (acted, kick_forced).

    The ORDER is the safety property:

    1. RESERVE durably. The attempt and the 1800 s cooldown are consumed
       BEFORE the action is invoked, and the reservation is on disk before
       the action exists. A reservation that cannot be proven durable
       refuses the effect: the action never runs, so nothing is ambiguous.
    2. INVOKE the action.
    3. ACKNOWLEDGE durably.

    Once the action ran, every outcome that is not a clean acknowledgement
    (generic nonzero exit, signal, timeout, OSError, interruption) leaves
    the reservation PENDING on disk: the seat is HELD until the original
    owner reconciles it explicitly. A pre-spawn refusal (policy or
    permission) proves the action was NOT applied, but it stays HELD too —
    it is never auto-retried after a cooldown. Success means the command
    was ACKNOWLEDGED (rc 0); it is NOT a recovery witness and NOT a
    release: the reservation is retained as
    ``acknowledged_awaiting_recovery`` and keeps holding the seat until a
    bound, strictly newer first-party recovery proof releases it.
    """
    # 1. RESERVE (durable, before the action exists).
    try:
        session.commit(
            lambda candidate: _reserve_kick(
                candidate,
                label,
                now,
                trigger=trigger,
                forced=forced,
                poll_value=poll_value,
                poll_digest=poll_digest,
            )
        )
    except (OSError, DurabilityUnproven, PolicyRefused) as exc:
        raise _LedgerWriteFailed("reservation", exc) from exc

    # 2. INVOKE.
    try:
        kick_argv = launchctl_kickstart_argv(seat_uid, label, force=forced)
    except (ActionRefused, PolicyRefused, IdentityRejected) as refused:
        # Pre-spawn denial: the action was NOT applied — but it stays held
        # for explicit reconciliation, never auto-retried.
        _hold_pending(session, label, PENDING_NOT_APPLIED, "pre_spawn_refused")
        report.alerts.append(Alert("kickstart_refused", label, str(refused), acted=True))
        return False, False
    try:
        result = runner(kick_argv)
    except (ActionRefused, PolicyRefused, IdentityRejected) as refused:
        _hold_pending(session, label, PENDING_NOT_APPLIED, "pre_spawn_refused")
        report.alerts.append(Alert("kickstart_refused", label, str(refused), acted=True))
        return False, False
    except (KeyboardInterrupt, SystemExit):
        # Interruption: the outcome is unknown, so the reservation stays.
        _hold_pending(session, label, PENDING_AMBIGUOUS, "interrupted")
        raise
    except Exception as exc:
        # OSError and every other runner fault: the outcome is unknown.
        _hold_pending(
            session, label, PENDING_AMBIGUOUS, f"runner_error:{exc.__class__.__name__}"
        )
        report.alerts.append(
            Alert(
                "kickstart_failed",
                label,
                f"runner_error:{exc.__class__.__name__}",
                acted=True,
            )
        )
        return False, False

    if bool(getattr(result, "timed_out", False)):
        # An EXPLICIT timeout holds the seat even when the runner contradicts
        # itself with rc0: a timed-out attempt may or may not have been
        # applied, and the contradiction is never resolved in favour of the
        # release.
        _hold_pending(session, label, PENDING_AMBIGUOUS, "timeout")
        report.alerts.append(
            Alert("kickstart_failed", label, f"rc={result.returncode} (timed out)", acted=True)
        )
        return False, False
    if result.returncode != 0:
        # A generic nonzero exit and a signal exit are AMBIGUOUS: the action
        # may or may not have been applied. The reservation stays.
        _hold_pending(session, label, PENDING_AMBIGUOUS, f"rc_{result.returncode}")
        report.alerts.append(
            Alert("kickstart_failed", label, f"rc={result.returncode}", acted=True)
        )
        return False, False

    # 3. SETTLE. The command was ACKNOWLEDGED. The attempt stays consumed
    #    and the seat stays not-healthy until a fresh first-party
    #    observation says so.
    _settle_pending(session, label)
    return True, forced


def run_pass(
    home: Path,
    runner: Any,
    *,
    now: float,
    recover: bool = True,
    poll_runner: Any = None,
) -> PassReport:
    """Single bounded health pass over exactly the five qualified labels.

    The pass tolerates a manifest past its one-day attestation bound (B1):
    trust is then re-derived from live host state per seat, and any seat
    whose live identity no longer matches the pinned manifest is ALERT ONLY
    for this pass. Mutation paths never receive this leniency.

    ``poll_runner`` is the injectable first-party CLI control-plane-poll
    seam (default: the real bounded runner); it is invoked ONLY for seats
    whose manifest qualifies the strictly typed CLI-poll heartbeat mode, and
    only when a launchd-proven PID is present — a missing PID recovers
    through the launchd-proven route without any poll.

    The kick ledger is owned for the whole pass by ONE exclusive lock,
    acquired BEFORE the ledger is read and held through the reservation,
    the effect, the settlement, and the final save. Contention fails
    closed: the pass goes alert-only and performs no effect."""
    home = Path(home)
    report = PassReport(started_at=now)
    poll_runner = poll_runner if poll_runner is not None else control_plane_poll_runner
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
    # tampered state can never be silently reset to empty. The exclusive
    # lock serializes every ledger-writing pass; contention fails closed.
    lock_fd: int | None = None
    session: _LedgerSession | None = None
    try:
        lock_fd = acquire_kick_ledger_lock(home)
    except PolicyRefused as refused:
        report.alerts.append(
            Alert("kick_ledger_lock_refused_alert_only", "host", str(refused))
        )
    try:
        ledger: dict[str, Any] | None = None
        if lock_fd is not None:
            try:
                ledger = load_kick_ledger(home)
            except PolicyRefused as refused:
                report.alerts.append(
                    Alert("kick_ledger_refused_recovery_alert_only", "host", str(refused))
                )
                ledger = None
        if ledger is not None:
            session = _LedgerSession(home, ledger, lock_fd)
        _run_seats(
            home=home,
            manifest=manifest,
            runner=runner,
            poll_runner=poll_runner,
            session=session,
            report=report,
            now=now,
            recover=recover,
            rogue=bool(rogue),
            suspect_labels=suspect_labels,
        )
        if session is not None and recover and not session.aborted:
            # Persist the observation-side ledger changes (the
            # witnessed-recovery resets). An observation-only pass NEVER
            # writes the ledger, so it can never overwrite a pending state.
            try:
                session.commit(lambda candidate: None)
            except (OSError, DurabilityUnproven, PolicyRefused) as exc:
                report.alerts.append(
                    Alert(ST_LEDGER_SETTLEMENT_FAILED, "host", str(exc))
                )
                session.aborted = True
    finally:
        if lock_fd is not None:
            release_kick_ledger_lock(lock_fd)
    _finish(report, home, now)
    return report


def _run_seats(
    *,
    home: Path,
    manifest: Mapping[str, Any],
    runner: Any,
    poll_runner: Any,
    session: _LedgerSession | None,
    report: PassReport,
    now: float,
    recover: bool,
    rogue: bool,
    suspect_labels: frozenset[str],
) -> None:
    """The per-seat body of one pass (exactly the five qualified labels)."""
    seats: dict[str, Any] = {}
    for label in sorted(TUNNEL_LABELS):
        entry = manifest["seats"][label]
        seat_uid = int(entry["uid"])
        heartbeat_mode = entry.get("heartbeat_mode") or HEARTBEAT_MODE_FILE_MTIME
        cli_poll = heartbeat_mode == HEARTBEAT_MODE_CLI_CONTROL_PLANE_POLL
        heartbeat_kind_fact = entry.get("heartbeat_kind")
        heartbeat_proof_note_fact = entry.get("heartbeat_proof_note")
        # B6 attestation requires BOTH positive operator facts — kind-only or
        # a blank proof note (e.g. a tampered private manifest) is alert-only
        # and can never authorize a stale forced kick.
        heartbeat_attested = operator_heartbeat_attested(
            heartbeat_kind_fact, heartbeat_proof_note_fact
        )
        # Qualified-evidence gate for EITHER mode (see classify_seat): a file
        # path for the legacy mode, the profile + derived locator for the
        # strictly typed CLI-poll mode.
        evidence_recorded = (
            bool(entry.get("heartbeat_profile_file")) and bool(entry.get("heartbeat_url_locator"))
        ) if cli_poll else bool(entry.get("heartbeat_path"))
        heartbeat_age: float | None = None
        poll_refused_code: str | None = None
        poll_replayed = False
        accepted_poll_value: float | None = None
        accepted_poll_digest: str | None = None
        # A rogue family member suspends per-seat recovery for this pass:
        # identity of the family itself is in question, so no kickstarts.
        pid = read_job_pid(runner, seat_uid, label) if not rogue else None
        pid_proven_present = (
            pid is not None
            and not isinstance(pid, _PIDStateUnknown)
            and label not in suspect_labels
            and session is not None
            and not rogue
        )
        if cli_poll and pid_proven_present:
            # Read-only first-party probe (pinned executable + pinned
            # locator only). Executed ONLY with a launchd-proven PID, a
            # trusted ledger, and a non-suspect seat.
            heartbeat_age, poll_refused_code, accepted_poll_value, accepted_poll_digest = cli_poll_evidence(
                label, entry, seat_uid, poll_runner, now=now, home=home, manifest=manifest
            )
            if poll_refused_code is None:
                # Replay check against the provenance recorded at the last
                # evidence-authorized kick: byte-identical consumed evidence
                # may not authorize another kick or witness freshness.
                prior_kick_entry = session.entry(label) if session is not None else {}
                poll_replayed = (
                    prior_kick_entry.get("last_kick_poll_value") == accepted_poll_value
                    and prior_kick_entry.get("last_kick_poll_digest") == accepted_poll_digest
                )
        elif not cli_poll and entry.get("heartbeat_path"):
            heartbeat_age = read_heartbeat_age(entry["heartbeat_path"], now)
        # An UNRESOLVED effect on this seat holds it: no attempt, whatever
        # the cooldown says, and no healthy observation may erase it.
        pending = session.pending(label) if session is not None else None
        # A bound first-party recovery proof may release ONE acknowledged
        # reservation. It is the only in-band way an attempt is refunded,
        # and it is admitted only by evidence that is strictly newer than
        # the reservation it releases AND FRESH at this pass by the
        # incumbent healthy rule. Everything else — an ambiguous,
        # refused, interrupted or still-reserved outcome, a fresh but
        # pre-attempt timestamp, a replay, a wrong service, an mtime, a
        # present PID alone, missing data, or a newer-but-STALE
        # observation — leaves the seat held, with its attempt count,
        # cooldown anchor and recorded recovery evidence unchanged.
        release_value = accepted_poll_value
        release_digest = accepted_poll_digest
        if (
            session is not None
            and not session.aborted
            and recover
            and pending is not None
            and cli_poll
            and poll_refused_code is None
            and not poll_replayed
            and release_value is not None
            and release_digest is not None
            and label not in suspect_labels
            and not rogue
            and _recovery_release_admits(
                pending,
                label=label,
                poll_value=release_value,
                poll_digest=release_digest,
                heartbeat_age=heartbeat_age,
            )
        ):
            value = float(release_value)
            digest = str(release_digest)
            try:
                session.commit(
                    lambda candidate: _release_acknowledged(
                        candidate,
                        label,
                        now=now,
                        poll_value=value,
                        poll_digest=digest,
                        heartbeat_age=heartbeat_age,
                    )
                )
            except (OSError, DurabilityUnproven, PolicyRefused) as exc:
                # The release could not be proven durable: the on-disk state
                # is uncertain, so this pass stops writing and performing.
                report.alerts.append(Alert(ST_LEDGER_SETTLEMENT_FAILED, label, str(exc)))
                session.aborted = True
            else:
                pending = session.pending(label)
                report.alerts.append(
                    Alert(
                        "kick_effect_recovered",
                        label,
                        "a bound first-party control-plane poll strictly newer than the "
                        "reservation released the acknowledged attempt; the attempt "
                        "ladder was reset and the recovery evidence was recorded in "
                        "the same kick ledger",
                    )
                )
        if label in suspect_labels:
            state, may_kick = ST_IDENTITY_SUSPECT, False
        elif pid is PID_STATE_UNKNOWN:
            # launchd state could not be QUALIFIED (unexpected print error):
            # never treated as a missing PID, never recovered, alert only.
            state, may_kick = ST_LAUNCHD_UNCERTAIN, False
        elif session is None:
            # Untrusted ledger: classification still reports, but no
            # recovery — kick history cannot bound the kickstart.
            state, may_kick = ST_LEDGER_REFUSED, False
        elif pending is not None:
            state, may_kick = ST_PENDING_EFFECT, False
        else:
            seat_entry = session.entry(label)
            state, may_kick = classify_seat(
                qualified=evidence_recorded and not rogue,
                pid=pid,
                heartbeat_age=heartbeat_age,
                heartbeat_path_recorded=evidence_recorded,
                heartbeat_kind=heartbeat_kind_fact,
                heartbeat_proof_note=heartbeat_proof_note_fact,
                last_kick_at=seat_entry.get("last_kick_at"),
                consecutive_kicks=int(seat_entry.get("consecutive_kicks") or 0),
                fresh_heartbeat_witnessed_since_kick=bool(
                    seat_entry.get("fresh_heartbeat_witnessed_since_kick")
                ),
                now=now,
                heartbeat_mode=heartbeat_mode,
                poll_refused_code=poll_refused_code,
                poll_replayed=poll_replayed,
            )
        acted = False
        kick_forced = False
        if may_kick and recover and not rogue and session is not None and not session.aborted:
            # Pre-effect identity re-proof: EVERY kickstart re-proves the
            # seat's whole identity against the pinned manifest from the
            # LIVE filesystem first — argv, executable path/digest and its
            # pinned dev/ino/owner/mode, parent and Cellar-allowance pins,
            # and any pinned poll-profile binding — never only after the
            # attestation day boundary. A drifting seat is a suspect seat:
            # alert only, no kick, until a human requalifies.
            drift = seat_identity_drift_problems(home, manifest, label)
            if drift:
                state = ST_IDENTITY_SUSPECT
                may_kick = False
                report.alerts.append(
                    Alert("seat_identity_drift_alert_only", label, ",".join(drift))
                )
        if may_kick and recover and not rogue and session is not None and not session.aborted:
            forced = state == ST_STALE_HEARTBEAT
            trigger = "stale_heartbeat" if forced else "missing_pid"
            try:
                acted, kick_forced = _invoke_reserved_kick(
                    session,
                    label,
                    runner,
                    seat_uid,
                    forced=forced,
                    trigger=trigger,
                    now=now,
                    poll_value=accepted_poll_value if cli_poll else None,
                    poll_digest=accepted_poll_digest if cli_poll else None,
                    report=report,
                )
            except _LedgerWriteFailed as failed:
                # The reservation could not be proven durable (the effect
                # never ran) or the settlement could not (the effect ran and
                # its outcome is uncertain). Either way this pass stops
                # writing and performing: the on-disk state is uncertain and
                # only the original ledger can settle it.
                code = (
                    ST_LEDGER_RESERVATION_FAILED
                    if failed.phase == "reservation"
                    else ST_LEDGER_SETTLEMENT_FAILED
                )
                report.alerts.append(Alert(code, label, str(failed)))
                session.aborted = True
                state = code
        # Re-read the reservation AFTER the action: this pass may have
        # CREATED one (an ambiguous or refused outcome), and the seat is
        # held from that moment on.
        pending_after = session.pending(label) if session is not None else None
        if pending_after is not None:
            if state not in (ST_LEDGER_RESERVATION_FAILED, ST_LEDGER_SETTLEMENT_FAILED):
                state = ST_PENDING_EFFECT
            report.alerts.append(
                Alert(
                    ST_PENDING_EFFECT,
                    label,
                    f"unresolved effect held in the kick ledger (state={pending_after.get('state')}); "
                    "no retry, no cooldown release, no healthy-observation erase; "
                    "an acknowledged attempt is released only by a bound first-party "
                    "poll strictly newer than its reservation AND fresh at this "
                    "pass; every other outcome is "
                    "held for the original owner's own reconciliation",
                )
            )
        if (
            state == ST_HEALTHY
            and session is not None
            and pending_after is None
            and not session.aborted
        ):
            # A replayed payload never reaches ST_HEALTHY, so consumed
            # evidence can never reset the escalation ladder here. A seat
            # with an unresolved effect is never reset by a healthy sighting
            # either.
            _witness_recovery(session.ledger, label)
        seats[label] = {
            "pid": None if isinstance(pid, _PIDStateUnknown) else pid,
            "heartbeat_age_seconds": None if heartbeat_age is None else int(heartbeat_age),
            "state": state,
            "heartbeat_mode": heartbeat_mode,
            "heartbeat_attested": heartbeat_attested,
            "kickstarted": acted,
            "kickstarted_forced": kick_forced,
            "effect_pending": pending_after is not None,
            # A STABLE pending-state code only — never a path, an argv body,
            # or any payload content.
            "effect_pending_state": (
                str(pending_after.get("state")) if pending_after is not None else ""
            ),
        }
        if cli_poll:
            # Stable refusal code and replay flag only — never a URL,
            # profile path, locator, or any payload content.
            seats[label]["poll_refused_code"] = poll_refused_code or ""
            seats[label]["poll_evidence_replayed"] = poll_replayed
        report.alerts.extend(
            alert for alert in _seat_alerts(state, label) if alert.code not in {a.code for a in report.alerts if a.label == label}
        )
    report.seats = seats


def _seat_alerts(state: str, label: str) -> list[Alert]:
    if state == ST_HEARTBEAT_MISSING:
        return [Alert(ST_HEARTBEAT_MISSING, label)]
    if state == ST_CLI_POLL_UNPROVEN:
        return [
            Alert(
                ST_CLI_POLL_UNPROVEN,
                label,
                "first-party control-plane poll evidence was refused or ambiguous this pass "
                "(stable per-seat refusal code in the pass report); NO action, fail closed",
            )
        ]
    if state == ST_POLL_EVIDENCE_REPLAYED:
        return [
            Alert(
                ST_POLL_EVIDENCE_REPLAYED,
                label,
                "byte-identical poll evidence to the last kick's recorded provenance; "
                "consumed evidence may not authorize another kick or witness freshness",
            )
        ]
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
                "heartbeat mtime is DIAGNOSTIC ONLY: it can never establish health, reset the attempt "
                "ladder, or authorize a stale forced restart — not even with heartbeat_kind + "
                "heartbeat_proof_note; the required host proof is the strictly typed first-party "
                "control-plane poll (heartbeat_mode=first_party_cli_control_plane_poll)",
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
    manifest = load_manifest(home, now=now)  # strict: install-time authorization is fresh
    # Pre-effect identity re-proof for all five qualified seats: the
    # watchdog acts ON those seats, so an install effect may only land while
    # every seat's live identity still matches the pinned manifest.
    for label in sorted(TUNNEL_LABELS):
        drift = seat_identity_drift_problems(home, manifest, label)
        if drift:
            raise PolicyRefused(f"{label}_watchdog_install_identity_drift:{','.join(drift)}")
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


# Every alert code that makes a pass FAIL (nonzero CLI exit). An unresolved
# effect, a refused ledger lock, and an unprovable reservation or settlement
# are all blocking: the pass could not establish a trustworthy state, and
# the CLI must not report success for it.
BLOCKING_ALERT_CODES: frozenset[str] = frozenset({
    "not_qualified",
    GEN_DRIFT,
    REPAIR_MISSING,
    ST_ESCALATED,
    ST_HEARTBEAT_MISSING,
    ST_CLI_POLL_UNPROVEN,
    ST_POLL_EVIDENCE_REPLAYED,
    ST_STALE_HEARTBEAT_UNPROVEN,
    ST_IDENTITY_SUSPECT,
    ST_LAUNCHD_UNCERTAIN,
    ST_LEDGER_REFUSED,
    ST_PENDING_EFFECT,
    ST_LEDGER_RESERVATION_FAILED,
    ST_LEDGER_SETTLEMENT_FAILED,
    "kick_ledger_lock_refused_alert_only",
    "seat_identity_drift_alert_only",
    "manifest_stale_revalidated",
    "seat_identity_tampered_alert_only",
    "seat_identity_rejected",
    TELEMETRY_STALE,
})


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
    blocking = BLOCKING_ALERT_CODES
    if any(alert.code in blocking for alert in report.alerts):
        return 4
    return 0

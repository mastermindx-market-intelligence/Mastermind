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
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

from fabric_tunnel_common import (
    DEFAULT_STALE_TELEMETRY_SECONDS,
    FORBIDDEN_LABELS,
    KICKSTART_COOLDOWN_SECONDS,
    KICKSTART_ESCALATION_LIMIT,
    KICK_LEDGER_SCHEMA,
    MASTER_SHA,
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
from fabric_tunnel_identity import load_manifest, scan_family, unqualified_health_alerts

# Health states, one per distinguishable outcome the plan names.
ST_HEALTHY = "healthy"
ST_MISSING_PID = "missing_pid"
ST_STALE_HEARTBEAT = "stale_heartbeat"
ST_HEARTBEAT_UNQUALIFIED = "heartbeat_unqualified"
ST_HEARTBEAT_MISSING = "heartbeat_missing"
ST_UNQUALIFIED = "unqualified"
ST_COOLDOWN = "kickstart_suppressed_cooldown"
ST_ESCALATED = "kickstart_escalated_alert"

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
    last_kick_at: float | None,
    consecutive_kicks: int,
    fresh_heartbeat_witnessed_since_kick: bool,
    now: float,
) -> tuple[str, bool]:
    """Return (state, may_kickstart).

    ``may_kickstart`` is True only for the two qualified recovery states and
    only when the persisted cooldown and escalation ledger allow it.
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
    if manifest_host.get("host_pull_telemetry_dir"):
        threshold = float(manifest_host.get("stale_telemetry_seconds") or DEFAULT_STALE_TELEMETRY_SECONDS)
        if telemetry_age is None:
            alerts.append(Alert(TELEMETRY_UNQUALIFIED, "host", "no telemetry readable"))
        elif telemetry_age > threshold:
            alerts.append(Alert(TELEMETRY_STALE, "host", f"age={int(telemetry_age)}s"))
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
    import stat as stat_module

    if not stat_module.S_ISREG(st.st_mode):
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


def read_telemetry_age(telemetry_dir: str, now: float) -> float | None:
    root = Path(telemetry_dir)
    try:
        candidates = sorted(p for p in root.rglob("*") if p.is_file())
    except OSError:
        return None
    if not candidates:
        return None
    newest = max(st.st_mtime for st in (p.lstat() for p in candidates))
    return max(0.0, now - newest)


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
    """Single bounded health pass over exactly the five qualified labels."""
    home = Path(home)
    report = PassReport(started_at=now)
    try:
        manifest = load_manifest(home, now=now)
    except (PolicyRefused, IdentityRejected) as refused:
        report.alerts.append(Alert("not_qualified", "host", str(refused)))
        _finish(report, home, now)
        return report

    for alert in unqualified_health_alerts(home, manifest):
        report.alerts.append(alert)

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
    if manifest.get("host_pull_telemetry_dir"):
        telemetry_age = read_telemetry_age(manifest["host_pull_telemetry_dir"], now)
    report.generation = {
        "selected_generation": selected,
        "pinned_generation": manifest.get("pinned_generation"),
        "telemetry_age_seconds": None if telemetry_age is None else int(telemetry_age),
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
        heartbeat_age = read_heartbeat_age(heartbeat_path, now) if heartbeat_path else None
        # A rogue family member suspends per-seat recovery for this pass:
        # identity of the family itself is in question, so no kickstarts.
        pid = read_job_pid(runner, seat_uid, label) if not rogue else None
        state, may_kick = classify_seat(
            qualified=bool(heartbeat_path) and not rogue,
            pid=pid,
            heartbeat_age=heartbeat_age,
            heartbeat_path_recorded=bool(heartbeat_path),
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
    """
    if not confirm:
        raise PolicyRefused("watchdog_install_requires_explicit_confirmation")
    manifest = load_manifest(home, now=now)
    from fabric_tunnel_install import _bootout_if_loaded, _bootstrap

    interpreter = shutil.which("python3")
    if not interpreter:
        raise PolicyRefused("python3_interpreter_unavailable")

    home = Path(home)
    module_dir = Path(__file__).resolve().parent
    target_dir = watchdog_dir(home)
    target_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(target_dir, 0o700)
    for name in _WATCHDOG_MODULE_FILES:
        source = module_dir / name
        require_regular_file(source, code="watchdog_source_missing")
        raw = source.read_bytes()
        dest = target_dir / name
        atomic_write_bytes(dest, raw, 0o600)
        os.chmod(dest, 0o600)
    entrypoint = target_dir / "fabric_tunnel_health.py"

    log_dir = private_state_root(home) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(log_dir, 0o700)
    program = [
        interpreter,
        str(entrypoint),
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
    raw = _ser(plist)
    atomic_write_bytes(plist_path, raw, 0o644)
    _bootout_if_loaded(runner, os.getuid(), WATCHDOG_LABEL)
    _bootstrap(runner, os.getuid(), plist_path)
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
        TELEMETRY_STALE,
    }
    if any(alert.code in blocking for alert in report.alerts):
        return 4
    return 0

"""Fixed root maintenance stop; no recovery, grant, enrollment or activation.

The ordinary service owner first stops Control, worker and Relay through their
existing lifecycle commands. This final bounded step disables/unloads only the
idle privileged broker. A residual socket is preserved by native no-replace
rename only across the complete stopped-source and old-owner observations.
It never unlinks a node or edits configuration, Runtime, grants or receipts.

A successful return is a sampled stopped state, not an OriginInterval. The
separately authorized forward entry must acquire its own fresh genuine context.
"""
from pathlib import Path
import os
import sys
import time

from control_plane import executive_incident_composition as composition
from control_plane import executive_incident_origin as origin
from control_plane import executive_recovery_host_observation as host
from control_plane import executive_recovery_namespace as namespace
from control_plane import executive_release_observation as release
from control_plane import executive_incident_release_observation as incident_release
from control_plane import executive_incident_socket_retirement as retirement

__all__ = ()
_LABEL = "com.mastermind.executive.privileged"
_SERVICE = "system/" + _LABEL
_DISABLE = ("/bin/launchctl", "disable", _SERVICE)
_BOOTOUT = ("/bin/launchctl", "bootout", _SERVICE)
_STOP_COMMANDS = (_DISABLE, _BOOTOUT)
_BUDGET_NS = 60_000_000_000
_ROLES = ("control", "worker", "relay", "gateway", "broker")


class BrokerMaintenanceError(RuntimeError):
    def __init__(self, code, *, disable_attempted=False, bootout_attempted=False,
                 socket_retirement_attempted=False):
        self.code = code
        self.disable_attempted = disable_attempted
        self.bootout_attempted = bootout_attempted
        self.socket_retirement_attempted = socket_retirement_attempted
        super().__init__(code)


def _refuse(code):
    raise BrokerMaintenanceError(code)


def _run_stop_command(argv, budget):
    if type(argv) is not tuple or argv not in _STOP_COMMANDS:
        _refuse("BROKER_MAINTENANCE_COMMAND_REFUSED")
    return origin._run_owned_native_command(argv, budget)


def _source():
    source = composition._loaded_source()
    expected = Path("/Library/Application Support/MastermindExecutive/releases") / source["release_sha"]
    if Path(__file__).resolve(strict=True).parents[1] != expected:
        _refuse("BROKER_MAINTENANCE_SOURCE_MISMATCH")
    return source


def _observe(source, budget):
    value = incident_release._observe_incident_release(deadline_monotonic_ns=budget.endpoint)
    incident_release._validate_observation(value)
    if tuple(row.role for row in value.roles) != _ROLES:
        _refuse("BROKER_MAINTENANCE_ROLE_MISMATCH")
    if any(row.content.release_commit != source["release_sha"] or
           row.content.installed_manifest_digest != source["manifest_sha256"]
           for row in value.roles if row.role != "relay"):
        _refuse("BROKER_MAINTENANCE_SOURCE_MISMATCH")
    if any(row.state != "UNLOADED" for row in value.roles[:3]):
        _refuse("BROKER_MAINTENANCE_CONSUMERS_NOT_STOPPED")
    if value.roles[-1].state not in ("LOADED_IDLE", "UNLOADED"):
        _refuse("BROKER_MAINTENANCE_ACTIVE_BROKER")
    return value


def _same_content(before, after):
    if before.boot_id != after.boot_id or tuple(row.content for row in before.roles) != tuple(
        row.content for row in after.roles
    ):
        _refuse("BROKER_MAINTENANCE_CONTENT_DRIFT")


def _require_closed_arms(observed, budget):
    from ops.executive_os.acceptance_maintenance import require_disarmed

    configurations = []
    for spec, row in zip(release._SPECS[:2], observed.roles[:2]):
        artifact = budget.call(release._artifact, spec.config,
                               spec.config_mode, spec.config_gid, budget)
        if artifact.digest != row.content.configuration_digest:
            _refuse("BROKER_MAINTENANCE_CONTENT_DRIFT")
        configurations.append(release.peer._load_strict_json(
            artifact.raw, code="BROKER_MAINTENANCE_CONFIG_MALFORMED"))
    require_disarmed(configurations[0])
    if configurations[1].get("operator_harness_armed") is not False:
        _refuse("BROKER_MAINTENANCE_WORKER_ARMED")


def _stop_incident_broker():
    """Once-only modifying verbs, followed by typed current-state observation.

    This reversible stop needs root maintenance authority, not a new credential
    grant. A dormant forward policy remains dormant throughout this operation.
    """
    disable_attempted = bootout_attempted = False
    socket_retirement_attempted = False
    handles = None
    error = None
    cleanup_failed = False
    result = None
    try:
        if sys.platform != "darwin" or os.geteuid() != 0:
            _refuse("BROKER_MAINTENANCE_PRINCIPAL_UNQUALIFIED")
        budget = release._Budget(time.monotonic_ns() + _BUDGET_NS)
        source = budget.call(_source)
        before = budget.call(_observe, source, budget)
        # Trusted config bytes match this observation and the following bracket.
        # Use the existing control policy and separate worker-harness obligation.
        budget.call(_require_closed_arms, before, budget)
        census = budget.call(host._root_census, budget)
        if census.matching_runtime_instances != (census.observer,):
            _refuse("BROKER_MAINTENANCE_OTHER_ROOT_OWNER")
        qualified = budget.call(_observe, source, budget)
        _same_content(before, qualified)
        if qualified.roles[-1].state != before.roles[-1].state:
            _refuse("BROKER_MAINTENANCE_BROKER_CHANGED")
        # A retained prior move blocks this operation before even disable.
        # Register handles before the return-side deadline fence so cleanup
        # remains owned on every pre-effect refusal.
        handles = namespace._acquire_namespace(deadline_monotonic_ns=budget.endpoint)
        budget.check(force=True)
        budget.call(retirement._require_retained_absent, handles)
        if before.roles[-1].state == "LOADED_IDLE":
            disable_attempted = True
            rc, out, err = _run_stop_command(_DISABLE, budget)
            if type(rc) is not int or rc != 0 or out or err:
                _refuse("BROKER_MAINTENANCE_DISABLE_REFUSED")
            # An ambiguous/failed disable never reaches bootout.
            host.normalize_disabled(*budget.call(
                release._command, release._PRINT_DISABLED_ARGV, budget))
            current = budget.call(_observe, source, budget)
            _same_content(before, current)
            if current.roles[-1].state != "LOADED_IDLE":
                _refuse("BROKER_MAINTENANCE_BROKER_CHANGED")
            bootout_attempted = True
            rc, out, err = _run_stop_command(_BOOTOUT, budget)
            if type(rc) is not int or rc != 0 or out or err:
                _refuse("BROKER_MAINTENANCE_BOOTOUT_REFUSED")
        # Reuse the exact installer readback; no second modifying command.
        host._wait_installer_unloaded(_LABEL, deadline_monotonic_ns=budget.endpoint)
        budget.check(force=True)
        candidate = budget.call(retirement._candidate, handles)
        retained = None
        if candidate is not None:
            excluded = budget.call(host._observe_old_owner_exclusion,
                                   deadline_monotonic_ns=budget.endpoint)
            stopped = budget.call(_observe, source, budget)
            _same_content(before, stopped)
            if (stopped.roles[-1].state != "UNLOADED"
                    or excluded.boot_id != stopped.boot_id
                    or excluded.boot_id != handles.boot
                    or excluded.census.observer != handles.owner):
                _refuse("BROKER_MAINTENANCE_RETIREMENT_OWNER_DRIFT")
            budget.call(_require_closed_arms, stopped, budget)
            if budget.call(_source) != source:
                _refuse("BROKER_MAINTENANCE_SOURCE_DRIFT")
            socket_retirement_attempted = True
            retained = retirement._retire(handles, candidate)
            budget.check(force=True)
        budget.call(namespace._require_socket_absent, handles)
        excluded_after = budget.call(host._observe_old_owner_exclusion,
                                     deadline_monotonic_ns=budget.endpoint)
        after = budget.call(_observe, source, budget)
        _same_content(before, after)
        if candidate is not None:
            if (excluded_after.boot_id != excluded.boot_id
                    or excluded_after.census.observer != excluded.census.observer):
                _refuse("BROKER_MAINTENANCE_RETIREMENT_OWNER_DRIFT")
            budget.call(retirement._recheck_retained, handles, retained)
        if after.roles[-1].state != "UNLOADED":
            _refuse("BROKER_MAINTENANCE_UNLOAD_UNPROVEN")
        if budget.call(_source) != source:
            _refuse("BROKER_MAINTENANCE_SOURCE_DRIFT")
        result = {"maintenance_state": "BROKER_STOPPED_OBSERVED",
                  "release_sha": source["release_sha"],
                  "observation_purpose": after.purpose,
                  "cohort_content_sha256": after.cohort_content_sha256,
                  "disable_attempted": disable_attempted,
                  "bootout_attempted": bootout_attempted,
                   "socket_retirement_attempted": socket_retirement_attempted,
                  "origin_custody": False, "provider_called": False}
    except BaseException as failure:
        error = failure
    finally:
        if handles is not None:
            try:
                namespace._release_namespace(handles)
            except BaseException:
                cleanup_failed = True
    if error is None and not cleanup_failed:
        try:
            budget.check(force=True)
        except BaseException as failure:
            error = failure
    if error is not None or cleanup_failed:
        raise BrokerMaintenanceError(
            "BROKER_MAINTENANCE_CLEANUP_UNPROVEN" if cleanup_failed else
            getattr(error, "code", "BROKER_MAINTENANCE_UNAVAILABLE"),
            disable_attempted=disable_attempted, bootout_attempted=bootout_attempted,
            socket_retirement_attempted=socket_retirement_attempted,
        ) from error
    return result

"""Dormant trusted-owner observation draft; not a forward-recovery guard.

No public entrypoint or core wiring. A future private caller must supply the
original absolute budget and preserve the installer/connection custody interval.
Source-only fixture tests do not qualify these native acquisitions on the host.
No service mutation, socket connection, permission or provider effect is here.
"""
from dataclasses import dataclass
import os
import stat
import sys
import time

from control_plane import executive_release_observation as release
from control_plane import executive_installed_peer as peer
from control_plane.executive_ambient_process import _proc_pid_path
from control_plane.executive_process_identity import _observe_process_instance
from control_plane.executive_recovery_observation_normalization import (
    Instance, ImageSample, ObservationRejected, normalize_image,
    normalize_disabled, normalize_root_inventory,
)

__all__ = ()


class HostObservationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _refuse(code):
    raise HostObservationError(code) from None


def _instance(pid, budget):
    value = budget.call(_observe_process_instance, pid)
    if (type(pid) is not int or not 0 < pid < 2**31
            or type(value.unique_id) is not int or not 0 < value.unique_id < 2**64
            or type(value.pidversion) is not int or not 0 < value.pidversion < 2**31):
        _refuse("RECOVERY_PROCESS_IDENTITY_UNAVAILABLE")
    return Instance(pid, value.unique_id, value.pidversion)


def _physical_file(path, budget):
    info = budget.call(os.lstat, path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink < 1:
        _refuse("RECOVERY_IMAGE_MAPPING_UNAVAILABLE")
    return peer._object_identity(info)


@dataclass(frozen=True, slots=True)
class _ImageRow:
    instance: Instance
    kernel_path: str
    file_identity: tuple


def _image_row(pid, budget):
    first = _instance(pid, budget)
    path = budget.call(_proc_pid_path, pid)
    if path is None:
        _refuse("RECOVERY_IMAGE_MAPPING_UNAVAILABLE")
    before_path = str(path)
    before_file = _physical_file(before_path, budget)
    second_path = budget.call(_proc_pid_path, pid)
    if second_path is None:
        _refuse("RECOVERY_IMAGE_MAPPING_UNAVAILABLE")
    after_path = str(second_path)
    after_file = _physical_file(after_path, budget)
    last = _instance(pid, budget)
    try:
        normalize_image(ImageSample(first, last, before_path, after_path))
    except ObservationRejected:
        _refuse("RECOVERY_PROCESS_IMAGE_DRIFT")
    if before_file != after_file:
        _refuse("RECOVERY_PROCESS_IMAGE_DRIFT")
    return _ImageRow(first, before_path, before_file)


def _root_pids(budget):
    # Closed runner owns the fixed ps process, waits/reaps it and closes both
    # pipes before returning its PID. Never accept a caller-supplied exemption.
    rc, out, err, own_child = budget.call(
        release._command, release._ROOT_PID_UID_ARGV, budget,
        include_owned_inventory_pid=True,
    )
    try:
        pids = normalize_root_inventory(rc, out, err)
    except ObservationRejected:
        _refuse("RECOVERY_ROOT_INVENTORY_UNAVAILABLE")
    if (type(own_child) is not int or own_child <= 1
            or own_child not in pids or own_child == os.getpid()):
        _refuse("RECOVERY_INVENTORY_CHILD_UNSETTLED")
    return tuple(pid for pid in pids if pid != own_child)


@dataclass(frozen=True, slots=True)
class _RootCensus:
    observer: Instance
    rows: tuple[_ImageRow, ...]
    matching_runtime_instances: tuple[Instance, ...]


def _root_census(budget):
    """Complete sampled root set under the existing trusted-root topology.

    Not a globally atomic process census or malicious-root containment. The
    qualified runtime main file is compared physically, not by comm/basename
    or launcher identity. Unknown/unqueryable images refuse, including exits.
    Only disagreement between two complete inventories permits reacquisition:
    at most three candidates share the caller's original budget and anchors.
    This never retries a failed acquisition or a surrounding maintenance effect.
    """
    runtime = budget.call(peer._verify_python_runtime, budget)
    main = _physical_file(peer._PYTHON_MAIN_EXECUTABLE, budget)
    observer_pid = os.getpid()
    own_before = _instance(observer_pid, budget)
    pinned_self = pinned_matches = None
    for _ in range(3):
        budget.check(force=True)
        before = _root_pids(budget)
        if observer_pid not in before:
            _refuse("RECOVERY_OBSERVER_NOT_ACCOUNTED")
        # No exceptions are caught. Even a known exited or unreadable PID
        # aborts; a partial image pass can never trigger reacquisition.
        rows = tuple(_image_row(pid, budget) for pid in before)
        after = _root_pids(budget)
        if observer_pid not in after:
            _refuse("RECOVERY_OBSERVER_NOT_ACCOUNTED")
        own_after = _instance(observer_pid, budget)
        if own_before != own_after:
            _refuse("RECOVERY_ROOT_CENSUS_DRIFT")
        observed_self = next(row for row in rows if row.instance.pid == observer_pid)
        if observed_self.instance != own_before or observed_self.file_identity[:2] != main[:2]:
            _refuse("RECOVERY_OBSERVER_IMAGE_UNQUALIFIED")
        matches = tuple(row.instance for row in rows if row.file_identity[:2] == main[:2])
        if pinned_self is not None and (observed_self != pinned_self or matches != pinned_matches):
            # Never hide an already observed qualified runtime owner by taking
            # a later inventory. Comparisons are anchors, not cached rows.
            _refuse("RECOVERY_ROOT_CENSUS_DRIFT")
        pinned_self, pinned_matches = observed_self, matches
        if before == after:
            # Recheck every process after the second full inventory. Positive
            # image/instance drift inside a candidate still refuses immediately.
            for row in rows:
                if _image_row(row.instance.pid, budget) != row:
                    _refuse("RECOVERY_ROOT_CENSUS_DRIFT")
        if _physical_file(peer._PYTHON_MAIN_EXECUTABLE, budget) != main:
            _refuse("RECOVERY_RUNTIME_DRIFT")
        budget.call(peer._recheck_python_runtime, runtime, budget)
        budget.check(force=True)
        if before == after:
            return _RootCensus(own_before, rows, matches)
        # Discard all rows and both inventories. The next candidate must read
        # every current PID anew; there is no sleep, exemption or budget reset.
    _refuse("RECOVERY_ROOT_CENSUS_DRIFT")


def _strict_disabled_unloaded(budget):
    try:
        normalize_disabled(*budget.call(release._command, release._PRINT_DISABLED_ARGV, budget))
        spec = release._SPECS[-1]
        if spec.role != "broker":
            _refuse("RECOVERY_BROKER_ROLE_DRIFT")
        rc, out, err = budget.call(release._command, ("/bin/launchctl", "print", spec.service), budget)
        # Reuse the canonical exact-113 parser. Empty argv/release cannot
        # qualify a loaded service, and only UNLOADED is accepted below.
        state, pid = release._parse_service(spec, rc, out, err, (), "")
        if state != "UNLOADED" or pid is not None:
            _refuse("RECOVERY_BROKER_STILL_LOADED")
    except (ObservationRejected, release.ReleaseObservationError):
        _refuse("RECOVERY_MAINTENANCE_UNPROVEN")


@dataclass(frozen=True, slots=True)
class _OldOwnerObservation:
    boot_id: str
    census: _RootCensus
    started_monotonic_ns: int
    completed_monotonic_ns: int
    deadline_monotonic_ns: int


def _observe_old_owner_exclusion(*, deadline_monotonic_ns):
    """One private sampled exclusion observation, never a standing lock.

    There is no disable/bootout/bootstrap here. The authorized installer owns
    those effects and must bind successful disable, namespace absence/origin,
    sole ownership and uninterrupted custody separately before this can be used.
    """
    try:
        budget = release._Budget(deadline_monotonic_ns)
        if sys.platform != "darwin" or os.geteuid() != 0:
            _refuse("RECOVERY_OBSERVER_PRINCIPAL_UNQUALIFIED")
        boot = budget.call(release._boot, budget)
        _strict_disabled_unloaded(budget)
        census = _root_census(budget)
        if census.matching_runtime_instances != (census.observer,):
            _refuse("RECOVERY_PINNED_ROOT_INTERPRETER_REMAINS")
        _strict_disabled_unloaded(budget)
        if budget.call(release._boot, budget) != boot:
            _refuse("RECOVERY_BOOT_DRIFT")
        budget.check(force=True)
        return _OldOwnerObservation(boot, census, budget.started, budget.last, budget.endpoint)
    except HostObservationError:
        raise
    except Exception:
        _refuse("RECOVERY_HOST_OBSERVATION_UNAVAILABLE")


def _wait_installer_unloaded(label, *, deadline_monotonic_ns):
    """Fixed installer readback only; does not disable or stop a service.

    One original absolute budget covers all bounded commands and waits. This
    tightens ordinary absence handling, but does not produce origin custody.
    """
    allowed = tuple(s.label for s in release._SPECS if s.role != "gateway") + (
        "com.mastermind.executive.backup",)
    if type(label) is not str or label not in allowed:
        _refuse("RECOVERY_INSTALLER_LABEL_REFUSED")
    try:
        budget = release._Budget(deadline_monotonic_ns)
        if sys.platform != "darwin" or os.geteuid() != 0:
            _refuse("RECOVERY_OBSERVER_PRINCIPAL_UNQUALIFIED")
        for attempt in range(5):
            if label == "com.mastermind.executive.privileged":
                normalize_disabled(*budget.call(release._command, release._PRINT_DISABLED_ARGV, budget))
            rc, out, err = budget.call(release._command, ("/bin/launchctl", "print", "system/" + label), budget)
            if release._exact_unloaded_reply(label, rc, out, err):
                budget.check(force=True)
                return
            if rc != 0 or err:
                _refuse("RECOVERY_INSTALLER_ABSENCE_UNAVAILABLE")
            # A successful print is still loaded, even if idle. A later fixed
            # readback may observe completed bootout; no effect is repeated.
            if attempt != 4:
                budget.call(time.sleep, min(1.0, budget.remaining()))
        _refuse("RECOVERY_INSTALLER_SERVICE_STILL_LOADED")
    except HostObservationError:
        raise
    except Exception:
        _refuse("RECOVERY_INSTALLER_ABSENCE_UNAVAILABLE")


@dataclass(frozen=True, slots=True)
class _BeforeBootstrapObservation:
    whole_release: object
    old_owner_before: _OldOwnerObservation
    old_owner_after: _OldOwnerObservation


def _observe_whole_content_before_bootstrap(*, deadline_monotonic_ns):
    """Dormant read-only seam for placement AFTER whole content publication.

    Never invoked by the installer in this draft. It cannot authorize bootstrap:
    namespace absence, live custody lifetime and actual core integration remain
    separate obligations. A JSON rendering cannot recreate this private context.
    """
    # The outer budget preserves clock-rollback/refusal state across the three
    # readers as well as their shared absolute endpoint. New inner budgets do
    # not excuse a backwards sample between reader return and next entry.
    budget = release._Budget(deadline_monotonic_ns)
    before = budget.call(_observe_old_owner_exclusion, deadline_monotonic_ns=deadline_monotonic_ns)
    whole = budget.call(release._observe_release, deadline_monotonic_ns=deadline_monotonic_ns)
    after = budget.call(_observe_old_owner_exclusion, deadline_monotonic_ns=deadline_monotonic_ns)
    if (whole.boot_id != before.boot_id or whole.boot_id != after.boot_id
            or before.census.observer != after.census.observer
            or tuple(r.role for r in whole.roles) != ("control", "worker", "relay", "gateway", "broker")
            or whole.roles[-1].state != "UNLOADED"):
        _refuse("RECOVERY_PREBOOTSTRAP_JOIN_UNAVAILABLE")
    budget.check(force=True)
    return _BeforeBootstrapObservation(whole, before, after)

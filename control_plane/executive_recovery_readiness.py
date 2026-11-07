"""Closed, read-only host recovery-readiness evidence contract.

This module answers exactly one question about one already-observed Mastermind
home Mac: after an unattended power loss or reboot, does the host come back far
enough for the *caller-named role* to resume without a human at the keyboard?

It validates and classifies one bounded observation produced elsewhere.  It does
not sample hosts, invoke commands, mutate power/service/encryption state, keep a
registry of hosts, schedule or gate execution, or persist anything.  Collection
and command invocation belong to ``ops/executive_os/host_recovery_readiness.py``;
privileged remediation remains with the reviewed broker owner.

There are exactly three closed profiles, and the caller must name one.  Nothing
here infers a profile from what happens to be installed: inferring the weaker
profile from missing daemons would let a broken Executive control host pass.

``home-mac-recovery-base/v1``
    Physical/local recoverability of one home Mac only: platform, power policy,
    Remote Login, preboot-unlock eligibility, and disk headroom.  It claims
    nothing about worker runtime or Executive control-plane readiness, so no
    Executive daemon predicate is load-bearing under it.
``fleet-secondary-host-preflight/v1``
    The physical/local base plus a load-bearing proof that the canonical central
    Executive control, MCP, and sol-state-relay LaunchDaemons are not installed.
    This is a pre-enrollment anti-duplication gate only; it claims nothing about
    Worker/Fabric, provider, MH1 gateway, or Studio Direct readiness.
``executive-control-host/v1``
    Everything in the base profile plus the already-installed Studio Executive
    control, MCP, and sol-state-relay LaunchDaemons running.

All profiles classify the same fixed superset of observations; the profile
changes classification requirements only, never what the collector may run.

Requirement semantics are deliberately explicit:

``REQUIRED`` / ``REQUIRED_RUNNING`` / ``REQUIRED_ABSENT``
    Load-bearing.  An unsatisfied or unknown predicate changes the overall
    recovery state. ``REQUIRED_ABSENT`` is used only for fixed system-daemon
    predicates and accepts only ``NOT_INSTALLED``.
``OPTIONAL``
    Reviewed-as-preferable but not load-bearing for unattended recovery.
``DISARMED_EXPECTED``
    The profile expects this service to be absent or disabled right now.  Its
    absence is the intended gate state, never a defect.
``ADVISORY``
    Reported because an operator must know it, but it cannot decide readiness.

The report contract is semantic, not merely syntactic.  A predicate's status,
its code and its measurement are only true together, so each is derived from
one law and the validator re-derives all three: given a predicate, the
requirement the named profile assigns it, and its code, exactly one status is
legal, and only the codes whose classifier observes a value may carry one.  A
failure code wearing ``OK``, an advisory-only code on a load-bearing pass, or a
bounded integer parked on an unrelated verdict is refused before any derived
recovery state is trusted.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


READINESS_SCHEMA = "mastermind.host_recovery_readiness/v1"

# Physical/local recoverability of one home Mac.  Explicitly NOT a claim that
# the host can execute Agent Fabric / worker work, and explicitly not Executive
# control-host acceptance.
BASE_RECOVERY_PROFILE = "home-mac-recovery-base/v1"
# The base profile plus the canonical Studio Executive control plane running.
EXECUTIVE_CONTROL_PROFILE = "executive-control-host/v1"
# Physical readiness plus proof that this secondary host does not contain a
# duplicate copy of the central Executive control plane.  This is deliberately
# a pre-enrollment gate, not worker/fabric or Studio Direct acceptance.
SECONDARY_HOST_PREFLIGHT_PROFILE = "fleet-secondary-host-preflight/v1"
READINESS_PROFILES = (
    BASE_RECOVERY_PROFILE,
    SECONDARY_HOST_PREFLIGHT_PROFILE,
    EXECUTIVE_CONTROL_PROFILE,
)

# Reviewed floor: the preboot recovery profile below is only reviewed against
# macOS 14+ on Apple silicon.  Raise it deliberately, never infer it.
MIN_SUPPORTED_MACOS_MAJOR = 14

# Apple-silicon remote FileVault unlock after a restart, over Remote Login and
# without a human at the keyboard, is only a supported platform capability from
# macOS 26 onward.  An encrypted host below that generation cannot satisfy the
# unattended preboot journey no matter how the rest of the host is configured,
# so this floor is a separate reviewed constant from the profile floor above.
MIN_PREBOOT_REMOTE_UNLOCK_MACOS_MAJOR = 26

# Reviewed free-space floor for an unattended host that must survive a cold boot
# plus log, snapshot and release growth without a human freeing space.
DISK_FREE_FLOOR_BYTES = 25 * 1024**3

HOST_REF_RE = re.compile(r"^host-[0-9a-f]{64}$")

REQUIREMENTS = frozenset(
    {
        "REQUIRED",
        "REQUIRED_RUNNING",
        "REQUIRED_ABSENT",
        "OPTIONAL",
        "DISARMED_EXPECTED",
        "ADVISORY",
    }
)
LOAD_BEARING_REQUIREMENTS = frozenset(
    {"REQUIRED", "REQUIRED_RUNNING", "REQUIRED_ABSENT"}
)
STATUSES = frozenset({"OK", "NOT_READY", "UNKNOWN", "ADVISORY", "NOT_APPLICABLE"})
RECOVERY_STATES = frozenset({"READY", "NOT_READY", "UNKNOWN"})
EVIDENCE_CLASSES = frozenset(
    {
        "SYSTEM_PLATFORM",
        "POWER_POLICY",
        "REMOTE_ACCESS_POLICY",
        "DISK_ENCRYPTION_STATE",
        "PREBOOT_RECOVERY_DEPENDENCY",
        "SYSTEM_SERVICE_STATE",
        "USER_SESSION_DEPENDENCY",
        "FILESYSTEM_CAPACITY",
    }
)

FILEVAULT_CODES = (
    "FILEVAULT_ON",
    "FILEVAULT_ENCRYPTION_IN_PROGRESS",
    "FILEVAULT_DECRYPTION_IN_PROGRESS",
    "FILEVAULT_OFF",
    "FILEVAULT_STATE_UNKNOWN",
)
REMOTE_LOGIN_OBSERVATIONS = frozenset(
    {"ENABLED", "DISABLED", "NOT_INSTALLED", "UNKNOWN"}
)
DAEMON_OBSERVATIONS = frozenset(
    {"RUNNING", "LOADED_NOT_RUNNING", "DISABLED", "NOT_INSTALLED", "UNKNOWN"}
)

# Already-installed critical Executive system LaunchDaemons that must be running
# for the canonical Executive control host to be useful after boot.  They are
# load-bearing under ``executive-control-host/v1`` only: a worker or capacity
# host must not run a duplicate Executive control plane, so their absence there
# is not a defect and installing them to turn this checker green is wrong.
REQUIRED_RUNNING_DAEMON_LABELS = (
    "com.mastermind.executive.control",
    "com.mastermind.executive.mcp",
    "com.mastermind.executive.sol-state-relay",
)
# Services the current gates deliberately keep absent or disabled.  The reviewed
# privileged broker (#613/#621) lives here: merged but intentionally uninstalled.
DISARMED_EXPECTED_DAEMON_LABELS = (
    "com.mastermind.executive.backup",
    "com.mastermind.executive.privileged",
    "com.mastermind.executive.worker.codex",
    "com.mastermind.executive.worker.codex-pro-01",
    "com.mastermind.executive.worker.codex-pro-02",
    "com.mastermind.executive.worker.codex-pro-03",
)
# All profiles observe the same fixed superset of system labels; only the
# requirement attached to each one differs.
ALL_DAEMON_LABELS = tuple(
    sorted(REQUIRED_RUNNING_DAEMON_LABELS + DISARMED_EXPECTED_DAEMON_LABELS)
)
# User-session surfaces. These are LaunchAgents: they cannot exist before a
# console login, so they are reported separately and never claim boot readiness.
USER_SESSION_CRITICAL_LABELS = (
    "com.mastermind.chairman-control-room",
    "com.mastermind.desktop-commander.remote",
    "com.mastermind.executive.tunnel",
    "com.mastermind.studio-direct-mcp",
)

DAEMON_PREDICATE_PREFIX = "system_daemon."
_DAEMON_CODES = frozenset(
    {
        "DAEMON_RUNNING",
        "DAEMON_LOADED_NOT_RUNNING",
        "DAEMON_DISABLED",
        "DAEMON_NOT_INSTALLED",
        "DAEMON_INTENTIONALLY_DISARMED",
        "DAEMON_UNEXPECTEDLY_RUNNING",
        "DAEMON_STATE_UNKNOWN",
    }
)

# Encryption state alone is an operator fact, not a readiness defect: an
# encrypted host can still be recovered unattended when the platform supports
# remote preboot unlock, and ``preboot_remote_unlock`` is the load-bearing
# predicate that decides that.
_FILEVAULT_CODE_STATUSES = {
    "FILEVAULT_ON": "ADVISORY",
    "FILEVAULT_ENCRYPTION_IN_PROGRESS": "ADVISORY",
    "FILEVAULT_DECRYPTION_IN_PROGRESS": "ADVISORY",
    "FILEVAULT_OFF": "OK",
    "FILEVAULT_STATE_UNKNOWN": "UNKNOWN",
}

# The non-daemon predicate table.  Each entry is
# ``(requirement, evidence_class, {code: canonical_status})`` and that third
# mapping is the *only* law relating a code to a status: the classifiers derive
# the status they emit from it and the validator derives the status it demands
# from it, so a report cannot pair a failure code with a passing status.  The
# code vocabulary is exactly the mapping's key set, so a new code cannot be
# added without deciding what it means.
_BASE_PREDICATES: dict[str, tuple[str, str, dict[str, str]]] = {
    "os_identity": (
        "REQUIRED",
        "SYSTEM_PLATFORM",
        {
            "OS_SUPPORTED": "OK",
            "OS_UNSUPPORTED_VERSION": "NOT_READY",
            "OS_NOT_DARWIN": "NOT_READY",
            "OS_IDENTITY_UNKNOWN": "UNKNOWN",
        },
    ),
    "cpu_architecture": (
        "REQUIRED",
        "SYSTEM_PLATFORM",
        {
            "ARCHITECTURE_APPLE_SILICON": "OK",
            "ARCHITECTURE_UNSUPPORTED": "NOT_READY",
            "ARCHITECTURE_UNKNOWN": "UNKNOWN",
        },
    ),
    "ac_sleep_policy": (
        "REQUIRED",
        "POWER_POLICY",
        {
            "AC_SLEEP_DISABLED": "OK",
            "AC_SLEEP_ENABLED": "NOT_READY",
            "AC_SLEEP_UNKNOWN": "UNKNOWN",
        },
    ),
    "auto_restart_after_power_loss": (
        "REQUIRED",
        "POWER_POLICY",
        {
            "AUTO_RESTART_ENABLED": "OK",
            "AUTO_RESTART_DISABLED": "NOT_READY",
            "AUTO_RESTART_UNKNOWN": "UNKNOWN",
        },
    ),
    "auto_restart_on_power_connect": (
        "OPTIONAL",
        "POWER_POLICY",
        {
            "AUTO_RESTART_ON_CONNECT_ENABLED": "OK",
            "AUTO_RESTART_ON_CONNECT_DISABLED": "ADVISORY",
            "AUTO_RESTART_ON_CONNECT_NOT_EXPOSED": "NOT_APPLICABLE",
            "AUTO_RESTART_ON_CONNECT_UNKNOWN": "UNKNOWN",
        },
    ),
    "remote_login_listener": (
        "REQUIRED",
        "REMOTE_ACCESS_POLICY",
        {
            "REMOTE_LOGIN_ENABLED": "OK",
            "REMOTE_LOGIN_DISABLED": "NOT_READY",
            "REMOTE_LOGIN_NOT_INSTALLED": "NOT_READY",
            "REMOTE_LOGIN_UNKNOWN": "UNKNOWN",
        },
    ),
    "disk_encryption_state": (
        "ADVISORY",
        "DISK_ENCRYPTION_STATE",
        {code: _FILEVAULT_CODE_STATUSES[code] for code in FILEVAULT_CODES},
    ),
    "preboot_remote_unlock": (
        "REQUIRED",
        "PREBOOT_RECOVERY_DEPENDENCY",
        {
            "PREBOOT_UNLOCK_NOT_REQUIRED": "OK",
            "PREBOOT_UNLOCK_SUPPORTED": "OK",
            "PREBOOT_UNLOCK_OS_GENERATION_UNSUPPORTED": "NOT_READY",
            "PREBOOT_UNLOCK_ARCHITECTURE_UNSUPPORTED": "NOT_READY",
            "PREBOOT_UNLOCK_REMOTE_LOGIN_UNAVAILABLE": "NOT_READY",
            "PREBOOT_UNLOCK_STATE_UNKNOWN": "UNKNOWN",
        },
    ),
    "user_session_surfaces": (
        "ADVISORY",
        "USER_SESSION_DEPENDENCY",
        {
            "USER_SESSION_LOGIN_REQUIRED": "ADVISORY",
            "USER_SESSION_AGENTS_ABSENT": "ADVISORY",
            "USER_SESSION_STATE_UNKNOWN": "UNKNOWN",
        },
    ),
    "disk_free_floor": (
        "REQUIRED",
        "FILESYSTEM_CAPACITY",
        {
            "DISK_FREE_ABOVE_FLOOR": "OK",
            "DISK_FREE_BELOW_FLOOR": "NOT_READY",
            "DISK_FREE_UNKNOWN": "UNKNOWN",
        },
    ),
}


class RecoveryReadinessContractError(ValueError):
    """A closed, non-secret recovery-readiness contract refusal."""


def _refuse(code: str) -> Any:
    raise RecoveryReadinessContractError(code)


class _PredicateProfile:
    """The frozen requirement table for exactly one closed readiness profile.

    Requirements are decided here, once, from the profile string the caller
    named.  Nothing about this table depends on later caller state, and the
    evidence class and code vocabulary of a predicate are identical in every
    profile, so only ``requirement`` can differ between two reports.
    """

    def __init__(
        self,
        profile: str,
        *,
        required_running_labels: tuple[str, ...] = (),
        required_absent_labels: tuple[str, ...] = (),
        disarmed_expected_labels: tuple[str, ...] = (),
    ) -> None:
        self.profile = profile
        self.required_running_labels = tuple(required_running_labels)
        self.required_absent_labels = tuple(required_absent_labels)
        self.disarmed_expected_labels = tuple(disarmed_expected_labels)
        owned = (
            set(self.required_running_labels)
            | set(self.required_absent_labels)
            | set(self.disarmed_expected_labels)
        )
        if (
            len(owned)
            != len(self.required_running_labels)
            + len(self.required_absent_labels)
            + len(self.disarmed_expected_labels)
            or not owned.issubset(ALL_DAEMON_LABELS)
        ):
            raise RecoveryReadinessContractError("PROFILE_DAEMON_REQUIREMENTS_INVALID")
        # Daemons not owned by this profile remain visibility-only.  This keeps
        # pre-enrollment classification from pretending an absent or running
        # worker/provider service proves the Worker/Fabric is ready.
        self.advisory_daemon_labels = tuple(
            label for label in ALL_DAEMON_LABELS if label not in owned
        )
        self.all_daemon_labels = ALL_DAEMON_LABELS
        table: dict[str, str] = {
            predicate_id: entry[0] for predicate_id, entry in _BASE_PREDICATES.items()
        }
        for label in ALL_DAEMON_LABELS:
            table[DAEMON_PREDICATE_PREFIX + label] = self._daemon_requirement(label)
        self._requirements = table

    def _daemon_requirement(self, label: str) -> str:
        if label in self.required_running_labels:
            return "REQUIRED_RUNNING"
        if label in self.required_absent_labels:
            return "REQUIRED_ABSENT"
        if label in self.disarmed_expected_labels:
            return "DISARMED_EXPECTED"
        return "ADVISORY"

    def requirement(self, predicate_id: str) -> str:
        requirement = self._requirements.get(predicate_id)
        if requirement is None:
            _refuse("PREDICATE_UNKNOWN")
        return requirement

    def evidence_class(self, predicate_id: str) -> str:
        return _evidence_class(predicate_id)

    def codes(self, predicate_id: str) -> frozenset[str]:
        return _predicate_codes(predicate_id)

    def predicate_ids(self) -> tuple[str, ...]:
        return PREDICATE_IDS


# The code -> canonical-status law for every non-daemon predicate.  Daemon
# predicates are deliberately absent: the same daemon code means different
# things under ADVISORY, REQUIRED_RUNNING and DISARMED_EXPECTED, so their law
# is requirement-specific and derived from ``_DAEMON_VERDICTS`` below.
PREDICATE_CODE_STATUSES: dict[str, dict[str, str]] = {
    predicate_id: dict(entry[2]) for predicate_id, entry in _BASE_PREDICATES.items()
}
PREDICATE_CODES: dict[str, frozenset[str]] = {
    predicate_id: frozenset(entry[2])
    for predicate_id, entry in _BASE_PREDICATES.items()
} | {DAEMON_PREDICATE_PREFIX + label: _DAEMON_CODES for label in ALL_DAEMON_LABELS}
PREDICATE_EVIDENCE_CLASSES: dict[str, str] = {
    predicate_id: entry[1] for predicate_id, entry in _BASE_PREDICATES.items()
} | {
    DAEMON_PREDICATE_PREFIX + label: "SYSTEM_SERVICE_STATE"
    for label in ALL_DAEMON_LABELS
}
PREDICATE_IDS = tuple(sorted(PREDICATE_CODES))


def _evidence_class(predicate_id: str) -> str:
    evidence_class = PREDICATE_EVIDENCE_CLASSES.get(predicate_id)
    if evidence_class is None:
        _refuse("PREDICATE_UNKNOWN")
    return evidence_class


def _predicate_codes(predicate_id: str) -> frozenset[str]:
    codes = PREDICATE_CODES.get(predicate_id)
    if codes is None:
        _refuse("PREDICATE_UNKNOWN")
    return codes


def _canonical_predicate_status(
    predicate_id: str, requirement: Any, code: Any
) -> str:
    """Return the one status this ``(predicate, requirement, code)`` may carry.

    There is exactly one legal status per triple, so a report cannot attach a
    passing status to a failure code, an unknown code to a decided status, or an
    advisory-only code to a load-bearing pass.  Daemon predicates resolve
    through the requirement-specific verdict table because the same observed
    daemon code is a defect under ``REQUIRED_RUNNING``, the intended gate state
    under ``DISARMED_EXPECTED``, and visibility-only under ``ADVISORY``.
    """

    statuses = PREDICATE_CODE_STATUSES.get(predicate_id)
    if statuses is None:
        if predicate_id not in PREDICATE_CODES:
            _refuse("PREDICATE_UNKNOWN")
        statuses = _DAEMON_CODE_STATUSES.get(requirement)
        if statuses is None:
            _refuse("PREDICATE_STATUS_CODE_MISMATCH")
    status = statuses.get(code)
    if status is None:
        # Either an out-of-vocabulary code or, for a daemon, a code this
        # requirement can never produce (a disarmed-expected verdict on a
        # required-running service, say).
        _refuse("PREDICATE_STATUS_CODE_MISMATCH")
    return status


# The closed measurement law.  A code appears here only when the classifier can
# legitimately attach an observed value to it; every code that does not appear
# must carry ``None``, so a bounded integer cannot be parked on a semantically
# unrelated verdict.
_MEASUREMENT_ABSENT = "ABSENT"
_MEASUREMENT_ZERO = "ZERO"
_MEASUREMENT_POSITIVE = "POSITIVE"
_MEASUREMENT_AT_OR_ABOVE_DISK_FLOOR = "AT_OR_ABOVE_DISK_FLOOR"
_MEASUREMENT_BELOW_DISK_FLOOR = "BELOW_DISK_FLOOR"

PREDICATE_MEASUREMENT_LAW: dict[str, dict[str, str]] = {
    # Only an enabled AC sleep timer has a value, and an enabled timer of zero
    # minutes is not a thing the classifier can observe.
    "ac_sleep_policy": {"AC_SLEEP_ENABLED": _MEASUREMENT_POSITIVE},
    # The observed console-agent count, which is what decides the code.
    "user_session_surfaces": {
        "USER_SESSION_AGENTS_ABSENT": _MEASUREMENT_ZERO,
        "USER_SESSION_LOGIN_REQUIRED": _MEASUREMENT_POSITIVE,
    },
    # Observed free bytes, which must sit on the side of the reviewed floor
    # that the code claims.
    "disk_free_floor": {
        "DISK_FREE_ABOVE_FLOOR": _MEASUREMENT_AT_OR_ABOVE_DISK_FLOOR,
        "DISK_FREE_BELOW_FLOOR": _MEASUREMENT_BELOW_DISK_FLOOR,
    },
}
_NO_MEASUREMENTS: dict[str, str] = {}


def _check_measurement(predicate_id: str, code: str, measurement: Any) -> None:
    """Refuse a measurement that the predicate's own code cannot carry."""

    rule = PREDICATE_MEASUREMENT_LAW.get(predicate_id, _NO_MEASUREMENTS).get(
        code, _MEASUREMENT_ABSENT
    )
    if rule == _MEASUREMENT_ABSENT:
        if measurement is not None:
            _refuse("PREDICATE_MEASUREMENT_MISMATCH")
        return
    if type(measurement) is not int or not 0 <= measurement <= _INT64_MAX:
        _refuse("PREDICATE_MEASUREMENT_MISMATCH")
    if rule == _MEASUREMENT_ZERO and measurement != 0:
        _refuse("PREDICATE_MEASUREMENT_MISMATCH")
    if rule == _MEASUREMENT_POSITIVE and measurement <= 0:
        _refuse("PREDICATE_MEASUREMENT_MISMATCH")
    if (
        rule == _MEASUREMENT_AT_OR_ABOVE_DISK_FLOOR
        and measurement < DISK_FREE_FLOOR_BYTES
    ):
        _refuse("PREDICATE_MEASUREMENT_MISMATCH")
    if rule == _MEASUREMENT_BELOW_DISK_FLOOR and measurement >= DISK_FREE_FLOOR_BYTES:
        _refuse("PREDICATE_MEASUREMENT_MISMATCH")


RECOVERY_PROFILES: dict[str, _PredicateProfile] = {
    BASE_RECOVERY_PROFILE: _PredicateProfile(BASE_RECOVERY_PROFILE),
    SECONDARY_HOST_PREFLIGHT_PROFILE: _PredicateProfile(
        SECONDARY_HOST_PREFLIGHT_PROFILE,
        required_absent_labels=REQUIRED_RUNNING_DAEMON_LABELS,
    ),
    EXECUTIVE_CONTROL_PROFILE: _PredicateProfile(
        EXECUTIVE_CONTROL_PROFILE,
        required_running_labels=REQUIRED_RUNNING_DAEMON_LABELS,
        disarmed_expected_labels=DISARMED_EXPECTED_DAEMON_LABELS,
    ),
}


def recovery_profile(profile: Any) -> _PredicateProfile:
    """Return the closed requirement table for one exact profile string."""

    if type(profile) is not str:
        _refuse("PROFILE_UNKNOWN")
    table = RECOVERY_PROFILES.get(profile)
    if table is None:
        _refuse("PROFILE_UNKNOWN")
    return table


PREDICATE_FIELDS = frozenset(
    {"requirement", "status", "code", "evidence_class", "measurement"}
)
REPORT_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "host_ref",
        "observed_at_ms",
        "predicates",
        "recovery_state",
        "blocking_predicates",
        "unknown_predicates",
    }
)
OBSERVATION_FIELDS = frozenset(
    {
        "host_ref",
        "observed_at_ms",
        "os_name",
        "macos_product_version",
        "apple_silicon",
        "ac_power_settings",
        "filevault_code",
        "remote_login",
        "system_daemons",
        "user_session_agents_present",
        "root_free_bytes",
    }
)

_ALLOWED_STATUSES = {
    "REQUIRED": frozenset({"OK", "NOT_READY", "UNKNOWN"}),
    "REQUIRED_RUNNING": frozenset({"OK", "NOT_READY", "UNKNOWN"}),
    "REQUIRED_ABSENT": frozenset({"OK", "NOT_READY", "UNKNOWN"}),
    "OPTIONAL": frozenset({"OK", "ADVISORY", "UNKNOWN", "NOT_APPLICABLE"}),
    "DISARMED_EXPECTED": frozenset({"OK", "ADVISORY", "UNKNOWN"}),
    "ADVISORY": frozenset({"OK", "ADVISORY", "UNKNOWN"}),
}
_MACOS_VERSION_RE = re.compile(r"^(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,4}){0,3}$")
_INT64_MAX = (1 << 63) - 1


def _predicate(
    predicate_id: str,
    *,
    code: str,
    requirement: str | None = None,
    measurement: int | None = None,
) -> dict[str, Any]:
    """Build one observation verdict from its code alone.

    The status is *derived*, never asserted by the classifier, so the code and
    the status can never disagree at the source either.  ``requirement`` is only
    needed by daemon predicates, whose status is requirement-specific; the
    report's ``requirement`` field is still stamped later from the profile the
    caller named, so no classifier reads requirements out of global state.
    """

    _check_measurement(predicate_id, code, measurement)
    return {
        "status": _canonical_predicate_status(predicate_id, requirement, code),
        "code": code,
        "evidence_class": _evidence_class(predicate_id),
        "measurement": measurement,
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value or len(value) > 64:
        _refuse("OBSERVATION_TEXT_INVALID")
    return value


def _optional_count(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= _INT64_MAX:
        _refuse("OBSERVATION_COUNT_INVALID")
    return value


def _validate_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != OBSERVATION_FIELDS:
        _refuse("OBSERVATION_FIELDS_INVALID")

    host_ref = value.get("host_ref")
    if host_ref is not None and (
        type(host_ref) is not str or HOST_REF_RE.fullmatch(host_ref) is None
    ):
        _refuse("HOST_REF_INVALID")

    observed_at_ms = value.get("observed_at_ms")
    if type(observed_at_ms) is not int or not 1 <= observed_at_ms <= _INT64_MAX:
        _refuse("OBSERVED_AT_INVALID")

    apple_silicon = value.get("apple_silicon")
    if apple_silicon is not None and type(apple_silicon) is not bool:
        _refuse("ARCHITECTURE_OBSERVATION_INVALID")

    settings = value.get("ac_power_settings")
    normalized_settings: dict[str, int] | None
    if settings is None:
        normalized_settings = None
    elif isinstance(settings, Mapping):
        normalized_settings = {}
        for key, setting in settings.items():
            if type(key) is not str or not key:
                _refuse("POWER_SETTING_INVALID")
            if type(setting) is not int or not 0 <= setting <= _INT64_MAX:
                _refuse("POWER_SETTING_INVALID")
            normalized_settings[key] = setting
    else:
        _refuse("POWER_SETTING_INVALID")

    if value.get("filevault_code") not in FILEVAULT_CODES:
        _refuse("FILEVAULT_OBSERVATION_INVALID")
    if value.get("remote_login") not in REMOTE_LOGIN_OBSERVATIONS:
        _refuse("REMOTE_LOGIN_OBSERVATION_INVALID")

    daemons = value.get("system_daemons")
    if not isinstance(daemons, Mapping):
        _refuse("DAEMON_OBSERVATION_INVALID")
    normalized_daemons: dict[str, str] = {}
    for label, state in daemons.items():
        if label not in ALL_DAEMON_LABELS:
            _refuse("DAEMON_LABEL_UNKNOWN")
        if state not in DAEMON_OBSERVATIONS:
            _refuse("DAEMON_OBSERVATION_INVALID")
        normalized_daemons[label] = state

    return {
        "host_ref": host_ref,
        "observed_at_ms": observed_at_ms,
        "os_name": _optional_text(value.get("os_name")),
        "macos_product_version": _optional_text(value.get("macos_product_version")),
        "apple_silicon": apple_silicon,
        "ac_power_settings": normalized_settings,
        "filevault_code": value["filevault_code"],
        "remote_login": value["remote_login"],
        "system_daemons": normalized_daemons,
        "user_session_agents_present": _optional_count(
            value.get("user_session_agents_present")
        ),
        "root_free_bytes": _optional_count(value.get("root_free_bytes")),
    }


def _macos_major(observation: Mapping[str, Any]) -> int | None:
    """Return the macOS major version, or ``None`` when it cannot be trusted."""

    if observation["os_name"] != "Darwin":
        return None
    version = observation["macos_product_version"]
    if version is None or _MACOS_VERSION_RE.fullmatch(version) is None:
        return None
    return int(version.split(".", 1)[0])


def _classify_os_identity(observation: Mapping[str, Any]) -> dict[str, Any]:
    os_name = observation["os_name"]
    if os_name is None:
        return _predicate("os_identity", code="OS_IDENTITY_UNKNOWN")
    if os_name != "Darwin":
        return _predicate("os_identity", code="OS_NOT_DARWIN")
    major = _macos_major(observation)
    if major is None:
        return _predicate("os_identity", code="OS_IDENTITY_UNKNOWN")
    if major < MIN_SUPPORTED_MACOS_MAJOR:
        return _predicate(
            "os_identity", code="OS_UNSUPPORTED_VERSION"
        )
    return _predicate("os_identity", code="OS_SUPPORTED")


def _classify_architecture(observation: Mapping[str, Any]) -> dict[str, Any]:
    apple_silicon = observation["apple_silicon"]
    if apple_silicon is None:
        return _predicate(
            "cpu_architecture", code="ARCHITECTURE_UNKNOWN"
        )
    if not apple_silicon:
        return _predicate(
            "cpu_architecture", code="ARCHITECTURE_UNSUPPORTED"
        )
    return _predicate(
        "cpu_architecture", code="ARCHITECTURE_APPLE_SILICON"
    )


def _classify_power(observation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    settings = observation["ac_power_settings"]
    if settings is None:
        return {
            "ac_sleep_policy": _predicate(
                "ac_sleep_policy", code="AC_SLEEP_UNKNOWN"
            ),
            "auto_restart_after_power_loss": _predicate(
                "auto_restart_after_power_loss",
                code="AUTO_RESTART_UNKNOWN",
            ),
            "auto_restart_on_power_connect": _predicate(
                "auto_restart_on_power_connect",
                code="AUTO_RESTART_ON_CONNECT_UNKNOWN",
            ),
        }

    sleep_value = settings.get("sleep")
    if sleep_value is None:
        sleep_predicate = _predicate(
            "ac_sleep_policy", code="AC_SLEEP_UNKNOWN"
        )
    elif sleep_value == 0:
        sleep_predicate = _predicate(
            "ac_sleep_policy", code="AC_SLEEP_DISABLED"
        )
    else:
        sleep_predicate = _predicate(
            "ac_sleep_policy",
            code="AC_SLEEP_ENABLED",
            measurement=sleep_value,
        )

    restart_value = settings.get("autorestart")
    if restart_value is None:
        restart_predicate = _predicate(
            "auto_restart_after_power_loss",
            code="AUTO_RESTART_UNKNOWN",
        )
    elif restart_value == 1:
        restart_predicate = _predicate(
            "auto_restart_after_power_loss", code="AUTO_RESTART_ENABLED"
        )
    else:
        restart_predicate = _predicate(
            "auto_restart_after_power_loss",
            code="AUTO_RESTART_DISABLED",
        )

    # ``autorestartatconnect`` only governs restarting when AC is reconnected.
    # An always-on desktop on continuous AC recovers from a power cut through
    # ``autorestart``; macOS also exposes this key only on models that support
    # the behavior.  The runbook therefore treats it as preferable, not required.
    connect_value = settings.get("autorestartatconnect")
    if connect_value is None:
        connect_predicate = _predicate(
            "auto_restart_on_power_connect",
            code="AUTO_RESTART_ON_CONNECT_NOT_EXPOSED",
        )
    elif connect_value == 1:
        connect_predicate = _predicate(
            "auto_restart_on_power_connect",
            code="AUTO_RESTART_ON_CONNECT_ENABLED",
        )
    else:
        connect_predicate = _predicate(
            "auto_restart_on_power_connect",
            code="AUTO_RESTART_ON_CONNECT_DISABLED",
        )

    return {
        "ac_sleep_policy": sleep_predicate,
        "auto_restart_after_power_loss": restart_predicate,
        "auto_restart_on_power_connect": connect_predicate,
    }


def _classify_remote_login(observation: Mapping[str, Any]) -> dict[str, Any]:
    observed = observation["remote_login"]
    if observed == "ENABLED":
        return _predicate(
            "remote_login_listener", code="REMOTE_LOGIN_ENABLED"
        )
    if observed == "DISABLED":
        return _predicate(
            "remote_login_listener", code="REMOTE_LOGIN_DISABLED"
        )
    if observed == "NOT_INSTALLED":
        return _predicate(
            "remote_login_listener",
            code="REMOTE_LOGIN_NOT_INSTALLED",
        )
    return _predicate(
        "remote_login_listener", code="REMOTE_LOGIN_UNKNOWN"
    )


def _classify_encryption(observation: Mapping[str, Any]) -> dict[str, Any]:
    return _predicate(
        "disk_encryption_state", code=observation["filevault_code"]
    )


def _classify_preboot_remote_unlock(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Decide whether this host can be unlocked at preboot without a keyboard.

    This is host-local eligibility only.  It never proves that a bastion, a
    tunnel, or any external path can actually reach the host; that remains a
    separate acceptance journey with its own evidence.

    FileVault off needs no preboot unlock at all, so the prerequisite is
    vacuously satisfied.  FileVault on requires the full Apple-silicon remote
    unlock generation: Apple silicon, macOS
    ``MIN_PREBOOT_REMOTE_UNLOCK_MACOS_MAJOR`` or later, and an enabled Remote
    Login listener.  A transitional or unreadable FileVault state cannot be
    decided, and neither can unknown architecture or unparseable version
    evidence, so all of those fail closed to ``UNKNOWN``.  The three
    prerequisites are evaluated in a fixed order — architecture, then OS
    generation, then Remote Login — so one host always yields one code.
    """

    filevault_code = observation["filevault_code"]
    if filevault_code == "FILEVAULT_OFF":
        return _predicate(
            "preboot_remote_unlock",
            code="PREBOOT_UNLOCK_NOT_REQUIRED",
        )
    if filevault_code != "FILEVAULT_ON":
        # Encrypting, decrypting, or unreadable: the preboot boot path this
        # host will actually present is not yet determined.
        return _predicate(
            "preboot_remote_unlock",
            code="PREBOOT_UNLOCK_STATE_UNKNOWN",
        )

    apple_silicon = observation["apple_silicon"]
    if apple_silicon is None:
        return _predicate(
            "preboot_remote_unlock",
            code="PREBOOT_UNLOCK_STATE_UNKNOWN",
        )
    if not apple_silicon:
        return _predicate(
            "preboot_remote_unlock",
            code="PREBOOT_UNLOCK_ARCHITECTURE_UNSUPPORTED",
        )

    major = _macos_major(observation)
    if major is None:
        return _predicate(
            "preboot_remote_unlock",
            code="PREBOOT_UNLOCK_STATE_UNKNOWN",
        )
    if major < MIN_PREBOOT_REMOTE_UNLOCK_MACOS_MAJOR:
        return _predicate(
            "preboot_remote_unlock",
            code="PREBOOT_UNLOCK_OS_GENERATION_UNSUPPORTED",
        )

    remote_login = observation["remote_login"]
    if remote_login == "UNKNOWN":
        return _predicate(
            "preboot_remote_unlock",
            code="PREBOOT_UNLOCK_STATE_UNKNOWN",
        )
    if remote_login != "ENABLED":
        return _predicate(
            "preboot_remote_unlock",
            code="PREBOOT_UNLOCK_REMOTE_LOGIN_UNAVAILABLE",
        )
    return _predicate(
        "preboot_remote_unlock", code="PREBOOT_UNLOCK_SUPPORTED"
    )


_REQUIRED_RUNNING_DAEMON_VERDICTS = {
    "RUNNING": ("OK", "DAEMON_RUNNING"),
    "LOADED_NOT_RUNNING": ("NOT_READY", "DAEMON_LOADED_NOT_RUNNING"),
    "DISABLED": ("NOT_READY", "DAEMON_DISABLED"),
    "NOT_INSTALLED": ("NOT_READY", "DAEMON_NOT_INSTALLED"),
    "UNKNOWN": ("UNKNOWN", "DAEMON_STATE_UNKNOWN"),
}
_REQUIRED_ABSENT_DAEMON_VERDICTS = {
    "RUNNING": ("NOT_READY", "DAEMON_UNEXPECTEDLY_RUNNING"),
    "LOADED_NOT_RUNNING": ("NOT_READY", "DAEMON_LOADED_NOT_RUNNING"),
    "DISABLED": ("NOT_READY", "DAEMON_DISABLED"),
    "NOT_INSTALLED": ("OK", "DAEMON_NOT_INSTALLED"),
    "UNKNOWN": ("UNKNOWN", "DAEMON_STATE_UNKNOWN"),
}
_DISARMED_EXPECTED_DAEMON_VERDICTS = {
    "RUNNING": ("ADVISORY", "DAEMON_UNEXPECTEDLY_RUNNING"),
    "LOADED_NOT_RUNNING": ("OK", "DAEMON_INTENTIONALLY_DISARMED"),
    "DISABLED": ("OK", "DAEMON_INTENTIONALLY_DISARMED"),
    "NOT_INSTALLED": ("OK", "DAEMON_NOT_INSTALLED"),
    "UNKNOWN": ("UNKNOWN", "DAEMON_STATE_UNKNOWN"),
}
# Visibility-only under the physical base profile: every state is reported
# truthfully and none of them can decide, or fail to decide, recoverability.
_ADVISORY_DAEMON_VERDICTS = {
    "RUNNING": ("OK", "DAEMON_RUNNING"),
    "LOADED_NOT_RUNNING": ("ADVISORY", "DAEMON_LOADED_NOT_RUNNING"),
    "DISABLED": ("ADVISORY", "DAEMON_DISABLED"),
    "NOT_INSTALLED": ("ADVISORY", "DAEMON_NOT_INSTALLED"),
    "UNKNOWN": ("UNKNOWN", "DAEMON_STATE_UNKNOWN"),
}
_DAEMON_VERDICTS = {
    "REQUIRED_RUNNING": _REQUIRED_RUNNING_DAEMON_VERDICTS,
    "REQUIRED_ABSENT": _REQUIRED_ABSENT_DAEMON_VERDICTS,
    "DISARMED_EXPECTED": _DISARMED_EXPECTED_DAEMON_VERDICTS,
    "ADVISORY": _ADVISORY_DAEMON_VERDICTS,
}


def _invert_daemon_verdicts(
    verdicts: Mapping[str, tuple[str, str]],
) -> dict[str, str]:
    """Derive the code -> status law for one requirement from its verdict table.

    The verdict tables above stay the single source of daemon semantics; this
    only reads them backwards so the validator can demand the same pairing the
    classifier would have produced.  Two observations may share a code (a
    disarmed service that is loaded-not-running and one that is disabled are
    both intentionally disarmed), but they must then share a status, or the
    table would not define one law and the module refuses to load.
    """

    inverted: dict[str, str] = {}
    for status, code in verdicts.values():
        if inverted.setdefault(code, status) != status:
            raise RecoveryReadinessContractError("DAEMON_VERDICT_TABLE_AMBIGUOUS")
    return inverted


_DAEMON_CODE_STATUSES = {
    requirement: _invert_daemon_verdicts(verdicts)
    for requirement, verdicts in _DAEMON_VERDICTS.items()
}


def _classify_daemons(
    profile: _PredicateProfile, observation: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    observed = observation["system_daemons"]
    predicates: dict[str, dict[str, Any]] = {}
    for label in ALL_DAEMON_LABELS:
        predicate_id = DAEMON_PREDICATE_PREFIX + label
        state = observed.get(label, "UNKNOWN")
        requirement = profile.requirement(predicate_id)
        _, code = _DAEMON_VERDICTS[requirement][state]
        predicates[predicate_id] = _predicate(
            predicate_id, code=code, requirement=requirement
        )
    return predicates


def _classify_user_session(observation: Mapping[str, Any]) -> dict[str, Any]:
    present = observation["user_session_agents_present"]
    if present is None:
        return _predicate(
            "user_session_surfaces",
            code="USER_SESSION_STATE_UNKNOWN",
        )
    code = (
        "USER_SESSION_LOGIN_REQUIRED" if present else "USER_SESSION_AGENTS_ABSENT"
    )
    return _predicate(
        "user_session_surfaces", code=code, measurement=present
    )


def _classify_disk(observation: Mapping[str, Any]) -> dict[str, Any]:
    free_bytes = observation["root_free_bytes"]
    if free_bytes is None:
        return _predicate(
            "disk_free_floor", code="DISK_FREE_UNKNOWN"
        )
    if free_bytes >= DISK_FREE_FLOOR_BYTES:
        return _predicate(
            "disk_free_floor",
            code="DISK_FREE_ABOVE_FLOOR",
            measurement=free_bytes,
        )
    return _predicate(
        "disk_free_floor",
        code="DISK_FREE_BELOW_FLOOR",
        measurement=free_bytes,
    )


def resolve_recovery_state(
    predicates: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[str], list[str]]:
    """Derive the overall state, failing closed on unknown load-bearing evidence."""

    blocking: list[str] = []
    unknown: list[str] = []
    for predicate_id in sorted(predicates):
        predicate = predicates[predicate_id]
        if predicate.get("requirement") not in LOAD_BEARING_REQUIREMENTS:
            continue
        status = predicate.get("status")
        if status == "NOT_READY":
            blocking.append(predicate_id)
        elif status == "UNKNOWN":
            unknown.append(predicate_id)
    if blocking:
        return "NOT_READY", blocking, unknown
    if unknown:
        return "UNKNOWN", blocking, unknown
    return "READY", blocking, unknown


def classify_recovery_readiness(
    observation: Mapping[str, Any], *, profile: Any
) -> dict[str, Any]:
    """Classify one validated observation under one caller-named profile.

    ``profile`` is mandatory and must be one of :data:`READINESS_PROFILES`.  It
    is never inferred from the observation: a Studio whose control plane has
    stopped looks exactly like a worker host that never had one, and guessing
    the weaker profile there would turn a real outage into a pass.
    """

    selected = recovery_profile(profile)
    normalized = _validate_observation(observation)

    predicates: dict[str, dict[str, Any]] = {
        "os_identity": _classify_os_identity(normalized),
        "cpu_architecture": _classify_architecture(normalized),
        "remote_login_listener": _classify_remote_login(normalized),
        "disk_encryption_state": _classify_encryption(normalized),
        "preboot_remote_unlock": _classify_preboot_remote_unlock(normalized),
        "user_session_surfaces": _classify_user_session(normalized),
        "disk_free_floor": _classify_disk(normalized),
    }
    predicates.update(_classify_power(normalized))
    predicates.update(_classify_daemons(selected, normalized))

    stamped = {
        predicate_id: {
            "requirement": selected.requirement(predicate_id),
            "status": predicate["status"],
            "code": predicate["code"],
            "evidence_class": predicate["evidence_class"],
            "measurement": predicate["measurement"],
        }
        for predicate_id, predicate in sorted(predicates.items())
    }

    recovery_state, blocking, unknown = resolve_recovery_state(stamped)
    report = {
        "schema": READINESS_SCHEMA,
        "profile": selected.profile,
        "host_ref": normalized["host_ref"],
        "observed_at_ms": normalized["observed_at_ms"],
        "predicates": stamped,
        "recovery_state": recovery_state,
        "blocking_predicates": blocking,
        "unknown_predicates": unknown,
    }
    return validate_recovery_readiness_report(report, expected_profile=selected.profile)


def validate_recovery_readiness_report(
    value: Mapping[str, Any], *, expected_profile: Any = None
) -> dict[str, Any]:
    """Return a defensive canonical-value copy or refuse the closed contract.

    The report's own ``profile`` must be a known closed profile, and every
    requirement must be exactly the one that profile derives.  A caller that
    knows which profile it asked for passes ``expected_profile``, so a report
    produced under one profile can never be accepted as the other.
    """

    if not isinstance(value, Mapping) or set(value) != REPORT_FIELDS:
        _refuse("REPORT_FIELDS_INVALID")
    if value.get("schema") != READINESS_SCHEMA:
        _refuse("REPORT_SCHEMA_INVALID")
    profile = recovery_profile(value.get("profile"))
    if expected_profile is not None and profile is not recovery_profile(
        expected_profile
    ):
        _refuse("REPORT_PROFILE_MISMATCH")

    host_ref = value.get("host_ref")
    if host_ref is not None and (
        type(host_ref) is not str or HOST_REF_RE.fullmatch(host_ref) is None
    ):
        _refuse("HOST_REF_INVALID")

    observed_at_ms = value.get("observed_at_ms")
    if type(observed_at_ms) is not int or not 1 <= observed_at_ms <= _INT64_MAX:
        _refuse("OBSERVED_AT_INVALID")

    predicates = value.get("predicates")
    if not isinstance(predicates, Mapping) or set(predicates) != set(PREDICATE_CODES):
        _refuse("PREDICATE_SET_INVALID")

    normalized_predicates: dict[str, dict[str, Any]] = {}
    for predicate_id in sorted(predicates):
        predicate = predicates[predicate_id]
        if not isinstance(predicate, Mapping) or set(predicate) != PREDICATE_FIELDS:
            _refuse("PREDICATE_FIELDS_INVALID")
        requirement = predicate.get("requirement")
        if requirement != profile.requirement(predicate_id):
            _refuse("PREDICATE_REQUIREMENT_MISMATCH")
        if predicate.get("evidence_class") != _evidence_class(predicate_id):
            _refuse("PREDICATE_EVIDENCE_CLASS_MISMATCH")
        status = predicate.get("status")
        if status not in STATUSES or status not in _ALLOWED_STATUSES[requirement]:
            _refuse("PREDICATE_STATUS_INVALID")
        code = predicate.get("code")
        if code not in PREDICATE_CODES[predicate_id]:
            _refuse("PREDICATE_CODE_INVALID")
        # Status vocabulary and code vocabulary are not enough: they are only
        # true together.  Re-derive the one status this code may carry under
        # this requirement and demand it, so a forged pass on a failure code is
        # refused before any derived state is trusted.
        if status != _canonical_predicate_status(predicate_id, requirement, code):
            _refuse("PREDICATE_STATUS_CODE_MISMATCH")
        measurement = predicate.get("measurement")
        if measurement is not None and (
            type(measurement) is not int or not 0 <= measurement <= _INT64_MAX
        ):
            _refuse("PREDICATE_MEASUREMENT_INVALID")
        _check_measurement(predicate_id, code, measurement)
        normalized_predicates[predicate_id] = {
            "requirement": requirement,
            "status": status,
            "code": code,
            "evidence_class": predicate["evidence_class"],
            "measurement": measurement,
        }

    recovery_state = value.get("recovery_state")
    if recovery_state not in RECOVERY_STATES:
        _refuse("RECOVERY_STATE_INVALID")
    expected_state, expected_blocking, expected_unknown = resolve_recovery_state(
        normalized_predicates
    )
    if recovery_state != expected_state:
        _refuse("RECOVERY_STATE_MISMATCH")
    if value.get("blocking_predicates") != expected_blocking:
        _refuse("BLOCKING_PREDICATES_MISMATCH")
    if value.get("unknown_predicates") != expected_unknown:
        _refuse("UNKNOWN_PREDICATES_MISMATCH")

    return {
        "schema": READINESS_SCHEMA,
        "profile": profile.profile,
        "host_ref": host_ref,
        "observed_at_ms": observed_at_ms,
        "predicates": normalized_predicates,
        "recovery_state": recovery_state,
        "blocking_predicates": list(expected_blocking),
        "unknown_predicates": list(expected_unknown),
    }


def canonical_recovery_readiness_json(
    value: Mapping[str, Any], *, expected_profile: Any = None
) -> bytes:
    """Render one validated report as bounded canonical UTF-8 JSON."""

    normalized = validate_recovery_readiness_report(
        value, expected_profile=expected_profile
    )
    try:
        rendered = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # defensive; validation owns shape
        raise RecoveryReadinessContractError("REPORT_JSON_INVALID") from exc
    return (rendered + "\n").encode("utf-8")


__all__ = [
    "ALL_DAEMON_LABELS",
    "BASE_RECOVERY_PROFILE",
    "DAEMON_OBSERVATIONS",
    "DAEMON_PREDICATE_PREFIX",
    "DISARMED_EXPECTED_DAEMON_LABELS",
    "DISK_FREE_FLOOR_BYTES",
    "EVIDENCE_CLASSES",
    "EXECUTIVE_CONTROL_PROFILE",
    "FILEVAULT_CODES",
    "HOST_REF_RE",
    "LOAD_BEARING_REQUIREMENTS",
    "MIN_PREBOOT_REMOTE_UNLOCK_MACOS_MAJOR",
    "MIN_SUPPORTED_MACOS_MAJOR",
    "OBSERVATION_FIELDS",
    "PREDICATE_CODES",
    "PREDICATE_CODE_STATUSES",
    "PREDICATE_EVIDENCE_CLASSES",
    "PREDICATE_FIELDS",
    "PREDICATE_MEASUREMENT_LAW",
    "PREDICATE_IDS",
    "READINESS_PROFILES",
    "READINESS_SCHEMA",
    "RECOVERY_PROFILES",
    "REMOTE_LOGIN_OBSERVATIONS",
    "REPORT_FIELDS",
    "REQUIRED_RUNNING_DAEMON_LABELS",
    "REQUIREMENTS",
    "RECOVERY_STATES",
    "STATUSES",
    "USER_SESSION_CRITICAL_LABELS",
    "RecoveryReadinessContractError",
    "canonical_recovery_readiness_json",
    "classify_recovery_readiness",
    "recovery_profile",
    "resolve_recovery_state",
    "validate_recovery_readiness_report",
]

"""Closed, read-only host recovery-readiness evidence contract.

This module answers exactly one question about one already-observed Mastermind
home Mac: after an unattended power loss or reboot, does the host come back far
enough for Executive work to resume without a human at the keyboard?

It validates and classifies one bounded observation produced elsewhere.  It does
not sample hosts, invoke commands, mutate power/service/encryption state, keep a
registry of hosts, schedule or gate execution, or persist anything.  Collection
and command invocation belong to ``ops/executive_os/host_recovery_readiness.py``;
privileged remediation remains with the reviewed broker owner.

Profile semantics (``always-on-executive-host/v1``) are deliberately explicit:

``REQUIRED`` / ``REQUIRED_RUNNING``
    Load-bearing.  An unsatisfied or unknown predicate changes the overall
    recovery state.
``OPTIONAL``
    Reviewed-as-preferable but not load-bearing for unattended recovery.
``DISARMED_EXPECTED``
    The profile expects this service to be absent or disabled right now.  Its
    absence is the intended gate state, never a defect.
``ADVISORY``
    Reported because an operator must know it, but it cannot decide readiness.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


READINESS_SCHEMA = "mastermind.host_recovery_readiness/v1"
READINESS_PROFILE = "always-on-executive-host/v1"

# Reviewed floor: the preboot recovery profile below is only reviewed against
# macOS 14+ on Apple silicon.  Raise it deliberately, never infer it.
MIN_SUPPORTED_MACOS_MAJOR = 14

# Reviewed free-space floor for an unattended host that must survive a cold boot
# plus log, snapshot and release growth without a human freeing space.
DISK_FREE_FLOOR_BYTES = 25 * 1024**3

HOST_REF_RE = re.compile(r"^host-[0-9a-f]{64}$")

REQUIREMENTS = frozenset(
    {"REQUIRED", "REQUIRED_RUNNING", "OPTIONAL", "DISARMED_EXPECTED", "ADVISORY"}
)
LOAD_BEARING_REQUIREMENTS = frozenset({"REQUIRED", "REQUIRED_RUNNING"})
STATUSES = frozenset({"OK", "NOT_READY", "UNKNOWN", "ADVISORY", "NOT_APPLICABLE"})
RECOVERY_STATES = frozenset({"READY", "NOT_READY", "UNKNOWN"})
EVIDENCE_CLASSES = frozenset(
    {
        "SYSTEM_PLATFORM",
        "POWER_POLICY",
        "REMOTE_ACCESS_POLICY",
        "DISK_ENCRYPTION_STATE",
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
# for an unattended host to be useful after boot.
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

_BASE_PREDICATES: dict[str, tuple[str, str, frozenset[str]]] = {
    "os_identity": (
        "REQUIRED",
        "SYSTEM_PLATFORM",
        frozenset(
            {
                "OS_SUPPORTED",
                "OS_UNSUPPORTED_VERSION",
                "OS_NOT_DARWIN",
                "OS_IDENTITY_UNKNOWN",
            }
        ),
    ),
    "cpu_architecture": (
        "REQUIRED",
        "SYSTEM_PLATFORM",
        frozenset(
            {
                "ARCHITECTURE_APPLE_SILICON",
                "ARCHITECTURE_UNSUPPORTED",
                "ARCHITECTURE_UNKNOWN",
            }
        ),
    ),
    "ac_sleep_policy": (
        "REQUIRED",
        "POWER_POLICY",
        frozenset({"AC_SLEEP_DISABLED", "AC_SLEEP_ENABLED", "AC_SLEEP_UNKNOWN"}),
    ),
    "auto_restart_after_power_loss": (
        "REQUIRED",
        "POWER_POLICY",
        frozenset(
            {"AUTO_RESTART_ENABLED", "AUTO_RESTART_DISABLED", "AUTO_RESTART_UNKNOWN"}
        ),
    ),
    "auto_restart_on_power_connect": (
        "OPTIONAL",
        "POWER_POLICY",
        frozenset(
            {
                "AUTO_RESTART_ON_CONNECT_ENABLED",
                "AUTO_RESTART_ON_CONNECT_DISABLED",
                "AUTO_RESTART_ON_CONNECT_NOT_EXPOSED",
                "AUTO_RESTART_ON_CONNECT_UNKNOWN",
            }
        ),
    ),
    "remote_login_listener": (
        "REQUIRED",
        "REMOTE_ACCESS_POLICY",
        frozenset(
            {
                "REMOTE_LOGIN_ENABLED",
                "REMOTE_LOGIN_DISABLED",
                "REMOTE_LOGIN_NOT_INSTALLED",
                "REMOTE_LOGIN_UNKNOWN",
            }
        ),
    ),
    "disk_encryption_state": (
        "ADVISORY",
        "DISK_ENCRYPTION_STATE",
        frozenset(FILEVAULT_CODES),
    ),
    "user_session_surfaces": (
        "ADVISORY",
        "USER_SESSION_DEPENDENCY",
        frozenset(
            {
                "USER_SESSION_LOGIN_REQUIRED",
                "USER_SESSION_AGENTS_ABSENT",
                "USER_SESSION_STATE_UNKNOWN",
            }
        ),
    ),
    "disk_free_floor": (
        "REQUIRED",
        "FILESYSTEM_CAPACITY",
        frozenset(
            {"DISK_FREE_ABOVE_FLOOR", "DISK_FREE_BELOW_FLOOR", "DISK_FREE_UNKNOWN"}
        ),
    ),
}


class _PredicateProfile:
    """The frozen requirement/evidence table for one readiness profile."""

    def __init__(self) -> None:
        self.required_running_labels = REQUIRED_RUNNING_DAEMON_LABELS
        self.disarmed_expected_labels = DISARMED_EXPECTED_DAEMON_LABELS
        self.all_daemon_labels = tuple(
            sorted(REQUIRED_RUNNING_DAEMON_LABELS + DISARMED_EXPECTED_DAEMON_LABELS)
        )
        table: dict[str, tuple[str, str, frozenset[str]]] = dict(_BASE_PREDICATES)
        for label in REQUIRED_RUNNING_DAEMON_LABELS:
            table[DAEMON_PREDICATE_PREFIX + label] = (
                "REQUIRED_RUNNING",
                "SYSTEM_SERVICE_STATE",
                _DAEMON_CODES,
            )
        for label in DISARMED_EXPECTED_DAEMON_LABELS:
            table[DAEMON_PREDICATE_PREFIX + label] = (
                "DISARMED_EXPECTED",
                "SYSTEM_SERVICE_STATE",
                _DAEMON_CODES,
            )
        self._table = table

    def requirement(self, predicate_id: str) -> str:
        return self._entry(predicate_id)[0]

    def evidence_class(self, predicate_id: str) -> str:
        return self._entry(predicate_id)[1]

    def codes(self, predicate_id: str) -> frozenset[str]:
        return self._entry(predicate_id)[2]

    def predicate_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._table))

    def _entry(self, predicate_id: str) -> tuple[str, str, frozenset[str]]:
        entry = self._table.get(predicate_id)
        if entry is None:
            _refuse("PREDICATE_UNKNOWN")
        return entry


class RecoveryReadinessContractError(ValueError):
    """A closed, non-secret recovery-readiness contract refusal."""


def _refuse(code: str) -> Any:
    raise RecoveryReadinessContractError(code)


PREDICATE_PROFILE = _PredicateProfile()
PREDICATE_CODES = {
    predicate_id: PREDICATE_PROFILE.codes(predicate_id)
    for predicate_id in PREDICATE_PROFILE.predicate_ids()
}
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
    "OPTIONAL": frozenset({"OK", "ADVISORY", "UNKNOWN", "NOT_APPLICABLE"}),
    "DISARMED_EXPECTED": frozenset({"OK", "ADVISORY", "UNKNOWN"}),
    "ADVISORY": frozenset({"OK", "ADVISORY", "UNKNOWN"}),
}
_MACOS_VERSION_RE = re.compile(r"^(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,4}){0,3}$")
_INT64_MAX = (1 << 63) - 1


def _predicate(
    predicate_id: str,
    *,
    status: str,
    code: str,
    measurement: int | None = None,
) -> dict[str, Any]:
    return {
        "requirement": PREDICATE_PROFILE.requirement(predicate_id),
        "status": status,
        "code": code,
        "evidence_class": PREDICATE_PROFILE.evidence_class(predicate_id),
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
        if label not in PREDICATE_PROFILE.all_daemon_labels:
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


def _classify_os_identity(observation: Mapping[str, Any]) -> dict[str, Any]:
    os_name = observation["os_name"]
    version = observation["macos_product_version"]
    if os_name is None:
        return _predicate("os_identity", status="UNKNOWN", code="OS_IDENTITY_UNKNOWN")
    if os_name != "Darwin":
        return _predicate("os_identity", status="NOT_READY", code="OS_NOT_DARWIN")
    if version is None or _MACOS_VERSION_RE.fullmatch(version) is None:
        return _predicate("os_identity", status="UNKNOWN", code="OS_IDENTITY_UNKNOWN")
    major = int(version.split(".", 1)[0])
    if major < MIN_SUPPORTED_MACOS_MAJOR:
        return _predicate(
            "os_identity", status="NOT_READY", code="OS_UNSUPPORTED_VERSION"
        )
    return _predicate("os_identity", status="OK", code="OS_SUPPORTED")


def _classify_architecture(observation: Mapping[str, Any]) -> dict[str, Any]:
    apple_silicon = observation["apple_silicon"]
    if apple_silicon is None:
        return _predicate(
            "cpu_architecture", status="UNKNOWN", code="ARCHITECTURE_UNKNOWN"
        )
    if not apple_silicon:
        return _predicate(
            "cpu_architecture", status="NOT_READY", code="ARCHITECTURE_UNSUPPORTED"
        )
    return _predicate(
        "cpu_architecture", status="OK", code="ARCHITECTURE_APPLE_SILICON"
    )


def _classify_power(observation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    settings = observation["ac_power_settings"]
    if settings is None:
        return {
            "ac_sleep_policy": _predicate(
                "ac_sleep_policy", status="UNKNOWN", code="AC_SLEEP_UNKNOWN"
            ),
            "auto_restart_after_power_loss": _predicate(
                "auto_restart_after_power_loss",
                status="UNKNOWN",
                code="AUTO_RESTART_UNKNOWN",
            ),
            "auto_restart_on_power_connect": _predicate(
                "auto_restart_on_power_connect",
                status="UNKNOWN",
                code="AUTO_RESTART_ON_CONNECT_UNKNOWN",
            ),
        }

    sleep_value = settings.get("sleep")
    if sleep_value is None:
        sleep_predicate = _predicate(
            "ac_sleep_policy", status="UNKNOWN", code="AC_SLEEP_UNKNOWN"
        )
    elif sleep_value == 0:
        sleep_predicate = _predicate(
            "ac_sleep_policy", status="OK", code="AC_SLEEP_DISABLED"
        )
    else:
        sleep_predicate = _predicate(
            "ac_sleep_policy",
            status="NOT_READY",
            code="AC_SLEEP_ENABLED",
            measurement=sleep_value,
        )

    restart_value = settings.get("autorestart")
    if restart_value is None:
        restart_predicate = _predicate(
            "auto_restart_after_power_loss",
            status="UNKNOWN",
            code="AUTO_RESTART_UNKNOWN",
        )
    elif restart_value == 1:
        restart_predicate = _predicate(
            "auto_restart_after_power_loss", status="OK", code="AUTO_RESTART_ENABLED"
        )
    else:
        restart_predicate = _predicate(
            "auto_restart_after_power_loss",
            status="NOT_READY",
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
            status="NOT_APPLICABLE",
            code="AUTO_RESTART_ON_CONNECT_NOT_EXPOSED",
        )
    elif connect_value == 1:
        connect_predicate = _predicate(
            "auto_restart_on_power_connect",
            status="OK",
            code="AUTO_RESTART_ON_CONNECT_ENABLED",
        )
    else:
        connect_predicate = _predicate(
            "auto_restart_on_power_connect",
            status="ADVISORY",
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
            "remote_login_listener", status="OK", code="REMOTE_LOGIN_ENABLED"
        )
    if observed == "DISABLED":
        return _predicate(
            "remote_login_listener", status="NOT_READY", code="REMOTE_LOGIN_DISABLED"
        )
    if observed == "NOT_INSTALLED":
        return _predicate(
            "remote_login_listener",
            status="NOT_READY",
            code="REMOTE_LOGIN_NOT_INSTALLED",
        )
    return _predicate(
        "remote_login_listener", status="UNKNOWN", code="REMOTE_LOGIN_UNKNOWN"
    )


def _classify_encryption(observation: Mapping[str, Any]) -> dict[str, Any]:
    code = observation["filevault_code"]
    if code == "FILEVAULT_OFF":
        status = "OK"
    elif code == "FILEVAULT_STATE_UNKNOWN":
        status = "UNKNOWN"
    else:
        # Encrypted volumes need a preboot unlock, so an unattended boot reaches
        # the login window rather than a usable session.  That is an operator
        # fact, not a readiness defect, and the required autorestart predicate
        # above is what proves the machine returns at all.
        status = "ADVISORY"
    return _predicate("disk_encryption_state", status=status, code=code)


def _classify_daemons(observation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    observed = observation["system_daemons"]
    predicates: dict[str, dict[str, Any]] = {}
    for label in PREDICATE_PROFILE.all_daemon_labels:
        predicate_id = DAEMON_PREDICATE_PREFIX + label
        state = observed.get(label, "UNKNOWN")
        requirement = PREDICATE_PROFILE.requirement(predicate_id)
        if requirement == "REQUIRED_RUNNING":
            status, code = {
                "RUNNING": ("OK", "DAEMON_RUNNING"),
                "LOADED_NOT_RUNNING": ("NOT_READY", "DAEMON_LOADED_NOT_RUNNING"),
                "DISABLED": ("NOT_READY", "DAEMON_DISABLED"),
                "NOT_INSTALLED": ("NOT_READY", "DAEMON_NOT_INSTALLED"),
                "UNKNOWN": ("UNKNOWN", "DAEMON_STATE_UNKNOWN"),
            }[state]
        else:
            status, code = {
                "RUNNING": ("ADVISORY", "DAEMON_UNEXPECTEDLY_RUNNING"),
                "LOADED_NOT_RUNNING": ("OK", "DAEMON_INTENTIONALLY_DISARMED"),
                "DISABLED": ("OK", "DAEMON_INTENTIONALLY_DISARMED"),
                "NOT_INSTALLED": ("OK", "DAEMON_NOT_INSTALLED"),
                "UNKNOWN": ("UNKNOWN", "DAEMON_STATE_UNKNOWN"),
            }[state]
        predicates[predicate_id] = _predicate(predicate_id, status=status, code=code)
    return predicates


def _classify_user_session(observation: Mapping[str, Any]) -> dict[str, Any]:
    present = observation["user_session_agents_present"]
    if present is None:
        return _predicate(
            "user_session_surfaces",
            status="UNKNOWN",
            code="USER_SESSION_STATE_UNKNOWN",
        )
    code = (
        "USER_SESSION_LOGIN_REQUIRED" if present else "USER_SESSION_AGENTS_ABSENT"
    )
    return _predicate(
        "user_session_surfaces", status="ADVISORY", code=code, measurement=present
    )


def _classify_disk(observation: Mapping[str, Any]) -> dict[str, Any]:
    free_bytes = observation["root_free_bytes"]
    if free_bytes is None:
        return _predicate(
            "disk_free_floor", status="UNKNOWN", code="DISK_FREE_UNKNOWN"
        )
    if free_bytes >= DISK_FREE_FLOOR_BYTES:
        return _predicate(
            "disk_free_floor",
            status="OK",
            code="DISK_FREE_ABOVE_FLOOR",
            measurement=free_bytes,
        )
    return _predicate(
        "disk_free_floor",
        status="NOT_READY",
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


def classify_recovery_readiness(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one validated observation into the closed readiness report."""

    normalized = _validate_observation(observation)

    predicates: dict[str, dict[str, Any]] = {
        "os_identity": _classify_os_identity(normalized),
        "cpu_architecture": _classify_architecture(normalized),
        "remote_login_listener": _classify_remote_login(normalized),
        "disk_encryption_state": _classify_encryption(normalized),
        "user_session_surfaces": _classify_user_session(normalized),
        "disk_free_floor": _classify_disk(normalized),
    }
    predicates.update(_classify_power(normalized))
    predicates.update(_classify_daemons(normalized))

    recovery_state, blocking, unknown = resolve_recovery_state(predicates)
    report = {
        "schema": READINESS_SCHEMA,
        "profile": READINESS_PROFILE,
        "host_ref": normalized["host_ref"],
        "observed_at_ms": normalized["observed_at_ms"],
        "predicates": predicates,
        "recovery_state": recovery_state,
        "blocking_predicates": blocking,
        "unknown_predicates": unknown,
    }
    return validate_recovery_readiness_report(report)


def validate_recovery_readiness_report(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive canonical-value copy or refuse the closed contract."""

    if not isinstance(value, Mapping) or set(value) != REPORT_FIELDS:
        _refuse("REPORT_FIELDS_INVALID")
    if value.get("schema") != READINESS_SCHEMA:
        _refuse("REPORT_SCHEMA_INVALID")
    if value.get("profile") != READINESS_PROFILE:
        _refuse("REPORT_PROFILE_INVALID")

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
        if requirement != PREDICATE_PROFILE.requirement(predicate_id):
            _refuse("PREDICATE_REQUIREMENT_MISMATCH")
        if predicate.get("evidence_class") != PREDICATE_PROFILE.evidence_class(
            predicate_id
        ):
            _refuse("PREDICATE_EVIDENCE_CLASS_MISMATCH")
        status = predicate.get("status")
        if status not in STATUSES or status not in _ALLOWED_STATUSES[requirement]:
            _refuse("PREDICATE_STATUS_INVALID")
        code = predicate.get("code")
        if code not in PREDICATE_CODES[predicate_id]:
            _refuse("PREDICATE_CODE_INVALID")
        measurement = predicate.get("measurement")
        if measurement is not None and (
            type(measurement) is not int or not 0 <= measurement <= _INT64_MAX
        ):
            _refuse("PREDICATE_MEASUREMENT_INVALID")
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
        "profile": READINESS_PROFILE,
        "host_ref": host_ref,
        "observed_at_ms": observed_at_ms,
        "predicates": normalized_predicates,
        "recovery_state": recovery_state,
        "blocking_predicates": list(expected_blocking),
        "unknown_predicates": list(expected_unknown),
    }


def canonical_recovery_readiness_json(value: Mapping[str, Any]) -> bytes:
    """Render one validated report as bounded canonical UTF-8 JSON."""

    normalized = validate_recovery_readiness_report(value)
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
    "DAEMON_OBSERVATIONS",
    "DAEMON_PREDICATE_PREFIX",
    "DISARMED_EXPECTED_DAEMON_LABELS",
    "DISK_FREE_FLOOR_BYTES",
    "EVIDENCE_CLASSES",
    "FILEVAULT_CODES",
    "HOST_REF_RE",
    "LOAD_BEARING_REQUIREMENTS",
    "MIN_SUPPORTED_MACOS_MAJOR",
    "OBSERVATION_FIELDS",
    "PREDICATE_CODES",
    "PREDICATE_FIELDS",
    "PREDICATE_PROFILE",
    "READINESS_PROFILE",
    "READINESS_SCHEMA",
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
    "resolve_recovery_state",
    "validate_recovery_readiness_report",
]

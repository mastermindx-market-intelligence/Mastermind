"""Model-free tests for the read-only host recovery-readiness vertical."""
from __future__ import annotations

import inspect
import io
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from control_plane.executive_recovery_readiness import (
    ALL_DAEMON_LABELS,
    BASE_RECOVERY_PROFILE,
    DAEMON_OBSERVATIONS,
    DISARMED_EXPECTED_DAEMON_LABELS,
    DISK_FREE_FLOOR_BYTES,
    EVIDENCE_CLASSES,
    EXECUTIVE_CONTROL_PROFILE,
    LOAD_BEARING_REQUIREMENTS,
    MIN_PREBOOT_REMOTE_UNLOCK_MACOS_MAJOR,
    MIN_SUPPORTED_MACOS_MAJOR,
    PREDICATE_CODES,
    PREDICATE_EVIDENCE_CLASSES,
    PREDICATE_IDS,
    PREDICATE_MEASUREMENT_LAW,
    READINESS_PROFILES,
    READINESS_SCHEMA,
    REPORT_FIELDS,
    REQUIRED_RUNNING_DAEMON_LABELS,
    USER_SESSION_CRITICAL_LABELS,
    RecoveryReadinessContractError,
    canonical_recovery_readiness_json,
    classify_recovery_readiness,
    recovery_profile,
    resolve_recovery_state,
    validate_recovery_readiness_report,
)
from ops.executive_os import host_recovery_readiness as probe_module
from ops.executive_os.host_recovery_readiness import (
    FDESETUP_STATUS_COMMAND,
    LAUNCHCTL_PRINT_DISABLED_COMMAND,
    PMSET_CUSTOM_COMMAND,
    READ_ONLY_COMMANDS,
    SSHD_LABEL,
    SSHD_SYSTEM_PLIST,
    SW_VERS_COMMAND,
    SYSCTL_ARM64_COMMAND,
    RecoveryReadinessProbeError,
    collect_recovery_observation,
    launchctl_print_command,
    main,
    parse_fdesetup_status,
    parse_launchctl_print_disabled,
    parse_launchctl_print_state,
    parse_pmset_custom,
    system_daemon_plist_path,
)


HOST_REF = "host-" + "c" * 64

PMSET_STUDIO = """AC Power:
 Sleep On Power Button 1
 autorestartatconnect 0
 lowpowermode         0
 standby              0
 ttyskeepawake        1
 powernap             1
 displaysleep         0
 womp                 1
 networkoversleep     0
 sleep                0
 tcpkeepalive         1
 autorestart          0
 disksleep            0
"""

PMSET_READY = """AC Power:
 sleep                0
 autorestart          1
 autorestartatconnect 1
 displaysleep         0

Battery Power:
 sleep                5
 autorestart          0
"""

LAUNCHCTL_DISABLED_STUDIO = """disabled services = {
\t\t"com.mastermind.executive.worker.codex-pro-02" => disabled
\t\t"com.mastermind.executive.worker.codex-pro-03" => disabled
\t\t"com.openssh.sshd" => enabled
\t\t"com.mastermind.executive.mcp" => enabled
\t\t"com.mastermind.executive.backup" => disabled
\t\t"com.mastermind.executive.sol-state-relay" => enabled
\t\t"com.mastermind.executive.worker.codex" => disabled
\t\t"com.mastermind.executive.worker.codex-pro-01" => disabled
\t\t"com.mastermind.executive.control" => enabled
}
"""


def _studio_daemons() -> dict[str, str]:
    states = {label: "DISABLED" for label in DISARMED_EXPECTED_DAEMON_LABELS}
    states["com.mastermind.executive.privileged"] = "NOT_INSTALLED"
    for label in REQUIRED_RUNNING_DAEMON_LABELS:
        states[label] = "RUNNING"
    return states


def _classify(
    observation: dict[str, Any], profile: str = EXECUTIVE_CONTROL_PROFILE
) -> dict[str, Any]:
    """Classify under the Executive control-host profile unless asked otherwise."""

    return classify_recovery_readiness(observation, profile=profile)


def _observation(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "host_ref": HOST_REF,
        "observed_at_ms": 1_789_000_000_000,
        "os_name": "Darwin",
        "macos_product_version": "26.5",
        "apple_silicon": True,
        "ac_power_settings": {"sleep": 0, "autorestart": 1, "autorestartatconnect": 1},
        "filevault_code": "FILEVAULT_OFF",
        "remote_login": "ENABLED",
        "system_daemons": {
            label: "RUNNING" for label in REQUIRED_RUNNING_DAEMON_LABELS
        }
        | {
            label: "NOT_INSTALLED"
            for label in DISARMED_EXPECTED_DAEMON_LABELS
        },
        "user_session_agents_present": len(USER_SESSION_CRITICAL_LABELS),
        "root_free_bytes": DISK_FREE_FLOOR_BYTES * 4,
    }
    base.update(overrides)
    return base


def _studio_observation(**overrides: Any) -> dict[str, Any]:
    studio: dict[str, Any] = {
        "ac_power_settings": {
            "sleep": 0,
            "autorestart": 0,
            "autorestartatconnect": 0,
        },
        "filevault_code": "FILEVAULT_ON",
        "system_daemons": _studio_daemons(),
    }
    studio.update(overrides)
    return _observation(**studio)


def _m1_observation(**overrides: Any) -> dict[str, Any]:
    """An Apple-silicon laptop on macOS 15 with FileVault off and safe power."""

    m1: dict[str, Any] = {
        "macos_product_version": "15.6",
        "apple_silicon": True,
        "ac_power_settings": {"sleep": 0, "autorestart": 1, "autorestartatconnect": 1},
        "filevault_code": "FILEVAULT_OFF",
        "remote_login": "ENABLED",
    }
    m1.update(overrides)
    return _observation(**m1)


def _m1_worker_observation(**overrides: Any) -> dict[str, Any]:
    """An M1-like host with safe physical state and no Executive control plane.

    A worker or capacity host must not run a duplicate Executive control plane,
    so every Executive system label is legitimately absent here.
    """

    worker: dict[str, Any] = {
        "system_daemons": {label: "NOT_INSTALLED" for label in ALL_DAEMON_LABELS},
    }
    worker.update(overrides)
    return _m1_observation(**worker)


def _completed(
    command: tuple[str, ...],
    *,
    returncode: int = 0,
    stdout: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, "")


def _blocking(report: dict[str, Any]) -> list[str]:
    return report["blocking_predicates"]


# ---------------------------------------------------------------- contract


def test_report_contract_is_closed_and_canonical() -> None:
    report = _classify(_observation())

    assert set(report) == REPORT_FIELDS
    assert report["schema"] == READINESS_SCHEMA
    assert report["profile"] == EXECUTIVE_CONTROL_PROFILE
    assert set(report["predicates"]) == set(PREDICATE_CODES)

    normalized = validate_recovery_readiness_report(report)
    assert normalized == report
    assert normalized is not report

    payload = canonical_recovery_readiness_json(report)
    assert payload.endswith(b"\n")
    assert not payload.endswith(b"\n\n")
    assert json.loads(payload) == report
    assert payload == (
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def test_every_predicate_declares_reviewed_requirement_and_evidence_class() -> None:
    report = _classify(_observation())

    profile = recovery_profile(EXECUTIVE_CONTROL_PROFILE)
    for predicate_id, predicate in report["predicates"].items():
        assert predicate["requirement"] == profile.requirement(predicate_id)
        assert predicate["evidence_class"] == PREDICATE_EVIDENCE_CLASSES[predicate_id]
        assert predicate["code"] in PREDICATE_CODES[predicate_id]


def test_unclosed_report_field_is_refused() -> None:
    report = _classify(_observation())
    report["extra_field"] = 1

    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(report)
    assert str(excinfo.value) == "REPORT_FIELDS_INVALID"


def test_derived_recovery_state_mismatch_is_refused() -> None:
    report = _classify(_studio_observation())
    assert report["recovery_state"] == "NOT_READY"
    report["recovery_state"] = "READY"

    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(report)
    assert str(excinfo.value) == "RECOVERY_STATE_MISMATCH"


def test_host_ref_must_be_opaque_or_absent() -> None:
    report = _classify(_observation(host_ref=None))
    assert report["host_ref"] is None

    with pytest.raises(RecoveryReadinessContractError):
        _classify(_observation(host_ref="studio.local"))


# --------------------------------------------------------- host-role profiles


def test_worker_host_is_ready_under_base_profile_without_any_executive_daemon() -> None:
    report = _classify(_m1_worker_observation(), BASE_RECOVERY_PROFILE)

    assert report["profile"] == BASE_RECOVERY_PROFILE
    assert report["recovery_state"] == "READY"
    assert _blocking(report) == []
    assert report["unknown_predicates"] == []

    for label in ALL_DAEMON_LABELS:
        predicate = report["predicates"][f"system_daemon.{label}"]
        assert predicate["requirement"] == "ADVISORY"
        assert predicate["requirement"] not in LOAD_BEARING_REQUIREMENTS
        assert predicate["status"] == "ADVISORY"
        # Truthful: the service is not installed.  It is deliberately not
        # called "intentionally disarmed", which would imply it belongs here.
        assert predicate["code"] == "DAEMON_NOT_INSTALLED"


def test_same_worker_observation_is_not_ready_under_control_profile() -> None:
    observation = _m1_worker_observation()

    base = _classify(observation, BASE_RECOVERY_PROFILE)
    control = _classify(observation, EXECUTIVE_CONTROL_PROFILE)

    assert base["recovery_state"] == "READY"
    assert control["recovery_state"] == "NOT_READY"
    assert _blocking(control) == [
        f"system_daemon.{label}" for label in sorted(REQUIRED_RUNNING_DAEMON_LABELS)
    ]
    assert control["unknown_predicates"] == []
    for label in REQUIRED_RUNNING_DAEMON_LABELS:
        predicate = control["predicates"][f"system_daemon.{label}"]
        assert predicate["requirement"] == "REQUIRED_RUNNING"
        assert predicate["code"] == "DAEMON_NOT_INSTALLED"


@pytest.mark.parametrize("state", ["NOT_INSTALLED", "DISABLED", "LOADED_NOT_RUNNING"])
def test_absent_or_stopped_executive_daemons_never_move_the_base_profile(
    state: str,
) -> None:
    report = _classify(
        _m1_worker_observation(
            system_daemons={label: state for label in ALL_DAEMON_LABELS}
        ),
        BASE_RECOVERY_PROFILE,
    )

    assert report["recovery_state"] == "READY"
    assert _blocking(report) == []
    assert report["unknown_predicates"] == []


def test_unknown_executive_daemon_state_cannot_make_the_base_profile_unknown() -> None:
    report = _classify(
        _m1_worker_observation(system_daemons={}), BASE_RECOVERY_PROFILE
    )

    assert report["recovery_state"] == "READY"
    assert report["unknown_predicates"] == []
    for label in ALL_DAEMON_LABELS:
        predicate = report["predicates"][f"system_daemon.{label}"]
        assert predicate["status"] == "UNKNOWN"
        assert predicate["code"] == "DAEMON_STATE_UNKNOWN"


def test_base_profile_still_reports_real_physical_defects_on_a_worker_host() -> None:
    """The current live M1: no autorestart, Remote Login off, no Executive daemons."""

    report = _classify(
        _m1_worker_observation(
            ac_power_settings={"sleep": 0, "autorestart": 0, "autorestartatconnect": 0},
            remote_login="DISABLED",
        ),
        BASE_RECOVERY_PROFILE,
    )

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == [
        "auto_restart_after_power_loss",
        "remote_login_listener",
    ]
    assert not any(
        predicate_id.startswith("system_daemon.")
        for predicate_id in _blocking(report)
    )


def test_base_profile_on_studio_reports_physical_defect_but_is_not_control_acceptance(
) -> None:
    observation = _studio_observation()

    base = _classify(observation, BASE_RECOVERY_PROFILE)
    control = _classify(observation, EXECUTIVE_CONTROL_PROFILE)

    assert base["recovery_state"] == "NOT_READY"
    assert _blocking(base) == ["auto_restart_after_power_loss"]
    # The base report says nothing about the Executive control plane, so it can
    # never be read as control-host acceptance even when it is otherwise green.
    green_base = _classify(
        _studio_observation(
            ac_power_settings={"sleep": 0, "autorestart": 1, "autorestartatconnect": 0}
        ),
        BASE_RECOVERY_PROFILE,
    )
    assert green_base["recovery_state"] == "READY"
    for label in REQUIRED_RUNNING_DAEMON_LABELS:
        assert (
            green_base["predicates"][f"system_daemon.{label}"]["requirement"]
            == "ADVISORY"
        )
        assert (
            control["predicates"][f"system_daemon.{label}"]["requirement"]
            == "REQUIRED_RUNNING"
        )


def test_a_stopped_studio_control_plane_cannot_pass_under_the_control_profile() -> None:
    """The reason no profile is inferred: a broken Studio looks like a worker."""

    daemons = _studio_daemons()
    daemons["com.mastermind.executive.control"] = "LOADED_NOT_RUNNING"
    report = _classify(
        _studio_observation(
            ac_power_settings={"sleep": 0, "autorestart": 1, "autorestartatconnect": 0},
            system_daemons=daemons,
        )
    )

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["system_daemon.com.mastermind.executive.control"]


def test_unknown_profile_is_refused_with_a_closed_code() -> None:
    for profile in (None, "", "always-on-executive-host/v1", 1, BASE_RECOVERY_PROFILE.upper()):
        with pytest.raises(RecoveryReadinessContractError) as excinfo:
            classify_recovery_readiness(_observation(), profile=profile)
        assert str(excinfo.value) == "PROFILE_UNKNOWN"


def test_profile_is_mandatory_and_never_positional() -> None:
    with pytest.raises(TypeError):
        classify_recovery_readiness(_observation())  # type: ignore[call-arg]


def test_gated_services_keep_disarmed_semantics_under_the_control_profile() -> None:
    report = _classify(_studio_observation())

    for label in DISARMED_EXPECTED_DAEMON_LABELS:
        predicate = report["predicates"][f"system_daemon.{label}"]
        assert predicate["requirement"] == "DISARMED_EXPECTED"
        assert predicate["status"] == "OK"


# --------------------------------------------------- cross-profile validation


def test_report_produced_under_one_profile_is_not_valid_as_the_other() -> None:
    observation = _m1_worker_observation()
    base = _classify(observation, BASE_RECOVERY_PROFILE)
    control = _classify(observation, EXECUTIVE_CONTROL_PROFILE)

    assert validate_recovery_readiness_report(
        base, expected_profile=BASE_RECOVERY_PROFILE
    ) == base
    assert validate_recovery_readiness_report(
        control, expected_profile=EXECUTIVE_CONTROL_PROFILE
    ) == control

    for report, wrong_profile in (
        (base, EXECUTIVE_CONTROL_PROFILE),
        (control, BASE_RECOVERY_PROFILE),
    ):
        with pytest.raises(RecoveryReadinessContractError) as excinfo:
            validate_recovery_readiness_report(report, expected_profile=wrong_profile)
        assert str(excinfo.value) == "REPORT_PROFILE_MISMATCH"


def test_profile_field_tampering_is_refused_by_the_validator() -> None:
    base = _classify(_m1_worker_observation(), BASE_RECOVERY_PROFILE)
    base["profile"] = EXECUTIVE_CONTROL_PROFILE

    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(base)
    assert str(excinfo.value) == "PREDICATE_REQUIREMENT_MISMATCH"


def test_cross_profile_requirement_substitution_is_refused() -> None:
    """Relabelling one control daemon as advisory cannot buy a Studio a pass."""

    report = _classify(_studio_observation())
    predicate = report["predicates"]["system_daemon.com.mastermind.executive.control"]
    predicate["requirement"] = "ADVISORY"
    predicate["status"] = "ADVISORY"

    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(report)
    assert str(excinfo.value) == "PREDICATE_REQUIREMENT_MISMATCH"


@pytest.mark.parametrize("profile", [None, "", "always-on-executive-host/v1"])
def test_unknown_report_profile_is_refused(profile: Any) -> None:
    report = _classify(_observation())
    report["profile"] = profile

    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(report)
    assert str(excinfo.value) == "PROFILE_UNKNOWN"


def test_canonical_json_is_deterministic_and_profile_stamped() -> None:
    observation = _m1_worker_observation()

    for profile in READINESS_PROFILES:
        report = _classify(observation, profile)
        payload = canonical_recovery_readiness_json(
            report, expected_profile=profile
        )
        assert payload == canonical_recovery_readiness_json(report)
        decoded = json.loads(payload)
        assert decoded["profile"] == profile
        assert tuple(decoded["predicates"]) == PREDICATE_IDS
        assert tuple(decoded) == tuple(sorted(REPORT_FIELDS))

    with pytest.raises(RecoveryReadinessContractError):
        canonical_recovery_readiness_json(
            _classify(observation, BASE_RECOVERY_PROFILE),
            expected_profile=EXECUTIVE_CONTROL_PROFILE,
        )


# ------------------------------------------------------------- Studio-like


def test_studio_like_host_is_not_ready_only_for_autorestart() -> None:
    report = _classify(_studio_observation())
    predicates = report["predicates"]

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["auto_restart_after_power_loss"]
    assert report["unknown_predicates"] == []
    assert predicates["auto_restart_after_power_loss"] == {
        "requirement": "REQUIRED",
        "status": "NOT_READY",
        "code": "AUTO_RESTART_DISABLED",
        "evidence_class": "POWER_POLICY",
        "measurement": None,
    }
    assert predicates["ac_sleep_policy"]["status"] == "OK"
    assert predicates["remote_login_listener"]["status"] == "OK"


def test_autorestart_at_connect_is_optional_and_never_blocking() -> None:
    report = _classify(_studio_observation())
    predicate = report["predicates"]["auto_restart_on_power_connect"]

    assert predicate["requirement"] == "OPTIONAL"
    assert predicate["requirement"] not in LOAD_BEARING_REQUIREMENTS
    assert predicate["status"] == "ADVISORY"
    assert predicate["code"] == "AUTO_RESTART_ON_CONNECT_DISABLED"
    assert "auto_restart_on_power_connect" not in _blocking(report)


def test_autorestart_at_connect_absent_key_is_not_applicable() -> None:
    report = _classify(
        _observation(ac_power_settings={"sleep": 0, "autorestart": 1})
    )
    predicate = report["predicates"]["auto_restart_on_power_connect"]

    assert report["recovery_state"] == "READY"
    assert predicate["status"] == "NOT_APPLICABLE"
    assert predicate["code"] == "AUTO_RESTART_ON_CONNECT_NOT_EXPOSED"


# -------------------------------------------------------------- fully ready


def test_fully_ready_host_is_ready() -> None:
    report = _classify(_observation())

    assert report["recovery_state"] == "READY"
    assert _blocking(report) == []
    assert report["unknown_predicates"] == []


def test_ac_sleep_enabled_blocks_always_on_profile() -> None:
    report = _classify(
        _observation(
            ac_power_settings={"sleep": 15, "autorestart": 1, "autorestartatconnect": 1}
        )
    )

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["ac_sleep_policy"]
    assert report["predicates"]["ac_sleep_policy"]["code"] == "AC_SLEEP_ENABLED"


def test_intel_and_unsupported_os_fail_the_preboot_profile() -> None:
    intel = _classify(_observation(apple_silicon=False))
    assert intel["recovery_state"] == "NOT_READY"
    assert intel["predicates"]["cpu_architecture"]["code"] == "ARCHITECTURE_UNSUPPORTED"

    old = _classify(
        _observation(macos_product_version=f"{MIN_SUPPORTED_MACOS_MAJOR - 1}.7")
    )
    assert old["recovery_state"] == "NOT_READY"
    assert old["predicates"]["os_identity"]["code"] == "OS_UNSUPPORTED_VERSION"

    linux = _classify(
        _observation(os_name="Linux", macos_product_version=None)
    )
    assert linux["recovery_state"] == "NOT_READY"
    assert linux["predicates"]["os_identity"]["code"] == "OS_NOT_DARWIN"


def test_remote_login_disabled_blocks_without_touching_sockets() -> None:
    report = _classify(_observation(remote_login="DISABLED"))

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["remote_login_listener"]
    assert (
        report["predicates"]["remote_login_listener"]["code"] == "REMOTE_LOGIN_DISABLED"
    )
    assert (
        report["predicates"]["remote_login_listener"]["evidence_class"]
        == "REMOTE_ACCESS_POLICY"
    )


# ------------------------------------------------------------ unknown evidence


def test_unknown_load_bearing_evidence_fails_closed_to_unknown() -> None:
    report = _classify(_observation(ac_power_settings=None))

    assert report["recovery_state"] == "UNKNOWN"
    assert _blocking(report) == []
    assert report["unknown_predicates"] == [
        "ac_sleep_policy",
        "auto_restart_after_power_loss",
    ]
    assert report["predicates"]["ac_sleep_policy"]["code"] == "AC_SLEEP_UNKNOWN"
    assert (
        report["predicates"]["auto_restart_on_power_connect"]["status"] == "UNKNOWN"
    )


def test_definite_defect_dominates_unknown_evidence() -> None:
    report = _classify(
        _observation(remote_login="UNKNOWN", apple_silicon=False)
    )

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["cpu_architecture"]
    assert report["unknown_predicates"] == ["remote_login_listener"]


def test_unknown_architecture_is_never_inferred_as_pass() -> None:
    report = _classify(_observation(apple_silicon=None))

    assert report["recovery_state"] == "UNKNOWN"
    assert report["predicates"]["cpu_architecture"]["code"] == "ARCHITECTURE_UNKNOWN"


# ------------------------------------------------------------------ FileVault


def test_filevault_on_is_advisory_preboot_dependency_not_a_defect() -> None:
    report = _classify(_studio_observation())
    predicate = report["predicates"]["disk_encryption_state"]

    assert predicate["requirement"] == "ADVISORY"
    assert predicate["status"] == "ADVISORY"
    assert predicate["code"] == "FILEVAULT_ON"
    assert predicate["evidence_class"] == "DISK_ENCRYPTION_STATE"
    assert "disk_encryption_state" not in _blocking(report)
    assert "disk_encryption_state" not in report["unknown_predicates"]


@pytest.mark.parametrize(
    "filevault_code,expected_status,expected_state",
    [
        ("FILEVAULT_ON", "ADVISORY", "READY"),
        ("FILEVAULT_ENCRYPTION_IN_PROGRESS", "ADVISORY", "UNKNOWN"),
        ("FILEVAULT_DECRYPTION_IN_PROGRESS", "ADVISORY", "UNKNOWN"),
        ("FILEVAULT_OFF", "OK", "READY"),
        ("FILEVAULT_STATE_UNKNOWN", "UNKNOWN", "UNKNOWN"),
    ],
)
def test_filevault_states_are_classified_without_recovery_material(
    filevault_code: str, expected_status: str, expected_state: str
) -> None:
    report = _classify(_observation(filevault_code=filevault_code))
    predicate = report["predicates"]["disk_encryption_state"]

    assert predicate["status"] == expected_status
    assert predicate["code"] == filevault_code
    # The base observation is macOS 26.5 Apple silicon with Remote Login on, so a
    # settled FileVault state is supported; a transitional or unknown one cannot
    # be decided and fails closed through the load-bearing preboot predicate.
    assert report["recovery_state"] == expected_state
    assert predicate["measurement"] is None


def test_filevault_recovery_key_text_is_never_carried_into_the_report() -> None:
    stdout = (
        "FileVault is On.\n"
        "Recovery key = ABCD-EFGH-IJKL-MNOP-QRST-UVWX\n"
        "Decryption in progress: Percent completed = 42\n"
    )
    assert parse_fdesetup_status(stdout) == "FILEVAULT_ON"

    payload = canonical_recovery_readiness_json(
        _classify(_observation(filevault_code="FILEVAULT_ON"))
    )
    assert b"ABCD" not in payload
    assert b"Recovery" not in payload


# ------------------------------------------- local preboot remote-unlock law


def test_filevault_off_needs_no_local_preboot_unlock() -> None:
    report = _classify(_observation(filevault_code="FILEVAULT_OFF"))
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["requirement"] == "REQUIRED"
    assert predicate["requirement"] in LOAD_BEARING_REQUIREMENTS
    assert predicate["status"] == "OK"
    assert predicate["code"] == "PREBOOT_UNLOCK_NOT_REQUIRED"
    assert predicate["evidence_class"] == "PREBOOT_RECOVERY_DEPENDENCY"
    assert report["recovery_state"] == "READY"


def test_m1_like_host_passes_preboot_predicate_despite_macos_below_26() -> None:
    report = _classify(_m1_observation())
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert int(_m1_observation()["macos_product_version"].split(".")[0]) < (
        MIN_PREBOOT_REMOTE_UNLOCK_MACOS_MAJOR
    )
    assert predicate["status"] == "OK"
    assert predicate["code"] == "PREBOOT_UNLOCK_NOT_REQUIRED"
    assert report["recovery_state"] == "READY"
    assert _blocking(report) == []
    assert report["unknown_predicates"] == []


def test_filevault_on_macos_15_cannot_satisfy_remote_preboot_unlock() -> None:
    report = _classify(
        _m1_observation(filevault_code="FILEVAULT_ON")
    )
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["preboot_remote_unlock"]
    assert predicate["status"] == "NOT_READY"
    assert predicate["code"] == "PREBOOT_UNLOCK_OS_GENERATION_UNSUPPORTED"
    assert predicate["measurement"] is None
    # Encryption state itself stays advisory; the conditional predicate is the
    # load-bearing law.
    assert report["predicates"]["disk_encryption_state"]["requirement"] == "ADVISORY"
    assert report["predicates"]["disk_encryption_state"]["status"] == "ADVISORY"
    assert report["predicates"]["os_identity"]["status"] == "OK"


def test_filevault_on_macos_26_with_remote_login_supports_preboot_unlock() -> None:
    report = _classify(
        _observation(
            filevault_code="FILEVAULT_ON",
            macos_product_version=f"{MIN_PREBOOT_REMOTE_UNLOCK_MACOS_MAJOR}.0",
            remote_login="ENABLED",
        )
    )
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["status"] == "OK"
    assert predicate["code"] == "PREBOOT_UNLOCK_SUPPORTED"
    assert report["recovery_state"] == "READY"


@pytest.mark.parametrize(
    "remote_login,expected_status,expected_code",
    [
        ("DISABLED", "NOT_READY", "PREBOOT_UNLOCK_REMOTE_LOGIN_UNAVAILABLE"),
        ("NOT_INSTALLED", "NOT_READY", "PREBOOT_UNLOCK_REMOTE_LOGIN_UNAVAILABLE"),
        ("UNKNOWN", "UNKNOWN", "PREBOOT_UNLOCK_STATE_UNKNOWN"),
    ],
)
def test_filevault_on_requires_remote_login_for_preboot_unlock(
    remote_login: str, expected_status: str, expected_code: str
) -> None:
    report = _classify(
        _observation(filevault_code="FILEVAULT_ON", remote_login=remote_login)
    )
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["status"] == expected_status
    assert predicate["code"] == expected_code
    if expected_status == "NOT_READY":
        assert report["recovery_state"] == "NOT_READY"
        assert _blocking(report) == [
            "preboot_remote_unlock",
            "remote_login_listener",
        ]
    else:
        assert report["recovery_state"] == "UNKNOWN"
        assert report["unknown_predicates"] == [
            "preboot_remote_unlock",
            "remote_login_listener",
        ]


@pytest.mark.parametrize(
    "apple_silicon,expected_status,expected_code",
    [
        (False, "NOT_READY", "PREBOOT_UNLOCK_ARCHITECTURE_UNSUPPORTED"),
        (None, "UNKNOWN", "PREBOOT_UNLOCK_STATE_UNKNOWN"),
    ],
)
def test_filevault_on_preboot_unlock_fails_closed_without_apple_silicon(
    apple_silicon: bool | None, expected_status: str, expected_code: str
) -> None:
    report = _classify(
        _observation(filevault_code="FILEVAULT_ON", apple_silicon=apple_silicon)
    )
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["status"] == expected_status
    assert predicate["code"] == expected_code


@pytest.mark.parametrize(
    "filevault_code",
    ["FILEVAULT_ENCRYPTION_IN_PROGRESS", "FILEVAULT_DECRYPTION_IN_PROGRESS"],
)
def test_transitional_filevault_is_unknown_for_preboot_unlock(
    filevault_code: str,
) -> None:
    report = _classify(_observation(filevault_code=filevault_code))
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["status"] == "UNKNOWN"
    assert predicate["code"] == "PREBOOT_UNLOCK_STATE_UNKNOWN"
    assert report["recovery_state"] == "UNKNOWN"
    assert report["unknown_predicates"] == ["preboot_remote_unlock"]


def test_unknown_filevault_state_is_unknown_for_preboot_unlock() -> None:
    report = _classify(
        _observation(filevault_code="FILEVAULT_STATE_UNKNOWN")
    )
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["status"] == "UNKNOWN"
    assert predicate["code"] == "PREBOOT_UNLOCK_STATE_UNKNOWN"
    assert report["recovery_state"] == "UNKNOWN"


@pytest.mark.parametrize(
    "macos_product_version", [None, "", "26-beta", "twentysix", "26.5.1.2.3"]
)
def test_malformed_os_version_never_guesses_a_preboot_pass(
    macos_product_version: str | None,
) -> None:
    observation = _observation(
        filevault_code="FILEVAULT_ON",
        macos_product_version=macos_product_version,
    )
    if macos_product_version == "":
        with pytest.raises(RecoveryReadinessContractError) as excinfo:
            _classify(observation)
        assert str(excinfo.value) == "OBSERVATION_TEXT_INVALID"
        return

    report = _classify(observation)
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["status"] == "UNKNOWN"
    assert predicate["code"] == "PREBOOT_UNLOCK_STATE_UNKNOWN"
    assert report["recovery_state"] == "UNKNOWN"


def test_non_darwin_host_never_claims_preboot_unlock_support() -> None:
    report = _classify(
        _observation(
            os_name="Linux",
            macos_product_version=None,
            filevault_code="FILEVAULT_ON",
        )
    )
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["status"] == "UNKNOWN"
    assert predicate["code"] == "PREBOOT_UNLOCK_STATE_UNKNOWN"
    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["os_identity"]


@pytest.mark.parametrize("profile", list(READINESS_PROFILES))
@pytest.mark.parametrize(
    "filevault_code,macos_product_version,expected_code",
    [
        ("FILEVAULT_OFF", "15.6", "PREBOOT_UNLOCK_NOT_REQUIRED"),
        ("FILEVAULT_ON", "15.6", "PREBOOT_UNLOCK_OS_GENERATION_UNSUPPORTED"),
        ("FILEVAULT_ON", "26.0", "PREBOOT_UNLOCK_SUPPORTED"),
        ("FILEVAULT_STATE_UNKNOWN", "26.0", "PREBOOT_UNLOCK_STATE_UNKNOWN"),
    ],
)
def test_filevault_and_macos_26_law_is_identical_under_both_profiles(
    profile: str,
    filevault_code: str,
    macos_product_version: str,
    expected_code: str,
) -> None:
    report = _classify(
        _m1_worker_observation(
            filevault_code=filevault_code,
            macos_product_version=macos_product_version,
        ),
        profile,
    )
    predicate = report["predicates"]["preboot_remote_unlock"]

    assert predicate["requirement"] == "REQUIRED"
    assert predicate["requirement"] in LOAD_BEARING_REQUIREMENTS
    assert predicate["code"] == expected_code
    assert report["predicates"]["disk_encryption_state"]["requirement"] == "ADVISORY"
    assert report["predicates"]["disk_encryption_state"]["code"] == filevault_code
    assert MIN_PREBOOT_REMOTE_UNLOCK_MACOS_MAJOR == 26


def test_preboot_unlock_predicate_is_independent_of_auto_restart() -> None:
    """The current Studio fixture must still block on exactly one predicate."""

    report = _classify(_studio_observation())

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["auto_restart_after_power_loss"]
    assert report["unknown_predicates"] == []
    assert report["predicates"]["preboot_remote_unlock"] == {
        "requirement": "REQUIRED",
        "status": "OK",
        "code": "PREBOOT_UNLOCK_SUPPORTED",
        "evidence_class": "PREBOOT_RECOVERY_DEPENDENCY",
        "measurement": None,
    }


def test_predicate_set_is_closed_and_canonically_ordered() -> None:
    expected_ids = (
        "ac_sleep_policy",
        "auto_restart_after_power_loss",
        "auto_restart_on_power_connect",
        "cpu_architecture",
        "disk_encryption_state",
        "disk_free_floor",
        "os_identity",
        "preboot_remote_unlock",
        "remote_login_listener",
        "system_daemon.com.mastermind.executive.backup",
        "system_daemon.com.mastermind.executive.control",
        "system_daemon.com.mastermind.executive.mcp",
        "system_daemon.com.mastermind.executive.privileged",
        "system_daemon.com.mastermind.executive.sol-state-relay",
        "system_daemon.com.mastermind.executive.worker.codex",
        "system_daemon.com.mastermind.executive.worker.codex-pro-01",
        "system_daemon.com.mastermind.executive.worker.codex-pro-02",
        "system_daemon.com.mastermind.executive.worker.codex-pro-03",
        "user_session_surfaces",
    )

    assert PREDICATE_IDS == expected_ids
    assert expected_ids == tuple(sorted(expected_ids))
    # The predicate set, its ordering, its evidence classes and its code
    # vocabulary are profile-independent; only requirements differ.
    for profile in READINESS_PROFILES:
        assert recovery_profile(profile).predicate_ids() == expected_ids

    report = _classify(_studio_observation())
    payload = canonical_recovery_readiness_json(report).decode("ascii")
    decoded = json.loads(payload)

    assert tuple(decoded["predicates"]) == expected_ids
    assert tuple(decoded) == tuple(sorted(REPORT_FIELDS))
    assert {
        PREDICATE_EVIDENCE_CLASSES[predicate_id] for predicate_id in expected_ids
    } <= EVIDENCE_CLASSES
    assert "PREBOOT_RECOVERY_DEPENDENCY" in EVIDENCE_CLASSES
    assert (
        PREDICATE_CODES["preboot_remote_unlock"]
        == frozenset(
            {
                "PREBOOT_UNLOCK_NOT_REQUIRED",
                "PREBOOT_UNLOCK_SUPPORTED",
                "PREBOOT_UNLOCK_OS_GENERATION_UNSUPPORTED",
                "PREBOOT_UNLOCK_ARCHITECTURE_UNSUPPORTED",
                "PREBOOT_UNLOCK_REMOTE_LOGIN_UNAVAILABLE",
                "PREBOOT_UNLOCK_STATE_UNKNOWN",
            }
        )
    )


def test_out_of_vocabulary_preboot_code_is_refused() -> None:
    report = _classify(_observation())
    report["predicates"]["preboot_remote_unlock"]["code"] = "PREBOOT_UNLOCK_ASSUMED_OK"

    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(report)
    assert str(excinfo.value) == "PREDICATE_CODE_INVALID"


# ------------------------------------------------- status/code semantic pairing


def _refusal(
    report: dict[str, Any], *, expected_profile: Any = None
) -> str:
    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(report, expected_profile=expected_profile)
    return str(excinfo.value)


def _forge_status(
    report: dict[str, Any], predicate_id: str, status: str
) -> dict[str, Any]:
    """Relabel one predicate's status and repair every derived field.

    This is the whole attack: a report whose syntax, vocabulary, requirement
    table and top-level derivation are all internally consistent, and which is
    a lie only in the pairing between a failure code and a passing status.
    """

    predicates = report["predicates"]
    predicates[predicate_id]["status"] = status
    state, blocking, unknown = resolve_recovery_state(predicates)
    report["recovery_state"] = state
    report["blocking_predicates"] = blocking
    report["unknown_predicates"] = unknown
    return report


def test_forged_daemon_pass_on_a_not_installed_control_daemon_is_refused() -> None:
    """The independent review's attack: DAEMON_NOT_INSTALLED relabelled OK.

    Every required Studio control daemon is genuinely missing, so the honest
    report is NOT_READY.  Relabelling each blocking predicate OK while leaving
    its failure code intact used to buy a forged READY, because status
    vocabulary and code vocabulary were validated independently.
    """

    daemons = {label: "NOT_INSTALLED" for label in REQUIRED_RUNNING_DAEMON_LABELS}
    daemons.update(
        {label: "DISABLED" for label in DISARMED_EXPECTED_DAEMON_LABELS}
    )
    honest = _classify(_observation(system_daemons=daemons))
    assert honest["recovery_state"] == "NOT_READY"
    assert _blocking(honest) == [
        f"system_daemon.{label}" for label in sorted(REQUIRED_RUNNING_DAEMON_LABELS)
    ]
    for label in REQUIRED_RUNNING_DAEMON_LABELS:
        predicate = honest["predicates"][f"system_daemon.{label}"]
        assert predicate["code"] == "DAEMON_NOT_INSTALLED"
        assert predicate["status"] == "NOT_READY"

    forged = json.loads(json.dumps(honest))
    for label in REQUIRED_RUNNING_DAEMON_LABELS:
        forged["predicates"][f"system_daemon.{label}"]["status"] = "OK"
    forged["recovery_state"] = "READY"
    forged["blocking_predicates"] = []

    assert (
        _refusal(forged, expected_profile=EXECUTIVE_CONTROL_PROFILE)
        == "PREDICATE_STATUS_CODE_MISMATCH"
    )
    assert _refusal(forged) == "PREDICATE_STATUS_CODE_MISMATCH"


def test_forged_daemon_failure_on_a_running_control_daemon_is_refused() -> None:
    """The inverse lie must refuse too: a running daemon reported NOT_READY."""

    report = _classify(_observation())
    predicate_id = "system_daemon.com.mastermind.executive.control"
    assert report["predicates"][predicate_id]["code"] == "DAEMON_RUNNING"

    forged = _forge_status(report, predicate_id, "NOT_READY")
    assert forged["recovery_state"] == "NOT_READY"

    assert _refusal(forged) == "PREDICATE_STATUS_CODE_MISMATCH"


@pytest.mark.parametrize(
    "profile,requirement,canonical_status",
    [
        (BASE_RECOVERY_PROFILE, "ADVISORY", "ADVISORY"),
        (EXECUTIVE_CONTROL_PROFILE, "REQUIRED_RUNNING", "NOT_READY"),
    ],
)
def test_same_daemon_code_has_profile_specific_canonical_status(
    profile: str, requirement: str, canonical_status: str
) -> None:
    """``DAEMON_NOT_INSTALLED`` is advisory under base and a defect under control.

    One observed code, two profiles, two different legal statuses — and neither
    of them is ``OK``.  The status the validator demands therefore has to be
    derived through the requirement the named profile assigns, not from a
    profile-independent code table.
    """

    observation = _m1_worker_observation()
    predicate_id = f"system_daemon.{REQUIRED_RUNNING_DAEMON_LABELS[0]}"
    report = _classify(observation, profile)
    predicate = report["predicates"][predicate_id]

    assert predicate["requirement"] == requirement
    assert predicate["code"] == "DAEMON_NOT_INSTALLED"
    assert predicate["status"] == canonical_status

    forged = _forge_status(report, predicate_id, "OK")
    assert _refusal(forged) == "PREDICATE_STATUS_CODE_MISMATCH"


def test_cross_requirement_daemon_status_is_refused_by_vocabulary() -> None:
    """The two layers compose: a status the requirement cannot hold at all.

    ``ADVISORY`` is the honest base-profile status for a missing Executive
    daemon, but a ``REQUIRED_RUNNING`` predicate may never carry it, so the
    status vocabulary refuses before the pairing law is consulted.
    """

    report = _classify(_m1_worker_observation(), EXECUTIVE_CONTROL_PROFILE)
    predicate_id = f"system_daemon.{REQUIRED_RUNNING_DAEMON_LABELS[0]}"
    report["predicates"][predicate_id]["status"] = "ADVISORY"

    assert _refusal(report) == "PREDICATE_STATUS_INVALID"


def test_disarmed_verdict_is_unreachable_on_a_required_running_daemon() -> None:
    """A code its own requirement can never emit is refused, not just an odd pair."""

    report = _classify(_observation())
    predicate_id = "system_daemon.com.mastermind.executive.mcp"
    report["predicates"][predicate_id]["code"] = "DAEMON_INTENTIONALLY_DISARMED"

    assert _refusal(report) == "PREDICATE_STATUS_CODE_MISMATCH"


@pytest.mark.parametrize(
    "predicate_id,observation_overrides,code,forged_status",
    [
        (
            "auto_restart_after_power_loss",
            {"ac_power_settings": {"sleep": 0, "autorestart": 0}},
            "AUTO_RESTART_DISABLED",
            "OK",
        ),
        (
            "auto_restart_after_power_loss",
            {},
            "AUTO_RESTART_ENABLED",
            "NOT_READY",
        ),
        (
            "remote_login_listener",
            {"remote_login": "DISABLED"},
            "REMOTE_LOGIN_DISABLED",
            "OK",
        ),
        (
            "preboot_remote_unlock",
            {"filevault_code": "FILEVAULT_ENCRYPTION_IN_PROGRESS"},
            "PREBOOT_UNLOCK_STATE_UNKNOWN",
            "OK",
        ),
        (
            "os_identity",
            {"macos_product_version": "13.6"},
            "OS_UNSUPPORTED_VERSION",
            "OK",
        ),
        (
            "cpu_architecture",
            {"apple_silicon": None},
            "ARCHITECTURE_UNKNOWN",
            "OK",
        ),
        (
            "disk_encryption_state",
            {"filevault_code": "FILEVAULT_STATE_UNKNOWN"},
            "FILEVAULT_STATE_UNKNOWN",
            "OK",
        ),
    ],
)
def test_non_daemon_status_code_forgery_is_refused(
    predicate_id: str,
    observation_overrides: dict[str, Any],
    code: str,
    forged_status: str,
) -> None:
    report = _classify(_observation(**observation_overrides))
    assert report["predicates"][predicate_id]["code"] == code

    forged = _forge_status(report, predicate_id, forged_status)
    assert _refusal(forged) == "PREDICATE_STATUS_CODE_MISMATCH"


def test_status_code_forgery_cannot_move_the_top_level_state() -> None:
    """A pairing lie is refused before ``recovery_state`` is ever believed."""

    honest = _classify(_studio_observation())
    assert honest["recovery_state"] == "NOT_READY"
    assert _blocking(honest) == ["auto_restart_after_power_loss"]

    forged = json.loads(json.dumps(honest))
    forged["predicates"]["auto_restart_after_power_loss"]["status"] = "OK"
    forged["recovery_state"] = "READY"
    forged["blocking_predicates"] = []
    assert _refusal(forged) == "PREDICATE_STATUS_CODE_MISMATCH"

    # The honest UNKNOWN case cannot be laundered into READY either.
    unknown = _classify(_observation(ac_power_settings=None))
    assert unknown["recovery_state"] == "UNKNOWN"
    laundered = json.loads(json.dumps(unknown))
    for predicate_id in unknown["unknown_predicates"]:
        laundered["predicates"][predicate_id]["status"] = "OK"
    laundered["recovery_state"] = "READY"
    laundered["unknown_predicates"] = []
    assert _refusal(laundered) == "PREDICATE_STATUS_CODE_MISMATCH"


# ------------------------------------------------------ measurement semantics


def test_every_predicate_that_never_measures_must_carry_no_measurement() -> None:
    report = _classify(_observation())

    measuring = set(PREDICATE_MEASUREMENT_LAW)
    for predicate_id in PREDICATE_IDS:
        if predicate_id in measuring:
            continue
        assert report["predicates"][predicate_id]["measurement"] is None

        tampered = json.loads(json.dumps(report))
        tampered["predicates"][predicate_id]["measurement"] = 1
        assert _refusal(tampered) == "PREDICATE_MEASUREMENT_MISMATCH"


@pytest.mark.parametrize("measurement", [0, None])
def test_enabled_ac_sleep_must_carry_a_positive_measurement(
    measurement: Any,
) -> None:
    report = _classify(
        _observation(ac_power_settings={"sleep": 15, "autorestart": 1})
    )
    predicate = report["predicates"]["ac_sleep_policy"]
    assert predicate["code"] == "AC_SLEEP_ENABLED"
    assert predicate["measurement"] == 15

    predicate["measurement"] = measurement
    assert _refusal(report) == "PREDICATE_MEASUREMENT_MISMATCH"


@pytest.mark.parametrize(
    "settings,code",
    [
        ({"sleep": 0, "autorestart": 1}, "AC_SLEEP_DISABLED"),
        ({"autorestart": 1}, "AC_SLEEP_UNKNOWN"),
    ],
)
def test_non_enabled_ac_sleep_cannot_carry_a_measurement(
    settings: dict[str, int], code: str
) -> None:
    report = _classify(_observation(ac_power_settings=settings))
    predicate = report["predicates"]["ac_sleep_policy"]
    assert predicate["code"] == code
    assert predicate["measurement"] is None

    predicate["measurement"] = 15
    assert _refusal(report) == "PREDICATE_MEASUREMENT_MISMATCH"


@pytest.mark.parametrize(
    "agents_present,code,forged",
    [
        (0, "USER_SESSION_AGENTS_ABSENT", 2),
        (3, "USER_SESSION_LOGIN_REQUIRED", 0),
        (None, "USER_SESSION_STATE_UNKNOWN", 3),
    ],
)
def test_user_session_count_must_match_its_own_code(
    agents_present: Any, code: str, forged: int
) -> None:
    report = _classify(_observation(user_session_agents_present=agents_present))
    predicate = report["predicates"]["user_session_surfaces"]
    assert predicate["code"] == code
    assert predicate["measurement"] == agents_present

    predicate["measurement"] = forged
    assert _refusal(report) == "PREDICATE_MEASUREMENT_MISMATCH"


def test_known_user_session_code_cannot_drop_its_count() -> None:
    report = _classify(_observation(user_session_agents_present=0))
    report["predicates"]["user_session_surfaces"]["measurement"] = None

    assert _refusal(report) == "PREDICATE_MEASUREMENT_MISMATCH"


@pytest.mark.parametrize(
    "free_bytes,code,forged",
    [
        (DISK_FREE_FLOOR_BYTES * 4, "DISK_FREE_ABOVE_FLOOR", DISK_FREE_FLOOR_BYTES - 1),
        (DISK_FREE_FLOOR_BYTES - 1, "DISK_FREE_BELOW_FLOOR", DISK_FREE_FLOOR_BYTES),
        (DISK_FREE_FLOOR_BYTES * 4, "DISK_FREE_ABOVE_FLOOR", None),
        (DISK_FREE_FLOOR_BYTES - 1, "DISK_FREE_BELOW_FLOOR", None),
    ],
)
def test_disk_free_measurement_must_sit_on_the_side_its_code_claims(
    free_bytes: int, code: str, forged: Any
) -> None:
    report = _classify(_observation(root_free_bytes=free_bytes))
    predicate = report["predicates"]["disk_free_floor"]
    assert predicate["code"] == code
    assert predicate["measurement"] == free_bytes

    predicate["measurement"] = forged
    assert _refusal(report) == "PREDICATE_MEASUREMENT_MISMATCH"


def test_unknown_disk_free_space_cannot_acquire_a_measurement() -> None:
    report = _classify(_observation(root_free_bytes=None))
    predicate = report["predicates"]["disk_free_floor"]
    assert predicate["code"] == "DISK_FREE_UNKNOWN"
    assert predicate["measurement"] is None

    predicate["measurement"] = DISK_FREE_FLOOR_BYTES * 4
    assert _refusal(report) == "PREDICATE_MEASUREMENT_MISMATCH"


def test_measurement_bounds_still_apply_before_semantics() -> None:
    report = _classify(_observation(root_free_bytes=DISK_FREE_FLOOR_BYTES * 4))
    report["predicates"]["disk_free_floor"]["measurement"] = -1

    assert _refusal(report) == "PREDICATE_MEASUREMENT_INVALID"


def test_untouched_reports_still_validate_and_canonicalize_byte_stably() -> None:
    """Closing the pairing law must not disturb any honest report."""

    for observation in (
        _observation(),
        _studio_observation(),
        _m1_observation(),
        _m1_worker_observation(),
        _observation(ac_power_settings=None, root_free_bytes=None),
        _observation(root_free_bytes=DISK_FREE_FLOOR_BYTES - 1),
        _observation(user_session_agents_present=0),
    ):
        for profile in READINESS_PROFILES:
            report = _classify(observation, profile)
            payload = canonical_recovery_readiness_json(
                report, expected_profile=profile
            )
            roundtripped = json.loads(payload)
            assert validate_recovery_readiness_report(
                roundtripped, expected_profile=profile
            ) == report
            assert (
                canonical_recovery_readiness_json(
                    roundtripped, expected_profile=profile
                )
                == payload
            )


# ------------------------------------------------------- daemon gate semantics


def test_intentionally_disarmed_daemons_are_not_defects() -> None:
    report = _classify(_studio_observation())

    for label in DISARMED_EXPECTED_DAEMON_LABELS:
        predicate = report["predicates"][f"system_daemon.{label}"]
        assert predicate["requirement"] == "DISARMED_EXPECTED"
        assert predicate["status"] == "OK"
        assert predicate["code"] in {
            "DAEMON_INTENTIONALLY_DISARMED",
            "DAEMON_NOT_INSTALLED",
        }
        assert f"system_daemon.{label}" not in _blocking(report)

    assert (
        report["predicates"][
            "system_daemon.com.mastermind.executive.worker.codex"
        ]["code"]
        == "DAEMON_INTENTIONALLY_DISARMED"
    )
    assert (
        report["predicates"][
            "system_daemon.com.mastermind.executive.privileged"
        ]["code"]
        == "DAEMON_NOT_INSTALLED"
    )


def test_disarmed_daemon_found_running_is_advisory_not_blocking() -> None:
    label = "com.mastermind.executive.backup"
    daemons = _studio_daemons()
    daemons[label] = "RUNNING"
    report = _classify(_studio_observation(system_daemons=daemons))
    predicate = report["predicates"][f"system_daemon.{label}"]

    assert predicate["status"] == "ADVISORY"
    assert predicate["code"] == "DAEMON_UNEXPECTEDLY_RUNNING"
    assert f"system_daemon.{label}" not in _blocking(report)


@pytest.mark.parametrize(
    "state,expected_status,expected_code",
    [
        ("RUNNING", "OK", "DAEMON_RUNNING"),
        ("LOADED_NOT_RUNNING", "NOT_READY", "DAEMON_LOADED_NOT_RUNNING"),
        ("DISABLED", "NOT_READY", "DAEMON_DISABLED"),
        ("NOT_INSTALLED", "NOT_READY", "DAEMON_NOT_INSTALLED"),
        ("UNKNOWN", "UNKNOWN", "DAEMON_STATE_UNKNOWN"),
    ],
)
def test_required_running_daemon_states(
    state: str, expected_status: str, expected_code: str
) -> None:
    label = "com.mastermind.executive.sol-state-relay"
    daemons = _studio_daemons()
    daemons[label] = state
    report = _classify(_studio_observation(system_daemons=daemons))
    predicate = report["predicates"][f"system_daemon.{label}"]

    assert predicate["requirement"] == "REQUIRED_RUNNING"
    assert predicate["status"] == expected_status
    assert predicate["code"] == expected_code


def test_missing_daemon_observation_is_unknown_not_absent() -> None:
    report = _classify(_studio_observation(system_daemons={}))

    for label in REQUIRED_RUNNING_DAEMON_LABELS:
        predicate = report["predicates"][f"system_daemon.{label}"]
        assert predicate["status"] == "UNKNOWN"
        assert predicate["code"] == "DAEMON_STATE_UNKNOWN"


def test_daemon_observation_vocabulary_is_closed() -> None:
    """An unknown observed state on a known label is refused, never classified.

    The label set already has its own refusal, so this pins the other half of
    the observation contract: a state token outside the reviewed vocabulary can
    neither reach a verdict table nor crash one.
    """

    assert DAEMON_OBSERVATIONS == frozenset(
        {"RUNNING", "LOADED_NOT_RUNNING", "DISABLED", "NOT_INSTALLED", "UNKNOWN"}
    )

    for label in (
        REQUIRED_RUNNING_DAEMON_LABELS[0],
        DISARMED_EXPECTED_DAEMON_LABELS[0],
    ):
        for state in ("WHATEVER", "running", "OK", "", None, 1, True):
            daemons = _studio_daemons()
            daemons[label] = state  # type: ignore[assignment]
            for profile in READINESS_PROFILES:
                with pytest.raises(RecoveryReadinessContractError) as excinfo:
                    _classify(_studio_observation(system_daemons=daemons), profile)
                assert str(excinfo.value) == "DAEMON_OBSERVATION_INVALID"


# ------------------------------------------------- user-session separation


def test_user_session_surfaces_are_reported_separately_and_never_load_bearing() -> None:
    report = _classify(_observation())
    predicate = report["predicates"]["user_session_surfaces"]

    assert predicate["requirement"] == "ADVISORY"
    assert predicate["evidence_class"] == "USER_SESSION_DEPENDENCY"
    assert predicate["status"] == "ADVISORY"
    assert predicate["code"] == "USER_SESSION_LOGIN_REQUIRED"
    assert predicate["measurement"] == len(USER_SESSION_CRITICAL_LABELS)
    assert report["recovery_state"] == "READY"

    system_ids = {
        predicate_id
        for predicate_id in report["predicates"]
        if predicate_id.startswith("system_daemon.")
    }
    assert "user_session_surfaces" not in system_ids
    for predicate_id in system_ids:
        assert (
            report["predicates"][predicate_id]["evidence_class"]
            == "SYSTEM_SERVICE_STATE"
        )


def test_absent_user_agents_are_advisory_not_ready_false() -> None:
    report = _classify(_observation(user_session_agents_present=0))
    predicate = report["predicates"]["user_session_surfaces"]

    assert predicate["status"] == "ADVISORY"
    assert predicate["code"] == "USER_SESSION_AGENTS_ABSENT"
    assert predicate["measurement"] == 0
    assert report["recovery_state"] == "READY"


def test_unreadable_user_agent_directory_is_unknown_but_not_blocking() -> None:
    report = _classify(_observation(user_session_agents_present=None))
    predicate = report["predicates"]["user_session_surfaces"]

    assert predicate["status"] == "UNKNOWN"
    assert predicate["code"] == "USER_SESSION_STATE_UNKNOWN"
    assert report["recovery_state"] == "READY"
    assert report["unknown_predicates"] == []


# ----------------------------------------------------------- disk free floor


def test_disk_free_floor_uses_reviewed_threshold() -> None:
    assert DISK_FREE_FLOOR_BYTES == 25 * 1024**3

    at_floor = _classify(
        _observation(root_free_bytes=DISK_FREE_FLOOR_BYTES)
    )
    assert at_floor["predicates"]["disk_free_floor"]["status"] == "OK"
    assert at_floor["predicates"]["disk_free_floor"]["code"] == "DISK_FREE_ABOVE_FLOOR"
    assert (
        at_floor["predicates"]["disk_free_floor"]["measurement"]
        == DISK_FREE_FLOOR_BYTES
    )

    below = _classify(
        _observation(root_free_bytes=DISK_FREE_FLOOR_BYTES - 1)
    )
    assert below["recovery_state"] == "NOT_READY"
    assert _blocking(below) == ["disk_free_floor"]
    assert below["predicates"]["disk_free_floor"]["code"] == "DISK_FREE_BELOW_FLOOR"


def test_unknown_disk_free_space_is_unknown_not_pass() -> None:
    report = _classify(_observation(root_free_bytes=None))

    assert report["recovery_state"] == "UNKNOWN"
    assert report["unknown_predicates"] == ["disk_free_floor"]
    assert report["predicates"]["disk_free_floor"]["code"] == "DISK_FREE_UNKNOWN"
    assert report["predicates"]["disk_free_floor"]["measurement"] is None


# ----------------------------------------------------------------- parsers


def test_parse_pmset_custom_splits_power_sections() -> None:
    parsed = parse_pmset_custom(PMSET_READY)

    assert parsed["AC Power"]["sleep"] == 0
    assert parsed["AC Power"]["autorestart"] == 1
    assert parsed["AC Power"]["autorestartatconnect"] == 1
    assert parsed["Battery Power"]["sleep"] == 5

    studio = parse_pmset_custom(PMSET_STUDIO)
    assert studio["AC Power"]["sleep"] == 0
    assert studio["AC Power"]["autorestart"] == 0
    assert studio["AC Power"]["autorestartatconnect"] == 0
    assert "Battery Power" not in studio
    assert "Sleep" not in studio["AC Power"]


def test_parse_pmset_custom_refuses_empty_or_sectionless_output() -> None:
    for stdout in ("", "   \n", "sleep 0\n"):
        with pytest.raises(RecoveryReadinessProbeError) as excinfo:
            parse_pmset_custom(stdout)
        assert excinfo.value.code == "POWER_POLICY_MALFORMED"


@pytest.mark.parametrize(
    "stdout,expected",
    [
        ("FileVault is On.\n", "FILEVAULT_ON"),
        ("FileVault is Off.\n", "FILEVAULT_OFF"),
        (
            "FileVault is On.\nEncryption in progress: Percent completed = 3\n",
            "FILEVAULT_ON",
        ),
        (
            "Encryption in progress: Percent completed = 3\n",
            "FILEVAULT_ENCRYPTION_IN_PROGRESS",
        ),
        (
            "Decryption in progress: Percent completed = 3\n",
            "FILEVAULT_DECRYPTION_IN_PROGRESS",
        ),
        ("something unexpected\n", "FILEVAULT_STATE_UNKNOWN"),
        ("", "FILEVAULT_STATE_UNKNOWN"),
    ],
)
def test_parse_fdesetup_status(stdout: str, expected: str) -> None:
    assert parse_fdesetup_status(stdout) == expected


def test_parse_launchctl_print_disabled_accepts_both_vocabularies() -> None:
    parsed = parse_launchctl_print_disabled(LAUNCHCTL_DISABLED_STUDIO)

    assert parsed["com.openssh.sshd"] is False
    assert parsed["com.mastermind.executive.control"] is False
    assert parsed["com.mastermind.executive.worker.codex"] is True

    legacy = parse_launchctl_print_disabled(
        'disabled services = {\n\t"com.openssh.sshd" => false\n'
        '\t"com.mastermind.executive.backup" => true\n}\n'
    )
    assert legacy["com.openssh.sshd"] is False
    assert legacy["com.mastermind.executive.backup"] is True


def test_parse_launchctl_print_disabled_ignores_unparsable_rows() -> None:
    parsed = parse_launchctl_print_disabled(
        'disabled services = {\n\t"com.openssh.sshd" => banana\n'
        "\tgarbage line\n}\n"
    )
    assert parsed == {}


@pytest.mark.parametrize(
    "stdout,expected",
    [
        ("\tstate = running\n\tpid = 3708\n", "RUNNING"),
        ("\tstate = waiting\n", "LOADED_NOT_RUNNING"),
        ("\tstate = not running\n", "LOADED_NOT_RUNNING"),
        ("no state line\n", "UNKNOWN"),
    ],
)
def test_parse_launchctl_print_state(stdout: str, expected: str) -> None:
    assert parse_launchctl_print_state(stdout) == expected


# ------------------------------------------------------- collector and CLI


REQUIRED_LABEL = "com.mastermind.executive.control"
UNINSTALLED_STUDIO_LABEL = "com.mastermind.executive.privileged"

# ``print-disabled`` on a host where nothing Executive-related was ever
# overridden: the table exists and is readable, but holds no row for any label
# this observer cares about.
LAUNCHCTL_DISABLED_NO_EXECUTIVE_ROWS = """disabled services = {
\t\t"com.apple.screensharing" => disabled
}
"""

STUDIO_PLISTS = frozenset(
    {SSHD_SYSTEM_PLIST}
    | {
        system_daemon_plist_path(label)
        for label in ALL_DAEMON_LABELS
        if label != UNINSTALLED_STUDIO_LABEL
    }
)


# Fixtures below simulate a Mac host. The production collector deliberately
# defaults to the real platform and refuses non-Darwin, so simulated-Mac calls
# must inject Darwin explicitly to stay hermetic on Linux CI runners.
_SIMULATED_DARWIN: Callable[[], str] = lambda: "Darwin"


def _plist_exists_for(paths: frozenset[Path]):
    present = frozenset(paths)

    def plist_exists(path: Path) -> bool:
        assert isinstance(path, Path)
        assert path.is_absolute()
        return path in present

    return plist_exists


def _runner_for(
    *,
    pmset: str = PMSET_STUDIO,
    sw_vers: str = "26.5\n",
    arm64: str = "1\n",
    fdesetup: str = "FileVault is On.\n",
    disabled: str = LAUNCHCTL_DISABLED_STUDIO,
    running_labels: frozenset[str] | None = None,
    sshd_registered: bool = True,
):
    running = (
        running_labels
        if running_labels is not None
        else frozenset(REQUIRED_RUNNING_DAEMON_LABELS)
    )

    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        if command == PMSET_CUSTOM_COMMAND:
            return _completed(command, stdout=pmset)
        if command == SW_VERS_COMMAND:
            return _completed(command, stdout=sw_vers)
        if command == SYSCTL_ARM64_COMMAND:
            return _completed(command, stdout=arm64)
        if command == FDESETUP_STATUS_COMMAND:
            return _completed(command, stdout=fdesetup)
        if command == LAUNCHCTL_PRINT_DISABLED_COMMAND:
            return _completed(command, stdout=disabled)
        if command == launchctl_print_command(SSHD_LABEL):
            if sshd_registered:
                return _completed(
                    command, stdout="\tstate = waiting\n\tsockets = {\n\t}\n"
                )
            return _completed(command, returncode=113, stdout="")
        for label in ALL_DAEMON_LABELS:
            if command == launchctl_print_command(label):
                if label in running:
                    return _completed(
                        command, stdout="\tstate = running\n\tpid = 1\n"
                    )
                return _completed(command, returncode=113, stdout="")
        raise AssertionError(f"unexpected command: {command!r}")

    return runner


def _collect(
    *,
    runner,
    plists: frozenset[Path] = STUDIO_PLISTS,
    launch_agents_dir: Path,
    host_ref: str | None = None,
    platform_system: Callable[[], str] = _SIMULATED_DARWIN,
) -> dict[str, Any]:
    return collect_recovery_observation(
        host_ref=host_ref,
        runner=runner,
        platform_system=platform_system,
        plist_exists=_plist_exists_for(plists),
        launch_agents_dir=launch_agents_dir,
        free_bytes=lambda: DISK_FREE_FLOOR_BYTES * 3,
        wall_time_ms=lambda: 1_789_000_000_000,
    )


def test_collector_reproduces_studio_like_unsafe_state(tmp_path: Path) -> None:
    for label in USER_SESSION_CRITICAL_LABELS:
        (tmp_path / f"{label}.plist").write_text("", encoding="utf-8")

    observation = _collect(
        runner=_runner_for(), launch_agents_dir=tmp_path, host_ref=HOST_REF
    )
    report = _classify(observation)

    assert observation["ac_power_settings"]["autorestart"] == 0
    assert observation["filevault_code"] == "FILEVAULT_ON"
    assert observation["remote_login"] == "ENABLED"
    assert observation["user_session_agents_present"] == len(
        USER_SESSION_CRITICAL_LABELS
    )
    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["auto_restart_after_power_loss"]


def test_collector_reproduces_ready_state(tmp_path: Path) -> None:
    observation = _collect(
        runner=_runner_for(pmset=PMSET_READY, fdesetup="FileVault is Off.\n"),
        launch_agents_dir=tmp_path,
        host_ref=HOST_REF,
    )
    report = _classify(observation)

    assert report["recovery_state"] == "READY"
    assert _blocking(report) == []


def test_collector_refuses_non_darwin_without_running_commands() -> None:
    """The refusal must precede every host read, proven by an empty call log.

    A runner that raises cannot prove this: ``_read_stdout`` deliberately
    swallows any runner exception and returns ``None``, so a collector that
    read the host first and only then checked the platform would still refuse
    ``UNSUPPORTED_PLATFORM`` and still look correct.  This runner therefore
    succeeds benignly and records every invocation, and the ordering claim is
    carried by the call log being exactly empty.
    """

    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _completed(command)

    with pytest.raises(RecoveryReadinessProbeError) as excinfo:
        collect_recovery_observation(
            host_ref=None,
            runner=runner,
            platform_system=lambda: "Linux",
            launch_agents_dir=Path("/nonexistent"),
            free_bytes=lambda: 0,
            wall_time_ms=lambda: 1,
        )
    assert excinfo.value.code == "UNSUPPORTED_PLATFORM"
    assert calls == []


def test_collector_maps_unavailable_commands_to_unknown(tmp_path: Path) -> None:
    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    observation = collect_recovery_observation(
        host_ref=None,
        runner=runner,
        platform_system=_SIMULATED_DARWIN,
        plist_exists=_plist_exists_for(STUDIO_PLISTS),
        launch_agents_dir=tmp_path,
        free_bytes=lambda: None,
        wall_time_ms=lambda: 1_789_000_000_000,
    )
    report = _classify(observation)

    assert observation["ac_power_settings"] is None
    assert observation["apple_silicon"] is None
    assert observation["filevault_code"] == "FILEVAULT_STATE_UNKNOWN"
    assert observation["remote_login"] == "UNKNOWN"
    assert report["recovery_state"] == "UNKNOWN"
    assert _blocking(report) == []


def test_permission_refusal_is_unknown_not_pass(tmp_path: Path) -> None:
    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        if command == LAUNCHCTL_PRINT_DISABLED_COMMAND:
            raise PermissionError("denied")
        return _runner_for()(command)

    observation = _collect(runner=runner, launch_agents_dir=tmp_path)

    assert observation["remote_login"] == "UNKNOWN"
    report = _classify(observation)
    assert report["predicates"]["remote_login_listener"]["status"] == "UNKNOWN"
    for label in REQUIRED_RUNNING_DAEMON_LABELS:
        assert observation["system_daemons"][label] == "UNKNOWN"


# ------------------------------------ install-vs-override discrimination


def test_missing_disable_override_row_never_means_not_installed(
    tmp_path: Path,
) -> None:
    """A fresh host has no override row for a normally enabled installed service."""

    observation = _collect(
        runner=_runner_for(disabled=LAUNCHCTL_DISABLED_NO_EXECUTIVE_ROWS),
        launch_agents_dir=tmp_path,
    )

    for label in REQUIRED_RUNNING_DAEMON_LABELS:
        assert observation["system_daemons"][label] == "RUNNING"
    report = _classify(observation)
    assert _blocking(report) == ["auto_restart_after_power_loss"]


def test_installed_daemon_unreadable_by_launchd_is_unknown_not_not_installed(
    tmp_path: Path,
) -> None:
    observation = _collect(
        runner=_runner_for(
            disabled=LAUNCHCTL_DISABLED_NO_EXECUTIVE_ROWS,
            running_labels=frozenset(),
        ),
        launch_agents_dir=tmp_path,
    )
    state = observation["system_daemons"][REQUIRED_LABEL]

    assert state != "NOT_INSTALLED"
    assert state == "UNKNOWN"
    report = _classify(observation)
    predicate = report["predicates"][f"system_daemon.{REQUIRED_LABEL}"]
    assert predicate["status"] == "UNKNOWN"
    assert predicate["code"] == "DAEMON_STATE_UNKNOWN"


def test_absent_daemon_plist_is_not_installed(tmp_path: Path) -> None:
    observation = _collect(
        runner=_runner_for(
            disabled=LAUNCHCTL_DISABLED_NO_EXECUTIVE_ROWS,
            running_labels=frozenset(),
        ),
        plists=frozenset(
            STUDIO_PLISTS - {system_daemon_plist_path(REQUIRED_LABEL)}
        ),
        launch_agents_dir=tmp_path,
    )

    assert observation["system_daemons"][REQUIRED_LABEL] == "NOT_INSTALLED"
    report = _classify(observation)
    assert (
        report["predicates"][f"system_daemon.{REQUIRED_LABEL}"]["code"]
        == "DAEMON_NOT_INSTALLED"
    )


def test_present_disabled_worker_stays_intentionally_disarmed(tmp_path: Path) -> None:
    label = "com.mastermind.executive.worker.codex"
    observation = _collect(runner=_runner_for(), launch_agents_dir=tmp_path)

    assert observation["system_daemons"][label] == "DISABLED"
    predicate = _classify(observation)["predicates"][
        f"system_daemon.{label}"
    ]
    assert predicate["status"] == "OK"
    assert predicate["code"] == "DAEMON_INTENTIONALLY_DISARMED"


def test_remote_login_enabled_needs_registration_not_just_the_system_plist(
    tmp_path: Path,
) -> None:
    enabled = _collect(
        runner=_runner_for(disabled=LAUNCHCTL_DISABLED_NO_EXECUTIVE_ROWS),
        launch_agents_dir=tmp_path,
    )
    assert enabled["remote_login"] == "ENABLED"

    unregistered = _collect(
        runner=_runner_for(
            disabled=LAUNCHCTL_DISABLED_NO_EXECUTIVE_ROWS, sshd_registered=False
        ),
        launch_agents_dir=tmp_path,
    )
    assert unregistered["remote_login"] == "UNKNOWN"


def test_remote_login_explicit_disabled_override_is_disabled(tmp_path: Path) -> None:
    observation = _collect(
        runner=_runner_for(
            disabled='disabled services = {\n\t\t"com.openssh.sshd" => disabled\n}\n'
        ),
        launch_agents_dir=tmp_path,
    )

    assert observation["remote_login"] == "DISABLED"
    report = _classify(observation)
    assert "remote_login_listener" in _blocking(report)


def test_remote_login_without_system_plist_is_not_installed(tmp_path: Path) -> None:
    observation = _collect(
        runner=_runner_for(sshd_registered=False),
        plists=frozenset(STUDIO_PLISTS - {SSHD_SYSTEM_PLIST}),
        launch_agents_dir=tmp_path,
    )

    assert observation["remote_login"] == "NOT_INSTALLED"
    assert (
        _classify(observation)["predicates"][
            "remote_login_listener"
        ]["code"]
        == "REMOTE_LOGIN_NOT_INSTALLED"
    )


def test_daemon_plist_path_is_fixed_and_rejects_unknown_labels() -> None:
    assert system_daemon_plist_path(REQUIRED_LABEL) == Path(
        f"/Library/LaunchDaemons/{REQUIRED_LABEL}.plist"
    )
    assert SSHD_SYSTEM_PLIST == Path("/System/Library/LaunchDaemons/ssh.plist")

    for label in ("../etc/passwd", SSHD_LABEL, "com.example.other"):
        with pytest.raises(RecoveryReadinessProbeError) as excinfo:
            system_daemon_plist_path(label)
        assert excinfo.value.code == "REFERENCE_INVALID"


def test_launchctl_print_command_is_fixed_and_rejects_unknown_labels() -> None:
    """The service-state query is closed over the reviewed label set alone."""

    for label in ALL_DAEMON_LABELS + (SSHD_LABEL,):
        assert launchctl_print_command(label) == (
            "/bin/launchctl",
            "print",
            f"system/{label}",
        )

    for label in (
        "com.example.other",
        "../etc/passwd",
        "system/com.mastermind.executive.control",
        "com.mastermind.executive.control ",
        "com.mastermind.executive",
        "",
        "com.mastermind.chairman-control-room",
    ):
        with pytest.raises(RecoveryReadinessProbeError) as excinfo:
            launchctl_print_command(label)
        assert excinfo.value.code == "REFERENCE_INVALID"


def test_main_emits_canonical_json_and_exits_zero(tmp_path: Path) -> None:
    stdout = io.BytesIO()
    stderr = io.StringIO()
    observation = _studio_observation()

    exit_code = main(
        ["--host-ref", HOST_REF, "--profile", EXECUTIVE_CONTROL_PROFILE],
        collector=lambda **_kwargs: observation,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["recovery_state"] == "NOT_READY"
    assert payload["schema"] == READINESS_SCHEMA
    assert payload["profile"] == EXECUTIVE_CONTROL_PROFILE
    assert stdout.getvalue().endswith(b"\n")


def test_main_emits_the_caller_named_base_profile() -> None:
    stdout = io.BytesIO()
    observation = _m1_worker_observation()

    exit_code = main(
        ["--profile", BASE_RECOVERY_PROFILE],
        collector=lambda **_kwargs: observation,
        stdout=stdout,
        stderr=io.StringIO(),
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["profile"] == BASE_RECOVERY_PROFILE
    assert payload["recovery_state"] == "READY"


def test_main_refuses_invalid_arguments_without_echoing_them() -> None:
    stderr = io.StringIO()
    exit_code = main(
        ["--host-ref", "secret-value", "--profile", BASE_RECOVERY_PROFILE],
        stdout=io.BytesIO(),
        stderr=stderr,
    )

    assert exit_code == 65
    assert "secret-value" not in stderr.getvalue()


def test_main_refuses_unsupported_platform() -> None:
    stderr = io.StringIO()

    def collector(**_kwargs: Any) -> dict[str, Any]:
        raise RecoveryReadinessProbeError("UNSUPPORTED_PLATFORM")

    exit_code = main(
        ["--profile", EXECUTIVE_CONTROL_PROFILE],
        collector=collector,
        stdout=io.BytesIO(),
        stderr=stderr,
    )

    assert exit_code == 65
    assert "UNSUPPORTED_PLATFORM" in stderr.getvalue()


# ------------------------------------------------------- explicit profile CLI


def _refusing_collector(**_kwargs: Any) -> dict[str, Any]:
    raise AssertionError("no host state may be observed before --profile is accepted")


@pytest.mark.parametrize(
    "argv,expected_code",
    [
        ([], "ARGUMENTS_INVALID"),
        (["--host-ref", HOST_REF], "ARGUMENTS_INVALID"),
        (["--profile"], "ARGUMENTS_INVALID"),
        (["--profile", "always-on-executive-host/v1"], "PROFILE_INVALID"),
        (["--profile", "home-mac-recovery-base"], "PROFILE_INVALID"),
        (["--profile", ""], "PROFILE_INVALID"),
        (
            ["--profile", BASE_RECOVERY_PROFILE, "--profile", EXECUTIVE_CONTROL_PROFILE],
            "ARGUMENTS_INVALID",
        ),
    ],
)
def test_main_requires_one_known_profile_before_observing_anything(
    argv: list[str], expected_code: str
) -> None:
    stdout = io.BytesIO()
    stderr = io.StringIO()

    exit_code = main(
        argv, collector=_refusing_collector, stdout=stdout, stderr=stderr
    )

    assert exit_code == 65
    assert expected_code in stderr.getvalue()
    assert stdout.getvalue() == b""


def test_cli_exposes_exactly_two_profiles_and_no_default() -> None:
    assert READINESS_PROFILES == (BASE_RECOVERY_PROFILE, EXECUTIVE_CONTROL_PROFILE)

    action = next(
        action
        for action in probe_module._parser()._actions
        if action.dest == "profile"
    )
    assert action.required is True
    assert action.default is None


# -------------------------------------------------------------- safety fences


def test_every_command_is_absolute_fixed_and_read_only() -> None:
    forbidden_tokens = frozenset(
        {
            "sudo",
            "-a",
            "-b",
            "-c",
            "set",
            "setrestartfreeze",
            "up",
            "down",
            "enable",
            "disable",
            "authrestart",
            "bootstrap",
            "bootout",
            "kickstart",
            "load",
            "unload",
            "reboot",
            "shutdown",
            "restart",
            "chmod",
            "chown",
            "route",
        }
    )
    commands = list(READ_ONLY_COMMANDS) + [
        launchctl_print_command(label)
        for label in ALL_DAEMON_LABELS + (SSHD_LABEL,)
    ]

    assert commands
    for command in commands:
        assert type(command) is tuple
        assert command[0].startswith("/")
        assert Path(command[0]).is_absolute()
        for token in command:
            assert token not in forbidden_tokens
    assert set(READ_ONLY_COMMANDS) == {
        PMSET_CUSTOM_COMMAND,
        SW_VERS_COMMAND,
        SYSCTL_ARM64_COMMAND,
        FDESETUP_STATUS_COMMAND,
        LAUNCHCTL_PRINT_DISABLED_COMMAND,
    }


def test_profile_is_not_command_authority(tmp_path: Path) -> None:
    """Naming a profile may change classification, never what the host observes."""

    invoked: list[tuple[str, ...]] = []

    def recording_runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        invoked.append(command)
        return _runner_for()(command)

    observation = _collect(runner=recording_runner, launch_agents_dir=tmp_path)
    argv = list(invoked)

    assert argv
    for command in argv:
        assert command in set(READ_ONLY_COMMANDS) | {
            launchctl_print_command(label)
            for label in ALL_DAEMON_LABELS + (SSHD_LABEL,)
        }

    # The collector takes no profile at all, so the same observation feeds both.
    assert "profile" not in observation
    assert "profile" not in inspect.signature(collect_recovery_observation).parameters

    for profile in READINESS_PROFILES:
        report = _classify(observation, profile)
        assert report["profile"] == profile
    assert list(invoked) == argv


def test_source_contains_no_mutation_or_privilege_escalation() -> None:
    forbidden_fragments = (
        "sudo",
        "pmset -a",
        "pmset -c",
        "fdesetup enable",
        "fdesetup disable",
        "fdesetup authrestart",
        "systemsetup -set",
        "launchctl bootstrap",
        "launchctl bootout",
        "launchctl kickstart",
        "launchctl load",
        "launchctl unload",
        "tailscale",
        "security find-generic-password",
        "/usr/sbin/route",
        "shutdown",
    )
    sources = (
        Path(probe_module.__file__).read_text(encoding="utf-8"),
        Path(
            __import__(
                "control_plane.executive_recovery_readiness",
                fromlist=["__file__"],
            ).__file__
        ).read_text(encoding="utf-8"),
    )

    for source in sources:
        for fragment in forbidden_fragments:
            assert fragment not in source, fragment


def test_report_carries_no_host_identifying_or_secret_material() -> None:
    payload = canonical_recovery_readiness_json(
        _classify(_studio_observation())
    ).decode("ascii")

    for leak in ("chriswong", "/Users/", "192.168.", "token", "password", "key ="):
        assert leak not in payload

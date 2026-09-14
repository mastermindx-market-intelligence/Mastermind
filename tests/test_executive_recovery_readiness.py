"""Model-free tests for the read-only host recovery-readiness vertical."""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from control_plane.executive_recovery_readiness import (
    DISK_FREE_FLOOR_BYTES,
    LOAD_BEARING_REQUIREMENTS,
    MIN_SUPPORTED_MACOS_MAJOR,
    PREDICATE_CODES,
    PREDICATE_PROFILE,
    READINESS_PROFILE,
    READINESS_SCHEMA,
    REPORT_FIELDS,
    USER_SESSION_CRITICAL_LABELS,
    RecoveryReadinessContractError,
    canonical_recovery_readiness_json,
    classify_recovery_readiness,
    validate_recovery_readiness_report,
)
from ops.executive_os import host_recovery_readiness as probe_module
from ops.executive_os.host_recovery_readiness import (
    FDESETUP_STATUS_COMMAND,
    LAUNCHCTL_PRINT_DISABLED_COMMAND,
    PMSET_CUSTOM_COMMAND,
    READ_ONLY_COMMANDS,
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
    states = {label: "DISABLED" for label in PREDICATE_PROFILE.disarmed_expected_labels}
    states["com.mastermind.executive.privileged"] = "NOT_INSTALLED"
    for label in PREDICATE_PROFILE.required_running_labels:
        states[label] = "RUNNING"
    return states


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
            label: "RUNNING" for label in PREDICATE_PROFILE.required_running_labels
        }
        | {
            label: "NOT_INSTALLED"
            for label in PREDICATE_PROFILE.disarmed_expected_labels
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
    report = classify_recovery_readiness(_observation())

    assert set(report) == REPORT_FIELDS
    assert report["schema"] == READINESS_SCHEMA
    assert report["profile"] == READINESS_PROFILE
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
    report = classify_recovery_readiness(_observation())

    for predicate_id, predicate in report["predicates"].items():
        assert predicate["requirement"] == PREDICATE_PROFILE.requirement(predicate_id)
        assert predicate["evidence_class"] == PREDICATE_PROFILE.evidence_class(
            predicate_id
        )
        assert predicate["code"] in PREDICATE_CODES[predicate_id]


def test_unclosed_report_field_is_refused() -> None:
    report = classify_recovery_readiness(_observation())
    report["extra_field"] = 1

    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(report)
    assert str(excinfo.value) == "REPORT_FIELDS_INVALID"


def test_derived_recovery_state_mismatch_is_refused() -> None:
    report = classify_recovery_readiness(_studio_observation())
    assert report["recovery_state"] == "NOT_READY"
    report["recovery_state"] = "READY"

    with pytest.raises(RecoveryReadinessContractError) as excinfo:
        validate_recovery_readiness_report(report)
    assert str(excinfo.value) == "RECOVERY_STATE_MISMATCH"


def test_host_ref_must_be_opaque_or_absent() -> None:
    report = classify_recovery_readiness(_observation(host_ref=None))
    assert report["host_ref"] is None

    with pytest.raises(RecoveryReadinessContractError):
        classify_recovery_readiness(_observation(host_ref="studio.local"))


# ------------------------------------------------------------- Studio-like


def test_studio_like_host_is_not_ready_only_for_autorestart() -> None:
    report = classify_recovery_readiness(_studio_observation())
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
    report = classify_recovery_readiness(_studio_observation())
    predicate = report["predicates"]["auto_restart_on_power_connect"]

    assert predicate["requirement"] == "OPTIONAL"
    assert predicate["requirement"] not in LOAD_BEARING_REQUIREMENTS
    assert predicate["status"] == "ADVISORY"
    assert predicate["code"] == "AUTO_RESTART_ON_CONNECT_DISABLED"
    assert "auto_restart_on_power_connect" not in _blocking(report)


def test_autorestart_at_connect_absent_key_is_not_applicable() -> None:
    report = classify_recovery_readiness(
        _observation(ac_power_settings={"sleep": 0, "autorestart": 1})
    )
    predicate = report["predicates"]["auto_restart_on_power_connect"]

    assert report["recovery_state"] == "READY"
    assert predicate["status"] == "NOT_APPLICABLE"
    assert predicate["code"] == "AUTO_RESTART_ON_CONNECT_NOT_EXPOSED"


# -------------------------------------------------------------- fully ready


def test_fully_ready_host_is_ready() -> None:
    report = classify_recovery_readiness(_observation())

    assert report["recovery_state"] == "READY"
    assert _blocking(report) == []
    assert report["unknown_predicates"] == []


def test_ac_sleep_enabled_blocks_always_on_profile() -> None:
    report = classify_recovery_readiness(
        _observation(
            ac_power_settings={"sleep": 15, "autorestart": 1, "autorestartatconnect": 1}
        )
    )

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["ac_sleep_policy"]
    assert report["predicates"]["ac_sleep_policy"]["code"] == "AC_SLEEP_ENABLED"


def test_intel_and_unsupported_os_fail_the_preboot_profile() -> None:
    intel = classify_recovery_readiness(_observation(apple_silicon=False))
    assert intel["recovery_state"] == "NOT_READY"
    assert intel["predicates"]["cpu_architecture"]["code"] == "ARCHITECTURE_UNSUPPORTED"

    old = classify_recovery_readiness(
        _observation(macos_product_version=f"{MIN_SUPPORTED_MACOS_MAJOR - 1}.7")
    )
    assert old["recovery_state"] == "NOT_READY"
    assert old["predicates"]["os_identity"]["code"] == "OS_UNSUPPORTED_VERSION"

    linux = classify_recovery_readiness(
        _observation(os_name="Linux", macos_product_version=None)
    )
    assert linux["recovery_state"] == "NOT_READY"
    assert linux["predicates"]["os_identity"]["code"] == "OS_NOT_DARWIN"


def test_remote_login_disabled_blocks_without_touching_sockets() -> None:
    report = classify_recovery_readiness(_observation(remote_login="DISABLED"))

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
    report = classify_recovery_readiness(_observation(ac_power_settings=None))

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
    report = classify_recovery_readiness(
        _observation(remote_login="UNKNOWN", apple_silicon=False)
    )

    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["cpu_architecture"]
    assert report["unknown_predicates"] == ["remote_login_listener"]


def test_unknown_architecture_is_never_inferred_as_pass() -> None:
    report = classify_recovery_readiness(_observation(apple_silicon=None))

    assert report["recovery_state"] == "UNKNOWN"
    assert report["predicates"]["cpu_architecture"]["code"] == "ARCHITECTURE_UNKNOWN"


# ------------------------------------------------------------------ FileVault


def test_filevault_on_is_advisory_preboot_dependency_not_a_defect() -> None:
    report = classify_recovery_readiness(_studio_observation())
    predicate = report["predicates"]["disk_encryption_state"]

    assert predicate["requirement"] == "ADVISORY"
    assert predicate["status"] == "ADVISORY"
    assert predicate["code"] == "FILEVAULT_ON"
    assert predicate["evidence_class"] == "DISK_ENCRYPTION_STATE"
    assert "disk_encryption_state" not in _blocking(report)
    assert "disk_encryption_state" not in report["unknown_predicates"]


@pytest.mark.parametrize(
    "filevault_code,expected_status",
    [
        ("FILEVAULT_ON", "ADVISORY"),
        ("FILEVAULT_ENCRYPTION_IN_PROGRESS", "ADVISORY"),
        ("FILEVAULT_DECRYPTION_IN_PROGRESS", "ADVISORY"),
        ("FILEVAULT_OFF", "OK"),
        ("FILEVAULT_STATE_UNKNOWN", "UNKNOWN"),
    ],
)
def test_filevault_states_are_classified_without_recovery_material(
    filevault_code: str, expected_status: str
) -> None:
    report = classify_recovery_readiness(_observation(filevault_code=filevault_code))
    predicate = report["predicates"]["disk_encryption_state"]

    assert predicate["status"] == expected_status
    assert predicate["code"] == filevault_code
    assert report["recovery_state"] == "READY"
    assert predicate["measurement"] is None


def test_filevault_recovery_key_text_is_never_carried_into_the_report() -> None:
    stdout = (
        "FileVault is On.\n"
        "Recovery key = ABCD-EFGH-IJKL-MNOP-QRST-UVWX\n"
        "Decryption in progress: Percent completed = 42\n"
    )
    assert parse_fdesetup_status(stdout) == "FILEVAULT_ON"

    payload = canonical_recovery_readiness_json(
        classify_recovery_readiness(_observation(filevault_code="FILEVAULT_ON"))
    )
    assert b"ABCD" not in payload
    assert b"Recovery" not in payload


# ------------------------------------------------------- daemon gate semantics


def test_intentionally_disarmed_daemons_are_not_defects() -> None:
    report = classify_recovery_readiness(_studio_observation())

    for label in PREDICATE_PROFILE.disarmed_expected_labels:
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
    report = classify_recovery_readiness(_studio_observation(system_daemons=daemons))
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
    report = classify_recovery_readiness(_studio_observation(system_daemons=daemons))
    predicate = report["predicates"][f"system_daemon.{label}"]

    assert predicate["requirement"] == "REQUIRED_RUNNING"
    assert predicate["status"] == expected_status
    assert predicate["code"] == expected_code


def test_missing_daemon_observation_is_unknown_not_absent() -> None:
    report = classify_recovery_readiness(_studio_observation(system_daemons={}))

    for label in PREDICATE_PROFILE.required_running_labels:
        predicate = report["predicates"][f"system_daemon.{label}"]
        assert predicate["status"] == "UNKNOWN"
        assert predicate["code"] == "DAEMON_STATE_UNKNOWN"


# ------------------------------------------------- user-session separation


def test_user_session_surfaces_are_reported_separately_and_never_load_bearing() -> None:
    report = classify_recovery_readiness(_observation())
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
    report = classify_recovery_readiness(_observation(user_session_agents_present=0))
    predicate = report["predicates"]["user_session_surfaces"]

    assert predicate["status"] == "ADVISORY"
    assert predicate["code"] == "USER_SESSION_AGENTS_ABSENT"
    assert predicate["measurement"] == 0
    assert report["recovery_state"] == "READY"


def test_unreadable_user_agent_directory_is_unknown_but_not_blocking() -> None:
    report = classify_recovery_readiness(_observation(user_session_agents_present=None))
    predicate = report["predicates"]["user_session_surfaces"]

    assert predicate["status"] == "UNKNOWN"
    assert predicate["code"] == "USER_SESSION_STATE_UNKNOWN"
    assert report["recovery_state"] == "READY"
    assert report["unknown_predicates"] == []


# ----------------------------------------------------------- disk free floor


def test_disk_free_floor_uses_reviewed_threshold() -> None:
    assert DISK_FREE_FLOOR_BYTES == 25 * 1024**3

    at_floor = classify_recovery_readiness(
        _observation(root_free_bytes=DISK_FREE_FLOOR_BYTES)
    )
    assert at_floor["predicates"]["disk_free_floor"]["status"] == "OK"
    assert at_floor["predicates"]["disk_free_floor"]["code"] == "DISK_FREE_ABOVE_FLOOR"
    assert (
        at_floor["predicates"]["disk_free_floor"]["measurement"]
        == DISK_FREE_FLOOR_BYTES
    )

    below = classify_recovery_readiness(
        _observation(root_free_bytes=DISK_FREE_FLOOR_BYTES - 1)
    )
    assert below["recovery_state"] == "NOT_READY"
    assert _blocking(below) == ["disk_free_floor"]
    assert below["predicates"]["disk_free_floor"]["code"] == "DISK_FREE_BELOW_FLOOR"


def test_unknown_disk_free_space_is_unknown_not_pass() -> None:
    report = classify_recovery_readiness(_observation(root_free_bytes=None))

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


def _runner_for(
    *,
    pmset: str = PMSET_STUDIO,
    sw_vers: str = "26.5\n",
    arm64: str = "1\n",
    fdesetup: str = "FileVault is On.\n",
    disabled: str = LAUNCHCTL_DISABLED_STUDIO,
    running_labels: frozenset[str] | None = None,
):
    running = (
        running_labels
        if running_labels is not None
        else frozenset(PREDICATE_PROFILE.required_running_labels)
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
        for label in PREDICATE_PROFILE.all_daemon_labels:
            if command == launchctl_print_command(label):
                if label in running:
                    return _completed(
                        command, stdout="\tstate = running\n\tpid = 1\n"
                    )
                return _completed(command, returncode=113, stdout="")
        raise AssertionError(f"unexpected command: {command!r}")

    return runner


def test_collector_reproduces_studio_like_unsafe_state(tmp_path: Path) -> None:
    for label in USER_SESSION_CRITICAL_LABELS:
        (tmp_path / f"{label}.plist").write_text("", encoding="utf-8")

    observation = collect_recovery_observation(
        host_ref=HOST_REF,
        runner=_runner_for(),
        launch_agents_dir=tmp_path,
        free_bytes=lambda: DISK_FREE_FLOOR_BYTES * 3,
        wall_time_ms=lambda: 1_789_000_000_000,
    )
    report = classify_recovery_readiness(observation)

    assert observation["ac_power_settings"]["autorestart"] == 0
    assert observation["filevault_code"] == "FILEVAULT_ON"
    assert observation["remote_login"] == "ENABLED"
    assert observation["user_session_agents_present"] == len(
        USER_SESSION_CRITICAL_LABELS
    )
    assert report["recovery_state"] == "NOT_READY"
    assert _blocking(report) == ["auto_restart_after_power_loss"]


def test_collector_reproduces_ready_state(tmp_path: Path) -> None:
    observation = collect_recovery_observation(
        host_ref=HOST_REF,
        runner=_runner_for(pmset=PMSET_READY, fdesetup="FileVault is Off.\n"),
        launch_agents_dir=tmp_path,
        free_bytes=lambda: DISK_FREE_FLOOR_BYTES * 3,
        wall_time_ms=lambda: 1_789_000_000_000,
    )
    report = classify_recovery_readiness(observation)

    assert report["recovery_state"] == "READY"
    assert _blocking(report) == []


def test_collector_refuses_non_darwin_without_running_commands() -> None:
    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        raise AssertionError("no command may run on an unsupported platform")

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


def test_collector_maps_unavailable_commands_to_unknown(tmp_path: Path) -> None:
    def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(command[0])

    observation = collect_recovery_observation(
        host_ref=None,
        runner=runner,
        launch_agents_dir=tmp_path,
        free_bytes=lambda: None,
        wall_time_ms=lambda: 1_789_000_000_000,
    )
    report = classify_recovery_readiness(observation)

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

    observation = collect_recovery_observation(
        host_ref=None,
        runner=runner,
        launch_agents_dir=tmp_path,
        free_bytes=lambda: DISK_FREE_FLOOR_BYTES * 3,
        wall_time_ms=lambda: 1_789_000_000_000,
    )

    assert observation["remote_login"] == "UNKNOWN"
    report = classify_recovery_readiness(observation)
    assert report["predicates"]["remote_login_listener"]["status"] == "UNKNOWN"


def test_main_emits_canonical_json_and_exits_zero(tmp_path: Path) -> None:
    stdout = io.BytesIO()
    stderr = io.StringIO()
    observation = _studio_observation()

    exit_code = main(
        ["--host-ref", HOST_REF],
        collector=lambda **_kwargs: observation,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    payload = json.loads(stdout.getvalue())
    assert payload["recovery_state"] == "NOT_READY"
    assert payload["schema"] == READINESS_SCHEMA
    assert stdout.getvalue().endswith(b"\n")


def test_main_refuses_invalid_arguments_without_echoing_them() -> None:
    stderr = io.StringIO()
    exit_code = main(
        ["--host-ref", "secret-value"],
        stdout=io.BytesIO(),
        stderr=stderr,
    )

    assert exit_code == 65
    assert "secret-value" not in stderr.getvalue()


def test_main_refuses_unsupported_platform() -> None:
    stderr = io.StringIO()

    def collector(**_kwargs: Any) -> dict[str, Any]:
        raise RecoveryReadinessProbeError("UNSUPPORTED_PLATFORM")

    exit_code = main([], collector=collector, stdout=io.BytesIO(), stderr=stderr)

    assert exit_code == 65
    assert "UNSUPPORTED_PLATFORM" in stderr.getvalue()


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
        launchctl_print_command(label) for label in PREDICATE_PROFILE.all_daemon_labels
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
        classify_recovery_readiness(_studio_observation())
    ).decode("ascii")

    for leak in ("chriswong", "/Users/", "192.168.", "token", "password", "key ="):
        assert leak not in payload

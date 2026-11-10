from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "executive_os"
INSTALL = OPS / "install.sh"
TEMPLATE = OPS / "control.json.template"
C1_PREP = OPS / "prepare-c1-sol-state-relay.sh"
C1_FIELDS = {
    "ceo_ingress_launchd_socket_name": "CeoIngress",
    "ceo_ingress_peer_uid": 452,
    "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
}
BRIDGE_FIELDS = {
    "dialogue_observation_launchd_socket_name": "DialogueObservation",
    "dialogue_observation_peer_uid": 457,
    "dialogue_observation_socket_path": (
        "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
    ),
    "dialogue_bridge_armed": False,
    "dialogue_wake_retry_policy": {
        "max_delivery_attempts": None,
        "retry_cooldown_s": None,
        "accepted_ttl_s": None,
        "target_unavailable_backoff_s": None,
        "reenable_on_binding_rotation": True,
        "armed": False,
    },
}


def _embedded_control_config_generator() -> str:
    source = INSTALL.read_text(encoding="utf-8")
    start_marker = "import json, os, pathlib, re, sys\nrelease_root = sys.argv.pop(1)\n"
    end_marker = '\nPY\n)\n/usr/sbin/chown "root:$CONTROL_GROUP" "$CONTROL_CONFIG"'
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _projected_digest() -> str:
    return "d" * 64


def _run_default_control_config(
    tmp_path: Path,
    *,
    release_root: Path = ROOT,
    source: Path | None = None,
    install_arm: str = "0",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    destination = tmp_path / "control.json"
    expected_sha = "a" * 40
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _embedded_control_config_generator(),
            str(release_root),
            str(destination),
            str(source) if source is not None else "",
            "/private/runtime",
            "/private/admin-checkout",
            "/private/workspaces",
            expected_sha,
            "/private/backups",
            "/private/receipts",
            "/private/provider-home",
            "/private/runs",
            "/private/canary.json",
            "/private/control-environment.json",
            "450",
            "451",
            "451",
            "501",
            "b" * 64,
            "0.147.0",
            install_arm,
            _projected_digest(),
            "",  # no attended APPLICATION configuration selected by default
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, destination


def _render_default_control_config(
    tmp_path: Path,
    *,
    release_root: Path = ROOT,
) -> dict[str, object]:
    completed, destination = _run_default_control_config(
        tmp_path,
        release_root=release_root,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(destination.read_text(encoding="utf-8"))


def _synthetic_release_schema(
    tmp_path: Path,
    *,
    c1_keys: set[str],
    bridge_keys: set[str] | None = None,
) -> Path:
    release_root = tmp_path / "release"
    scripts = release_root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    template_keys = set(json.loads(TEMPLATE.read_text(encoding="utf-8")))
    base_keys = template_keys - set(C1_FIELDS) - set(BRIDGE_FIELDS)
    optional_keys = sorted(
        base_keys
        | c1_keys
        | (bridge_keys or set())
        | {"python_runtime_provenance_digest"}
    )
    (scripts / "executive_os_phase1c.py").write_text(
        "CONTROL_CONFIG_SCHEMA_VERSION = 'mastermind.executive_control_config/v1'\n"
        "_CONFIG_REQUIRED = frozenset()\n"
        f"_CONFIG_OPTIONAL = frozenset({optional_keys!r})\n",
        encoding="utf-8",
    )
    return release_root


def test_default_installer_control_config_matches_c1_unarmed_composition(tmp_path: Path) -> None:
    generated = _render_default_control_config(tmp_path)
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    prep = C1_PREP.read_text(encoding="utf-8")

    for key, value in C1_FIELDS.items():
        assert template[key] == value
        assert generated[key] == value
        assert f'"{key}"' in prep
    for key, value in BRIDGE_FIELDS.items():
        assert template[key] == value
        assert generated[key] == value
        assert f'"{key}"' in prep

    assert "ceo_ingress_armed" not in generated
    assert "ceo_ingress_armed" not in template
    assert generated["python_runtime_provenance_digest"] == _projected_digest()


def test_installer_does_not_inject_c1_fields_into_pre_c1_release_schema(tmp_path: Path) -> None:
    release_root = _synthetic_release_schema(tmp_path, c1_keys=set())

    generated = _render_default_control_config(
        tmp_path,
        release_root=release_root,
    )

    assert set(C1_FIELDS).isdisjoint(generated)
    assert set(BRIDGE_FIELDS).isdisjoint(generated)
    assert "ceo_ingress_armed" not in generated
    assert generated["python_runtime_provenance_digest"] == _projected_digest()


def test_installer_refuses_partial_c1_release_schema(tmp_path: Path) -> None:
    release_root = _synthetic_release_schema(
        tmp_path,
        c1_keys={"ceo_ingress_socket_path"},
    )

    completed, destination = _run_default_control_config(
        tmp_path,
        release_root=release_root,
    )

    assert completed.returncode != 0
    assert "partial CeoIngress control-config schema" in completed.stderr
    assert not destination.exists()


def test_installer_refuses_partial_dialogue_bridge_release_schema(
    tmp_path: Path,
) -> None:
    release_root = _synthetic_release_schema(
        tmp_path,
        c1_keys=set(C1_FIELDS),
        bridge_keys={"dialogue_observation_socket_path"},
    )

    completed, destination = _run_default_control_config(
        tmp_path,
        release_root=release_root,
    )

    assert completed.returncode != 0
    assert "partial Executive Dialogue Bridge control-config schema" in completed.stderr
    assert not destination.exists()

SAFE_OPTIONAL_DEFAULTS = {
    "ceo_submit_armed": False,
    "coo_foreground_only": False,
    "exact_worker_claim_target": {"mode": "disabled"},
    "terminal_return_armed": False,
    "terminal_return_socket_path": "/var/db/mastermind-agent-relay/socket/agent-relay.sock",
}


def test_default_installer_seeds_safe_optional_fields(tmp_path: Path) -> None:
    value = _render_default_control_config(tmp_path)
    for key, expected in SAFE_OPTIONAL_DEFAULTS.items():
        assert value[key] == expected
        assert value[key] == json.loads(TEMPLATE.read_text())[key]


def test_old_source_migrates_only_missing_safe_fields(tmp_path: Path) -> None:
    value = _render_default_control_config(tmp_path)
    for key in SAFE_OPTIONAL_DEFAULTS:
        value.pop(key, None)
    value.pop("python_runtime_provenance_digest")
    value["model"] = "preserve-existing-model"
    source = tmp_path / "old-control.json"
    source.write_text(json.dumps(value))
    original = source.read_bytes()
    completed, destination = _run_default_control_config(tmp_path, source=source)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(destination.read_text()) == {
        **value,
        **SAFE_OPTIONAL_DEFAULTS,
        "python_runtime_provenance_digest": _projected_digest(),
    }
    assert source.read_bytes() == original


def test_existing_source_conflicting_runtime_provenance_refuses_before_write(
    tmp_path: Path,
) -> None:
    value = _render_default_control_config(tmp_path)
    value["python_runtime_provenance_digest"] = "e" * 64
    source = tmp_path / "conflicting-control.json"
    source.write_text(json.dumps(value))
    destination = tmp_path / "control.json"
    before = destination.read_bytes()

    completed, _ = _run_default_control_config(tmp_path, source=source)

    assert completed.returncode != 0
    assert "conflicts with the validated Python runtime receipt" in completed.stderr
    assert destination.read_bytes() == before


def test_existing_optional_values_are_not_replaced(tmp_path: Path) -> None:
    value = _render_default_control_config(tmp_path)
    value.update(SAFE_OPTIONAL_DEFAULTS)
    value["ceo_submit_armed"] = True
    value["terminal_return_armed"] = True
    value["exact_worker_claim_target"] = {"mode": "fixed", "definition": "existing-owner-definition", "max_age_ms": 500}
    source = tmp_path / "existing-control.json"
    source.write_text(json.dumps(value))
    completed, destination = _run_default_control_config(tmp_path, source=source)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(destination.read_text()) == value


@pytest.mark.parametrize("armed", [False, True])
def test_exact_legacy_terminal_socket_migrates_only_while_disarmed(tmp_path: Path, armed: bool) -> None:
    value = _render_default_control_config(tmp_path)
    value.update(SAFE_OPTIONAL_DEFAULTS)
    value["terminal_return_armed"] = armed
    value["terminal_return_socket_path"] = "/var/run/mastermind-agent-relay/agent-relay.sock"
    source = tmp_path / "legacy-control.json"
    source.write_text(json.dumps(value))
    before = (tmp_path / "control.json").read_bytes()
    completed, destination = _run_default_control_config(tmp_path, source=source)
    if armed:
        assert completed.returncode != 0
        assert "armed terminal-return socket migration refused" in completed.stderr
        assert destination.read_bytes() == before
    else:
        assert completed.returncode == 0, completed.stderr
        after = json.loads(destination.read_text())
        assert after["terminal_return_armed"] is False
        assert after["terminal_return_socket_path"] == SAFE_OPTIONAL_DEFAULTS["terminal_return_socket_path"]
        assert source.read_text() == json.dumps(value)


def test_unknown_legacy_socket_source_refused_without_mutation(tmp_path: Path) -> None:
    value = _render_default_control_config(tmp_path)
    value.update(SAFE_OPTIONAL_DEFAULTS)
    value["terminal_return_socket_path"] = "/var/run/untrusted-relay/agent-relay.sock"
    source = tmp_path / "foreign-control.json"
    source.write_text(json.dumps(value))
    before = (tmp_path / "control.json").read_bytes()
    completed, destination = _run_default_control_config(tmp_path, source=source)
    assert completed.returncode != 0
    assert "unrecognized terminal-return socket path refused" in completed.stderr
    assert destination.read_bytes() == before


@pytest.mark.parametrize("missing", ["terminal_return_armed", "terminal_return_socket_path"])
def test_partial_terminal_return_source_refuses_before_write(tmp_path: Path, missing: str) -> None:
    value = _render_default_control_config(tmp_path)
    value.update(SAFE_OPTIONAL_DEFAULTS)
    value.pop(missing)
    source = tmp_path / "partial-control.json"
    source.write_text(json.dumps(value))
    destination = tmp_path / "control.json"
    before = destination.read_bytes()
    completed, _ = _run_default_control_config(tmp_path, source=source)
    assert completed.returncode != 0
    assert "partial terminal-return" in completed.stderr
    assert destination.read_bytes() == before


def test_older_schema_does_not_receive_new_optional_fields(tmp_path: Path) -> None:
    release = _synthetic_release_schema(tmp_path, c1_keys=set())
    schema = release / "scripts/executive_os_phase1c.py"
    text = schema.read_text()
    for key in SAFE_OPTIONAL_DEFAULTS:
        text = text.replace(repr(key) + ", ", "").replace(", " + repr(key), "")
    schema.write_text(text)
    value = _render_default_control_config(tmp_path, release_root=release)
    assert set(SAFE_OPTIONAL_DEFAULTS).isdisjoint(value)


@pytest.mark.parametrize("field,member,replacement", [
    ("control_uid", None, 450.0),
    ("worker_uid", None, 451.0),
    ("ceo_ingress_peer_uid", None, 452.0),
    ("dialogue_observation_peer_uid", None, 457.0),
    ("allowed_peer_uids", None, [450.0, 501]),
    ("dialogue_bridge_armed", None, 0),
    ("dialogue_wake_retry_policy", "reenable_on_binding_rotation", 1),
    ("dialogue_wake_retry_policy", "armed", 0),
])
def test_installer_refuses_type_coercion_before_replacing_control(
    tmp_path: Path, field: str, member: str | None, replacement: object,
) -> None:
    """Exercise the actual embedded generator, never the privileged installer.

    These values compare equal in Python but violate the incumbent Control
    loader's integer/boolean contract. Neither source nor prior target may move.
    """
    import copy

    valid = _render_default_control_config(tmp_path)
    changed = copy.deepcopy(valid)
    if member is None:
        changed[field] = replacement
    else:
        changed[field][member] = replacement
    assert changed == valid
    assert json.dumps(changed, sort_keys=True) != json.dumps(valid, sort_keys=True)
    source = tmp_path / "wrong-type-control.json"
    source.write_text(json.dumps(changed), encoding="utf-8")
    source_before = source.read_bytes()
    destination = tmp_path / "control.json"
    before = destination.read_bytes()
    completed, actual_destination = _run_default_control_config(tmp_path, source=source)

    assert completed.returncode != 0
    assert f"control config {field} differs from the reviewed host policy" in completed.stderr
    assert actual_destination == destination and destination.read_bytes() == before
    assert source.read_bytes() == source_before
    assert list(tmp_path.glob(".control.json.*.tmp")) == []


@pytest.mark.parametrize("fault", [
    "duplicate_arm", "duplicate_nested", "nan", "positive_infinity",
    "negative_infinity", "positive_overflow", "negative_overflow",
    "unpaired_surrogate",
])
def test_installer_refuses_ambiguous_or_nonfinite_source_before_any_replacement(
    tmp_path: Path, fault: str,
) -> None:
    """Actual generator refusal preserves the prior file, mode and inode."""
    import stat

    value = _render_default_control_config(tmp_path)
    if fault == "unpaired_surrogate":
        value["model"] = "\ud800"
    raw = json.dumps(value, sort_keys=True)
    if fault == "duplicate_arm":
        original = '"ceo_submit_armed": false'
        assert raw.count(original) == 1
        raw = raw.replace(original, original + ', "ceo_submit_armed": true')
    elif fault == "duplicate_nested":
        original = '"exact_worker_claim_target": {"mode": "disabled"}'
        assert raw.count(original) == 1
        raw = raw.replace(original,
            '"exact_worker_claim_target": {"mode": "fixed", "mode": "disabled"}')
    elif fault != "unpaired_surrogate":
        token = {
            "nan": "NaN", "positive_infinity": "Infinity",
            "negative_infinity": "-Infinity", "positive_overflow": "1e999",
            "negative_overflow": "-1e999",
        }[fault]
        original = '"broker_timeout_seconds": 30.0'
        assert raw.count(original) == 1
        raw = raw.replace(original, '"broker_timeout_seconds": ' + token)

    source = tmp_path / "ambiguous-control.json"
    source.write_text(raw, encoding="utf-8")
    source_before = source.read_bytes()
    destination = tmp_path / "control.json"
    before = destination.read_bytes()
    identity = destination.stat()

    completed, actual_destination = _run_default_control_config(tmp_path, source=source)

    assert completed.returncode != 0
    assert "control config source must contain unambiguous finite UTF-8 JSON" in completed.stderr
    assert actual_destination == destination and destination.read_bytes() == before
    after = destination.stat()
    assert (after.st_ino, after.st_mtime_ns, stat.S_IMODE(after.st_mode)) == (
        identity.st_ino, identity.st_mtime_ns, stat.S_IMODE(identity.st_mode))
    assert source.read_bytes() == source_before
    assert list(tmp_path.glob(".control.json.*.tmp")) == []


@pytest.mark.parametrize("prior_arm", [False, True])
@pytest.mark.parametrize("install_arm", ["0", "1"])
def test_preserved_broker_readiness_requires_the_same_explicit_install_arm(
    tmp_path: Path, prior_arm: bool, install_arm: str,
) -> None:
    """Execute only the existing embedded generator, never the installer shell."""
    value = _render_default_control_config(tmp_path)
    value["privileged_readiness_armed"] = prior_arm
    value["privileged_broker_socket_path"] = (
        "/var/run/mastermind-executive/privileged.sock" if prior_arm else None
    )
    source = tmp_path / "preserved-control.json"
    source.write_text(json.dumps(value))
    before_source = source.read_bytes()
    destination = tmp_path / "control.json"
    before_destination = destination.read_bytes()
    completed, _ = _run_default_control_config(
        tmp_path, source=source, install_arm=install_arm,
    )
    assert source.read_bytes() == before_source
    if prior_arm == (install_arm == "1"):
        assert completed.returncode == 0, completed.stderr
        assert json.loads(destination.read_bytes()) == value
    else:
        assert completed.returncode != 0
        assert "conflicts with privileged broker installation arm" in completed.stderr
        assert destination.read_bytes() == before_destination


def test_existing_closed_memory_stanzas_roundtrip_without_minting_authority(tmp_path: Path) -> None:
    # Reuse the accepted explicit v3 fixture, not live/private configuration.
    # This proves lossless installer serialization only; actual Control loader,
    # current root/receiver/Linux/economic permission remain distinct owners.
    from tests.test_memory_v3_wire_configuration import stanzas
    value = _render_default_control_config(tmp_path)
    value.update(stanzas())
    source = tmp_path / "preserved-memory-control.json"
    source.write_text(json.dumps(value))
    before = source.read_bytes()
    completed, destination = _run_default_control_config(tmp_path, source=source)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(destination.read_bytes()) == value
    assert source.read_bytes() == before


@pytest.mark.parametrize("field,old_value", [
    ("proof_base_sha", "9" * 40),
    ("proof_source_repository", "/private/old-admin-checkout"),
])
def test_preserved_source_must_already_name_the_qualified_target_coordinates(
    tmp_path: Path, field: str, old_value: str,
) -> None:
    value = _render_default_control_config(tmp_path)
    value[field] = old_value
    source = tmp_path / "old-generation-control.json"
    source.write_text(json.dumps(value))
    source_before = source.read_bytes()
    destination = tmp_path / "control.json"
    before = destination.read_bytes()
    completed, _ = _run_default_control_config(tmp_path, source=source)
    assert completed.returncode != 0
    assert f"control config {field} differs from the reviewed host policy" in completed.stderr
    assert source.read_bytes() == source_before
    assert destination.read_bytes() == before

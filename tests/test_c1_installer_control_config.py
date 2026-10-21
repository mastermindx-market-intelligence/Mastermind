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
            "0",
            _projected_digest(),
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
    "exact_worker_claim_target": {"mode": "disabled"},
    "terminal_return_armed": False,
    "terminal_return_socket_path": "/var/run/mastermind-agent-relay/agent-relay.sock",
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

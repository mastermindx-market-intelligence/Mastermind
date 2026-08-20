from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.ohf.laboratory import FORBIDDEN_IMPORT_PREFIXES, REPO_ROOT, default_user_codex_home
from scripts.ohf.p1a_capability_policy import (
    CLASS_FORBIDDEN,
    CLASS_UNCLASSIFIED,
    LAUNCH_OK,
    LAUNCH_REFUSED_FORBIDDEN_PRESENT,
    LAUNCH_REFUSED_MISSING_REQUIRED,
    LAUNCH_REFUSED_UNCLASSIFIED,
    classify_observed,
    render_minimal_surface_config,
    write_profile_fail_closed,
)
from scripts.ohf.p1a_minimal_surface import main as p1a_main

OHF_ROOT = REPO_ROOT / "scripts" / "ohf"


def test_minimal_config_contains_verified_0_147_keys():
    text = render_minimal_surface_config(
        model="gpt-5.6-sol",
        mcp_command="python3",
        mcp_args=["-m", "scripts.ohf.fixtures.ohf_probe_mcp"],
        mcp_cwd="/tmp/repo",
    )
    assert "[features]" in text
    assert "apps = false" in text
    assert "[skills.bundled]" in text
    assert "enabled = false" in text
    assert 'approval_policy = "never"' in text
    assert 'sandbox_mode = "read-only"' in text
    assert "[mcp_servers.ohf_probe]" in text
    assert "bundled = false\n" not in text


def test_write_profile_fail_closed_on_unclassified_and_forbidden():
    missing = classify_observed(
        ["other"],
        required=["ohf-probe"],
        allowed_ambient=[],
        forbidden=[],
    )
    assert write_profile_fail_closed(missing) == LAUNCH_REFUSED_MISSING_REQUIRED
    forbidden = classify_observed(
        ["ohf-probe", "github.fetch"],
        required=["ohf-probe"],
        allowed_ambient=[],
        forbidden=["github.fetch"],
    )
    assert forbidden[CLASS_FORBIDDEN] == ["github.fetch"]
    assert write_profile_fail_closed(forbidden) == LAUNCH_REFUSED_FORBIDDEN_PRESENT
    ambient = classify_observed(
        ["ohf-probe", "skill-creator"],
        required=["ohf-probe"],
        allowed_ambient=["skill-creator"],
        forbidden=[],
    )
    assert write_profile_fail_closed(ambient) == LAUNCH_OK
    unclassified = classify_observed(
        ["ohf-probe", "mystery"],
        required=["ohf-probe"],
        allowed_ambient=[],
        forbidden=[],
    )
    assert unclassified[CLASS_UNCLASSIFIED] == ["mystery"]
    assert write_profile_fail_closed(unclassified) == LAUNCH_REFUSED_UNCLASSIFIED


def test_p1a_spike_fake_backend_is_inert(tmp_path):
    out = tmp_path / "evidence"
    assert p1a_main(["--backend", "fake", "--workdir", str(tmp_path / "lab"), "--out-dir", str(out)]) == 0
    payload = json.loads((out / "minimal_surface.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "mastermind.ohf_p1a_minimal_surface/v1"
    assert payload["auth_isolation"]["auth_json_copied"] is False
    assert payload["auth_isolation"]["auth_json_symlinked"] is False
    assert payload["auth_isolation"]["implicit_default_home_fallback"] is False
    assert payload["skills"]["fixture_discovered"] is True
    assert payload["mcp"]["fixture_server_visible"] is True


def test_p1a_does_not_import_executive_or_adapter():
    imported: set[str] = set()
    for path in (OHF_ROOT / "p1a_capability_policy.py", OHF_ROOT / "p1a_minimal_surface.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        text = path.read_text(encoding="utf-8")
        assert "WorkerExecutionAdapter" not in text
        assert "read_bytes()" not in text or "config.toml" in text
        assert "auth.json" not in text or "print" in text.lower()
    forbidden = {
        name
        for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES)
    }
    assert not forbidden


def test_p1a_live_help_refuses_default_home(tmp_path):
    rc = p1a_main(["--live", "--workdir", str(tmp_path / "lab"), "--out-dir", str(tmp_path / "out")])
    assert rc == 2
    default = default_user_codex_home()
    try:
        p1a_main(
            [
                "--live",
                "--codex-home",
                str(default),
                "--workdir",
                str(tmp_path / "lab2"),
                "--out-dir",
                str(tmp_path / "out2"),
            ]
        )
        raise AssertionError("live spike must refuse ~/.codex")
    except RuntimeError as exc:
        assert "refuses" in str(exc).lower() or "dedicated" in str(exc).lower() or "implicit" in str(exc).lower()

"""Negative gates for the opt-in, no-network DSH fixture supply preparer."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/prepare_dsh_governed_supply.py"


def module():
    spec = importlib.util.spec_from_file_location("dsh_governed_supply_preparer", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(result)
    return result


def test_fixed_provenance_is_not_manifest_supplied():
    mod = module()
    assert mod.DONOR_SHA == "4878cdabd87d4041bdaff61d04c966883b9fd07a"
    assert mod.DONOR_LOCK == "081d9f8641590187c359477a5ee01efe99e0f216d19b8ac946d50cc710cdfb8b"
    assert mod.R4_SHA == "243ec445db513db3bb9ff0cad05bc70550df972a785b8af1546d89c055cadc1f"
    assert mod.PROFILE_SHA == "c77814901495ebb3131d28b4968bd3f1cce3f39233e1c0cb580de5a7b9f9106c"
    assert mod.NODE_SHA == "913b144fdb40638b1acef7974ab3c33fbd527cc0974cb5da467ab1e6ac51b4d4"
    assert mod.PNPM_TREE_SHA == "bc046d6eee33feed3fa4782ec38761937a875b8230f36a0645d306fd5bed0b86"
    assert mod.load_qualifier().EXPECTED_PNPM_TREE_SHA == mod.PNPM_TREE_SHA


def test_incorrect_artifact_is_rejected_before_any_build(tmp_path):
    mod = module()
    fake = tmp_path / "fake.patch"
    fake.write_text("do not accept this as the R4 patch\n")
    before = {p.name for p in tmp_path.iterdir()}
    with pytest.raises(mod.Refused, match="digest mismatch"):
        mod.require_sha(fake, mod.R4_SHA, "R4")
    assert {p.name for p in tmp_path.iterdir()} == before


def test_missing_artifact_refuses_without_creating_it(tmp_path):
    mod = module()
    missing = tmp_path / "missing"
    with pytest.raises(mod.Refused, match="unavailable"):
        mod.require_sha(missing, mod.NODE_SHA, "Node")
    assert not missing.exists()


def test_output_refuses_existing_directory_and_source_overlap(tmp_path):
    mod = module()
    immutable = tmp_path / "input"
    immutable.mkdir()
    with pytest.raises(mod.Refused, match="fresh absolute"):
        mod.owned_out(immutable, (immutable,))
    with pytest.raises(mod.Refused, match="overlaps"):
        mod.owned_out(immutable / "descendant", (immutable,))
    assert not (immutable / "descendant").exists()


def test_output_refuses_nonabsolute_path(tmp_path):
    mod = module()
    with pytest.raises(mod.Refused, match="fresh absolute"):
        mod.owned_out(Path("unapproved/relative-output"), (tmp_path,))


def test_generated_mcp_boundary_is_fail_closed():
    mod = module()
    script = mod.CATALOG_SOURCE
    assert "serverName:'granted'" in script
    assert "reconnect:{enabled:false}" in script
    assert "failOnStartupError:true" in script
    assert "['read_file','search_files','write_file']" in script
    assert "process.env" not in script  # no credential projection


def test_missing_args_has_no_execution_effect(tmp_path):
    before = {p.name for p in tmp_path.iterdir()}
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode != 0
    assert "--donor" in result.stderr and "--output" in result.stderr
    assert {p.name for p in tmp_path.iterdir()} == before


def _read_search_projection_example():
    config = {
        "transport": "stdio", "serverName": "granted",
        "command": "/example/pinned-node", "args": ["/example/server.mjs"],
    }
    tools = [
        {"name": "read_file", "inputSchema": {"type": "object", "properties": {"file": {"enum": ["memo.txt"]}}}},
        {"name": "search_files", "inputSchema": {"type": "object", "properties": {"query": {"maxLength": 64}}}},
    ]
    catalog = {"serverInfo": {"name": "mmx-stdio-fixture", "version": "1"},
               "tools": tools + [{"name": "write_file", "inputSchema": {"type": "object"}}]}
    projection = {
        "schema": "mastermind.dsh_mcp_tool_projection.v1",
        "production_armed": False,
        "required": True,
        "approvalMode": "approve",
        "source": {"capability_id": "fixture.dsh.read", "profile_id": "fixture.dsh.projection"},
        "serverInfo": catalog["serverInfo"],
        "target": {"transport": "stdio", "serverName": "granted",
                   "command": config["command"], "args": config["args"]},
        "tools": [dict(t, outputSchema=None, annotations=None, execution=None) for t in tools],
    }
    return projection, config, catalog


def test_canonical_two_tool_projection_is_accepted():
    mod = module()
    projection, config, catalog = _read_search_projection_example()
    mod.require_read_search_projection(projection, config, catalog)


@pytest.mark.parametrize("mutation", [
    "ungranted_write",
    "duplicate_read",
    "schema_widened",
    "production_armed",
    "spoofed_server",
    "different_executable",
    "different_grant",
    "approval_downgrade",
    "output_schema_changed",
    "annotation_changed",
    "execution_changed",
])
def test_malformed_two_tool_projection_is_rejected(mutation):
    # Every malicious projection has the same tool count as the real grant.
    mod = module()
    projection, config, catalog = _read_search_projection_example()
    if mutation == "ungranted_write":
        projection["tools"][1]["name"] = "write_file"
    elif mutation == "duplicate_read":
        projection["tools"][1]["name"] = "read_file"
    elif mutation == "schema_widened":
        projection["tools"][0]["inputSchema"] = {"type": "object"}
    elif mutation == "production_armed":
        projection["production_armed"] = True
    elif mutation == "spoofed_server":
        projection["serverInfo"] = {"name": "untrusted-server", "version": "1"}
    elif mutation == "different_executable":
        projection["target"]["command"] = "/usr/bin/other-node"
    elif mutation == "different_grant":
        projection["source"]["capability_id"] = "fixture.dsh.write"
    elif mutation == "approval_downgrade":
        projection["approvalMode"] = "never"
    elif mutation == "output_schema_changed":
        projection["tools"][0]["outputSchema"] = {"type": "string"}
    elif mutation == "annotation_changed":
        projection["tools"][1]["annotations"] = {"readOnlyHint": False}
    elif mutation == "execution_changed":
        projection["tools"][0]["execution"] = {"timeoutMs": 0}
    assert len(projection["tools"]) == 2
    with pytest.raises(mod.Refused, match="MCP projection"):
        mod.require_read_search_projection(projection, config, catalog)


def test_ignored_installed_dependency_mutation_changes_frozen_digest(tmp_path):
    mod = module()
    verifier = mod.load_qualifier()
    donor = tmp_path / "donor"
    package = donor / "node_modules/.pnpm/example@1/node_modules/example"
    package.mkdir(parents=True)
    code = package / "index.js"
    code.write_text("module.exports = 1;\n")
    before = verifier.materialized_dependency_digest(donor)
    assert len(before) == 64
    code.write_text("module.exports = 999;\n")
    assert verifier.materialized_dependency_digest(donor) != before
    # Symlink substitution cannot silently reach code outside the pinned donor.
    link = donor / "node_modules/.pnpm/external"
    outside = tmp_path / "outsider"
    outside.write_text("untracked hostile input")
    link.symlink_to(outside)
    with pytest.raises(verifier.QualificationRefused, match="escapes frozen donor"):
        verifier.materialized_dependency_digest(donor)


def test_wrong_materialized_dependency_fingerprint_refuses_before_clone(tmp_path, monkeypatch):
    mod = module()
    verifier = mod.load_qualifier()
    monkeypatch.setattr(verifier, "materialized_dependency_digest", lambda _donor: "0" * 64)
    with pytest.raises(mod.Refused, match="immutable donor lock closure"):
        mod.require_dependency_closure(verifier, tmp_path)
    monkeypatch.setattr(verifier, "materialized_dependency_digest",
                        lambda _donor: mod.PNPM_TREE_SHA)
    mod.require_dependency_closure(verifier, tmp_path)


def test_git_identity_gate_excludes_ambient_provider_and_git_settings(tmp_path, monkeypatch):
    from types import SimpleNamespace

    mod = module()
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong-git-dir"))
    monkeypatch.setenv("OPENAI_API_KEY", "not-to-be-inherited")
    observed = []

    def fake_run(*_args, **kwargs):
        observed.append({"arguments": _args[0], **kwargs})
        return SimpleNamespace(stdout="frozen-head\n")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.safe_donor_git(tmp_path, "rev-parse", "HEAD") == "frozen-head"
    assert len(observed) == 1
    assert observed[0]["timeout"] == 20
    assert "GIT_DIR" not in observed[0]["env"]
    assert "OPENAI_API_KEY" not in observed[0]["env"]
    assert observed[0]["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert observed[0]["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert "core.fsmonitor=false" in observed[0]["arguments"]
    assert "core.hooksPath=/dev/null" in observed[0]["arguments"]


def test_git_identity_gate_timeout_refuses(tmp_path, monkeypatch):
    mod = module()

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["git"], 20)

    monkeypatch.setattr(mod.subprocess, "run", timeout)
    with pytest.raises(mod.Refused, match="git provenance preflight refused"):
        mod.safe_donor_git(tmp_path, "status", "--porcelain")


def test_pnpm_symlink_retarget_and_executable_bit_change_are_detected(tmp_path):
    import stat

    mod = module()
    qualifier = mod.load_qualifier()
    donor = tmp_path / "donor"
    pnpm = donor / "node_modules/.pnpm"
    for name in ("pkg-a", "pkg-b"):
        root = pnpm / name
        root.mkdir(parents=True)
        (root / "index.js").write_text("module.exports = 'same bytes';\n")
    links = pnpm / "node_modules"
    links.mkdir()
    link = links / "selected"
    link.symlink_to("../pkg-a", target_is_directory=True)
    initial = qualifier.materialized_dependency_digest(donor)
    link.unlink()
    link.symlink_to("../pkg-b", target_is_directory=True)
    retargeted = qualifier.materialized_dependency_digest(donor)
    assert retargeted != initial  # link text is part of the frozen closure
    code = pnpm / "pkg-a/index.js"
    code.chmod(code.stat().st_mode | stat.S_IXUSR)
    assert qualifier.materialized_dependency_digest(donor) != retargeted

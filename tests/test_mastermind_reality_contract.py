"""Contract tests for the production-inert Mastermind Reality R1 package."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plugins/mastermind-reality"
MANIFEST = PACKAGE / ".codex-plugin/plugin.json"
SCHEMA = PACKAGE / "references/reality-observation.schema.json"
BOUNDARY = PACKAGE / "references/reality-boundary.md"
CATALOG = PACKAGE / "references/catalog.fragment.json"
SKILL = PACKAGE / "skills/inspect-product-journey/SKILL.md"

EXPECTED_PACKAGE_FILES = {
    ".codex-plugin/plugin.json",
    "references/catalog.fragment.json",
    "references/reality-boundary.md",
    "references/reality-observation.schema.json",
    "skills/inspect-product-journey/SKILL.md",
}


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_observation() -> dict[str, object]:
    control = lambda status, detail: {"status": status, "detail": detail}
    return {
        "schema": "mastermind.reality_observation.v1",
        "observation_id": "REALITY-CONTROL-ROOM-R1",
        "capability_state": "PARTIAL",
        "persona": {
            "name": "Chairman",
            "user_job": "See what truly needs attention",
            "non_goals": ["account actuation", "new browser backend"],
        },
        "target": {
            "product": "Chairman Control Room",
            "environment": "approved local product",
            "locator": "owner-qualified loopback target",
            "authorization_ref": "current live assignment",
            "surface_class": "APPROVED_PRODUCT",
        },
        "source_relationship": {
            "protected_sha": "b" * 40,
            "observed_deployed_sha": "7" * 40,
            "relation": "DIFFERENT",
        },
        "journey": {
            "steps": [
                {
                    "action": "load the decision surface",
                    "result": "degraded state rendered honestly",
                }
            ],
            "outcome": "PARTIAL",
        },
        "capture": {
            "started_at": "2026-09-08T05:30:00Z",
            "completed_at": "2026-09-08T05:30:10Z",
            "screenshots": [
                {
                    "artifact_ref": "desktop.png",
                    "sha256": "a" * 64,
                    "mime_type": "image/png",
                    "bytes": 100,
                    "bytes_present": True,
                    "model_consumed": True,
                    "viewport": {"width": 1440, "height": 900},
                    "data_state": "DEGRADED",
                },
                {
                    "artifact_ref": "mobile.png",
                    "sha256": "c" * 64,
                    "mime_type": "image/png",
                    "bytes": 90,
                    "bytes_present": True,
                    "model_consumed": True,
                    "viewport": {"width": 390, "height": 844},
                    "data_state": "DEGRADED",
                },
            ],
            "semantic_evidence": {
                "artifact_ref": "semantic.json",
                "sha256": "d" * 64,
                "consumed": True,
            },
            "runtime_evidence": [
                {
                    "artifact_ref": "state.json",
                    "sha256": "e" * 64,
                    "coverage": "rendered state envelope",
                    "consumed": True,
                }
            ],
        },
        "findings": [
            {
                "basis": "MODEL_INFERENCE",
                "claim": "raw diagnostics displace the decision outcome",
                "evidence_refs": ["desktop.png", "mobile.png", "semantic.json"],
                "unknowns": ["causal user impact is not instrumented"],
            }
        ],
        "negative_controls": {
            "wrong_target": control("DETECTED", "target identity differs"),
            "stale_capture": control("DETECTED", "source clocks expose age"),
            "different_build": control("DETECTED", "deployed and protected revisions differ"),
            "different_viewport_or_data_state": control("DETECTED", "receipts remain distinct"),
            "missing_screenshot_bytes": control("REFUSED", "visual claims require bytes"),
            "broken_browser_connection": control("DETECTED", "provider-specific disconnection retained"),
            "excluded_account_surface": control("REFUSED", "managed account surface is outside scope"),
        },
        "limitations": ["no accepted runtime admission"],
        "next_action": {
            "owner": "current package integration owner",
            "action": "review the exact source candidate and integration seam",
            "terminal": False,
        },
    }


def validator() -> Draft202012Validator:
    schema = load_json(SCHEMA)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_manifest_is_closed_skills_only_read_package() -> None:
    manifest = load_json(MANIFEST)
    assert manifest == {
        "name": "mastermind-reality",
        "version": "0.1.0",
        "description": (
            "Governed inspection of one approved Mastermind product journey with actual visual, "
            "semantic, runtime, uncertainty, and negative-control evidence."
        ),
        "author": {"name": "Mastermind-X"},
        "skills": "./skills/",
        "interface": {
            "displayName": "Mastermind Reality",
            "shortDescription": "Inspect real product journeys and degraded states",
            "longDescription": (
                "Inspect one approved Mastermind product journey through existing browser and "
                "observability owners, consume actual pixels, and return bounded evidence without "
                "creating another browser, lifecycle, identity, evidence, or control plane."
            ),
            "developerName": "Mastermind-X",
            "category": "Productivity",
            "capabilities": ["Read"],
        },
    }


def test_package_file_inventory_is_closed() -> None:
    actual = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert actual == EXPECTED_PACKAGE_FILES


def test_observation_schema_accepts_closed_receipt() -> None:
    validator().validate(valid_observation())


def test_observation_rejects_unconsumed_screenshot_bytes() -> None:
    candidate = deepcopy(valid_observation())
    candidate["capture"]["screenshots"][0]["model_consumed"] = False
    assert list(validator().iter_errors(candidate))


def test_observation_rejects_missing_screenshot_bytes() -> None:
    candidate = deepcopy(valid_observation())
    candidate["capture"]["screenshots"][0]["bytes_present"] = False
    assert list(validator().iter_errors(candidate))


def test_observation_rejects_managed_account_as_target() -> None:
    candidate = deepcopy(valid_observation())
    candidate["target"]["surface_class"] = "MANAGED_CHAIRMAN_ACCOUNT"
    assert list(validator().iter_errors(candidate))


def test_observation_rejects_known_relation_without_deployed_sha() -> None:
    candidate = deepcopy(valid_observation())
    candidate["source_relationship"]["observed_deployed_sha"] = None
    candidate["source_relationship"]["relation"] = "MATCH"
    assert list(validator().iter_errors(candidate))


def test_skill_requires_current_source_pixels_owner_reuse_and_negative_controls() -> None:
    text = SKILL.read_text(encoding="utf-8")
    for marker in (
        "Read protected Mastermind `master`",
        "`docs/sol_skills/INDEX.md`",
        "same exact commit",
        "modifying workflow is unavailable",
        "actual PNG bytes",
        "model must inspect",
        "existing browser owner",
        "existing trace owner",
        "existing observability owner",
        "wrong target",
        "stale capture",
        "different build",
        "different viewport or data state",
        "missing screenshot bytes",
        "broken browser connection",
        "excluded account surface",
        "EFFECT_UNKNOWN",
    ):
        assert marker in text


def test_boundary_refuses_duplicate_planes_and_false_completion() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")
    for marker in (
        "no new browser registry",
        "no credential passthrough",
        "managed Chairman account surfaces",
        "source green is not production proof",
        "unknown is not zero",
        "existing evidence owner",
        "NOT_APPLIED",
        "APPLIED",
        "EFFECT_UNKNOWN",
    ):
        assert marker in text


def test_catalog_fragment_is_inert_and_package_local() -> None:
    fragment = load_json(CATALOG)
    assert fragment == {
        "schema": "mastermind.plugin_catalog_fragment.v1",
        "plugin": "mastermind-reality",
        "package_path": "plugins/mastermind-reality",
        "manifest_path": "plugins/mastermind-reality/.codex-plugin/plugin.json",
        "skills": ["inspect-product-journey"],
        "capabilities": ["Read"],
        "source_state": "SOURCE_CANDIDATE",
        "installation_state": "NOT_INSTALLED",
    }


def test_package_contains_no_live_binding_or_secret_shape() -> None:
    forbidden_names = {".app.json", "mcp.json", ".mcp.json"}
    forbidden_markers = (
        "xoxb-",
        "xoxp-",
        "ghp_",
        "github_pat_",
        "sk-proj-",
        "sk-ant-",
        "begin private key",
        "begin openssh private key",
    )
    for path in PACKAGE.rglob("*"):
        if not path.is_file():
            continue
        assert path.name not in forbidden_names
        text = path.read_text(encoding="utf-8").casefold()
        assert not any(marker in text for marker in forbidden_markers)

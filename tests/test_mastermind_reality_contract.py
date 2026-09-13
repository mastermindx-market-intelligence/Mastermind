"""Contract tests for the production-inert Mastermind Reality R1 package."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plugins/mastermind-reality"
MANIFEST = PACKAGE / ".codex-plugin/plugin.json"
SCHEMA = PACKAGE / "references/reality-observation.schema.json"
BOUNDARY = PACKAGE / "references/reality-boundary.md"
CATALOG = PACKAGE / "references/catalog.fragment.json"
SKILL = PACKAGE / "skills/inspect-product-journey/SKILL.md"
OBSERVATION = ROOT / "research/MASTERMIND_REALITY_R1_CONTROL_ROOM_OBSERVATION_2026-09-07.json"

EXPECTED_PACKAGE_FILES = {
    ".codex-plugin/plugin.json",
    "references/catalog.fragment.json",
    "references/reality-boundary.md",
    "references/reality-observation.schema.json",
    "skills/inspect-product-journey/SKILL.md",
}
APP_ID_RE = re.compile(
    r"\b(?:asdk_app|connector|templated_apps|plugin)_[A-Za-z0-9_-]+\b"
)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_observation() -> dict[str, object]:
    control = lambda status, detail: {"status": status, "detail": detail}
    proof_digest = "9" * 64
    consumption = lambda suffix: {
        "state": "CONSUMED",
        "consumer_ref": "web-sol/current-chairman-directed-session",
        "method": "MODEL_VISIBLE_IMAGE_DELIVERY",
        "proof_ref": f"private-evidence/visual-consumption-{suffix}.json",
        "proof_sha256": proof_digest,
        "consumed_at": None,
        "limitation": "The provider exposed no native consumption timestamp.",
    }
    return {
        "schema": "mastermind.reality_observation.v1",
        "observation_id": "REALITY-CONTROL-ROOM-R1",
        "capability_state": "PARTIAL",
        "recorded_at": "2026-09-08T06:15:00Z",
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
            "observed_at": "2026-09-08T05:30:00Z",
            "relation": "DIFFERENT",
            "revision_comparison": "DISTINCT",
        },
        "journey": {
            "steps": [{"action": "load the decision surface", "result": "degraded state rendered honestly"}],
            "outcome": "PARTIAL",
        },
        "capture": {
            "started_at": "2026-09-08T05:30:00Z",
            "completed_at": "2026-09-08T05:30:10Z",
            "screenshots": [
                {
                    "artifact_ref": "private-evidence/desktop.png",
                    "sha256": "a" * 64,
                    "mime_type": "image/png",
                    "bytes": 100,
                    "bytes_present": True,
                    "consumption": consumption("desktop"),
                    "viewport": {"width": 1440, "height": 900},
                    "data_state": "DEGRADED",
                },
                {
                    "artifact_ref": "private-evidence/mobile.png",
                    "sha256": "c" * 64,
                    "mime_type": "image/png",
                    "bytes": 90,
                    "bytes_present": True,
                    "consumption": consumption("mobile"),
                    "viewport": {"width": 390, "height": 844},
                    "data_state": "DEGRADED",
                },
            ],
            "semantic_evidence": {
                "state": "AVAILABLE",
                "artifacts": [
                    {
                        "artifact_ref": "private-evidence/desktop-semantic.json",
                        "sha256": "d" * 64,
                        "coverage": "desktop semantic snapshot",
                        "consumed": True,
                    },
                    {
                        "artifact_ref": "private-evidence/mobile-semantic.json",
                        "sha256": "f" * 64,
                        "coverage": "mobile semantic snapshot",
                        "consumed": True,
                    },
                ],
                "reason": None,
            },
            "runtime_evidence": {
                "state": "AVAILABLE",
                "artifacts": [
                    {
                        "artifact_ref": "private-evidence/state.json",
                        "sha256": "e" * 64,
                        "coverage": "rendered state envelope",
                        "consumed": True,
                    }
                ],
                "reason": None,
            },
        },
        "findings": [
            {
                "basis": "MODEL_INFERENCE",
                "claim": "raw diagnostics displace the decision outcome",
                "evidence_refs": [
                    "private-evidence/desktop.png",
                    "private-evidence/mobile.png",
                    "private-evidence/semantic.json",
                ],
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
        "effect": {
            "state": "NOT_APPLIED",
            "operation_ref": "reality-control-room-r1",
            "carrier_ref": "web-sol/current-chairman-directed-session",
            "evidence_refs": ["private-evidence/capture-set.json"],
            "detail": "The one-shot journey was read-only and produced no product or account mutation.",
        },
        "cleanup": {
            "state": "CLEAN",
            "temporary_processes": "ABSENT",
            "temporary_profile": "REMOVED",
            "shared_resources": "UNCHANGED",
            "evidence_refs": ["private-evidence/cleanup-attestation.json"],
            "detail": "The isolated browser process and temporary profile were absent at return.",
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
    assert load_json(MANIFEST) == {
        "name": "mastermind-reality",
        "version": "0.1.0",
        "description": (
            "Governed inspection of one approved Mastermind product journey "
            "with actual visual, semantic, runtime, uncertainty, and "
            "negative-control evidence."
        ),
        "author": {"name": "Mastermind-X"},
        "skills": "./skills/",
        "interface": {
            "displayName": "Mastermind Reality",
            "shortDescription": (
                "Inspect real product journeys and degraded states"
            ),
            "longDescription": (
                "Inspect one approved Mastermind product journey through "
                "existing browser and observability owners, consume actual "
                "pixels, and return bounded evidence without creating another "
                "browser, lifecycle, identity, evidence, or control plane."
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


def test_published_control_room_observation_validates() -> None:
    validator().validate(load_json(OBSERVATION))


def test_published_observation_uses_exact_retained_evidence_refs() -> None:
    observation = load_json(OBSERVATION)
    assert isinstance(observation, dict)

    retained = {
        "private-evidence/control-room-desktop-1440x900.png":
            "6ec2806af08b02d4b1761517ec86cc28a87659fcd57dff3407186d65acb2fbf5",
        "private-evidence/control-room-mobile-390x844.png":
            "d0e9308c3ed055b7b2fecdbfc947a0f2efbfcecde3e0b0d9e3c5b7c1edecbeea",
        "private-evidence/visual-consumption-attestation-20260908.json":
            "b46f7b966655811309fef4d0c9941f72ff44f1bc890b19dbde747413112fb4fc",
        "private-evidence/control-room-desktop-1440x900.semantic.json":
            "0c02ab077cb2ca4ed5c08483455679e7c8f2aced2d0bcd654e78cf4611b13e27",
        "private-evidence/control-room-mobile-390x844.semantic.json":
            "c70cfe6db96b3b4f6451540e6665219a8e3943237c34daba420a21ce3c2ea7d5",
        "private-evidence/control-room-desktop-1440x900.state.json":
            "9540945a0f841067e9b362d6d91f19333ebcc999f0fe8076060bf1a8e1923027",
        "private-evidence/control-room-desktop-1440x900.trace.zip":
            "adbe826424fc81412a2f4d8c7b31a3bfe7e1c9a491a9d784c313d86ef86f2289",
    }

    capture = observation["capture"]
    evidence = []
    for screenshot in capture["screenshots"]:
        evidence.append((screenshot["artifact_ref"], screenshot["sha256"]))
        consumption = screenshot["consumption"]
        evidence.append((consumption["proof_ref"], consumption["proof_sha256"]))
    for family in ("semantic_evidence", "runtime_evidence"):
        evidence.extend(
            (artifact["artifact_ref"], artifact["sha256"])
            for artifact in capture[family]["artifacts"]
        )

    assert set(evidence) == set(retained.items())


def test_observation_rejects_unconsumed_screenshot_bytes() -> None:
    candidate = deepcopy(valid_observation())
    candidate["capture"]["screenshots"][0]["consumption"]["state"] = "UNCONSUMED"
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
    candidate["source_relationship"]["revision_comparison"] = "EQUAL"
    assert list(validator().iter_errors(candidate))


def test_observation_rejects_non_utc_capture_timestamp() -> None:
    candidate = deepcopy(valid_observation())
    candidate["capture"]["started_at"] = "September 8, 2026"
    assert list(validator().iter_errors(candidate))


def test_observation_rejects_oversized_finding_claim() -> None:
    candidate = deepcopy(valid_observation())
    candidate["findings"][0]["claim"] = "x" * 4001
    assert list(validator().iter_errors(candidate))


def test_skill_requires_source_pixels_owner_reuse_and_controls() -> None:
    text = SKILL.read_text(encoding="utf-8")
    markers = (
        "Read protected Mastermind `master`",
        "`docs/sol_skills/INDEX.md`",
        "same exact commit",
        "modifying workflow is unavailable",
        "The model must inspect the actual PNG bytes.",
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
    )
    assert all(marker in text for marker in markers)


def test_boundary_refuses_duplicate_planes_and_false_completion() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")
    markers = (
        "no new browser registry",
        "no credential passthrough",
        "managed Chairman account surfaces",
        "source green is not production proof",
        "unknown is not zero",
        "existing evidence owner",
        "NOT_APPLIED",
        "APPLIED",
        "EFFECT_UNKNOWN",
    )
    assert all(marker in text for marker in markers)


def test_catalog_fragment_is_inert_package_local_and_not_app_id_shaped() -> None:
    fragment = load_json(CATALOG)
    assert fragment == {
        "schema": "mastermind.reality_catalog_fragment.v1",
        "plugin": "mastermind-reality",
        "package_path": "plugins/mastermind-reality",
        "manifest_path": "plugins/mastermind-reality/.codex-plugin/plugin.json",
        "skills": ["inspect-product-journey"],
        "capabilities": ["Read"],
        "source_state": "SOURCE_CANDIDATE",
        "installation_state": "NOT_INSTALLED",
    }
    assert APP_ID_RE.search(json.dumps(fragment, sort_keys=True)) is None


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


def test_schema_accepts_recording_effect_cleanup_and_consumption_receipts() -> None:
    validator().validate(valid_observation())


def test_schema_accepts_explicitly_unavailable_runtime_evidence() -> None:
    candidate = valid_observation()
    candidate["capture"]["runtime_evidence"] = {
        "state": "UNAVAILABLE",
        "artifacts": [],
        "reason": "The runtime owner was unavailable for this observation epoch.",
    }
    validator().validate(candidate)


def test_schema_rejects_available_evidence_without_artifacts() -> None:
    candidate = valid_observation()
    candidate["capture"]["semantic_evidence"] = {
        "state": "AVAILABLE",
        "artifacts": [],
        "reason": None,
    }
    assert list(validator().iter_errors(candidate))


def test_schema_rejects_absolute_and_traversal_artifact_refs() -> None:
    for unsafe in (
        "/Users/example/private.png",
        "../private.png",
        "private-evidence/../../private.png",
        "https://example.invalid/image.png?token=secret",
    ):
        candidate = valid_observation()
        candidate["capture"]["screenshots"][0]["artifact_ref"] = unsafe
        assert list(validator().iter_errors(candidate)), unsafe


def test_schema_rejects_inconsistent_source_relationship_claim() -> None:
    candidate = valid_observation()
    candidate["source_relationship"]["relation"] = "MATCH"
    assert list(validator().iter_errors(candidate))


def test_schema_rejects_consumption_without_proof_reference() -> None:
    candidate = valid_observation()
    del candidate["capture"]["screenshots"][0]["consumption"]["proof_ref"]
    assert list(validator().iter_errors(candidate))


def test_skill_requires_closed_cross_field_and_missing_evidence_checks() -> None:
    text = SKILL.read_text(encoding="utf-8")
    for marker in (
        "recorded_at",
        "completion does not precede start",
        "MATCH requires identical source revisions",
        "DIFFERENT requires distinct source revisions",
        "evidence reference resolves to one declared artifact",
        "UNAVAILABLE with a concrete reason",
        "consumption proof",
        "effect and cleanup",
    ):
        assert marker in text


def test_boundary_requires_consumption_proof_and_explicit_absence() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")
    for marker in (
        "bare boolean is not consumption proof",
        "explicitly `UNAVAILABLE`",
        "safe owner-relative reference",
        "effect and cleanup",
        "recorded_at",
        "MATCH requires identical",
        "DIFFERENT requires distinct",
    ):
        assert marker in text

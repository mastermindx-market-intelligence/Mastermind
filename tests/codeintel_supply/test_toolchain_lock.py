from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from experiments.codeintel_supply.toolchain_lock import (
    LockValidationError,
    SupplyEvidenceError,
    load_toolchain_lock,
    lock_digest,
    validate_toolchain_lock,
    verify_phase_p_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json"
SCHEMA_PATH = ROOT / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json"


def _lock() -> dict[str, object]:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def _phase_p_evidence(document: dict[str, object]) -> dict[str, object]:
    components = document["components"]
    return {
        "platform": "linux-x64",
        "components": {
            name: {
                "source": value["source"],
                "dependency_lock": value["dependency_lock"],
                "license": value["license"],
                "artifacts": value["artifacts"],
            }
            for name, value in components.items()
        },
    }


def test_committed_lock_validates_against_its_closed_schema_and_has_a_stable_digest():
    jsonschema = pytest.importorskip("jsonschema")
    document = _lock()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(schema).validate(document)
    validated = validate_toolchain_lock(document)

    assert validated["schema"] == "mastermind.codeintel_experiment_toolchain_lock.v1"
    assert validated["operation_key"] == (
        "mastermind-codeintel-b0-hosted-tool-bundle-forge-20260902-sol-001"
    )
    assert validated["supported_platforms"] == ["linux-x64"]
    assert validated["lock_digest"] == lock_digest(document)
    assert set(validated["components"]) == {
        "serena",
        "pyright",
        "typescript_language_server",
        "typescript",
        "zoekt",
        "node_runtime",
        "go_runtime",
    }


@pytest.mark.parametrize(
    "mutation, code",
    [
        (
            lambda value: value["components"]["serena"]["artifacts"][0].pop("checksum"),
            "ARTIFACT_CHECKSUM_MISSING",
        ),
        (
            lambda value: value["components"]["pyright"]["source"].update(commit="a" * 39),
            "SOURCE_COMMIT_INVALID",
        ),
        (
            lambda value: value["components"]["typescript_language_server"]["platforms"].append("darwin-arm64"),
            "UNSUPPORTED_PLATFORM",
        ),
        (
            lambda value: value["components"]["zoekt"]["build_recipe"].update(sha256="0" * 64),
            "BUILD_RECIPE_DIGEST_MISMATCH",
        ),
    ],
)
def test_lock_refuses_incomplete_or_mutated_supply_identity(mutation, code):
    document = copy.deepcopy(_lock())
    mutation(document)

    with pytest.raises(LockValidationError, match=code):
        validate_toolchain_lock(document)


def test_lock_digest_detects_a_silent_committed_document_change():
    document = _lock()
    document["components"]["node_runtime"]["artifacts"][0]["checksum"]["value"] = "f" * 64

    with pytest.raises(LockValidationError, match="LOCK_DIGEST_MISMATCH"):
        validate_toolchain_lock(document)


def test_phase_p_evidence_must_match_each_resolved_supply_identity():
    document = _lock()
    evidence = _phase_p_evidence(document)

    assert verify_phase_p_evidence(document, evidence) == evidence

    altered = copy.deepcopy(document)
    altered["components"]["zoekt"]["source"]["tree_sha1"] = "e" * 40
    altered["lock_digest"] = lock_digest(altered)

    with pytest.raises(SupplyEvidenceError, match="SOURCE_TREE_MISMATCH"):
        verify_phase_p_evidence(altered, evidence)

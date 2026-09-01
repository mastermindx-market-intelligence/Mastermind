"""EVAL-R0 evaluation-graph verification (design §6.4, plan §5.3).

Implements the second of R0's two verification scopes. R0 exposes:

  1. SHAPE_VALID              -- scripts.agent_eval.contracts
  2. EVALUATION_GRAPH_VERIFIED -- this module
  3. EVIDENCE_CONTENT_VERIFIED -- NOT implemented; reserved for EVAL-C0/OHF2

No function in this module ever returns or claims EVIDENCE_CONTENT_VERIFIED.
A graph-verified artifact whose external artifact refs are only sealed
(digest known, bytes unread) is never mislabeled content-verified.
"""
from __future__ import annotations

from dataclasses import dataclass

from scripts.agent_eval import contracts
from scripts.agent_eval.errors import ContractDefect, VerificationContextError
from scripts.agent_eval.resolver import ArtifactResolver

GRAPH_VERIFIED_SCOPE = "EVALUATION_GRAPH_VERIFIED"


@dataclass(frozen=True)
class VerificationResult:
    """One graph-verification claim. ``external_content_unverified_refs`` is
    the exact, sorted set of owner-native artifact refs this result does
    NOT claim to have read/matched bytes for -- R0 always states this
    honestly rather than silently implying content verification."""

    scope: str
    artifact_id: str
    artifact_digest: str
    external_content_unverified_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.scope != GRAPH_VERIFIED_SCOPE:
            raise ValueError("VerificationResult.scope must be EVALUATION_GRAPH_VERIFIED in R0")


def _collect_scenario_artifact_refs(document: dict) -> set[str]:
    refs = {document["input_fixture"]["artifact_ref"], document["expected_contract"]["artifact_ref"]}
    for item in document["source_policy"]["allowlist_artifacts"]:
        refs.add(item["artifact_ref"])
    return refs


def _collect_configuration_artifact_refs(document: dict) -> set[str]:
    refs = {
        document["procedure"]["instruction_bundle"]["artifact_ref"],
        document["context"]["context_packet"]["artifact_ref"],
    }
    handoff = document["procedure"].get("handoff")
    if handoff:
        refs.add(handoff["artifact_ref"])
    retrieval = document["context"].get("retrieval_configuration")
    if retrieval:
        refs.add(retrieval["artifact_ref"])
    return refs


def verify_scenario_graph(document: dict, resolver: ArtifactResolver) -> VerificationResult:
    """Scenario graph verification checks shape/own digest and reports
    input/expected/allowlist artifacts as externally sealed/unverified; it
    never claims content verification."""
    contracts.validate_scenario_shape(document)
    external_refs = _collect_scenario_artifact_refs(document)
    return VerificationResult(
        scope=GRAPH_VERIFIED_SCOPE,
        artifact_id=document["scenario_id"],
        artifact_digest=document["scenario_digest"],
        external_content_unverified_refs=tuple(sorted(external_refs)),
    )


def verify_configuration_graph(document: dict, resolver: ArtifactResolver) -> VerificationResult:
    contracts.validate_configuration_shape(document)
    external_refs = _collect_configuration_artifact_refs(document)
    return VerificationResult(
        scope=GRAPH_VERIFIED_SCOPE,
        artifact_id=document["configuration_id"],
        artifact_digest=document["configuration_digest"],
        external_content_unverified_refs=tuple(sorted(external_refs)),
    )


def verify_experiment_graph(document: dict, resolver: ArtifactResolver) -> VerificationResult:
    """Resolves every scenario/configuration referenced by the experiment,
    checks exact IDs/digests/corpus revisions, and runs compatibility for
    every scenario x arm pairing. Missing/substituted/incompatible
    artifacts fail verification -- they never downgrade to a warning."""
    contracts.validate_experiment_shape(document)
    defects: list[ContractDefect] = []
    resolved_scenarios: dict[tuple[str, int], dict] = {}
    for index, scenario_ref in enumerate(document["scenario_refs"]):
        path = f"$.scenario_refs[{index}]"
        found = resolver.resolve_scenario(scenario_ref["scenario_id"], scenario_ref["scenario_version"])
        if found is None:
            defects.append(ContractDefect(path, "SCENARIO_NOT_RESOLVED", "referenced scenario could not be resolved"))
            continue
        if found.get("scenario_digest") != scenario_ref["scenario_digest"]:
            defects.append(
                ContractDefect(path, "SCENARIO_DIGEST_MISMATCH", "resolved scenario digest does not match experiment")
            )
        if found.get("corpus_revision") != scenario_ref["corpus_revision"]:
            defects.append(
                ContractDefect(
                    path, "SCENARIO_CORPUS_REVISION_MISMATCH", "resolved scenario corpus_revision does not match experiment"
                )
            )
        resolved_scenarios[(scenario_ref["scenario_id"], scenario_ref["scenario_version"])] = found

    resolved_configurations: dict[str, dict] = {}
    for index, arm in enumerate(document["arms"]):
        path = f"$.arms[{index}]"
        found = resolver.resolve_configuration(arm["configuration_id"])
        if found is None:
            defects.append(
                ContractDefect(path, "CONFIGURATION_NOT_RESOLVED", "referenced configuration could not be resolved")
            )
            continue
        if found.get("configuration_digest") != arm["configuration_digest"]:
            defects.append(
                ContractDefect(
                    path, "CONFIGURATION_DIGEST_MISMATCH", "resolved configuration digest does not match experiment arm"
                )
            )
        resolved_configurations[arm["configuration_id"]] = found

    if not defects:
        for scenario in resolved_scenarios.values():
            for configuration in resolved_configurations.values():
                defects.extend(contracts.scenario_configuration_defects(scenario, configuration))

    if defects:
        raise VerificationContextError(sorted(set(defects)))

    external_refs: set[str] = set()
    for scenario in resolved_scenarios.values():
        external_refs |= _collect_scenario_artifact_refs(scenario)
    for configuration in resolved_configurations.values():
        external_refs |= _collect_configuration_artifact_refs(configuration)

    return VerificationResult(
        scope=GRAPH_VERIFIED_SCOPE,
        artifact_id=document["experiment_id"],
        artifact_digest=document["experiment_digest"],
        external_content_unverified_refs=tuple(sorted(external_refs)),
    )

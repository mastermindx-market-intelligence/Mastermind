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

from dataclasses import dataclass, field

from scripts.agent_eval import contracts
from scripts.agent_eval.errors import ContractDefect, VerificationContextError
from scripts.agent_eval.resolver import ArtifactResolver

GRAPH_VERIFIED_SCOPE = "EVALUATION_GRAPH_VERIFIED"


@dataclass(frozen=True)
class _ClosedInputResolver:
    """Minimal PRODUCTION read-only resolver scoped to a fixed, explicit set
    of documents the caller already holds (e.g. the scenario/configuration/
    experiment a CLI command already resolved from the real ArtifactStore
    before finalizing a run). This is NOT the test-only
    ``MemoryArtifactResolver`` (``tests/agent_eval_factories.py``, plan
    §5.6) -- it is a separate, narrower production implementation with no
    add/update/delete/search/fallback method, used only to verify that a
    caller's own already-resolved inputs are internally consistent. It
    performs no filesystem, network, or environment access."""

    scenarios: dict = field(default_factory=dict)
    configurations: dict = field(default_factory=dict)
    experiments: dict = field(default_factory=dict)
    runs: dict = field(default_factory=dict)
    scorer_passes: dict = field(default_factory=dict)
    evidence_refs: dict = field(default_factory=dict)

    def resolve_scenario(self, scenario_id: str, scenario_version: int):
        return self.scenarios.get((scenario_id, scenario_version))

    def resolve_configuration(self, configuration_id: str):
        return self.configurations.get(configuration_id)

    def resolve_experiment(self, experiment_id: str):
        return self.experiments.get(experiment_id)

    def resolve_run(self, run_id: str):
        return self.runs.get(run_id)

    def resolve_scorer_pass(self, scorer_pass_id: str):
        return self.scorer_passes.get(scorer_pass_id)

    def resolve_evidence_ref(self, evidence_ref_id: str):
        return self.evidence_refs.get(evidence_ref_id)


def closed_input_resolver(
    *,
    scenarios: tuple = (),
    configurations: tuple = (),
    experiments: tuple = (),
    runs: tuple = (),
    scorer_passes: tuple = (),
    evidence_refs: tuple = (),
) -> _ClosedInputResolver:
    """Build a :class:`_ClosedInputResolver` over an explicit, fixed set of
    already-resolved documents. Production-internal helper; see the class
    docstring for why this is distinct from the test-only resolver."""
    return _ClosedInputResolver(
        scenarios={(doc["scenario_id"], doc["scenario_version"]): doc for doc in scenarios},
        configurations={doc["configuration_id"]: doc for doc in configurations},
        experiments={doc["experiment_id"]: doc for doc in experiments},
        runs={doc["run_id"]: doc for doc in runs},
        scorer_passes={doc["scorer_pass_id"]: doc for doc in scorer_passes},
        evidence_refs={doc["evidence_ref_id"]: doc for doc in evidence_refs},
    )


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


def _collect_run_evidence_refs(document: dict) -> set[str]:
    refs = {document["evidence"]["output"]["artifact_ref"], document["evidence"]["tool_events"]["artifact_ref"]}
    trace = document["evidence"].get("trace")
    if trace:
        refs.add(trace["artifact_ref"])
    for item in document["evidence"]["artifacts"]:
        refs.add(item["artifact_ref"])
    for source in document["observations"]["observed_sources"]:
        refs.add(source["artifact_ref"])
    return refs


def verify_run_graph(document: dict, resolver: ArtifactResolver) -> VerificationResult:
    """Resolve the run's own claimed scenario/configuration/experiment,
    check shape, and recompute exact validity status/reasons. A forged or
    stale ``validity`` block fails verification -- it is never trusted."""
    contracts.validate_run_shape(document)
    # deferred import: scripts.agent_eval.validity imports this module for
    # verify_scenario_graph/verify_configuration_graph/verify_experiment_graph,
    # so importing it back at module load time would be circular.
    from scripts.agent_eval import validity as _validity  # noqa: PLC0415

    defects: list[ContractDefect] = []
    scenario_ref = document["scenario"]
    scenario = resolver.resolve_scenario(scenario_ref["scenario_id"], scenario_ref["scenario_version"])
    if scenario is None:
        defects.append(ContractDefect("$.scenario", "SCENARIO_NOT_RESOLVED", "referenced scenario could not be resolved"))

    configuration = resolver.resolve_configuration(document["configuration"]["configuration_id"])
    if configuration is None:
        defects.append(
            ContractDefect("$.configuration", "CONFIGURATION_NOT_RESOLVED", "referenced configuration could not be resolved")
        )

    experiment_id = document["comparison"]["experiment_id"]
    experiment = None
    if experiment_id is not None:
        experiment = resolver.resolve_experiment(experiment_id)
        if experiment is None:
            defects.append(
                ContractDefect(
                    "$.comparison.experiment_id", "EXPERIMENT_NOT_RESOLVED", "referenced experiment could not be resolved"
                )
            )

    if defects:
        raise VerificationContextError(sorted(set(defects)))

    contracts.validate_scenario_shape(scenario)
    contracts.validate_configuration_shape(configuration)
    if experiment is not None:
        contracts.validate_experiment_shape(experiment)

    recomputed = _validity.evaluate_validity(scenario, configuration, experiment, document)
    stored = document["validity"]
    if recomputed["status"] != stored["status"] or list(recomputed["reason_codes"]) != list(stored["reason_codes"]):
        raise VerificationContextError(
            [
                ContractDefect(
                    "$.validity",
                    "VALIDITY_NOT_RECOMPUTABLE",
                    "stored validity does not match recomputation from stored evaluation artifacts",
                )
            ]
        )

    external_refs = (
        _collect_scenario_artifact_refs(scenario)
        | _collect_configuration_artifact_refs(configuration)
        | _collect_run_evidence_refs(document)
    )

    return VerificationResult(
        scope=GRAPH_VERIFIED_SCOPE,
        artifact_id=document["run_id"],
        artifact_digest=document["run_digest"],
        external_content_unverified_refs=tuple(sorted(external_refs)),
    )

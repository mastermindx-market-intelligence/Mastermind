"""Bounded native implementation of the published Harness2 refinement method.

Method reference: arXiv:2610.14224v1, sections 2.2-2.3; serialization reference
is google-research/harness2@1cfe254e8d25b15f37048c3730134686abe60335.
This is an original native integration, NOT Google's provider launcher.

The existing host supplies an admitted port. This function creates no process,
provider client, scheduler, database, retry, worker or persistent library. The
port remains responsible for exact parent/Attempt grants, sandboxing, immutable
retention and resource admission BEFORE each call. Local finite limits are an
additional defensive ceiling, never a new budget grant. 'Parallel' describes
independent search branches; actual concurrent execution belongs to the port.

Every task starts at the supplied common base. Prior Agent OS experience is
frozen for the whole task and only guides the improver. Reflection returns a
candidate, never an automatic Agent OS write or a shared-harness deployment.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any, Protocol

from scripts.agent_eval import contracts, validity
from scripts.agent_eval.harness2_native import configuration_lock, harness_digest, sha256_bytes
from scripts.agent_eval.harness2_context import read_context_bundle


class Harness2CycleError(RuntimeError):
    """Stop this finite invocation; no retry or alternate-carrier implication."""

    def __init__(self, code: str, retained_run_ids: tuple[str, ...] = ()) -> None:
        self.code = code
        self.retained_run_ids = retained_run_ids
        super().__init__(code)


@dataclass(frozen=True)
class Limits:
    """A ceiling supplied by existing admission, not an authorization receipt."""

    max_rollouts: int
    max_improver_calls: int
    selector_seed: int


@dataclass(frozen=True)
class Trial:
    """Existing native EVAL objects and their retained output bytes."""

    scenario: dict
    configuration: dict
    experiment: dict | None
    run: dict
    output: bytes


@dataclass(frozen=True)
class Proposal:
    files: dict[str, bytes]
    notes: str
    evidence_run_ids: tuple[str, ...]


class Harness2Port(Protocol):
    """Adapter methods, not a second runtime or a source of grants.

    A production implementation must preserve its incumbent Runtime/OHF binding.
    Returned Trial objects must already be retained by the native EVAL owner.
    Exceptions are never retried here; reconcile them through that same owner.
    """

    def execute(self, task: dict, label: str, files: dict[str, bytes]) -> Trial: ...
    def improve(self, task: dict, label: str, kind: str, context: dict) -> Proposal: ...
    def select(self, task: dict, candidates: dict[str, bytes]) -> str: ...
    def reflect(self, task: dict, chosen: dict, context: dict) -> dict | None: ...


def _check(condition: bool, code: str) -> None:
    if not condition:
        raise Harness2CycleError(code)


def _validate_trial(trial: Trial, files: dict[str, bytes]) -> None:
    _check(type(trial) is Trial, "NATIVE_TRIAL_REQUIRED")
    contracts.validate_configuration_shape(trial.configuration)
    contracts.validate_run_shape(trial.run)
    _check(type(trial.output) is bytes and 0 < len(trial.output) <= 1_048_576,
           "TRIAL_OUTPUT_BOUND")
    _check(trial.run["evidence"]["output"]["digest"] == sha256_bytes(trial.output),
           "TRIAL_OUTPUT_CHANGED")
    _check(trial.configuration["procedure"]["instruction_bundle"]["digest"] == harness_digest(files),
           "TRIAL_HARNESS_MISMATCH")
    v = trial.run["validity"]
    draft = {key: copy.deepcopy(value) for key, value in trial.run.items()
             if key not in ("validity", "run_digest", "created_at")}
    draft["schema"] = contracts.RUN_DRAFT_SCHEMA
    recomputed = validity.finalize_run_receipt(
        trial.scenario, trial.configuration, trial.experiment, draft,
        validator_id=v["validator_id"], validator_version=v["validator_version"],
        validator_code_ref=v["validator_code_ref"], validated_at=v["validated_at"],
        created_at=trial.run["created_at"],
    )
    _check(recomputed == trial.run, "NATIVE_VALIDITY_DISAGREEMENT")
    _check(trial.run["effect"]["state"] == "NO_EFFECT", "NATIVE_EFFECT_REQUIRES_RECONCILIATION")
    _check(v["status"] == "VALID", "NATIVE_TRIAL_INVALID")


def _validate_proposal(value: Proposal, current: dict[str, bytes], allowed: frozenset[str],
                       evidence_ids: frozenset[str]) -> dict[str, bytes]:
    _check(type(value) is Proposal, "PROPOSAL_REQUIRED")
    harness_digest(value.files)
    _check(type(value.notes) is str and 0 < len(value.notes.strip()) <= 8192, "PROPOSAL_NOTES_REQUIRED")
    _check(type(value.evidence_run_ids) is tuple and 0 < len(value.evidence_run_ids) <= 128
           and all(type(v) is str and v in evidence_ids for v in value.evidence_run_ids),
           "PROPOSAL_EVIDENCE_UNBOUND")
    changed = {p for p in set(current) | set(value.files) if current.get(p) != value.files.get(p)}
    _check(changed <= allowed, "PROPOSAL_OUTSIDE_ADMITTED_SURFACE")
    _check(not (set(current) - set(value.files)), "PROPOSAL_DELETION_REFUSED")
    return copy.deepcopy(value.files)


def run_refinement(*, task: dict, common_base: dict[str, bytes],
                   expected_scenario: dict, baseline_configuration: dict,
                   prior_experience: tuple[dict, ...], allowed_edit_paths: frozenset[str],
                   k: int, mode: str, limits: Limits, port: Harness2Port,
                   agentos_context_inputs: dict | None = None) -> dict:
    """One finite Propose-Probe-Compose/Select/Reflect invocation.

    No ground-truth score is accepted or provided to the improver/selector.
    Every native rollout is validated and compared under a factor lock excluding
    only the changing instruction bundle. A failed/ambiguous owner call stops
    immediately; its owner retains reconciliation and all prior run records.
    This is not an efficacy evaluator: downstream independent scorers decide that.
    """
    _check(type(task) is dict and set(task) == {"task_id", "domain", "request"}, "TASK_SHAPE")
    for value in task.values():
        _check(type(value) is str and 0 < len(value.strip()) <= 16384, "TASK_TEXT_BOUND")
    _check(type(k) is int and 1 <= k <= 16 and mode in ("agg", "seq"), "RECURSION_MODE_OR_BUDGET")
    _check(type(limits) is Limits and type(limits.max_rollouts) is int
           and type(limits.max_improver_calls) is int and type(limits.selector_seed) is int,
           "LIMITS_REQUIRED")
    needed_improvers = 3 * k + 1 + (1 if k > 1 else 0)
    _check(4 * k <= limits.max_rollouts and needed_improvers <= limits.max_improver_calls,
           "ADMITTED_CEILING_INSUFFICIENT")
    _check(type(allowed_edit_paths) is frozenset and 0 < len(allowed_edit_paths) <= 128
           and all(type(p) is str for p in allowed_edit_paths), "EXACT_EDIT_SURFACE_REQUIRED")
    # Validate even not-yet-existing allowed paths before sending any request.
    harness_digest({p: b"" for p in allowed_edit_paths})
    base = copy.deepcopy(common_base)
    base_digest = harness_digest(base)
    contracts.validate_scenario_shape(expected_scenario)
    contracts.validate_configuration_shape(baseline_configuration)
    _check(baseline_configuration["procedure"]["instruction_bundle"]["digest"] == base_digest,
           "DECLARED_BASE_HARNESS_MISMATCH")
    expected_ref = {key: expected_scenario[key] for key in
                    ("scenario_id", "scenario_version", "scenario_digest", "corpus_revision")}
    expected_ref["temporal_cutoff"] = expected_scenario["temporal"]["cutoff_at"]
    expected_lock = configuration_lock(expected_ref, baseline_configuration)
    _check(type(prior_experience) is tuple and len(prior_experience) <= 32, "EXPERIENCE_BOUND")
    source_context = None
    if agentos_context_inputs is not None:
        _check(type(agentos_context_inputs) is dict and not prior_experience,
               "CONTEXT_LIBRARY_MUST_NOT_BE_MIXED")
        _check(agentos_context_inputs.get("task_domain") == task["domain"], "CONTEXT_TASK_DOMAIN_MISMATCH")
        source_context = read_context_bundle(**agentos_context_inputs)
        _check(baseline_configuration["context"]["context_packet"]["digest"] == source_context.bundle_digest,
               "NATIVE_CONTEXT_PACKET_MISMATCH")
        prior_experience = source_context.experience
    library = copy.deepcopy(prior_experience)
    fields = {"discovery_ref", "source_ref", "domain", "claim", "falsifier", "so_what", "harness_artifact"}
    provenance_fields = {"confidence", "source_run_ids", "method_source_ref"}
    for entry in library:
        _check(type(entry) is dict and (set(entry) == fields or set(entry) == fields | provenance_fields),
               "EXPERIENCE_SHAPE")
        _check(entry["domain"] == task["domain"], "EXPERIENCE_DOMAIN_MISMATCH")
        _check(all(type(v) is str and 0 < len(v.strip()) <= 8192
                   for key, v in entry.items() if key not in ("harness_artifact", "source_run_ids")), "EXPERIENCE_TEXT_BOUND")
        _check(entry["discovery_ref"].startswith("DSC:"), "EXPERIENCE_DISCOVERY_REQUIRED")
        if provenance_fields <= set(entry):
            _check(entry["confidence"] in ("verified", "probable", "suspected"), "EXPERIENCE_CONFIDENCE_INVALID")
            refs = entry["source_run_ids"]
            _check(type(refs) is list and 2 <= len(refs) <= 128, "EXPERIENCE_RUN_REFERENCE_BOUND")
            for ref in refs:
                contracts.v_run_id(ref, "$.experience.source_run_ids")
            _check(len(set(refs)) == len(refs), "EXPERIENCE_RUN_REFERENCE_DUPLICATE")
        # Full adopted trees stay in their existing artifact owner. The port may
        # retrieve this exact artifact on demand; no shadow library is persisted.
        contracts.v_artifact_pair(entry["harness_artifact"], "$.experience.harness_artifact")
    task = copy.deepcopy(task)
    trials: dict[str, Trial] = {}
    trees: dict[str, dict[str, bytes]] = {}
    notes: dict[str, str] = {}
    native_ids: set[str] = set()
    observed_ids: list[str] = []
    improver_calls = 0

    def context(current: dict[str, bytes], labels: list[str]) -> dict:
        # Fresh detached values each time; a callback cannot alter the frozen library.
        return copy.deepcopy({
            "current_harness": current, "common_base": base,
            "prior_experience": library,
            # Preserve higher law, the workstream and missingness rather than
            # replacing the native context packet with a persuasive lesson list.
            "organizational_context": source_context.bundle if source_context else None,
            "experience_exclusions": source_context.experience_exclusions if source_context else (),
            "executions": [{"label": label, "run_id": trials[label].run["run_id"],
                            "output": trials[label].output, "harness": trees[label],
                            "notes": notes.get(label, "")} for label in labels],
        })

    def execute(label: str, files: dict[str, bytes]) -> None:
        _check(label not in trials and len(trials) < limits.max_rollouts, "ROLLOUT_CEILING_OR_DUPLICATE")
        returned = port.execute(copy.deepcopy(task), label, copy.deepcopy(files))
        if type(returned) is Trial and type(returned.run) is dict:
            run_id = returned.run.get("run_id")
            contracts.v_run_id(run_id, "$.run_id")
            if run_id not in observed_ids:
                observed_ids.append(run_id)
        _validate_trial(returned, files)
        run_id = returned.run["run_id"]
        _check(run_id not in native_ids, "NATIVE_RUN_REUSED")
        lock = configuration_lock(returned.run["scenario"], returned.configuration)
        _check(expected_lock == lock, "MATCHED_CONFIGURATION_CHANGED")
        native_ids.add(run_id)
        trials[label] = copy.deepcopy(returned)
        trees[label] = copy.deepcopy(files)

    def improve(label: str, kind: str, current: dict[str, bytes], labels: list[str]) -> dict[str, bytes]:
        nonlocal improver_calls
        _check(improver_calls < limits.max_improver_calls, "IMPROVER_CEILING")
        improver_calls += 1
        response = port.improve(copy.deepcopy(task), label, kind, context(current, labels))
        result = _validate_proposal(response, current, allowed_edit_paths,
                                   frozenset(trials[x].run["run_id"] for x in labels))
        notes[label] = response.notes
        return result

    try:
        baselines = [f"base{i}" for i in range(1, k + 1)]
        for label in baselines:
            execute(label, base)
        finals: list[str] = []
        if mode == "agg":
            proposals = []
            for index in range(1, k + 1):
                for stem, kind in (("inv", "invariant"), ("dom", "domain")):
                    label = f"{stem}{index}"
                    proposals.append((label, improve(label, kind, base, baselines)))
            for label, files in proposals:
                execute(label, files)
            pool = baselines + [label for label, _files in proposals]
            for index in range(1, k + 1):
                label = f"agg{index}"
                composed = improve(label, "compose", base, pool)
                execute(label, composed)
                finals.append(label)
        else:
            current = base
            history = list(baselines)
            for index in range(1, k + 1):
                proposals = []
                for stem, kind in (("inv", "invariant"), ("dom", "domain")):
                    label = f"{stem}{index}"
                    proposals.append((label, improve(label, kind, current, history)))
                for label, files in proposals:
                    execute(label, files)
                history += [label for label, _files in proposals]
                label = f"c{index}"
                current = improve(label, "compose", current, history)
                execute(label, current)
                history.append(label)
                finals.append(label)
        if k == 1:
            chosen = finals[0]
        else:
            shuffled = list(finals)
            random.Random(limits.selector_seed).shuffle(shuffled)
            anonymized = {chr(65 + i): label for i, label in enumerate(shuffled)}
            improver_calls += 1
            selection = port.select(copy.deepcopy(task),
                                    {key: trials[label].output for key, label in anonymized.items()})
            _check(type(selection) is str and selection in anonymized, "SELECTION_NOT_IN_FINALS")
            chosen = anonymized[selection]
        improver_calls += 1
        # No scenario/grader document is exposed to model-facing reflection.
        chosen_view = {"run_id": trials[chosen].run["run_id"], "output": trials[chosen].output,
                       "harness_digest": harness_digest(trees[chosen])}
        reflection = port.reflect(copy.deepcopy(task), chosen_view,
                                  context(trees[chosen], list(trials)))
        if reflection is not None:
            _check(type(reflection) is dict and set(reflection) == {"claim", "falsifier", "so_what", "evidence_run_ids"},
                   "REFLECTION_SHAPE")
            for key in ("claim", "falsifier", "so_what"):
                _check(type(reflection[key]) is str and 0 < len(reflection[key].strip()) <= 8192,
                       "REFLECTION_TEXT_BOUND")
            refs = reflection["evidence_run_ids"]
            _check(type(refs) is list and 2 <= len(refs) <= 128
                   and all(type(v) is str and v in native_ids for v in refs) and len(set(refs)) == len(refs),
                   "REFLECTION_EVIDENCE_UNBOUND")
            _check(trials[chosen].run["run_id"] in refs
                   and any(trials[label].run["run_id"] in refs for label in baselines),
                   "REFLECTION_BASELINE_AND_SELECTED_REQUIRED")
        _check(len(trials) == 4 * k and improver_calls == needed_improvers, "RECURSION_ACCOUNTING_MISMATCH")
        return {
            "task_id": task["task_id"], "domain": task["domain"], "mode": mode, "k": k,
            "selected_label": chosen, "selected_native_run_id": trials[chosen].run["run_id"],
            "selected_harness": copy.deepcopy(trees[chosen]), "selected_output": trials[chosen].output,
            "selected_harness_artifact": copy.deepcopy(trials[chosen].configuration["procedure"]["instruction_bundle"]),
            "retained_native_runs": tuple(trials[label].run["run_id"] for label in trials),
            "baseline_native_run_ids": tuple(trials[label].run["run_id"] for label in baselines),
            "baseline_harness_digest": base_digest,
            "rollout_count": len(trials), "improver_call_count": improver_calls,
            "factor_lock_digest": expected_lock, "step_notes": copy.deepcopy(notes),
            "context_bundle_digest": source_context.bundle_digest if source_context else None,
            "experience_exclusions": copy.deepcopy(source_context.experience_exclusions) if source_context else (),
            "experience_candidate": copy.deepcopy(reflection),
            "automatic_memory_write": False, "promotion": "NONE",
        }
    except Exception as exc:
        # Includes an owner-returned invalid/effect-unknown run, not only valid probes.
        retained = tuple(observed_ids)
        if isinstance(exc, Harness2CycleError):
            raise Harness2CycleError(exc.code, retained) from exc
        raise Harness2CycleError("OWNER_CALL_OR_EVIDENCE_FAILED", retained) from exc

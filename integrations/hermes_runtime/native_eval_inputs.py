"""EVAL inputs bound to one original native admission, never a second runner.

The held entry selects the existing ArtifactStore. Private control supplies
intent IDs and bounded input bytes; this owner resolves immutable EVAL objects
and checks their byte bindings. The resulting private marker is retained in
the original admission fingerprint. It is not an execution or effect grant.

This input contribution is deliberately insufficient for a complete EVAL run.
Policy, complete source/effect coverage and cleanup remain their owners' facts.
"""
from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import stat

from scripts.agent_eval import contracts, validity
from scripts.agent_eval.canonical import canonical_json_bytes, digest_value
from scripts.agent_eval.harness2_native import harness_digest, validate_native_harness_text
from scripts.agent_eval.privacy import assert_public_safe_evidence
from scripts.agent_eval.store import ArtifactStore
from scripts.agent_eval.verification import verify_configuration_graph, verify_experiment_graph, verify_scenario_graph

from .errors import RuntimeRefusal

RECIPE_SCHEMA = "mastermind.hermes_native_eval_inputs/v1"
LEGACY_MARKER_SCHEMA = "mastermind.hermes_native_eval_admission/v1"
MARKER_SCHEMA = "mastermind.hermes_native_eval_admission/v2"
MARKER_KEY = "mastermind_eval_inputs_v1"
RESULT_KEY = "mastermind_eval_inputs"
LEGACY_RESULT_SCHEMA = "mastermind.hermes_native_eval_input_observation/v1"
PREVIOUS_RESULT_SCHEMA = "mastermind.hermes_native_eval_input_observation/v2"
RESULT_SCHEMA = "mastermind.hermes_native_eval_input_observation/v3"
STRONG_RESULT_SCHEMAS = frozenset({PREVIOUS_RESULT_SCHEMA, RESULT_SCHEMA})
RENDERER = "mastermind.harness_instruction_text/v1"
MAX_MARKER_BYTES = 192 * 1024
MAX_CANDIDATE_BYTES = 16 * 1024
MAX_CONTEXT_BYTES = 16 * 1024
MAX_INPUT_BYTES = 16 * 1024
MAX_EVENTS = 8
LEGACY_OBSERVATION_ERRORS = frozenset({"delivery_overflow", "assembly_overflow", "metadata_overflow",
    "delivery_unavailable", "assembly_unavailable", "tool_schema_unavailable", "retention_overflow"})
OBSERVATION_ERRORS = LEGACY_OBSERVATION_ERRORS | {"history_overflow", "history_unavailable"}
HISTORY_BOUNDARY = "build_turn_context.history_adoption"
MAX_HISTORY_ROWS = 1 << 16
_PRIVATE = object()
_REQUEST_FIELDS = {"run_id", "scenario_id", "scenario_version", "scenario_digest",
    "configuration_id", "configuration_digest", "experiment_id", "experiment_digest",
    "arm_id", "pair_key", "replicate_index", "candidate_files", "context_text"}
_LEGACY_MARKER_FIELDS = {"schema", "run_id", "source", "input", "scenario", "configuration",
    "experiment", "comparison", "candidate_files", "context_text", "renderer",
    "rendered_sha256", "binding_sha256"}
_MARKER_FIELDS = _LEGACY_MARKER_FIELDS | {"producer", "publication"}
RUNNER_ID = "mastermind.hermes_native_admission.v1"
EXECUTION_SURFACE = "hermes-native"


def producer_descriptor(release, base_sha, patch_sha256):
    """Describe the already-qualified source; this grants no execution."""
    if (type(release) is not str or re.fullmatch(r"[0-9a-f]{40}", release) is None
            or type(base_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", base_sha) is None
            or type(patch_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", patch_sha256) is None):
        _refuse("NATIVE_EVAL_PRODUCER_UNQUALIFIED")
    return {"runner_id": RUNNER_ID,
            "runner_code_ref": "git:mastermindx-market-intelligence/Mastermind@" + release,
            "execution_surface": EXECUTION_SURFACE,
            "execution_surface_version": "hermes@" + base_sha + "+native_eval_inputs@" + patch_sha256}


def _validate_publication_binding(marker):
    producer, publication = marker["producer"], marker["publication"]
    if (type(producer) is not dict or set(producer) != {
            "runner_id", "runner_code_ref", "execution_surface", "execution_surface_version"}
            or producer["runner_id"] != RUNNER_ID or producer["execution_surface"] != EXECUTION_SURFACE
            or producer["runner_code_ref"] != "git:mastermindx-market-intelligence/Mastermind@" + marker["source"]["release"]
            or type(producer["execution_surface_version"]) is not str
            or re.fullmatch(r"hermes@[0-9a-f]{40}\+native_eval_inputs@[0-9a-f]{64}",
                            producer["execution_surface_version"]) is None
            or type(publication) is not dict or set(publication) != {"artifact_root", "root_identity"}):
        _refuse("NATIVE_EVAL_PRODUCER_UNQUALIFIED")
    root = publication["artifact_root"]
    _bytes(root, 1024)
    if (not Path(root).is_absolute() or str(Path(root)) != root or ".." in Path(root).parts
            or any(ord(char) < 32 for char in root)):
        _refuse("NATIVE_EVAL_STORE_UNQUALIFIED")
    identity = publication["root_identity"]
    if (type(identity) is not dict or set(identity) != {"device", "inode", "uid", "mode"}
            or any(type(value) is not int or value < 0 for value in identity.values())
            or identity["inode"] == 0 or identity["mode"] != 0o700):
        _refuse("NATIVE_EVAL_STORE_UNQUALIFIED")
    expected = marker["configuration"]["execution"]
    if any(producer[key] != expected[key] for key in ("execution_surface", "execution_surface_version")):
        _refuse("NATIVE_EVAL_SURFACE_MISMATCH")


def _refuse(code="NATIVE_EVAL_INPUTS_UNQUALIFIED"):
    raise RuntimeRefusal(code)


def _bytes(text, maximum, *, empty=False):
    if type(text) is not str or (not text and not empty):
        _refuse()
    try:
        raw = text.encode("utf-8", "strict")
    except UnicodeError:
        _refuse()
    if len(raw) > maximum:
        _refuse("NATIVE_EVAL_INPUT_BOUND")
    return raw


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def submission_id_for_run(run_id):
    """One run UUID maps to one request on the fixed enrolled native session."""
    try:
        contracts.parse_run_id(run_id)
    except Exception:
        _refuse()
    return "mastermind-eval:" + run_id.removeprefix("run:")


def _detach(value, *, maximum=MAX_MARKER_BYTES):
    try:
        raw = canonical_json_bytes(value)
        if len(raw) > maximum:
            _refuse("NATIVE_EVAL_INPUT_BOUND")
        assert_public_safe_evidence(value)
        return json.loads(raw)
    except RuntimeRefusal:
        raise
    except Exception:
        _refuse()


def _files(value):
    if type(value) is not dict or not 1 <= len(value) <= 32:
        _refuse()
    result = {name: _bytes(text, MAX_CANDIDATE_BYTES, empty=True) for name, text in value.items()}
    try:
        validate_native_harness_text(result)
    except Exception:
        _refuse()
    if sum(len(raw) for raw in result.values()) > MAX_CANDIDATE_BYTES:
        _refuse("NATIVE_EVAL_INPUT_BOUND")
    return result


def render_inputs(files, context_text):
    """One deterministic instruction-text representation, not installed skills."""
    _files(files)
    _bytes(context_text, MAX_CONTEXT_BYTES, empty=True)
    return ("\n\nMastermind evaluation instruction files (" + RENDERER + "):\n"
            + canonical_json_bytes(files).decode("utf-8")
            + "\n\nMastermind evaluation context packet:\n" + context_text
            + "\nEnd Mastermind evaluation inputs.")


def _comparison(scenario, configuration, experiment, comparison):
    """Use the existing finalizer's comparison rules and exact artifact joins."""
    try:
        contracts._v_comparison(comparison, "$.comparison")
        validity._require_matching_identity(scenario, configuration, experiment, {
            "scenario": scenario, "configuration": configuration, "comparison": comparison})
        if experiment is None:
            if any(comparison[key] is not None for key in ("arm_id", "pair_key", "replicate_index")):
                _refuse()
        else:
            if comparison["arm_id"] is None or comparison["replicate_index"] is None:
                _refuse()
            selected = {"scenario_id": scenario["scenario_id"],
                "scenario_version": scenario["scenario_version"],
                "scenario_digest": scenario["scenario_digest"], "corpus_revision": scenario["corpus_revision"]}
            if selected not in experiment["scenario_refs"]:
                _refuse()
            arms = [arm for arm in experiment["arms"] if arm["arm_id"] == comparison["arm_id"]]
            if (len(arms) != 1 or arms[0]["configuration_id"] != configuration["configuration_id"]
                    or arms[0]["configuration_digest"] != configuration["configuration_digest"]):
                _refuse()
        if validity.comparison_binding_reason_codes(scenario, configuration, experiment, comparison):
            _refuse()
    except RuntimeRefusal:
        raise
    except Exception:
        _refuse()


def validate_marker(marker, *, text=None):
    """Closed historical byte validation. This alone never authenticates a marker."""
    marker = _detach(marker)
    if type(marker) is not dict:
        _refuse()
    fields = (_MARKER_FIELDS if marker.get("schema") == MARKER_SCHEMA else
              _LEGACY_MARKER_FIELDS if marker.get("schema") == LEGACY_MARKER_SCHEMA else None)
    if fields is None or set(marker) != fields or marker["renderer"] != RENDERER:
        _refuse()
    try:
        contracts.parse_run_id(marker["run_id"])
        contracts.validate_scenario_shape(marker["scenario"])
        contracts.validate_configuration_shape(marker["configuration"])
        if marker["experiment"] is not None:
            contracts.validate_experiment_shape(marker["experiment"])
    except Exception:
        _refuse()
    # Core EVAL can retain newer control policies, but this selected native
    # route still injects a scalar seed and manual effort. Do not accidentally
    # admit tagged inputs before that original execution boundary is qualified.
    if marker["configuration"]["schema"] != contracts.CONFIGURATION_SCHEMA:
        _refuse("NATIVE_EVAL_CONFIGURATION_VERSION_UNQUALIFIED")
    source, identity = marker["source"], marker["input"]
    if (type(source) is not dict or set(source) != {"release", "profile_id", "profile_digest"}
            or type(identity) is not dict or set(identity) != {"principal_id", "session_id", "submission_id", "text_sha256"}):
        _refuse()
    for key in ("release", "profile_id", "profile_digest"):
        _bytes(source[key], 1024)
    for key in identity:
        _bytes(identity[key], 1024)
    if (len(source["release"]) != 40 or any(c not in "0123456789abcdef" for c in source["release"])
            or len(identity["text_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in identity["text_sha256"])):
        _refuse()
    scenario, config = marker["scenario"], marker["configuration"]
    if marker["schema"] == MARKER_SCHEMA:
        _validate_publication_binding(marker)
    _comparison(scenario, config, marker["experiment"], marker["comparison"])
    if identity["submission_id"] != submission_id_for_run(marker["run_id"]):
        _refuse("NATIVE_EVAL_REQUEST_ID_MISMATCH")
    files = _files(marker["candidate_files"])
    if (harness_digest(files) != config["procedure"]["instruction_bundle"]["digest"]
            or "sha256:" + _sha(_bytes(marker["context_text"], MAX_CONTEXT_BYTES, empty=True))
               != config["context"]["context_packet"]["digest"]
            or config["capabilities"]["profile_id"] != source["profile_id"]
            or config["capabilities"]["profile_digest"] != source["profile_digest"]
            or "sha256:" + identity["text_sha256"] != scenario["input_fixture"]["digest"]
            or contracts.scenario_configuration_defects(scenario, config)):
        _refuse()
    policy = scenario["execution_policy"]
    if (any(policy[key] for key in ("fresh_process_required", "fresh_workspace_required", "fresh_session_required"))
            or policy["resume_allowed"] is not True):
        _refuse("NATIVE_EVAL_WARM_SESSION_REQUIRED")
    # A pre-existing frozen fresh scenario is refused, never rewritten to fit.
    if (scenario["privacy"]["classification"] != "PUBLIC_SAFE"
            or scenario["privacy"]["retention_class"] != "DURABLE_SANITIZED"):
        _refuse("NATIVE_EVAL_RETENTION_UNQUALIFIED")
    source_policy = scenario["source_policy"]
    forbidden = set(source_policy["denylist_refs"]) | set(source_policy["solution_refs_hidden"])
    supplied = (scenario["input_fixture"], config["context"]["context_packet"],
                config["procedure"]["instruction_bundle"])
    if any(pair["artifact_ref"] in forbidden for pair in supplied):
        _refuse("NATIVE_EVAL_SOURCE_FORBIDDEN")
    allowed = {pair["artifact_ref"]: pair["digest"] for pair in source_policy["allowlist_artifacts"]}
    # Input/context are model-visible data. The instruction bundle is the
    # explicitly variable procedure, not an additional retrieved data source.
    if any(allowed.get(pair["artifact_ref"]) != pair["digest"] for pair in supplied[:2]):
        _refuse("NATIVE_EVAL_DATA_SOURCE_UNQUALIFIED")
    visible = set(scenario["privacy"]["model_visible_artifact_refs"])
    if any(pair["artifact_ref"] not in visible for pair in supplied[:2]):
        _refuse("NATIVE_EVAL_DATA_SOURCE_UNQUALIFIED")
    rendered = render_inputs(marker["candidate_files"], marker["context_text"])
    if marker["rendered_sha256"] != _sha(rendered.encode("utf-8")):
        _refuse()
    unsigned = {key: value for key, value in marker.items() if key != "binding_sha256"}
    if marker["binding_sha256"] != _sha(canonical_json_bytes(unsigned)):
        _refuse()
    if text is not None:
        if _sha(_bytes(text, MAX_INPUT_BYTES)) != identity["text_sha256"]:
            _refuse("NATIVE_EVAL_INPUT_CHANGED")
        # The marker contains only the input hash. Its privacy check cannot
        # stand in for checking the bytes retained by the native admission.
        try:
            assert_public_safe_evidence({"input_text": text})
        except Exception:
            _refuse("NATIVE_EVAL_RETENTION_UNQUALIFIED")
    return marker


def retained_admission_payload(payload):
    """Keep historical safe inputs, or only the irreversible request fence.

    Called by the original terminal retirement owner. A marker key keeps the
    admission/request identity even when its contents cannot be interpreted.
    Full content requires the closed, versioned historical byte/privacy checks;
    this never consults today's launch, enrollment, configuration, or store.
    """
    if type(payload) is not dict or MARKER_KEY not in payload:
        return {}
    fence = {MARKER_KEY: None}
    if set(payload) != {"text", "finite", MARKER_KEY} or payload["finite"] is not True:
        return fence
    try:
        value = _detach(payload, maximum=MAX_MARKER_BYTES + MAX_INPUT_BYTES + 1024)
        _bytes(value["text"], MAX_INPUT_BYTES)
        validate_marker(value[MARKER_KEY], text=value["text"])
    except RuntimeRefusal:
        return fence
    return value


def authority_source_sha(launch, vendor):
    """Select the changed authority source only through its exact held receipt."""
    from ops.executive_os.native_gateway_sources import (
        DERIVATION_BASE, EVAL_INPUTS_DERIVATION_KIND, EVAL_INPUTS_DERIVATION_PATCH,
        EVAL_INPUTS_DERIVATION_POSTIMAGES, PRIVACY_LICENSE_SHA256)
    launch.check()
    selected = launch.recipe.get("vendor_derivation")
    expected = {"kind": EVAL_INPUTS_DERIVATION_KIND, "base_sha": DERIVATION_BASE,
        "patch_sha256": EVAL_INPUTS_DERIVATION_PATCH, "postimages": dict(EVAL_INPUTS_DERIVATION_POSTIMAGES),
        "license_sha256": PRIVACY_LICENSE_SHA256, "vendor_root": str(vendor)}
    if ("evaluation_inputs" not in launch.recipe or type(selected) is not dict
            or set(selected) != {"kind", "base_sha", "patch_sha256", "source_root"}
            or any(type(selected[key]) is not str or selected[key] != expected[key]
                   for key in ("kind", "base_sha", "patch_sha256"))
            or type(selected["source_root"]) is not str or not Path(selected["source_root"]).is_absolute()
            or launch.recipe.get("vendor_root") != str(vendor) or launch.derivation != expected):
        _refuse("NATIVE_EVAL_DERIVATION_UNQUALIFIED")
    return EVAL_INPUTS_DERIVATION_POSTIMAGES["gateway/session_authority.py"]


@dataclass(frozen=True, init=False)
class _PrivateSelection:
    owner: object
    encoded: bytes

    def __init__(self, owner, marker, key):
        if key is not _PRIVATE:
            _refuse()
        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "encoded", canonical_json_bytes(validate_marker(marker)))


class NativeEvalInputOwner:
    """An optional contribution held by the existing request-observation binding."""

    def __init__(self, launch, profile, binding):
        from ops.executive_os.release_manifest import _NativeGatewayLaunch
        from .profile import RuntimeProfile, dump_profile, profile_sha256
        if type(launch) is not _NativeGatewayLaunch or type(profile) is not RuntimeProfile:
            _refuse()
        recipe = launch.recipe.get("evaluation_inputs")
        if type(recipe) is not dict or set(recipe) != {"schema", "artifact_root"} or recipe["schema"] != RECIPE_SCHEMA:
            _refuse()
        self.launch, self.binding = launch, binding
        self.require_transport()
        authority_source_sha(launch, Path(launch.recipe["vendor_root"]))
        self.recipe = _detach(recipe)
        self.profile_id = str(binding.role_home)
        self.profile_digest = "sha256:" + profile_sha256(dump_profile(profile))
        self.release = launch.owner.root.name
        from integrations.hermes_models.contract import native_provider
        self.provider_spec = native_provider(profile.role, profile.native_provider_id)
        if self.provider_spec.provider_id != "zai.glm-5.3":
            _refuse("NATIVE_EVAL_EFFORT_ROUTE_UNQUALIFIED")
        root = Path(recipe["artifact_root"])
        info = root.lstat()
        if (not root.is_absolute() or root.is_symlink() or root.resolve(strict=True) != root
                or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            _refuse("NATIVE_EVAL_STORE_UNQUALIFIED")
        # Existing trusted-root/create-only store; never initialize another root.
        self.store = ArtifactStore(root, create_root=False)
        self.root_identity = (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
        derivation = launch.recipe["vendor_derivation"]
        self.producer = producer_descriptor(self.release, derivation["base_sha"], derivation["patch_sha256"])
        self.publication = {"artifact_root": str(root), "root_identity": dict(zip(
            ("device", "inode", "uid", "mode"), self.root_identity))}
        launch.check()
        # Extend the existing qualified memory/turn owner before native startup.
        # The hook observes adoption only; it creates no history reader or store.
        from .native_agentos_memory import NativeAgentOsMemoryFactory
        factory = binding.memory_factory
        if type(factory) is not NativeAgentOsMemoryFactory or factory.observation is not binding:
            _refuse("NATIVE_EVAL_HISTORY_OWNER_UNAVAILABLE")
        factory.bind_evaluation_history(self)

    def check(self):
        self.launch.check()
        self.require_transport()
        if getattr(self.binding.memory_factory, "evaluation_history_owner", None) is not self:
            _refuse("NATIVE_EVAL_HISTORY_OWNER_CHANGED")
        info = self.store.root.lstat()
        if (self.binding.evaluation_owner is not self
                or self.launch.recipe.get("evaluation_inputs") != self.recipe
                or self.launch.owner.root.name != self.release
                or self.producer != producer_descriptor(self.release,
                    self.launch.recipe["vendor_derivation"]["base_sha"],
                    self.launch.recipe["vendor_derivation"]["patch_sha256"])
                or self.publication != {"artifact_root": str(self.store.root), "root_identity": dict(zip(
                    ("device", "inode", "uid", "mode"), self.root_identity))}
                or self.store.root.resolve(strict=True) != self.store.root
                or not stat.S_ISDIR(info.st_mode)
                or (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) != self.root_identity):
            _refuse("NATIVE_EVAL_OWNER_CHANGED")

    def require_transport(self):
        from .native_transport_observation import Installation
        selected = self.binding.transport_installation
        if (type(selected) is not Installation or selected.binding is not self.binding
                or not selected.registered_current()):
            _refuse("NATIVE_EVAL_DISPATCH_FENCE_UNAVAILABLE")

    def require_enrollment(self, principal, session_id):
        from .native_agentos_memory import NativeAgentOsMemoryFactory
        factory = self.binding.memory_factory
        authority = self.binding.authority
        if (type(factory) is not NativeAgentOsMemoryFactory or not factory.registered_current()
                or authority is None or factory.observation is not self.binding
                or factory.session_id != session_id or factory.instance_id != authority.instance_id
                or factory.authority_epoch != authority.epoch
                or factory.publication.session.principal_id != principal):
            _refuse("NATIVE_EVAL_ENROLLED_SESSION_REQUIRED")
        from integrations.hermes_omh.effort_config import PLUGIN
        adaptive = factory.slot.manager._plugins.get(PLUGIN)
        if adaptive is not None and getattr(adaptive, "enabled", False) is not False:
            # Do not disable or override another effort owner. This first
            # manual slice is selected by the existing closed plugin config.
            _refuse("NATIVE_EVAL_MANUAL_EFFORT_UNAVAILABLE")

    def select(self, specification, *, principal, session_id, submission_id, text):
        self.check()
        self.require_enrollment(principal, session_id)
        specification = _detach(specification)
        if type(specification) is not dict or set(specification) != _REQUEST_FIELDS:
            _refuse()
        try:
            contracts.parse_run_id(specification["run_id"])
            if submission_id != submission_id_for_run(specification["run_id"]):
                _refuse("NATIVE_EVAL_REQUEST_ID_MISMATCH")
            if self.store.resolve_run(specification["run_id"]) is not None:
                _refuse("NATIVE_EVAL_RUN_ALREADY_RETAINED")
            scenario = self.store.resolve_scenario(specification["scenario_id"], specification["scenario_version"])
            configuration = self.store.resolve_configuration(specification["configuration_id"])
            experiment = (self.store.resolve_experiment(specification["experiment_id"])
                          if specification["experiment_id"] is not None else None)
            verify_scenario_graph(scenario, self.store)
            verify_configuration_graph(configuration, self.store)
            if experiment is not None:
                verify_experiment_graph(experiment, self.store)
        except RuntimeRefusal:
            raise
        except Exception:
            _refuse("NATIVE_EVAL_INPUT_ARTIFACT_UNAVAILABLE")
        if (scenario["scenario_id"] != specification["scenario_id"]
                or scenario["scenario_version"] != specification["scenario_version"]
                or scenario["scenario_digest"] != specification["scenario_digest"]
                or configuration["configuration_id"] != specification["configuration_id"]
                or configuration["configuration_digest"] != specification["configuration_digest"]
                or (None if experiment is None else experiment["experiment_id"]) != specification["experiment_id"]
                or (None if experiment is None else experiment["experiment_digest"]) != specification["experiment_digest"]):
            _refuse("NATIVE_EVAL_INPUT_CHANGED")
        comparison = {key: specification[key] for key in ("experiment_id", "arm_id", "pair_key", "replicate_index")}
        _comparison(scenario, configuration, experiment, comparison)
        marker = {"schema": MARKER_SCHEMA, "run_id": specification["run_id"],
            "source": {"release": self.release, "profile_id": self.profile_id, "profile_digest": self.profile_digest},
            "producer": copy.deepcopy(self.producer), "publication": copy.deepcopy(self.publication),
            "input": {"principal_id": principal, "session_id": session_id,
                "submission_id": submission_id, "text_sha256": _sha(_bytes(text, MAX_INPUT_BYTES))},
            "scenario": scenario, "configuration": configuration, "experiment": experiment,
            "comparison": comparison, "candidate_files": specification["candidate_files"],
            "context_text": specification["context_text"], "renderer": RENDERER,
            "rendered_sha256": _sha(render_inputs(specification["candidate_files"], specification["context_text"]).encode("utf-8"))}
        marker["binding_sha256"] = _sha(canonical_json_bytes(marker))
        marker = validate_marker(marker, text=text)
        self.check()
        return _PrivateSelection(self, marker, _PRIVATE)

    def require_unretained_run(self, run_id):
        try:
            if self.store.resolve_run(run_id) is not None:
                _refuse("NATIVE_EVAL_RUN_ALREADY_RETAINED")
        except RuntimeRefusal:
            raise
        except Exception:
            _refuse("NATIVE_EVAL_INPUT_ARTIFACT_UNAVAILABLE")

    def restore(self, scope, row):
        self.check()
        payload = row.get("payload")
        if type(payload) is not dict or set(payload) != {"text", "finite", MARKER_KEY} or payload["finite"] is not True:
            _refuse()
        marker = validate_marker(payload[MARKER_KEY], text=payload["text"])
        self.require_unretained_run(marker["run_id"])
        self.require_enrollment(marker["input"]["principal_id"], scope.session_id)
        if (marker["source"] != {"release": self.release, "profile_id": self.profile_id, "profile_digest": self.profile_digest}
                or marker["schema"] != MARKER_SCHEMA or marker["producer"] != self.producer
                or marker["publication"] != self.publication
                or marker["input"]["session_id"] != scope.session_id
                or marker["input"]["principal_id"] != row.get("principal_id")
                or marker["input"]["submission_id"] != row.get("request_id")
                or scope.binding is not self.binding or not scope.current()):
            _refuse("NATIVE_EVAL_ORIGINAL_BINDING_CHANGED")
        # Retained inputs remain the source of execution. The immutable store
        # must still resolve those same identities and the complete graph.
        try:
            scenario, config, experiment = marker["scenario"], marker["configuration"], marker["experiment"]
            if (self.store.resolve_scenario(scenario["scenario_id"], scenario["scenario_version"]) != scenario
                    or self.store.resolve_configuration(config["configuration_id"]) != config):
                _refuse()
            verify_scenario_graph(scenario, self.store)
            verify_configuration_graph(config, self.store)
            if experiment is not None:
                if self.store.resolve_experiment(experiment["experiment_id"]) != experiment:
                    _refuse()
                verify_experiment_graph(experiment, self.store)
        except Exception:
            _refuse("NATIVE_EVAL_INPUT_ARTIFACT_UNAVAILABLE")
        return EvalInputClaim(self, scope, marker)


def private_inputs_payload(authority, actor, request, selected):
    """Called by the explicitly selected native derivation before its fingerprint."""
    if type(selected) is not _PrivateSelection or type(selected.owner) is not NativeEvalInputOwner:
        _refuse("NATIVE_EVAL_PRIVATE_PRODUCER_REQUIRED")
    owner = selected.owner
    owner.check()
    owner.require_enrollment(actor.subject, request.ref.session_id)
    marker = validate_marker(json.loads(selected.encoded), text=request.payload.get("text"))
    owner.require_unretained_run(marker["run_id"])
    if (owner.binding.authority is not authority or request.intent != "queue"
            or set(request.payload) != {"text", "finite"} or request.payload["finite"] is not True
            or str(request.ref.profile_id) != owner.profile_id
            or marker["input"] != {"principal_id": actor.subject, "session_id": request.ref.session_id,
                "submission_id": request.request_id, "text_sha256": _sha(_bytes(request.payload["text"], MAX_INPUT_BYTES))}):
        _refuse("NATIVE_EVAL_ORIGINAL_BINDING_CHANGED")
    source = authority.sessions[request.ref.session_id].source
    if source is None or source.user_id != actor.subject:
        _refuse("NATIVE_EVAL_ORIGINAL_BINDING_CHANGED")
    return marker


def private_inputs_admission_guard(authority, actor, request, selected, original):
    """Compose with the incumbent new-write guard, within its one transaction.

    Original exact live/terminal replay returns before this guard. Reaching it
    means a new admission_id would be inserted: any prior run request therefore
    refuses, including one with the same textual carrier identity. The selected
    donor retains these PUBLIC_SAFE EVAL tombstones in its original namespace.
    """
    marker = private_inputs_payload(authority, actor, request, selected)
    request_id = marker["input"]["submission_id"]
    from hermes_state_terminal import ADMISSION_PREFIX

    def authorize(conn):
        if original is not None:
            original(conn)
        if (conn.execute("SELECT 1 FROM session_admissions WHERE request_id=? LIMIT 1", (request_id,)).fetchone()
                or conn.execute("SELECT 1 FROM state_meta WHERE key GLOB ? "
                    "AND json_extract(value, '$.request_id')=? LIMIT 1",
                    (ADMISSION_PREFIX + "*", request_id)).fetchone()):
            _refuse("NATIVE_EVAL_ORIGINAL_CARRIER_REQUIRED")
    return authorize


def _digest_text(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    return value


def validate_delivery(value, *, admission_id, generation, messages_digest, turn_id):
    """Closed same-claim projection from the existing Agent OS delivery owner."""
    from .native_request_observation import _text, _integer
    fields = {"admission_id", "execution_generation", "agent_session_id", "bundle_sha256",
        "receipt_sha256", "prefetch_context_sha256", "prefetch_context_bytes", "prompt"}
    value = _detach(value, maximum=2048)
    if (type(value) is not dict or set(value) != fields
            or value["admission_id"] != admission_id or value["execution_generation"] != generation
            or not _text(value["agent_session_id"]) or not _integer(value["execution_generation"])
            or not _integer(value["prefetch_context_bytes"]) or value["prefetch_context_bytes"] <= 0):
        _refuse("NATIVE_EVAL_DELIVERY_UNAVAILABLE")
    for key in ("bundle_sha256", "receipt_sha256", "prefetch_context_sha256"):
        _digest_text(value[key])
    prompt = value["prompt"]
    if (type(prompt) is not dict or set(prompt) != {
            "boundary", "turn_id", "context_block_sha256", "api_messages_sha256"}
            or prompt["boundary"] != "build_api_messages" or prompt["turn_id"] != turn_id
            or not _text(turn_id) or prompt["api_messages_sha256"] != messages_digest):
        _refuse("NATIVE_EVAL_DELIVERY_UNAVAILABLE")
    _digest_text(prompt["context_block_sha256"])
    _digest_text(prompt["api_messages_sha256"])
    return value


def record_source_pairs(inventory, *, bundle_sha256):
    """Project exact DATA refs, retaining distinct paths with identical bytes.

    The original context owner validates the inventory. Full file hashes bind
    selected record contributions; they do not claim full-file prompt delivery.
    """
    from control_plane.agentos_context_bundle import validate_retained_record_sources
    try:
        checked = validate_retained_record_sources(inventory, bundle_sha256=bundle_sha256,
                                                   data_commit=inventory["data_commit"])
        prefix = "git:" + checked["repository"] + "@" + checked["data_commit"] + "#"
        pairs = [{"artifact_ref": prefix + row["path"], "digest": "sha256:" + row["sha256"]}
                 for row in checked["entries"]]
        return contracts.v_source_artifact_list(pairs, "$.selected_record_sources")
    except Exception:
        _refuse("NATIVE_EVAL_SOURCE_INVENTORY_UNQUALIFIED")


def _require_record_policy(marker, inventory, *, bundle_sha256):
    pairs = record_source_pairs(inventory, bundle_sha256=bundle_sha256)
    if inventory["retention"] != "COMPLETE" or inventory["omitted_items"]:
        _refuse("NATIVE_EVAL_SOURCE_INVENTORY_INCOMPLETE")
    reasons = validity.source_policy_reason_codes(marker["scenario"], pairs)
    if reasons:
        _refuse("NATIVE_EVAL_" + sorted(reasons)[0])
    visible = set(marker["scenario"]["privacy"]["model_visible_artifact_refs"])
    if any(pair["artifact_ref"] not in visible for pair in pairs):
        _refuse("NATIVE_EVAL_SOURCE_NOT_MODEL_VISIBLE")
    return pairs


def _request_identity(row):
    return tuple(row.get(key) for key in ("agent_session_id", "turn_id", "api_request_id",
                                         "api_call_count", "retry_count", "content_sha256"))


def observed_record_sources(value):
    """Only original validated delivery-to-assembly joins contribute sources."""
    if value["schema"] not in STRONG_RESULT_SCHEMAS:
        return []
    snapshots = {row["inventory_sha256"]: row for row in value["source_snapshots"]}
    deliveries = {row["sequence"]: row for row in value["deliveries"]}
    pairs = {}
    for assembly in value["assemblies"]:
        delivery = deliveries[assembly["delivery_sequence"]]
        inventory = snapshots[delivery["source_inventory_sha256"]]
        for pair in record_source_pairs(inventory, bundle_sha256=delivery["agentos"]["bundle_sha256"]):
            previous = pairs.setdefault(pair["artifact_ref"], pair["digest"])
            if previous != pair["digest"]:
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    return [{"artifact_ref": ref, "digest": pairs[ref]} for ref in sorted(pairs)]


def _history_conversation_row(row):
    """Recognize a small replayable subset without retaining its content."""
    role = row.get("role")
    if type(role) is not str or role not in {"user", "assistant"}:
        return False
    content = row.get("content")
    if type(content) is str and content.strip():
        return True
    if type(content) is list:
        for item in content:
            if type(item) is not dict:
                continue
            if (item.get("type") == "text" and type(item.get("text")) is str
                    and item["text"].strip()):
                return True
            picture = item.get("image_url")
            if (item.get("type") == "image_url" and type(picture) is dict
                    and type(picture.get("url")) is str and picture["url"].strip()):
                return True
    calls = row.get("tool_calls")
    if role == "assistant" and type(calls) is list:
        for call in calls:
            if type(call) is not dict or call.get("type") != "function":
                continue
            function = call.get("function")
            if (type(call.get("id")) is str and call["id"].strip()
                    and type(function) is dict and type(function.get("name")) is str
                    and function["name"].strip() and type(function.get("arguments")) is str):
                return True
    return False


def _validate_history(row, *, sequence):
    from .native_request_observation import _text, _integer
    if (type(row) is not dict or set(row) != {"sequence", "boundary", "agent_session_id",
            "turn_id", "row_count", "conversation_rows"}
            or type(row["sequence"]) is not int or row["sequence"] != sequence
            or row["boundary"] != HISTORY_BOUNDARY
            or not _text(row["agent_session_id"]) or not _text(row["turn_id"])
            or not _integer(row["row_count"]) or not _integer(row["conversation_rows"])
            or not 0 <= row["conversation_rows"] <= row["row_count"] <= MAX_HISTORY_ROWS):
        _refuse("NATIVE_EVAL_OBSERVATION_INVALID")


def validate_observation(value, *, marker, receipt, request_observation):
    """Historical projection from the original row/result, never today's owner."""
    from .native_request_observation import MAX_METADATA_BYTES, _text, _integer
    value = _detach(value, maximum=MAX_METADATA_BYTES)
    schema = value.get("schema") if type(value) is dict else None
    version2 = type(schema) is str and schema in STRONG_RESULT_SCHEMAS
    version3 = schema == RESULT_SCHEMA
    allowed_errors = OBSERVATION_ERRORS if version3 else LEGACY_OBSERVATION_ERRORS
    expected = {"schema": value["schema"] if version2 else LEGACY_RESULT_SCHEMA, "run_id": marker["run_id"],
        "binding_sha256": marker["binding_sha256"], "admission_id": receipt["admission_id"],
        "execution_generation": receipt["execution_generation"], "authority_epoch": receipt["authority_epoch"],
        "candidate_digest": marker["configuration"]["procedure"]["instruction_bundle"]["digest"],
        "rendered_sha256": marker["rendered_sha256"], "complete_evaluation": False}
    extra_fields = ({"source_snapshots"} if version2 else set()) | ({"histories"} if version3 else set())
    if (type(value) is not dict or set(value) != set(expected) | {"instance_id", "deliveries", "assemblies", "errors"} | extra_fields
            or any(type(value[key]) is not type(item) or value[key] != item for key, item in expected.items())
            or not _text(value["instance_id"]) or not _integer(value["execution_generation"])
            or not _integer(value["authority_epoch"]) or value["authority_epoch"] < 1
            or type(value["errors"]) is not list or any(type(e) is not str or e not in allowed_errors for e in value["errors"])
            or value["errors"] != sorted(set(value["errors"]))):
        _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    # The caller supplies the independently validated sibling projection from
    # the same original stored result. Never join history to today's process.
    sibling = request_observation
    if (type(sibling) is not dict or type(sibling.get("scope")) is not dict
            or sibling["scope"].get("instance_id") != value["instance_id"]
            or any(sibling["scope"].get(key) != value[key] for key in (
                "admission_id", "execution_generation", "authority_epoch"))
            or type(sibling.get("observations")) is not list):
        _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    available = Counter((row.get("turn_id"), row.get("api_request_id"), row.get("content_sha256"))
                        for row in sibling["observations"])
    snapshots, deliveries, histories = {}, {}, {}
    if version3:
        rows = value["histories"]
        if type(rows) is not list or len(rows) > MAX_EVENTS:
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
        for sequence, row in enumerate(rows, 1):
            _validate_history(row, sequence=sequence)
            histories[sequence] = row
    if version2:
        rows = value["source_snapshots"]
        if type(rows) is not list or len(rows) > MAX_EVENTS:
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
        for row in rows:
            if type(row) is not dict:
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
            record_source_pairs(row, bundle_sha256=row.get("bundle_sha256"))
            digest = row["inventory_sha256"]
            if digest in snapshots:
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
            snapshots[digest] = row
        if list(snapshots) != sorted(snapshots):
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
        available = Counter(_request_identity(row) for row in sibling["observations"])
        # A duplicate identity cannot prove which original retry was joined.
        if any(count != 1 for count in available.values()):
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    for kind in ("deliveries", "assemblies"):
        if type(value[kind]) is not list or len(value[kind]) > MAX_EVENTS:
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    for ordinal, row in enumerate(value["deliveries"], 1):
        fields = {"rendered_sha256", "messages_sha256", "turn_id", "agentos"}
        if version2:
            fields |= {"sequence", "source_inventory_sha256", "current_user"}
        if version3:
            fields.add("history_sequence")
        if (type(row) is not dict or set(row) != fields
                or row["rendered_sha256"] != marker["rendered_sha256"] or not _text(row["turn_id"])):
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
        _digest_text(row["messages_sha256"])
        validate_delivery(row["agentos"], admission_id=receipt["admission_id"],
            generation=receipt["execution_generation"], messages_digest=row["messages_sha256"], turn_id=row["turn_id"])
        if version2:
            anchor = row["current_user"]
            if (type(row["sequence"]) is not int or row["sequence"] != ordinal
                    or row["source_inventory_sha256"] not in snapshots
                    or type(anchor) is not dict or set(anchor) != {"row_index", "row_count", "text_sha256"}
                    or not _integer(anchor["row_index"]) or not _integer(anchor["row_count"])
                    or not 0 <= anchor["row_index"] < anchor["row_count"] <= 65536):
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
            _digest_text(anchor["text_sha256"])
            inventory = snapshots[row["source_inventory_sha256"]]
            record_source_pairs(inventory, bundle_sha256=row["agentos"]["bundle_sha256"])
            deliveries[ordinal] = row
        if version3 and row["history_sequence"] is not None:
            sequence = row["history_sequence"]
            if (type(sequence) is not int or sequence not in histories
                    or histories[sequence]["turn_id"] != row["turn_id"]
                    or histories[sequence]["agent_session_id"] != row["agentos"]["agent_session_id"]):
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    if version2 and set(snapshots) != {row["source_inventory_sha256"] for row in deliveries.values()}:
        _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    for row in value["assemblies"]:
        fields = {"content_sha256", "turn_id", "api_request_id", "tool_schema_digests"}
        if version2:
            fields |= {"agent_session_id", "api_call_count", "retry_count", "messages_sha256",
                       "delivery_sequence", "delivery_sha256"}
        if (type(row) is not dict or set(row) != fields
                or not _text(row["turn_id"]) or not _text(row["api_request_id"])
                or type(row["tool_schema_digests"]) is not list or len(row["tool_schema_digests"]) > 128):
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
        _digest_text(row["content_sha256"])
        for digest in row["tool_schema_digests"]:
            if type(digest) is not str or not digest.startswith("sha256:"):
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
            _digest_text(digest.removeprefix("sha256:"))
        if row["tool_schema_digests"] != sorted(set(row["tool_schema_digests"])):
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
        identity = (row["turn_id"], row["api_request_id"], row["content_sha256"])
        if version2:
            if (not _text(row["agent_session_id"]) or not _integer(row["api_call_count"])
                    or not _integer(row["retry_count"]) or type(row["delivery_sequence"]) is not int
                    or row["delivery_sequence"] not in deliveries
                    or row["messages_sha256"] != row["content_sha256"]):
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
            delivery = deliveries[row["delivery_sequence"]]
            if (delivery["turn_id"] != row["turn_id"]
                    or delivery["agentos"]["agent_session_id"] != row["agent_session_id"]
                    or row["delivery_sha256"] != _sha(canonical_json_bytes(delivery))):
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
            inventory = snapshots[delivery["source_inventory_sha256"]]
            _require_record_policy(marker, inventory, bundle_sha256=delivery["agentos"]["bundle_sha256"])
            identity = _request_identity(row)
            original = [event for event in sibling["observations"] if _request_identity(event) == identity]
            if len(original) != 1 or original[0].get("invalid_fields") or original[0].get("fields") != ["messages"]:
                _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
        available[identity] -= 1
        if available[identity] < 0:
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
    return value


class EvalInputClaim:
    """One transient input contribution to the original executing scope."""

    def __init__(self, owner, scope, marker):
        self.owner, self.scope, self.marker = owner, scope, marker
        self.rendered = render_inputs(marker["candidate_files"], marker["context_text"])
        self.resolved_route = self.resolved_ephemeral = None
        self.deliveries, self.assemblies, self.histories = [], [], []
        self.history_proof = None  # Original transient claim/turn, never a history cache.
        self.source_snapshots = {}
        self.delivery_proof = None  # One current original claim; never a history lookup.
        self.errors = set()

    def current(self):
        self.owner.check()
        self.owner.require_enrollment(self.marker["input"]["principal_id"], self.scope.session_id)
        if self.scope.closed or not self.scope.current() or self.scope.evaluation is not self:
            _refuse("NATIVE_EVAL_ORIGINAL_BINDING_CHANGED")

    def fail(self, code):
        if code not in OBSERVATION_ERRORS:
            _refuse()
        with self.scope.live.event_stream.lock, self.scope.lock:
            if not self.scope.closed:
                self.errors.add(code)

    def _append(self, agent, records, row, overflow):
        with self.scope.live.event_stream.lock, self.scope.lock:
            if (self.scope.closed or not self.scope.current()
                    or self.scope.evaluation is not self or not self.scope.adopted(agent)):
                return
            if len(records) >= MAX_EVENTS:
                self.errors.add(overflow)
            elif self.scope._reserve(row):
                records.append(row)
            else:
                self.errors.add("metadata_overflow")

    def history_snapshot(self, claim, agent, history, messages):
        """Only counts from the qualified caller's already copied history."""
        factory = self.owner.binding.memory_factory
        if (claim.scope is not self.scope or self.scope.evaluation is not self or self.scope.closed
                or not self.scope.current() or claim.factory is not factory or claim.agent is not agent
                or not claim.current(adopted=True) or factory.current_claim() is not claim):
            return None
        self.history_proof = None
        if not factory.evaluation_history_current(claim, agent):
            return None
        rows = [] if history is None else history
        if (type(rows) is not list or type(messages) is not list
                or len(rows) > MAX_HISTORY_ROWS or len(messages) != len(rows)
                or any(type(row) is not dict or messages[index] is not row
                       for index, row in enumerate(rows))):
            return None
        # Reuse the existing bounded JSON walk; discard its digest. The
        # observation retains neither history bytes nor a history-content hash.
        from .native_request_observation import _content_digest
        _content_digest({"messages": rows})
        row = {"sequence": 1, "boundary": HISTORY_BOUNDARY,
            "agent_session_id": agent.session_id, "turn_id": getattr(agent, "_current_turn_id", None),
            "row_count": len(rows),
            "conversation_rows": sum(_history_conversation_row(item) for item in rows)}
        _validate_history(row, sequence=1)
        return row

    def note_history(self, claim, agent, snapshot):
        """Retain once the original hydration helper returned without failure."""
        factory = self.owner.binding.memory_factory
        with self.scope.live.event_stream.lock, self.scope.lock:
            if (claim.scope is not self.scope or self.scope.evaluation is not self or self.scope.closed
                    or not self.scope.current() or not factory.evaluation_history_current(claim, agent)
                    or snapshot["agent_session_id"] != agent.session_id
                    or snapshot["turn_id"] != getattr(agent, "_current_turn_id", None)):
                return
            if len(self.histories) >= MAX_EVENTS:
                self.errors.add("history_overflow")
                return
            row = {**snapshot, "sequence": len(self.histories) + 1}
            if not self.scope._reserve(row):
                self.errors.add("metadata_overflow")
                return
            self.histories.append(row)
            self.history_proof = {"claim": claim, "agent": agent, "row": row}

    def history_for_delivery(self, claim, agent):
        proof = self.history_proof
        factory = self.owner.binding.memory_factory
        if (proof is None or proof["claim"] is not claim or proof["agent"] is not agent
                or claim.scope is not self.scope or self.scope.evaluation is not self or self.scope.closed
                or not self.scope.current() or not factory.evaluation_history_current(claim, agent)
                or proof["row"]["agent_session_id"] != agent.session_id
                or proof["row"]["turn_id"] != getattr(agent, "_current_turn_id", None)):
            return None
        return proof["row"]["sequence"]

    def _descriptor(self, route):
        from integrations.hermes_omh.hae_zai_extension import direct_zai_levels
        runtime = route["runtime"]
        result = {"model": route["model"], "provider": runtime.get("provider"),
            "requested_provider": runtime.get("requested_provider"),
            "api_mode": runtime.get("api_mode"), "base_url": runtime.get("base_url")}
        effort = self.marker["configuration"]["execution"]["reasoning_effort"]
        spec = self.owner.provider_spec
        # Pinned runtime_provider_custom resolves the configured named entry
        # to provider="custom" and retains requested_provider. Keep both actual
        # identities; this is not a string normalization or a model-ID claim.
        if (spec.provider_id != "zai.glm-5.3" or result != {
                "model": spec.served_model, "provider": "custom", "requested_provider": spec.hermes_name,
                "api_mode": "chat_completions", "base_url": spec.base_url}
                or effort not in direct_zai_levels("zai", result["model"], result["api_mode"], result["base_url"])):
            _refuse("NATIVE_EVAL_EFFORT_ROUTE_UNQUALIFIED")
        # Never capture credentials or mutable runtime/client objects.
        return _detach(result, maximum=2048)

    def _route(self, route, reasoning):
        self.current()
        configuration = self.marker["configuration"]
        expected = configuration["execution"]
        if (type(route) is not dict or type(route.get("runtime")) is not dict
                or route.get("model") != expected["model_requested"]
                or route["runtime"].get("provider") != expected["provider"]
                or route["runtime"].get("api_mode") != "chat_completions"
                or type(reasoning) is not dict or reasoning.get("enabled") is False
                or reasoning.get("effort") != expected["reasoning_effort"]):
            _refuse("NATIVE_EVAL_ROUTE_UNQUALIFIED")
        old = route.get("request_overrides")
        if old is not None and type(old) is not dict:
            _refuse()
        overrides = dict(old or {})
        seed = configuration["randomness"]["seed"]
        if (("seed" in overrides and (type(overrides["seed"]) is not int or overrides["seed"] != seed))
                or (type(overrides.get("extra_body")) is dict and "seed" in overrides["extra_body"])):
            _refuse("NATIVE_EVAL_SEED_CONFLICT")
        overrides["seed"] = seed
        return {**route, "runtime": dict(route["runtime"]), "request_overrides": overrides}

    def resolve_arguments(self, original, turn, args, kwargs):
        bound = inspect.signature(original).bind(turn, *args, **kwargs)
        values = bound.arguments
        values["reasoning_config"] = {"enabled": True,
            "effort": self.marker["configuration"]["execution"]["reasoning_effort"]}
        values["turn_route"] = self._route(values["turn_route"], values["reasoning_config"])
        ephemeral = values["combined_ephemeral"]
        if ephemeral is not None and type(ephemeral) is not str:
            _refuse()
        values["combined_ephemeral"] = (ephemeral or "") + self.rendered
        self.resolved_route = self._descriptor(values["turn_route"])
        self.resolved_ephemeral = values["combined_ephemeral"]
        return bound.args[1:], bound.kwargs

    def wire_arguments(self, original, turn, agent, args, kwargs):
        bound = inspect.signature(original).bind(turn, agent, *args, **kwargs)
        values = bound.arguments
        values["reasoning_config"] = {"enabled": True,
            "effort": self.marker["configuration"]["execution"]["reasoning_effort"]}
        route = self._route(values["turn_route"], values["reasoning_config"])
        if self.resolved_route is None or self._descriptor(route) != self.resolved_route:
            _refuse("NATIVE_EVAL_ROUTE_CHANGED")
        values["turn_route"] = route
        return bound.args[2:], bound.kwargs

    def require_agent(self, agent):
        self.current()
        expected = self.marker["configuration"]["execution"]
        actual_route = {"model": agent.model, "runtime": {"provider": agent.provider,
            "requested_provider": agent.requested_provider,
            "api_mode": agent.api_mode, "base_url": agent.base_url}}
        if (not self.scope.adopted(agent) or agent.model != expected["model_requested"]
                or agent.provider != expected["provider"] or agent.api_mode != "chat_completions"
                or self._descriptor(actual_route) != self.resolved_route
                or getattr(agent, "_disable_streaming", None) is not True
                or agent.ephemeral_system_prompt != self.resolved_ephemeral
                or type(getattr(agent, "request_overrides", None)) is not dict
                or type(agent.request_overrides.get("seed")) is not int
                or agent.request_overrides["seed"] != self.marker["configuration"]["randomness"]["seed"]):
            _refuse("NATIVE_EVAL_AGENT_INPUTS_UNQUALIFIED")

    def require_messages(self, agent, result):
        self.require_agent(agent)
        messages, effective_system = result
        if (type(effective_system) is not str or not effective_system.endswith(self.rendered)
                or type(messages) is not list or not messages or type(messages[0]) is not dict
                or messages[0].get("role") != "system" or messages[0].get("content") != effective_system):
            _refuse("NATIVE_EVAL_CANDIDATE_NOT_DELIVERED")

    def require_request(self, agent, api_kwargs):
        self.require_agent(agent)
        factory = self.owner.binding.memory_factory
        claim = factory.current_claim()
        if claim.scope is not self.scope or claim.agent is not agent or not claim.barrier_entered:
            _refuse("NATIVE_EVAL_ORIGINAL_BINDING_CHANGED")
        # Required execution custody, outside the optional observer catch.
        # This uses the original attachment and durable generation owner; an
        # in-memory stamp alone cannot qualify a retired execution.
        factory.require_snapshot(claim, agent)
        proof = self.delivery_proof
        if (proof is None or proof["claim"] is not claim
                or proof["instance"] is not claim.instance
                or proof["provider"] is not claim.instance.provider
                or proof["snapshot"] is not claim.instance.provider._snapshot
                or proof["anchor"] is not claim.prompt_anchor
                or proof["delivery"] != claim.returned
                or proof["delivery"]["prompt"]["turn_id"] != getattr(agent, "_current_turn_id", None)):
            _refuse("NATIVE_EVAL_DELIVERY_UNAVAILABLE")
        expected = self.marker["configuration"]["execution"]
        if type(api_kwargs) is not dict:
            _refuse("NATIVE_EVAL_ASSEMBLED_INPUTS_CHANGED")
        extra = api_kwargs.get("extra_body")
        # The OpenAI serializer merges extra_body over typed request fields.
        # Do not admit a second, contradictory input through that merge seam.
        # The selected named custom profile emits no extra-body fields. Keep
        # that finite qualified route closed instead of guessing which future
        # provider extension might override a typed field or carry content.
        if (extra is not None and (type(extra) is not dict or extra)
                or set(api_kwargs) & {"input", "system", "instructions", "prompt", "input_messages"}):
            _refuse("NATIVE_EVAL_ASSEMBLED_INPUTS_CHANGED")
        messages = api_kwargs.get("messages")
        if (type(messages) is not list or not messages or type(messages[0]) is not dict
                or messages[0].get("role") != "system" or type(messages[0].get("content")) is not str
                or not messages[0]["content"].endswith(self.rendered)
                or api_kwargs.get("model") != expected["model_requested"]
                or type(api_kwargs.get("seed")) is not int
                or api_kwargs["seed"] != self.marker["configuration"]["randomness"]["seed"]
                or api_kwargs.get("reasoning_effort") != expected["reasoning_effort"]
                or api_kwargs.get("stream", False) is not False):
            _refuse("NATIVE_EVAL_ASSEMBLED_INPUTS_CHANGED")
        anchor = proof["anchor"]
        if (len(messages) != anchor["row_count"] or any(type(row) is not dict for row in messages)
                or tuple(row.get("role") for row in messages) != anchor["roles"]):
            _refuse("NATIVE_EVAL_AGENTOS_DELIVERY_CHANGED")
        content = messages[anchor["row_index"]].get("content")
        pieces = ([content] if type(content) is str else [item.get("text") for item in content
            if type(item) is dict and item.get("type") == "text"] if type(content) is list else [])
        if sum(type(piece) is str and piece == anchor["text"] for piece in pieces) != 1:
            _refuse("NATIVE_EVAL_AGENTOS_DELIVERY_CHANGED")
        _require_record_policy(self.marker, proof["inventory"],
                               bundle_sha256=proof["delivery"]["bundle_sha256"])
        factory.require_snapshot(claim, agent)
        if claim.instance.provider._snapshot is not proof["snapshot"]:
            _refuse("NATIVE_EVAL_DELIVERY_UNAVAILABLE")
        return proof

    def note_messages(self, agent, result, delivery):
        self.delivery_proof = None
        self.require_messages(agent, result)
        messages, _ = result
        from .native_request_observation import _content_digest
        messages_digest = _content_digest({"messages": messages})["content_sha256"]
        delivery = validate_delivery(delivery, admission_id=self.scope.admission_id,
            generation=self.scope.generation, messages_digest=messages_digest,
            turn_id=getattr(agent, "_current_turn_id", None))
        if delivery["agent_session_id"] != agent.session_id:
            _refuse("NATIVE_EVAL_DELIVERY_UNAVAILABLE")
        factory = self.owner.binding.memory_factory
        claim = factory.current_claim()
        factory.require_snapshot(claim, agent)
        instance, anchor = claim.instance, claim.prompt_anchor
        provider = instance.provider
        snapshot = provider._snapshot
        current = provider.context_observation()
        if (claim.scope is not self.scope or claim.agent is not agent or not claim.barrier_entered
                or current is None or anchor is None or claim.returned != delivery
                or any(current[key] != delivery[target] for key, target in (
                    ("bundle_sha256", "bundle_sha256"), ("receipt_sha256", "receipt_sha256"),
                    ("rendered_context_sha256", "prefetch_context_sha256"),
                    ("rendered_context_bytes", "prefetch_context_bytes")))):
            _refuse("NATIVE_EVAL_DELIVERY_UNAVAILABLE")
        inventory = provider._record_sources_observation(
            rendered_context_sha256=delivery["prefetch_context_sha256"])
        record_source_pairs(inventory, bundle_sha256=delivery["bundle_sha256"])
        factory.require_snapshot(claim, agent)
        if provider._snapshot is not snapshot or claim.prompt_anchor is not anchor:
            _refuse("NATIVE_EVAL_DELIVERY_UNAVAILABLE")
        observed = {"rendered_sha256": self.marker["rendered_sha256"],
            "messages_sha256": messages_digest,
            "turn_id": getattr(agent, "_current_turn_id", None), "agentos": delivery,
            "sequence": len(self.deliveries) + 1,
            "history_sequence": self.history_for_delivery(claim, agent),
            "source_inventory_sha256": inventory["inventory_sha256"],
            "current_user": {key: anchor[key] for key in ("row_index", "row_count", "text_sha256")}}
        # Retain one inventory per digest within the original shared budget.
        # Live policy still uses this original snapshot if later retention is
        # exhausted; lost historical evidence never becomes complete coverage.
        sequence = None
        with self.scope.live.event_stream.lock, self.scope.lock:
            if (self.scope.closed or not self.scope.current()
                    or self.scope.evaluation is not self or not self.scope.adopted(agent)):
                _refuse("NATIVE_EVAL_ORIGINAL_BINDING_CHANGED")
            previous = self.source_snapshots.get(inventory["inventory_sha256"])
            reservation = {"delivery": observed, "source_snapshot": inventory if previous is None else None}
            if len(self.deliveries) >= MAX_EVENTS:
                self.errors.add("delivery_overflow")
            elif self.scope._reserve(reservation):
                self.source_snapshots.setdefault(inventory["inventory_sha256"], copy.deepcopy(inventory))
                self.deliveries.append(observed)
                sequence = observed["sequence"]
            else:
                self.errors.add("metadata_overflow")
        self.delivery_proof = {"claim": claim, "instance": instance, "provider": provider,
            "snapshot": snapshot, "anchor": anchor, "delivery": delivery,
            "inventory": inventory, "sequence": sequence,
            "delivery_sha256": _sha(canonical_json_bytes(observed))}

    def record_assembly(self, agent, api_kwargs, event):
        proof = self.require_request(agent, api_kwargs)
        from .native_request_observation import _json_digest, _content_digest, _text, _integer
        if proof["sequence"] is None:
            self.fail("delivery_unavailable")
            return
        messages_digest = _content_digest({"messages": api_kwargs["messages"]})["content_sha256"]
        if (event.get("fields") != ["messages"] or event.get("invalid_fields")
                or event.get("content_sha256") != messages_digest
                or event.get("agent_session_id") != agent.session_id
                or any(not _text(event.get(key)) for key in ("turn_id", "api_request_id"))
                or event["turn_id"] != proof["delivery"]["prompt"]["turn_id"]
                or any(not _integer(event.get(key)) for key in ("api_call_count", "retry_count"))):
            _refuse("NATIVE_EVAL_OBSERVATION_INVALID")
        tools = api_kwargs.get("tools", [])
        if (type(tools) is not list or len(tools) > 128
                or any(type(tool) is not dict for tool in tools)):
            self.fail("tool_schema_unavailable")
            return
        _json_digest(tools)  # Bound total bytes/depth/nodes before individual schemas.
        row = {"content_sha256": event["content_sha256"],
            "turn_id": event.get("turn_id"), "api_request_id": event.get("api_request_id"),
            "agent_session_id": event["agent_session_id"], "api_call_count": event["api_call_count"],
            "retry_count": event["retry_count"], "messages_sha256": messages_digest,
            "delivery_sequence": proof["sequence"],
            "delivery_sha256": proof["delivery_sha256"],
            "tool_schema_digests": sorted({"sha256:" + _json_digest(tool)[0] for tool in tools})}
        self._append(agent, self.assemblies, row, "assembly_overflow")

    def document(self, *, force_empty=False):
        return {"schema": RESULT_SCHEMA, "run_id": self.marker["run_id"],
            "binding_sha256": self.marker["binding_sha256"],
            "admission_id": self.scope.admission_id, "execution_generation": self.scope.generation,
            "instance_id": self.scope.instance_id, "authority_epoch": self.scope.epoch,
            "candidate_digest": self.marker["configuration"]["procedure"]["instruction_bundle"]["digest"],
            "rendered_sha256": self.marker["rendered_sha256"],
            "deliveries": [] if force_empty else copy.deepcopy(self.deliveries),
            "assemblies": [] if force_empty else copy.deepcopy(self.assemblies),
            "histories": [] if force_empty else copy.deepcopy(self.histories),
            "source_snapshots": [] if force_empty else [copy.deepcopy(self.source_snapshots[key])
                                                        for key in sorted(self.source_snapshots)],
            "errors": sorted(self.errors | ({"retention_overflow"} if force_empty else set())),
            "complete_evaluation": False}

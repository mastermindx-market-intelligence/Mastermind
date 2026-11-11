"""Typed ADOPT recipe integration over the actual captured Agent OS compiler.

This module neither acquires source nor authenticates a caller. The incumbent
qualified source factory supplies the actual compiler/record-owner modules and
source binding; the common source-operation owner supplies current grants,
reserved-scope qualification, verified private-artifact reads, committed phase
settlement, Git/CAS and publication. No dict here is a grant or a receipt.
Recipes remain PREVIEW_ONLY until those existing owners perform their effects.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from types import ModuleType

ACTION = "ADOPT_PLAN"
PRIVATE_SCHEMA = "mastermind.project_source_original_input.v1"
_PATHS = {"compiler": "scripts/agentos_plan_adoption.py", "owner": "scripts/agentos.py",
          "contract": "scripts/agentos_project_plan_contract.py"}
_MACRO = "mastermindx-market-intelligence/macro"
_KEYS = {"schema", "action", "request", "actor", "initial_snapshot", "source_binding"}
_CODES = {"PLAN_ADOPTION_INPUT_INVALID", "PLAN_ADOPTION_INPUT_CONFLICT", "PLAN_ADOPTION_RECIPE_UNAVAILABLE"}


class PlanAdoptionOperationError(ValueError):
    def __init__(self, code):
        self.code = code if code in _CODES else "PLAN_ADOPTION_RECIPE_UNAVAILABLE"
        super().__init__(self.code)


def _fail(code):
    raise PlanAdoptionOperationError(code)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def adoption_snapshot_material(value, *, source_binding=None, work_ref=None, current_phase=False):
    """Detach legacy content or an installed CODE/DATA observation.

    Observation dictionaries grant nothing. The installed nominal DATA owner
    constructs them and the incumbent private artifact/Event owner restores
    them. They stay outside the canonical compiler's closed snapshot schema.
    """
    if type(value) is not dict:
        _fail("PLAN_ADOPTION_INPUT_INVALID")
    if set(value) == {"snapshot", "canonical_data"}:
        from common.canonical_project_data_observation_contract import validate
        try:
            observed = validate(value["canonical_data"])
            snapshot = value["snapshot"]
            if type(snapshot) is not dict or snapshot["commit"] != observed["canonical_data_commit"]:
                _fail("PLAN_ADOPTION_INPUT_CONFLICT")
            if source_binding is not None and observed["executable_macro_commit"] != source_binding["compiler"]["commit"]:
                _fail("PLAN_ADOPTION_INPUT_CONFLICT")
            operation, continuity = observed["source_operation"], observed.get("data_continuity")
            if work_ref is not None and ((operation is not None and operation["selection"]["work_ref"] != work_ref)
                    or (continuity is not None and continuity["work_ref"] != work_ref)):
                _fail("PLAN_ADOPTION_INPUT_CONFLICT")
            return deepcopy(snapshot)
        except PlanAdoptionOperationError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError):
            _fail("PLAN_ADOPTION_INPUT_CONFLICT")
    # Legacy CURRENT snapshots already advance after the candidate's real
    # publication. Their unchanged records/candidate are checked by the
    # canonical compiler, as before; only the legacy INITIAL pin was equal.
    if not current_phase and source_binding is not None and value.get("commit") != source_binding["compiler"]["commit"]:
        _fail("PLAN_ADOPTION_INPUT_CONFLICT")
    return deepcopy(value)


class PreparedPlanAdoption:
    """Private frozen material, not an issued authorization or publication fact.

    Accessors detach data. The adapter recomputes its actual compiler fingerprint
    before each use. The common owner must only restore through its verified
    private-artifact read, with the trusted fingerprint from its original event.
    """
    __slots__ = ("_payload", "_fingerprint")

    def __init__(self, payload, fingerprint):
        self._payload = deepcopy(payload)
        self._fingerprint = fingerprint

    @property
    def fingerprint_sha256(self):
        return self._fingerprint

    def private_payload(self):
        return deepcopy(self._payload)

    def initial_snapshot(self):
        return adoption_snapshot_material(self._payload["initial_snapshot"],
            source_binding=self._payload["source_binding"], work_ref=self._payload["request"]["work_ref"])

    def safe_metadata(self):
        request = self._payload["request"]
        return {"action": ACTION, "request_id": request["request_id"],
                "work_ref": request["work_ref"], "trusted_recipe_fingerprint": self._fingerprint,
                "source_binding_sha256": _digest(self._payload["source_binding"])}


class PlanAdoptionRecipeAdapter:
    """Action-specific wrapper for the existing source-operation engine.

    ``source_binding`` has exactly compiler/owner/contract code bindings at the
    original captured Macro commit. Membership and module/code correspondence
    are established by the installed source factory, not by these labels.
    No public request can supply modules, actor, snapshots or this binding.
    """
    action = ACTION

    def __init__(self, *, compiler: ModuleType, owner: ModuleType, source_binding: dict):
        try:
            if (type(compiler) is not ModuleType or type(owner) is not ModuleType
                    or not callable(getattr(compiler, "compile_candidate_recipe", None))
                    or not callable(getattr(compiler, "compile_adoption_recipe", None))
                    or type(source_binding) is not dict or set(source_binding) != set(_PATHS)):
                _fail("PLAN_ADOPTION_INPUT_INVALID")
            # Code bindings are NOT plan-content SourceRefs (.md only). Their
            # three paths are closed here; labels still prove no membership.
            binding = deepcopy(source_binding)
            for name, ref in binding.items():
                if (type(ref) is not dict or set(ref) != {"repository", "path", "commit", "content_sha256"}
                        or ref["repository"] != _MACRO or ref["path"] != _PATHS[name]
                        or type(ref["commit"]) is not str or re.fullmatch(r"[0-9a-f]{40}", ref["commit"]) is None
                        or type(ref["content_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", ref["content_sha256"]) is None):
                    _fail("PLAN_ADOPTION_INPUT_INVALID")
            if len({ref["commit"] for ref in binding.values()}) != 1:
                _fail("PLAN_ADOPTION_INPUT_INVALID")
            self._compiler, self._owner = compiler, owner
            self._binding = deepcopy(binding)
        except PlanAdoptionOperationError:
            raise
        except Exception:
            _fail("PLAN_ADOPTION_INPUT_INVALID")

    def _candidate(self, payload):
        try:
            if (type(payload) is not dict or set(payload) != _KEYS
                    or payload["schema"] != PRIVATE_SCHEMA or payload["action"] != ACTION):
                _fail("PLAN_ADOPTION_INPUT_INVALID")
            if payload["source_binding"] != self._binding:
                _fail("PLAN_ADOPTION_INPUT_CONFLICT")
            snapshot = adoption_snapshot_material(payload["initial_snapshot"],
                source_binding=self._binding, work_ref=payload["request"]["work_ref"])
            recipe = self._compiler.compile_candidate_recipe(request=deepcopy(payload["request"]),
                snapshot=snapshot, actor=deepcopy(payload["actor"]), owner=self._owner)
            if (type(recipe) is not dict or recipe.get("schema") != "agentos.plan_adoption_recipe.v1"
                    or recipe.get("status") != "PREVIEW_ONLY" or recipe.get("phase") != "CANDIDATE"
                    or recipe.get("request_id") != payload["request"]["request_id"]
                    or recipe.get("work_ref") != payload["request"]["work_ref"]):
                _fail("PLAN_ADOPTION_RECIPE_UNAVAILABLE")
            return recipe
        except PlanAdoptionOperationError:
            raise
        except Exception:
            _fail("PLAN_ADOPTION_RECIPE_UNAVAILABLE")

    def prepare(self, *, request, initial_snapshot, actor):
        """Called by the qualified preview factory before showing Review.

        The real owner must persist this exact private material in its existing
        artifact helper before accepting a submit for this original ID.
        """
        payload = {"schema": PRIVATE_SCHEMA, "action": ACTION, "request": deepcopy(request),
            "actor": deepcopy(actor), "initial_snapshot": deepcopy(initial_snapshot),
            "source_binding": deepcopy(self._binding)}
        recipe = self._candidate(payload)
        return PreparedPlanAdoption(payload, recipe["request_sha256"])

    def restore(self, *, private_payload, trusted_recipe_fingerprint):
        """Use only an actual verified artifact read and committed owner fingerprint.

        This method cannot authenticate dictionaries or a client-provided hash.
        It refuses changed source/code/actor/request/predecessor rather than
        reconstructing a replacement intent from current source.
        """
        recipe = self._candidate(private_payload)
        if recipe["request_sha256"] != trusted_recipe_fingerprint:
            _fail("PLAN_ADOPTION_INPUT_CONFLICT")
        return PreparedPlanAdoption(private_payload, recipe["request_sha256"])

    def candidate_recipe(self, prepared):
        if type(prepared) is not PreparedPlanAdoption:
            _fail("PLAN_ADOPTION_INPUT_INVALID")
        recipe = self._candidate(prepared.private_payload())
        if recipe["request_sha256"] != prepared.fingerprint_sha256:
            _fail("PLAN_ADOPTION_INPUT_CONFLICT")
        return deepcopy(recipe)

    def decision_recipe(self, prepared, *, current_snapshot, prior_qualified_publication):
        """The existing engine qualifies prior publication before this call.

        Its private proof uses the compiler fingerprint, not the observed public
        request hash. UNKNOWN, queued and local-only publication fail in a5cb.
        Current grant/source/CAS and unique phase-attempt remain engine duties.
        """
        self.candidate_recipe(prepared)  # recheck all frozen material first
        payload = prepared.private_payload()
        try:
            recipe = self._compiler.compile_adoption_recipe(request=payload["request"],
                initial_snapshot=prepared.initial_snapshot(),
                current_snapshot=adoption_snapshot_material(current_snapshot,
                    source_binding=self._binding, work_ref=payload["request"]["work_ref"], current_phase=True),
                actor=payload["actor"], candidate_publication=deepcopy(prior_qualified_publication), owner=self._owner)
            if (type(recipe) is not dict or recipe.get("status") != "PREVIEW_ONLY"
                    or recipe.get("phase") != "ADOPTION_DECISION"
                    or recipe.get("request_id") != payload["request"]["request_id"]
                    or recipe.get("work_ref") != payload["request"]["work_ref"]
                    or recipe.get("request_sha256") != prepared.fingerprint_sha256):
                _fail("PLAN_ADOPTION_RECIPE_UNAVAILABLE")
            return deepcopy(recipe)
        except PlanAdoptionOperationError:
            raise
        except Exception:
            _fail("PLAN_ADOPTION_RECIPE_UNAVAILABLE")

"""Private typed ADOPT mode of the incumbent fixed Git publisher.

No compiler, source acquisition, credential, grant issuance, Event append or
retry lives here. The installed action owner supplies the actual committed
phase binding and nonserializable permit. Planned CAS hashes are never proof
of publication. The same publisher's guarded Git/PR primitives do the work.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from control_plane import workspace_project_git_publisher as p

SCHEMA = "mastermind.plan_adoption_git_publication.v1"
BINDING_SCHEMA = "mastermind.plan_adoption_publication_binding.v1"
LOOKUP_SCHEMA = "mastermind.workspace_source_operation_lookup.v1"
RECIPE_KEYS = {"schema", "status", "phase", "request_id", "request_sha256", "work_ref",
    "principal_id", "expected_commit", "candidate_path", "candidate_sha256", "decision_ref",
    "proposal_source", "base_source", "expected_adoption", "requires_publication",
    "candidate_source", "edits", "preview"}
REQUEST_KEYS = {"schema", "request_id", "work_ref", "expected_commit", "expected_adoption",
                "proposal_source", "base_source", "candidate_sha256"}
MAX_BYTES = 262144


def _fail(reason="RECIPE_INVALID", *, conflict=False):
    raise p._Refusal(p.STATE_CONFLICT if conflict else p.STATE_NOT_DISPATCHED, reason)


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _lookup(value):
    _closed(value, {"schema", "action", "request_id", "work_ref"})
    if (value["schema"] != LOOKUP_SCHEMA or value["action"] != "ADOPT_PLAN"
            or type(value["request_id"]) is not str
            or re.fullmatch(r"mmos-project-adopt-[0-9a-f]{40}", value["request_id"]) is None
            or not p._valid_work_ref(value["work_ref"])):
        _fail("REQUEST_INVALID")
    return deepcopy(value)


def _source(ref):
    _closed(ref, {"repository", "commit", "path", "content_sha256"})
    if (ref["repository"] not in (p.REPOSITORY, "macro", "Mastermind", "mastermindx-market-intelligence/Mastermind")
            or not p._is_hex40(ref["commit"]) or not p._is_hex64(ref["content_sha256"])
            or type(ref["path"]) is not str or not p._valid_repo_path(ref["path"])
            or not ref["path"].endswith(".md")):
        _fail()


def _candidate_path(path, digest):
    return (type(path) is str and p._valid_repo_path(path)
        and not path.lower().startswith(("agentos/", ".git/"))
        and path.endswith(".candidate-" + digest[:20] + ".md"))


def validate_adoption_request(value):
    """Closed public selection before any source callback; grants nothing."""
    _closed(value, REQUEST_KEYS)
    _lookup({"schema": LOOKUP_SCHEMA, "action": "ADOPT_PLAN",
             "request_id": value["request_id"], "work_ref": value["work_ref"]})
    if (value["schema"] != "agentos.plan_adoption_request.v1"
            or not p._is_hex40(value["expected_commit"]) or not p._is_hex64(value["candidate_sha256"])):
        _fail("REQUEST_INVALID")
    for ref in (value["proposal_source"], value["base_source"]):
        _source(ref)
    if value["proposal_source"]["repository"] not in (p.REPOSITORY, "macro"):
        _fail("REQUEST_INVALID")
    prior = value["expected_adoption"]
    if prior is not None and (type(prior) is not str or re.fullmatch(r"DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*", prior) is None):
        _fail("REQUEST_INVALID")
    if len(_json(value)) > 32768:
        _fail("REQUEST_INVALID")
    return deepcopy(value)


def _targets(lookup, phase, images, *, predecessor=None, candidate_path=None, candidate_sha=None):
    paths = {image["path"] for image in images}
    if phase == "CANDIDATE":
        if len(images) != 1 or not _candidate_path(images[0]["path"], images[0]["content_sha256"]):
            _fail()
        if candidate_path is not None and paths != {candidate_path}:
            _fail()
    else:
        ws = "agentos/workstreams/" + lookup["work_ref"].replace(":", "-", 1) + ".md"
        dec = "agentos/decisions/DEC-PLAN-ADOPTION-" + lookup["request_id"][-40:].upper() + ".md"
        if not {ws, dec} <= paths or len(images) not in (2, 3):
            _fail()
        extras = paths - {ws, dec}
        if any(re.fullmatch(r"agentos/decisions/DEC-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md", path) is None for path in extras):
            _fail()
        if predecessor is not None:
            expected = set() if predecessor is False else {
                "agentos/decisions/" + predecessor.replace(":", "-", 1) + ".md"}
            if extras != expected:
                _fail()
        for image in images:
            if image["path"] == dec and image["expected_preimage_sha256"] is not None:
                _fail()
            if image["path"] != dec and image["expected_preimage_sha256"] is None:
                _fail()
            if image["path"] == ws and candidate_sha is not None and image["content_sha256"] != candidate_sha:
                _fail()


class PlanAdoptionGitMode:
    mode_name = "plan_adoption"
    allowed_phases = ("CANDIDATE", "ADOPTION")
    request_keys = REQUEST_KEYS
    action = "ADOPT_PLAN"
    lookup = staticmethod(_lookup)
    def __init__(self, publisher, *, authorize, stamp, load, claim):
        self.owner = publisher
        self.seams = {"authorize": authorize, "stamp": stamp, "load": load, "claim": claim}
        for name, seam in self.seams.items():
            if seam is not None:
                p._require_callable(seam, name)
        self.identities = {name: None if seam is None else p._callable_identity(seam)
                           for name, seam in self.seams.items()}

    def _check(self):
        if any(seam is None for seam in self.seams.values()):
            _fail("ADOPTION_SEAMS_ABSENT")
        if ({name: p._callable_identity(seam) for name, seam in self.seams.items()}
                != self.identities):
            _fail("SEAM_IDENTITY_CHANGED")

    def permission(self, principal, op):
        self._check()
        if self.seams["authorize"](principal, op.lookup["work_ref"]) is not True:
            _fail("UNAUTHORIZED")
        stamp = self.seams["stamp"](principal, op.lookup["work_ref"])
        if not p._is_hex64(stamp):
            _fail("PERMISSION_STAMP_INVALID")
        return stamp

    def _metadata(self, principal, lookup, phase, scope):
        value = self.seams["load"](principal, deepcopy(lookup), phase)
        if value is None:
            _fail("OPERATION_MISSING")
        _closed(value, {"schema", "selection", "principal_scope", "request_sha256",
            "recipe_fingerprint_sha256", "permission_binding_digest", "phase", "publication_binding"})
        if (value["schema"] != BINDING_SCHEMA or _lookup(value["selection"]) != lookup
                or value["principal_scope"] != scope or value["phase"] != phase
                or any(not p._is_hex64(value[k]) for k in ("request_sha256",
                    "recipe_fingerprint_sha256", "permission_binding_digest"))
                or value["request_sha256"] == value["recipe_fingerprint_sha256"]):
            _fail("OPERATION_CONFLICT", conflict=True)
        binding = _closed(value["publication_binding"], {"expected_commit", "postimages", "branch"})
        if (not p._is_hex40(binding["expected_commit"]) or type(binding["postimages"]) is not list
                or not 1 <= len(binding["postimages"]) <= 3):
            _fail()
        for image in binding["postimages"]:
            _closed(image, {"path", "content_sha256", "expected_preimage_sha256"})
            if (type(image["path"]) is not str or not p._valid_repo_path(image["path"])
                    or not p._is_hex64(image["content_sha256"])
                    or (image["expected_preimage_sha256"] is not None
                        and not p._is_hex64(image["expected_preimage_sha256"]))):
                _fail()
        if len({i["path"] for i in binding["postimages"]}) != len(binding["postimages"]):
            _fail()
        _targets(lookup, phase, binding["postimages"])
        branch = self.branch(lookup, scope, phase)
        if binding["branch"] not in (None, branch):
            _fail("OPERATION_CONFLICT", conflict=True)
        return deepcopy(value)

    @staticmethod
    def branch(lookup, scope, phase):
        return "mmos/plan-adopt-" + hashlib.sha256(_json({"principal_scope": scope,
            "request_id": lookup["request_id"], "phase": phase})).hexdigest()

    def prewrite(self, op):
        current = self._metadata(op.principal, op.original_lookup, op.adoption_phase, op.scope)
        if current != op.metadata or current["permission_binding_digest"] != op.stamp:
            _fail("OPERATION_CONFLICT", conflict=True)
        if self.seams["claim"](op.principal, deepcopy(op.original_lookup), op.claim, current) is not True:
            _fail("CLAIM_INVALID")

    def _recipe(self, request, recipe, op):
        validate_adoption_request(request)
        if (request["schema"] != "agentos.plan_adoption_request.v1"
                or request["request_id"] != op.original_lookup["request_id"]
                or request["work_ref"] != op.work_ref or not p._is_hex40(request["expected_commit"])
                or not p._is_hex64(request["candidate_sha256"])):
            _fail()
        for ref in (request["proposal_source"], request["base_source"]):
            _source(ref)
        if request["proposal_source"]["repository"] not in (p.REPOSITORY, "macro"):
            _fail()
        prior = request["expected_adoption"]
        if prior is not None and (type(prior) is not str or re.fullmatch(r"DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*", prior) is None):
            _fail()
        _closed(recipe, RECIPE_KEYS)
        expected_phase = "CANDIDATE" if op.adoption_phase == "CANDIDATE" else "ADOPTION_DECISION"
        candidate = request["proposal_source"]["path"][:-3] + ".candidate-" + request["candidate_sha256"][:20] + ".md"
        if (recipe["schema"] != "agentos.plan_adoption_recipe.v1" or recipe["status"] != "PREVIEW_ONLY"
                or recipe["phase"] != expected_phase or recipe["request_id"] != request["request_id"]
                or recipe["work_ref"] != request["work_ref"]
                or recipe["request_sha256"] != op.recipe_fingerprint
                or hashlib.sha256(_json(request)).hexdigest() != op.request_sha256
                or recipe["expected_commit"] != op.expected_commit
                or (op.adoption_phase == "CANDIDATE" and request["expected_commit"] != op.expected_commit)
                or recipe["candidate_path"] != candidate or not _candidate_path(candidate, request["candidate_sha256"])
                or recipe["candidate_sha256"] != request["candidate_sha256"]
                or recipe["proposal_source"] != request["proposal_source"]
                or recipe["base_source"] != request["base_source"] or recipe["expected_adoption"] != prior
                or recipe["decision_ref"] != "DEC:PLAN-ADOPTION-" + request["request_id"][-40:].upper()
                or type(recipe["edits"]) is not list or len(recipe["edits"]) > 3
                or type(recipe["requires_publication"]) is not bool):
            _fail("OPERATION_CONFLICT", conflict=True)
        images = op.metadata["publication_binding"]["postimages"]
        _targets(op.original_lookup, op.adoption_phase, images, predecessor=prior or False,
                 candidate_path=candidate, candidate_sha=request["candidate_sha256"])
        edits, total = {}, 0
        for edit in recipe["edits"]:
            _closed(edit, {"path", "mode", "expected_sha256", "content_utf8", "content_sha256"})
            if (type(edit["path"]) is not str or edit["path"] in edits or edit["mode"] != "100644"
                    or type(edit["content_utf8"]) is not str):
                _fail()
            raw = edit["content_utf8"].encode("utf-8")
            total += len(raw)
            if hashlib.sha256(raw).hexdigest() != edit["content_sha256"] or total > MAX_BYTES:
                _fail()
            edits[edit["path"]] = edit
        if set(edits) - {image["path"] for image in images}:
            _fail()
        normalized = []
        ws = "agentos/workstreams/" + request["work_ref"].replace(":", "-", 1) + ".md"
        for image in images:
            edit = edits.get(image["path"])
            if edit is None:
                # The real compiler omits unchanged WS. It is STILL a logical
                # CAS/postimage obligation, read at the exact committed base.
                if (op.adoption_phase != "ADOPTION" or image["path"] != ws
                        or image["content_sha256"] != image["expected_preimage_sha256"]):
                    if not (op.adoption_phase == "CANDIDATE" and not recipe["requires_publication"]
                            and image["content_sha256"] == image["expected_preimage_sha256"]):
                        _fail()
                raw = self.owner._read_blob_at(op, op.expected_commit, image["path"])
                if raw is None or hashlib.sha256(raw).hexdigest() != image["content_sha256"]:
                    _fail("PREIMAGE_CONFLICT", conflict=True)
                content = raw.decode("utf-8")
            else:
                if (edit["content_sha256"] != image["content_sha256"]
                        or edit["expected_sha256"] != image["expected_preimage_sha256"]):
                    _fail("OPERATION_CONFLICT", conflict=True)
                content = edit["content_utf8"]
            normalized.append({**image, "content_utf8": content})
        return {"postimages": normalized, "request_fingerprint": op.recipe_fingerprint}

    def _observed(self, op, commit):
        binding = op.metadata["publication_binding"]
        return self.owner._default_carries_postimages(op, commit, binding)

    def _result(self, op, state, *, source=None, proposal=None, reason=None):
        if state in (p.STATE_SOURCE_PUBLISHED, p.STATE_PROPOSAL_PUBLISHED):
            self.owner._read_guard(op)
        if reason not in p.KNOWLEDGE_REASONS | {None, "ADOPTION_SEAMS_ABSENT"}:
            reason = "GIT_WRITE_UNKNOWN" if op.effects_started else "GIT_INVOCATION_FAILED"
        return {"schema": SCHEMA, "selection": deepcopy(getattr(op, "original_lookup", None)),
            "phase": getattr(op, "adoption_phase", None), "state": state,
            "recipe_fingerprint_sha256": op.recipe_fingerprint,
            "source": deepcopy(source), "proposal": deepcopy(proposal), "reason": reason, "retryable": False}

    def _published(self, op, commit):
        self.owner._read_guard(op)
        if self.owner._remote_branch_commit(op, self.owner._binding.default_branch) != commit:
            raise p._Unknown("REMOTE_BRANCH_UNVERIFIED")
        source = {"repository": p.REPOSITORY, "commit": commit, "postimages": [
            {"path": i["path"], "content_sha256": i["content_sha256"]}
            for i in op.metadata["publication_binding"]["postimages"]]}
        return self._result(op, p.STATE_SOURCE_PUBLISHED, source=source)

    def _reconcile(self, op, default):
        o = self.owner
        if self._observed(op, default):
            return self._published(op, default)
        binding = op.metadata["publication_binding"]
        local, remote = o._local_branch_commit(op, op.branch), o._remote_branch_commit(op, op.branch)
        for commit in set(filter(None, (local, remote))):
            if commit != local:
                fetched = o._git(["fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "origin", commit], op)
                if fetched.returncode != 0:
                    raise p._Unknown("REMOTE_BRANCH_UNVERIFIED")
            o._verify_knowledge_commit_payload(op, commit, binding["postimages"], op.lookup,
                                               op.recipe_fingerprint, op.expected_commit)
        receipt = o._lookup_pull_request(op, op.branch, op.request_sha256, remote or local)
        o._read_guard(op)
        if o._remote_branch_commit(op, op.branch) != remote or (receipt is not None and remote is None):
            raise p._Unknown("REMOTE_BRANCH_UNVERIFIED")
        if receipt is not None:
            return self._result(op, p.STATE_PROPOSAL_PUBLISHED, proposal=receipt)
        if local or remote:
            return self._result(op, p.STATE_PREPARED, reason="REMOTE_BRANCH_WITHOUT_PR" if remote else "LOCAL_ONLY")
        raise p._Unknown("NO_EXISTING_PUBLICATION")

    def operate(self, value, recipe, principal, *, phase, claim, reconcile=False):
        op = p._Operation(self.owner._binding)
        op.mode, op.adoption_phase = self.mode_name, phase
        # A reconciliation cannot prove that a prior attempted effect did NOT
        # occur merely because its current grant or read is unavailable.
        op.effects_started = reconcile
        try:
            self._check()
            if phase not in self.allowed_phases:
                _fail("REQUEST_INVALID")
            if reconcile:
                lookup = self.lookup(value)
            else:
                _closed(value, self.request_keys)
                lookup = self.lookup({"schema": LOOKUP_SCHEMA, "action": self.action,
                                   "request_id": value["request_id"], "work_ref": value["work_ref"]})
                if claim is None:
                    _fail("CLAIM_INVALID")
            op.original_lookup = lookup
            op.lookup = deepcopy(lookup)
            op.principal, op.scope, op.claim = principal, self.owner._principal_scope(principal), claim
            if not p._is_hex64(op.scope):
                _fail("UNAUTHORIZED")
            op.stamp = self.permission(principal, op)
            self.owner._require_seams()
            self.owner._require_qualifier()
            op.metadata = self._metadata(principal, lookup, phase, op.scope)
            if op.metadata["permission_binding_digest"] != op.stamp:
                _fail("AUTHORIZATION_REVOKED")
            op.expected_commit = op.metadata["publication_binding"]["expected_commit"]
            op.recipe_fingerprint = op.metadata["recipe_fingerprint_sha256"]
            op.context(op.metadata["request_sha256"], lookup["work_ref"], self.branch(lookup, op.scope, phase))
            op.lookup.update(request_sha256=op.request_sha256, source_commit=op.expected_commit, phase=phase)
            if self.owner._check_worktree(op) != "sha1":
                _fail("WORKTREE_INVALID")
            default = self.owner._resolve_default_commit(op)
            if reconcile:
                return self._reconcile(op, default)
            normalized = self._recipe(value, recipe, op)
            if self._observed(op, default):
                return self._published(op, default)
            if default != op.expected_commit:
                _fail("STALE_EXPECTED_COMMIT")
            self.owner._verify_knowledge_preimages_at_base(op, op.expected_commit, normalized["postimages"])
            self.prewrite(op)
            existing = self.owner._local_branch_commit(op, op.branch) or self.owner._remote_branch_commit(op, op.branch)
            receipt = self.owner._lookup_pull_request(op, op.branch, op.request_sha256, existing)
            if existing or receipt:
                op.effects_started = True
                return self._reconcile(op, default)
            commit = self.owner._build_knowledge_commit(op, normalized, op.lookup)
            commit = self.owner._claim_local_branch_knowledge(op, principal, op.stamp, commit, normalized, op.lookup)
            self.owner._push_knowledge_branch(op, principal, op.stamp, op.branch, commit, normalized, op.lookup)
            receipt = self.owner._ensure_pull_request_knowledge(op, principal, op.stamp, op.branch, op.lookup, commit)
            default = self.owner._resolve_default_commit(op)
            if self._observed(op, default):
                return self._published(op, default)
            return self._result(op, p.STATE_PROPOSAL_PUBLISHED, proposal=receipt)
        except p._Refusal as error:
            return self._result(op, p.STATE_EFFECT_UNKNOWN if op.effects_started and error.state == p.STATE_NOT_DISPATCHED else error.state, reason=error.reason)
        except p._Unknown as error:
            return self._result(op, p.STATE_EFFECT_UNKNOWN, reason=error.reason)
        except Exception:
            return self._result(op, p.STATE_EFFECT_UNKNOWN if op.effects_started else p.STATE_NOT_DISPATCHED,
                                reason="GIT_WRITE_UNKNOWN" if op.effects_started else "GIT_INVOCATION_FAILED")

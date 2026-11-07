"""Fixed ADOPT snapshot over the incumbent nominal canonical DATA view.

Only current same-work artifact association and exact captured Macro members
are read. Record SourceRefs never select another repository/network/root.
CODE remains the view's configured executable pin; DATA is never executed.
"""
from copy import deepcopy
import hashlib
from control_plane.project_canonical_data import CanonicalProjectDataView
from control_plane.project_plan_canonical_basis import capture_current_plan_basis, _git, _one
from control_plane.project_plan_adoption_git import validate_adoption_request


def _fail():
    raise ValueError("PLAN_ADOPTION_BASIS_UNAVAILABLE")


class _Record:
    def __init__(self, raw): self.raw = raw
    def read_text(self, *, encoding): return self.raw.decode(encoding)


def capture_plan_adoption_snapshot(view, *, request, phase):
    if type(view) is not CanonicalProjectDataView or phase not in ("CANDIDATE", "ADOPTION"):
        _fail()
    request = validate_adoption_request(request)
    work = request["work_ref"]
    with view.capture_scope():
        view._require_work(work)
        basis = capture_current_plan_basis(view, work_ref=work)
        material = basis.material()
        if phase == "CANDIDATE" and request["expected_commit"] != view.data_commit:
            _fail()
        if request["expected_adoption"] != material["base_adoption"] or request["base_source"] != material["base_source"]:
            _fail()
        ws = basis._snapshot["workstream"]
        record, _ = basis._owner.parse_record(_Record(ws["raw_bytes"]))
        source = request["proposal_source"]
        path = source["path"]
        if (source["repository"] != "mastermindx-market-intelligence/macro"
                or path not in (record.get("artifacts") or []) and "macro:" + path not in (record.get("artifacts") or [])):
            _fail()
        # Original immutable source must be in this same qualified ancestry;
        # current capture must still have the exact selected proposal bytes.
        _git(view, ["merge-base", "--is-ancestor", source["commit"], view.data_commit], maximum=2048)
        proposal = _one(view, view.data_commit, path)
        if any(proposal["source"][key] != source[key] for key in ("repository", "path", "content_sha256")):
            _fail()
        if phase == "CANDIDATE" and proposal["source"] != source:
            _fail()
        header, candidate = basis._owner.parse_project_plan_proposal(proposal["raw_bytes"], work_ref=work)
        if header["candidate_sha256"] != request["candidate_sha256"] or hashlib.sha256(candidate).hexdigest() != request["candidate_sha256"]:
            _fail()
        candidate_path = path[:-3] + ".candidate-" + request["candidate_sha256"][:20] + ".md"
        decision_path = "agentos/decisions/DEC-PLAN-ADOPTION-" + request["request_id"][-40:].upper() + ".md"

        def target(relative):
            listed = _git(view, ["ls-tree", "-z", view.data_commit, "--", relative], maximum=2048)
            if not listed: return {"path": relative, "state": "ABSENT"}
            return {"path": relative, "state": "CAPTURED", "capture": _one(view, view.data_commit, relative)}

        snapshot = {"schema": "agentos.plan_adoption_snapshot.v1", "repository": "mastermindx-market-intelligence/macro",
            "commit": view.data_commit, "workstream": deepcopy(ws), "decisions": deepcopy(basis._snapshot["decisions"]),
            "proposal": proposal, "base": deepcopy(basis._snapshot["base"]),
            "candidate_target": target(candidate_path), "decision_target": target(decision_path)}
        basis.check(); view.check()
        return {"snapshot": snapshot, "canonical_data": view.witness()}

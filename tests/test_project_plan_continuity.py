"""Real captured Agent OS owner joins; synthetic records, no live source access."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zlib

import pytest

from control_plane.project_plan_continuity import project_captured_continuity


MACRO = "mastermindx-market-intelligence/macro"
HEAD = "a" * 40
WORK = "WS:PLAN-TEST"


@pytest.fixture
def owner(tmp_path):
    # Immutable actual owner code, not a replacement parser or decoder shim.
    fixture = json.loads((Path(__file__).parent / "fixtures/agentos-project-plan-owner-contract.json").read_bytes())
    root = tmp_path / "captured-owner"
    for item in fixture["files"]:
        assert item["path"] in {"scripts/agentos.py", "scripts/agentos_project_plan_contract.py"}
        source = zlib.decompress(base64.b64decode(item["zlib_base64"], validate=True))
        assert hashlib.sha256(source).hexdigest() == item["sha256"]
        assert hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest() == item["blob"]
        target = root / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source)
    spec = importlib.util.spec_from_file_location("continuity_real_owner", root / "scripts/agentos.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    prior_path = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = prior_path
    return module


def capture(path, raw, commit=HEAD, repository=MACRO):
    return {"source": {"repository": repository, "path": path, "commit": commit,
                       "content_sha256": hashlib.sha256(raw).hexdigest()}, "raw_bytes": raw}


def record(owner, path, value):
    return capture(path, owner._yaml_frontmatter(value).encode() + b"\nRecord body is not a projection.\n")


def decision(key, adopted_source, *, predecessor=None, proposal_source=None):
    result = {"key": key, "question": "Which exact plan content?", "answer": "The recorded bytes.",
              "rationale": "An explicit fixture decision.", "alternatives": [{"option": "Infer", "why_not": "No."}],
              "evidence": ["Fixture"], "affects": [WORK], "confidence": "high", "reversibility": "easy",
              "decided_by": "fixture-owner", "decided_at": "2026-11-04",
              "project_plan_adoption": {"schema": "agentos.project_plan_adoption.v1", "work_ref": WORK,
                                        "adopted_source": adopted_source, "predecessor": predecessor,
                                        "proposal_source": proposal_source, "display_revision": None}}
    if predecessor:
        result["supersedes"] = [predecessor]
    return result


def inputs(owner):
    baseline = capture("planning/base.md", b"# Recorded baseline\n", "b" * 40)
    candidate = b"# Improved candidate\n"
    header = {"schema": "agentos.project_plan_proposal.v1", "proposal_id": "PLAN-PROPOSAL", "work_ref": WORK,
              "base_adoption": "DEC:PLAN-FIRST", "base_source": baseline["source"],
              "candidate_sha256": hashlib.sha256(candidate).hexdigest(), "rationale": "A concrete proposed change.",
              "evidence": []}
    proposal = capture("planning/proposal.md", owner._yaml_frontmatter(header).encode() + candidate)
    ws = {"key": "PLAN-TEST", "title": "Plan fixture", "objective": "Deliver actual content.", "status": "active",
          "program": "executive-os", "repos": ["macro"], "owner": "ceo", "class": "build",
          "blast_radius": "user_facing", "ambiguity": "scoped", "waves": [{"id": "W0", "title": "Read", "status": "todo"}],
          "next_action": "Read the recorded content.", "artifacts": ["macro:planning/proposal.md"]}
    dec = decision("PLAN-FIRST", baseline["source"])
    kwargs = dict(owner=owner, work_ref=WORK, qualified_commits={MACRO: HEAD},
                  workstream_capture=record(owner, "agentos/workstreams/WS-PLAN-TEST.md", ws),
                  decision_captures=[record(owner, "agentos/decisions/DEC-PLAN-FIRST.md", dec)],
                  proposal_captures=[proposal], content_captures=[baseline])
    return kwargs, baseline, proposal, header, candidate, ws, dec


def test_actual_owner_and_captured_bodies_produce_adoption_and_pending_comparison(owner):
    kwargs, baseline, proposal, *_ = inputs(owner)
    value = project_captured_continuity(**kwargs)
    assert value["adoption"]["state"] == "AVAILABLE"
    assert value["adoption"]["content"] == baseline["raw_bytes"].decode()
    assert value["adoption"]["decided_at"] == "2026-11-04"
    item = value["proposals"]["items"][0]
    assert item["proposal_source"] == proposal["source"]
    assert item["state"] == "RECORDED_PROPOSAL"
    assert item["adoption_relation"] == "UNASSOCIATED_WITH_CURRENT_DECISION"
    assert item["comparison"]["state"] == "AVAILABLE"
    assert item["comparison_basis"] == "ADOPTED_CONTENT"
    assert "Record body" not in json.dumps(value)


def test_without_typed_decision_only_recorded_comparison_is_available(owner):
    kwargs, _, proposal, header, candidate, *_ = inputs(owner)
    kwargs["decision_captures"] = []
    header["base_adoption"] = None
    kwargs["proposal_captures"] = [capture(proposal["source"]["path"], owner._yaml_frontmatter(header).encode() + candidate)]
    value = project_captured_continuity(**kwargs)
    assert value["adoption"] == {"state": "UNAVAILABLE", "reason": "NOT_DECLARED"}
    assert value["proposals"]["items"][0]["comparison_basis"] == "RECORDED_SOURCE"
    assert value["proposals"]["items"][0]["comparison"]["state"] == "AVAILABLE"


def test_missing_body_never_becomes_available_from_digest_metadata(owner):
    kwargs, *_ = inputs(owner)
    kwargs["content_captures"] = []
    value = project_captured_continuity(**kwargs)
    assert value["adoption"]["state"] == "UNAVAILABLE"
    assert value["adoption"]["reason"] == "SOURCE_UNAVAILABLE"
    assert "declared_decision" in value["adoption"]
    assert value["proposals"]["items"][0]["comparison"]["state"] == "UNAVAILABLE"
    assert value["proposals"]["items"][0]["comparison_basis"] == "DECLARED_ADOPTION_SOURCE"


def test_stale_pending_proposal_is_not_compared_as_current(owner):
    kwargs, _, proposal, header, candidate, *_ = inputs(owner)
    header["base_adoption"] = "DEC:OTHER-BASE"
    kwargs["proposal_captures"] = [capture(proposal["source"]["path"], owner._yaml_frontmatter(header).encode() + candidate)]
    item = project_captured_continuity(**kwargs)["proposals"]["items"][0]
    assert item["comparison"] == {"state": "UNAVAILABLE", "reason": "STALE_PREDECESSOR"}


@pytest.mark.parametrize("failure", ["bytes", "unqualified_repo", "source_commit", "unassociated", "scope"])
def test_tampered_or_unqualified_capture_fails_closed_without_external_resolution(owner, failure):
    kwargs, baseline, proposal, _, _, ws, _ = inputs(owner)
    if failure == "bytes":
        kwargs["content_captures"][0]["raw_bytes"] = b"SECRET corrupted content"
    elif failure == "unqualified_repo":
        kwargs["content_captures"] = [capture("private.md", b"SECRET", repository="mastermindx-market-intelligence/Mastermind")]
    elif failure == "source_commit":
        kwargs["workstream_capture"]["source"]["commit"] = "c" * 40
    elif failure == "unassociated":
        ws["artifacts"] = []
        kwargs["workstream_capture"] = record(owner, "agentos/workstreams/WS-PLAN-TEST.md", ws)
    else:
        kwargs["work_ref"] = "WS:FOREIGN"
    value = project_captured_continuity(**kwargs)
    assert value["adoption"] == {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE"}
    assert "SECRET" not in json.dumps(value)


def test_missing_lineage_never_falls_back_to_null_adoption(owner):
    kwargs, baseline, _, _, _, _, dec = inputs(owner)
    dec["project_plan_adoption"]["predecessor"] = "DEC:MISSING-BASE"
    dec["supersedes"] = ["DEC:MISSING-BASE"]
    kwargs["decision_captures"] = [record(owner, "agentos/decisions/DEC-PLAN-FIRST.md", dec)]
    value = project_captured_continuity(**kwargs)
    assert value["adoption"]["reason"] == "LINEAGE_INVALID"
    assert value["proposals"]["reason"] == "LINEAGE_INVALID"


def test_duplicate_proposal_identity_is_not_timestamp_elected(owner):
    kwargs, _, proposal, _, _, ws, _ = inputs(owner)
    other = capture("planning/other.md", proposal["raw_bytes"])
    ws["artifacts"].append("macro:planning/other.md")
    kwargs["workstream_capture"] = record(owner, "agentos/workstreams/WS-PLAN-TEST.md", ws)
    kwargs["proposal_captures"].append(other)
    assert project_captured_continuity(**kwargs)["proposals"] == {
        "state": "UNAVAILABLE", "reason": "RECORD_INVALID", "coverage": "CAPTURED_ASSOCIATIONS_ONLY"}


def test_current_decision_referenced_proposal_compares_its_real_predecessor(owner):
    kwargs, baseline, proposal, _, candidate, _, first = inputs(owner)
    adopted = capture("planning/adopted.md", candidate, "c" * 40)
    first["superseded_by"] = "DEC:PLAN-SECOND"
    second = decision("PLAN-SECOND", adopted["source"], predecessor="DEC:PLAN-FIRST", proposal_source=proposal["source"])
    kwargs["decision_captures"] = [record(owner, "agentos/decisions/DEC-PLAN-FIRST.md", first),
                                   record(owner, "agentos/decisions/DEC-PLAN-SECOND.md", second)]
    kwargs["content_captures"].append(adopted)
    value = project_captured_continuity(**kwargs)
    assert value["adoption"]["state"] == "AVAILABLE"
    assert value["adoption"]["decision_ref"] == "DEC:PLAN-SECOND"
    item = value["proposals"]["items"][0]
    assert item["adoption_relation"] == "CURRENT_DECISION_REFERENCES_PROPOSAL"
    assert item["comparison_basis"] == "RECORDED_PREDECESSOR"
    assert item["comparison"]["state"] == "AVAILABLE"
    # A different adopted body cannot be substantiated by this proposal.
    other = capture("planning/adopted.md", b"Different adopted bytes\n", "c" * 40)
    second["project_plan_adoption"]["adopted_source"] = other["source"]
    kwargs["decision_captures"][1] = record(owner, "agentos/decisions/DEC-PLAN-SECOND.md", second)
    kwargs["content_captures"] = [baseline, other]
    bad = project_captured_continuity(**kwargs)
    assert bad["adoption"]["reason"] == "PROPOSAL_MISMATCH"
    assert bad["proposals"]["items"][0]["comparison"]["state"] == "UNAVAILABLE"


def test_conflicting_capture_identity_and_result_budget_are_closed(owner):
    kwargs, baseline, *_ = inputs(owner)
    kwargs["content_captures"].append(capture(baseline["source"]["path"], b"Different bytes", "b" * 40))
    assert project_captured_continuity(**kwargs)["adoption"]["state"] == "UNAVAILABLE"
    kwargs, _, _, _, _, _, dec = inputs(owner)
    big = capture("planning/base.md", b"x" * 130000, "b" * 40)
    dec["project_plan_adoption"]["adopted_source"] = big["source"]
    kwargs["decision_captures"] = [record(owner, "agentos/decisions/DEC-PLAN-FIRST.md", dec)]
    kwargs["content_captures"] = [big]
    kwargs["proposal_captures"] = []
    value = project_captured_continuity(**kwargs)
    assert value["adoption"]["reason"] == "CONTENT_OVER_BUDGET"
    assert len(json.dumps(value).encode()) < 131072

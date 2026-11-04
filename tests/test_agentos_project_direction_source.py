"""Actual captured Macro parser/helper bytes with an inert bounded Git facade."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

import pytest

from common import workspace_project_direction_contract as wire
from control_plane.agentos_project_direction import AgentOsProjectDirectionReader, DirectionSourceUnavailable, read_from_macro_owner

WORK = "WS:DIRECTION-TEST"
PATH = "agentos/workstreams/WS-DIRECTION-TEST.md"
WS = """---
key: DIRECTION-TEST
title: Source-backed programme
objective: An authored objective is not accepted Direction.
status: active
program: executive-os
repos: [macro, mastermind]
owner: astra-meta-ceo
class: build
blast_radius: user_facing
ambiguity: scoped
waves:
  - id: ONE
    title: Deliver the original journey
    status: in_progress
next_action: Complete the actual journey.
decisions: [DEC:CURRENT]
accepted_direction: DEC:CURRENT
---
Private workstream body must not be projected.
"""


def decision(key, predecessor, successor=None):
    lineage = "" if predecessor is None else "supersedes: [" + predecessor + "]\n"
    if successor is not None:
        lineage += "superseded_by: " + successor + "\n"
    return """---
key: """ + key + """
question: Which outcome is the accepted Direction?
answer: """ + ("Complete the original journey" if key == "CURRENT" else "An explicit earlier Direction") + """
rationale: The delegated principal explicitly recorded this decision.
alternatives:
  - option: Infer acceptance from objective or Git history
    why_not: These are different source facts.
evidence: [Inert source fixture only]
affects: [WS:DIRECTION-TEST]
confidence: high
reversibility: easy
decided_by: fixture-principal
decided_at: 2026-11-04
direction:
  schema: agentos.direction_acceptance.v1
  state: ACCEPTED
  work_ref: WS:DIRECTION-TEST
  predecessor: """ + ("null" if predecessor is None else predecessor) + "\n" + lineage + "---\nPRIVATE_DEC_BODY_AND_PATHS_MUST_NOT_LEAK\n"


@pytest.fixture
def direction_git():
    fixture = json.loads((Path(__file__).parent / "fixtures/agentos-direction-owner.json").read_bytes())
    files = {}
    for path, item in fixture["files"].items():
        raw = zlib.decompress(base64.b64decode(item["zlib_base64"], validate=True))
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        files[path] = raw.decode()
    files.update({PATH: WS, "agentos/decisions/DEC-CURRENT.md": decision("CURRENT", "DEC:PREVIOUS"),
                  "agentos/decisions/DEC-PREVIOUS.md": decision("PREVIOUS", None, "DEC:CURRENT")})
    calls = []
    def runner(argv, **bounds):
        calls.append((argv, bounds))
        args = argv[5:]
        if args == ["rev-parse", "HEAD"]:
            result = fixture["commit"] + "\n"
        elif args[:3] == ["ls-tree", "-z", fixture["commit"]]:
            path = args[-1]
            result = "100644 blob " + "b" * 40 + "\t" + path + "\0" if path in files else ""
        elif args[0] == "show" and args[1].startswith(fixture["commit"] + ":"):
            result = files[args[1][41:]]
        else:
            pytest.fail("Unexpected source operation")
        return {"code": 0, "stdout": result, "timed_out": False, "limit_exceeded": False, "invalid_utf8": False}
    return fixture["commit"], files, calls, runner


def read(source, runner=None):
    commit, _files, _calls, default = source
    return read_from_macro_owner(macro_root=Path("/qualified/macro"), expected_macro_sha=commit,
                                 work_ref=WORK, runner=runner or default)


def test_actual_owner_parser_and_direction_contract_join_two_records(direction_git):
    value = read(direction_git)
    assert value["availability"] == "AVAILABLE", value
    current, history = value["direction"]["current"], value["direction"]["history"]
    assert current["decision_ref"] == "DEC:CURRENT" and current["answer"] == "Complete the original journey"
    assert current["date_precision"] == "DAY" and current["decided_at"] == "2026-11-04"
    assert history["revisions"][0]["decision_ref"] == "DEC:PREVIOUS" and history["total_count"] == 2
    assert history["has_more"] is False
    encoded = json.dumps(value)
    assert "Private workstream" not in encoded and "PRIVATE_DEC_BODY" not in encoded and "authored objective" not in encoded
    assert current["source"]["content_sha256"] == hashlib.sha256(direction_git[1]["agentos/decisions/DEC-CURRENT.md"].encode()).hexdigest()
    assert all(0 < bound["timeout"] <= 10 and bound["max_bytes"] <= 1048576 for _, bound in direction_git[2])


@pytest.mark.parametrize("change,reason", [
    ("absent", "NOT_DECLARED"), ("generic_decision", "RECORD_INVALID"),
    ("cross_work", "RECORD_INVALID"), ("missing_previous", "RECORD_NOT_FOUND"),
    ("broken_reciprocal", "LINEAGE_CONFLICT"), ("cycle", "LINEAGE_CONFLICT"),
    ("symlink", "RECORD_INVALID"), ("changed_before", "SOURCE_CHANGED"),
    ("changed_after", "SOURCE_CHANGED"), ("over_budget", "SOURCE_UNAVAILABLE"),
])
def test_explicit_binding_lineage_and_capture_negative_cases(direction_git, change, reason):
    commit, files, _, original = direction_git
    if change == "absent": files[PATH] = WS.replace("accepted_direction: DEC:CURRENT\n", "")
    if change == "generic_decision": files["agentos/decisions/DEC-CURRENT.md"] = decision("CURRENT", "DEC:PREVIOUS").replace("schema: agentos.direction_acceptance.v1", "schema: agentos.project_plan_adoption.v1")
    if change == "cross_work": files["agentos/decisions/DEC-CURRENT.md"] = decision("CURRENT", "DEC:PREVIOUS").replace("work_ref: WS:DIRECTION-TEST", "work_ref: WS:OTHER")
    if change == "missing_previous": files.pop("agentos/decisions/DEC-PREVIOUS.md")
    if change == "broken_reciprocal": files["agentos/decisions/DEC-PREVIOUS.md"] = decision("PREVIOUS", None, "DEC:OTHER")
    if change == "cycle": files["agentos/decisions/DEC-PREVIOUS.md"] = decision("PREVIOUS", "DEC:CURRENT", "DEC:CURRENT")
    heads = [0]
    def runner(argv, **bounds):
        result = original(argv, **bounds); args = argv[5:]
        if args == ["rev-parse", "HEAD"]:
            heads[0] += 1
            if change == "changed_before" or change == "changed_after" and heads[0] == 2: result["stdout"] = "b" * 40
        if change == "symlink" and args[0] == "ls-tree" and args[-1].endswith("DEC-CURRENT.md"):
            result["stdout"] = result["stdout"].replace("100644", "120000")
        if change == "over_budget" and args[0] == "show": result["limit_exceeded"] = True
        return result
    value = read(direction_git, runner)
    assert value == wire.unavailable(WORK, reason)


def test_unissued_source_reader_cannot_choose_a_repository():
    with pytest.raises(DirectionSourceUnavailable, match="^SOURCE_UNAVAILABLE$"):
        AgentOsProjectDirectionReader(macro_root=Path("/qualified/macro")).read(work_ref=WORK)


def test_public_selection_has_no_history_revision_path_or_job_selector(direction_git):
    for extra in ("commit", "path", "root_job_id", "history_revision", "direction_ref"):
        with pytest.raises(ValueError): wire.selection({"work_ref": WORK, extra: "caller-selected"})
    assert direction_git[2] == []

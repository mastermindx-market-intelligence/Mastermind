"""Actual qualified Macro owner parser, bounded Git facade; no provider or host effects."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

import pytest

from control_plane.agentos_project_plan import (_HISTORY_BATCH_BYTES,
    AgentOsProjectPlanReader, ProjectPlanSourceUnavailable, read_from_macro_owner)

SHA = "a" * 40
WORK = "WS:ONE"
PATH = "agentos/workstreams/WS-ONE.md"
RECORD = """---
key: ONE
title: An actual authored plan
objective: Deliver the real owner content.
status: active
program: executive-os
repos: [macro]
owner: ceo
class: build
blast_radius: user_facing
ambiguity: scoped
waves:
  - id: first
    title: Qualify the source
    status: in_progress
  - id: second
    title: Deliver the result
    status: todo
    depends_on: [first]
next_action: Qualify the source.
---
Private body must not become public plan content.
"""
BLOB = RECORD.encode("utf-8")
# Commit selectors and blob identities are distinct source facts.
REV = "c" * 40
BLOB_OID = hashlib.sha1(b"blob " + str(len(BLOB)).encode() + b"\0" + BLOB).hexdigest()


@pytest.fixture
def source_git():
    fixture = json.loads((Path(__file__).parent / "fixtures/agentos-project-plan-parser-ed12006d.json").read_bytes())
    source = zlib.decompress(base64.b64decode(fixture["zlib_base64"], validate=True))
    assert hashlib.sha256(source).hexdigest() == fixture["sha256"] == "eb9b9b628118bfec4a3f2e1a31fa9246798611cfda3093947aee46f27b430025"
    assert hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest() == fixture["blob"]
    calls = []
    def runner(argv, **limits):
        calls.append((argv, limits))
        command = argv[5:]
        if command == ["rev-parse", "HEAD"]:
            text = SHA + "\n"
        elif command == ["ls-tree", "-z", SHA, "--", PATH]:
            text = "100644 blob " + "b" * 40 + "\t" + PATH + "\0"
        elif command == ["show", SHA + ":" + PATH]:
            text = RECORD
        elif command == ["show", SHA + ":scripts/agentos.py"]:
            text = source.decode()
        elif command == ["log", "--max-count=8", "--format=%H%x00%cI%x00", SHA, "--", PATH]:
            text = REV + "\x00" + "2026-11-03T00:00:00Z" + "\x00\n"
        elif command == ["cat-file", "--batch"]:
            request = (REV + ":" + PATH + "\n").encode("utf-8")
            if limits.get("input_bytes") != request:
                pytest.fail("Unexpected history batch request: " + repr(limits.get("input_bytes")))
            text = BLOB_OID + " blob " + str(len(BLOB)) + "\n" + RECORD + "\n"
        else:
            pytest.fail("Unexpected source operation: " + repr(command))
        return dict(code=0, stdout=text, timed_out=False, limit_exceeded=False, invalid_utf8=False)
    return runner, calls


def read(runner):
    return read_from_macro_owner(macro_root=Path("/qualified/macro"),
        expected_macro_sha=SHA, work_ref=WORK, runner=runner)


def test_actual_macro_parser_and_validator_produce_real_fields(source_git):
    runner, calls = source_git
    value = read(runner)
    assert value["availability"] == "AVAILABLE"
    assert value["plan"]["objective"] == "Deliver the real owner content."
    assert [wave["id"] for wave in value["plan"]["waves"]] == ["first", "second"]
    assert value["plan"]["waves"][1]["depends_on"] == ["first"]
    assert "Private body" not in json.dumps(value)
    assert value["source"]["content_sha256"] == hashlib.sha256(RECORD.encode()).hexdigest()
    assert value["plan"]["version_history"]["kind"] == "GIT_RECORD_REVISIONS"
    assert value["plan"]["version_history"]["revisions"][0]["commit"] == REV
    assert value["plan"]["version_history"]["revisions"][0]["committed_at"] == "2026-11-03T00:00:00Z"
    assert value["plan"]["version_history"]["revisions"][0]["content_sha256"] == hashlib.sha256(BLOB).hexdigest()
    assert all(0 < limits["timeout"] <= 10 for _, limits in calls)
    # Only the one request-local history batch may exceed the per-read bound.
    assert all(limits["max_bytes"] <= 1048576 for _, limits in calls if limits.get("input_bytes") is None)
    assert [limits["max_bytes"] for _, limits in calls if limits.get("input_bytes") is not None] == [_HISTORY_BATCH_BYTES]


@pytest.mark.parametrize("failure,expected", [
    ("head", "SOURCE_CHANGED"), ("missing", "RECORD_NOT_FOUND"),
    ("symlink", "RECORD_INVALID"), ("invalid_record", "RECORD_INVALID"),
    ("changed_after", "SOURCE_CHANGED"), ("limit", "SOURCE_UNAVAILABLE"),
])
def test_source_drift_absence_and_invalid_owner_content_fail_closed(source_git, failure, expected):
    original, calls = source_git
    heads = [0]
    def runner(argv, **limits):
        response = original(argv, **limits)
        command = argv[5:]
        if command == ["rev-parse", "HEAD"]:
            heads[0] += 1
            if failure == "head" or failure == "changed_after" and heads[0] == 2:
                response["stdout"] = "b" * 40
        if command[0] == "ls-tree":
            if failure == "missing": response["stdout"] = ""
            if failure == "symlink": response["stdout"] = response["stdout"].replace("100644", "120000")
        if command == ["show", SHA + ":" + PATH]:
            if failure == "invalid_record": response["stdout"] = RECORD.replace("key: ONE", "key: OTHER")
            if failure == "limit": response["limit_exceeded"] = True
        return response
    value = read(runner)
    assert value["availability"] == "UNAVAILABLE"
    assert value["reason_codes"] == [expected]
    assert value["source"] is None and value["plan"] is None


def test_unissued_reader_cannot_supply_its_own_source_owner():
    with pytest.raises(ProjectPlanSourceUnavailable):
        AgentOsProjectPlanReader(macro_root=Path("/qualified/macro")).read(work_ref=WORK)


def test_missing_history_retains_available_actual_plan_content(source_git):
    original, calls = source_git
    def runner(argv, **limits):
        if argv[5] == "log":
            return dict(code=1, stdout="", timed_out=False, limit_exceeded=False, invalid_utf8=False)
        return original(argv, **limits)
    value = read(runner)
    assert value["availability"] == "AVAILABLE"
    assert value["plan"]["objective"] == "Deliver the real owner content."
    assert value["plan"]["version_history"] == {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE"}


def test_failed_history_batch_retains_available_actual_plan_content(source_git):
    original, calls = source_git
    def runner(argv, **limits):
        if argv[5] == "cat-file":
            request = (REV + ":" + PATH + "\n").encode("utf-8")
            assert limits.get("input_bytes") == request
            text = BLOB_OID + " blob " + str(len(BLOB)) + "\n" + RECORD + "\n"
            return dict(code=0, stdout=text, timed_out=False,
                limit_exceeded=False, invalid_utf8=True)
        return original(argv, **limits)
    value = read(runner)
    assert value["availability"] == "AVAILABLE"
    assert value["plan"]["objective"] == "Deliver the real owner content."
    assert value["plan"]["version_history"] == {"state": "UNAVAILABLE", "reason": "SOURCE_UNAVAILABLE"}


def test_frontend_wire_fixture_is_actual_bounded_macro_parser_output(source_git):
    path = Path(__file__).resolve().parents[1] / "app/mastermind_os/src/fixtures/project-plan-canonical-owner.json"
    assert json.loads(path.read_bytes()) == read(source_git[0])

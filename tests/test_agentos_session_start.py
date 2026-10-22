import hashlib
import io
import json

import pytest

from integrations.session_bridge import agentos_session_start as hook
from ops.fabric_launch.context import LaunchInputError


@pytest.fixture
def focused(tmp_path):
    workspace = tmp_path / "assigned workspace"
    workspace.mkdir()
    owner = tmp_path / "macro owner"
    owner.mkdir()
    event = {"hook_event_name": "SessionStart", "source": "startup",
             "session_id": "original-session", "cwd": str(workspace),
             "transcript_path": "/must/not/read/private.jsonl"}
    bundle = {"schema": "context_bundle.v1", "target": {"workstream": "WS:FIXTURE"},
              "no_answer_reason": None,
              "sections": [{"id": "workstream", "items": [
                  "Objective: finish project", "Constraint: preserve active child",
                  "Accepted: do not redo phase one", "Next: review phase two"]}],
              "degraded": ["current runtime ownership was not acquired"],
              "excluded": ["sibling project"], "omitted_due_to_budget": ["old optional note"]}
    calls = []
    def reader(workstream, budget, *, owner_root):
        calls.append((workstream, budget, owner_root))
        raw = (json.dumps(bundle, indent=2) + "\n").encode()
        observation = {"owner": "agent_os", "workstream": "WS:FIXTURE",
                       "bundle_sha256": hashlib.sha256(raw).hexdigest(),
                       "source_script_sha256": "a" * 64, "execution_authority": False}
        return raw, observation
    options = {"workspace_root": workspace, "workstream": "WS:FIXTURE",
               "owner_root": owner, "reader": reader}
    return event, bundle, calls, options, reader


@pytest.mark.parametrize("source", sorted(hook.SOURCES))
def test_native_sources_receive_complete_owner_context(focused, source):
    event, bundle, calls, options, _ = focused
    event["source"] = source
    result = hook.session_start_context(event, **options)
    assert set(result) == {"hookSpecificOutput"}
    assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    text = result["hookSpecificOutput"]["additionalContext"]
    assert text.endswith(json.dumps(bundle, indent=2) + "\n")
    assert "Constraint: preserve active child" in text
    assert "Accepted: do not redo phase one" in text
    assert '"parent_custody": "UNOBSERVED"' in text
    assert "private.jsonl" not in text
    assert calls == [("WS:FIXTURE", 4000, options["owner_root"])]


def test_sibling_workspace_does_not_acquire_or_inject(focused, tmp_path):
    event, _, calls, options, _ = focused
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    event["cwd"] = str(sibling)
    assert hook.session_start_context(event, **options) == {}
    assert calls == []


def test_compact_rereads_changed_decision_without_cached_or_duplicate_work(focused):
    event, bundle, calls, options, _ = focused
    first = hook.session_start_context(event, **options)
    bundle["sections"][0]["items"].append("Current decision: use revised acceptance")
    event["source"] = "compact"
    second = hook.session_start_context(event, **options)
    assert len(calls) == 2
    assert "revised acceptance" not in first["hookSpecificOutput"]["additionalContext"]
    assert "revised acceptance" in second["hookSpecificOutput"]["additionalContext"]
    assert "do not redo phase one" in second["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("field,value", [("target", {"workstream": "WS:OTHER"}),
    ("no_answer_reason", "unknown project"), ("omitted_due_to_budget", None)])
def test_wrong_target_or_missing_accounting_never_supplies_a_bundle(focused, field, value):
    event, bundle, calls, options, _ = focused
    bundle[field] = value
    text = hook.session_start_context(event, **options)["hookSpecificOutput"]["additionalContext"]
    assert "No project bundle was supplied" in text
    assert "finish project" not in text
    assert len(calls) == 1


def test_oversize_mandatory_context_is_explicitly_refused_without_clipping(focused):
    event, bundle, _, options, _ = focused
    bundle["sections"][0]["items"].append("x" * hook.MAX_CONTEXT_BYTES)
    text = hook.session_start_context(event, **options)["hookSpecificOutput"]["additionalContext"]
    assert "AGENTOS_CONTEXT_DELIVERY_TOO_LARGE" in text
    assert "finish project" not in text
    assert len(text.encode()) < hook.MAX_CONTEXT_BYTES


@pytest.mark.parametrize("reason", ["AGENTOS_CONTEXT_READ_UNCERTAIN", "AGENTOS_CONTEXT_READ_TIMEOUT",
    "AGENTOS_CONTEXT_OUTPUT_LIMIT", "private exception includes secret=value"])
def test_failed_read_has_no_retry_and_sanitizes_diagnostics(focused, reason):
    event, _, calls, options, _ = focused
    def failed(*args, **kwargs):
        calls.append("one")
        raise LaunchInputError(reason)
    options["reader"] = failed
    text = hook.session_start_context(event, **options)["hookSpecificOutput"]["additionalContext"]
    assert calls == ["one"]
    assert "No project bundle was supplied" in text
    assert "secret=value" not in text


@pytest.mark.parametrize("field,value", [("bundle_sha256", "b" * 64),
    ("execution_authority", True), ("workstream", "WS:OTHER")])
def test_acquisition_metadata_cannot_misbind_or_promote_authority(focused, field, value):
    event, _, _, options, reader = focused
    def changed(*args, **kwargs):
        raw, observation = reader(*args, **kwargs)
        observation[field] = value
        return raw, observation
    options["reader"] = changed
    text = hook.session_start_context(event, **options)["hookSpecificOutput"]["additionalContext"]
    assert "AGENTOS_READ_OBSERVATION_MISMATCH" in text
    assert "finish project" not in text


@pytest.mark.parametrize("field,value", [("source", "unknown"), ("session_id", ""),
    ("hook_event_name", "Stop"), ("cwd", "relative")])
def test_invalid_event_does_not_read_context(focused, field, value):
    event, _, calls, options, _ = focused
    event[field] = value
    with pytest.raises(LaunchInputError):
        hook.session_start_context(event, **options)
    assert calls == []


def test_cli_outputs_only_protocol_json_and_does_not_write_owner_state(focused):
    event, _, _, options, reader = focused
    before = list(options["owner_root"].iterdir())
    out, err = io.StringIO(), io.StringIO()
    code = hook.main(["--workspace-root", str(options["workspace_root"]),
                      "--workstream", options["workstream"],
                      "--macro-root", str(options["owner_root"])],
                     stdin=io.BytesIO(json.dumps(event).encode()),
                     stdout=out, stderr=err, reader=reader)
    assert code == 0 and not err.getvalue()
    assert "finish project" in json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
    assert list(options["owner_root"].iterdir()) == before


@pytest.mark.parametrize("raw", [b'not JSON', b'{"cwd":"a","cwd":"b"}',
    b'{"source": NaN}', b'x' * (hook.MAX_EVENT_BYTES + 1)])
def test_bad_stdin_is_inert_and_never_blocks_session(focused, raw):
    _, _, calls, options, reader = focused
    out, err = io.StringIO(), io.StringIO()
    assert hook.main(["--workspace-root", str(options["workspace_root"]),
                      "--workstream", options["workstream"]], stdin=io.BytesIO(raw),
                     stdout=out, stderr=err, reader=reader) == 0
    assert json.loads(out.getvalue()) == {} and err.getvalue()
    assert calls == []


@pytest.mark.parametrize("tail", [["--budget", "secret=" + "x" * 50000],
                                  ["--unknown", "secret=value"], ["--budget"]])
def test_invalid_cli_configuration_is_bounded_and_inert(focused, tail):
    _, _, calls, options, reader = focused
    out, err = io.StringIO(), io.StringIO()
    assert hook.main(["--workspace-root", str(options["workspace_root"]),
                      "--workstream", options["workstream"], *tail],
                     stdin=io.BytesIO(b''), stdout=out, stderr=err, reader=reader) == 0
    assert json.loads(out.getvalue()) == {}
    assert err.getvalue() == "SESSION_CONTEXT_ARGUMENTS_INVALID\n"
    assert calls == []

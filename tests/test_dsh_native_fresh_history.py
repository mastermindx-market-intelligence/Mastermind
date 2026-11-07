"""Native immutable-input history through the existing authenticated READ owner."""
import asyncio
import dataclasses
import hashlib
import json

import pytest

from common.project_conversation_read_contract import arguments
from control_plane.fresh_conversation import FreshConversationOwner
from tests.test_dsh_native_fresh_conversation import native_case, ready_send, frame
from tests.test_fresh_conversation import cleanup


def _selector(descriptor, *, turn_key=None, offset=0):
    return dict(kind="initial_input" if turn_key is None else "turn_input",
        **({} if turn_key is None else {"turn_key": turn_key}),
        source_event_id=descriptor["source_event_id"], source_event_sha256=descriptor["source_event_sha256"],
        sha256=descriptor["sha256"], offset_utf8=offset)


def _assembled(owner, principal, reference, descriptor, *, turn_key=None):
    text, offset = "", 0
    while True:
        selected = _selector(descriptor, turn_key=turn_key, offset=offset)
        result = owner.read_reference(principal, {**reference, "fragment": selected})
        assert result["schema"] == "mastermind.fresh_conversation_input_fragment.v1"
        assert result["fragment"] == selected and result["reference"] == reference
        raw = result["text"].encode("utf-8")
        assert 0 < len(raw) <= 4096
        assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= 28000
        text += result["text"]
        next_offset = result["next_offset_utf8"]
        if next_offset is None:
            assert offset + len(raw) == result["utf8_bytes"] == descriptor["utf8_bytes"]
            break
        assert next_offset == offset + len(raw) > offset
        offset = next_offset
    assert hashlib.sha256(text.encode()).hexdigest() == descriptor["sha256"]
    return text


@pytest.mark.parametrize("input_kind", ["unicode", "json_escaping"])
def test_native_maximum_input_and_followup_reopen_without_writer_or_operation_key(tmp_path, monkeypatch, input_kind):
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        initial = ("中😀 \n" * 14563 + "  \n X") if input_kind == "unicode" else (chr(34) + chr(92)) * 65536
        followup = " \n" * 3000 + "🪐" * 31267 + " End"
        assert len(initial.encode()) == len(followup.encode()) == 131072
        try:
            request = {**request, "message": initial}
            selected, send = await ready_send(owner, principal, request)
            send = {key: value for key, value in send.items() if key != "preview_digest"}
            send["message"] = followup
            preview = await frame(owner, principal, send, "turn_preview")
            assert preview["ok"], preview
            answer = await frame(owner, principal, {**send, "preview_digest": preview["data"]["preview_digest"]}, "turn")
            assert answer["ok"] and answer["data"]["state"] == "RECORDED", answer
            # New stateless reader, same canonical owners. No persisted opkey is supplied.
            reader = FreshConversationOwner(service, expected_policy=owner._expected_policy)
            before = runtime.events.list_events()
            catalogue = reader.project_references(principal, {"work_ref": request["work_ref"]})
            assert catalogue["schema"] == "mastermind.fresh_conversation_references.v2"
            row = catalogue["entries"][0]
            assert "initial_message" not in row and "operation_key" not in row["reference"]
            assert row["initial_input"]["utf8_bytes"] == 131072 and not row["initial_input"]["complete"]
            assert len(row["initial_input"]["preview"].encode()) <= 256
            reference = row["reference"]
            window = reader.read_reference(principal, reference)
            assert window["schema"] == "mastermind.fresh_conversation_window.v3"
            assert window["initial_input"] == row["initial_input"]
            assert window["initial_result"]["digest"] == send["initial_digest"]
            assert window["head_result"] == window["turns"][0]["result"] == answer["data"]["result"]
            assert window["turns"][0]["input"]["utf8_bytes"] == 131072
            assert not window["can_send"] and not window["parent_consumed"]
            assert "envelope" not in window["initial_result"]
            assert _assembled(reader, principal, reference, row["initial_input"]) == initial
            assert _assembled(reader, principal, reference, window["turns"][0]["input"], turn_key=send["turn_key"]) == followup
            # Exact source, UTF-8 scalar boundary and exclusive request-shape checks.
            fragment = _selector(row["initial_input"])
            if input_kind == "unicode":
                with pytest.raises(ValueError):
                    reader.read_reference(principal, {**reference, "fragment": {**fragment, "offset_utf8": 1}})
            for changed in ({**fragment, "offset_utf8": 131072},
                            {**fragment, "sha256": "0"*64}, {**fragment, "source_event_sha256": "0"*64},
                            {**fragment, "source_event_id": fragment["source_event_id"] + 1}):
                with pytest.raises(ValueError):
                    reader.read_reference(principal, {**reference, "fragment": changed})
            with pytest.raises(ValueError):
                reader.read_reference(dataclasses.replace(principal, subject_digest="f"*64), reference)
            with pytest.raises(ValueError):
                arguments({**reference, "fragment": fragment, "before_event_id": 99}, "fresh_read")
            assert runtime.events.list_events() == before
            assert adapters[0].calls == 2 and adapters[0].start_calls == len(adapters) == 1
            with pytest.raises(ValueError):
                runtime.store.unique_root_created_event(reference["root_job_id"], max_payload_bytes=1)
            import os
            output = os.environ.get("MMX_DSH_HISTORY_FIXTURE_OUTPUT")
            if output and input_kind == "unicode":
                from pathlib import Path
                with Path(output).open("x") as file:
                    json.dump(dict(schema="mastermind.native_fresh_history_fixture.v1",
                        catalogue=catalogue, window=window, initial_message=initial, followup_message=followup,
                        actual_counts=dict(jobs=2, attempts=1, native_turns=2, reader_added_events=0),
                        seams=["inert installed policy/process", "actual original Runtime/reader", "client transport is separately synthetic"]),
                        file, ensure_ascii=False, sort_keys=True, indent=2)
                    file.write("\n")
            # Quarantine blocks new writes but preserves cold original READ.
            service._service_state = "QUARANTINED"
            assert reader.read_reference(principal, reference)["initial_input"] == row["initial_input"]
            assert runtime.events.list_events() == before
        finally:
            await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("changed", [
    {"offset_utf8": True}, {"offset_utf8": -1}, {"offset_utf8": 131072},
    {"source_event_id": True}, {"source_event_id": 0}, {"source_event_id": 2**53},
    {"kind": "answer"}, {"path": "/tmp/foreign"}, {"turn_key": "unexpected"},
])
def test_native_fragment_closed_selector_rejects_unsafe_or_ambiguous_data(changed):
    reference = dict(schema="mastermind.fresh_conversation_reference.v1", work_ref="WS:ONE",
        root_job_id="JOB-1", root_event_id=1, root_event_sha256="a"*64, principal_scope_sha256="b"*64)
    fragment = dict(kind="initial_input", source_event_id=1, source_event_sha256="a"*64, sha256="c"*64, offset_utf8=0)
    with pytest.raises(ValueError):
        arguments({**reference, "fragment": {**fragment, **changed}}, "fresh_read")



@pytest.mark.parametrize("fault", ["ordinary", "wrong_input_digest", "different_copy", "mixed_project", "metadata_budget", "hard_cap"])
def test_large_root_allowance_requires_exact_native_source_and_bounded_metadata(tmp_path, monkeypatch, fault):
    import copy
    from common.fresh_conversation_contract import canonical_digest
    async def run():
        service, runtime, owner, principal, request, adapters = native_case(tmp_path, monkeypatch)
        request = {**request, "message": "x" * 131072}
        append = runtime.store.append_event
        def changed(connection, **kwargs):
            if kwargs["event_type"] == "JOB_CREATED" and "fresh_conversation_admission" in kwargs.get("payload", {}):
                payload = copy.deepcopy(kwargs["payload"])
                if fault == "ordinary":
                    payload.pop("fresh_conversation_admission")
                    payload["provenance"].pop("fresh_conversation")
                    payload["provenance"].pop("fresh_conversation_digest")
                    payload["oversized_ordinary_metadata"] = "x" * 65537
                elif fault == "wrong_input_digest":
                    for source in (payload["provenance"]["fresh_conversation"], payload["fresh_conversation_admission"]["source"]):
                        source["initial_message_sha256"] = "0" * 64
                    payload["provenance"]["fresh_conversation_digest"] = canonical_digest(payload["provenance"]["fresh_conversation"])
                    payload["fresh_conversation_admission"]["source_digest"] = canonical_digest(payload["fresh_conversation_admission"]["source"])
                elif fault == "different_copy":
                    payload["fresh_conversation_admission"]["source"]["initial_message"] = "y" * 131072
                elif fault == "mixed_project":
                    payload["project_execution_admission"] = {}
                else:
                    payload["unrelated_metadata"] = "x" * (65537 if fault == "metadata_budget" else 6 * 131072)
                kwargs = {**kwargs, "payload": payload}
            return append(connection, **kwargs)
        monkeypatch.setattr(runtime.store, "append_event", changed)
        try:
            preview = await frame(owner, principal, request, "preview")
            assert preview["ok"], preview
            result = await frame(owner, principal, {**request, "preview_digest": preview["data"]["preview"]["digest"]}, "create")
            assert not result["ok"]
            roots = [job for job in runtime.jobs.list_jobs() if job.parent_job_id is None]
            assert len(roots) == 1 and not adapters
            with pytest.raises(ValueError, match="original root unavailable or budget exceeded"):
                runtime.store.unique_root_created_event(roots[0].job_id)
        finally:
            await cleanup(service)
    asyncio.run(run())

"""Real temporary Runtime Events and incumbent reply reader; no live provider.

The existing continuation fixture supplies synthetic admitted native/carrier
facts. Catalogue ownership/root/request joins and observation finalization are
real. Synthetic retained metadata forks do not attest a live provider session.
"""
import asyncio
import copy
import dataclasses
import json
import os
from pathlib import Path

import pytest

from control_plane.native_continuation import _continue_key, _digest, _request_key
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.session_bridge.project_conversations import RuntimeProjectConversationsReader, validate_selection
from integrations.session_bridge.schemas import BridgeError
from integrations.slack_agent_dialogue.contract_v2 import build_message_v2
from tests.test_session_bridge_runtime_return import setup, bind, populate


def reader(s):
    return RuntimeProjectConversationsReader(s.owner)


def catalogue(s, principal=None, **arguments):
    return reader(s).catalogue(principal or s.projection,
        {"work_ref": s.binding.work_ref, **arguments}, guard=lambda: True)


def selection(page, index=0):
    row = page["conversations"][index]
    return {"work_ref": page["work_ref"], **{k: row[k] for k in
        ("conversation_ref", "revision", "requests")}}


def fork_record(s, *, native=False, foreign=False, work=None):
    """Retain another canonical original Event fixture, never a provider call."""
    original = s.runtime.events.list_events(aggregate_type="session_bridge_continue")[0]
    value = copy.deepcopy(original.payload)
    operation = "session-continue-" + _digest({"fixture": len(s.runtime.events.list_events()),
        "native": native, "foreign": foreign, "work": work})
    key = _request_key(operation)
    value.update(operation_key=operation, read_ref="session-reply-"+key,
                 request_message_key=_continue_key(operation))
    if native:
        value["generation"].update(session_epoch_id="retained-epoch-02", native_session_sha256="a"*64)
    if foreign:
        value["principal"]["subject_digest"] = "f"*64
    if work:
        value["context"]["work_ref"] = work
    with s.runtime.store.transaction() as connection:
        s.runtime.store.append_event(connection, aggregate_type="session_bridge_continue", aggregate_id=key,
            event_type="SESSION_BRIDGE_CONTINUE_REQUESTED", actor="executive-session-bridge",
            job_id=value["job_id"], attempt_id=value["attempt_id"], worker_id=value["worker_id"],
            payload=value, command_id="session-bridge-continue:"+key)


def test_real_catalogue_deduplicates_native_session_and_keeps_other_epoch_separate(setup):
    s=setup;bind(s)
    fork_record(s);fork_record(s,native=True);fork_record(s,foreign=True);fork_record(s,work="WS:OTHER")
    before=s.runtime.events.list_events()
    page=catalogue(s)
    assert len(page["conversations"])==2
    assert sorted(len(row["requests"]) for row in page["conversations"])==[1,2]
    assert len({row["conversation_ref"] for row in page["conversations"]})==2
    assert all(row["title"] is None for row in page["conversations"])
    assert page["coverage"]=="PARTIAL" and page["can_send"] is False
    assert not s.service.calls and s.runtime.events.list_events()==before
    assert "native_session_sha256" not in repr(page) and "target_ref" not in repr(page)


def test_real_owned_request_and_incumbent_qualified_reply_reopen_without_effect(setup):
    s=setup;populate(s);s.service.calls.clear()
    page=catalogue(s);chosen=selection(page)
    before=s.runtime.events.list_events()
    first=asyncio.run(reader(s).read(s.projection,chosen,guard=lambda:True))
    second=asyncio.run(reader(s).read(s.projection,chosen,guard=lambda:True))
    assert first==second and first["turns"][0]["state"]=="AVAILABLE"
    turn=first["turns"][0]
    assert turn["instruction"]==s.args["instruction"] and turn["stop_condition"]==s.args["stop_condition"]
    assert turn["reply"]["text"]=="The bounded finding is confirmed."
    assert turn["reply"]["parent_consumed"] is False and first["can_send"] is False
    assert s.runtime.events.list_events()==before
    assert all(call["operation"]=="read_thread" for call in s.service.calls)
    output=os.environ.get("MM_PROJECT_CONVERSATION_FIXTURE_OUTPUT")
    if output:
        Path(output).write_text(json.dumps({"catalogue":page,"selection":chosen,"read":first},ensure_ascii=False,indent=2)+"\n")


def test_uncommitted_native_turn_is_gap_not_raw_thread_or_guessed_text(setup):
    s=setup;bind(s)
    result=asyncio.run(reader(s).read(s.projection,selection(catalogue(s)),guard=lambda:True))
    assert result["turns"][0]["state"]=="UNAVAILABLE"
    assert all(result["turns"][0][key] is None for key in ("instruction","stop_condition","reply"))


def test_other_thread_messages_are_never_projected_as_owned_turn_content(setup):
    s=setup;populate(s)
    unrelated=copy.deepcopy(s.service.items[-1]["message"]);unrelated.pop("fingerprint")
    unrelated["message_key"]="asd-native-reply-"+"9"*40
    unrelated["body"]["completed"]="Other private thread content must remain absent."
    s.service.items.append({"message":build_message_v2(unrelated),"primary_ts":"1788000003.123456"})
    result=asyncio.run(reader(s).read(s.projection,selection(catalogue(s)),guard=lambda:True))
    assert result["turns"][0]["state"]=="AVAILABLE"
    assert "Other private thread content" not in repr(result)


def test_tampered_original_prompt_withholds_turn_instead_of_reconstructing_text(setup):
    s=setup;populate(s)
    request=copy.deepcopy(s.service.items[0]["message"]);request.pop("fingerprint")
    request["body"]["instruction"]="Changed prompt does not match the original input digest."
    s.service.items[0]["message"]=build_message_v2(request)
    result=asyncio.run(reader(s).read(s.projection,selection(catalogue(s)),guard=lambda:True))
    assert result["turns"][0]["state"]=="UNAVAILABLE"
    assert result["turns"][0]["instruction"] is None


@pytest.mark.parametrize("field",["subject_digest","client_ref","resource","issuer_digest"])
def test_foreign_principal_cannot_reopen_or_read_carrier(setup,field):
    s=setup;populate(s);chosen=selection(catalogue(s));s.service.calls.clear()
    value="https://foreign.test/mcp" if field=="resource" else "f"*64
    foreign=dataclasses.replace(s.projection,**{field:value})
    with pytest.raises(BridgeError):asyncio.run(reader(s).read(foreign,chosen,guard=lambda:True))
    assert not s.service.calls


@pytest.mark.parametrize("fault",["revision","conversation","request-revision","duplicate","extra","work"])
def test_changed_or_extra_selection_refused_before_carrier(setup,fault):
    s=setup;bind(s);chosen=selection(catalogue(s))
    if fault=="revision":chosen["revision"]="f"*64
    if fault=="conversation":chosen["conversation_ref"]="conversation-"+"f"*64
    if fault=="request-revision":chosen["requests"][0]["request_revision"]="f"*64
    if fault=="duplicate":chosen["requests"]*=2
    if fault=="extra":chosen["target_ref"]="codex:"+"a"*64
    if fault=="work":chosen["work_ref"]="WS:OTHER"
    with pytest.raises(BridgeError):asyncio.run(reader(s).read(s.projection,chosen,guard=lambda:True))
    assert not s.service.calls


def test_cross_native_turn_manifest_cannot_manufacture_conversation(setup):
    s=setup;bind(s);fork_record(s,native=True)
    page=catalogue(s);chosen=selection(page)
    chosen["requests"]+=page["conversations"][1]["requests"]
    chosen["revision"]=_digest({"conversation_ref":chosen["conversation_ref"],"requests":chosen["requests"]})
    with pytest.raises(BridgeError):asyncio.run(reader(s).read(s.projection,chosen,guard=lambda:True))
    assert not s.service.calls


def test_current_permission_withdrawal_during_read_withholds_entire_body(setup):
    s=setup;populate(s);chosen=selection(catalogue(s));current=[True]
    s.service.calls.clear()
    s.service.on_read=lambda:current.__setitem__(0,False)
    with pytest.raises(BridgeError):asyncio.run(reader(s).read(s.projection,chosen,guard=lambda:current[0]))
    assert len(s.service.calls)==1  # Not a later post-hoc refusal after more reads.


def test_private_source_replacement_during_read_cannot_retarget_later_ipc(setup):
    s=setup;populate(s);chosen=selection(catalogue(s));original_reader=reader(s)
    s.service.calls.clear();foreign=[]
    async def other(*args,**kwargs):foreign.append(args);raise AssertionError("must not call replaced source")
    s.service.on_read=lambda:setattr(s.owner,"service_call",other)
    with pytest.raises(BridgeError):asyncio.run(original_reader.read(s.projection,chosen,guard=lambda:True))
    assert len(s.service.calls)==1 and not foreign


def test_expired_read_principal_and_absent_host_guard_do_no_carrier_io(setup):
    s=setup;bind(s)
    with pytest.raises(BridgeError):catalogue(s,principal=dataclasses.replace(s.projection,expires_at=1))
    with pytest.raises(BridgeError):reader(s).catalogue(s.projection,{"work_ref":s.binding.work_ref},guard=lambda:False)
    assert not s.service.calls


def test_catalogue_cursor_is_original_principal_work_bound(setup):
    s=setup;bind(s);page=catalogue(s)
    if page["next_cursor"]:
        with pytest.raises(BridgeError):catalogue(s,work_ref="WS:OTHER",cursor=page["next_cursor"])
    assert not s.service.calls


def test_closed_selection_cannot_supply_principal_path_or_unbounded_turns(setup):
    s=setup;bind(s);chosen=selection(catalogue(s))
    for extra in ("principal","path","session_id","page_size"):
        with pytest.raises(BridgeError):validate_selection({**chosen,extra:"caller"})
    chosen["requests"]*=5
    with pytest.raises(BridgeError):validate_selection(chosen)

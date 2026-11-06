"""Native wire fixtures from actual signed BFF/Runtime projection code.

Only injected material readers/private peer are inert. No live target, Runtime,
provider, credentials, socket, enrollment or installed authority is claimed.
"""
import copy
import json
from pathlib import Path
from control_plane.native_continuation import _request_key
from tests.test_mastermind_os_session_transport import make_app,request,message_key
from tests.test_mastermind_os_session_transport import auth_fixture,rsa_key,NOW
from tests.test_session_bridge_runtime_owner import projector

def test_native_session_source_producer_and_signed_permissions(rsa_key):
    owner,_=projector()
    row=owner.list_targets()[0].public_projection()
    selection={k:row[k] for k in ("work_ref","root_job_id")}
    key=row["continuation_operation_key"]
    args={"target_ref":row["target_ref"],"operation_key":key,
          "instruction":"Read the original result.\n  保留原文  \n", "stop_condition":"Return one finding.\n"}
    app,peer,clock,_=make_app(rsa_key)
    peer.rows=[row]
    digest=_request_key(key)
    read_ref="session-reply-"+digest
    peer.send_result={"target_ref":row["target_ref"],"reply_committed":True,
      "carrier":{"reply_committed":True,"action":"POSTED","message_key":message_key("continue",key),
       "fingerprint":"d"*64,"thread_ts":"1800000000.000001"},
      "attention":{"state":"UNAVAILABLE"},"read_ref":read_ref}
    peer.reply_result={"schema":"mastermind.native_reply_read.v1","read_ref":read_ref,
      "request_ref":"session-bridge-continue:"+digest,"in_reply_to":message_key("continue",key),
      "message_key":message_key("native_reply",key),"fingerprint":"e"*64,
      "text":"Original qualified reply.","next_step":"Review the result.","primary_ts":"1800000000.000002",
      "reply_committed":True,"parent_consumed":False,"operation_key":key}
    submit=auth_fixture._submit_token(rsa_key)
    read=auth_fixture._read_token(rsa_key)
    status,context=request(app,submit,payload={"selection":selection})
    assert status==200 and context["data"]["target"]==row and context["data"]["capabilities"]["send"]
    status,read_context=request(app,read,payload={"selection":selection})
    assert status==200 and not read_context["data"]["capabilities"]["send"]
    before=len(peer.calls)
    status,refused=request(app,read,"send",{"arguments":args})
    assert status==401 and refused["effect"]=="NONE" and len(peer.calls)==before
    status,sent=request(app,submit,"send",{"arguments":args})
    assert status==200 and sent["effect"]=="CONTINUATION_COMMITTED" and peer.calls[-1]["arguments"]==args
    status,reply=request(app,submit,"reply",{"arguments":{"operation_key":key}})
    assert status==200 and reply["data"]["parent_consumed"] is False
    # Late actual verifier expiry withholds original data after dispatch,
    # remaining UNKNOWN rather than no effect or a replacement operation.
    peer.after=lambda:clock.__setitem__(0,NOW+400)
    status,unknown=request(app,submit,"send",{"arguments":args})
    assert unknown["effect"]=="UNKNOWN" and unknown["operation_key"]==key and unknown["data"] is None
    result={"schema":"mastermind.native_session_send_source_fixture.v1","now_ms":NOW*1000,
      "selection":selection,"arguments":args,"context":context,"read_context":read_context,
      "sent":sent,"reply":reply,"unknown":unknown,
      "premises":["actual Runtime target projector with injected current material readers",
       "actual RS256 verifier/authenticator and fixed OsSessionTransportApp",
       "inert InstalledSessionBridgeClient peer; no live target/dispatch or installed authority"]}
    path=Path(__file__).parents[1]/"app/mastermind_os/src/fixtures/native-session-send-producer.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")

def test_unavailable_session_context_cannot_issue_entry_identity(rsa_key):
    app,peer,_,_=make_app(rsa_key)
    peer.error="session_unavailable"
    status,body=request(app,auth_fixture._submit_token(rsa_key))
    assert status==503 and body["operation"]=="context" and body["data"] is None and body["effect"]=="NONE"
    path=Path(__file__).parents[1]/"app/mastermind_os/src/fixtures/native-session-context-unavailable.json"
    path.write_text(json.dumps(body,indent=2)+"\n")

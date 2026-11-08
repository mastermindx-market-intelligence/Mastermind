"""Native actual-owner history DTOs over the original signed HTTP read route.

Stored DTOs come from the actual native owner fixture. Native/provider I/O and
authority are inert there; this test uses real RS256 and Unix client framing.
"""
import asyncio
import copy
import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from common import project_conversation_read_contract as wire
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from integrations.mastermind_executive_app.project_conversation_transport import (
    ProjectConversationReadClient, ProjectConversationTransportApp, validate_result,
)
from tests import test_project_conversation_transport as http
from tests import test_mastermind_os_session_transport as session
from tests import test_mastermind_executive_app_asgi as auth

rsa_key = auth.rsa_key
FIXTURE = json.loads((http.F / "native-fresh-conversation-owner.json").read_text())


def fragment_case(kind="initial_input", offset=0):
    window = FIXTURE["window"]
    turn = window["turns"][0]
    descriptor = window["initial_input"] if kind == "initial_input" else turn["input"]
    text = FIXTURE["initial_message"] if kind == "initial_input" else FIXTURE["followup_message"]
    selected = {key: descriptor[key] for key in ("sha256", "source_event_id", "source_event_sha256")}
    selected.update(kind=kind, offset_utf8=offset)
    if kind == "turn_input":
        selected["turn_key"] = turn["turn_key"]
    raw = text.encode()
    part = raw[offset:offset+4096].decode("utf-8", errors="ignore")
    end = offset + len(part.encode())
    args = {**window["reference"], "fragment": selected}
    result = dict(schema="mastermind.fresh_conversation_input_fragment.v1",
        reference=window["reference"], fragment=selected, text=part,
        utf8_bytes=len(raw), next_offset_utf8=end if end < len(raw) else None)
    return args, result


@pytest.mark.parametrize("kind", ["catalogue", "window", "initial_input", "turn_input", "result_content"])
def test_native_history_passes_signed_http_and_actual_unix_client(rsa_key, kind):
    async def run():
        owner, _, _, _ = session.make_app(rsa_key)
        if kind == "catalogue":
            operation, args, result = "fresh_references", {"work_ref": FIXTURE["catalogue"]["work_ref"]}, FIXTURE["catalogue"]
        elif kind == "window":
            operation, args, result = "fresh_read", FIXTURE["window"]["reference"], FIXTURE["window"]
        elif kind == "result_content":
            content = json.loads((http.F / "native-fresh-content-owner.json").read_text())["fragments"][0]
            operation, args, result = "fresh_read", content["request"], content["response"]
        else:
            operation = "fresh_read"
            args, result = fragment_case(kind)
        observed = []
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "read.sock"
            async def serve(reader, writer):
                frame = wire.decode_frame(await reader.readline())
                observed.append(frame)
                raw = (json.dumps({"ok": True, "result": result}, ensure_ascii=False)+"\n").encode()
                assert len(raw) <= wire.MAX_RESPONSE_BYTES
                writer.write(raw)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            server = await asyncio.start_unix_server(serve, path=str(path))
            try:
                client = ProjectConversationReadClient(path, client=CeoIngressClient())
                app = ProjectConversationTransportApp(client, auth_owner=owner)
                status, data = await http.exchange(app, auth._read_token(rsa_key), operation, args)
                assert status == 200 and data == result
                assert len(observed) == 1 and observed[0]["arguments"] == args
                assert observed[0]["principal"]["policy_id"] == "bsc-e1-test-read"
            finally:
                server.close()
                await server.wait_closed()
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["initial_input", "turn_input"])
def test_all_native_input_fragments_reconstruct_exact_actual_owner_text(kind):
    text = FIXTURE["initial_message"] if kind == "initial_input" else FIXTURE["followup_message"]
    reconstructed = ""
    offset = 0
    while True:
        args, result = fragment_case(kind, offset)
        assert validate_result(result, "fresh_read", args) == result
        reconstructed += result["text"]
        if result["next_offset_utf8"] is None:
            break
        offset = result["next_offset_utf8"]
    assert reconstructed == text and len(reconstructed.encode()) == 131072
    assert hashlib.sha256(reconstructed.encode()).hexdigest() == args["fragment"]["sha256"]


@pytest.mark.parametrize("fault", [
    "input_source", "seal_digest", "turn_order", "window_selector", "fragment_echo",
    "fragment_progress", "fragment_source", "catalogue_source", "can_send",
])
def test_native_history_http_validator_withholds_substituted_or_malformed_data(fault):
    operation = "fresh_read"
    args, data = copy.deepcopy(FIXTURE["window"]["reference"]), copy.deepcopy(FIXTURE["window"])
    if fault == "input_source":
        data["initial_input"]["source_event_sha256"] = "f"*64
    elif fault == "seal_digest":
        data["initial_result"]["digest"] = "f"*64
    elif fault == "turn_order":
        data["turns"][0]["input"]["source_event_id"] = args["root_event_id"]
    elif fault == "window_selector":
        data["reference"]["root_job_id"] = "JOB-999"
    elif fault.startswith("fragment_"):
        raw_args, raw_data = fragment_case()
        args, data = copy.deepcopy(raw_args), copy.deepcopy(raw_data)
        if fault == "fragment_echo": data["fragment"]["offset_utf8"] += 1
        elif fault == "fragment_progress": data["next_offset_utf8"] -= 1
        else:
            args["fragment"]["source_event_sha256"] = data["fragment"]["source_event_sha256"] = "f"*64
    elif fault == "catalogue_source":
        operation, args, data = "fresh_references", {"work_ref": FIXTURE["catalogue"]["work_ref"]}, copy.deepcopy(FIXTURE["catalogue"])
        data["entries"][0]["initial_input"]["source_event_id"] += 1
    elif fault == "can_send":
        data["can_send"] = True
    with pytest.raises((ValueError, TypeError)):
        validate_result(data, operation, args)


def test_native_fragment_late_revocation_withholds_original_response(rsa_key):
    args, result = fragment_case()
    app, calls, _, audit = http.setup(rsa_key, "fresh_read", result=result)
    original = app._reader._client._send_frame
    from types import MethodType
    async def late(self, *a, **kw):
        value = await original(*a, **kw)
        audit.fail = True
        return value
    replacement = MethodType(late, app._reader._client)
    app._reader._client._send_frame = replacement
    app._reader._inner = replacement
    status, data = asyncio.run(http.exchange(app, auth._read_token(rsa_key), "fresh_read", args))
    assert status != 200 and data != result and len(calls) == 1

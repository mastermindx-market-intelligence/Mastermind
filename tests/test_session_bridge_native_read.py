"""Authorized original-request reply reads; no subscription or consumption writes."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import importlib

import pytest

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.session_bridge.schemas import BridgeError
from test_session_bridge_native_reply import Resolver as NativeResolver, Service, arguments, writer, THREAD, REQUEST

NOW = 1800000000
ISSUER = "https://auth.example.test/"
PRINCIPAL = VerifiedPrincipal(policy_id="executive-read", issuer=ISSUER,
    issuer_digest=hashlib.sha256(ISSUER.encode()).hexdigest(), resource="https://exec.example.test/mcp",
    subject_digest="1" * 64, client_ref="2" * 64, scopes=("mastermind.executive.read",),
    issued_at=NOW - 100, expires_at=NOW + 100, jti_digest=None)
READ_REF = "native-return-read-001"


def api():
    spec = importlib.util.find_spec("integrations.session_bridge.native_read")
    assert spec is not None, "authenticated canonical native reply reader is missing"
    return importlib.import_module(spec.name)


class Resolver:
    def __init__(self):
        r, self.service = NativeResolver(), Service()
        asyncio.run(writer(r, self.service)(arguments()))
        message = self.service.items[-1]["message"]
        self.binding = api().NativeReplyReadBinding(
            authorized_principal=principal_projection(PRINCIPAL), read_ref=READ_REF,
            request_ref="request-001", request_message_key=REQUEST, thread_ts=THREAD,
            reply_message_key=message["message_key"], reply_fingerprint=message["fingerprint"],
            context=r.binding.context, authorization_revision="authorization-revision-001")
        self.calls = []
        self.service.calls.clear()
    async def resolve_read(self, *, principal, read_ref):
        self.calls.append((principal, read_ref))
        return self.binding


def reader(resolver, **kwargs):
    from pathlib import Path
    return api().NativeReplyReader(resolver, socket_path=Path("/private/tmp/native-read-proof.sock"),
        service_call=resolver.service, clock=lambda: NOW, **kwargs)


def run(resolver, principal=PRINCIPAL, args=None):
    return asyncio.run(reader(resolver)(principal, {"read_ref": READ_REF} if args is None else args))


def test_read_ref_returns_exact_canonical_reply_with_no_write_or_consumption_claim():
    r = Resolver()
    result = run(r)
    assert result["schema"] == "mastermind.native_reply_read.v1"
    assert result["read_ref"] == READ_REF and result["request_ref"] == "request-001"
    assert result["in_reply_to"] == REQUEST
    assert result["text"] == arguments()["text"] and result["next_step"] == arguments()["next_step"]
    assert result["reply_committed"] is True and result["parent_consumed"] is False
    assert result["fingerprint"] == r.binding.reply_fingerprint
    assert len(r.calls) == 2
    assert [p["operation"] for p in r.service.calls] == ["read_thread"]


@pytest.mark.parametrize("args", [{}, {"read_ref": ""}, {"read_ref": READ_REF, "thread_ts": THREAD},
    {"read_ref": READ_REF, "principal": "forged"}, {"read_ref": READ_REF, "consume": True},
    {"read_ref": "other-read-reference"}, {"read_ref": "x" * 257}])
def test_model_cannot_select_carrier_principal_or_acknowledge_consumption(args):
    r = Resolver()
    with pytest.raises(BridgeError):
        run(r, args=args)
    assert not r.service.calls


@pytest.mark.parametrize("changes", [{"subject_digest": "3" * 64}, {"client_ref": "4" * 64},
    {"resource": "https://foreign.example.test/mcp"}, {"policy_id": "other-policy"},
    {"issuer": "https://foreign.example.test/", "issuer_digest": hashlib.sha256(b"https://foreign.example.test/").hexdigest()},
    {"expires_at": NOW}, {"scopes": ()}])
def test_foreign_expired_or_unscoped_principal_cannot_read(changes):
    r = Resolver()
    with pytest.raises(BridgeError):
        run(r, dataclasses.replace(PRINCIPAL, **changes))
    assert not r.service.calls


def test_unverified_object_is_not_accepted_as_caller_identity():
    r = Resolver()
    with pytest.raises(BridgeError):
        run(r, dataclasses.asdict(PRINCIPAL))
    assert not r.service.calls


def test_refreshed_token_for_same_principal_can_read_without_new_identity():
    r = Resolver()
    p = dataclasses.replace(PRINCIPAL, issued_at=NOW - 10, expires_at=NOW + 300, jti_digest="5" * 64)
    assert run(r, p)["reply_committed"] is True


@pytest.mark.parametrize("changes", [{"authorization_revision": "revoked-revision-002"},
    {"thread_ts": "1787896129.000001"}, {"reply_fingerprint": "0" * 64},
    {"request_ref": "other-request"}])
def test_authorization_or_binding_change_across_read_suppresses_result(changes):
    r = Resolver()
    r.service.on_read = lambda: setattr(r, "binding", dataclasses.replace(r.binding, **changes))
    with pytest.raises(BridgeError):
        run(r)
    assert len(r.service.calls) == 1


@pytest.mark.parametrize("field,value", [("fingerprint", "0" * 64),
    ("reply_to_message_key", "asd-other-request"), ("message_key", "asd-other-reply")])
def test_tampered_or_foreign_reply_is_not_returned(field, value):
    r = Resolver()
    r.service.items[-1]["message"][field] = value
    with pytest.raises(BridgeError):
        run(r)
    assert len(r.service.calls) == 1


def test_missing_reply_has_same_public_error_as_foreign_access():
    r = Resolver()
    r.service.items.pop()
    with pytest.raises(BridgeError) as missing:
        run(r)
    other = Resolver()
    with pytest.raises(BridgeError) as foreign:
        run(other, dataclasses.replace(PRINCIPAL, subject_digest="9" * 64))
    assert (missing.value.code, str(missing.value)) == (foreign.value.code, str(foreign.value))


def test_duplicate_physical_reply_rows_are_ambiguous():
    r = Resolver()
    r.service.items.append(r.service.items[-1].copy())
    with pytest.raises(BridgeError):
        run(r)


def test_authenticated_read_error_never_exposes_backend_diagnostics():
    r = Resolver()
    async def failing(*args):
        raise RuntimeError("private-path-and-token-diagnostic")
    r.service = failing
    with pytest.raises(BridgeError) as error:
        run(r)
    assert "private" not in str(error.value)


def test_reader_cancellation_propagates_without_write():
    r = Resolver()
    async def cancelled(*args):
        raise asyncio.CancelledError()
    r.service = cancelled
    with pytest.raises(asyncio.CancelledError):
        run(r)


def test_token_expiry_during_final_authorization_await_suppresses_reply():
    from pathlib import Path
    r = Resolver()
    clock = [NOW]
    class DelayedResolver:
        async def resolve_read(self, **kwargs):
            binding = await r.resolve_read(**kwargs)
            if len(r.calls) == 2:
                clock[0] = PRINCIPAL.expires_at
            return binding
    instance = api().NativeReplyReader(DelayedResolver(),
        socket_path=Path("/private/tmp/native-read-proof.sock"),
        service_call=r.service, clock=lambda: clock[0])
    with pytest.raises(BridgeError):
        asyncio.run(instance(PRINCIPAL, {"read_ref": READ_REF}))
    assert len(r.service.calls) == 1

from __future__ import annotations

import asyncio
import json

from integrations.mastermind_workspace_content.resource import WorkspaceContentResource

RESOURCE = "https://workspace.example.test/api/conversations/live"
ORIGIN = "https://workspace.example.test"
SOURCE = "managed-window:test-turn"


class Owner:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.allowed = True
        self.auth_calls = 0
        self.read_calls = 0

    async def authorize(self, header: str, resource: str, source_ref: str):
        self.auth_calls += 1
        if self.allowed and header == "Bearer test" and resource == RESOURCE and source_ref == SOURCE:
            return ("policy", "subject", "grant-v1")
        return None

    async def read(self, source_ref: str) -> bytes:
        self.read_calls += 1
        assert source_ref == SOURCE
        return self.payload


async def request(app, *, method: str = "GET", authorization: bytes | None = b"Bearer test"):
    sent = []
    frames = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():
        return frames.pop(0)

    async def send(message):
        sent.append(message)

    headers = [(b"host", b"workspace.example.test"), (b"origin", ORIGIN.encode())]
    if authorization is not None:
        headers.append((b"authorization", authorization))
    await app(
        {
            "type": "http",
            "method": method,
            "scheme": "https",
            "path": "/api/conversations/live",
            "raw_path": b"/api/conversations/live",
            "root_path": "",
            "query_string": b"",
            "headers": headers,
        },
        receive,
        send,
    )
    status = sent[0]["status"]
    body = b"".join(message.get("body", b"") for message in sent[1:])
    return status, json.loads(body)


def make_payload() -> bytes:
    return json.dumps(
        {
            "schema": "mastermind.workspace.visible_window.v1",
            "source_ref": SOURCE,
            "scope": "one-managed-turn-window",
            "observed_at": "2026-09-16T22:00:00+00:00",
            "epoch": "0" * 64,
            "terminal": False,
            "coverage": "OBSERVED_WINDOW",
            "history": "NOT_PROVEN",
            "acceptance": "NOT_PROJECTED",
            "capabilities": {"send": False, "provider_control": False, "history": False},
            "items": [],
            "gaps": [],
        },
        separators=(",", ":"),
    ).encode()


def test_fixed_authorized_get_returns_no_store_window() -> None:
    owner = Owner(make_payload())
    app = WorkspaceContentResource(
        owner=owner,
        resource=RESOURCE,
        source_ref=SOURCE,
        allowed_origin=ORIGIN,
    )
    status, body = asyncio.run(request(app))

    assert status == 200
    assert body["mode"] == "observed-turn-window"
    assert body["selection_ref"] == SOURCE
    assert owner.read_calls == 1
    assert owner.auth_calls == 2


def test_missing_authentication_never_reads_source() -> None:
    owner = Owner(make_payload())
    app = WorkspaceContentResource(owner=owner, resource=RESOURCE, source_ref=SOURCE, allowed_origin=ORIGIN)
    status, body = asyncio.run(request(app, authorization=None))

    assert status == 401
    assert body == {"error": "authentication_required"}
    assert owner.read_calls == 0


def test_access_change_after_read_refuses_payload() -> None:
    owner = Owner(make_payload())

    original = owner.authorize

    async def changing(header: str, resource: str, source_ref: str):
        result = await original(header, resource, source_ref)
        if owner.auth_calls == 1:
            owner.allowed = False
        return result

    owner.authorize = changing
    app = WorkspaceContentResource(owner=owner, resource=RESOURCE, source_ref=SOURCE, allowed_origin=ORIGIN)
    status, body = asyncio.run(request(app))

    assert status == 403
    assert body == {"error": "access_changed"}


def test_unknown_route_and_method_are_closed() -> None:
    owner = Owner(make_payload())
    app = WorkspaceContentResource(owner=owner, resource=RESOURCE, source_ref=SOURCE, allowed_origin=ORIGIN)
    status, body = asyncio.run(request(app, method="POST"))
    assert status == 405
    assert body == {"error": "method_not_allowed"}


def test_duplicate_json_member_is_refused_even_when_last_value_looks_valid() -> None:
    valid = make_payload().decode("utf-8")
    duplicated = valid.replace(
        '{"schema":',
        '{"schema":"attacker-shadow","schema":',
        1,
    ).encode("utf-8")
    owner = Owner(duplicated)
    app = WorkspaceContentResource(owner=owner, resource=RESOURCE, source_ref=SOURCE, allowed_origin=ORIGIN)

    status, body = asyncio.run(request(app))

    assert status == 502
    assert body == {"error": "source_unavailable"}

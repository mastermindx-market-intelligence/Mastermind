"""Mastermind Browser MCP shell over an injected existing owner.

Fixtures provide synthetic caller/owner objects only; these tests grant no Runtime,
browser, provider, tunnel, or OAuth authority.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import importlib
from importlib.util import find_spec
import json

import pytest


CATALOG_MODULE = "integrations.mastermind_browser_plugin.catalog"
FACADE_MODULE = "integrations.mastermind_browser_plugin.facade"
SERVER_MODULE = "integrations.mastermind_browser_plugin.server"


def load(name):
    assert find_spec(name) is not None, f"{name} must exist"
    return importlib.import_module(name)


class Owner:
    async def browser_fleet(self, caller, args):
        return {"caller": caller, "browsers": []}

    async def browser_tabs(self, caller, args):
        return {"caller": caller, "tabs": []}

    async def browser_snapshot(self, caller, args):
        return {"caller": caller, "text": "untrusted page"}

    async def browser_screenshot(self, caller, args):
        return {"caller": caller, "mime_type": "image/jpeg", "bytes": 123}

    async def prepare_browser_action(self, caller, args):
        return {"action_ref": f"{caller}:prepared"}

    async def run_browser_action(self, caller, args):
        if (
            args.get("tab_ref") != "tab-1"
            or args["action_ref"] != f"{caller}:prepared"
        ):
            raise load(FACADE_MODULE).OwnerRefused("FOREIGN_REFERENCE")
        return {"effect": "APPLIED", "status": "completed"}

    async def reconcile_browser_action(self, caller, args):
        if args.get("tab_ref") != "tab-1":
            raise load(FACADE_MODULE).OwnerRefused("FOREIGN_REFERENCE")
        return {"effect": "EFFECT_UNKNOWN", "status": "pending"}


def test_closed_catalog_is_exact_and_defensive():
    m = load(CATALOG_MODULE)
    rows = m.catalog()
    assert [row["name"] for row in rows] == [
        "browser_fleet",
        "browser_tabs",
        "browser_snapshot",
        "browser_screenshot",
        "prepare_browser_action",
        "run_browser_action",
        "reconcile_browser_action",
    ]
    assert all(row["inputSchema"]["additionalProperties"] is False for row in rows)
    assert rows[4]["annotations"]["readOnlyHint"] is True
    assert rows[5]["annotations"]["readOnlyHint"] is False
    assert rows[6]["annotations"]["readOnlyHint"] is True
    assert rows[5]["inputSchema"]["required"] == ["tab_ref", "action_ref"]
    assert rows[6]["inputSchema"]["required"] == ["tab_ref", "action_ref"]
    assert len(m.SCHEMA_DIGEST) == 64
    rows[0]["name"] = "shell"
    assert m.catalog()[0]["name"] == "browser_fleet"


def test_facade_requires_existing_owner_and_trusted_caller_resolver():
    m = load(FACADE_MODULE)
    for owner, resolver in [
        (None, lambda: "alice"),
        (Owner(), None),
        (object(), lambda: "alice"),
    ]:
        with pytest.raises(TypeError):
            m.BrowserFacade(owner=owner, caller_resolver=resolver)


@pytest.mark.parametrize(
    "name,args",
    [
        ("browser_fleet", {"actor": "admin"}),
        ("browser_fleet", {"limit": True}),
        ("browser_fleet", {"limit": 51}),
        ("browser_tabs", {"browser_ref": "x", "host": "m2"}),
        ("browser_snapshot", {"tab_ref": "x", "session_id": "admin"}),
        (
            "prepare_browser_action",
            {
                "tab_ref": "x",
                "operation_key": "op",
                "action": "evaluate",
                "args": {"javascript": "fetch()"},
            },
        ),
        (
            "prepare_browser_action",
            {
                "tab_ref": "x",
                "operation_key": "op",
                "action": "type",
                "args": {"element_ref": "ref", "text": "x", "token": "secret"},
            },
        ),
        (
            "prepare_browser_action",
            {
                "tab_ref": "x",
                "operation_key": "op",
                "action": "navigate",
                "args": {"url": "file:///etc/passwd"},
            },
        ),
        (
            "prepare_browser_action",
            {
                "tab_ref": "x",
                "operation_key": "op",
                "action": "scroll",
                "args": {"delta_x": 2001, "delta_y": 0},
            },
        ),
        ("run_browser_action", {"tab_ref": "tab-1", "action_ref": "x", "force": True}),
        ("reconcile_browser_action", {"action_ref": "x"}),
        ("shell", {}),
        ("browser_fleet", None),
    ],
)
def test_closed_inputs_refuse_without_dispatch(name, args):
    m = load(FACADE_MODULE)

    class NoCalls(Owner):
        async def browser_fleet(self, *unused):
            raise AssertionError("owner dispatch")

    result = asyncio.run(
        m.BrowserFacade(owner=NoCalls(), caller_resolver=lambda: "alice").call(
            name, args
        )
    )
    assert result["is_error"] is True
    assert result["effect"] == "NOT_APPLIED"
    assert result["code"] in {"INVALID_ARGUMENTS", "UNKNOWN_TOOL"}


def test_each_call_resolves_current_caller_and_foreign_reference_refuses():
    m = load(FACADE_MODULE)
    caller = ContextVar("caller", default="alice")
    facade = m.BrowserFacade(owner=Owner(), caller_resolver=caller.get)

    async def exercise():
        prepared = await facade.call(
            "prepare_browser_action",
            {
                "tab_ref": "tab-1",
                "operation_key": "op-1",
                "action": "click",
                "args": {"element_ref": "e-1"},
            },
        )
        assert prepared["effect"] == "NOT_APPLIED"
        assert prepared["data"]["action_ref"] == "alice:prepared"
        caller.set("bob")
        foreign = await facade.call(
            "run_browser_action",
            {"tab_ref": "tab-1", "action_ref": "alice:prepared"},
        )
        assert foreign["code"] == "FOREIGN_REFERENCE"
        assert foreign["effect"] == "NOT_APPLIED"
        caller.set("alice")
        own = await facade.call(
            "run_browser_action",
            {"tab_ref": "tab-1", "action_ref": "alice:prepared"},
        )
        assert own["data"]["effect"] == "APPLIED"

    asyncio.run(exercise())


def test_missing_caller_refuses_before_owner_and_never_echoes_private_error():
    m = load(FACADE_MODULE)

    def broken():
        raise RuntimeError("private token detail")

    for resolver in (lambda: None, broken):
        result = asyncio.run(
            m.BrowserFacade(owner=Owner(), caller_resolver=resolver).call(
                "browser_fleet", {}
            )
        )
        assert result["code"] == "CALLER_UNAVAILABLE"
        assert "private" not in json.dumps(result)


def test_uncertain_mutation_is_not_retried_or_downgraded():
    m = load(FACADE_MODULE)

    class Broken(Owner):
        calls = 0

        async def run_browser_action(self, *unused):
            self.calls += 1
            raise RuntimeError("private socket token")

    owner = Broken()
    facade = m.BrowserFacade(owner=owner, caller_resolver=lambda: "alice")
    result = asyncio.run(
        facade.call(
            "run_browser_action",
            {"tab_ref": "tab-1", "action_ref": "alice:prepared"},
        )
    )
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert result["retry_allowed"] is False
    assert owner.calls == 1
    result = asyncio.run(
        facade.call(
            "reconcile_browser_action",
            {"tab_ref": "tab-1", "action_ref": "alice:prepared"},
        )
    )
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert owner.calls == 1
    assert "private" not in json.dumps(result)


def test_mutating_owner_result_requires_effect_and_read_cannot_smuggle_effect():
    m = load(FACADE_MODULE)

    class Invalid(Owner):
        async def browser_fleet(self, *unused):
            return {"effect": "APPLIED"}

        async def run_browser_action(self, *unused):
            return {"status": "success"}

    facade = m.BrowserFacade(owner=Invalid(), caller_resolver=lambda: "alice")
    assert asyncio.run(facade.call("browser_fleet", {}))["code"] == "OWNER_RESULT_INVALID"
    run = asyncio.run(
        facade.call(
            "run_browser_action",
            {"tab_ref": "tab-1", "action_ref": "alice:prepared"},
        )
    )
    assert run["code"] == "OWNER_RESULT_INVALID"
    assert run["effect"] == "EFFECT_UNKNOWN"


def test_http_server_uses_existing_auth_per_request_and_exact_internal_route():
    pytest.importorskip("mcp")
    httpx = pytest.importorskip("httpx")
    m = load(SERVER_MODULE)

    async def authenticate(request):
        return {"alice": "alice", "bob": "bob"}.get(
            request.headers.get("x-fixture-caller")
        )

    app = m.create_http_app(
        owner=Owner(),
        authenticate=authenticate,
        auth_challenge='Bearer resource_metadata="https://browser.test/.well-known/oauth-protected-resource"',
        allowed_hosts=["browser.test"],
    )

    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "synthetic-test", "version": "1"},
        },
    }

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://browser.test",
            ) as client:
                headers = {
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                    "x-fixture-caller": "alice",
                }
                assert (
                    await client.post(m.INTERNAL_PATH, json=init)
                ).status_code == 401
                initialized = await client.post(
                    m.INTERNAL_PATH, json=init, headers=headers
                )
                assert initialized.status_code == 200, initialized.text
                assert initialized.json()["result"]["serverInfo"]["name"] == "mastermind-browser"
                tools = await client.post(
                    m.INTERNAL_PATH,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    headers=headers,
                )
                assert len(tools.json()["result"]["tools"]) == 7

                async def call(who):
                    response = await client.post(
                        m.INTERNAL_PATH,
                        headers={**headers, "x-fixture-caller": who},
                        json={
                            "jsonrpc": "2.0",
                            "id": 3,
                            "method": "tools/call",
                            "params": {
                                "name": "browser_fleet",
                                "arguments": {},
                            },
                        },
                    )
                    assert response.status_code == 200, response.text
                    return response.json()["result"]["structuredContent"]["data"][
                        "caller"
                    ]

                assert await asyncio.gather(call("alice"), call("bob")) == [
                    "alice",
                    "bob",
                ]
                bad = await client.post(
                    m.INTERNAL_PATH,
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "browser_fleet",
                            "arguments": {"actor": "admin"},
                        },
                    },
                )
                assert bad.json()["result"]["isError"] is True
                wrong_host = await client.post(
                    m.INTERNAL_PATH,
                    headers={**headers, "host": "attacker.test"},
                    json=init,
                )
                assert wrong_host.status_code == 421
                assert (
                    await client.post(
                        m.INTERNAL_PATH, headers=headers, content="x" * 100000
                    )
                ).status_code == 413
                assert (
                    await client.post("/mcp", headers=headers, json=init)
                ).status_code == 404

    asyncio.run(exercise())


def test_http_factory_requires_real_owner_auth_challenge_and_exact_hosts():
    pytest.importorskip("mcp")
    m = load(SERVER_MODULE)
    cases = [
        {"owner": None, "authenticate": lambda unused: None, "auth_challenge": "Bearer", "allowed_hosts": ["browser.test"]},
        {"owner": Owner(), "authenticate": None, "auth_challenge": "Bearer", "allowed_hosts": ["browser.test"]},
        {"owner": Owner(), "authenticate": lambda unused: None, "auth_challenge": "Basic", "allowed_hosts": ["browser.test"]},
        {"owner": Owner(), "authenticate": lambda unused: None, "auth_challenge": "Bearer", "allowed_hosts": ["*"]},
    ]
    for kwargs in cases:
        with pytest.raises(TypeError):
            m.create_http_app(**kwargs)


def test_private_stdio_uses_same_seven_tool_server_and_exits_on_eof():
    pytest.importorskip("mcp")
    import os
    from pathlib import Path
    import select
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    code = r"""
import asyncio
from integrations.mastermind_browser_plugin.facade import BrowserFacade, OwnerRefused
from integrations.mastermind_browser_plugin.server import serve_stdio

class Owner:
    async def browser_fleet(self, caller, args): return {"caller": caller, "browsers": []}
    async def browser_tabs(self, caller, args): return {"caller": caller, "tabs": []}
    async def browser_snapshot(self, caller, args): return {"caller": caller, "text": "synthetic"}
    async def browser_screenshot(self, caller, args): return {"caller": caller, "mime_type": "image/jpeg"}
    async def prepare_browser_action(self, caller, args): return {"action_ref": caller + ":prepared"}
    async def run_browser_action(self, caller, args):
        if args["action_ref"] != caller + ":prepared": raise OwnerRefused("FOREIGN_REFERENCE")
        return {"effect": "APPLIED"}
    async def reconcile_browser_action(self, caller, args): return {"effect": "EFFECT_UNKNOWN"}

asyncio.run(serve_stdio(BrowserFacade(owner=Owner(), caller_resolver=lambda: "native-fixture")))
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                part
                for part in (str(root), os.environ.get("PYTHONPATH", ""))
                if part
            ),
            "PYTHONUNBUFFERED": "1",
        },
        bufsize=0,
    )

    def send(value):
        process.stdin.write((json.dumps(value) + "\n").encode())
        process.stdin.flush()

    def receive(timeout=8):
        ready, _, _ = select.select([process.stdout], [], [], timeout)
        assert ready, "native Browser MCP response timed out"
        line = process.stdout.readline()
        assert line, process.stderr.read().decode(errors="replace")
        return json.loads(line)

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "native-fixture", "version": "1"},
                },
            }
        )
        initialized = receive()
        assert initialized["result"]["serverInfo"]["name"] == "mastermind-browser"
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert len(receive()["result"]["tools"]) == 7
        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "browser_fleet", "arguments": {}},
            }
        )
        assert (
            receive()["result"]["structuredContent"]["data"]["caller"]
            == "native-fixture"
        )
        process.stdin.close()
        assert process.wait(timeout=8) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

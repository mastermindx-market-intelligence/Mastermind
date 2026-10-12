"""Mounted ASGI liveness/readiness tests; no credentials or network sockets."""
from __future__ import annotations

import asyncio
from mcp.server.fastmcp import FastMCP
import httpx
import pytest

from integrations.product_access_mcp.mount import create_product_asgi_app


def test_owner_ready_is_required_at_construction():
    with pytest.raises(ValueError):
        create_product_asgi_app(server=None, owner_ready=lambda: True)
    with pytest.raises(ValueError):
        create_product_asgi_app(server=FastMCP("fixture"), owner_ready=None)


def test_liveness_never_substitutes_for_owner_readiness():
    async def exercise():
        selected = [False]
        synthetic = FastMCP("No credentials or product data", stateless_http=True, json_response=True)
        app = create_product_asgi_app(server=synthetic, owner_ready=lambda: selected[0])
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as client:
                health = await client.get("/healthz")
                assert health.status_code == 200 and health.text == "OK\n"
                blocked = await client.get("/readyz")
                assert blocked.status_code == 503
                assert blocked.text == "NOT_READY\n"
                # A not-ready owner MUST NOT serve tools merely because the
                # MCP SDK session manager is already running.
                unavailable = await client.post("/mcp", json={"not": "admitted"})
                assert unavailable.status_code == 503
                selected[0] = True
                ready = await client.get("/readyz")
                assert ready.status_code == 200
                assert ready.text == "READY\n"
                selected[0] = False
                assert (await client.get("/readyz")).status_code == 503
                # The catch-all Product gate refuses unsupported writes
                # while the owner is unavailable, rather than reaching MCP.
                assert (await client.post("/readyz")).status_code == 503

    asyncio.run(exercise())


@pytest.mark.parametrize("status", [False, None, "READY", 1])
def test_non_boolean_readiness_never_claims_ready(status):
    async def exercise():
        app = create_product_asgi_app(
            server=FastMCP("fixture", stateless_http=True, json_response=True),
            owner_ready=lambda: status,
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as client:
                result = await client.get("/readyz")
                assert result.status_code == 503
                assert result.text == "NOT_READY\n"

    asyncio.run(exercise())


def test_private_readiness_exception_is_not_exposed():
    def probe():
        raise RuntimeError("PRIVATE_OPERATION_RECEIPT_AND_CREDENTIAL")
    async def exercise():
        app = create_product_asgi_app(
            server=FastMCP("fixture", stateless_http=True, json_response=True),
            owner_ready=probe,
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as client:
                result = await client.get("/readyz")
                assert result.status_code == 503
                assert result.text == "NOT_READY\n"
                assert "PRIVATE" not in result.text

    asyncio.run(exercise())

"""The actual OS composition must admit only the qualified V3 1.4/1.5 producers."""

import asyncio

import pytest

from test_mastermind_os_executive_transport import (
    _v3_app,
    client,
    fixture,
    headers,
    rsa_key,
    settings,
    short_socket_root,
)
from integrations.executive_mcp import web_ceo_v3


def test_os_optin_composes_qualified_v3_15(settings, monkeypatch):
    monkeypatch.setattr(web_ceo_v3, "WEB_CEO_V3_SERVER_VERSION", "1.5.0")
    app = _v3_app(settings)
    assert app.os_transport is not None


def test_authenticated_os_context_emits_qualified_v3_15(
    settings, rsa_key, monkeypatch
):
    monkeypatch.setattr(web_ceo_v3, "WEB_CEO_V3_SERVER_VERSION", "1.5.0")

    async def exercise():
        async with client(settings) as inner:
            response = await inner.post(
                "/os/executive/context",
                headers=headers(fixture._submit_token(rsa_key)),
                json={},
            )
            assert response.status_code == 200
            assert response.json()["profile"] == {
                "name": "web_ceo_v3",
                "server_version": "1.5.0",
            }

    asyncio.run(exercise())


@pytest.mark.parametrize("version", ["1.2.0", "1.3.0", "1.6.0", "2.0.0", "", None])
def test_os_optin_refuses_unqualified_versions(settings, monkeypatch, version):
    monkeypatch.setattr(web_ceo_v3, "WEB_CEO_V3_SERVER_VERSION", version)
    with pytest.raises(ValueError, match="exact installed v3 composition"):
        _v3_app(settings)

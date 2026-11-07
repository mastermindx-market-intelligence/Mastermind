"""Run inside the pinned Hermes test checkout via scripts/run_tests.sh.

The package is copied beside these tests into a disposable qualification tree.
No production home, credential, provider or gateway is used.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import struct
import zlib

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

PACKAGE = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("mastermind_mobile_metadata", PACKAGE / "dashboard" / "plugin_api.py")
api = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(api)
PREFIX = "/api/plugins/mastermind-mobile"


@pytest.mark.parametrize("base", ["", "/hermes", "/office/hermes"])
def test_manifest_stays_on_its_origin_and_selects_agents_without_sending(base):
    value = api.manifest(base)
    assert value["scope"] == base + "/"
    assert value["id"] == base + "/?app=mastermind-mobile"
    assert value["display"] == "standalone"
    assert value["start_url"] == base + "/?mastermind-agent=meta-ceo-uncensored#/mastermind"
    assert [row["name"] for row in value["shortcuts"]] == ["Meta-CEO", "Secretary", "Chief of Staff"]
    for shortcut in value["shortcuts"]:
        assert shortcut["url"].startswith(base + "/?mastermind-agent=")
        assert shortcut["url"].endswith("#/mastermind")
        assert "token" not in shortcut["url"]
    assert {row["sizes"] for row in value["icons"]} == {"192x192", "512x512"}
    assert all(row["src"].startswith(base + PREFIX + "/") for row in value["icons"])
    assert "serviceworker" not in value
    assert "share_target" not in value


@pytest.mark.parametrize("base", ["https://other.test", "//other.test", "/../", "/x?token=private", "/x#fragment", "/x\\y", "/x\nY"])
def test_manifest_rejects_unsafe_deployment_prefixes(base):
    with pytest.raises(ValueError):
        api.manifest(base)


@pytest.mark.parametrize("size", [192, 512])
def test_original_maskable_icon_is_a_valid_opaque_png(size):
    payload = api.icon_png(size)
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    offset, chunks = 8, {}
    while offset < len(payload):
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        kind = payload[offset + 4:offset + 8]
        data = payload[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", payload[offset + 8 + length:offset + 12 + length])[0]
        assert crc == zlib.crc32(kind + data) & 0xFFFFFFFF
        chunks[kind] = data
        offset += 12 + length
    assert struct.unpack(">IIBBBBB", chunks[b"IHDR"]) == (size, size, 8, 2, 0, 0, 0)
    pixels = zlib.decompress(chunks[b"IDAT"])
    assert len(pixels) == size * (1 + size * 3)
    assert set(pixels) <= {0, 28, 30, 245}
    assert chunks[b"IEND"] == b""


def test_static_router_uses_the_native_proxy_prefix_without_accepting_a_foreign_origin():
    app = FastAPI()
    app.include_router(api.router, prefix=PREFIX)
    with TestClient(app) as client:
        response = client.get(PREFIX + "/metadata", headers={"X-Forwarded-Prefix": "/hermes"})
        assert response.status_code == 200
        assert response.json()["manifest"] == "/hermes" + PREFIX + "/manifest.webmanifest"
        assert response.headers["Cache-Control"] == "private, no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        bad = client.get(PREFIX + "/metadata", headers={"X-Forwarded-Prefix": "/x?next=elsewhere"})
        assert bad.status_code == 400
        assert client.get(PREFIX + "/icon-1024.png").status_code == 404
        manifest = client.get(PREFIX + "/manifest.webmanifest")
        assert manifest.headers["content-type"].startswith("application/manifest+json")


@pytest.fixture
def native_client(_isolate_hermes_home, monkeypatch):
    """Use Hermes's own auth, runtime plugin gate and dynamic mount, not a mock gate."""
    from hermes_cli import web_server
    from hermes_cli.config import load_config, save_config
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    target = home / "plugins" / "mastermind-mobile"
    target.mkdir(parents=True)
    for name in ("plugin.yaml", "__init__.py"):
        shutil.copyfile(PACKAGE / name, target / name)
    shutil.copytree(PACKAGE / "dashboard", target / "dashboard")
    config = load_config()
    config["plugins"] = {"enabled": ["mastermind-mobile"], "disabled": [], "isolation": "in-process"}
    save_config(config)
    original = list(web_server.app.router.routes)
    web_server._dashboard_plugins_cache = None
    monkeypatch.setattr(web_server.app.state, "auth_required", False, raising=False)
    monkeypatch.setattr(web_server.app.state, "bound_host", None, raising=False)
    client = TestClient(web_server.app)
    try:
        yield client, web_server, save_config, config
    finally:
        client.close()
        web_server.app.router.routes[:] = original
        web_server._dashboard_plugins_cache = None


@pytest.mark.parametrize("path", ["/metadata", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"])
def test_native_authentication_precedes_plugin_discovery_and_admits_owner_assets(native_client, path):
    client, server, _, _ = native_client
    assert client.get(PREFIX + path, follow_redirects=False).status_code == 401
    client.headers[server._SESSION_HEADER_NAME] = server._SESSION_TOKEN
    response = client.get(PREFIX + path, follow_redirects=False)
    assert response.status_code == 200, response.text[:200]
    assert response.headers["Cache-Control"] == "private, no-store"
    client.headers.clear()
    assert client.get(PREFIX + path, follow_redirects=False).status_code == 401


def test_native_disable_revokes_previously_mounted_install_metadata(native_client):
    client, server, save_config, config = native_client
    client.headers[server._SESSION_HEADER_NAME] = server._SESSION_TOKEN
    assert client.get(PREFIX + "/metadata").status_code == 200
    config["plugins"]["enabled"] = []
    config["plugins"]["disabled"] = ["mastermind-mobile"]
    save_config(config)
    assert client.get(PREFIX + "/metadata").status_code == 404
    client.headers.clear()
    assert client.get(PREFIX + "/metadata").status_code == 401


def test_metadata_adds_no_chat_mutation_or_arbitrary_file_route(native_client):
    client, server, _, _ = native_client
    client.headers[server._SESSION_HEADER_NAME] = server._SESSION_TOKEN
    assert client.get(PREFIX + "/metadata").status_code == 200
    assert client.post(PREFIX + "/metadata", json={"message": "must not send"}).status_code == 405
    assert client.get(PREFIX + "/secrets.txt").status_code == 404
    assert client.get(PREFIX + "/icon-0.png").status_code == 404

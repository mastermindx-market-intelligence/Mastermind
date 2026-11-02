"""Actual 13-file client output through the existing closed asset owners.

All files, manifests and HTTP applications here are disposable test fixtures.
No installed path, public edge, service configuration or provider is touched.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from integrations.mastermind_executive_app.os_assets import os_asset_mimes
from ops.executive_os.executive_mcp_entry import build_os_asset_manifest
from ops.executive_os.os_public_edge import asset_routes, render

BASE = ["index.html", "assets/index-css.css", "assets/index-js.js"]
NOIR = BASE + ["assets/atelier-office-image.jpg", "assets/Manrope-Variable-font.ttf",
    "assets/Inter-Variable-font.woff2", "licenses/fonts/Inter-OFL.txt",
    "licenses/fonts/Manrope-OFL.txt", "licenses/fonts/Manrope-FONTLOG.txt"]
CLIENT = NOIR + ["assets/SourceMarkdown-rich.js", "assets/SourceMarkdown-rich.css",
    "third-party/deepseek-client-dependency-NOTICES.txt", "third-party/deepseek-harness-LICENSE.txt"]
LICENSED = NOIR + CLIENT[-2:]


def make_dist(root: Path, names=CLIENT):
    dist = root / "app/mastermind_os/dist"
    for name in names:
        path = dist / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("source:" + name).encode())
    (dist / "index.html").write_text('<script src="/os/assets/index-js.js"></script><link href="/os/assets/index-css.css">')
    return dist


@pytest.mark.parametrize("names", [BASE, NOIR, LICENSED, CLIENT])
def test_four_exact_supported_layouts_and_mime_sets(names):
    mimes = os_asset_mimes(names)
    assert set(mimes) == set(names)
    assert mimes["index.html"] == "text/html; charset=utf-8"
    assert mimes["assets/index-js.js"] == "text/javascript; charset=utf-8"
    if names == CLIENT:
        assert mimes["assets/SourceMarkdown-rich.js"] == "text/javascript; charset=utf-8"
        assert mimes["assets/SourceMarkdown-rich.css"] == "text/css; charset=utf-8"
        assert mimes["third-party/deepseek-harness-LICENSE.txt"] == "text/plain; charset=utf-8"


@pytest.mark.parametrize("removed", CLIENT)
def test_every_required_member_is_required(removed):
    with pytest.raises(ValueError):
        os_asset_mimes([name for name in CLIENT if name != removed])


@pytest.mark.parametrize("name", [
    "assets/SourceMarkdown-rich.js.map", "assets/OtherFeature-rich.js",
    "assets/SourceMarkdown-rich.js?x=1", "assets/SourceMarkdown-rich.js#fragment",
    "assets/../SourceMarkdown-rich.js", "assets/SourceMarkdown-rich.js\n}",
    "assets/SourceMarkdown-rich.js *", "assets/SourceMarkdown-rich.js/extra",
    "assets/SourceMarkdown-rich\u2028.js", "assets/SourceMarkdown-rich\\.js",
    "assets/SourceMarkdown-rich%2ejs", "assets/SourceMarkdown-.js",
    "third-party/foreign-NOTICES.txt", "third-party/.env", "third-party/private.key",
    "third-party/deepseek-harness-LICENSE.html", "/third-party/deepseek-harness-LICENSE.txt",
    "third-party/../deepseek-harness-LICENSE.txt", "third-party\\deepseek-harness-LICENSE.txt",
    "assets/SourceMarkdown-rich.js;import", "assets/SourceMarkdown-rich.js\r\n",
])
def test_unknown_or_injectable_member_never_becomes_a_route(name):
    altered = list(CLIENT)
    altered[9] = name
    with pytest.raises(ValueError):
        os_asset_mimes(altered)


@pytest.mark.parametrize("names", [
    CLIENT + ["assets/foreign.js"], CLIENT + [CLIENT[0]],
    CLIENT[:9] + CLIENT[9:11], CLIENT[:9] + [CLIENT[9], CLIENT[-1]],
    BASE + CLIENT[9:], CLIENT[:9] + [CLIENT[9]] * 4,
    CLIENT[:9] + [None] * 4, CLIENT[:9] + [1] * 4,
])
def test_partial_extra_duplicate_or_malformed_layout_refuses(names):
    with pytest.raises(ValueError):
        os_asset_mimes(names)


@pytest.mark.parametrize("names", [BASE, NOIR, LICENSED, CLIENT])
def test_actual_manifest_and_public_edge_accept_exact_layouts(tmp_path, names):
    dist = make_dist(tmp_path, names)
    manifest = build_os_asset_manifest(tmp_path)
    assert len(manifest["files"]) == len(names)
    for entry in manifest["files"]:
        data = (dist / entry["path"]).read_bytes()
        assert entry["byte_count"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["mime"] == os_asset_mimes(names)[entry["path"]]
    routes = asset_routes(manifest)
    assert set(routes) == {"/os/" if name == "index.html" else "/os/" + name for name in names}
    config = render(manifest, 49152)
    for route in routes:
        assert route in config
    assert config.count("reverse_proxy 127.0.0.1:49152") == 2
    assert "path /os/executive/context /os/executive/submit /os/executive/status" in config
    assert "/mcp" not in config


@pytest.mark.parametrize("fault", ["extra-directory", "missing-license", "extra-source-map", "symlink-license", "index-loads-lazy-chunk", "oversize-license", "empty-license"])
def test_real_manifest_retains_closed_topology_reference_and_byte_fences(tmp_path, fault):
    dist = make_dist(tmp_path)
    if fault == "extra-directory":
        (dist / "private").mkdir()
    elif fault == "missing-license":
        (dist / CLIENT[-1]).unlink()
    elif fault == "extra-source-map":
        (dist / "assets/SourceMarkdown-rich.js.map").write_text("private source")
    elif fault == "symlink-license":
        (dist / CLIENT[-1]).unlink()
        (dist / CLIENT[-1]).symlink_to(dist / CLIENT[-2])
    elif fault == "index-loads-lazy-chunk":
        (dist / "index.html").write_text('<script src="/os/assets/SourceMarkdown-rich.js"></script><link href="/os/assets/index-css.css">')
    elif fault == "oversize-license":
        (dist / CLIENT[-1]).write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    else:
        (dist / CLIENT[-1]).write_bytes(b"")
    with pytest.raises(ValueError):
        build_os_asset_manifest(tmp_path)


def test_captured_release_snapshot_uses_the_same_closed_owner(tmp_path):
    from ops.executive_os.os_release_assets import _capture_dist
    dist = make_dist(tmp_path)
    manifest, files = _capture_dist(tmp_path, sealed=False)
    assert manifest == build_os_asset_manifest(tmp_path)
    assert set(files) == set(CLIENT)
    assert files[CLIENT[-1]] == (dist / CLIENT[-1]).read_bytes()


def test_static_http_owner_serves_new_bytes_without_expanding_dynamic_routes(tmp_path):
    import httpx
    from integrations.executive_mcp.server import OsStaticApp
    dist = make_dist(tmp_path)
    manifest = build_os_asset_manifest(tmp_path)
    assets = {("/os/" if item["path"] == "index.html" else "/os/" + item["path"]):
        ((dist / item["path"]).read_bytes(), item["mime"]) for item in manifest["files"]}
    app = OsStaticApp(assets)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://example.test") as client:
            for name in CLIENT[9:]:
                response = await client.get("/os/" + name)
                assert response.status_code == 200
                assert response.content == (dist / name).read_bytes()
                assert response.headers["content-type"] == os_asset_mimes(CLIENT)[name]
                assert response.headers["x-content-type-options"] == "nosniff"
                assert "script-src 'self'" in response.headers["content-security-policy"]
            for route in ["/os/assets/foreign.js", "/os/third-party/private.key", "/os/third-party/", "/os/executive/submit", "/mcp"]:
                assert (await client.get(route)).status_code == 404
            assert (await client.post("/os/" + CLIENT[9])).status_code == 404
            assert (await client.get("/os/" + CLIENT[9] + "?x=1")).status_code == 404
            assert (await client.get("/os/assets/SourceMarkdown-rich%2ejs")).status_code == 404
            assert (await client.request("GET", "/os/" + CLIENT[9], content=b"body")).status_code == 400
    asyncio.run(check())


def test_license_mime_cannot_be_relabelled_executable(tmp_path):
    from integrations.executive_mcp.server import OsStaticApp
    dist = make_dist(tmp_path)
    manifest = build_os_asset_manifest(tmp_path)
    target = next(item for item in manifest["files"] if item["path"] == CLIENT[-1])
    target["mime"] = "text/javascript; charset=utf-8"
    with pytest.raises(ValueError):
        asset_routes(manifest)
    assets = {("/os/" if item["path"] == "index.html" else "/os/" + item["path"]):
        ((dist / item["path"]).read_bytes(), item["mime"]) for item in manifest["files"]}
    with pytest.raises(ValueError):
        OsStaticApp(assets)

"""Exact private-entry, Team and historical output through the closed owners.

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
PRIVATE = LICENSED + ["assets/private-entry-image.jpg"]
TEAM = PRIVATE + ["assets/CompanyWorkspace-team_js.js", "assets/CompanyWorkspace-team_css.css"]


def make_dist(root: Path, names=CLIENT):
    dist = root / "app/mastermind_os/dist"
    for name in names:
        path = dist / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("source:" + name).encode())
    (dist / "index.html").write_text('<script src="/os/assets/index-js.js"></script><link href="/os/assets/index-css.css">')
    return dist


@pytest.mark.parametrize("names", [BASE, NOIR, LICENSED, PRIVATE, CLIENT, TEAM])
def test_six_exact_supported_layouts_and_mime_sets(names):
    mimes = os_asset_mimes(names)
    assert set(mimes) == set(names)
    assert mimes["index.html"] == "text/html; charset=utf-8"
    assert mimes["assets/index-js.js"] == "text/javascript; charset=utf-8"
    assert os_asset_mimes(reversed(names)) == mimes
    if names in (PRIVATE, TEAM):
        assert mimes["assets/private-entry-image.jpg"] == "image/jpeg"
        assert mimes["third-party/deepseek-harness-LICENSE.txt"] == "text/plain; charset=utf-8"
    if names == TEAM:
        assert mimes[TEAM[-2]] == "text/javascript; charset=utf-8"
        assert mimes[TEAM[-1]] == "text/css; charset=utf-8"
    if names == CLIENT:
        assert mimes["assets/SourceMarkdown-rich.js"] == "text/javascript; charset=utf-8"
        assert mimes["assets/SourceMarkdown-rich.css"] == "text/css; charset=utf-8"
        assert mimes["third-party/deepseek-harness-LICENSE.txt"] == "text/plain; charset=utf-8"


@pytest.mark.parametrize("names,removed", [(names, removed) for names in (CLIENT, TEAM) for removed in names])
def test_every_required_member_is_required(names, removed):
    with pytest.raises(ValueError):
        os_asset_mimes([name for name in names if name != removed])


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


@pytest.mark.parametrize("names", [BASE, NOIR, LICENSED, PRIVATE, CLIENT, TEAM])
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
    # Five fixed branches: OS GET, legacy OS POST (64KB), the dedicated
    # source-operation POST branch (98304), and the two public MCP entrypoint
    # branches (RFC 9728 metadata GET, POST /mcp). Asset names only ever widen
    # the OS GET matcher; they cannot create or alter an MCP or source branch.
    assert config.count("reverse_proxy 127.0.0.1:49152") == 5
    assert "path /os/executive/context /os/executive/submit /os/executive/status" in config
    assert ("path /workspace/source-operation/prepare /workspace/source-operation/submit"
            " /workspace/source-operation/reconcile /workspace/source-operation/advance\n") in config
    assert ("path /.well-known/oauth-protected-resource/mcp"
            " /.well-known/oauth-protected-resource/mcp/coo\n") in config
    assert "path /mcp /mcp/coo\n" in config
    assert config.count("/mcp") == 4
    assert config.count("max_size 98304") == 1
    assert config.count("max_size 64KB") == 2
    assert config.count("header_up Host mcp.mastermind-x.com") == 4
    assert config.count("header_up Host 127.0.0.1") == 1


@pytest.mark.parametrize("fault", ["extra-directory", "missing-license", "extra-source-map", "symlink-license", "index-loads-lazy-chunk", "oversize-license", "empty-license"])
@pytest.mark.parametrize("names", [CLIENT, TEAM])
def test_real_manifest_retains_closed_topology_reference_and_byte_fences(tmp_path, fault, names):
    dist = make_dist(tmp_path, names)
    lazy_js = TEAM[-2] if names == TEAM else CLIENT[9]
    if fault == "extra-directory":
        (dist / "private").mkdir()
    elif fault == "missing-license":
        (dist / CLIENT[-1]).unlink()
    elif fault == "extra-source-map":
        (dist / (lazy_js + ".map")).write_text("private source")
    elif fault == "symlink-license":
        (dist / CLIENT[-1]).unlink()
        (dist / CLIENT[-1]).symlink_to(dist / CLIENT[-2])
    elif fault == "index-loads-lazy-chunk":
        (dist / "index.html").write_text(f'<script src="/os/{lazy_js}"></script><link href="/os/assets/index-css.css">')
    elif fault == "oversize-license":
        (dist / CLIENT[-1]).write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    else:
        (dist / CLIENT[-1]).write_bytes(b"")
    with pytest.raises(ValueError):
        build_os_asset_manifest(tmp_path)


@pytest.mark.parametrize("names", [CLIENT, PRIVATE, TEAM])
def test_captured_release_snapshot_uses_the_same_closed_owner(tmp_path, names):
    from ops.executive_os.os_release_assets import _capture_dist
    dist = make_dist(tmp_path, names)
    manifest, files = _capture_dist(tmp_path, sealed=False)
    assert manifest == build_os_asset_manifest(tmp_path)
    assert set(files) == set(names)
    assert all(files[name] == (dist / name).read_bytes() for name in names)
    assert {str(path.relative_to(dist)) for path in dist.rglob("*") if path.is_dir()} == {
        "assets", "licenses", "licenses/fonts", "third-party"}


@pytest.mark.parametrize("names", [CLIENT, PRIVATE, TEAM])
def test_static_http_owner_serves_new_bytes_without_expanding_dynamic_routes(tmp_path, names):
    import httpx
    from integrations.executive_mcp.server import OsStaticApp
    dist = make_dist(tmp_path, names)
    manifest = build_os_asset_manifest(tmp_path)
    assets = {("/os/" if item["path"] == "index.html" else "/os/" + item["path"]):
        ((dist / item["path"]).read_bytes(), item["mime"]) for item in manifest["files"]}
    app = OsStaticApp(assets)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://example.test") as client:
            for name in names[9:]:
                response = await client.get("/os/" + name)
                assert response.status_code == 200
                assert response.content == (dist / name).read_bytes()
                assert response.headers["content-type"] == os_asset_mimes(names)[name]
                assert response.headers["x-content-type-options"] == "nosniff"
                assert "script-src 'self'" in response.headers["content-security-policy"]
            for route in ["/os/assets/foreign.js", "/os/third-party/private.key", "/os/third-party/", "/os/executive/submit", "/mcp"]:
                assert (await client.get(route)).status_code == 404
            assert (await client.post("/os/" + names[-1])).status_code == 404
            assert (await client.get("/os/" + names[-1] + "?x=1")).status_code == 404
            assert (await client.get("/os/assets/SourceMarkdown-rich%2ejs")).status_code == 404
            assert (await client.get("/os/assets/private-entry-image%2ejpg")).status_code == 404
            assert (await client.get("/os/assets/CompanyWorkspace-team_js%2ejs")).status_code == 404
            assert (await client.request("GET", "/os/" + names[-1], content=b"body")).status_code == 400
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


@pytest.mark.parametrize("removed", PRIVATE)
def test_private_entry_profile_requires_each_member_or_complete_licensed11(removed):
    altered = [name for name in PRIVATE if name != removed]
    if removed == PRIVATE[-1]:
        assert os_asset_mimes(altered) == os_asset_mimes(LICENSED)
    else:
        with pytest.raises(ValueError):
            os_asset_mimes(altered)


@pytest.mark.parametrize("names", [
    PRIVATE + [PRIVATE[-1]], PRIVATE + ["assets/private-entry-second.jpg"],
    PRIVATE[:-1] + ["assets/private-entry-image.png"],
    PRIVATE[:-1] + ["assets/private-entry-image.jpg?x=1"],
    PRIVATE[:-1] + ["assets/private-entry-image.jpg#fragment"],
    PRIVATE[:-1] + ["/assets/private-entry-image.jpg"],
    PRIVATE[:-1] + ["assets/../private-entry-image.jpg"],
    PRIVATE[:-1] + ["assets/private-entry-image%2ejpg"],
    PRIVATE[:-1] + ["assets/private-entry-image.jpg\n"],
    PRIVATE[:-1] + ["assets/private-entry-.jpg"],
    BASE + NOIR[3:6] + [PRIVATE[-1]],
    NOIR + [PRIVATE[-1]],
    PRIVATE + ["assets/SourceMarkdown-rich.css"],
    CLIENT + [PRIVATE[-1]],
])
def test_private_entry_partial_raw_unlicensed_and_hybrid_sets_refuse(names):
    with pytest.raises(ValueError):
        os_asset_mimes(names)


def test_private_jpeg_mime_cannot_be_relabelled(tmp_path):
    from integrations.executive_mcp.server import OsStaticApp
    dist = make_dist(tmp_path, PRIVATE)
    manifest = build_os_asset_manifest(tmp_path)
    target = next(row for row in manifest["files"] if row["path"] == PRIVATE[-1])
    target["mime"] = "text/javascript; charset=utf-8"
    with pytest.raises(ValueError):
        asset_routes(manifest)
    assets = {("/os/" if row["path"] == "index.html" else "/os/" + row["path"]):
              ((dist / row["path"]).read_bytes(), row["mime"]) for row in manifest["files"]}
    with pytest.raises(ValueError):
        OsStaticApp(assets)


@pytest.mark.parametrize("name", [
    "assets/CompanyWorkspace-team_js.js.map", "assets/OtherFeature-team_js.js",
    "assets/CompanyWorkspace-team_js.js?x=1", "assets/CompanyWorkspace-team_js.js#fragment",
    "assets/../CompanyWorkspace-team_js.js", "assets/CompanyWorkspace-team_js%2ejs",
    "/assets/CompanyWorkspace-team_js.js", "assets/CompanyWorkspace-.js",
    "assets/CompanyWorkspace-team_js.js\n", "assets/CompanyWorkspace-team_js.js/extra",
    "assets/CompanyWorkspace-team_js.css", None,
])
def test_team_chunk_names_remain_closed(name):
    with pytest.raises(ValueError):
        os_asset_mimes(TEAM[:-2] + [name, TEAM[-1]])


@pytest.mark.parametrize("names", [
    TEAM + [TEAM[-1]], TEAM + ["assets/CompanyWorkspace-second.js"],
    TEAM[:-2] + [TEAM[-2], TEAM[-2]],
    TEAM[:-2] + [TEAM[-2], "assets/CompanyWorkspace-second.js"],
    LICENSED + TEAM[-2:], PRIVATE + CLIENT[9:11],
    TEAM + CLIENT[9:11],
])
def test_team_partial_duplicate_and_wrong_chunk_families_refuse(names):
    with pytest.raises(ValueError):
        os_asset_mimes(names)


@pytest.mark.parametrize("name", TEAM[-2:])
def test_team_chunks_cannot_be_symlinks_or_relabelled(tmp_path, name):
    from integrations.executive_mcp.server import OsStaticApp
    dist = make_dist(tmp_path, TEAM)
    manifest = build_os_asset_manifest(tmp_path)
    target = next(row for row in manifest["files"] if row["path"] == name)
    target["mime"] = "text/plain; charset=utf-8"
    with pytest.raises(ValueError):
        asset_routes(manifest)
    assets = {("/os/" if row["path"] == "index.html" else "/os/" + row["path"]):
              ((dist / row["path"]).read_bytes(), row["mime"]) for row in manifest["files"]}
    with pytest.raises(ValueError):
        OsStaticApp(assets)
    (dist / name).unlink()
    (dist / name).symlink_to(dist / "assets/index-js.js")
    with pytest.raises(ValueError, match="OS assets cannot be symlinks"):
        build_os_asset_manifest(tmp_path)

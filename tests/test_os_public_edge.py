import copy
import hashlib
import os

import pytest

from integrations.mastermind_executive_app.os_assets import os_asset_mimes
from ops.executive_os.os_public_edge import asset_routes, render, stage


def manifest(noir=False, notices=False):
    names = ["index.html", "assets/index-a.css", "assets/index-b.js"]
    if noir:
        names += ["assets/atelier-office-a.jpg", "assets/Manrope-Variable-a.ttf",
                  "assets/Inter-Variable-a.woff2", "licenses/fonts/Inter-OFL.txt",
                  "licenses/fonts/Manrope-OFL.txt", "licenses/fonts/Manrope-FONTLOG.txt"]
    if notices:
        names += ["third-party/deepseek-client-dependency-NOTICES.txt",
                  "third-party/deepseek-harness-LICENSE.txt"]
    return {"schema": "mastermind.os_assets.v1", "files": [
        {"path": name, "byte_count": 1, "sha256": "a" * 64, "mime": mime}
        for name, mime in os_asset_mimes(names).items()
    ]}


def test_authenticated_control_room_routes_are_exact_and_method_scoped():
    from ops.executive_os.os_public_edge import (
        GET_ROUTES, LEGACY_GET_ROUTES, POST_ROUTES, LEGACY_POST_ROUTES,
    )

    # The client and the MCP source already consume mission/v4. Requiring an
    # exact allowlist delta catches accidental omission without opening a
    # wildcard route or silently expanding the legacy installed profile.
    expected_get = {
        "/workspace/control-room/state/current",
        "/workspace/control-room/discover/current",
        "/workspace/mission/v4/current",
    }
    expected_post = {
        "/workspace/control-room/open",
        "/workspace/control-room/bind",
        "/workspace/control-room/unbind",
        "/workspace/control-room/refresh-builds",
    }
    assert set(GET_ROUTES) == set(LEGACY_GET_ROUTES) | expected_get
    assert set(POST_ROUTES) == set(LEGACY_POST_ROUTES) | expected_post
    assert len(GET_ROUTES) == len(set(GET_ROUTES))
    assert len(POST_ROUTES) == len(set(POST_ROUTES))
    assert set(GET_ROUTES).isdisjoint(POST_ROUTES)
    config = render(manifest(), 49152)
    get_branch, post_branch = config.split("    handle @get {", 1)[0], config.split("    handle @post {", 1)[0]
    assert get_branch.count("      path ") == 1
    assert post_branch.count("      path ") == 2
    # The rendered Caddy contract must match the closed Python route contract,
    # not merely contain a few exemplar paths. Query strings are not routes.
    caddy_get = set(get_branch.split("      path ", 1)[1].splitlines()[0].split())
    caddy_post = set(post_branch.rsplit("      path ", 1)[1].splitlines()[0].split())
    assert caddy_get == set(GET_ROUTES) | set(asset_routes(manifest()))
    assert caddy_post == set(POST_ROUTES)
    for route in expected_get:
        assert route in get_branch
    for route in expected_post:
        assert route not in get_branch
        assert route in post_branch
    for route in expected_get:
        assert route not in post_branch.split("    @post {", 1)[1]
    assert "      method GET" in get_branch
    assert "      method POST" in post_branch
    assert "max_size 64KB" in config
    assert "    abort" in config


@pytest.mark.parametrize("noir,notices,count", [(False, False, 3), (True, False, 9), (True, True, 11)])
def test_all_accepted_topologies_have_exact_routes(noir, notices, count):
    value = manifest(noir, notices)
    routes = asset_routes(value)
    assert len(routes) == count
    config = render(value, 49152)
    assert config.count("reverse_proxy 127.0.0.1:49152") == 2
    assert "path /os/executive/context /os/executive/submit /os/executive/status" in config
    assert "max_size 64KB" in config
    assert config.rstrip().endswith("abort\n  }\n}")
    assert "/mcp" not in config
    for route in routes:
        assert route in config
    if notices:
        for name in ("deepseek-client-dependency-NOTICES.txt", "deepseek-harness-LICENSE.txt"):
            assert "/os/third-party/" + name in routes
            item = next(item for item in value["files"] if item["path"] == "third-party/" + name)
            assert item["mime"] == "text/plain; charset=utf-8"


@pytest.mark.parametrize("damage", ["missing", "renamed", "extra", "duplicate", "traversal", "mime"])
def test_notice_layout_remains_closed(damage):
    value = manifest(True, True)
    if damage == "missing":
        value["files"].pop()
    elif damage == "renamed":
        value["files"][-1]["path"] = "third-party/other-LICENSE.txt"
    elif damage == "extra":
        extra = copy.deepcopy(value["files"][-1])
        extra["path"] = "third-party/extra.txt"
        value["files"].append(extra)
    elif damage == "duplicate":
        value["files"][-1] = copy.deepcopy(value["files"][-2])
    elif damage == "traversal":
        value["files"][-1]["path"] = "third-party/../deepseek-harness-LICENSE.txt"
    else:
        value["files"][-1]["mime"] = "text/javascript; charset=utf-8"
    with pytest.raises(ValueError):
        render(value, 49152)


def test_legacy_plus_notices_is_not_an_admitted_five_file_layout():
    with pytest.raises(ValueError, match="fixed OS asset set"):
        manifest(False, True)


@pytest.mark.parametrize("path", [
    "assets/index-x.css\n}\n:80 { respond hacked",
    "assets/index-x.css *", "../index.html", "/index.html", "assets/../index-x.css",
    "assets/index-x.css?x=1", "assets/index-x.css#x", "assets\\index-x.css",
    "licenses/fonts/unknown.txt",
])
def test_manifest_path_cannot_inject_or_expand_caddy_routes(path):
    value = manifest()
    value["files"][1]["path"] = path
    with pytest.raises(ValueError):
        render(value, 49152)


@pytest.mark.parametrize("field,value", [
    ("byte_count", True), ("byte_count", 0), ("byte_count", 4 * 1024 * 1024 + 1),
    ("sha256", "bad"), ("mime", "text/plain"), ("path", None),
])
def test_metadata_is_closed(field, value):
    data = manifest()
    data["files"][0][field] = value
    with pytest.raises(ValueError):
        render(data, 49152)


def test_duplicate_and_extra_schema_fields_refuse():
    data = manifest()
    data["files"].append(copy.deepcopy(data["files"][0]))
    with pytest.raises(ValueError):
        render(data, 49152)
    data = manifest()
    data["command"] = "unsafe"
    with pytest.raises(ValueError):
        render(data, 49152)


@pytest.mark.parametrize("port", [True, "49152", 8443, 49151, 50201])
def test_only_reserved_loopback_relay_range(port):
    with pytest.raises(ValueError):
        render(manifest(), port)


def test_staging_is_exclusive_and_receipt_observes_exact_bytes(tmp_path):
    output = tmp_path / "os.caddy"
    receipt = stage(manifest=manifest(True), relay_port=49152, output=output)
    assert receipt["installed"] is False
    assert receipt["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert output.stat().st_mode & 0o777 == 0o600
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        stage(manifest=manifest(), relay_port=49152, output=output)
    assert output.read_bytes() == before


def test_dangling_symlink_and_writable_output_directory_refuse(tmp_path):
    output = tmp_path / "os.caddy"
    output.symlink_to(tmp_path / "absent")
    with pytest.raises(FileExistsError):
        stage(manifest=manifest(), relay_port=49152, output=output)
    assert not (tmp_path / "absent").exists()
    os.chmod(tmp_path, 0o777)
    try:
        with pytest.raises(ValueError):
            stage(manifest=manifest(), relay_port=49152, output=tmp_path / "other")
    finally:
        os.chmod(tmp_path, 0o700)

import copy
import hashlib
import os

import pytest

from integrations.mastermind_executive_app.os_assets import os_asset_mimes
from ops.executive_os.os_public_edge import (
    MCP_MAX_BODY, MCP_METADATA_ROUTE, MCP_ROUTES, asset_routes, render, stage,
)


def manifest(noir=False):
    names = ["index.html", "assets/index-a.css", "assets/index-b.js"]
    if noir:
        names += ["assets/atelier-office-a.jpg", "assets/Manrope-Variable-a.ttf",
                  "assets/Inter-Variable-a.woff2", "licenses/fonts/Inter-OFL.txt",
                  "licenses/fonts/Manrope-OFL.txt", "licenses/fonts/Manrope-FONTLOG.txt"]
    return {"schema": "mastermind.os_assets.v1", "files": [
        {"path": name, "byte_count": 1, "sha256": "a" * 64, "mime": mime}
        for name, mime in os_asset_mimes(names).items()
    ]}


@pytest.mark.parametrize("noir", [False, True])
def test_both_accepted_topologies_have_exact_routes(noir):
    value = manifest(noir)
    routes = asset_routes(value)
    assert len(routes) == (9 if noir else 3)
    config = render(value, 49152)
    # OS GET, OS POST, MCP metadata GET and MCP POST all share the one relay.
    assert config.count("reverse_proxy 127.0.0.1:49152") == 4
    assert "path /os/executive/context /os/executive/submit /os/executive/status" in config
    assert config.count("max_size 64KB") == 2
    assert config.rstrip().endswith("abort\n  }\n}")
    for route in routes:
        assert route in config


@pytest.mark.parametrize("noir", [False, True])
def test_public_mcp_entrypoint_is_two_exact_branches_before_abort(noir):
    config = render(manifest(noir), 49152)
    # RFC 9728 metadata is GET-only; the Streamable HTTP endpoint is POST-only.
    assert f"method GET\n      path {MCP_METADATA_ROUTE}\n" in config
    assert "method POST\n      path /mcp\n" in config
    assert MCP_METADATA_ROUTE == "/.well-known/oauth-protected-resource/mcp"
    assert MCP_ROUTES == ("/mcp",)
    # No wildcard or prefix match can widen the public surface.
    assert "/mcp*" not in config and "/mcp/" not in config and "/.well-known/*" not in config
    # The /mcp branch alone presents a loopback Host (the gateway SDK fence admits
    # only loopback hosts); every other branch keeps the public host.
    assert config.count("header_up Host 127.0.0.1\n") == 1
    assert config.count("header_up Host mcp.mastermind-x.com\n") == 3
    # The /mcp branch caps the body at the gateway's own ceiling; no other
    # branch gained a larger or unbounded body.
    mcp_branch = config.split("handle @mcp {")[1]
    assert mcp_branch.index("max_size 64KB") < mcp_branch.index("reverse_proxy")
    assert MCP_MAX_BODY == 64000
    # The Host counts above would also pass if the two values swapped branches, so
    # pin each Host inside its own branch slice.
    assert "header_up Host 127.0.0.1\n" in mcp_branch
    assert "header_up Host mcp.mastermind-x.com\n" not in mcp_branch
    meta_branch = config.split("handle @mcpmeta {")[1].split("@mcp {")[0]
    assert "header_up Host mcp.mastermind-x.com\n" in meta_branch
    assert "header_up Host 127.0.0.1\n" not in meta_branch
    for marker, following in (("handle @get {", "@post {"), ("handle @post {", "@mcpmeta {")):
        os_branch = config.split(marker)[1].split(following)[0]
        assert "header_up Host mcp.mastermind-x.com\n" in os_branch
        assert "header_up Host 127.0.0.1\n" not in os_branch
    # Order is part of the contract: both MCP branches precede the terminal abort,
    # after the original GET and POST OS branches.
    order = [config.index(marker) for marker in
             ("handle @get {", "handle @post {", "handle @mcpmeta {", "handle @mcp {", "\n    abort\n")]
    assert order == sorted(order)
    # Caddy performs no authentication or token handling on any branch.
    for forbidden in ("basicauth", "forward_auth", "jwt", "authorization", "Authorization"):
        assert forbidden not in config
    # Untrusted forwarding and CDN client-identity headers are stripped on every
    # branch and forwarding identity is rewritten to loopback/https.
    for header in ("Forwarded", "X-Forwarded-Host", "X-Forwarded-Port", "X-Real-IP",
                   "CF-Connecting-IP", "EO-Connecting-IP", "EO-Client-IP"):
        assert config.count(f"header_up -{header}\n") == 4
    assert config.count("header_up X-Forwarded-Proto https\n") == 4
    assert config.count("header_up X-Forwarded-For 127.0.0.1\n") == 4


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
    assert receipt["mcp"] == {"get": [MCP_METADATA_ROUTE], "post": list(MCP_ROUTES)}
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

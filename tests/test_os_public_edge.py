import copy
import hashlib
import json
import os
import shutil
import subprocess

import pytest

from integrations.mastermind_executive_app.os_assets import os_asset_mimes
from ops.executive_os.os_public_edge import (
    COMPLETE_MCP_METADATA_ROUTES, COMPLETE_MCP_ROUTES, GET_ROUTES, LEGACY_POST_ROUTES,
    MCP_COO_METADATA_ROUTE, MCP_COO_ROUTE, MCP_MAX_BODY, MCP_METADATA_ROUTE, MCP_METADATA_ROUTES,
    MCP_ROUTES, POST_ROUTES, INCUMBENT_POST_ROUTES, SOURCE_POST_ROUTES, SOURCE_MAX_BODY,
    asset_routes, render, stage,
)


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


def test_authenticated_native_and_control_room_routes_are_exact_and_method_scoped():
    from ops.executive_os.os_public_edge import (
        GET_ROUTES, INCUMBENT_GET_ROUTES, POST_ROUTES, INCUMBENT_POST_ROUTES,
    )

    # The client and the MCP source already consume mission/v4. Requiring an
    # exact allowlist delta catches accidental omission without opening a
    # wildcard route or silently expanding the legacy installed profile.
    expected_get = {
        "/workspace/control-room/state/current",
        "/workspace/control-room/discover/current",
        "/workspace/mission/v4/current",
        "/workspace/fabric/catalog/current",
        "/workspace/fabric/status/current",
        "/workspace/project-plan/current",
        "/workspace/project-journal/current",
        "/workspace/autonomy/current",
        "/workspace/project-session/current",
        "/workspace/resources/capacity/current",
        "/workspace/project-direction/current",
        "/workspace/project-admission/current",
        "/workspace/project-instructions/current",
        "/workspace/project-access/current",
        "/workspace/project-admission/operation",
        "/workspace/projects/archive/current",
        "/workspace/project-knowledge/current",
        "/workspace/project-memory/current",
        "/workspace/project-source/current",
        "/workspace/source-operation/context",
        "/workspace/source-operation/operation",
        "/workspace/source-operation/options",
        "/workspace/resources/host-observation/current",
        "/workspace/mission-result/current",
        "/workspace/native-draft-identity/current",
        "/workspace/byok/roles/current",
        "/workspace/instruction-admission/current",
        "/workspace/instruction-admission/operation",
    }
    expected_post = {
        "/workspace/control-room/open",
        "/workspace/control-room/bind",
        "/workspace/control-room/unbind",
        "/workspace/control-room/refresh-builds",
        "/workspace/project-admission/pause",
        "/workspace/project-admission/resume",
        "/workspace/instruction-admission/pause",
        "/os/executive/project-execution/preview",
        "/os/executive/project-execution/submit",
        "/os/executive/project-execution/status",
        "/os/executive/session/project-executions",
        "/os/executive/session/project-execution-read",
        "/os/executive/project-planning/submit",
        "/os/executive/project-planning/status",
        "/os/executive/project-planning/result",
        "/os/executive/project-planning/consume",
        "/os/executive/project-planning/prepare_proposal",
        "/os/executive/session/history-context",
        "/os/executive/session/conversations",
        "/os/executive/session/conversation-read",
        "/os/executive/session/fresh-conversations",
        "/os/executive/session/fresh-conversation-read",
        "/os/executive/conversation/preview",
        "/os/executive/conversation/create",
        "/os/executive/conversation/status",
        "/os/executive/conversation/read",
        "/os/executive/conversation/consume",
        "/os/executive/conversation/turn",
        "/os/executive/conversation/turn/status",
        "/os/executive/conversation/turn/read",
        "/os/executive/conversation/consume/status",
        "/os/executive/conversation/turn/preview",
        "/os/executive/session/send",
        "/os/executive/direct-native/result",
        "/os/executive/direct-native/consume",
        "/os/executive/direct-native/correction",
        "/os/executive/company-priorities",
    }
    assert set(GET_ROUTES) == set(INCUMBENT_GET_ROUTES) | expected_get
    assert set(POST_ROUTES) == set(INCUMBENT_POST_ROUTES) | expected_post
    assert len(GET_ROUTES) == len(set(GET_ROUTES))
    assert len(POST_ROUTES) == len(set(POST_ROUTES))
    assert set(GET_ROUTES).isdisjoint(POST_ROUTES)
    config = render(manifest(), 49152)
    get_branch = config.split("    @get {", 1)[1].split("    }", 1)[0]
    post_branch = config.split("    @post {", 1)[1].split("    }", 1)[0]
    source_branch = config.split("    @sourcepost {", 1)[1].split("    }", 1)[0]
    assert get_branch.count("      path ") == 1
    assert post_branch.count("      path ") == 1
    assert source_branch.count("      path ") == 1
    assert source_branch.split("      path ", 1)[1].splitlines()[0].split() == list(SOURCE_POST_ROUTES)
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
        assert route not in post_branch
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
    # OS GET, legacy POST, source POST and both MCP branches share one relay.
    assert config.count("reverse_proxy 127.0.0.1:49152") == 5
    # All public POSTs are explicit paths. The historical reader tuple stays
    # exact; qualified Session SEND is a separate final-profile addition.
    assert "path " + " ".join(POST_ROUTES) + "\n" in config
    assert INCUMBENT_POST_ROUTES == LEGACY_POST_ROUTES + (
        "/os/executive/session/context", "/os/executive/session/reply",
        "/os/executive/session/references")
    assert config.count("/os/executive/session/send") == 1
    assert config.count("max_size 64KB") == 2
    assert config.count("max_size 98304") == 1
    assert SOURCE_MAX_BODY == 98304
    assert config.rstrip().endswith("abort\n  }\n}")
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


@pytest.mark.parametrize("noir", [False, True])
def test_public_mcp_entrypoint_is_two_exact_branches_before_abort(noir):
    config = render(manifest(noir), 49152)
    # RFC 9728 metadata is GET-only; the Streamable HTTP endpoint is POST-only.
    # The complete CEO+COO profile extends the same two exact method branches:
    # one metadata list, one transport list, never a merged branch.
    assert MCP_METADATA_ROUTE == "/.well-known/oauth-protected-resource/mcp"
    assert MCP_COO_METADATA_ROUTE == "/.well-known/oauth-protected-resource/mcp/coo"
    assert MCP_ROUTES == ("/mcp",)
    assert MCP_COO_ROUTE == "/mcp/coo"
    assert MCP_METADATA_ROUTES == (MCP_METADATA_ROUTE,)
    assert COMPLETE_MCP_METADATA_ROUTES == (MCP_METADATA_ROUTE, MCP_COO_METADATA_ROUTE)
    assert COMPLETE_MCP_ROUTES == ("/mcp", "/mcp/coo")
    assert f"method GET\n      path {MCP_METADATA_ROUTE} {MCP_COO_METADATA_ROUTE}\n" in config
    assert f"method POST\n      path {MCP_ROUTES[0]} {MCP_COO_ROUTE}\n" in config
    # Metadata and transport stay separate: one GET matcher, one POST matcher,
    # neither carrying the other's method or the other's paths.
    metadata_line = f"path {MCP_METADATA_ROUTE} {MCP_COO_METADATA_ROUTE}\n"
    transport_line = f"path {MCP_ROUTES[0]} {MCP_COO_ROUTE}\n"
    assert config.count(metadata_line) == 1 and config.count(transport_line) == 1
    assert config.count("method GET\n") == 2 and config.count("method POST\n") == 3
    # No wildcard or prefix match can widen the public surface. Caddy's path
    # matcher is exact without a wildcard, so each token must be a literal.
    matcher_paths = [line.split("path ", 1)[1].split() for line in config.splitlines()
                     if line.strip().startswith("path ")]
    assert len(matcher_paths) == 5
    for tokens in matcher_paths:
        for token in tokens:
            assert "*" not in token, token
    assert "/.well-known/*" not in config
    # The /mcp branch alone presents a loopback Host (the gateway SDK fence admits
    # only loopback hosts); every other branch keeps the public host.
    assert config.count("header_up Host 127.0.0.1\n") == 1
    assert config.count("header_up Host mcp.mastermind-x.com\n") == 4
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
    for marker, following in (("handle @get {", "@post {"), ("handle @post {", "@sourcepost {"),
                              ("handle @sourcepost {", "@mcpmeta {")):
        os_branch = config.split(marker)[1].split(following)[0]
        assert "header_up Host mcp.mastermind-x.com\n" in os_branch
        assert "header_up Host 127.0.0.1\n" not in os_branch
    # Order is part of the contract: both MCP branches precede the terminal abort,
    # after the original GET and POST OS branches.
    order = [config.index(marker) for marker in
             ("handle @get {", "handle @post {", "handle @sourcepost {", "handle @mcpmeta {", "handle @mcp {", "\n    abort\n")]
    assert order == sorted(order)
    # Caddy performs no authentication or token handling on any branch.
    for forbidden in ("basicauth", "forward_auth", "jwt", "authorization", "Authorization"):
        assert forbidden not in config
    # Untrusted forwarding and CDN client-identity headers are stripped on every
    # branch and forwarding identity is rewritten to loopback/https.
    for header in ("Forwarded", "X-Forwarded-Host", "X-Forwarded-Port", "X-Real-IP",
                   "CF-Connecting-IP", "EO-Connecting-IP", "EO-Client-IP"):
        assert config.count(f"header_up -{header}\n") == 5
    assert config.count("header_up X-Forwarded-Proto https\n") == 5
    assert config.count("header_up X-Forwarded-For 127.0.0.1\n") == 5


@pytest.mark.parametrize("damage", [
    "ceo-only-metadata", "ceo-only-transport", "extra-metadata-path",
    "extra-transport-path", "wildcard-metadata", "dropped-metadata",
])
def test_render_refuses_a_template_without_the_complete_mcp_path_lists(tmp_path, monkeypatch, damage):
    """The renderer checks the complete intended lists, not placeholder counts.

    A template that still carries the CEO-only pair, or that widens either
    list, must not render: the public surface is fixed by the owner, never by
    the template text.
    """
    from ops.executive_os import os_public_edge as edge
    original = edge._TEMPLATE
    template = original.read_text(encoding="utf-8")
    metadata = " ".join(COMPLETE_MCP_METADATA_ROUTES)
    transport = " ".join(COMPLETE_MCP_ROUTES)
    if damage == "ceo-only-metadata":
        template = template.replace(f"path {metadata}\n", f"path {MCP_METADATA_ROUTE}\n")
    elif damage == "ceo-only-transport":
        template = template.replace(f"path {transport}\n", f"path {MCP_ROUTES[0]}\n")
    elif damage == "extra-metadata-path":
        template = template.replace(
            f"path {metadata}\n", f"path {metadata} /.well-known/oauth-protected-resource/mcp/extra\n")
    elif damage == "extra-transport-path":
        template = template.replace(f"path {transport}\n", f"path {transport} /mcp/extra\n")
    elif damage == "wildcard-metadata":
        template = template.replace(f"path {metadata}\n",
                                    "path /.well-known/oauth-protected-resource/*\n")
    else:
        template = template.replace(f"path {metadata}\n", "")
    assert template != original.read_text(encoding="utf-8")
    damaged = tmp_path / "damaged.caddy.template"
    damaged.write_text(template, encoding="utf-8")
    monkeypatch.setattr(edge, "_TEMPLATE", damaged)
    with pytest.raises(ValueError, match="template differs"):
        render(manifest(), 49152)
    # The undamaged template still renders, so the guard is not a blanket refusal.
    monkeypatch.setattr(edge, "_TEMPLATE", original)
    assert render(manifest(), 49152)


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
    assert receipt["mcp"] == {"get": list(COMPLETE_MCP_METADATA_ROUTES),
                              "post": list(COMPLETE_MCP_ROUTES)}
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



@pytest.mark.parametrize("noir", [False, True])
def test_real_caddy_adapter_preserves_exact_read_only_edge_routes(tmp_path, noir):
    """Native adapter proof, not a Caddy reload or live-host admission.

    Skip when Caddy is not installed on a CI runner, while preserving the
    pure-renderer and JSON-transition tests on all hosts.
    """
    executable = shutil.which("caddy")
    if executable is None:
        pytest.skip("Caddy binary absent: inert native-adapter qualification unavailable")
    caddyfile = tmp_path / "r2-read-only-edge.caddy"
    caddyfile.write_text(render(manifest(noir), 49152), encoding="utf-8")
    actual = subprocess.run(
        [executable, "adapt", "--config", str(caddyfile), "--adapter", "caddyfile"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=12, check=False,
    )
    assert actual.returncode == 0, actual.stderr[:1000]
    config = json.loads(actual.stdout)
    servers = config["apps"]["http"]["servers"]
    assert len(servers) == 1

    route_matchers = []
    matched_routes = []
    def visit(node):
        if type(node) is dict:
            if "match" in node and "handle" in node:
                for match in node["match"]:
                    if "method" in match:
                        route_matchers.append(match)
                        matched_routes.append(node)
            for child in node.values():
                visit(child)
        elif type(node) is list:
            for child in node:
                visit(child)
    visit(servers)
    # Three OS branches plus the two public-MCP branches, nothing else.
    assert len(route_matchers) == 5
    assert all(set(match) == {"method", "path"} for match in route_matchers)
    by_paths = {(tuple(match["method"]), tuple(match["path"])): match for match in route_matchers}
    assert (("POST",), tuple(POST_ROUTES)) in by_paths
    assert (("POST",), tuple(SOURCE_POST_ROUTES)) in by_paths
    assert (("GET",), tuple(COMPLETE_MCP_METADATA_ROUTES)) in by_paths
    assert (("POST",), tuple(COMPLETE_MCP_ROUTES)) in by_paths
    assert POST_ROUTES.count("/os/executive/session/send") == 1
    os_get = [match for match in route_matchers
              if match["method"] == ["GET"] and match["path"] != list(COMPLETE_MCP_METADATA_ROUTES)]
    assert len(os_get) == 1
    assert set(os_get[0]["path"]) == set(GET_ROUTES) | set(asset_routes(manifest(noir)))
    assert config["apps"]["http"]["servers"]

    # Inspect the actual Caddy adapter's nested handlers, not a hand-built JSON
    # approximation. The larger body cap is confined to the dedicated source
    # branch; both legacy POST branches retain their decimal 64KB cap.
    def handlers(node, kind):
        if type(node) is dict:
            found = [node] if node.get("handler") == kind else []
            return found + [item for child in node.values() for item in handlers(child, kind)]
        if type(node) is list:
            return [item for child in node for item in handlers(child, kind)]
        return []

    for route in matched_routes:
        match = route["match"][0]
        paths = match["path"]
        bodies = handlers(route["handle"], "request_body")
        expected_cap = (SOURCE_MAX_BODY if paths == list(SOURCE_POST_ROUTES)
                        else MCP_MAX_BODY if match["method"] == ["POST"] else None)
        assert [body["max_size"] for body in bodies] == ([] if expected_cap is None else [expected_cap])
        proxies = handlers(route["handle"], "reverse_proxy")
        assert len(proxies) == 1
        assert proxies[0]["upstreams"] == [{"dial": "127.0.0.1:49152"}]
        headers = proxies[0]["headers"]["request"]
        assert headers["set"]["Host"] == (["127.0.0.1"] if paths == list(COMPLETE_MCP_ROUTES)
                                           else ["mcp.mastermind-x.com"])
        assert set(headers["delete"]) == {
            "Forwarded", "X-Forwarded-Host", "X-Forwarded-Port", "X-Real-IP",
            "CF-Connecting-IP", "EO-Connecting-IP", "EO-Client-IP"}

    # Feed that real, current six-branch adapter topology back through the
    # transition planner. It must preserve the source/MCP handlers and all
    # surrounding Caddy configuration exactly, changing only qualified assets.
    from ops.executive_os.os_public_edge_transition import prepare_config, final_config
    current = manifest(noir)
    candidate = copy.deepcopy(current)
    for item in candidate["files"]:
        item["path"] = item["path"].replace("index-a.css", "index-next.css").replace("index-b.js", "index-next.js")
        if item["path"] == "index.html" or "index-next" in item["path"]:
            item["sha256"] = "b" * 64
    original = copy.deepcopy(config)
    old_get = os_get[0]["path"]
    for maker, expected_paths in (
        (prepare_config, sorted(set(GET_ROUTES) | set(asset_routes(current)) | set(asset_routes(candidate)))),
        (final_config, sorted(set(GET_ROUTES) | set(asset_routes(candidate)))),
    ):
        changed = maker(fullconfig=config, current_manifest=current,
                        candidate_manifest=candidate, relay_port=49152)
        expected = copy.deepcopy(config)
        def replace_get(node):
            if type(node) is dict:
                if node.get("match") == [{"method": ["GET"], "path": old_get}]:
                    node["match"][0]["path"] = expected_paths
                    return 1
                return sum(replace_get(child) for child in node.values())
            if type(node) is list:
                return sum(replace_get(child) for child in node)
            return 0
        assert replace_get(expected) == 1
        assert changed == expected
    assert config == original

def test_admission_transition_keeps_exact_predecessor_and_no_partial_upgrade():
    from ops.executive_os.os_public_edge import PRE_PROJECT_ADMISSION_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES, TRANSITION_ROUTE_PROFILES
    assert (PRE_PROJECT_ADMISSION_GET_ROUTES,PRE_PROJECT_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert (GET_ROUTES,POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert (GET_ROUTES,PRE_PROJECT_ADMISSION_POST_ROUTES) not in TRANSITION_ROUTE_PROFILES
    assert (PRE_PROJECT_ADMISSION_GET_ROUTES,POST_ROUTES) not in TRANSITION_ROUTE_PROFILES
    assert '/workspace/project-admission/current' not in POST_ROUTES
    assert '/workspace/project-admission/pause' not in GET_ROUTES


def test_instruction_read_profile_preserves_old_exact_profile_and_adds_only_get():
    from ops.executive_os.os_public_edge import PRE_PROJECT_INSTRUCTIONS_GET_ROUTES,PRE_INSTRUCTION_ADMISSION_GET_ROUTES,PRE_INSTRUCTION_ADMISSION_POST_ROUTES,TRANSITION_ROUTE_PROFILES
    assert PRE_INSTRUCTION_ADMISSION_GET_ROUTES==PRE_PROJECT_INSTRUCTIONS_GET_ROUTES+('/workspace/project-instructions/current',)
    assert (PRE_PROJECT_INSTRUCTIONS_GET_ROUTES,PRE_INSTRUCTION_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert (PRE_INSTRUCTION_ADMISSION_GET_ROUTES,PRE_INSTRUCTION_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert '/workspace/project-instructions/current' not in POST_ROUTES
    assert not any('/workspace/project-instructions/pause' in routes for profile in TRANSITION_ROUTE_PROFILES for routes in profile)


def test_project_access_adds_one_fixed_read_and_preserves_full_instruction_predecessor():
    from ops.executive_os.os_public_edge import (PRE_PROJECT_ACCESS_GET_ROUTES,TRANSITION_ROUTE_PROFILES,
        PRE_JOURNEY_GET_ROUTES,PRE_JOURNEY_POST_ROUTES)
    assert PRE_JOURNEY_GET_ROUTES==PRE_PROJECT_ACCESS_GET_ROUTES+('/workspace/project-access/current',)
    assert (PRE_PROJECT_ACCESS_GET_ROUTES,PRE_JOURNEY_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert '/workspace/project-access/current' not in POST_ROUTES
    assert not any('/workspace/project-access/pause' in routes for profile in TRANSITION_ROUTE_PROFILES for routes in profile)

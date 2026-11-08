import copy
import hashlib
import json
import os
import sys

import pytest

from integrations.mastermind_executive_app.os_assets import os_asset_mimes
from ops.executive_os import os_public_edge_transition as module
from ops.executive_os.os_public_edge import (
    COMPLETE_MCP_METADATA_ROUTES, COMPLETE_MCP_ROUTES, GET_ROUTES, HOST, LEGACY_GET_ROUTES,
    LEGACY_POST_ROUTES, MCP_COO_METADATA_ROUTE, MCP_COO_ROUTE, MCP_MAX_BODY, MCP_METADATA_ROUTE,
    MCP_METADATA_ROUTES, MCP_ROUTES, POST_ROUTES, asset_routes,
    INCUMBENT_GET_ROUTES, INCUMBENT_POST_ROUTES, CONTROL_ROOM_LEGACY_GET_ROUTES,
    CONTROL_ROOM_GET_ROUTES, CONTROL_ROOM_POST_ROUTES, COMPOSED_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES,
    SOURCE_CONTEXT_GET_ROUTES, SOURCE_POST_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES,
    PRE_DIRECT_NATIVE_GET_ROUTES, PRE_DIRECT_NATIVE_POST_ROUTES, DIRECT_NATIVE_POST_ROUTES,
)
from ops.executive_os.os_public_edge_transition import (
    FINAL_NAME, PLAN_NAME, PREPARE_NAME, final_config, plan, prepare_config,
    preparation_complete, restart_diagnostic, stage_transition,
)

OLD_SHA = "b" * 40
NEW_SHA = "c" * 40


def manifest(suffix, index_sha="a" * 64, asset_sha="a" * 64):
    names = ["index.html", f"assets/index-{suffix}.css", f"assets/index-{suffix}.js"]
    return {"schema": "mastermind.os_assets.v1", "files": [
        {"path": name, "byte_count": 1,
         "sha256": index_sha if name == "index.html" else asset_sha, "mime": mime}
        for name, mime in os_asset_mimes(names).items()
    ]}


OLD = manifest("DrspFhr6")
NEW = manifest("Br9E9bcG", index_sha="b" * 64, asset_sha="c" * 64)


def proxy(port=49152):
    return {"handler": "reverse_proxy", "upstreams": [{"dial": f"127.0.0.1:{port}"}],
            "headers": {"request": {
                "delete": ["Forwarded", "X-Forwarded-Host", "X-Forwarded-Port", "X-Real-IP",
                           "CF-Connecting-IP", "EO-Connecting-IP", "EO-Client-IP"],
                "set": {"Host": [HOST], "X-Forwarded-Proto": ["https"],
                        "X-Forwarded-For": ["127.0.0.1"]}}},
            "transport": {"protocol": "http"}}


def host_route(get_paths, port=49152, hosts=None):
    return {
        "match": [{"host": [HOST] if hosts is None else hosts}],
        "handle": [{"handler": "subroute", "routes": [
            {"match": [{"method": ["GET"], "path": list(get_paths)}], "handle": [proxy(port)]},
            {"match": [{"method": ["POST"], "path": list(PRE_INSTRUCTION_ADMISSION_POST_ROUTES)}],
             "handle": [{"handler": "request_body", "max_size": 64000}, proxy(port)]},
            {"handle": [{"handler": "static_response", "abort": True}]},
        ]}],
        "terminal": True,
    }


def source_branch(port=49152, group=None):
    # Independent expected dedicated branch; do not use the production builder.
    handler = proxy(port)
    handler.pop("transport")  # Caddy's default HTTP proxy representation.
    value = {"match": [{"method": ["POST"], "path": list(SOURCE_POST_ROUTES)}],
             "handle": [{"handler": "request_body", "max_size": 98304}, handler]}
    if group is not None:
        value["group"] = group
    return value


NATIVE_PATHS = tuple("/os/executive/conversation/v2/" + operation
    for operation in ("preview", "create", "status", "read", "recover",
        "consume", "consume/status", "turn/preview", "turn", "turn/status",
        "turn/read", "turn/recover", "resume/preview", "resume",
        "resume/status", "stop", "stop/status"))


def native_branch(port=49152, group=None):
    # Independent expected branch: do not use the production constructor.
    handler = proxy(port)
    handler.pop("transport")
    value = {"match": [{"method": ["POST"], "path": list(NATIVE_PATHS)}],
             "handle": [{"handler": "request_body", "max_size": 524288}, handler]}
    if group is not None:
        value["group"] = group
    return value


def expect_native_upgrade(branches):
    branches.insert(len(branches) - 1, native_branch(group=branches[1].get("group")))


def expect_source_upgrade(branches):
    branches.insert(2, source_branch(group=branches[1].get("group")))


def expect_complete_mcp(branches):
    """Give the public-MCP matchers the complete CEO+COO path lists.

    Only the two fixed path lists change; every handler, Host, header list and
    body cap on those branches is preserved.
    """
    found = 0
    for branch in branches:
        match = branch.get("match")
        if not match or type(match[0]) is not dict:
            continue
        method, paths = match[0].get("method"), match[0].get("path")
        if method == ["GET"] and paths and paths[0].startswith("/.well-known/"):
            match[0]["path"] = list(COMPLETE_MCP_METADATA_ROUTES)
            found += 1
        elif method == ["POST"] and paths and paths[0] == "/mcp":
            match[0]["path"] = list(COMPLETE_MCP_ROUTES)
            found += 1
    assert found == 2, "the public-MCP pair must be present exactly once"


def other_site(host="workspace.mastermind-x.com"):
    return {"match": [{"host": [host]}],
            "handle": [{"handler": "subroute", "routes": [
                {"match": [{"path": ["/healthz"]}],
                 "handle": [{"handler": "static_response", "body": "ok"}]}]}]}


def fullconfig(old=OLD, port=49152, site=None, routes=None):
    get_paths = sorted(list(SOURCE_CONTEXT_GET_ROUTES) + list(asset_routes(old)))
    site = host_route(get_paths, port) if site is None else site
    servers = {"srv0": {"listen": [":443"],
                        "routes": [site, other_site()] if routes is None else routes}}
    return {"admin": {"listen": ["localhost:2019"]},
            "apps": {"http": {"servers": servers},
                     "tls": {"certificates": {"automate": [HOST]}}}}


def site_of(config, server="srv0", index=0):
    return config["apps"]["http"]["servers"][server]["routes"][index]


def inner_of(config):
    return site_of(config)["handle"][0]["routes"]


def get_paths_of(config):
    return inner_of(config)[0]["match"][0]["path"]


def post_paths_of(config):
    return inner_of(config)[1]["match"][0]["path"]


def test_legacy_get_profile_is_the_exact_historical_eight():
    assert LEGACY_GET_ROUTES == (
        "/os/", "/os/auth/callback", "/workspace/programs/current",
        "/workspace/work/current", "/workspace/mission/current",
        "/workspace/mission/v3/current", "/workspace/result/current",
        "/workspace/window/current",
    )


# Spell out representative historical and complete current pairs independently of the table.
ADMITTED_ROUTE_PAIRS = (
    (LEGACY_GET_ROUTES, LEGACY_POST_ROUTES),
    (LEGACY_GET_ROUTES, INCUMBENT_POST_ROUTES),
    (INCUMBENT_GET_ROUTES, LEGACY_POST_ROUTES),
    (INCUMBENT_GET_ROUTES, INCUMBENT_POST_ROUTES),
    (CONTROL_ROOM_LEGACY_GET_ROUTES, LEGACY_POST_ROUTES),
    (CONTROL_ROOM_GET_ROUTES, CONTROL_ROOM_POST_ROUTES),
    (COMPOSED_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES),
    (SOURCE_CONTEXT_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES),
    (PRE_DIRECT_NATIVE_GET_ROUTES, PRE_DIRECT_NATIVE_POST_ROUTES),
    (GET_ROUTES, POST_ROUTES),
)


@pytest.mark.parametrize("fixed,posts", ADMITTED_ROUTE_PAIRS)
@pytest.mark.parametrize("index_overlap", [False, True])
@pytest.mark.parametrize("with_mcp", [False, True])
def test_complete_profiles_upgrade_paths_and_only_the_dedicated_source_branch(fixed, index_overlap, posts, with_mcp):
    paths = (sorted(list(fixed) + list(asset_routes(OLD))) if index_overlap
             else sorted(set(fixed) | set(asset_routes(OLD))))
    live = mcp_fullconfig() if with_mcp else fullconfig()
    get_paths_of(live)[:] = paths
    post_paths_of(live)[:] = list(posts)
    if fixed == GET_ROUTES:
        expect_source_upgrade(inner_of(live))
    before = copy.deepcopy(live)
    planned, prepared, final = transition_values(live)
    assert live == before
    for value, expected_get in (
        (prepared, sorted(set(GET_ROUTES) | set(asset_routes(OLD)) | set(asset_routes(NEW)))),
        (final, sorted(set(GET_ROUTES) | set(asset_routes(NEW)))),
    ):
        expected = copy.deepcopy(before)
        get_paths_of(expected)[:] = expected_get
        post_paths_of(expected)[:] = list(POST_ROUTES)
        if fixed != GET_ROUTES:
            expect_source_upgrade(inner_of(expected))
        if with_mcp:
            expect_complete_mcp(inner_of(expected))
        expect_native_upgrade(inner_of(expected))
        assert value == expected
        assert len(inner_of(value)) == (7 if with_mcp else 5)
        if with_mcp:
            # The public-MCP branches keep every handler and gain exactly the
            # one COO path in their two fixed path lists.
            observed = inner_of(before)[3:5] if fixed == GET_ROUTES else inner_of(before)[2:4]
            result_branches = inner_of(value)[3:5]
            for seen, result in zip(observed, result_branches):
                assert result["handle"] == seen["handle"]
                assert result.get("group") == seen.get("group")
                assert result["match"][0]["method"] == seen["match"][0]["method"]
                assert result["match"][0]["path"] == (
                    list(COMPLETE_MCP_METADATA_ROUTES)
                    if seen["match"][0]["method"] == ["GET"] else list(COMPLETE_MCP_ROUTES))
        else:
            assert inner_of(value)[4:] == inner_of(before)[3 if fixed == GET_ROUTES else 2:]
    assert planned["get_routes"]["fixed"] == list(GET_ROUTES)
    assert planned["bindings"]["observed_fullconfig_sha256"] == module._sha256(before)


INCOMPATIBLE_ROUTE_PAIRS = tuple(
    (fixed, posts)
    for fixed in (LEGACY_GET_ROUTES, INCUMBENT_GET_ROUTES,
                  CONTROL_ROOM_LEGACY_GET_ROUTES, CONTROL_ROOM_GET_ROUTES,
                  COMPOSED_GET_ROUTES, GET_ROUTES)
    for posts in (LEGACY_POST_ROUTES, INCUMBENT_POST_ROUTES, CONTROL_ROOM_POST_ROUTES,
                  PRE_PROJECT_ADMISSION_POST_ROUTES, PRE_DIRECT_NATIVE_POST_ROUTES, POST_ROUTES)
    if (fixed, posts) not in ADMITTED_ROUTE_PAIRS
)


@pytest.mark.parametrize("fixed,posts", INCOMPATIBLE_ROUTE_PAIRS)
@pytest.mark.parametrize("with_mcp", [False, True])
def test_complete_but_incompatible_os_profiles_refuse(fixed, posts, with_mcp):
    assert len(INCOMPATIBLE_ROUTE_PAIRS) == 27
    live = mcp_fullconfig() if with_mcp else fullconfig()
    get_paths_of(live)[:] = sorted(set(fixed) | set(asset_routes(OLD)))
    post_paths_of(live)[:] = list(posts)
    with pytest.raises(ValueError, match="mixed or incomplete route profile"):
        transition_values(live)


@pytest.mark.parametrize("mask", range(1, 7))
@pytest.mark.parametrize("with_mcp", [False, True])
def test_partial_native_post_upgrade_is_not_an_admitted_historical_profile(mask, with_mcp):
    live = mcp_fullconfig() if with_mcp else fullconfig()
    get_paths_of(live)[:] = sorted(set(GET_ROUTES) | set(asset_routes(OLD)))
    post_paths_of(live)[:] = list(POST_ROUTES)
    expect_source_upgrade(inner_of(live))
    post_paths_of(live)[:] = list(PRE_DIRECT_NATIVE_POST_ROUTES) + [
        path for bit, path in enumerate(DIRECT_NATIVE_POST_ROUTES) if mask & (1 << bit)
    ]
    with pytest.raises(ValueError, match="observed POST route differs"):
        transition_values(live)


@pytest.mark.parametrize("path", [
    "/os/executive/direct-native/result", "/os/executive/direct-native/consume",
    "/os/executive/direct-native/correction",
])
def test_native_post_routes_cannot_be_added_to_get_profile(path):
    live = fullconfig()
    get_paths_of(live)[:] = sorted(set(GET_ROUTES) | set(asset_routes(OLD)))
    post_paths_of(live)[:] = list(POST_ROUTES)
    expect_source_upgrade(inner_of(live))
    get_paths_of(live).append(path)
    with pytest.raises(ValueError, match="observed GET routes differ"):
        transition_values(live)


@pytest.mark.parametrize("path", [
    "/os/executive/direct-native/*", "/os/executive/direct-native/result/",
    "/os/executive/direct-native/arbitrary", "/os/executive/direct-native/submit",
])
def test_native_upgrade_does_not_admit_wildcards_aliases_or_other_operations(path):
    live = fullconfig()
    get_paths_of(live)[:] = sorted(set(GET_ROUTES) | set(asset_routes(OLD)))
    post_paths_of(live)[:] = list(POST_ROUTES)
    expect_source_upgrade(inner_of(live))
    post_paths_of(live).append(path)
    with pytest.raises(ValueError, match="observed POST route differs"):
        transition_values(live)


@pytest.mark.parametrize("mask", range(1, 7))
def test_partial_new_get_profiles_refuse(mask):
    additions = ("/workspace/result-references/current", "/workspace/plan/current",
                 "/workspace/operator/activity/current")
    paths = set(LEGACY_GET_ROUTES) | set(asset_routes(OLD))
    paths.update(path for bit, path in enumerate(additions) if mask & (1 << bit))
    live = fullconfig(site=host_route(sorted(paths)))
    post_paths_of(live)[:] = list(INCUMBENT_POST_ROUTES)
    with pytest.raises(ValueError, match="observed GET routes differ|mixed or incomplete route profile"):
        transition_values(live)


@pytest.mark.parametrize("fault", ["missing-old", "extra", "wildcard", "wrong-assets",
                                   "duplicate-fixed", "duplicate-asset", "excess-os"])
def test_legacy_get_profile_never_admits_extras_or_missing_members(fault):
    paths = sorted(set(LEGACY_GET_ROUTES) | set(asset_routes(OLD)))
    if fault == "missing-old": paths.remove("/workspace/window/current")
    elif fault == "extra": paths.append("/workspace/extra/current")
    elif fault == "wildcard": paths.append("/workspace/*")
    elif fault == "wrong-assets": paths = sorted(set(LEGACY_GET_ROUTES) | set(asset_routes(NEW)))
    elif fault == "duplicate-fixed": paths.append("/workspace/window/current")
    elif fault == "duplicate-asset": paths.append("/os/assets/index-DrspFhr6.css")
    else: paths.extend(["/os/", "/os/"])
    live = fullconfig(site=host_route(paths))
    with pytest.raises(ValueError, match="observed GET routes differ"):
        transition_values(live)


def test_retained_legacy_get_wrappers_upgrade_without_masking_the_profile():
    route = copy.deepcopy(RETAINED_CADDY_ROUTE)
    branches = route["handle"][0]["routes"][0]["handle"][0]["routes"]
    # Keep the genuine eight fixed paths, adapter wrappers, group, headers,
    # legacy POST profile and body limit; substitute only qualified test assets.
    branches[0]["match"][0]["path"] = sorted(list(LEGACY_GET_ROUTES) + list(asset_routes(OLD)))
    live = fullconfig(site=route)
    before = copy.deepcopy(live)
    planned, prepared, final = transition_values(live)
    assert live == before
    for value, expected_get in (
        (prepared, sorted(set(GET_ROUTES) | set(asset_routes(OLD)) | set(asset_routes(NEW)))),
        (final, sorted(set(GET_ROUTES) | set(asset_routes(NEW)))),
    ):
        expected = copy.deepcopy(before)
        target = site_of(expected)["handle"][0]["routes"][0]["handle"][0]["routes"]
        target[0]["match"][0]["path"] = expected_get
        target[1]["match"][0]["path"] = list(POST_ROUTES)
        expect_source_upgrade(target)
        expect_native_upgrade(target)
        assert value == expected
    assert planned["get_routes"]["fixed"] == list(GET_ROUTES)


@pytest.mark.parametrize("index_overlap", [False, True])
def test_legacy_get_profile_with_retained_nine_asset_names(index_overlap):
    # Public names from the sanitized91c1 diagnosis; contents are synthetic.
    names = ["index.html", "assets/Inter-Variable-DiVDrmQJ.woff2",
             "assets/Manrope-Variable-FzEoaBTQ.ttf", "assets/atelier-office-poIrp4_y.jpg",
             "assets/index-B0ewcH8_.css", "assets/index-dP5lZ6yG.js",
             "licenses/fonts/Inter-OFL.txt", "licenses/fonts/Manrope-FONTLOG.txt",
             "licenses/fonts/Manrope-OFL.txt"]
    def nine(paths):
        return {"schema": "mastermind.os_assets.v1", "files": [
            {"path": name, "byte_count": 1, "sha256": "a" * 64, "mime": mime}
            for name, mime in os_asset_mimes(paths).items()]}
    old = nine(names)
    new = nine([name.replace("index-B0ewcH8_", "index-Br9E9bcG")
                .replace("index-dP5lZ6yG", "index-Br9E9bcG") for name in names])
    paths = (sorted(list(LEGACY_GET_ROUTES) + list(asset_routes(old))) if index_overlap
             else sorted(set(LEGACY_GET_ROUTES) | set(asset_routes(old))))
    live = fullconfig(site=host_route(paths))
    post_paths_of(live)[:] = list(INCUMBENT_POST_ROUTES)
    before = copy.deepcopy(live)
    prepared = prepare_config(fullconfig=live, current_manifest=old,
                              candidate_manifest=new, relay_port=49152)
    final = final_config(fullconfig=live, current_manifest=old,
                         candidate_manifest=new, relay_port=49152)
    assert live == before
    for value, expected_get in (
        (prepared, sorted(set(GET_ROUTES) | set(asset_routes(old)) | set(asset_routes(new)))),
        (final, sorted(set(GET_ROUTES) | set(asset_routes(new)))),
    ):
        expected = copy.deepcopy(before)
        get_paths_of(expected)[:] = expected_get
        post_paths_of(expected)[:] = list(POST_ROUTES)
        expect_source_upgrade(inner_of(expected))
        expect_native_upgrade(inner_of(expected))
        assert value == expected


def test_only_sealed_legacy_or_read_expanded_public_posts_upgrade():
    for old_posts in (LEGACY_POST_ROUTES, INCUMBENT_POST_ROUTES):
        observed = fullconfig()
        get_paths_of(observed)[:] = sorted(set(INCUMBENT_GET_ROUTES) | set(asset_routes(OLD)))
        post_paths_of(observed)[:] = list(old_posts)
        before = copy.deepcopy(observed)
        planned, prepare, final = transition_values(observed)
        assert observed == before  # no implicit host changes during planning
        assert post_paths_of(prepare) == list(POST_ROUTES)
        assert post_paths_of(final) == list(POST_ROUTES)
        assert inner_of(prepare)[1]["handle"] == inner_of(observed)[1]["handle"]
        assert inner_of(final)[1]["handle"] == inner_of(observed)[1]["handle"]
        assert planned["post_routes"] == list(POST_ROUTES)
        assert planned["bindings"]["prepare_fullconfig_sha256"] == module._sha256(prepare)
        assert planned["bindings"]["final_fullconfig_sha256"] == module._sha256(final)
        assert post_paths_of(prepare).count("/os/executive/session/send") == 1
        assert get_paths_of(prepare) == sorted(set(GET_ROUTES) | set(asset_routes(OLD)) | set(asset_routes(NEW)))


@pytest.mark.parametrize("bad", [
    list(LEGACY_POST_ROUTES) + ["/os/executive/session/send"],
    list(POST_ROUTES) + ["/os/executive/session/send"],
    list(POST_ROUTES[:-2]),
    list(POST_ROUTES) + [POST_ROUTES[0]],
    ["/os/executive/session/context"],
])
def test_public_transition_refuses_unknown_broad_or_partial_post_routes(bad):
    live = fullconfig()
    post_paths_of(live)[:] = bad
    with pytest.raises(ValueError):
        transition_values(live)


def transition_values(live=None):
    live = fullconfig() if live is None else live
    return (
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152),
        prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                       relay_port=49152),
        final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                     relay_port=49152),
    )


def canonical_bytes(value):
    return module._canonical(value) + b"\n"


@pytest.fixture
def sealed(tmp_path):
    parent = tmp_path / "seal"
    parent.mkdir()
    os.chmod(parent, 0o700)
    yield parent
    os.chmod(parent, 0o700)



def incumbent_public_edge():
    """Old deployed Caddy profile, not a second publication authority."""
    config = fullconfig()
    inner = inner_of(config)
    inner[0]["match"][0]["path"] = sorted(set(CONTROL_ROOM_LEGACY_GET_ROUTES) | set(asset_routes(OLD)))
    inner[1]["match"][0]["path"] = list(LEGACY_POST_ROUTES)
    return config


def test_exact_incumbent_edge_gains_only_qualified_control_room_routes():
    observed = incumbent_public_edge()
    before = copy.deepcopy(observed)
    args = dict(fullconfig=observed, current_manifest=OLD,
                candidate_manifest=NEW, relay_port=49152)
    receipt = plan(old_source=OLD_SHA, new_source=NEW_SHA, **args)
    prepared, finished = prepare_config(**args), final_config(**args)
    assert observed == before  # pure plan; no update to installed Caddy
    assert receipt["get_routes"]["fixed"] == list(GET_ROUTES)
    assert receipt["post_routes"] == list(POST_ROUTES)
    for config in (prepared, finished):
        get, post, source, native, terminal = inner_of(config)
        assert native == native_branch()
        assert source == source_branch()
        paths = get["match"][0]["path"]
        assert set(GET_ROUTES) <= set(paths)
        assert post["match"][0] == {"method": ["POST"], "path": list(POST_ROUTES)}
        assert post["handle"][0] == {"handler": "request_body", "max_size": 64000}
        assert terminal == {"handle": [{"handler": "static_response", "abort": True}]}
        assert "/workspace/control-room/delete-all" not in paths
        assert "/workspace/control-room/delete-all" not in post["match"][0]["path"]
    assert set(asset_routes(OLD)) <= set(inner_of(prepared)[0]["match"][0]["path"])
    assert set(asset_routes(OLD)) - set(asset_routes(NEW)) <= (
        set(inner_of(prepared)[0]["match"][0]["path"]) -
        set(inner_of(finished)[0]["match"][0]["path"]))


@pytest.mark.parametrize("damage", ["new_get_old_post", "old_get_new_post", "foreign_get", "foreign_post"])
def test_incumbent_edge_refuses_mixed_or_widened_profiles(damage):
    observed = incumbent_public_edge()
    get, post, _ = inner_of(observed)
    if damage == "new_get_old_post":
        get["match"][0]["path"] = sorted(set(GET_ROUTES) | set(asset_routes(OLD)))
    elif damage == "old_get_new_post":
        post["match"][0]["path"] = list(POST_ROUTES)
    elif damage == "foreign_get":
        get["match"][0]["path"].append("/workspace/control-room/owner-admin")
    else:
        post["match"][0]["path"].append("/workspace/control-room/owner-admin")
    with pytest.raises(ValueError, match="(profile|routes differ|route differs)"):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=observed,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)


def test_plan_binds_exact_routes_and_flags():
    live = fullconfig()
    value = plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
                 current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert value["schema"] == module.PLAN_SCHEMA
    assert value["host"] == HOST
    assert value["sources"] == {"retired": OLD_SHA, "candidate": NEW_SHA, "binding_only": True}
    assert value["bindings"]["observed_fullconfig_sha256"] == module._sha256(live)
    assert value["bindings"]["current_manifest_sha256"] == module._sha256(OLD)
    assert value["bindings"]["candidate_manifest_sha256"] == module._sha256(NEW)
    assert value["get_routes"]["fixed"] == list(GET_ROUTES)
    assert value["get_routes"]["retired"] == list(asset_routes(OLD))
    assert value["get_routes"]["candidate"] == list(asset_routes(NEW))
    assert value["get_routes"]["prepare"] == sorted(
        set(GET_ROUTES) | set(asset_routes(OLD)) | set(asset_routes(NEW)))
    assert value["get_routes"]["final"] == sorted(set(GET_ROUTES) | set(asset_routes(NEW)))
    assert value["post_routes"] == list(POST_ROUTES)
    assert value["shared_assets_verified"] == []  # retired and candidate names are disjoint
    assert value["installed"] is False
    assert value["published"] is False


def test_shared_asset_names_with_identical_bytes_are_verified():
    # A candidate that keeps the retired hash-named assets byte-identical and
    # switches only index.html verifies those shared names in the plan.
    same_names = manifest("DrspFhr6", index_sha="d" * 64)
    value = plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=fullconfig(),
                 current_manifest=OLD, candidate_manifest=same_names, relay_port=49152)
    assert value["shared_assets_verified"] == ["assets/index-DrspFhr6.css", "assets/index-DrspFhr6.js"]
    live = fullconfig()
    assert get_paths_of(prepare_config(fullconfig=live, current_manifest=OLD,
                                       candidate_manifest=same_names, relay_port=49152)) \
        == sorted(set(GET_ROUTES) | set(asset_routes(OLD)))


def test_old_only_observed_route_cannot_satisfy_new_html_asset():
    # The installed edge still serves only the retired hash-named assets while
    # the candidate manifest introduces the new names: the plan refuses, and
    # the same observation accepts the manifest that matches it.
    live = fullconfig(OLD)
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=NEW, candidate_manifest=NEW, relay_port=49152)
    assert plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
                current_manifest=OLD, candidate_manifest=NEW,
                relay_port=49152)["installed"] is False


@pytest.mark.parametrize("paths", [
    sorted(list(GET_ROUTES) + list(asset_routes(OLD)))[:-1],
    sorted(list(GET_ROUTES) + list(asset_routes(OLD)) + ["/workspace/extra/current"]),
    sorted(list(GET_ROUTES) + list(asset_routes(OLD)) + ["/os/", "/os/"]),
])
def test_observed_get_matcher_deviations_refuse(paths):
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=fullconfig(site=host_route(paths)),
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)


@pytest.mark.parametrize("mangle", [
    pytest.param(lambda c: site_of(c, index=0) and c["apps"]["http"]["servers"]["srv0"]["routes"].insert(
        0, copy.deepcopy(site_of(c))), id="duplicate-host-same-server"),
    pytest.param(lambda c: c["apps"]["http"]["servers"].__setitem__(
        "srv1", {"listen": [":8443"], "routes": [copy.deepcopy(site_of(c))]}), id="duplicate-host-second-server"),
    pytest.param(lambda c: site_of(c)["match"][0].__setitem__("host", [HOST, "*"]), id="extra-wildcard-host"),
    pytest.param(lambda c: site_of(c)["match"][0].__setitem__("host", ["*"]), id="wildcard-host-only"),
    pytest.param(lambda c: site_of(c)["match"][0].__setitem__("host", [HOST, "mcp.mastermind-x.com"]), id="duplicate-host-entry"),
    pytest.param(lambda c: inner_of(c).append(
        {"match": [{"method": ["GET"], "path": ["/os/assets/index-x.js"]}], "handle": [proxy()]}), id="duplicate-get"),
    pytest.param(lambda c: inner_of(c).append(
        {"match": [{"method": ["POST"], "path": list(POST_ROUTES)}], "handle": [proxy()]}), id="duplicate-post"),
    pytest.param(lambda c: inner_of(c)[0]["handle"].append(proxy()), id="extra-proxy"),
    pytest.param(lambda c: inner_of(c)[0]["handle"][0]["upstreams"][0].__setitem__(
        "dial", "127.0.0.1:8443"), id="wrong-upstream"),
    pytest.param(lambda c: inner_of(c)[1]["handle"][1]["upstreams"][0].__setitem__(
        "dial", "10.0.0.5:49152"), id="non-loopback-upstream"),
    pytest.param(lambda c: site_of(c)["handle"].append(
        {"handler": "file_server", "root": "/var/www"}), id="extra-host-handle"),
    pytest.param(lambda c: inner_of(c).append(
        {"handle": [{"handler": "headers", "response": {"set": {"X-Tempt": ["1"]}}}]}), id="extra-matcher-free-route"),
    pytest.param(lambda c: inner_of(c)[0]["match"].__setitem__(
        0, {"method": ["GET"], "path": get_paths_of(c), "query": {"x": ["1"]}}), id="extra-matcher-key"),
])
def test_ambiguous_or_mutated_observed_config_refuses(mangle):
    live = fullconfig()
    mangle(live)
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    with pytest.raises(ValueError):
        prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                       relay_port=49152)


def test_prepare_covers_both_and_final_removes_only_retired():
    prepare = prepare_config(fullconfig=fullconfig(), current_manifest=OLD,
                             candidate_manifest=NEW, relay_port=49152)
    final = final_config(fullconfig=fullconfig(), current_manifest=OLD,
                         candidate_manifest=NEW, relay_port=49152)
    assert get_paths_of(prepare) == sorted(
        set(GET_ROUTES) | set(asset_routes(OLD)) | set(asset_routes(NEW)))
    assert get_paths_of(final) == sorted(set(GET_ROUTES) | set(asset_routes(NEW)))
    retired_only = set(asset_routes(OLD)) - set(asset_routes(NEW))
    assert retired_only
    assert not retired_only & set(get_paths_of(final))
    assert retired_only <= set(get_paths_of(prepare))


@pytest.mark.parametrize("maker", [prepare_config, final_config])
def test_only_get_paths_and_dedicated_source_branch_differ(maker):
    live = fullconfig()
    changed = maker(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                    relay_port=49152)
    stripped = copy.deepcopy(changed)
    assert inner_of(stripped).pop(-2) == native_branch()
    assert inner_of(stripped).pop(2) == source_branch()
    stripped["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["routes"][0]["match"][0]["path"] = None
    original = copy.deepcopy(live)
    original["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["routes"][0]["match"][0]["path"] = None
    post_paths_of(original)[:] = list(POST_ROUTES)
    assert stripped == original
    expected_post = copy.deepcopy(inner_of(live)[1])
    expected_post["match"][0]["path"] = list(POST_ROUTES)
    assert inner_of(changed)[1] == expected_post
    assert inner_of(changed)[4] == inner_of(live)[2]
    assert changed["apps"]["tls"] == live["apps"]["tls"]
    assert changed["admin"] == live["admin"]
    assert site_of(changed, index=1) == site_of(live, index=1)


def test_index_is_the_deliberate_switch_and_shared_names_reuse_refuses():
    switched = manifest("Br9E9bcG", index_sha="d" * 64, asset_sha="e" * 64)
    prepare = prepare_config(fullconfig=fullconfig(), current_manifest=OLD,
                             candidate_manifest=switched, relay_port=49152)
    assert sorted(set(GET_ROUTES) | set(asset_routes(OLD)) | set(asset_routes(switched))) \
        == get_paths_of(prepare)
    for field, value in (("sha256", "f" * 64), ("byte_count", 2), ("mime", "text/plain")):
        reused = copy.deepcopy(OLD)
        reused["files"][1][field] = value
        with pytest.raises(ValueError):
            final_config(fullconfig=fullconfig(), current_manifest=OLD,
                         candidate_manifest=reused, relay_port=49152)


@pytest.mark.parametrize("old,new", [
    (OLD_SHA, OLD_SHA), ("short", NEW_SHA), (None, NEW_SHA), (NEW_SHA.upper(), NEW_SHA),
    ("b" * 39, NEW_SHA), (True, NEW_SHA),
])
def test_distinct_source_ids_refused(old, new):
    with pytest.raises(ValueError):
        plan(old_source=old, new_source=new, fullconfig=fullconfig(),
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)


@pytest.mark.parametrize("port", [True, "49152", 8443, 49151, 50201, None])
def test_relay_port_refused(port):
    with pytest.raises(ValueError):
        prepare_config(fullconfig=fullconfig(), current_manifest=OLD,
                       candidate_manifest=NEW, relay_port=port)


@pytest.mark.parametrize("breakage", [
    lambda m: m.__setitem__("schema", "other.v1"),
    lambda m: m.__setitem__("extra", True),
    lambda m: m["files"][0].__setitem__("byte_count", 0),
    lambda m: m["files"].pop(),
])
def test_invalid_candidate_manifest_refused(breakage):
    broken = copy.deepcopy(NEW)
    breakage(broken)
    with pytest.raises(ValueError):
        prepare_config(fullconfig=fullconfig(), current_manifest=OLD,
                       candidate_manifest=broken, relay_port=49152)


@pytest.mark.parametrize("config", [None, {}, {"apps": {}}, {"apps": {"http": {}}},
                                    {"apps": {"http": {"servers": {}}}}, []])
def test_fullconfig_shape_refused(config):
    with pytest.raises(ValueError):
        prepare_config(fullconfig=config, current_manifest=OLD, candidate_manifest=NEW,
                       relay_port=49152)


def test_caller_inputs_are_not_mutated_and_outputs_are_detached():
    live = fullconfig()
    old, new = copy.deepcopy(OLD), copy.deepcopy(NEW)
    snapshots = (copy.deepcopy(live), copy.deepcopy(OLD), copy.deepcopy(NEW))
    value = plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
                 current_manifest=old, candidate_manifest=new, relay_port=49152)
    prepare = prepare_config(fullconfig=live, current_manifest=old, candidate_manifest=new,
                             relay_port=49152)
    final = final_config(fullconfig=live, current_manifest=old, candidate_manifest=new,
                         relay_port=49152)
    assert (live, old, new) == snapshots
    assert prepare is not live and final is not live and value["get_routes"]["prepare"] is not live
    get_paths_of(prepare).append("/workspace/injected/current")
    value["get_routes"]["prepare"].append("/workspace/injected/current")
    assert (live, old, new) == snapshots


def test_preparation_complete_requires_exact_observed_equality():
    live = fullconfig()
    prepare = prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                             relay_port=49152)
    receipt = preparation_complete(observed=copy.deepcopy(prepare), prepared=prepare)
    assert receipt["schema"] == module.PREPARE_CHECK_SCHEMA
    assert receipt["prepared_observed_exactly"] is True
    assert receipt["observed_sha256"] == receipt["prepared_sha256"] == module._sha256(prepare)
    assert receipt["installed"] is False and receipt["published"] is False
    with pytest.raises(ValueError):  # stale observation: retired-only GET routes
        preparation_complete(observed=live, prepared=prepare)
    with pytest.raises(ValueError):  # final cleanup observed where prepare was expected
        preparation_complete(observed=final_config(fullconfig=live, current_manifest=OLD,
                                                   candidate_manifest=NEW, relay_port=49152),
                             prepared=prepare)
    drifted = copy.deepcopy(prepare)
    drifted["apps"]["tls"]["certificates"]["automate"] = ["workspace.mastermind-x.com"]
    with pytest.raises(ValueError):
        preparation_complete(observed=drifted, prepared=prepare)
    with pytest.raises(ValueError):
        preparation_complete(observed=[], prepared=prepare)


def startup_without_mcp():
    return {"admin": {"listen": ["localhost:2019"]},
            "apps": {"http": {"servers": {"srv0": {"listen": [":443"],
                                                   "routes": [other_site()]}}},
                     "tls": {"certificates": {"automate": ["workspace.mastermind-x.com"]}}}}


def test_autosave_equality_alone_never_says_restart_safe():
    live = fullconfig()
    diagnostic = restart_diagnostic(observed=live, autosave=copy.deepcopy(live),
                                    startup=startup_without_mcp())
    assert diagnostic["schema"] == module.RESTART_SCHEMA
    assert diagnostic["observed_equals_autosave"] is True
    assert diagnostic["observed_equals_startup"] is False
    assert diagnostic["autosave_equals_startup"] is False
    assert diagnostic["restart_safe_by_config_equality"] is False
    assert diagnostic["restart_verified"] is False
    assert diagnostic["autosave_alone_qualifies_restart"] is False
    assert diagnostic["host_routes"] == {"observed": 1, "autosave": 1, "startup": 0}
    assert "startup config differs" in diagnostic["verdict"]
    bindings = diagnostic["bindings"]
    assert bindings["observed_sha256"] == module._sha256(live)
    assert bindings["startup_sha256"] == module._sha256(startup_without_mcp())


def test_config_equality_is_still_not_an_actually_tested_restart():
    live = fullconfig()
    matched = restart_diagnostic(observed=live, autosave=startup_without_mcp(),
                                 startup=copy.deepcopy(live))
    assert matched["restart_safe_by_config_equality"] is True
    assert matched["autosave_equals_startup"] is False
    assert matched["restart_verified"] is False
    all_equal = restart_diagnostic(observed=live, autosave=copy.deepcopy(live),
                                   startup=copy.deepcopy(live))
    assert all_equal["restart_safe_by_config_equality"] is True
    assert all_equal["restart_verified"] is False
    assert all_equal["autosave_alone_qualifies_restart"] is False
    with pytest.raises(ValueError):
        restart_diagnostic(observed=[], autosave={}, startup={})


def test_stage_transition_writes_exclusive_0600_documents(sealed):
    plan_value, prepare, final = transition_values()
    receipt = stage_transition(plan=plan_value, prepare=prepare, final=final, out=sealed)
    assert receipt == {"schema": module.STAGE_SCHEMA,
                       "files": {name: hashlib.sha256(canonical_bytes(value)).hexdigest()
                                 for name, value in ((PLAN_NAME, plan_value), (PREPARE_NAME, prepare),
                                                     (FINAL_NAME, final))},
                       "installed": False, "published": False}
    for name, value in ((PLAN_NAME, plan_value), (PREPARE_NAME, prepare), (FINAL_NAME, final)):
        staged = sealed / name
        assert staged.stat().st_mode & 0o777 == 0o600
        assert staged.is_file() and not staged.is_symlink()
        assert staged.read_bytes() == canonical_bytes(value)
    before = {name: (sealed / name).read_bytes() for name in (PLAN_NAME, PREPARE_NAME, FINAL_NAME)}
    with pytest.raises(FileExistsError):
        stage_transition(plan=plan_value, prepare=prepare, final=final, out=sealed)
    assert {name: (sealed / name).read_bytes()
            for name in (PLAN_NAME, PREPARE_NAME, FINAL_NAME)} == before


def test_stage_transition_refuses_non_dict_documents(sealed):
    with pytest.raises(ValueError):
        stage_transition(plan=[], prepare={}, final={}, out=sealed)
    assert list(sealed.iterdir()) == []


def test_stage_transition_refuses_insecure_symlinked_and_existing_destinations(tmp_path):
    plan_value, prepare, final = transition_values()
    writable = tmp_path / "writable"
    writable.mkdir()
    os.chmod(writable, 0o722)
    with pytest.raises(ValueError):
        stage_transition(plan=plan_value, prepare=prepare, final=final, out=writable)
    assert list(writable.iterdir()) == []
    real = tmp_path / "real"
    real.mkdir()
    (real / FINAL_NAME).symlink_to(tmp_path / "absent")
    linked = tmp_path / "linked"
    linked.symlink_to(real)
    with pytest.raises(ValueError):
        stage_transition(plan=plan_value, prepare=prepare, final=final, out=linked)
    with pytest.raises(FileExistsError):
        stage_transition(plan=plan_value, prepare=prepare, final=final, out=real)
    assert not (tmp_path / "absent").exists()
    assert (real / FINAL_NAME).is_symlink()
    assert (real / PLAN_NAME).read_bytes() == canonical_bytes(plan_value)
    with pytest.raises(FileNotFoundError):
        stage_transition(plan=plan_value, prepare=prepare, final=final,
                         out=tmp_path / "absent")



def write_json(path, value):
    path.write_bytes(json.dumps(value).encode("utf-8"))
    return path


def test_cli_json_guards_refuse_duplicates_nonfinite_and_oversize(tmp_path):
    (tmp_path / "ok.json").write_bytes(b'{"a": {"b": 1}}')
    (tmp_path / "dup.json").write_bytes(b'{"a": 1, "a": 2}')
    (tmp_path / "nested.json").write_bytes(b'{"a": {"b": 1, "c": 2, "b": 3}}')
    (tmp_path / "nan.json").write_bytes(b'{"a": NaN}')
    (tmp_path / "inf.json").write_bytes(b'{"a": Infinity}')
    (tmp_path / "big.json").write_bytes(b" " * (module._MAX_INPUT_BYTES + 1))
    assert module._load(tmp_path / "ok.json") == {"a": {"b": 1}}
    for name in ("dup.json", "nested.json", "nan.json", "inf.json", "big.json"):
        with pytest.raises(ValueError):
            module._load(tmp_path / name)


def test_cli_stages_compact_bindings_only(tmp_path, sealed, monkeypatch, capsys):
    live = write_json(tmp_path / "live.json", fullconfig())
    current = write_json(tmp_path / "current.json", OLD)
    candidate = write_json(tmp_path / "candidate.json", NEW)
    autosave = write_json(tmp_path / "autosave.json", fullconfig())
    startup = write_json(tmp_path / "startup.json", startup_without_mcp())
    monkeypatch.setattr(sys, "argv", [
        "os_public_edge_transition", "--live", str(live), "--manifest-current", str(current),
        "--manifest-candidate", str(candidate), "--source-old", OLD_SHA,
        "--source-new", NEW_SHA, "--relay-port", "49152", "--out", str(sealed),
        "--autosave", str(autosave), "--startup", str(startup)])
    module.main()
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    assert "apps" not in lines[0] and "reverse_proxy" not in lines[0] and HOST not in lines[0]
    summary = json.loads(lines[0])
    assert summary["schema"] == module.STAGE_SCHEMA
    assert summary["installed"] is False and summary["published"] is False
    assert summary["relay_port"] == 49152
    assert summary["get_route_counts"] == {
        "prepare": len(sorted(set(GET_ROUTES) | set(asset_routes(OLD)) | set(asset_routes(NEW)))),
        "final": len(sorted(set(GET_ROUTES) | set(asset_routes(NEW))))}
    assert summary["restart"] == {"observed_equals_autosave": True,
                                  "observed_equals_startup": False,
                                  "restart_safe_by_config_equality": False,
                                  "restart_verified": False}
    staged = {name: json.loads((sealed / name).read_bytes())
              for name in (PLAN_NAME, PREPARE_NAME, FINAL_NAME)}
    assert staged[PREPARE_NAME] == prepare_config(
        fullconfig=fullconfig(), current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert staged[FINAL_NAME] == final_config(
        fullconfig=fullconfig(), current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert staged[PLAN_NAME]["schema"] == module.PLAN_SCHEMA


def test_cli_refuses_a_stale_observation(tmp_path, sealed, monkeypatch):
    live = write_json(tmp_path / "live.json", fullconfig(site=host_route(
        sorted(list(GET_ROUTES) + list(asset_routes(OLD)))[:-1])))
    current = write_json(tmp_path / "current.json", OLD)
    candidate = write_json(tmp_path / "candidate.json", NEW)
    monkeypatch.setattr(sys, "argv", [
        "os_public_edge_transition", "--live", str(live), "--manifest-current", str(current),
        "--manifest-candidate", str(candidate), "--source-old", OLD_SHA,
        "--source-new", NEW_SHA, "--relay-port", "49152", "--out", str(sealed)])
    with pytest.raises(ValueError):
        module.main()
    assert list(sealed.iterdir()) == []


# Exact retained Caddy adapter topology; private values are not part of this fixture.
RETAINED_CADDY_ROUTE = {'handle': [{'handler': 'subroute', 'routes': [{'handle': [{'handler': 'subroute', 'routes': [{'group': 'group2', 'handle': [{'handler': 'subroute', 'routes': [{'handle': [{'handler': 'reverse_proxy', 'headers': {'request': {'delete': ['Forwarded', 'X-Forwarded-Host', 'X-Forwarded-Port', 'X-Real-IP', 'CF-Connecting-IP', 'EO-Connecting-IP', 'EO-Client-IP'], 'set': {'Host': ['mcp.mastermind-x.com'], 'X-Forwarded-For': ['127.0.0.1'], 'X-Forwarded-Proto': ['https']}}}, 'upstreams': [{'dial': '127.0.0.1:49152'}]}]}]}], 'match': [{'method': ['GET'], 'path': ['/os/', '/os/auth/callback', '/workspace/programs/current', '/workspace/work/current', '/workspace/mission/current', '/workspace/mission/v3/current', '/workspace/result/current', '/workspace/window/current', '/os/', '/os/assets/Inter-Variable-DiVDrmQJ.woff2', '/os/assets/Manrope-Variable-FzEoaBTQ.ttf', '/os/assets/atelier-office-poIrp4_y.jpg', '/os/assets/index-B0ewcH8_.css', '/os/assets/index-Br9E9bcG.js', '/os/licenses/fonts/Inter-OFL.txt', '/os/licenses/fonts/Manrope-FONTLOG.txt', '/os/licenses/fonts/Manrope-OFL.txt']}]}, {'group': 'group2', 'handle': [{'handler': 'subroute', 'routes': [{'handle': [{'handler': 'request_body', 'max_size': 64000}, {'handler': 'reverse_proxy', 'headers': {'request': {'delete': ['Forwarded', 'X-Forwarded-Host', 'X-Forwarded-Port', 'X-Real-IP', 'CF-Connecting-IP', 'EO-Connecting-IP', 'EO-Client-IP'], 'set': {'Host': ['mcp.mastermind-x.com'], 'X-Forwarded-For': ['127.0.0.1'], 'X-Forwarded-Proto': ['https']}}}, 'upstreams': [{'dial': '127.0.0.1:49152'}]}]}]}], 'match': [{'method': ['POST'], 'path': ['/os/executive/context', '/os/executive/submit', '/os/executive/status']}]}, {'handle': [{'abort': True, 'handler': 'static_response'}]}]}]}]}], 'match': [{'host': ['mcp.mastermind-x.com']}], 'terminal': True}


def test_retained_caddy_adapter_topology_is_accepted():
    route = copy.deepcopy(RETAINED_CADDY_ROUTE)
    # Retain the real adapter wrappers, groups, headers and 64KB body limit;
    # substitute only the manifest paths for this deterministic fixture.
    route["handle"][0]["routes"][0]["handle"][0]["routes"][0]["match"][0]["path"] = sorted(list(LEGACY_GET_ROUTES) + list(asset_routes(OLD)))
    live = fullconfig(site=route)
    planned = prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert planned != live
    assert preparation_complete(observed=planned, prepared=copy.deepcopy(planned))["prepared_observed_exactly"]


def test_normalized_final_supports_the_next_transition():
    normalized = final_config(fullconfig=fullconfig(), current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    following = manifest("next", index_sha="e" * 64, asset_sha="f" * 64)
    result = plan(old_source=NEW_SHA, new_source="d" * 40, fullconfig=normalized,
                  current_manifest=NEW, candidate_manifest=following, relay_port=49152)
    assert "/os/assets/index-next.js" in result["get_routes"]["prepare"]


def test_uncertain_fsync_retains_partial_file_and_blocks_reentry(sealed, monkeypatch):
    values = transition_values()
    def fail(fd):
        raise OSError("simulated fsync failure")
    monkeypatch.setattr(module.os, "fsync", fail)
    with pytest.raises(OSError):
        stage_transition(plan=values[0], prepare=values[1], final=values[2], out=sealed)
    assert (sealed / PLAN_NAME).is_file()
    monkeypatch.undo()
    with pytest.raises(FileExistsError):
        stage_transition(plan=values[0], prepare=values[1], final=values[2], out=sealed)


def test_loading_reads_no_more_than_the_cap_plus_one(tmp_path, monkeypatch):
    import io
    reads = []
    class Stream(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            assert 0 <= size <= module._MAX_INPUT_BYTES + 1
            return super().read(size)
    monkeypatch.setattr(type(tmp_path), "open", lambda self, *a, **kw: Stream(b"{}"))
    assert module._load(tmp_path / "input.json") == {}
    assert reads == [module._MAX_INPUT_BYTES + 1]


def test_prepare_comparison_distinguishes_boolean_and_integer():
    prepared = prepare_config(fullconfig=fullconfig(), current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    observed = copy.deepcopy(prepared)
    site_of(observed)["terminal"] = 1
    with pytest.raises(ValueError):
        preparation_complete(observed=observed, prepared=prepared)


def test_plan_binds_both_complete_candidate_configs():
    value, prepared, final = transition_values()
    assert value["bindings"]["prepare_fullconfig_sha256"] == module._sha256(prepared)
    assert value["bindings"]["final_fullconfig_sha256"] == module._sha256(final)


def test_extra_host_matcher_constraint_refuses():
    live = fullconfig()
    site_of(live)["match"][0]["path"] = ["/unrelated/*"]
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live, current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)


def test_two_get_proxies_cannot_replace_the_post_proxy():
    live = fullconfig()
    inner_of(live)[0]["handle"].append(inner_of(live)[1]["handle"].pop())
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live, current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)


# --- Public MCP entrypoint (#1656): the five-branch shape ------------------------
# GET / POST / MCP-metadata-GET / MCP-POST / abort. Only the first branch's path
# list is ever rewritten; the two MCP branches are observed and must stay exact.

def mcp_proxy(port=49152, host="127.0.0.1"):
    value = proxy(port)
    value["headers"]["request"]["set"]["Host"] = [host]
    return value


def mcp_branches(port=49152):
    return [
        {"match": [{"method": ["GET"], "path": [MCP_METADATA_ROUTE]}], "handle": [proxy(port)]},
        {"match": [{"method": ["POST"], "path": list(MCP_ROUTES)}],
         "handle": [{"handler": "request_body", "max_size": MCP_MAX_BODY}, mcp_proxy(port)]},
    ]


def mcp_fullconfig(old=OLD, port=49152):
    get_paths = sorted(list(SOURCE_CONTEXT_GET_ROUTES) + list(asset_routes(old)))
    site = host_route(get_paths, port)
    site["handle"][0]["routes"][2:2] = mcp_branches(port)
    return fullconfig(old=old, port=port, site=site)


@pytest.mark.parametrize("maker", [prepare_config, final_config])
def test_mcp_shape_changes_only_get_paths_and_dedicated_source_branch(maker):
    live = mcp_fullconfig()
    changed = maker(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert len(inner_of(changed)) == 7
    stripped = copy.deepcopy(changed)
    assert inner_of(stripped).pop(-2) == native_branch()
    assert inner_of(stripped).pop(2) == source_branch()
    inner_of(stripped)[0]["match"][0]["path"] = None
    original = copy.deepcopy(live)
    inner_of(original)[0]["match"][0]["path"] = None
    post_paths_of(original)[:] = list(POST_ROUTES)
    # The two public-MCP matchers carry the complete CEO+COO path lists.
    expect_complete_mcp(inner_of(original))
    assert stripped == original
    expected_post = copy.deepcopy(inner_of(live)[1])
    expected_post["match"][0]["path"] = list(POST_ROUTES)
    assert inner_of(changed)[1] == expected_post
    # Only the two fixed public-MCP path lists change inside those branches.
    for seen, result in zip(inner_of(live)[2:4], inner_of(changed)[3:5]):
        assert result["handle"] == seen["handle"]
        assert result.get("group") == seen.get("group")
        assert result["match"][0]["method"] == seen["match"][0]["method"]
        assert result["match"][0]["path"] == (
            list(COMPLETE_MCP_METADATA_ROUTES)
            if seen["match"][0]["method"] == ["GET"] else list(COMPLETE_MCP_ROUTES))
    assert changed["apps"]["tls"] == live["apps"]["tls"]
    assert site_of(changed, index=1) == site_of(live, index=1)


def test_mcp_shape_plans_the_same_route_sets_as_the_legacy_shape():
    legacy_plan, legacy_prepare, legacy_final = transition_values()
    mcp_plan, mcp_prepare, mcp_final = transition_values(mcp_fullconfig())
    assert mcp_plan["get_routes"] == legacy_plan["get_routes"]
    assert mcp_plan["post_routes"] == legacy_plan["post_routes"]
    assert get_paths_of(mcp_prepare) == get_paths_of(legacy_prepare)
    assert get_paths_of(mcp_final) == get_paths_of(legacy_final)
    assert mcp_plan["bindings"]["observed_fullconfig_sha256"] != legacy_plan["bindings"]["observed_fullconfig_sha256"]
    assert mcp_plan["bindings"]["prepare_fullconfig_sha256"] == module._sha256(mcp_prepare)
    assert mcp_plan["bindings"]["final_fullconfig_sha256"] == module._sha256(mcp_final)
    assert mcp_plan["installed"] is False and mcp_plan["published"] is False
    assert preparation_complete(observed=mcp_prepare, prepared=copy.deepcopy(mcp_prepare))["prepared_observed_exactly"]


def other_route():
    return {"match": [{"method": ["GET"], "path": ["/extra"]}], "handle": [proxy()]}


@pytest.mark.parametrize("mangle", [
    pytest.param(lambda c: inner_of(c)[2]["handle"][0]["upstreams"][0].__setitem__(
        "dial", "127.0.0.1:8443"), id="metadata-wrong-upstream"),
    pytest.param(lambda c: inner_of(c)[3]["handle"][1]["upstreams"][0].__setitem__(
        "dial", "10.0.0.5:49152"), id="mcp-non-loopback-upstream"),
    pytest.param(lambda c: inner_of(c)[2]["match"][0].__setitem__(
        "path", [MCP_METADATA_ROUTE, "/.well-known/oauth-authorization-server"]), id="metadata-extra-path"),
    pytest.param(lambda c: inner_of(c)[2]["match"][0].__setitem__(
        "path", ["/.well-known/oauth-protected-resource"]), id="metadata-wrong-path"),
    pytest.param(lambda c: inner_of(c)[2]["match"][0].__setitem__("method", ["POST"]), id="metadata-wrong-method"),
    pytest.param(lambda c: inner_of(c)[2]["handle"].append(proxy()), id="metadata-extra-proxy"),
    pytest.param(lambda c: inner_of(c)[3]["match"][0].__setitem__("path", ["/mcp", "/mcp/"]), id="mcp-extra-path"),
    pytest.param(lambda c: inner_of(c)[3]["match"][0].__setitem__("path", ["/mcp/*"]), id="mcp-wildcard-path"),
    pytest.param(lambda c: inner_of(c)[3]["match"][0].__setitem__("method", ["GET"]), id="mcp-wrong-method"),
    pytest.param(lambda c: inner_of(c)[3]["handle"][0].__setitem__("max_size", 1048576), id="mcp-larger-body"),
    pytest.param(lambda c: inner_of(c)[3]["handle"][0].__setitem__("max_size", 64000.0), id="mcp-float-body"),
    pytest.param(lambda c: inner_of(c)[3]["handle"][0].__setitem__("max_size", True), id="mcp-bool-body"),
    pytest.param(lambda c: inner_of(c)[3]["handle"].pop(0), id="mcp-no-body-limit"),
    pytest.param(lambda c: inner_of(c).pop(2), id="metadata-branch-missing"),
    pytest.param(lambda c: inner_of(c).pop(3), id="mcp-branch-missing"),
    pytest.param(lambda c: inner_of(c).pop(), id="terminal-abort-missing"),
    pytest.param(lambda c: inner_of(c).insert(2, inner_of(c).pop(3)), id="mcp-branches-reordered"),
    pytest.param(lambda c: inner_of(c).insert(4, copy.deepcopy(inner_of(c)[3])), id="mcp-post-duplicated"),
    pytest.param(lambda c: inner_of(c).insert(2, other_route()), id="six-branches-extra-route"),
    pytest.param(lambda c: inner_of(c).__setitem__(2, copy.deepcopy(inner_of(c)[0])), id="metadata-replaced-by-get-clone"),
    pytest.param(lambda c: inner_of(c).__setitem__(3, copy.deepcopy(inner_of(c)[1])), id="mcp-replaced-by-os-post-clone"),
    pytest.param(lambda c: inner_of(c).__setitem__(
        4, {"handle": [{"handler": "static_response", "body": "open"}]}), id="terminal-not-abort"),
    pytest.param(lambda c: inner_of(c).append(
        {"handle": [{"handler": "static_response", "abort": True}]}), id="two-terminal-aborts"),
])
def test_mcp_shape_mutations_refuse(mangle):
    live = mcp_fullconfig()
    mangle(live)
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    with pytest.raises(ValueError):
        prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                       relay_port=49152)
    with pytest.raises(ValueError):
        final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                     relay_port=49152)


@pytest.mark.parametrize("count", [1, 2, 4, 6, 7])
def test_wrong_counts_or_unrecognized_extra_branches_refuse(count):
    live = fullconfig()
    routes = inner_of(live)
    abort = routes[-1]
    head = routes[:2]
    del routes[:]
    routes.extend(head + [other_route() for _ in range(count - 3)] + [abort])
    routes[:] = routes[:count - 1] + [abort] if count < 3 else routes
    assert len(routes) == count
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)


# Real `caddy adapt` (v2.11.4) output for the owner template rendered with the
# three-file manifest; all five branches share one group, so they stay mutually
# exclusive. The /mcp POST branch alone presents the loopback Host.
RETAINED_MCP_CADDY_ROUTE = {'match': [{'host': ['mcp.mastermind-x.com']}], 'handle': [{'handler': 'subroute', 'routes': [{'handle': [{'handler': 'subroute', 'routes': [{'group': 'group4', 'handle': [{'handler': 'subroute', 'routes': [{'handle': [{'handler': 'reverse_proxy', 'headers': {'request': {'delete': ['Forwarded', 'X-Forwarded-Host', 'X-Forwarded-Port', 'X-Real-IP', 'CF-Connecting-IP', 'EO-Connecting-IP', 'EO-Client-IP'], 'set': {'Host': ['mcp.mastermind-x.com'], 'X-Forwarded-For': ['127.0.0.1'], 'X-Forwarded-Proto': ['https']}}}, 'upstreams': [{'dial': '127.0.0.1:49152'}]}]}]}], 'match': [{'method': ['GET'], 'path': ['/os/', '/os/auth/callback', '/workspace/programs/current', '/workspace/work/current', '/workspace/mission/current', '/workspace/mission/v3/current', '/workspace/result/current', '/workspace/plan/current', '/workspace/operator/activity/current', '/workspace/window/current', '/os/', '/os/assets/index-a.css', '/os/assets/index-b.js']}]}, {'group': 'group4', 'handle': [{'handler': 'subroute', 'routes': [{'handle': [{'handler': 'request_body', 'max_size': 64000}, {'handler': 'reverse_proxy', 'headers': {'request': {'delete': ['Forwarded', 'X-Forwarded-Host', 'X-Forwarded-Port', 'X-Real-IP', 'CF-Connecting-IP', 'EO-Connecting-IP', 'EO-Client-IP'], 'set': {'Host': ['mcp.mastermind-x.com'], 'X-Forwarded-For': ['127.0.0.1'], 'X-Forwarded-Proto': ['https']}}}, 'upstreams': [{'dial': '127.0.0.1:49152'}]}]}]}], 'match': [{'method': ['POST'], 'path': ['/os/executive/context', '/os/executive/submit', '/os/executive/status']}]}, {'group': 'group4', 'handle': [{'handler': 'subroute', 'routes': [{'handle': [{'handler': 'reverse_proxy', 'headers': {'request': {'delete': ['Forwarded', 'X-Forwarded-Host', 'X-Forwarded-Port', 'X-Real-IP', 'CF-Connecting-IP', 'EO-Connecting-IP', 'EO-Client-IP'], 'set': {'Host': ['mcp.mastermind-x.com'], 'X-Forwarded-For': ['127.0.0.1'], 'X-Forwarded-Proto': ['https']}}}, 'upstreams': [{'dial': '127.0.0.1:49152'}]}]}]}], 'match': [{'method': ['GET'], 'path': ['/.well-known/oauth-protected-resource/mcp']}]}, {'group': 'group4', 'handle': [{'handler': 'subroute', 'routes': [{'handle': [{'handler': 'request_body', 'max_size': 64000}, {'handler': 'reverse_proxy', 'headers': {'request': {'delete': ['Forwarded', 'X-Forwarded-Host', 'X-Forwarded-Port', 'X-Real-IP', 'CF-Connecting-IP', 'EO-Connecting-IP', 'EO-Client-IP'], 'set': {'Host': ['127.0.0.1'], 'X-Forwarded-For': ['127.0.0.1'], 'X-Forwarded-Proto': ['https']}}}, 'upstreams': [{'dial': '127.0.0.1:49152'}]}]}]}], 'match': [{'method': ['POST'], 'path': ['/mcp']}]}, {'handle': [{'abort': True, 'handler': 'static_response'}]}]}]}]}], 'terminal': True}


def test_retained_caddy_adapter_topology_with_mcp_is_accepted():
    route = copy.deepcopy(RETAINED_MCP_CADDY_ROUTE)
    # Keep the real adapter wrappers, shared group, headers and 64KB body limits;
    # substitute only the manifest paths for this deterministic fixture.
    wrapper = route["handle"][0]["routes"][0]["handle"][0]["routes"]
    assert len(wrapper) == 5 and {item.get("group") for item in wrapper[:4]} == {"group4"}
    wrapper[0]["match"][0]["path"] = sorted(list(CONTROL_ROOM_LEGACY_GET_ROUTES) + list(asset_routes(OLD)))
    assert wrapper[2]["match"][0] == {"method": ["GET"], "path": [MCP_METADATA_ROUTE]}
    assert wrapper[3]["match"][0] == {"method": ["POST"], "path": list(MCP_ROUTES)}
    hosts = [branch["handle"][0]["routes"][0]["handle"][-1]["headers"]["request"]["set"]["Host"] for branch in wrapper[:4]]
    assert hosts == [[HOST], [HOST], [HOST], ["127.0.0.1"]]
    live = fullconfig(site=route)
    planned = prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert planned != live
    assert preparation_complete(observed=planned, prepared=copy.deepcopy(planned))["prepared_observed_exactly"]
    finalized = final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    final_wrapper = site_of(finalized)["handle"][0]["routes"][0]["handle"][0]["routes"]
    # Preserve the retained OS POST group, handlers, body cap and proxy while
    # updating its exact path list and inserting only the dedicated source branch.
    expected_post = copy.deepcopy(wrapper[1])
    assert expected_post["match"][0]["path"] == list(LEGACY_POST_ROUTES)
    expected_post["match"][0]["path"] = list(POST_ROUTES)
    assert final_wrapper[1] == expected_post
    assert final_wrapper[2] == source_branch(group="group4")
    # The retained adapter wrappers, group, headers and body caps survive; only
    # the two fixed public-MCP path lists gain their exact COO path.
    for index, (seen, result) in enumerate(zip(wrapper[2:4], final_wrapper[3:5])):
        assert result["handle"] == seen["handle"], index
        assert result.get("group") == seen.get("group"), index
        assert result["match"][0]["method"] == seen["match"][0]["method"], index
        assert result["match"][0]["path"] == (
            list(COMPLETE_MCP_METADATA_ROUTES) if index == 0 else list(COMPLETE_MCP_ROUTES))
    assert final_wrapper[5] == native_branch(group="group4")
    assert final_wrapper[6] == wrapper[4]
    assert final_wrapper[0]["match"][0]["path"] == sorted(set(GET_ROUTES) | set(asset_routes(NEW)))


# --- Proxy handler equality on every branch (#1656 independent review, finding 2) ---
# Matching only the upstream let a changed Host, header-strip list, rewrite or
# transport through the planner. The whole reverse_proxy handler must equal the
# rendered one; only /mcp presents the gateway's loopback Host.

def branch_proxy(config, index):
    return inner_of(config)[index]["handle"][-1]


PROXY_MUTATIONS = {
    "host-changed": lambda p: p["headers"]["request"]["set"].__setitem__("Host", ["attacker.example"]),
    "host-doubled": lambda p: p["headers"]["request"]["set"].__setitem__("Host", [HOST, "127.0.0.1"]),
    "forwarded-for-changed": lambda p: p["headers"]["request"]["set"].__setitem__("X-Forwarded-For", ["203.0.113.9"]),
    "forwarded-proto-changed": lambda p: p["headers"]["request"]["set"].__setitem__("X-Forwarded-Proto", ["http"]),
    "extra-set-header": lambda p: p["headers"]["request"]["set"].__setitem__("X-Admin", ["1"]),
    "strip-list-trimmed": lambda p: p["headers"]["request"]["delete"].remove("CF-Connecting-IP"),
    "strip-list-emptied": lambda p: p["headers"]["request"].__setitem__("delete", []),
    "headers-missing": lambda p: p.pop("headers"),
    "response-headers-added": lambda p: p["headers"].__setitem__("response", {"set": {"X-Open": ["1"]}}),
    "rewrite-added": lambda p: p.__setitem__("rewrite", {"uri": "/os/executive/submit"}),
    "tls-transport": lambda p: p.__setitem__("transport", {"protocol": "http", "tls": {"insecure_skip_verify": True}}),
    "other-transport": lambda p: p.__setitem__("transport", {"protocol": "fastcgi"}),
    "handle-response-added": lambda p: p.__setitem__("handle_response", [{"routes": []}]),
    "load-balancing-added": lambda p: p.__setitem__("load_balancing", {"retries": 3}),
    "upstream-option-added": lambda p: p["upstreams"][0].__setitem__("max_requests", 1),
    "second-upstream": lambda p: p["upstreams"].append({"dial": "127.0.0.1:8443"}),
}


@pytest.mark.parametrize("shape,index", [
    ("legacy", 0), ("legacy", 1), ("mcp", 0), ("mcp", 1), ("mcp", 2), ("mcp", 3),
    ("source", 2),
])
@pytest.mark.parametrize("mutation", sorted(PROXY_MUTATIONS))
def test_every_branch_proxy_must_equal_the_rendered_handler(shape, index, mutation):
    live = mcp_fullconfig() if shape == "mcp" else fullconfig()
    if shape == "source":
        get_paths_of(live)[:] = sorted(set(GET_ROUTES) | set(asset_routes(OLD)))
        expect_source_upgrade(inner_of(live))
    PROXY_MUTATIONS[mutation](branch_proxy(live, index))
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    with pytest.raises(ValueError):
        prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                       relay_port=49152)
    with pytest.raises(ValueError):
        final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                     relay_port=49152)


@pytest.mark.parametrize("index,wrong_host", [(2, "127.0.0.1"), (3, HOST), (0, "127.0.0.1"), (1, "127.0.0.1")])
def test_each_branch_presents_only_its_own_upstream_host(index, wrong_host):
    live = mcp_fullconfig()
    branch_proxy(live, index)["headers"]["request"]["set"]["Host"] = [wrong_host]
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)


def test_proxy_equality_accepts_the_adapter_shape_without_a_transport():
    live = mcp_fullconfig()
    for index in range(4):
        branch_proxy(live, index).pop("transport", None)
    value = plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
                 current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert value["relay_port"] == 49152


def test_a_proxy_for_another_relay_port_is_refused_on_every_branch():
    live = mcp_fullconfig(port=49153)
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)


# --- Public COO route pair (#2120) ------------------------------------------------
# The public edge gains exactly one COO metadata path and one COO transport path.
# They extend the same two exact method branches the CEO pair already uses, so
# the two coherent profiles are the CEO-only pair and the complete CEO+COO pair.

def mcp_matcher_branches(config):
    """The two public-MCP matcher branches, keyed by their role."""
    found = {}
    for branch in inner_of(config):
        match = branch.get("match")
        if not match or type(match[0]) is not dict:
            continue
        method, paths = match[0].get("method"), match[0].get("path")
        if method == ["GET"] and paths and paths[0].startswith("/.well-known/"):
            found["metadata"] = branch
        elif method == ["POST"] and paths and paths[0] == "/mcp":
            found["transport"] = branch
    return found


def mcp_matcher_paths(config):
    """The observed public-MCP path lists, keyed by their role."""
    return {role: list(branch["match"][0]["path"])
            for role, branch in mcp_matcher_branches(config).items()}


def observed_public_edge(with_source=False):
    """An observed public edge carrying the CEO-only public-MCP pair."""
    live = mcp_fullconfig()
    if with_source:
        get_paths_of(live)[:] = sorted(set(GET_ROUTES) | set(asset_routes(OLD)))
        post_paths_of(live)[:] = list(POST_ROUTES)
        expect_source_upgrade(inner_of(live))
    return live


@pytest.mark.parametrize("with_source", [False, True])
def test_public_mcp_pair_upgrades_ceo_only_to_complete_in_place(with_source):
    live = observed_public_edge(with_source)
    assert mcp_matcher_paths(live) == {"metadata": list(MCP_METADATA_ROUTES),
                                       "transport": list(MCP_ROUTES)}
    before = copy.deepcopy(live)
    prepared = prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                              relay_port=49152)
    finalized = final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                             relay_port=49152)
    assert live == before  # pure planning; the observed config is never mutated
    for value in (prepared, finalized):
        assert mcp_matcher_paths(value) == {
            "metadata": list(COMPLETE_MCP_METADATA_ROUTES),
            "transport": list(COMPLETE_MCP_ROUTES)}
        branches = mcp_matcher_branches(value)
        # Metadata keeps the public Host; the transport keeps the gateway's
        # loopback Host, its stripped forwarding headers and its 64000-byte cap.
        assert branches["metadata"]["handle"][-1]["headers"]["request"]["set"]["Host"] == [HOST]
        assert branches["transport"]["handle"][-1]["headers"]["request"]["set"]["Host"] == ["127.0.0.1"]
        assert branches["transport"]["handle"][0] == {"handler": "request_body",
                                                       "max_size": MCP_MAX_BODY}
        assert branches["metadata"]["handle"][-1]["headers"]["request"]["delete"] == list(
            module._STRIPPED_REQUEST_HEADERS)
        # The unrelated host route and the TLS policy are untouched.
        assert site_of(value, index=1) == site_of(live, index=1)
        assert value["apps"]["tls"] == live["apps"]["tls"]
    # The source-operation branch keeps its own cap and public Host.
    source = [b for b in inner_of(prepared) if b.get("match", [{}])[0].get("path") == list(SOURCE_POST_ROUTES)]
    assert len(source) == 1
    assert source[0]["handle"][0] == {"handler": "request_body", "max_size": module.SOURCE_MAX_BODY}
    assert source[0]["handle"][-1]["headers"]["request"]["set"]["Host"] == [HOST]


def test_complete_public_mcp_pair_is_idempotent():
    live = observed_public_edge(True)
    expect_complete_mcp(inner_of(live))
    finalized = final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                             relay_port=49152)
    assert mcp_matcher_paths(finalized) == {"metadata": list(COMPLETE_MCP_METADATA_ROUTES),
                                            "transport": list(COMPLETE_MCP_ROUTES)}
    # Planning the already-complete configuration again is a fixed point.
    again = prepare_config(fullconfig=finalized, current_manifest=NEW, candidate_manifest=NEW,
                           relay_port=49152)
    assert again == finalized
    assert mcp_matcher_paths(again) == {"metadata": list(COMPLETE_MCP_METADATA_ROUTES),
                                        "transport": list(COMPLETE_MCP_ROUTES)}


def test_legacy_no_mcp_topology_never_gains_a_public_mcp_family():
    live = fullconfig()  # the legacy three-branch topology, no public-MCP family
    assert mcp_matcher_paths(live) == {}
    prepared = prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                              relay_port=49152)
    finalized = final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                             relay_port=49152)
    for value in (prepared, finalized):
        paths = [path for branch in inner_of(value) if branch.get("match")
                 for path in branch["match"][0]["path"]]
        assert "/mcp" not in paths and "/mcp/coo" not in paths
        assert not any(path.startswith("/.well-known/") for path in paths)
        assert mcp_matcher_paths(value) == {}


@pytest.mark.parametrize("upgraded", ["metadata", "transport"])
def test_mixed_public_mcp_profiles_refuse(upgraded):
    live = observed_public_edge(False)
    branches = mcp_matcher_branches(live)
    if upgraded == "metadata":
        branches["metadata"]["match"][0]["path"] = list(COMPLETE_MCP_METADATA_ROUTES)
    else:
        branches["transport"]["match"][0]["path"] = list(COMPLETE_MCP_ROUTES)
    with pytest.raises(ValueError, match="mixed or incomplete MCP profile"):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    with pytest.raises(ValueError, match="mixed or incomplete MCP profile"):
        prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                       relay_port=49152)
    with pytest.raises(ValueError, match="mixed or incomplete MCP profile"):
        final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                     relay_port=49152)


@pytest.mark.parametrize("mangle", [
    pytest.param(lambda c: mcp_matcher_branches(c)["metadata"]["match"][0].__setitem__(
        "path", list(COMPLETE_MCP_METADATA_ROUTES) + [MCP_METADATA_ROUTE]),
        id="metadata-duplicate"),
    pytest.param(lambda c: mcp_matcher_branches(c)["metadata"]["match"][0].__setitem__(
        "path", ["/.well-known/oauth-protected-resource/*"]), id="metadata-wildcard"),
    pytest.param(lambda c: mcp_matcher_branches(c)["metadata"]["match"][0].__setitem__(
        "path", list(COMPLETE_MCP_METADATA_ROUTES) + [
            "/.well-known/oauth-protected-resource/mcp/extra"]), id="metadata-extra"),
    pytest.param(lambda c: mcp_matcher_branches(c)["metadata"]["match"][0].__setitem__(
        "method", ["POST"]), id="metadata-wrong-method"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["match"][0].__setitem__(
        "path", list(COMPLETE_MCP_ROUTES) + ["/mcp"]), id="transport-duplicate"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["match"][0].__setitem__(
        "path", ["/mcp/*"]), id="transport-wildcard"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["match"][0].__setitem__(
        "path", list(COMPLETE_MCP_ROUTES) + ["/mcp/extra"]), id="transport-extra"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["match"][0].__setitem__(
        "method", ["GET"]), id="transport-wrong-method"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["handle"][0].__setitem__(
        "max_size", 65536), id="transport-larger-body"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["handle"][0].__setitem__(
        "max_size", 64000.0), id="transport-float-body"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["handle"][0].__setitem__(
        "max_size", True), id="transport-bool-body"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["handle"].pop(0),
                 id="transport-no-body-limit"),
    pytest.param(lambda c: mcp_matcher_branches(c)["metadata"]["handle"][-1]["headers"]
                 ["request"]["set"].__setitem__("Host", ["127.0.0.1"]),
                 id="metadata-loopback-host"),
    pytest.param(lambda c: mcp_matcher_branches(c)["transport"]["handle"][-1]["headers"]
                 ["request"]["set"].__setitem__("Host", [HOST]),
                 id="transport-public-host"),
    pytest.param(lambda c: mcp_matcher_branches(c)["metadata"]["handle"][-1]["headers"]
                 ["request"]["delete"].remove("CF-Connecting-IP"),
                 id="metadata-trimmed-strip-list"),
    pytest.param(lambda c: inner_of(c).remove(mcp_matcher_branches(c)["metadata"]),
                 id="metadata-branch-removed"),
    pytest.param(lambda c: inner_of(c).remove(mcp_matcher_branches(c)["transport"]),
                 id="transport-branch-removed"),
    pytest.param(lambda c: inner_of(c).insert(2, inner_of(c).pop(3)),
                 id="mcp-branches-reordered"),
])
def test_public_mcp_profile_mutations_refuse(mangle):
    live = observed_public_edge(False)
    mangle(live)
    with pytest.raises(ValueError):
        plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
             current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    with pytest.raises(ValueError):
        prepare_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                       relay_port=49152)
    with pytest.raises(ValueError):
        final_config(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                     relay_port=49152)


def test_plan_records_the_public_mcp_route_matrix():
    complete = {"metadata": list(COMPLETE_MCP_METADATA_ROUTES),
                "transport": list(COMPLETE_MCP_ROUTES)}
    ceo_only = plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=observed_public_edge(False),
                     current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert ceo_only["mcp_routes"] == {"observed_profile": "ceo_only", **complete}
    live = observed_public_edge(False)
    expect_complete_mcp(inner_of(live))
    already = plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
                   current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert already["mcp_routes"] == {"observed_profile": "complete", **complete}
    absent = plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=fullconfig(),
                  current_manifest=OLD, candidate_manifest=NEW, relay_port=49152)
    assert absent["mcp_routes"] == {"observed_profile": "absent",
                                    "metadata": [], "transport": []}
    # The plan still binds both planned configurations by their exact bytes.
    for value in (ceo_only, already, absent):
        assert value["bindings"]["prepare_fullconfig_sha256"] == module._sha256(
            prepare_config(fullconfig=(observed_public_edge(False) if value is ceo_only else
                                       (live if value is already else fullconfig())),
                           current_manifest=OLD, candidate_manifest=NEW, relay_port=49152))


def native_current_config(with_mcp=False):
    live = mcp_fullconfig() if with_mcp else fullconfig()
    get_paths_of(live)[:] = sorted(set(GET_ROUTES) | set(asset_routes(OLD)))
    post_paths_of(live)[:] = list(POST_ROUTES)
    expect_source_upgrade(inner_of(live))
    if with_mcp:
        expect_complete_mcp(inner_of(live))
    expect_native_upgrade(inner_of(live))
    return live


def assert_native_refused(live):
    for make in (
        lambda: plan(old_source=OLD_SHA, new_source=NEW_SHA, fullconfig=live,
            current_manifest=OLD, candidate_manifest=NEW, relay_port=49152),
        lambda: prepare_config(fullconfig=live, current_manifest=OLD,
            candidate_manifest=NEW, relay_port=49152),
        lambda: final_config(fullconfig=live, current_manifest=OLD,
            candidate_manifest=NEW, relay_port=49152),
    ):
        with pytest.raises(ValueError):
            make()


@pytest.mark.parametrize("with_mcp", [False, True])
@pytest.mark.parametrize("fault", [
    "missing", "extra", "duplicate", "reordered", "wildcard", "slash", "query",
    "wrong_method", "extra_matcher", "extra_handler", "handler_order",
    "duplicate_branch", "misplaced", "merged_get", "merged_post",
])
def test_native_branch_rejects_any_changed_closed_topology(with_mcp, fault):
    live = native_current_config(with_mcp)
    branches = inner_of(live)
    native = branches[-2]
    paths = native["match"][0]["path"]
    if fault == "missing":
        paths.pop()
    elif fault == "extra":
        paths.append("/os/executive/conversation/v2/arbitrary")
    elif fault == "duplicate":
        paths.append(paths[0])
    elif fault == "reordered":
        paths.reverse()
    elif fault in {"wildcard", "slash", "query"}:
        paths[0] += {"wildcard": "*", "slash": "/", "query": "?x=1"}[fault]
    elif fault == "wrong_method":
        native["match"][0]["method"] = ["GET"]
    elif fault == "extra_matcher":
        native["match"][0]["query"] = {"x": ["1"]}
    elif fault == "extra_handler":
        native["handle"].append(proxy())
    elif fault == "handler_order":
        native["handle"].reverse()
    elif fault == "duplicate_branch":
        branches.insert(-1, copy.deepcopy(native))
    elif fault == "misplaced":
        branches.insert(2, branches.pop(-2))
    else:
        target = 0 if fault == "merged_get" else 1
        branches[target]["match"][0]["path"].append(paths[0])
    assert_native_refused(live)


@pytest.mark.parametrize("with_mcp", [False, True])
@pytest.mark.parametrize("cap", [64000, 98304, 524287, 524289, 524288.0, True])
def test_native_branch_requires_exact_integer_request_limit(with_mcp, cap):
    live = native_current_config(with_mcp)
    inner_of(live)[-2]["handle"][0]["max_size"] = cap
    assert_native_refused(live)


@pytest.mark.parametrize("with_mcp", [False, True])
@pytest.mark.parametrize("mutation", sorted(PROXY_MUTATIONS))
def test_native_branch_requires_the_whole_public_host_proxy(with_mcp, mutation):
    live = native_current_config(with_mcp)
    PROXY_MUTATIONS[mutation](inner_of(live)[-2]["handle"][-1])
    assert_native_refused(live)


@pytest.mark.parametrize("fault", ["historical", "missing_source", "missing_current_get", "ceo_only"])
def test_native_branch_cannot_authorize_a_partial_or_historical_profile(fault):
    live = native_current_config(fault == "ceo_only")
    if fault == "historical":
        get_paths_of(live)[:] = sorted(set(SOURCE_CONTEXT_GET_ROUTES) | set(asset_routes(OLD)))
        post_paths_of(live)[:] = list(PRE_INSTRUCTION_ADMISSION_POST_ROUTES)
    elif fault == "missing_source":
        inner_of(live).pop(2)
    elif fault == "missing_current_get":
        get_paths_of(live).remove("/workspace/byok/roles/current")
    else:
        inner_of(live)[3]["match"][0]["path"] = list(MCP_METADATA_ROUTES)
        inner_of(live)[4]["match"][0]["path"] = list(MCP_ROUTES)
    assert_native_refused(live)


@pytest.mark.parametrize("with_mcp", [False, True])
def test_native_current_branch_preserves_wrappers_group_and_proxy_without_duplication(with_mcp):
    live = native_current_config(with_mcp)
    native = inner_of(live)[-2]
    native["group"] = "retained-native-group"
    native["handle"][-1]["transport"] = {"protocol": "http"}
    native["handle"] = [{"handler": "subroute", "routes": [{"handle": native["handle"]}]}]
    before = copy.deepcopy(live)
    planned, prepared, final = transition_values(live)
    assert live == before
    assert planned["observed_native_branch"] is True
    assert planned["native_post_routes"] == list(NATIVE_PATHS)
    assert planned["native_max_body"] == 524288
    for changed in (prepared, final):
        branches = inner_of(changed)
        assert len(branches) == (7 if with_mcp else 5)
        assert branches[-2] == inner_of(before)[-2]
        assert sum(b.get("match") == [{"method": ["POST"], "path": list(NATIVE_PATHS)}]
                   for b in branches) == 1
        assert branches[1]["handle"][0]["max_size"] == 64000
        assert branches[2]["handle"][0]["max_size"] == 98304
        if with_mcp:
            assert branches[4]["handle"][0]["max_size"] == 64000

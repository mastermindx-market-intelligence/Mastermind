"""Focused source-operation edge tests using actual repository modules.

All configurations are inert fixtures. Native Caddy syntax/topology qualification
is covered separately by test_os_public_edge; no server reload is performed.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
import types

_HERE = Path(__file__).resolve().parent
RELAY = 49200
RELAY_OTHER = 49301
OLD_SOURCE = "a" * 40
NEW_SOURCE = "b" * 40
from integrations.mastermind_executive_app.os_assets import os_asset_mimes
from ops.executive_os import os_public_edge as edge, os_public_edge_transition as transition

def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _manifest(suffix):
    names=['index.html','assets/index-'+suffix+'.css','assets/index-shared.js']
    return {'schema':'mastermind.os_assets.v1','files':[
        {'path':path,'byte_count':1024+len(path),'sha256':_digest(path), 'mime':mime}
        for path,mime in os_asset_mimes(names).items()]}

CURRENT_MANIFEST = _manifest('current')
CANDIDATE_MANIFEST = _manifest('candidate')
CURRENT_ROUTES = edge.asset_routes(CURRENT_MANIFEST)
CANDIDATE_ROUTES = edge.asset_routes(CANDIDATE_MANIFEST)


def _proxy(relay_port: int, host: str) -> dict:
    return transition._expected_proxy(relay_port, host)


def _branch(method: str, paths, handlers, group) -> dict:
    item = {"match": [{"method": [method], "path": list(paths)}], "handle": handlers}
    if group is not None:
        item["group"] = group
    return item


def _body(cap: int) -> dict:
    return {"handler": "request_body", "max_size": cap}


def _inner(relay_port: int, get_paths, post_paths, *, source=False, mcp=False,
           source_paths=None, source_cap=None, post_cap=64000, mcp_cap=64000,
           group="group_0") -> list:
    items = [
        _branch("GET", get_paths, [_proxy(relay_port, edge.HOST)], group),
        _branch("POST", post_paths, [_body(post_cap), _proxy(relay_port, edge.HOST)], group),
    ]
    if source:
        paths = list(edge.SOURCE_POST_ROUTES) if source_paths is None else list(source_paths)
        cap = edge.SOURCE_MAX_BODY if source_cap is None else source_cap
        items.append(_branch("POST", paths, [_body(cap), _proxy(relay_port, edge.HOST)], group))
    if mcp:
        items.append(_branch("GET", [edge.MCP_METADATA_ROUTE], [_proxy(relay_port, edge.HOST)], group))
        items.append(_branch("POST", list(edge.MCP_ROUTES),
                             [_body(mcp_cap), _proxy(relay_port, "127.0.0.1")], group))
    items.append({"handle": [{"handler": "static_response", "abort": True}]})
    return items


def _fullconfig(inner_routes: list, *, relay_port: int = RELAY, extra_server=False) -> dict:
    host_route = {
        "match": [{"host": [edge.HOST]}],
        "handle": [{"handler": "subroute", "routes": [
            {"handle": [{"handler": "subroute", "routes": list(inner_routes)}]},
        ]}],
        "terminal": True,
    }
    config = {"apps": {"http": {"servers": {"srv0": {"routes": [host_route]}}}}}
    if extra_server:
        config["apps"]["http"]["servers"]["srv1"] = {"listen": [":443"], "routes": [
            {"match": [{"host": ["unrelated.example"]}],
             "handle": [{"handler": "static_response", "body": "untouched"}], "terminal": True},
        ]}
    return config


def _inner_of(config: dict) -> list:
    return (config["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["routes"][0]
            ["handle"][0]["routes"])


@contextlib.contextmanager
def _refused(label: str, errors=(ValueError,)):
    refused = False
    try:
        yield
    except errors:
        refused = True
    if not refused:
        raise AssertionError("expected refusal: " + label)


def _plan(cfg, *, current=CURRENT_MANIFEST, candidate=CANDIDATE_MANIFEST, relay=RELAY):
    return transition.plan(old_source=OLD_SOURCE, new_source=NEW_SOURCE, fullconfig=cfg,
                           current_manifest=current, candidate_manifest=candidate,
                           relay_port=relay)


def _final(cfg, *, current=CURRENT_MANIFEST, candidate=CANDIDATE_MANIFEST, relay=RELAY):
    return transition.final_config(fullconfig=cfg, current_manifest=current,
                                   candidate_manifest=candidate, relay_port=relay)


def _prepare(cfg, *, current=CURRENT_MANIFEST, candidate=CANDIDATE_MANIFEST, relay=RELAY):
    return transition.prepare_config(fullconfig=cfg, current_manifest=current,
                                     candidate_manifest=candidate, relay_port=relay)


def test_legacy_three_branch_transition():
    # The observed legacy shape must be one whole admitted profile pair, here
    # the control-room GET set with the CCR action POST set.
    get_paths = list(edge.CONTROL_ROOM_GET_ROUTES) + list(CURRENT_ROUTES)
    cfg = _fullconfig(_inner(RELAY, get_paths, list(edge.CONTROL_ROOM_POST_ROUTES)), extra_server=True)
    plan = _plan(cfg)
    assert plan["schema"] == transition.PLAN_SCHEMA and plan["host"] == edge.HOST
    assert plan["installed"] is False and plan["published"] is False
    assert plan["bindings"]["prepare_fullconfig_sha256"] == transition._sha256(_prepare(cfg))
    assert plan["bindings"]["final_fullconfig_sha256"] == transition._sha256(_final(cfg))
    final = _final(cfg)
    inner = _inner_of(final)
    assert len(inner) == 4
    assert inner[0]["match"][0]["path"] == sorted(set(edge.GET_ROUTES) | set(CANDIDATE_ROUTES))
    assert inner[1]["match"][0]["path"] == list(edge.POST_ROUTES)
    assert inner[1]["handle"][0] == _body(64000)
    assert inner[2] == transition._source_branch(RELAY, "group_0")
    assert inner[2]["handle"][0] == _body(edge.SOURCE_MAX_BODY)
    assert (inner[2]["handle"][1]["headers"]["request"]["set"]["Host"] == [edge.HOST]
            and inner[2]["match"][0] == {"method": ["POST"], "path": list(edge.SOURCE_POST_ROUTES)})
    assert inner[3] == {"handle": [{"handler": "static_response", "abort": True}]}
    assert final["apps"]["http"]["servers"]["srv1"] == cfg["apps"]["http"]["servers"]["srv1"]
    prepare = _prepare(cfg)
    assert _inner_of(prepare)[0]["match"][0]["path"] == sorted(
        set(edge.GET_ROUTES) | set(CURRENT_ROUTES) | set(CANDIDATE_ROUTES))
    assert _inner_of(prepare)[2] == transition._source_branch(RELAY, "group_0")
    assert plan["get_routes"]["final"] == sorted(set(edge.GET_ROUTES) | set(CANDIDATE_ROUTES))
    assert plan["post_routes"] == list(edge.POST_ROUTES)
    assert plan["source_post_routes"] == list(edge.SOURCE_POST_ROUTES)
    assert plan["shared_assets_verified"] == ["assets/index-shared.js"]


def test_legacy_five_branch_mcp_transition():
    get_paths = list(edge.SOURCE_CONTEXT_GET_ROUTES) + list(CURRENT_ROUTES)
    cfg = _fullconfig(_inner(RELAY, get_paths, list(edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES), mcp=True))
    final = _final(cfg)
    inner = _inner_of(final)
    assert len(inner) == 6
    assert inner[2] == transition._source_branch(RELAY, "group_0")
    assert inner[3]["match"][0]["path"] == list(edge.COMPLETE_MCP_METADATA_ROUTES)
    assert inner[4]["match"][0]["path"] == list(edge.COMPLETE_MCP_ROUTES)
    assert inner[4]["handle"][0] == _body(edge.MCP_MAX_BODY)
    assert inner[4]["handle"][1] == _proxy(RELAY, "127.0.0.1")
    assert inner[5] == {"handle": [{"handler": "static_response", "abort": True}]}
    assert inner[0]["match"][0]["path"] == sorted(set(edge.GET_ROUTES) | set(CANDIDATE_ROUTES))


def test_current_four_branch_source_transition():
    get_paths = list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES)
    cfg = _fullconfig(_inner(RELAY, get_paths, list(edge.POST_ROUTES), source=True))
    final = _final(cfg, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    inner = _inner_of(final)
    original = _inner_of(cfg)
    assert len(inner) == 4
    assert inner[0]["match"][0]["path"] == sorted(set(edge.GET_ROUTES) | set(CANDIDATE_ROUTES))
    assert inner[1:] == original[1:]


def test_current_six_branch_idempotent_transition():
    # The already-canonical observed form (sorted unique union) must come back
    # byte-identical; the duplicated matcher list form is normalized instead.
    get_paths = sorted(set(edge.GET_ROUTES) | set(CANDIDATE_ROUTES))
    observed = _fullconfig(_inner(RELAY, get_paths, list(edge.POST_ROUTES), source=True, mcp=True))
    final = _final(observed, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    # The observed CEO-only public-MCP pair is upgraded to the complete pair;
    # the complete pair is then idempotent.
    assert transition._canonical(final) != transition._canonical(observed)
    assert transition._canonical(
        _final(final, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    ) == transition._canonical(final)
    staged = _final(_fullconfig(_inner(RELAY, list(edge.SOURCE_CONTEXT_GET_ROUTES) + list(CURRENT_ROUTES),
                                       list(edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES))))
    again = _final(staged, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    assert transition._canonical(staged) == transition._canonical(again)
    plan_a = _plan(_fullconfig(_inner(RELAY, list(edge.SOURCE_CONTEXT_GET_ROUTES) + list(CURRENT_ROUTES),
                                      list(edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES))))
    plan_b = _plan(staged, current=CANDIDATE_MANIFEST)
    assert (plan_a["bindings"]["final_fullconfig_sha256"]
            == plan_b["bindings"]["final_fullconfig_sha256"])


def test_body_caps_unchanged_and_dedicated():
    assert edge.SOURCE_MAX_BODY == 98304 and edge.MCP_MAX_BODY == 64000
    template = edge._TEMPLATE.read_text(encoding="utf-8")
    assert template.count("max_size 98304") == 1 and template.count("max_size 64KB") == 2
    assert "96KB" not in template
    rendered = edge.render(CANDIDATE_MANIFEST, RELAY)
    assert rendered.count("max_size 64KB") == 2 and rendered.count("max_size 98304") == 1
    assert rendered.count("max_size 98304") == 1
    assert str(RELAY) in rendered and "__RELAY_PORT__" not in rendered
    assert "__ASSET_PATHS__" not in rendered and "/os/assets/index-candidate.css" in rendered
    with _refused("wrong source body cap"):
        cfg = _fullconfig(_inner(RELAY, list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES),
                                 list(edge.POST_ROUTES), source=True, source_cap=100352))
        _final(cfg, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    with _refused("raised legacy cap"):
        cfg = _fullconfig(_inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES),
                                 list(edge.POST_ROUTES), post_cap=98304))
        _final(cfg)
    with _refused("raised MCP cap"):
        cfg = _fullconfig(_inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES),
                                 list(edge.POST_ROUTES), mcp=True, mcp_cap=98304))
        _final(cfg)


def test_get_route_coherence():
    assert edge.GET_ROUTES.count("/workspace/source-operation/context") == 1
    assert edge.GET_ROUTES.count("/workspace/source-operation/operation") == 1
    assert edge.PRE_PROJECT_INSTRUCTIONS_GET_ROUTES[-1] == "/workspace/source-operation/operation"
    assert edge.SOURCE_CONTEXT_GET_ROUTES == tuple(edge.PRE_PROJECT_INSTRUCTIONS_GET_ROUTES[:-1])
    profiles = edge.TRANSITION_ROUTE_PROFILES
    assert profiles[-1] == (edge.GET_ROUTES, edge.POST_ROUTES)
    assert (edge.SOURCE_CONTEXT_GET_ROUTES, edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES) in profiles
    assert edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES[-6:] == edge.CONTROL_ROOM_ACTION_ROUTES + edge.PROJECT_ADMISSION_POST_ROUTES
    # The old final POST tail stays exact on its complete predecessor; the
    # planning and conversation route groups extend POST_ROUTES after it.
    assert edge.PRE_JOURNEY_POST_ROUTES == edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES + ('/workspace/instruction-admission/pause',)
    assert edge.PRE_DIRECT_NATIVE_POST_ROUTES == (edge.PRE_JOURNEY_POST_ROUTES + edge.PROJECT_PLANNING_POST_ROUTES
                                + edge.PROJECT_CONVERSATION_READ_POST_ROUTES
                                + edge.FRESH_CONVERSATION_POST_ROUTES + ('/os/executive/session/send',)
                                + edge.PROJECT_EXECUTION_POST_ROUTES)
    assert edge.PRE_COMPANY_PRIORITIES_POST_ROUTES == edge.PRE_DIRECT_NATIVE_POST_ROUTES + (
        "/os/executive/direct-native/result", "/os/executive/direct-native/consume",
        "/os/executive/direct-native/correction",
    )
    assert edge.POST_ROUTES == edge.PRE_COMPANY_PRIORITIES_POST_ROUTES + (
        "/os/executive/company-priorities",
    )
    assert (edge.PRE_AUTHORIZATION_IDENTITY_GET_ROUTES, edge.PRE_COMPANY_PRIORITIES_POST_ROUTES) in profiles
    assert not set(edge.SOURCE_POST_ROUTES) & set(edge.POST_ROUTES)
    template = edge._TEMPLATE.read_text(encoding="utf-8")
    get_line = "path " + " ".join(edge.GET_ROUTES) + " __ASSET_PATHS__"
    assert template.count(get_line) == 1
    assert template.count("path " + " ".join(edge.SOURCE_POST_ROUTES)) == 1
    assert edge.render(CURRENT_MANIFEST, RELAY).count("/workspace/source-operation/context") == 1


def test_refuses_wildcard_duplicate_reordered_source():
    base = _inner(RELAY, list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES), list(edge.POST_ROUTES))
    wildcard = ["/workspace/source-operation/*"] + list(edge.SOURCE_POST_ROUTES)[1:]
    cfg = _fullconfig(_inner(RELAY, list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES),
                             list(edge.POST_ROUTES), source=True, source_paths=wildcard))
    with _refused("wildcard source path"):
        _final(cfg, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    reordered = list(reversed(edge.SOURCE_POST_ROUTES))
    cfg = _fullconfig(_inner(RELAY, list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES),
                             list(edge.POST_ROUTES), source=True, source_paths=reordered))
    with _refused("reordered source paths"):
        _final(cfg, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    duplicated = list(edge.SOURCE_POST_ROUTES[:3]) + [edge.SOURCE_POST_ROUTES[3], edge.SOURCE_POST_ROUTES[0]]
    cfg = _fullconfig(_inner(RELAY, list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES),
                             list(edge.POST_ROUTES), source=True, source_paths=duplicated))
    with _refused("duplicated source paths"):
        _final(cfg, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)


def test_refuses_merged_source_into_legacy_post():
    merged = list(edge.POST_ROUTES) + list(edge.SOURCE_POST_ROUTES)
    cfg = _fullconfig(_inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES), merged))
    with _refused("merged source routes"):
        _final(cfg)


def test_refuses_mixed_or_partial_profiles():
    new_get = list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES)
    cfg = _fullconfig(_inner(RELAY, new_get, list(edge.POST_ROUTES)))
    with _refused("new GET without source branch"):
        _final(cfg, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    legacy_get = list(edge.SOURCE_CONTEXT_GET_ROUTES) + list(CURRENT_ROUTES)
    cfg = _fullconfig(_inner(RELAY, legacy_get, list(edge.POST_ROUTES), source=True))
    with _refused("source branch with legacy GET profile"):
        _final(cfg)


def test_refuses_changed_proxy_or_relay():
    cfg = _fullconfig(_inner(RELAY_OTHER, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES),
                             list(edge.POST_ROUTES)))
    with _refused("relay port drift"):
        _final(cfg)
    inner = _inner(RELAY, list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES), list(edge.POST_ROUTES), source=True)
    inner[2]["handle"][1] = _proxy(RELAY, "evil.example")
    cfg = _fullconfig(inner)
    with _refused("changed source proxy host"):
        _final(cfg, current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)
    inner = _inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES), list(edge.POST_ROUTES))
    del inner[1]["handle"][1]["headers"]["request"]["delete"][3]
    cfg = _fullconfig(inner)
    with _refused("missing stripped forwarded header"):
        _final(cfg)
    inner = _inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES), list(edge.POST_ROUTES))
    inner[0]["handle"][0]["headers"]["request"]["set"]["X-Forwarded-Proto"] = ["http"]
    cfg = _fullconfig(inner)
    with _refused("changed forwarded proto"):
        _final(cfg)


def test_refuses_branch_reorder_and_shape():
    inner = _inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES), list(edge.POST_ROUTES))
    inner[0], inner[1] = inner[1], inner[0]
    with _refused("swapped GET/POST order"):
        _final(_fullconfig(inner))
    source = _branch("POST", list(edge.SOURCE_POST_ROUTES),
                     [_body(edge.SOURCE_MAX_BODY), _proxy(RELAY, edge.HOST)], "group_0")
    inner = _inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES),
                   list(edge.POST_ROUTES), mcp=True)
    inner.insert(4, source)
    with _refused("source branch after MCP branches"):
        _final(_fullconfig(inner))
    inner = _inner(RELAY, list(edge.GET_ROUTES) + list(CANDIDATE_ROUTES), list(edge.POST_ROUTES), source=True)
    inner[2]["handle"] = {"handler": "request_body", "max_size": edge.SOURCE_MAX_BODY}
    with _refused("non-list branch handlers"):
        _final(_fullconfig(inner), current=CANDIDATE_MANIFEST, candidate=CANDIDATE_MANIFEST)


def test_stage_receipt_and_exclusive_creation():
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory).resolve() / "os-public-edge.caddy.json"
        receipt = edge.stage(manifest=CANDIDATE_MANIFEST, relay_port=RELAY, output=target)
        routes = receipt["routes"]
        assert receipt["schema"] == "mastermind.os_public_edge.stage.v1"
        assert routes["get"] == sorted(set(edge.GET_ROUTES) | set(CANDIDATE_ROUTES))
        assert routes["post"] == list(edge.POST_ROUTES)
        assert routes["source_post"] == list(edge.SOURCE_POST_ROUTES)
        assert receipt["mcp"] == {"get": list(edge.COMPLETE_MCP_METADATA_ROUTES),
                                  "post": list(edge.COMPLETE_MCP_ROUTES)}
        assert receipt["installed"] is False
        assert receipt["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        # Exclusive creation stays visible as FileExistsError, never a replace.
        with _refused("exclusive re-stage", errors=(FileExistsError,)):
            edge.stage(manifest=CANDIDATE_MANIFEST, relay_port=RELAY, output=target)


def test_stage_transition_and_prepare_check():
    cfg = _fullconfig(_inner(RELAY, list(edge.SOURCE_CONTEXT_GET_ROUTES) + list(CURRENT_ROUTES),
                             list(edge.PRE_INSTRUCTION_ADMISSION_POST_ROUTES)))
    plan = _plan(cfg)
    prepared = _prepare(cfg)
    final = _final(cfg)
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory).resolve()
        receipt = transition.stage_transition(plan=plan, prepare=prepared, final=final, out=out)
        assert receipt["installed"] is False and receipt["published"] is False
        for name, digest in receipt["files"].items():
            payload = (out / name).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == digest
            assert payload.endswith(b"\n")
        check = transition.preparation_complete(observed=prepared, prepared=prepared)
        assert check["prepared_observed_exactly"] is True and check["installed"] is False
        with _refused("prepared config not observed exactly"):
            transition.preparation_complete(observed=cfg, prepared=prepared)
    diagnostic = transition.restart_diagnostic(observed=cfg, autosave=cfg, startup=cfg)
    assert diagnostic["restart_safe_by_config_equality"] is True
    assert diagnostic["restart_verified"] is False


def test_template_branch_layout_and_loopback():
    template = edge._TEMPLATE.read_text(encoding="utf-8")
    assert template.count("__RELAY_PORT__") == 5 and template.count("__ASSET_PATHS__") == 1
    assert template.count("path " + " ".join(edge.POST_ROUTES) + "\n") == 1
    assert template.count("path " + " ".join(edge.SOURCE_POST_ROUTES) + "\n") == 1
    assert template.count("path " + " ".join(edge.GET_ROUTES) + " __ASSET_PATHS__\n") == 1
    blocks = template.split("handle ")
    assert sum(1 for block in blocks if "Host mcp.mastermind-x.com" in block) == 4
    assert sum(1 for block in blocks if "Host 127.0.0.1\n" in block) == 1
    for header in transition._STRIPPED_REQUEST_HEADERS:
        assert template.count("header_up -" + header) == 5
    with tempfile.TemporaryDirectory() as directory:
        original, target = edge._TEMPLATE, Path(directory).resolve() / "tampered.template"
        payload = template.replace("path " + " ".join(edge.SOURCE_POST_ROUTES) + "\n", "")
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
        try:
            edge._TEMPLATE = target
            with _refused("tampered template without source branch"):
                edge.render(CANDIDATE_MANIFEST, RELAY)
        finally:
            edge._TEMPLATE = original


def test_refuses_invalid_manifest_and_profile_inputs():
    with _refused("bad manifest schema"):
        edge.asset_routes({"schema": "mastermind.os_assets.v2", "files": []})
    with _refused("bad asset mime"):
        broken = copy.deepcopy(CANDIDATE_MANIFEST)
        broken["files"][0]["mime"] = "application/x-httpd-php"
        edge.asset_routes(broken)
    with _refused("shared asset bytes changed"):
        broken = copy.deepcopy(CANDIDATE_MANIFEST)
        next(item for item in broken["files"] if item["path"] == "assets/index-shared.js")["sha256"] = _digest("changed")
        _final(_fullconfig(_inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES),
                                  list(edge.POST_ROUTES))), candidate=broken)
    with _refused("identical source ids"):
        cfg = _fullconfig(_inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES),
                                 list(edge.POST_ROUTES)))
        transition.plan(old_source=OLD_SOURCE, new_source=OLD_SOURCE, fullconfig=cfg,
                        current_manifest=CURRENT_MANIFEST, candidate_manifest=CANDIDATE_MANIFEST,
                        relay_port=RELAY)
    with _refused("relay port out of range"):
        _plan(_fullconfig(_inner(RELAY, list(edge.LEGACY_GET_ROUTES) + list(CURRENT_ROUTES),
                                 list(edge.POST_ROUTES))), relay=60000)


def _main() -> None:
    tests = [(name, value) for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value) and name != "test__main__"]
    for name, test in tests:
        test()
    print("ok: %d source-operation public-edge tests" % len(tests))


if __name__ == "__main__":
    _main()

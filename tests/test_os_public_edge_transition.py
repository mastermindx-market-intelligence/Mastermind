import copy
import hashlib
import json
import os
import sys

import pytest

from integrations.mastermind_executive_app.os_assets import os_asset_mimes
from ops.executive_os import os_public_edge_transition as module
from ops.executive_os.os_public_edge import (
    GET_ROUTES, HOST, LEGACY_GET_ROUTES, LEGACY_POST_ROUTES, POST_ROUTES, asset_routes,
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
            {"match": [{"method": ["POST"], "path": list(POST_ROUTES)}],
             "handle": [{"handler": "request_body", "max_size": 64000}, proxy(port)]},
            {"handle": [{"handler": "static_response", "abort": True}]},
        ]}],
        "terminal": True,
    }


def other_site(host="workspace.mastermind-x.com"):
    return {"match": [{"host": [host]}],
            "handle": [{"handler": "subroute", "routes": [
                {"match": [{"path": ["/healthz"]}],
                 "handle": [{"handler": "static_response", "body": "ok"}]}]}]}


def fullconfig(old=OLD, port=49152, site=None, routes=None):
    get_paths = sorted(list(GET_ROUTES) + list(asset_routes(old)))
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
    inner[0]["match"][0]["path"] = sorted(set(LEGACY_GET_ROUTES) | set(asset_routes(OLD)))
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
        get, post, terminal = inner_of(config)
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
def test_only_the_get_path_list_differs(maker):
    live = fullconfig()
    changed = maker(fullconfig=live, current_manifest=OLD, candidate_manifest=NEW,
                    relay_port=49152)
    stripped = copy.deepcopy(changed)
    stripped["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["routes"][0]["match"][0]["path"] = None
    original = copy.deepcopy(live)
    original["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["routes"][0]["match"][0]["path"] = None
    assert stripped == original
    assert inner_of(changed)[1] == inner_of(live)[1]
    assert inner_of(changed)[2] == inner_of(live)[2]
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

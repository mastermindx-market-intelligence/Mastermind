"""Real qualification and real single-manifest consumer; no privileged effects.

Only platform ownership/ACL checks and the npm build are replaced in temporary
fixtures. Git source qualification, seal verification, bundle digest, byte/MIME
contracts, phase journals and OsStaticApp are exercised as shipped. Publication
uses an inert HTTP stand-in; neither root custody nor live deployment is claimed.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

import pytest

from ops.executive_os import executive_mcp_entry as entry
from ops.executive_os import os_public_edge_publication as m
from ops.executive_os import os_release_assets as assets
from ops.executive_os import release_manifest as seals
from ops.executive_os.os_public_edge import HOST, GET_ROUTES, POST_ROUTES, asset_routes


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def make_dist(app, tag):
    dist = app / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(f'<script src="/os/assets/index-{tag}.js"></script>'
                                   f'<link href="/os/assets/index-{tag}.css">')
    (dist / f"assets/index-{tag}.js").write_text(f'console.log("{tag}");')
    (dist / f"assets/index-{tag}.css").write_text(f'body{{color:{tag}}}')
    return {"operator_uid": 501, "tools": {"/fixture/node": "a" * 64, "/fixture/npm": "b" * 64}}


def fullconfig(manifest):
    proxy = {"handler": "reverse_proxy", "upstreams": [{"dial": "127.0.0.1:49152"}]}
    return {"admin": {"listen": "127.0.0.1:2019"}, "apps": {
        "tls": {"automation": {"policies": [{"subjects": ["other.example.invalid"]}]}},
        "http": {"servers": {"srv0": {"listen": [":443"], "routes": [{
            "match": [{"host": [HOST]}], "terminal": True,
            "handle": [{"handler": "subroute", "routes": [
                {"match": [{"method": ["GET"], "path": sorted(set(GET_ROUTES) | set(asset_routes(manifest)))}],
                 "handle": [copy.deepcopy(proxy)]},
                {"match": [{"method": ["POST"], "path": list(POST_ROUTES)}],
                 "handle": [{"handler": "request_body", "max_size": 64000}, copy.deepcopy(proxy)]},
                {"handle": [{"handler": "static_response", "abort": True}]}]}]},
            {"match": [{"host": ["other.example.invalid"]}],
             "handle": [{"handler": "static_response", "body": "retained"}]}]}}}}}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(entry, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(assets, "_no_acl", lambda *a, **k: None)
    monkeypatch.setattr(assets, "_require_root", lambda: None)
    monkeypatch.setattr(seals, "_validate_owned_info", lambda *a, **k: None)
    monkeypatch.setattr(seals, "_has_acl", lambda *a, **k: False)
    monkeypatch.setattr(m, "_root", lambda: None)
    monkeypatch.setattr(m, "_owner", lambda s: m.require(s.st_uid == os.getuid()
                                                       and not s.st_mode & 0o022, "unsafe fixture custody"))
    repo = tmp_path / "source"
    repo.mkdir()
    for name in assets.INPUTS:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((assets.ROOT / name).read_bytes())
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "source")
    sha, tree = git(repo, "rev-parse", "HEAD"), git(repo, "rev-parse", "HEAD^{tree}")
    git(repo, "update-ref", "refs/remotes/origin/master", sha)
    monkeypatch.setattr(assets, "_build", lambda app, **kw: make_dist(app, "new"))
    bundle = tmp_path / "bundle"
    assets.prepare(source_repo=repo, expected_sha=sha, web_client_id="test-public-client",
                   output=bundle, build_user="fixture", node=Path("/fixture/node"), npm_cli=Path("/fixture/npm"))
    qualified = assets.qualify(bundle, expected_sha=sha, tree_sha=tree, source_repo=repo)
    old = tmp_path / "old"
    make_dist(old / "app/mastermind_os", "old")
    manifest = entry.build_os_asset_manifest(old)
    (old / assets.DIST / "asset-manifest.json").write_bytes(m.canonical(manifest))
    seals.create(old, "a" * 40, "b" * 40)
    live = tmp_path / "live.json"
    live.write_bytes(m.canonical(fullconfig(manifest)))
    return dict(old_root=old, old_sha="a" * 40, old_tree="b" * 40,
                new_bundle=bundle, source_repo=repo, new_sha=sha, new_tree=tree,
                new_digest=qualified.digest, live_config=live, relay_port=49152,
                out=tmp_path / "stage")


class InertRelay:
    def __init__(self, inputs):
        self.current = json.loads(inputs["live_config"].read_bytes())
        self.apps = {"old": entry.load_os_app(inputs["old_root"]),
                     "new": entry.load_os_app(inputs["new_bundle"])}
        self.selected = "old"
        self.etag = '"0"'
        self.events = []
        self.bad = None

    def http(self, port, method, path, *, body=None, headers=None, maximum=m.MAX_BYTES):
        if port == 2019:
            self.events.append((method, "config"))
            if method == "POST":
                assert headers["If-Match"] == self.etag
                assert headers["Content-Type"] == "application/json"
                self.current = json.loads(body)
                self.etag = '"next"'
                if self.bad == "post-lost":
                    raise OSError("reply lost after effect")
                if self.bad == "readback":
                    self.current["unexpected"] = True
                return 200, {}, b""
            return 200, {"etag": self.etag}, m.canonical(self.current)
        self.events.append(("GET", self.selected, path))
        messages = []
        async def invoke():
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message):
                messages.append(message)
            await self.apps[self.selected]({"type": "http", "method": "GET", "path": path,
                "raw_path": path.encode(), "query_string": b"", "headers": []}, receive, send)
        asyncio.run(invoke())
        start = next(v for v in messages if v["type"] == "http.response.start")
        content = b"".join(v.get("body", b"") for v in messages if v["type"] == "http.response.body")
        response_headers = {k.decode(): v.decode() for k, v in start["headers"]}
        if self.bad == "mime":
            response_headers["content-type"] = "application/octet-stream"
        elif self.bad == "short":
            content = content[:-1]
        elif self.bad == "extra":
            content += b"x"
        elif self.bad == "bytes":
            content = b"x" * len(content)
        return start["status"], response_headers, content


@pytest.fixture
def staged(inputs, monkeypatch):
    result = m.stage_host(**inputs)
    relay = InertRelay(inputs)
    monkeypatch.setattr(m, "_http", relay.http)
    monkeypatch.setattr(m, "_listener", lambda port, pid: m.require((port, pid) == (49152, 123), "listener differs"))
    def validate(stage, phase, config):
        assert json.loads(stage.read("prepare.json" if phase == "prepare" else "final.json")) == config
        relay.events.append(("validate", phase))
    monkeypatch.setattr(m, "_validate", validate)
    return inputs, result, relay


def publish(staged, phase="prepare", **changes):
    i, r, _ = staged
    return m.publish(**{**dict(stage_path=i["out"], stage_digest=r["stage_digest"],
                              listener_pid=123, phase=phase), **changes})


def ready(staged, **changes):
    i, r, _ = staged
    return m.verify_cutover(**{**dict(stage_path=i["out"], stage_digest=r["stage_digest"],
                                     new_sha=i["new_sha"], new_digest=i["new_digest"]), **changes})


def test_real_consumer_two_phase_order_and_single_selected_release(staged):
    i, r, relay = staged
    with pytest.raises(FileNotFoundError):
        ready(staged)
    before = copy.deepcopy(relay.current)
    assert publish(staged)["state"] == "PREPARED"
    post = relay.events.index(("POST", "config"))
    assert any(v == ("GET", "old", "/os/auth/callback") for v in relay.events[:post])
    assert not any(v[:2] == ("GET", "new") for v in relay.events)
    assert ready(staged)["state"] == "CUTOVER_READY"
    # This is the test host's explicit switch, never a publisher callback.
    relay.selected = "new"
    assert publish(staged, "finalize")["state"] == "FINAL"
    assert relay.events.count(("POST", "config")) == 2
    assert relay.current["apps"]["tls"] == before["apps"]["tls"]
    paths = relay.current["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["routes"][0]["match"][0]["path"]
    assert "/os/assets/index-old.js" not in paths and "/os/assets/index-new.js" in paths
    assert relay.http(49152, "GET", "/os/assets/index-old.js")[0] == 404
    with pytest.raises(ValueError):
        ready(staged)
    with pytest.raises(ValueError):
        publish(staged, "finalize")
    with pytest.raises(ValueError):
        publish(staged)


@pytest.mark.parametrize("field,value", [("new_digest", "c" * 64), ("new_sha", "d" * 40),
    ("new_tree", "e" * 40), ("old_sha", "f" * 40), ("old_tree", "0" * 40)])
def test_real_qualification_rejects_wrong_provenance_before_stage(inputs, field, value):
    with pytest.raises((ValueError, RuntimeError)):
        m.stage_host(**{**inputs, field: value})
    assert not inputs["out"].exists()


@pytest.mark.parametrize("damage", ["bytes", "manifest", "receipt", "duplicate", "unprotected"])
def test_stage_rejects_actual_changed_bundle_or_protected_source(inputs, damage):
    p = inputs["new_bundle"]
    if damage == "unprotected":
        git(inputs["source_repo"], "update-ref", "-d", "refs/remotes/origin/master")
    else:
        path = p / (assets.RECEIPT if damage in ("receipt", "duplicate") else assets.DIST +
                    ("/asset-manifest.json" if damage == "manifest" else "/assets/index-new.js"))
        path.chmod(0o644)
        if damage == "duplicate":
            raw = path.read_bytes().rstrip()
            path.write_bytes(raw[:-1] + b',"source_sha":"' + inputs["new_sha"].encode() + b'"}')
            # Even if caller supplies the new opaque digest, duplicate JSON is rejected.
            q = assets.qualify(p, expected_sha=inputs["new_sha"], tree_sha=inputs["new_tree"], source_repo=inputs["source_repo"])
            inputs["new_digest"] = q.digest
        else:
            path.write_bytes(b"{}" if damage in ("receipt", "manifest") else b"changed")
    with pytest.raises((ValueError, RuntimeError, KeyError)):
        m.stage_host(**inputs)
    assert not inputs["out"].exists()


@pytest.mark.parametrize("bad", ["mime", "short", "extra", "bytes"])
def test_wrong_old_bytes_before_intent(staged, bad):
    i, _, relay = staged
    relay.bad = bad
    with pytest.raises(ValueError):
        publish(staged)
    assert not (i["out"] / m.OPERATION).exists()
    assert ("POST", "config") not in relay.events


@pytest.mark.parametrize("failure", ["post-lost", "readback", "receipt-write", "after-receipt", "intent-only"])
def test_uncertain_prepare_blocks_replay_and_cutover_and_final(staged, monkeypatch, failure):
    i, _, relay = staged
    relay.bad = failure
    original = m.PrivateDirectory.write
    def broken(self, name, raw):
        if failure == "receipt-write" and name == "prepare-receipt.json":
            raise OSError("receipt persistence failed")
        original(self, name, raw)
        if failure == "after-receipt" and name == "prepare-receipt.json":
            raise OSError("receipt fsync return uncertain")
        if failure == "intent-only" and name == "prepare-intent.json":
            raise OSError("crashed before POST")
    monkeypatch.setattr(m.PrivateDirectory, "write", broken)
    with pytest.raises((OSError, ValueError)):
        publish(staged)
    assert (i["out"] / m.OPERATION / "prepare-intent.json").exists()
    post_count = relay.events.count(("POST", "config"))
    for action in (lambda: publish(staged), lambda: publish(staged, "finalize"), lambda: ready(staged)):
        with pytest.raises((ValueError, FileNotFoundError)):
            action()
    assert relay.events.count(("POST", "config")) == post_count


def test_final_requires_new_bytes_and_original_prepare(staged):
    publish(staged)
    with pytest.raises(ValueError, match="selected relay"):
        publish(staged, "finalize")
    assert not (staged[0]["out"] / m.OPERATION / "finalize-intent.json").exists()
    with pytest.raises(ValueError, match="target"):
        ready(staged, new_sha="f" * 40)


def test_cutover_refuses_later_config_drift(staged):
    publish(staged)
    staged[2].current["apps"]["tls"]["changed"] = True
    with pytest.raises(ValueError, match="no longer current"):
        ready(staged)


def test_uncertain_final_is_not_replayed(staged):
    publish(staged)
    staged[2].selected = "new"
    staged[2].bad = "post-lost"
    with pytest.raises(OSError):
        publish(staged, "finalize")
    posts = staged[2].events.count(("POST", "config"))
    with pytest.raises(ValueError):
        publish(staged, "finalize")
    with pytest.raises(ValueError):
        ready(staged)
    assert staged[2].events.count(("POST", "config")) == posts


@pytest.mark.parametrize("phase", ["prepare", "finalize"])
def test_reconciliation_racing_receipt_cannot_return_success(staged, monkeypatch, phase):
    if phase == "finalize":
        publish(staged)
        staged[2].selected = "new"
    original = m.PrivateDirectory.write
    def raced(self, name, raw):
        original(self, name, raw)
        if name == phase + "-receipt.json":
            original(self, phase + "-reconciliation.json", b'{"state":"RECONCILIATION_REQUIRED"}')
    monkeypatch.setattr(m.PrivateDirectory, "write", raced)
    with pytest.raises((ValueError, FileExistsError)):
        publish(staged, phase)
    posts = staged[2].events.count(("POST", "config"))
    for action in (lambda: ready(staged), lambda: publish(staged, "finalize")):
        with pytest.raises(ValueError):
            action()
    assert staged[2].events.count(("POST", "config")) == posts


@pytest.mark.parametrize("field", ["state", "stage_digest", "config_digest", "intent_digest", "predecessor_digest", "new_bundle_digest"])
def test_receipt_bindings_are_validated_not_just_state(staged, field):
    publish(staged)
    path = staged[0]["out"] / m.OPERATION / "prepare-receipt.json"
    r = json.loads(path.read_bytes())
    r[field] = "fabricated"
    path.write_bytes(m.canonical(r))
    with pytest.raises(ValueError):
        ready(staged)
    with pytest.raises(ValueError):
        publish(staged, "finalize")


@pytest.mark.parametrize("damage", ["stage-digest", "config", "extra-file", "symlink", "hardlink", "mode", "directory"])
def test_immutable_stage_custody_and_bytes(staged, damage, tmp_path):
    i, r, relay = staged
    path = i["out"] / "prepare.json"
    if damage == "stage-digest":
        r["stage_digest"] = "0" * 64
    elif damage == "config":
        path.write_bytes(b"{}")
    elif damage == "extra-file":
        (i["out"] / "extra").write_bytes(b"unknown")
    elif damage in ("symlink", "hardlink"):
        backup = tmp_path / "content"
        path.rename(backup)
        path.symlink_to(backup) if damage == "symlink" else os.link(backup, path)
    elif damage == "mode":
        path.chmod(0o644)
    else:
        i["out"].chmod(0o755)
    with pytest.raises((ValueError, OSError)):
        publish(staged)
    assert ("POST", "config") not in relay.events


def test_descriptor_directory_replacement_is_not_followed(staged, tmp_path):
    path = staged[0]["out"]
    with m.private(path) as held:
        path.rename(tmp_path / "prior")
        path.mkdir(mode=0o700)
        with pytest.raises(ValueError, match="replaced"):
            held.write("intent.json", b"{}")
    assert not list(path.iterdir())


@pytest.mark.parametrize("drift", ["tls", "other", "etag", "pid"])
def test_current_config_etag_listener_drift_no_post(staged, monkeypatch, drift):
    _, _, relay = staged
    if drift in ("tls", "other"):
        relay.current["apps"]["tls" if drift == "tls" else "http"]["drift"] = True
    elif drift == "etag":
        original = m._config
        count = 0
        def config():
            nonlocal count
            count += 1
            value, etag = original()
            return value, etag if count == 1 else '"changed"'
        monkeypatch.setattr(m, "_config", config)
    with pytest.raises(ValueError):
        publish(staged, listener_pid=999 if drift == "pid" else 123)
    assert ("POST", "config") not in relay.events


def test_fixed_production_listener_argv_and_no_extra_pid(monkeypatch):
    calls = []
    def run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, 'LISTEN 0 128 127.0.0.1:49152 0.0.0.0:* users:(("ssh",pid=123,fd=7))\n', '')
    monkeypatch.setattr(m.subprocess, "run", run)
    m._listener(49152, 123)
    assert calls == [["/usr/bin/ss", "-H", "-ltnp", "sport = :49152"]]
    with pytest.raises(ValueError):
        m._listener(49152, 124)


@pytest.mark.parametrize("behavior", ["redirect", "oversize", "duplicate", "lost"])
def test_http_fixed_loopback_single_request_budget_and_no_redirect_retry(monkeypatch, behavior):
    calls = []
    class Response:
        status = 302 if behavior == "redirect" else 200
        def getheaders(self):
            return [("ETag", '"a"'), ("eTAG", '"b"')] if behavior == "duplicate" else [
                ("Location", "https://unrelated.example.invalid")]
        def read(self, size):
            calls.append(("read", size))
            return b"12345" if behavior == "oversize" else b"ok"
    class Connection:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))
        def request(self, *args, **kwargs):
            calls.append(("request", args, kwargs))
            if behavior == "lost":
                raise OSError("connection lost")
        def getresponse(self):
            return Response()
        def close(self):
            calls.append(("close",))
    monkeypatch.setattr(m.http.client, "HTTPConnection", Connection)
    monkeypatch.setenv("HTTP_PROXY", "http://unrelated.example.invalid")
    if behavior == "redirect":
        assert m._http(2019, "GET", "/config/", maximum=4)[0] == 302
    else:
        with pytest.raises((ValueError, OSError)):
            m._http(2019, "GET", "/config/", maximum=4)
    assert calls[0] == ("connect", "127.0.0.1", 2019, 20)
    assert sum(c[0] == "request" for c in calls) == 1
    assert calls[-1] == ("close",)
    if behavior in ("redirect", "oversize"):
        assert ("read", 5) in calls


@pytest.mark.parametrize("drift", [False, True])
def test_fixed_caddy_validation_checks_input_after_process(inputs, monkeypatch, drift):
    m.stage_host(**inputs)
    path = inputs["out"] / "prepare.json"
    candidate = json.loads(path.read_bytes())
    calls = []
    def run(argv, **kw):
        calls.append((argv, kw))
        if drift:
            path.write_bytes(b"{}")
        return subprocess.CompletedProcess(argv, 0, b"", b"")
    monkeypatch.setattr(m.subprocess, "run", run)
    with m.private(inputs["out"]) as stage:
        if drift:
            with pytest.raises(ValueError, match="input changed"):
                m._validate(stage, "prepare", candidate)
        else:
            m._validate(stage, "prepare", candidate)
    assert calls == [(["/usr/bin/caddy", "validate", "--config", str(path)],
                      {"capture_output": True, "timeout": 30, "check": True})]


@pytest.mark.parametrize("command", ["stage-host", "prepare", "verify-cutover", "finalize"])
def test_cli_explicit_argument_wiring(command, monkeypatch, capsys):
    calls = []
    function = "stage_host" if command == "stage-host" else "verify_cutover" if command == "verify-cutover" else "publish"
    monkeypatch.setattr(m, function, lambda **kwargs: calls.append(kwargs) or {"fixture": True})
    args = [command]
    if command == "stage-host":
        for name in ("old-root", "new-bundle", "source-repo", "live-config", "out"):
            args += ["--" + name, "/fixture/" + name]
        for name in ("old-sha", "old-tree", "new-sha", "new-tree", "new-digest"):
            args += ["--" + name, "exact-" + name]
        args += ["--relay-port", "49152"]
    else:
        args += ["--stage-path", "/fixture/stage", "--stage-digest", "digest"]
        args += ["--new-sha", "source", "--new-digest", "bundle"] if command == "verify-cutover" else ["--listener-pid", "123"]
    m.main(args)
    assert len(calls) == 1 and json.loads(capsys.readouterr().out) == {"fixture": True}
    if command in ("prepare", "finalize"):
        assert calls[0]["phase"] == command and calls[0]["listener_pid"] == 123
    elif command == "stage-host":
        assert calls[0]["source_repo"] == Path("/fixture/source-repo") and calls[0]["relay_port"] == 49152
    else:
        assert calls[0]["new_sha"] == "source" and calls[0]["new_digest"] == "bundle"


@pytest.mark.parametrize("raw", [b'{"v":1,"v":2}', b'{"v":NaN}', b'{"v":Infinity}'])
def test_closed_json_refusals(raw):
    with pytest.raises(ValueError):
        m.decode(raw)

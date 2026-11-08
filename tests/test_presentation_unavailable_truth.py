"""User-facing read failures stay distinct from legitimate not-built-yet states."""
from __future__ import annotations

import asyncio
import builtins
import copy
import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest


def _body(resp):
    return json.loads(resp.body)


def _boom(*_args, **_kwargs):
    raise RuntimeError("secret /Users/private/presentation token=bad")


def test_posture_failure_is_unavailable_and_secret_safe(monkeypatch):
    from app import web
    from brain import posture

    monkeypatch.setattr(posture, "posture", _boom)
    response = web.api_posture("flagship")
    payload = _body(response)

    assert payload["available"] is False
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "posture_unavailable"
    assert payload["posture_label"] == "—"
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def test_market_view_missing_artifact_remains_not_built(tmp_path, monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    response = web.api_market_view()
    payload = _body(response)
    assert response.status_code == 404
    assert payload["available"] is False
    assert "not built yet" in payload["note"]
    assert "read_status" not in payload


def test_market_view_read_failure_is_closed_unavailable(tmp_path, monkeypatch):
    from app import web

    root = tmp_path / "market_view"
    root.mkdir(parents=True)
    (root / "latest.json").write_text("{not-json")
    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    response = web.api_market_view()
    payload = _body(response)

    assert response.status_code == 500
    assert payload == {
        "available": False,
        "read_status": "unavailable",
        "error": "market_view_unavailable",
        "note": "market view unavailable",
    }
    assert "not-json" not in response.body.decode()


def test_agenda_missing_artifact_remains_not_built(monkeypatch):
    from app import web
    from brain import improvement_agenda

    monkeypatch.setattr(improvement_agenda, "latest", lambda **_kwargs: None)
    response = web.api_agenda()
    payload = _body(response)
    assert response.status_code == 404
    assert payload["available"] is False
    assert "no agenda built yet" in payload["note"]
    assert "read_status" not in payload


def test_agenda_read_failure_is_closed_unavailable(monkeypatch):
    from app import web
    from brain import improvement_agenda

    monkeypatch.setattr(improvement_agenda, "latest", _boom)
    response = web.api_agenda()
    payload = _body(response)

    assert response.status_code == 500
    assert payload == {
        "available": False,
        "read_status": "unavailable",
        "error": "agenda_unavailable",
        "note": "agenda unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def test_clients_render_failure_as_unavailable_not_not_built_or_raw_error():
    index = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert "function _postureUnavailable()" in index
    chip = index[index.index("function _postureChipHTML") : index.index("function loadDeskPosture")]
    assert "p.read_status === 'unavailable'" in chip
    assert chip.index("p.read_status === 'unavailable'") < chip.index("!p.available")
    load = index[index.index("function loadDeskPosture") : index.index("function renderDecisions")]
    assert "_postureUnavailable()" in load
    assert "host.innerHTML = '';" not in load

    market = (Path(__file__).parents[1] / "app" / "static" / "market_view.html").read_text()
    fetch = market[market.index('fetch("/api/market_view"') : market.index('</script>', market.index('fetch("/api/market_view"'))]
    assert "res.body.error" not in fetch
    assert "e && e.message" not in fetch
    assert '"market view unavailable"' in fetch

    agenda = (Path(__file__).parents[1] / "app" / "static" / "agenda.html").read_text()
    fetch = agenda[agenda.index('fetch("/api/agenda"') : agenda.index('</script>', agenda.index('fetch("/api/agenda"'))]
    assert "res.body.error" not in fetch
    assert "e && e.message" not in fetch
    assert '"agenda unavailable"' in fetch


_SECRET = "secret /Users/private/presentation token=bad"


@pytest.fixture(autouse=True)
def _private_display_paths(monkeypatch, tmp_path):
    from app import web
    from brain import improvement_agenda

    root = tmp_path / "display"
    root.mkdir()
    monkeypatch.setattr(web, "_data", lambda: root)
    monkeypatch.setattr(improvement_agenda, "_OUT", root / "agenda")
    return root


def _closed(response, name, status=500):
    assert response.status_code == status
    assert _body(response) == {
        "available": False,
        "read_status": "unavailable",
        "error": name.replace(" ", "_") + "_unavailable",
        "note": name + " unavailable",
    }
    assert response.headers["cache-control"] == "no-cache"
    assert all(marker not in response.body.decode() for marker in ("secret", "/Users/private", "token=bad"))


def _deny_endpoint_import(monkeypatch, member):
    from app import web

    original = builtins.__import__

    def checked(name, globals=None, locals=None, fromlist=(), level=0):
        if globals is web.__dict__ and name == "brain" and member in fromlist:
            raise ImportError(_SECRET)
        return original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", checked)


def _request(path, params=None):
    from app import web
    from fastapi import FastAPI
    import httpx

    application = FastAPI()
    application.include_router(web.router)

    async def request():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://private.test") as client:
            return await client.get(path, params=params)

    return asyncio.run(request())


@pytest.mark.parametrize("mode", [
    "dangling_file", "dangling_parent", "parent_file", "directory_file",
    "read_denied", "lstat_denied", "nonobject",
])
def test_market_file_failures_do_not_masquerade_as_not_built(monkeypatch, _private_display_paths, mode):
    from app import web

    root = _private_display_paths
    directory = root / "market_view"
    path = directory / "latest.json"
    if mode == "dangling_parent":
        directory.symlink_to(root / "absent", target_is_directory=True)
    elif mode == "parent_file":
        directory.write_text("not a directory")
    else:
        directory.mkdir()
        if mode == "dangling_file":
            path.symlink_to(root / "absent")
        elif mode == "directory_file":
            path.mkdir()
        elif mode == "nonobject":
            path.write_text("[]")
        elif mode == "read_denied":
            path.write_text("{}")
            original = Path.read_text

            def denied(self, *args, **kwargs):
                if self == path:
                    raise PermissionError(_SECRET)
                return original(self, *args, **kwargs)

            monkeypatch.setattr(Path, "read_text", denied)
        elif mode == "lstat_denied":
            original = Path.lstat

            def denied(self, *args, **kwargs):
                if self == path:
                    raise PermissionError(_SECRET)
                return original(self, *args, **kwargs)

            monkeypatch.setattr(Path, "lstat", denied)
    _closed(web.api_market_view(), "market view")


@pytest.mark.parametrize("mode,status", [
    ("missing_dir", 404), ("empty_dir", 404), ("malformed", 500),
    ("nonobject", 500), ("empty_object", 500), ("dangling_selected", 500),
    ("dangling_directory", 500), ("parent_file", 500), ("directory_selected", 500),
    ("newest_corrupt", 500),
])
def test_actual_agenda_store_distinguishes_absence_from_failure(_private_display_paths, mode, status):
    from app import web

    root = _private_display_paths
    directory = root / "agenda"
    selected = directory / "2026-11-07.json"
    if mode == "dangling_directory":
        directory.symlink_to(root / "absent", target_is_directory=True)
    elif mode == "parent_file":
        directory.write_text("not a directory")
    elif mode != "missing_dir":
        directory.mkdir()
        if mode in {"malformed", "newest_corrupt"}:
            selected.write_text("{secret token=bad")
            if mode == "newest_corrupt":
                (directory / "2026-11-06.json").write_text(json.dumps({"items": [{"id": "stale"}]}))
        elif mode == "nonobject":
            selected.write_text("[]")
        elif mode == "empty_object":
            selected.write_text("{}")
        elif mode == "dangling_selected":
            selected.symlink_to(root / "absent")
        elif mode == "directory_selected":
            selected.mkdir()
    response = web.api_agenda()
    assert response.status_code == status
    if status == 404:
        assert _body(response) == {
            "available": False,
            "note": "no agenda built yet (brain.improvement_agenda.write runs in the weekly CIO job)",
        }
    else:
        _closed(response, "agenda")
        assert "stale" not in response.body.decode()


@pytest.mark.parametrize("mode", ["read_denied", "listing_denied", "absence_probe_denied"])
def test_agenda_read_boundaries_report_unavailable(monkeypatch, _private_display_paths, mode):
    from app import web

    directory = _private_display_paths / "agenda"
    selected = directory / "2026-11-07.json"
    if mode != "absence_probe_denied":
        directory.mkdir()
        selected.write_text(json.dumps({"items": [], "n_items": 0}))
    if mode == "read_denied":
        original = Path.read_text

        def denied(self, *args, **kwargs):
            if self == selected:
                raise PermissionError(_SECRET)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)
    elif mode == "listing_denied":
        original = Path.iterdir

        def denied(self):
            if self == directory:
                raise PermissionError(_SECRET)
            return original(self)

        monkeypatch.setattr(Path, "iterdir", denied)
    else:
        original = Path.lstat

        def denied(self, *args, **kwargs):
            if self == directory:
                raise PermissionError(_SECRET)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "lstat", denied)
    _closed(web.api_agenda(), "agenda")


def test_agenda_newest_nonempty_artifact_is_preserved_without_writes(_private_display_paths):
    from app import web

    directory = _private_display_paths / "agenda"
    directory.mkdir()
    old = {"schema_version": "improvement_agenda.v1", "items": [{"id": "old"}]}
    latest = {
        "schema_version": "improvement_agenda.v1", "as_of": "2026-11-07", "n_items": 1,
        "items": [{"id": "review", "readiness": {"status": "blocked"}, "rank": 1}],
        "readiness_input": {"available": False, "degraded": ["fixture"]},
        "owners": {"opus-session": 1}, "note": "Advisory fixture",
    }
    (directory / "2026-11-06.json").write_text(json.dumps(old))
    (directory / "2026-11-07.json").write_text(json.dumps(latest))
    (directory / "unrelated.json").write_text("{ignored")
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    response = web.api_agenda()
    assert response.status_code == 200
    assert _body(response) == latest
    assert response.headers["cache-control"] == "no-cache"
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_agenda_default_reader_retains_tolerant_compatibility(_private_display_paths):
    from brain import improvement_agenda

    directory = _private_display_paths / "agenda"
    directory.mkdir()
    (directory / "2026-11-07.json").write_text("{bad")
    assert improvement_agenda.latest() == {}


def test_market_success_preserves_projection_contract_and_publication(monkeypatch, _private_display_paths):
    from app import web
    from brain import market_view

    published = {
        "schema_version": market_view._SCHEMA_VERSION, "region": "us", "asof": "2026-11-06",
        "built_at": "2026-11-06T12:00:00+00:00", "seq": 7, "planes": {},
        "posture_floor_defense": True, "coherence": None,
        "disagreements": [{"historical": True}], "budget_ref": {"as_published": "fixture"},
    }
    directory = _private_display_paths / "market_view"
    directory.mkdir()
    path = directory / "latest.json"
    path.write_text(json.dumps(published))
    before = path.read_bytes()
    expected = copy.deepcopy(published)
    expected["serving_freshness"] = {
        "checked_at": "2026-11-07T12:00:00+00:00",
        "current_confirmation_available": False,
    }
    calls = []

    def serve(view):
        calls.append(copy.deepcopy(view))
        return copy.deepcopy(expected)

    monkeypatch.setattr(market_view, "serving_view", serve)
    response = web.api_market_view()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert _body(response) == expected
    assert calls == [published]
    assert path.read_bytes() == before
    assert _body(response)["built_at"] == published["built_at"]
    assert _body(response)["posture_floor_defense"] is True


def test_market_projection_failure_is_closed(monkeypatch, _private_display_paths):
    from app import web
    from brain import market_view

    directory = _private_display_paths / "market_view"
    directory.mkdir()
    (directory / "latest.json").write_text("{}")
    monkeypatch.setattr(market_view, "serving_view", _boom)
    _closed(web.api_market_view(), "market view")


@pytest.mark.parametrize("available", [False, True])
def test_posture_successful_payload_and_book_are_preserved(monkeypatch, available):
    from app import web
    from brain import posture

    payload = {"book": "flagship", "available": available, "posture_label": "Defensive",
               "favored": ["quality"], "detail": "fixture", "cash_pct": 50}
    calls = []

    def read(book):
        calls.append(book)
        return payload

    monkeypatch.setattr(posture, "posture", read)
    response = web.api_posture("flagship")
    assert response.status_code == 200
    assert _body(response) == payload
    assert calls == ["flagship"]


@pytest.mark.parametrize("member", ["posture", "improvement_agenda"])
def test_endpoint_import_failure_uses_fixed_unavailable(monkeypatch, member):
    from app import web

    _deny_endpoint_import(monkeypatch, member)
    response = web.api_posture("flagship") if member == "posture" else web.api_agenda()
    if member == "posture":
        assert response.status_code == 200
        assert _body(response)["read_status"] == "unavailable"
        assert _body(response)["error"] == "posture_unavailable"
        assert all(marker not in response.body.decode() for marker in ("secret", "/Users/private", "token=bad"))
    else:
        _closed(response, "agenda")


@pytest.mark.parametrize("endpoint,status", [("posture", 200), ("market_view", 500), ("agenda", 500)])
def test_actual_display_http_failures_are_unavailable(monkeypatch, _private_display_paths, endpoint, status):
    from brain import posture

    if endpoint == "posture":
        monkeypatch.setattr(posture, "posture", _boom)
    else:
        directory = _private_display_paths / endpoint
        directory.mkdir()
        name = "latest.json" if endpoint == "market_view" else "2026-11-07.json"
        (directory / name).write_text("{secret token=bad")
    response = _request("/api/" + endpoint)
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["read_status"] == "unavailable"
    assert response.json()["error"] == endpoint + "_unavailable"
    assert all(marker not in response.text for marker in ("secret", "/Users/private", "token=bad"))


def test_posture_registered_route_retains_default_and_unknown_book_rejection(monkeypatch):
    from app import web
    from brain import posture

    calls = []

    def read(book):
        calls.append(book)
        return {"book": book, "available": False}

    monkeypatch.setattr(posture, "posture", read)
    default = _request("/api/posture")
    blank = _request("/api/posture", {"book": ""})
    unknown = _request("/api/posture", {"book": "fixture_unknown_book"})
    assert default.status_code == blank.status_code == 200
    assert default.json()["book"] == blank.json()["book"] == web._PRODUCT_DEFAULT_ID
    assert calls == [web._PRODUCT_DEFAULT_ID, web._PRODUCT_DEFAULT_ID]
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["error"] == "unknown_portfolio"
    assert "read_status" not in unknown.json()

_NODE_RUNNER = "const vm = require('node:vm');\nconst assert = require('node:assert/strict');\nconst input = JSON.parse(process.argv[1]);\nconst elements = {\n  'desk-posture': {innerHTML: ''}, 'mv-root': {innerHTML: ''}, 'mv-sub': {textContent: ''},\n  'root': {innerHTML: ''}, 'sub': {textContent: ''}\n};\nconst records = {fetches: []};\nconst ctx = {\n  assert, elements, records, language: 'en',\n  E: id => elements[id] || null,\n  document: {\n    getElementById: id => elements[id] || null,\n    documentElement: {getAttribute: () => ctx.language}\n  },\n  esc: value => String(value == null ? '' : value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'),\n  http: (status, body) => ({ok: status >= 200 && status < 300, status, json: async () => body}),\n  drain: () => new Promise(resolve => setImmediate(resolve)),\n};\nvm.createContext(ctx);\nvm.runInContext(input.source.posture, ctx, {timeout: 1500});\nctx.runPage = name => {\n  assert.ok(name === 'market' || name === 'agenda');\n  return vm.runInContext(input.source[name], ctx, {timeout: 1500});\n};\nconst pending = vm.runInContext('(async function () {\\n' + input.body + '\\n})()',\n  ctx, {timeout: 1500});\nPromise.resolve(pending).then(() => process.stdout.write('ok\\n')).catch(error => {\n  process.stderr.write(String(error.stack || error) + '\\n'); process.exitCode = 1;\n});\n"

_CLIENT_CASES = {
    "posture_typed_unavailable": "var failed={available:false,read_status:'unavailable',posture_label:'secret',note:'secret /Users/private token=bad'};\nvar html=_postureChipHTML(failed); assert.ok(html.includes('Posture unavailable')); assert.ok(!html.includes('No posture yet')); assert.ok(!html.includes('secret'));\nlanguage='zh'; html=_postureChipHTML(failed); assert.ok(html.includes('姿态暂不可用')); assert.ok(!html.includes('secret'));",
    "posture_legitimate_absence": "var html=_postureChipHTML({available:false});\nassert.ok(html.includes('No posture yet')); assert.ok(!html.includes('Posture unavailable'));\nfetch=async()=>http(200,{available:false}); loadDeskPosture(); await drain();\nassert.ok(E('desk-posture').innerHTML.includes('No posture yet'));",
    "posture_http_failure": "fetch=async url=>{records.fetches.push(url);return http(503,{note:'secret'});};\nloadDeskPosture();await drain();assert.equal(records.fetches[0],'/api/posture?book=flagship');\nassert.ok(E('desk-posture').innerHTML.includes('Posture unavailable'));\nassert.ok(!E('desk-posture').innerHTML.includes('No posture yet'));",
    "posture_transport_failures": "for(var mode of ['fetch','json']){\n  fetch=async()=>{if(mode==='fetch')throw new Error('secret /Users/private token=bad');\n    return {ok:true,json:async()=>{throw new Error('secret parse');}};};\n  loadDeskPosture();await drain();var html=E('desk-posture').innerHTML;\n  assert.ok(html.includes('Posture unavailable'));assert.ok(!html.includes('secret'));\n}",
    "posture_malformed_payload": "for(var payload of [null,{},[],1,'secret',{available:'false'}]){\n  fetch=async()=>http(200,payload);loadDeskPosture();await drain();var html=E('desk-posture').innerHTML;\n  assert.ok(html.includes('Posture unavailable'));assert.ok(!html.includes('No posture yet'));assert.ok(!html.includes('secret'));\n}",
    "posture_valid_rendering": "var payload={available:true,posture_label:'Quality < growth',posture_label_zh:'稳健策略',posture_tone:'muted',\nsub_strategy:'Fixture playbook',favored:['Cash'],avoided:['Leverage'],driver:'Cash buffer',detail:'Observed fixture',as_of:'2026-11-07'};\nfetch=async()=>http(200,payload);loadDeskPosture();await drain();\nvar html=E('desk-posture').innerHTML;assert.ok(html.includes('Quality &lt; growth'));assert.ok(html.includes('Fixture playbook'));\nassert.ok(html.includes('Cash buffer'));assert.ok(!html.includes('Posture unavailable'));\nlanguage='zh';loadDeskPosture();await drain();assert.ok(E('desk-posture').innerHTML.includes('稳健策略'));",
    "posture_missing_host": "delete elements['desk-posture'];fetch=async()=>{records.fetches.push('unexpected');return http(200,{});};\nloadDeskPosture();await drain();assert.equal(records.fetches.length,0);",
    "pages_typed_unavailable": "for(var item of [['market','mv-root','mv-sub','market view'],['agenda','root','sub','agenda']]){\n  fetch=async()=>http(200,{available:false,read_status:'unavailable',note:'secret /Users/private token=bad'});\n  runPage(item[0]);await drain();assert.equal(E(item[1]).innerHTML,'<div class=\"msg\">'+item[3]+' unavailable</div>');\n  assert.equal(E(item[2]).textContent,'unavailable');\n}",
    "pages_hostile_error_notes": "for(var item of [['market','mv-root','market view'],['agenda','root','agenda']]){\n  for(var payload of [{note:'secret /Users/private token=bad',error:'secret'},{error:'secret raw exception'},{note:{secret:true}},{note:42}]){\n    fetch=async()=>http(500,payload);runPage(item[0]);await drain();\n    assert.equal(E(item[1]).innerHTML,'<div class=\"msg\">'+item[2]+' unavailable</div>');\n  }\n}",
    "pages_known_missing_only": "for(var item of [\n['market','mv-root','market view','market_view artifact not built yet (brain.market_view.build has not run)','market view not built yet'],\n['agenda','root','agenda','no agenda built yet (brain.improvement_agenda.write runs in the weekly CIO job)','no agenda built yet']]){\n  fetch=async()=>http(404,{available:false,note:item[3]});runPage(item[0]);await drain();\n  assert.equal(E(item[1]).innerHTML,'<div class=\"msg\">'+item[4]+'</div>');\n  for(var bad of [http(404,{available:false,note:'secret missing'}),http(500,{available:false,note:item[3]}),\n    http(404,{available:false,read_status:'unavailable',note:item[3]})]){\n    fetch=async()=>bad;runPage(item[0]);await drain();\n    assert.equal(E(item[1]).innerHTML,'<div class=\"msg\">'+item[2]+' unavailable</div>');\n  }\n}",
    "pages_fetch_rejection": "for(var item of [['market','mv-root','mv-sub','market view'],['agenda','root','sub','agenda']]){\n  fetch=async()=>{throw new Error('secret /Users/private token=bad');};runPage(item[0]);await drain();\n  assert.equal(E(item[1]).innerHTML,'<div class=\"msg\">'+item[3]+' unavailable</div>');assert.equal(E(item[2]).textContent,'unavailable');\n}",
    "pages_json_rejection": "for(var item of [['market','mv-root','market view'],['agenda','root','agenda']]){\n  fetch=async()=>({ok:false,status:502,json:async()=>{throw new Error('secret raw HTML token=bad');}});\n  runPage(item[0]);await drain();assert.equal(E(item[1]).innerHTML,'<div class=\"msg\">'+item[2]+' unavailable</div>');\n}",
    "pages_malformed_payload": "for(var item of [['market','mv-root','market view'],['agenda','root','agenda']]){\n  for(var payload of [null,[],'secret',7]){\n    fetch=async()=>http(200,payload);runPage(item[0]);await drain();\n    assert.equal(E(item[1]).innerHTML,'<div class=\"msg\">'+item[2]+' unavailable</div>');\n  }\n}",
    "pages_successful_rendering": "var market={schema_version:'market_view.v1',region:'us',asof:'2026-11-07',seq:7,planes:{},\nlabel_vs_planes:{},net_posture_tilt:{tilt:0,n_validated:0,contributors:[]},assembly:{},\nbrief:{what_changed:'Valid market fixture'},serving_freshness:{checked_at:'2026-11-07T12:00:00Z'}};\nfetch=async url=>{records.fetches.push(url);return http(200,market);};runPage('market');await drain();\nassert.equal(records.fetches[0],'/api/market_view');assert.ok(E('mv-root').innerHTML.includes('Planes'));\nassert.ok(E('mv-root').innerHTML.includes('Valid market fixture'));assert.ok(E('mv-sub').textContent.includes('seq 7'));\nvar agenda={schema_version:'improvement_agenda.v1',as_of:'2026-11-07',n_items:1,items:[{rank:1,title:'Fixture title',\nsuggested_fix:'Review fixture',evidence:[],readiness:{status:'blocked'}}],owners:{},class_counts:{},\nreadiness_input:{available:false,degraded:[]},note:'Advisory fixture'};\nfetch=async url=>{records.fetches.push(url);return http(200,agenda);};runPage('agenda');await drain();\nassert.equal(records.fetches[1],'/api/agenda');assert.ok(E('root').innerHTML.includes('<b>1</b> open items'));\nassert.ok(E('root').innerHTML.includes('Advisory fixture'));assert.ok(E('sub').textContent.includes('2026-11-07'));"
}

@lru_cache(maxsize=1)
def _node_runtime():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable for the isolated dashboard behavior checks")
    result = subprocess.run(
        [node, "--version"], capture_output=True, text=True, timeout=8,
        env={"PATH": str(Path(node).parent), "LANG": "C"},
    )
    assert result.returncode == 0, result.stderr
    major = int(result.stdout.strip().lstrip("v").split(".")[0])
    if major < 20:
        pytest.skip("Node 20+ is required for permission-constrained dashboard checks")
    return node, "--permission" if major >= 23 else "--experimental-permission"


def _client_source():
    static = Path(__file__).parents[1] / "app/static"
    index = (static / "index.html").read_text()
    start = index.index("// ── STRATEGY POSTURE:")
    end = index.index("function renderDecisions", start)
    sources = {"posture": index[start:end]}
    for key, filename in (("market", "market_view.html"), ("agenda", "agenda.html")):
        html = (static / filename).read_text()
        begin = html.rindex("<script>") + len("<script>")
        sources[key] = html[begin:html.index("</script>", begin)]
    return sources


def _run_client(case):
    node, permission = _node_runtime()
    payload = json.dumps({"case": case, "source": _client_source(), "body": _CLIENT_CASES[case]})
    result = subprocess.run(
        [node, permission, "--eval", _NODE_RUNNER, "--", payload],
        cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=8,
        env={"PATH": str(Path(node).parent), "LANG": "C"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok\n", result.stdout


@pytest.mark.parametrize("case", ["posture_typed_unavailable","posture_legitimate_absence","posture_http_failure","posture_transport_failures","posture_malformed_payload","posture_valid_rendering","posture_missing_host","pages_typed_unavailable","pages_hostile_error_notes","pages_known_missing_only","pages_fetch_rejection","pages_json_rejection","pages_malformed_payload","pages_successful_rendering"])
def test_actual_presentation_clients(case):
    _run_client(case)

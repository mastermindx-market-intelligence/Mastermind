"""Research PDF failures are typed and never relay backend exception detail to the browser."""
from __future__ import annotations

import asyncio
import builtins
import json
import shutil
import subprocess
import sys
import types
from functools import lru_cache
from pathlib import Path

import pytest


def _body(resp):
    return json.loads(resp.body)


def _boom(*_args, **_kwargs):
    raise RuntimeError("secret /Users/private/research.pdf api_key=bad")


def test_missing_paper_remains_clean_not_found(monkeypatch):
    from app import web
    from brain import research_paper

    monkeypatch.setattr(research_paper, "load_papers", lambda: [])
    response = web.research_paper_pdf(id="missing")
    payload = _body(response)
    assert response.status_code == 404
    assert payload["error"] == "research paper not found"
    assert "read_status" not in payload


def test_paper_store_read_failure_is_closed(monkeypatch):
    from app import web
    from brain import research_paper

    monkeypatch.setattr(research_paper, "load_papers", _boom)
    response = web.research_paper_pdf(id="paper-1")
    payload = _body(response)
    assert response.status_code == 500
    assert payload == {
        "read_status": "unavailable",
        "error": "research_paper_unavailable",
        "note": "research paper unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


def test_successful_pdf_route_keeps_pdf_contract(monkeypatch):
    import sys
    import types
    import app
    from app import web
    from brain import research_paper

    paper = {"id": "paper-1", "ticker": "NVDA", "asof": "2026-09-17", "report_md": "## Thesis"}
    monkeypatch.setattr(research_paper, "load_papers", lambda: [paper])
    fake = types.ModuleType("app.research_pdf")
    fake.build = lambda _paper, _meta: b"%PDF-1.4\n%%EOF"
    monkeypatch.setitem(sys.modules, "app.research_pdf", fake)
    monkeypatch.setattr(app, "research_pdf", fake, raising=False)

    response = web.research_paper_pdf(id="paper-1")
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")
    assert "attachment" in response.headers["content-disposition"]


def test_pdf_engine_import_failure_is_closed(monkeypatch):
    from app import web
    from brain import research_paper

    paper = {"id": "paper-1", "ticker": "NVDA", "report_md": "## Thesis"}
    monkeypatch.setattr(research_paper, "load_papers", lambda: [paper])
    _deny_endpoint_import(monkeypatch, "app", "research_pdf")
    response = web.research_paper_pdf(id="paper-1")
    payload = _body(response)
    assert response.status_code == 503
    assert payload == {
        "read_status": "unavailable",
        "error": "research_pdf_engine_unavailable",
        "note": "PDF engine unavailable",
    }


def test_pdf_generation_failure_is_closed(monkeypatch):
    import sys
    import types
    import app
    from app import web
    from brain import research_paper

    paper = {"id": "paper-1", "ticker": "NVDA", "report_md": "## Thesis"}
    monkeypatch.setattr(research_paper, "load_papers", lambda: [paper])
    fake = types.ModuleType("app.research_pdf")
    fake.build = _boom
    monkeypatch.setitem(sys.modules, "app.research_pdf", fake)
    monkeypatch.setattr(app, "research_pdf", fake, raising=False)
    response = web.research_paper_pdf(id="paper-1")
    payload = _body(response)
    assert response.status_code == 500
    assert payload == {
        "read_status": "unavailable",
        "error": "research_pdf_generation_failed",
        "note": "PDF generation failed",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


def test_pdf_client_never_renders_server_error_or_raw_body():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    start = html.index("window.downloadPaperPdf = function()")
    end = html.index("// open a thesis from the Positions panel", start)
    block = html[start:end]

    assert "j.error" not in block
    assert "if (body) msg = body" not in block
    assert "j.note" in block
    assert "PDF generation failed" in block
    assert "e && e.message" not in block


_SECRET = "secret /Users/private/research.pdf api_key=bad"


@pytest.fixture(autouse=True)
def _private_pdf_paths(monkeypatch, tmp_path):
    from app import web
    from brain import research_paper

    papers = tmp_path / "papers"
    papers.mkdir()
    monkeypatch.setattr(research_paper, "_PAPERS", papers)
    monkeypatch.setattr(research_paper, "_INDEX", papers / "index.jsonl")
    monkeypatch.setattr(web, "_company_meta", lambda _ticker: {})
    return papers


def _deny_endpoint_import(monkeypatch, package, member):
    from app import web

    original = builtins.__import__

    def checked(name, globals=None, locals=None, fromlist=(), level=0):
        if globals is web.__dict__ and name == package and member in fromlist:
            raise ImportError(_SECRET)
        return original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", checked)


def _renderer(monkeypatch, build):
    import app

    module = types.ModuleType("app.research_pdf")
    module.build = build
    monkeypatch.setitem(sys.modules, "app.research_pdf", module)
    monkeypatch.setattr(app, "research_pdf", module, raising=False)


def _assert_closed(response, status, code, note):
    assert response.status_code == status
    assert _body(response) == {
        "read_status": "unavailable",
        "error": code,
        "note": note,
    }
    raw = response.body.decode()
    for marker in ("secret", "/Users/private", "api_key"):
        assert marker not in raw


def test_store_import_failure_is_closed(monkeypatch):
    from app import web

    _deny_endpoint_import(monkeypatch, "brain", "research_paper")
    response = web.research_paper_pdf(id="paper-1")
    _assert_closed(response, 503, "research_store_unavailable", "research store unavailable")


@pytest.mark.parametrize("mode,status,code,note", [
    ("store_import", 503, "research_store_unavailable", "research store unavailable"),
    ("paper_read", 500, "research_paper_unavailable", "research paper unavailable"),
    ("missing", 404, "research paper not found", "research paper not found"),
    ("engine_import", 503, "research_pdf_engine_unavailable", "PDF engine unavailable"),
    ("render", 500, "research_pdf_generation_failed", "PDF generation failed"),
])
def test_actual_pdf_http_failure_contract(monkeypatch, mode, status, code, note):
    from app import web
    from brain import research_paper
    from fastapi import FastAPI
    import httpx

    paper = {"id": "paper-1", "ticker": "NVDA", "report_md": "## Thesis"}
    if mode != "missing":
        monkeypatch.setattr(research_paper, "load_papers", lambda: [paper])
    if mode == "store_import":
        _deny_endpoint_import(monkeypatch, "brain", "research_paper")
    elif mode == "paper_read":
        monkeypatch.setattr(research_paper, "load_papers", _boom)
    elif mode == "engine_import":
        _deny_endpoint_import(monkeypatch, "app", "research_pdf")
    elif mode == "render":
        _renderer(monkeypatch, _boom)

    application = FastAPI()
    application.include_router(web.router)

    async def request():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://private.test") as client:
            return await client.get("/research_paper.pdf", params={"id": "paper-1"})

    response = asyncio.run(request())
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/json")
    expected = {"error": code, "note": note}
    if mode != "missing":
        expected["read_status"] = "unavailable"
    assert response.json() == expected
    assert all(marker not in response.text for marker in ("secret", "/Users/private", "api_key"))


@pytest.mark.parametrize("query,expected_id", [
    ({"id": "old", "ticker": "NVDA"}, "old"),
    ({"ticker": "nvda"}, "new"),
    ({"id": "unknown", "ticker": "nvda"}, "new"),
])
def test_private_saved_paper_selection_and_pdf_headers(monkeypatch, _private_pdf_paths, query, expected_id):
    from app import web

    rows = [
        {"id": "old", "ticker": "NVDA", "asof": "2026-09-16", "generated_at": "2026-09-16T12:00:00Z"},
        {"id": "new", "ticker": "NVDA", "asof": "2026-09-17", "generated_at": "2026-09-17T12:00:00Z"},
        {"id": "other", "ticker": "MSFT", "asof": "2026-09-18", "generated_at": "2026-09-18T12:00:00Z"},
    ]
    for row in rows:
        (_private_pdf_paths / (row["id"] + ".json")).write_text(json.dumps(row))
    before = {p.name: p.read_bytes() for p in _private_pdf_paths.iterdir()}
    meta = {"name": "Nvidia", "sector": "Technology"}
    seen = []
    monkeypatch.setattr(web, "_company_meta", lambda ticker: meta if ticker == "NVDA" else None)

    def build(paper, received_meta):
        seen.append((paper, received_meta))
        return b"%PDF-1.4\n%%EOF"

    _renderer(monkeypatch, build)
    response = web.research_paper_pdf(**query)
    expected = next(row for row in rows if row["id"] == expected_id)
    assert response.status_code == 200
    assert response.body == b"%PDF-1.4\n%%EOF"
    assert response.media_type == "application/pdf"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="Mastermind_NVDA_{expected["asof"]}.pdf"'
    )
    assert seen == [(expected, meta)]
    assert {p.name: p.read_bytes() for p in _private_pdf_paths.iterdir()} == before


def test_metadata_failure_keeps_successful_pdf(monkeypatch):
    from app import web
    from brain import research_paper

    paper = {"id": "paper-1", "ticker": "NVDA"}
    monkeypatch.setattr(research_paper, "load_papers", lambda: [paper])
    monkeypatch.setattr(web, "_company_meta", _boom)
    received = []

    def build(selected, meta):
        received.append((selected, meta))
        return b"%PDF-1.4\n%%EOF"

    _renderer(monkeypatch, build)
    response = web.research_paper_pdf(id="paper-1")
    assert response.status_code == 200
    assert received == [(paper, {})]


def test_pdf_filename_remains_allowlisted(monkeypatch):
    from app import web
    from brain import research_paper

    paper = {"id": "paper-1", "ticker": 'NV"DA\r\n', "asof": "2026-09-17\r\ninjected"}
    monkeypatch.setattr(research_paper, "load_papers", lambda: [paper])
    _renderer(monkeypatch, lambda *_: b"%PDF-1.4\n%%EOF")
    response = web.research_paper_pdf(id="paper-1")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="Mastermind_NV_DA___2026-09-17.pdf"'
    )
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("kind", [RuntimeError, ValueError, PermissionError, TypeError])
def test_renderer_exceptions_are_fixed_and_secret_safe(monkeypatch, kind):
    from app import web
    from brain import research_paper

    paper = {"id": "paper-1", "ticker": "NVDA"}
    monkeypatch.setattr(research_paper, "load_papers", lambda: [paper])

    def fail(*_args):
        raise kind(_SECRET)

    _renderer(monkeypatch, fail)
    response = web.research_paper_pdf(id="paper-1")
    _assert_closed(response, 500, "research_pdf_generation_failed", "PDF generation failed")

_NODE_RUNNER = "const vm = require('node:vm');\nconst assert = require('node:assert/strict');\nconst input = JSON.parse(process.argv[1]);\nconst elements = {\n  'mm-pdf-btn': {disabled: false, innerHTML: 'Download PDF'},\n  'mm-modal-title': {textContent: 'NVDA Research'}\n};\nconst records = {alerts: [], fetches: [], urls: [], revoked: [], anchors: [], appended: [], removed: [], timers: []};\nconst ctx = {\n  assert, window: {}, _openPaperId: 'paper /?&=1', records, elements,\n  E: id => elements[id] || null,\n  alert: value => records.alerts.push(value),\n  URL: {\n    createObjectURL: blob => { records.urls.push(blob); return 'blob:private-pdf'; },\n    revokeObjectURL: url => records.revoked.push(url)\n  },\n  document: {\n    createElement: tag => {\n      assert.equal(tag, 'a');\n      const anchor = {href: '', download: '', clicks: 0, click() { this.clicks += 1; }};\n      records.anchors.push(anchor); return anchor;\n    },\n    body: {\n      appendChild: node => records.appended.push(node),\n      removeChild: node => records.removed.push(node)\n    }\n  },\n  setTimeout: (fn, delay) => { records.timers.push({fn, delay}); return records.timers.length; },\n  http: (status, payload) => ({\n    ok: status >= 200 && status < 300, status,\n    json: async () => payload,\n    text: async () => typeof payload === 'string' ? payload : JSON.stringify(payload)\n  }),\n  drain: () => new Promise(resolve => setImmediate(resolve)),\n};\nvm.createContext(ctx);\nconst pending = vm.runInContext(input.source + '\\n;(async function () {\\n' + input.body + '\\n})()',\n  ctx, {timeout: 1500});\nPromise.resolve(pending).then(() => process.stdout.write('ok\\n')).catch(error => {\n  process.stderr.write(String(error.stack || error) + '\\n'); process.exitCode = 1;\n});\n"

_CLIENT_CASES = {
    "typed_failures": "for (var item of [[503,'research store unavailable'],[500,'research paper unavailable'],[503,'PDF engine unavailable'],[500,'PDF generation failed'],[404,'research paper not found']]) {\n  fetch = async () => http(item[0], {read_status:'unavailable', note:item[1], error:'secret api_key=bad'});\n  window.downloadPaperPdf(); assert.equal(E('mm-pdf-btn').disabled,true); await drain();\n  assert.equal(records.alerts.at(-1),item[1]); assert.equal(E('mm-pdf-btn').disabled,false);\n  assert.equal(E('mm-pdf-btn').innerHTML,'Download PDF');\n}\nassert.equal(records.anchors.length,0);",
    "hostile_notes": "for (var payload of [{note:'secret /Users/private api_key=bad',error:'secret'},{note:{text:'secret'}},{note:42},null,{},[],{error:'secret raw exception'}]) {\n  fetch = async () => http(500,payload); window.downloadPaperPdf(); await drain();\n  assert.equal(records.alerts.at(-1),'PDF generation failed');\n  assert.equal(E('mm-pdf-btn').disabled,false);\n}\nfetch = async () => http(403,{note:'PDF engine unavailable'});\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.alerts.at(-1),'PDF generation failed');",
    "non_json_failure": "for (var status of [502,404]) {\n  fetch = async () => ({ok:false,status,json:async()=>{throw new Error('secret JSON');},text:async()=>'secret /Users/private api_key=bad'});\n  window.downloadPaperPdf(); await drain();\n  assert.equal(records.alerts.at(-1),status===404?'research paper not found':'PDF generation failed');\n  assert.equal(E('mm-pdf-btn').disabled,false); assert.equal(E('mm-pdf-btn').innerHTML,'Download PDF');\n}",
    "rejected_fetch": "fetch = async () => {throw new Error('secret /Users/private api_key=bad');};\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.alerts[0],'PDF generation failed');\nassert.equal(E('mm-pdf-btn').disabled,false); assert.equal(E('mm-pdf-btn').innerHTML,'Download PDF');",
    "forged_safe_message": "for (var message of ['secret /Users/private api_key=bad','research store unavailable']) {\n  fetch = async () => {throw {safeMessage:message};};\n  window.downloadPaperPdf(); await drain(); assert.equal(records.alerts.at(-1),'PDF generation failed');\n}\nassert.equal(E('mm-pdf-btn').disabled,false);",
    "rejected_blob": "fetch = async () => ({ok:true,blob:async()=>{throw new Error('secret blob');}});\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.alerts[0],'PDF generation failed');\nassert.equal(records.urls.length,0); assert.equal(E('mm-pdf-btn').disabled,false);",
    "successful_download": "var pdf = {type:'application/pdf',bytes:'%PDF'};\nfetch = async url => {records.fetches.push(url);return {ok:true,blob:async()=>pdf};};\nwindow.downloadPaperPdf(); assert.equal(E('mm-pdf-btn').disabled,true); await drain();\nassert.equal(records.fetches[0],'/research_paper.pdf?id=paper%20%2F%3F%26%3D1');\nassert.strictEqual(records.urls[0],pdf); assert.equal(records.anchors.length,1);\nvar anchor=records.anchors[0]; assert.equal(anchor.href,'blob:private-pdf'); assert.equal(anchor.download,'Mastermind_NVDA.pdf');\nassert.equal(anchor.clicks,1); assert.strictEqual(records.appended[0],anchor); assert.strictEqual(records.removed[0],anchor);\nassert.equal(records.timers[0].delay,5000); records.timers[0].fn(); assert.equal(records.revoked[0],'blob:private-pdf');\nassert.equal(records.alerts.length,0); assert.equal(E('mm-pdf-btn').disabled,false); assert.equal(E('mm-pdf-btn').innerHTML,'Download PDF');",
    "no_paper_guard": "_openPaperId=''; fetch=async()=>{records.fetches.push('unexpected');};\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.fetches.length,0); assert.equal(records.alerts.length,0);\nassert.equal(E('mm-pdf-btn').disabled,false); assert.equal(E('mm-pdf-btn').innerHTML,'Download PDF');",
    "disabled_button_guard": "E('mm-pdf-btn').disabled=true; fetch=async()=>{records.fetches.push('unexpected');};\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.fetches.length,0); assert.equal(E('mm-pdf-btn').disabled,true);",
    "missing_button": "delete elements['mm-pdf-btn'];\nfetch=async()=>({ok:true,blob:async()=>({type:'application/pdf'})});\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.anchors[0].clicks,1); assert.equal(records.alerts.length,0);\nrecords.timers[0].fn(); assert.equal(records.revoked[0],'blob:private-pdf');",
    "filename_sanitization": "E('mm-modal-title').textContent='NV<DA\"/? Research';\nfetch=async()=>({ok:true,blob:async()=>({type:'application/pdf'})});\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.anchors[0].download,'Mastermind_NVDA.pdf');",
    "recovery": "fetch=async()=>http(503,{note:'PDF engine unavailable'});\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.alerts[0],'PDF engine unavailable');\nfetch=async()=>({ok:true,blob:async()=>{throw new Error('secret');}});\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.alerts[1],'PDF generation failed');\nfetch=async()=>({ok:true,blob:async()=>({type:'application/pdf'})});\nwindow.downloadPaperPdf(); await drain(); assert.equal(records.alerts.length,2); assert.equal(records.anchors[0].clicks,1);\nassert.equal(E('mm-pdf-btn').innerHTML,'Download PDF');"
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
    html = (Path(__file__).parents[1] / "app/static/index.html").read_text()
    begin = html.index("window.downloadPaperPdf = function()")
    end = html.index("// open a thesis from the Positions panel", begin)
    return html[begin:end]


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


@pytest.mark.parametrize("case", ["typed_failures","hostile_notes","non_json_failure","rejected_fetch","forged_safe_message","rejected_blob","successful_download","no_paper_guard","disabled_button_guard","missing_button","filename_sanitization","recovery"])
def test_actual_pdf_download_client(case):
    _run_client(case)

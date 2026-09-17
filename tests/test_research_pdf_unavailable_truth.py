"""Research PDF failures are typed and never relay backend exception detail to the browser."""
from __future__ import annotations

import json
from pathlib import Path


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

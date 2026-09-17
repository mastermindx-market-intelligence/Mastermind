"""Research-feed and saved-paper read failures must remain unavailable, not empty."""
from __future__ import annotations

import json
from pathlib import Path


def test_research_feed_failure_is_closed_not_empty(tmp_path, monkeypatch):
    from app import web

    notes = tmp_path / "research" / "notes"
    notes.mkdir(parents=True)
    (notes / "one.md").write_text("# one\n", encoding="utf-8")
    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    monkeypatch.setattr(
        web, "_parse_note",
        lambda _p: (_ for _ in ()).throw(RuntimeError("secret /Users/private/research/one.md")),
    )

    resp = web.api_research()
    payload = json.loads(resp.body)
    assert resp.status_code >= 500
    assert payload["research_status"] == "unavailable"
    assert payload["error"] == "research_feed_unavailable"
    assert payload["notes"] is None
    raw = json.dumps(payload)
    assert "secret" not in raw.lower()
    assert "/Users/private" not in raw


def test_genuine_empty_research_feed_stays_successfully_empty(tmp_path, monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    resp = web.api_research()
    assert resp.status_code == 200
    assert json.loads(resp.body) == []


def test_research_papers_failure_is_closed_not_empty(monkeypatch):
    from app import web
    from brain import research_paper

    monkeypatch.setattr(
        research_paper, "load_papers",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/papers/index.jsonl")),
    )
    payload = json.loads(web.api_research_papers().body)
    assert payload["paper_status"] == "unavailable"
    assert payload["error"] == "research_papers_unavailable"
    assert payload["papers"] is None
    raw = json.dumps(payload)
    assert "secret" not in raw.lower()
    assert "/Users/private" not in raw


def test_genuine_empty_research_papers_stay_successfully_empty(monkeypatch):
    from app import web
    from brain import research_paper

    monkeypatch.setattr(research_paper, "load_papers", lambda: [])
    payload = json.loads(web.api_research_papers().body)
    assert payload == {"papers": []}


def test_research_feed_ui_distinguishes_loading_unavailable_and_empty():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert "var _researchStatus = 'loading'" in html
    assert "function _researchUnavailable()" in html
    assert "function _researchFetch()" in html
    assert "window.retryResearchFeed" in html

    a = html.index("function renderResearch()")
    b = html.index("window.toggleResearch", a)
    block = html[a:b]
    assert "_researchStatus === 'loading'" in block
    assert "_researchStatus === 'unavailable'" in block
    assert block.index("_researchStatus === 'unavailable'") < block.index("!_research.length")
    assert "Research feed unavailable" in block

    a = html.index("function _hydrateShared()")
    b = html.index("async function fetchAll", a)
    hydrate = html[a:b]
    assert "_researchFetch()" in hydrate
    assert "_applyResearchFeed" in hydrate


def test_research_papers_ui_is_secret_safe_and_failed_loads_retry():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert "var _papersStatus = 'loading'" in html
    assert "function _researchPapersUnavailable()" in html

    a = html.index("function renderResearchPapers()")
    b = html.index("window.showMorePapers", a)
    render = html[a:b]
    assert "_papersStatus === 'loading'" in render
    assert "_papersStatus === 'unavailable'" in render
    assert render.index("_papersStatus === 'unavailable'") < render.index("!_papers.length")
    assert "Research papers unavailable" in render
    assert "_papersErr" not in render

    a = html.index("function _ensureResearchPapers()")
    b = html.index("function _calibrationUnavailable()", a)
    ensure = html[a:b]
    assert "_researchPapersUnavailable()" in ensure
    assert "_papersLoaded = _papersStatus !== 'unavailable'" in ensure

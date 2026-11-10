"""Guards for the on-the-spot research-paper PDF engine (app/research_pdf).

The engine renders WITHOUT AI, deterministically, so the real risk is robustness across
wildly varying content: long reports, empty sections, XML-special chars, ragged markdown
tables, malformed emphasis, missing fields. These tests prove it always emits a valid PDF
and never raises on content — exactly the failure mode flagged for this feature.
"""
from __future__ import annotations

import glob
import json
import os
import re
import unittest
from unittest.mock import patch
from pathlib import Path

import pytest

from app import research_pdf as R

_PAPERS = glob.glob(str(Path(__file__).resolve().parent.parent / "data" / "research" / "papers" / "*.json"))


def _valid_pdf(b: bytes) -> bool:
    return isinstance(b, (bytes, bytearray)) and b[:4] == b"%PDF" and b"%%EOF" in b[-2048:]


def test_tags_balanced():
    assert R._tags_balanced("<b>x</b>")
    assert R._tags_balanced("<b>a <i>b</i> c</b>")
    assert not R._tags_balanced("<b>a <i>b</b></i>")   # mis-nested
    assert not R._tags_balanced("<b>unclosed")
    assert R._tags_balanced("plain text, no tags")


def test_escaping_neutralises_xml():
    # a stray '<', '&', '>' must never reach ReportLab unescaped
    out = R._esc("P<E & margins > 50% <NVDA>")
    assert "<" not in out and ">" not in out
    assert "&amp;" in out and "&lt;" in out and "&gt;" in out


def test_malformed_emphasis_falls_back_to_plain():
    # overlapping markers would mis-nest; _p must fall back, not crash
    para = R._p("**bold *italic** weird* nesting", R._styles()["body"])
    assert para is not None


@pytest.mark.skipif(not _PAPERS, reason="no saved research papers present")
def test_all_saved_papers_render():
    for f in _PAPERS:
        paper = json.load(open(f))
        b = R.build(paper, {})
        assert _valid_pdf(b), f"invalid PDF for {os.path.basename(f)}"


@pytest.mark.parametrize("paper", [
    {},                                                              # totally empty
    {"ticker": "X"},                                                # ticker only
    {"ticker": "LONG", "report_md": "## H\n\n" + ("word " * 5000)},  # multi-page flow
    {"ticker": "XML", "report_md": "a < b & c > d, P<E, M&A, 3<5x",
     "key_risks": ["risk with < and & and > chars"], "summary": "1 < 2 & 3 > 0"},
    {"ticker": "TBL", "report_md": "| Lens | Dir | Val |\n|---|---|---|\n| Trend | up | 1.2 |\n| Carry | mixed |\n| x |"},
    {"ticker": "BAD", "report_md": "**bold *italic** stray * and ** and `code"},
    {"ticker": "LINK", "report_md": "see [SEC](https://sec.gov/x?a=1&b=2) and [bad](notaurl)"},
    {"ticker": "BUL", "report_md": "- a\n- b\n* c\n1. d\n2. e\n\n---\n\nplain"},
    {"ticker": "FV", "fair_value": 245, "price_at_review": 210.69, "engine_score": 55,
     "research_score": 52, "combined": 54, "viability": "rich", "confirmed": False},
    # malformed-shape guards (these used to crash build() — see adversarial review)
    {"ticker": "ZP", "fair_value": 100, "price_at_review": "0"},      # string-zero price → no ZeroDivisionError
    {"ticker": "ZP2", "fair_value": 100, "price_at_review": "0.0"},
    {"ticker": "MD", "report_md": {"k": "v"}},                        # non-string report_md
    {"ticker": "MD2", "report_md": 42},
    {"ticker": "KR", "key_risks": 42},                               # non-iterable key_risks
    {"ticker": "KR2", "key_risks": {"a": 1}},
    {"ticker": "VB", "viability": 123},                              # non-string viability
])
def test_edge_cases_never_crash(paper):
    b = R.build(paper, {})
    assert _valid_pdf(b)


def test_meta_fields_render():
    paper = {"ticker": "NVDA", "fair_value": 245, "price_at_review": 210.69,
             "combined": 54, "engine_score": 55, "research_score": 52, "viability": "rich",
             "report_md": "## Thesis\n\nGreat company.", "key_risks": ["concentration"]}
    meta = {"name": "Nvidia Corp", "sector": "Technology", "price": 211.0, "market_cap": 5.2e12,
            "fwd_pe": 34.0, "div_yield": 0.0003, "analyst_target": 260, "rating": "Buy",
            "rev_growth": 0.85, "gross_margin": 0.75, "net_margin": 0.55, "roe": 1.1,
            "description": "Designs GPUs.", "next_earnings": "Aug 20, 2026"}
    assert _valid_pdf(R.build(paper, meta))
    # None-laden meta must also be safe
    assert _valid_pdf(R.build(paper, {k: None for k in meta}))


def test_endpoint_returns_pdf():
    import bot  # noqa: F401 — bootstraps vendor/macro
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    from app import web
    from brain import research_paper

    # conftest isolates the papers dir to a tmp path, so seed one paper for the endpoint to find
    paper = {"id": "2026-06-18-NVDA", "ticker": "NVDA", "asof": "2026-06-18",
             "generated_at": "2026-06-18T00:00:00Z", "fair_value": 245, "engine_score": 55,
             "research_score": 52, "combined": 54, "viability": "rich", "confirmed": False,
             "report_md": "## Thesis\n\nGreat company with **observed** demand.",
             "summary": "Strong franchise.", "key_risks": ["concentration"],
             "mode": "llm", "schema": "research_paper.v1"}
    research_paper.save_paper(paper)
    pid = "2026-06-18-NVDA"
    app = FastAPI(); app.include_router(web.router)
    c = TestClient(app)
    r = c.get("/research_paper.pdf", params={"id": pid})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.content[:4] == b"%PDF"
    # unknown id -> clean 404, not a 500
    assert c.get("/research_paper.pdf", params={"id": "nope-xyz"}).status_code == 404


# Real ReportLab pagination; synthetic content, no store or network reads.
class ResearchPdfPaginationTests(unittest.TestCase):
    def render(self, markdown):
        drawn = []
        draw_text = R.NumberedCanvas.drawText

        def record(canvas, text_object):
            drawn.append(text_object.getCode())
            return draw_text(canvas, text_object)

        paper = {
            "ticker": "SYNTH",
            "company": "Synthetic Pagination Fixture",
            "generated_at": "2026-11-10T05:00:00Z",
            "combined": 50,
            "engine_score": 40,
            "research_score": 60,
            "report_md": markdown,
        }
        with patch.object(R.NumberedCanvas, "drawText", record):
            pdf = R.build(paper, {})
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        pages = len(re.findall(rb"/Type\s*/Page\b", pdf))
        self.assertGreaterEqual(pages, 1)
        text = "\n".join(drawn)
        for page in range(1, pages + 1):
            self.assertEqual(text.count(f"Page {page} of {pages}"), 1)
        return pages, text

    def test_tall_body_cell_splits_without_losing_or_repeating_text(self):
        values = [f"fact{i:04d}" for i in range(700)]
        pages, text = self.render(
            "| EvidenceHeader | DetailHeader |\n|---|---|\n| Synthetic | "
            + " ".join(values) + " |\n\nAfterTableMarker"
        )
        self.assertGreaterEqual(pages, 3)
        self.assertEqual(re.findall(r"fact\d{4}", text), values)
        self.assertGreaterEqual(text.count("DetailHeader"), 3)
        self.assertEqual(text.count("AfterTableMarker"), 1)

    def test_tall_cells_in_both_columns_preserve_following_rows(self):
        left = [f"left{i:04d}" for i in range(500)]
        right = [f"right{i:04d}" for i in range(650)]
        pages, text = self.render(
            "| LeftHeader | RightHeader |\n|---|---|\n| "
            + " ".join(left) + " | " + " ".join(right)
            + " |\n| FinalLeftMarker | FinalRightMarker |"
        )
        self.assertGreaterEqual(pages, 3)
        self.assertEqual(re.findall(r"left\d{4}", text), left)
        self.assertEqual(re.findall(r"right\d{4}", text), right)
        self.assertGreaterEqual(text.count("RightHeader"), 3)
        self.assertEqual(text.count("FinalLeftMarker"), 1)
        self.assertEqual(text.count("FinalRightMarker"), 1)

    def test_regular_table_stays_on_one_page(self):
        pages, text = self.render(
            "| KeyHeader | ValueHeader |\n|---|---|\n| OrdinaryMarker | 0 |"
        )
        self.assertEqual(pages, 1)
        self.assertEqual(text.count("KeyHeader"), 1)
        self.assertEqual(text.count("OrdinaryMarker"), 1)

    def test_ragged_table_preserves_present_cells(self):
        _, text = self.render(
            "| KeyHeader | ValueHeader | ExtraHeader |\n|---|---|---|\n"
            "| RaggedMarker |\n| SecondMarker | ThirdMarker | FourthMarker |"
        )
        for marker in ("RaggedMarker", "SecondMarker", "ThirdMarker", "FourthMarker"):
            self.assertEqual(text.count(marker), 1)

    def test_long_plain_paragraph_still_paginates(self):
        values = [f"plain{i:04d}" for i in range(1000)]
        pages, text = self.render(" ".join(values))
        self.assertGreaterEqual(pages, 2)
        self.assertEqual(re.findall(r"plain\d{4}", text), values)



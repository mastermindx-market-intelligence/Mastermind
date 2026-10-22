"""Structural + behavioral proof for the US-only V3 Decision Snapshot evidence inspector.

The panel is a bounded, read-only manifest view over one already-hydrated
``GET /api/decision-snapshot?book=autonomous`` call: it must never imply a PM, target,
alpha result, execution authority, or live allocation exists. Structural assertions use a
brace-counting ``_function_block`` (a one-line regex stops at the first unrelated closing
brace inside a body) to isolate JS functions; behavioral assertions execute the actual
renderer source in Node against a fake DOM so escaping, row caps, state colors, and the
hard-false authority fence are proven against real output rather than substrings alone.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from control_plane.wake_events import canonical_json_bytes

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
NODE = shutil.which("node")

_FORBIDDEN_COPY = (
    "recommend", "recommendation", "target weight", "forecast", "ranking",
    "proven alpha", "validated alpha", "buy signal", "sell signal", "trade now",
)


# ---------------------------------------------------------------------------
# Structural helpers — brace counting, not a fragile one-line regex.
# ---------------------------------------------------------------------------

def _function_block(html: str, name: str) -> str:
    """Extract the full source of a top-level ``function <name>(...) { ... }``.

    Walks braces one character at a time, tracking string/template-literal and comment
    state, so a ``}`` that only closes an inner block (or one that lives inside a string
    or comment) never terminates the extraction early.
    """
    marker = "function " + name + "("
    start = html.find(marker)
    if start == -1:
        raise AssertionError(f"function {name} not found in HTML")
    brace_start = html.find("{", start)
    if brace_start == -1:
        raise AssertionError(f"function {name} has no body")
    depth = 0
    in_str: str | None = None
    in_line_comment = False
    in_block_comment = False
    i = brace_start
    n = len(html)
    while i < n:
        ch = html[i]
        two = html[i:i + 2]
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if two == "*/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if two == "//":
            in_line_comment = True
            i += 2
            continue
        if two == "/*":
            in_block_comment = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[start:i + 1]
        i += 1
    raise AssertionError(f"function {name} body never closes (unbalanced braces)")


def _fetch_calls(html: str) -> list[str]:
    """Return the full text of every ``fetch(...)`` call expression (brace/paren-depth
    aware, string-aware) so a URL substring check can't be fooled by a comment or an
    unrelated later paren."""
    calls = []
    idx = 0
    while True:
        start = html.find("fetch(", idx)
        if start == -1:
            break
        i = start + len("fetch")
        depth = 0
        in_str: str | None = None
        while i < len(html):
            ch = html[i]
            if in_str is not None:
                if ch == "\\":
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                i += 1
                continue
            if ch in ("'", '"', "`"):
                in_str = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        # extend to the end of a trailing .then(...).catch(...) chain on the same statement
        j = i
        while html[j:j + 1] == "." or html[j:j + 5] in (".then", ".catc"):
            nxt = html.find("(", j)
            if nxt == -1:
                break
            depth2 = 0
            k = nxt
            in_str2: str | None = None
            while k < len(html):
                ch = html[k]
                if in_str2 is not None:
                    if ch == "\\":
                        k += 2
                        continue
                    if ch == in_str2:
                        in_str2 = None
                    k += 1
                    continue
                if ch in ("'", '"', "`"):
                    in_str2 = ch
                elif ch == "(":
                    depth2 += 1
                elif ch == ")":
                    depth2 -= 1
                    if depth2 == 0:
                        k += 1
                        break
                k += 1
            j = k
        calls.append(html[start:j])
        idx = j
    return calls


def _write_methods(html: str) -> str:
    """Concatenation of every fetch call (see ``_fetch_calls``) that declares an explicit
    POST/PUT/PATCH/DELETE method — so a caller can assert a given URL never appears in a
    write path."""
    write_re = re.compile(r"""method\s*:\s*['"](POST|PUT|PATCH|DELETE)['"]""")
    return "\n".join(call for call in _fetch_calls(html) if write_re.search(call))


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

def test_snapshot_panel_is_us_v3_scoped_and_bilingual():
    assert 'id="decision-snapshot"' in HTML
    assert "V3 Decision Snapshot" in HTML
    assert "V3 决策快照" in HTML
    assert "PF_US_V3_ONLY" in HTML
    assert "'decision-snapshot'" in HTML


def test_panel_precedes_shadow_books_section():
    assert HTML.index('id="decision-snapshot"') < HTML.index('id="shadow-books"')


def test_snapshot_fetch_is_read_only_and_singleton_hydrated():
    assert "fetch('/api/decision-snapshot?book=autonomous')" in HTML
    assert "renderDecisionSnapshot()" in HTML
    assert "/api/decision-snapshot" not in _write_methods(HTML)
    # singleton: exactly one call site fetches this endpoint anywhere in the file.
    assert HTML.count("fetch('/api/decision-snapshot?book=autonomous')") == 1


def test_snapshot_renderer_escapes_server_text():
    block = _function_block(HTML, "renderDecisionSnapshot")
    for field in ("snapshot_id", "source_id", "status", "error_code"):
        assert "esc(" in block
    assert "innerHTML = d." not in block


def test_non_us_books_hide_snapshot_panel():
    block = _function_block(HTML, "applyPortfolioScope")
    assert "var usV3 = _portfolio === 'autonomous'" in block
    assert "PF_US_V3_ONLY.forEach" in block


def test_pf_us_v3_only_is_not_folded_into_pf_auto_only_or_brain_book_check():
    # Mutation guard: the brief explicitly forbids reusing _isBrainBook/PF_AUTO_ONLY for
    # this US-only scope, since CN/HK/archived Brain books have no V3 snapshot evidence.
    only_block = HTML[HTML.index("var PF_US_V3_ONLY"):HTML.index("var PF_US_V3_ONLY") + 200]
    assert "_isBrainBook" not in only_block
    auto_only_line = HTML[HTML.index("var PF_AUTO_ONLY"):HTML.index("\n", HTML.index("var PF_AUTO_ONLY"))]
    assert "decision-snapshot" not in auto_only_line


def test_collapse_map_and_restoration_and_final_applycoll_include_panel():
    collapsed_line = HTML[HTML.index("var _collapsed ="):HTML.index("\n", HTML.index("var _collapsed ="))]
    assert "'decision-snapshot': true" in collapsed_line
    restore_block = HTML[HTML.index("['runs', 'rejected', 'brainlog', 'research'"):]
    restore_line = restore_block[:restore_block.index("\n")]
    assert "'decision-snapshot'" in restore_line
    fetch_all_block = _function_block(HTML, "fetchAll")
    assert "applyColl('decision-snapshot')" in fetch_all_block


def test_render_wiring_calls_renderer_from_renderall():
    block = _function_block(HTML, "_renderAll")
    assert "renderDecisionSnapshot" in block


def test_lang_rerender_reuses_cache_without_refetch():
    # langchange must re-render from the cached _decisionSnapshot, not issue a second fetch.
    start = HTML.index("document.addEventListener('langchange'")
    end = HTML.index("});", start) + 3
    block = HTML[start:end]
    assert "_renderAll()" in block
    assert "/api/decision-snapshot" not in block


def test_hydrate_shared_settled_indexing_is_correct():
    block = _function_block(HTML, "_hydrateShared")
    assert "decisionSnapshotRes = s[9]" in block
    assert "_decisionSnapshot = decisionSnapshotRes.status === 'fulfilled' ? decisionSnapshotRes.value : null;" in block
    # exactly one decision-snapshot fetch inside the Promise.allSettled array this function builds
    assert block.count("/api/decision-snapshot") == 1


def test_no_forbidden_execution_or_forecast_copy_in_static_source():
    block = _function_block(HTML, "renderDecisionSnapshot")
    lowered = block.lower()
    for phrase in _FORBIDDEN_COPY:
        assert phrase not in lowered, f"forbidden copy found: {phrase!r}"


def test_authority_fence_is_hard_coded_not_read_from_payload():
    block = _function_block(HTML, "renderDecisionSnapshot")
    assert "write_permitted=false" in block
    assert "execution_authority=false" in block
    assert "numeric_target_authority=false" in block
    # never trusts a payload-supplied authority value for the fence text
    assert "d.write_permitted" not in block
    assert "snap.authority" not in block


def test_row_caps_and_omitted_counts_present():
    block = _function_block(HTML, "renderDecisionSnapshot")
    assert "MAX_ROWS = 40;" in block
    assert "sourcesArr.slice(0, MAX_ROWS)" in block
    assert "gapsArr.slice(0, MAX_ROWS)" in block
    assert "srcOmitted" in block and "gapOmitted" in block


def test_pr548_dependency_surfaced_never_says_repaired():
    block = _function_block(HTML, "renderDecisionSnapshot")
    assert "#548" in block
    assert "not repaired" in block or "尚未修复" in block
    assert "repaired" not in block.lower().replace("not repaired", "")


def test_no_section_page_fetch_bounded_manifest_only():
    block = _function_block(HTML, "renderDecisionSnapshot")
    assert "fetch(" not in block


# ---------------------------------------------------------------------------
# Behavioral tests — execute the real renderer source in Node against a fake DOM.
# ---------------------------------------------------------------------------

def _extract_renderer_source() -> str:
    start = HTML.index("var DECISION_SNAPSHOT_STATE_COLOR")
    end_marker = "function renderDecisionSnapshot("
    end_start = HTML.index(end_marker, start)
    render_block = _function_block(HTML, "renderDecisionSnapshot")
    return HTML[start:end_start] + render_block


def _run_renderer(snapshot_payload, *, lang: str = "en") -> dict:
    if NODE is None:
        pytest.skip("node is required for the fake-DOM renderer proof")
    source = _extract_renderer_source()
    # Extract the real GLOBAL esc() implementation — the one the renderer actually calls at
    # runtime. There is a second, weaker `var esc = function(s) {` scoped inside renderMd()
    # that only escapes `& < >` (no quotes); anchoring on a bare substring match would find
    # that one first since it appears earlier in the file. The global declaration is the only
    # occurrence that sits at column 0 (immediately after a newline, no leading indentation).
    esc_start = HTML.index("\nvar esc = function(s) {") + 1
    esc_end = HTML.index("};", esc_start) + 2
    esc_source = HTML[esc_start:esc_end]
    assert "&quot;" in esc_source and "&#39;" in esc_source, "harness bound the wrong esc()"

    harness = f"""
{esc_source}
var E = function(id) {{ return document.getElementById(id); }};
var _decisionSnapshot = {json.dumps(snapshot_payload)};
var __el = {{ innerHTML: '' }};
var document = {{
  documentElement: {{ getAttribute: function() {{ return {json.dumps(lang)}; }} }},
  getElementById: function(id) {{ return id === 'decision-snapshot' ? __el : null; }}
}};
function collH2(id, en, zh, sub) {{ return '<h2>' + en + '|' + zh + '</h2>'; }}
{source}
renderDecisionSnapshot();
console.log(JSON.stringify({{ html: __el.innerHTML }}));
"""
    result = subprocess.run([NODE, "-e", harness], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"node harness failed: {result.stderr}")
    return json.loads(result.stdout)


def _receipt(source_id, domains, status="AVAILABLE", coverage_state="COMPLETE", error_code=None):
    return {
        "source_id": source_id, "domains": domains, "status": status,
        "coverage_state": coverage_state, "error_code": error_code,
    }


def _seal_gap(*, code, source_id=None, section_id=None, owner=None, detail=None):
    """Build a gap exactly the way ``portfolio.decision_snapshot._seal_gaps`` does: a dict
    with the fixed ``code/source_id/section_id/owner/detail`` fields, sealed through the
    same canonical-JSON serializer the production code path uses
    (``control_plane.wake_events.canonical_json_bytes``) — not a hand-rolled ``json.dumps``
    that could silently drift from the real byte shape. Real snapshot gaps are strings, not
    objects (``decision_snapshot_contracts.py``'s ``.gaps must be a list of strings``)."""
    gap = {"code": code, "source_id": source_id, "section_id": section_id, "owner": owner, "detail": detail}
    return canonical_json_bytes(gap).decode("ascii")


def _base_snapshot(**overrides):
    # Real internal source_id for the book_truth domain (decision_snapshot_sources.py:199),
    # not a fabricated one — fixtures must track the checked-in contract, not the renderer's
    # own assumptions about it.
    snap = {
        "snapshot_id": "sha256:" + "ab" * 32,
        "decision_cutoff": "2026-09-14T20:00:00Z",
        "recorded_at": "2026-09-14T20:05:00Z",
        "coverage_state": "PARTIAL",
        "summary": {"sources_total": 2, "sources_available": 1},
        "correction": {"status": "ORIGINAL"},
        "sources": [
            _receipt("macro.risk_envelope", ["risk_truth"], coverage_state="COMPLETE"),
            _receipt("book.account", ["book_truth"], coverage_state="PARTIAL"),
        ],
        "gaps": [],
    }
    snap.update(overrides)
    return snap


@pytest.mark.parametrize("status,expected_color", [
    ("COMPLETE", "var(--up)"),
    ("PARTIAL", "var(--warn)"),
    ("CORRECTED_GENERATION_AVAILABLE", "var(--warn)"),
    ("BLOCKED", "var(--down)"),
    ("INVALID", "var(--down)"),
])
def test_state_colors_are_distinct_per_status(status, expected_color):
    out = _run_renderer({"status": status, "snapshot": _base_snapshot()})
    match = re.search(r'color:(var\(--\w+\))">' + re.escape(status), out["html"])
    assert match is not None, out["html"]
    assert match.group(1) == expected_color


def test_no_snapshot_state_renders_muted_and_distinct_from_error():
    no_snap = _run_renderer({"status": "NO_SNAPSHOT"})
    assert "var(--up)" not in no_snap["html"]
    assert "var(--down)" not in no_snap["html"]
    assert "No V3 decision snapshot" in no_snap["html"]

    err = _run_renderer(None)
    assert "unavailable" in err["html"]
    assert "No V3 decision snapshot" not in err["html"]


def test_malformed_payload_degrades_without_throwing():
    out = _run_renderer({"status": "COMPLETE", "snapshot": "not-an-object"})
    assert "unavailable" in out["html"]
    out2 = _run_renderer({"status": 123})
    assert "unavailable" in out2["html"]


def test_authority_fence_survives_a_tampered_true_claim():
    snap = _base_snapshot(authority={"write_permitted": True, "execution_authority": True,
                                      "numeric_target_authority": True})
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    assert "write_permitted=false" in out["html"]
    assert "write_permitted=true" not in out["html"].lower()


def test_server_strings_are_escaped_not_injected():
    canary = "<script>alert(1)</script>\"'"
    snap = _base_snapshot(
        sources=[_receipt(canary, ["book_truth"], coverage_state="PARTIAL")],
        gaps=[_seal_gap(code=canary, owner=canary, detail=canary)],
    )
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    assert "<script>" not in out["html"]
    assert "&lt;script&gt;" in out["html"]


def test_harness_binds_the_quote_escaping_global_esc():
    # Important-1: a prior harness bound the wrong (weaker, quote-unaware) local `esc()`
    # scoped inside renderMd(), so the XSS canary above passed even though a real attribute
    # interpolation would not have been safe. Prove the harness — and therefore every other
    # behavioral assertion here — actually exercises the quote-escaping global `esc()`.
    snap = _base_snapshot(sources=[_receipt('a"b\'c', ["book_truth"])])
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    assert "&quot;" in out["html"] and "&#39;" in out["html"]
    assert 'a"b' not in out["html"]


def test_unparseable_gap_string_renders_raw_escaped_fallback_not_blank():
    # Critical-1 edge case: a gap string that fails JSON.parse must still render as one
    # escaped row, never as ''.
    bad = "not-json-at-all <b>x</b>"
    out = _run_renderer({"status": "PARTIAL", "snapshot": _base_snapshot(gaps=[bad])})
    html = out["html"]
    assert "not-json-at-all" in html
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html
    assert html.count("<tr>") >= 1


def test_sealed_string_gaps_render_as_rows_not_blanks():
    # Critical-1: real snapshot gaps are sealed canonical-JSON strings, not objects.
    gaps = [
        _seal_gap(code="MISSING", source_id="macro.regime"),
        _seal_gap(code="UNQUALIFIED_CLOCK", source_id="macro.factor_betas"),
    ]
    out = _run_renderer({"status": "PARTIAL", "snapshot": _base_snapshot(gaps=gaps)})
    html = out["html"]
    assert "Gaps (2)" in html
    assert "MISSING" in html
    assert "UNQUALIFIED_CLOCK" in html
    assert html.count("<tr>") >= 2


def test_malformed_source_entry_renders_visible_placeholder_not_vanish():
    # Minor-3 (folded into the Critical-1 honesty repair): a non-object source entry must
    # still consume a visible row rather than silently disappearing from the count.
    snap = _base_snapshot(sources=[
        _receipt("a", ["book_truth"], coverage_state="COMPLETE"),
        "not-a-receipt-object",
        None,
    ])
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    html = out["html"]
    assert "Sources (3)" in html
    assert html.count("<tr>") >= 3
    assert "not-a-receipt-object" in html


def test_forty_row_cap_and_exact_omitted_count():
    sources = [_receipt(f"src-{i}", ["book_truth"]) for i in range(45)]
    gaps = [_seal_gap(code=f"GAP-{i}") for i in range(43)]
    snap = _base_snapshot(sources=sources, gaps=gaps)
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    html = out["html"]
    assert html.count("src-") == 40
    assert html.count("GAP-") == 40
    assert "5 additional source row(s) omitted" in html
    assert "3 additional gap row(s) omitted" in html
    # Discriminates a "fixed" omitted count that still hides real rows: the caption/omitted
    # arithmetic can lie independently of whether any <tr> actually rendered.
    assert html.count("<tr>") >= 40


def test_domain_coverage_never_invents_absent_domains_as_complete():
    snap = _base_snapshot(sources=[
        _receipt("a", ["market_structure"], coverage_state="COMPLETE"),
        _receipt("b", ["market_structure"], coverage_state="BLOCKED"),
    ])
    out = _run_renderer({"status": "BLOCKED", "snapshot": snap})
    assert "market_structure" in out["html"]
    assert "risk_truth" not in out["html"]  # absent from every receipt: never invented


def test_domain_coverage_all_complete_rule():
    snap = _base_snapshot(sources=[
        _receipt("a", ["independence"], coverage_state="COMPLETE"),
        _receipt("b", ["independence"], coverage_state="COMPLETE"),
    ])
    out = _run_renderer({"status": "COMPLETE", "snapshot": snap})
    idx = out["html"].index("independence")
    assert "COMPLETE" in out["html"][idx:idx + 200]


def test_pr548_surfaced_from_real_contract_receipt_shape():
    # Critical-2 Path A: the identifying field is source_id, not domains — domains for this
    # source is always ("market_structure",) per decision_snapshot_sources.EXTERNAL_SOURCE_SPECS.
    snap = _base_snapshot(sources=[
        _receipt("macro.sector_rotation", ["market_structure"],
                 status="DEPENDENCY_PARTIAL", coverage_state="PARTIAL"),
    ])
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    assert "#548" in out["html"]
    assert "not repaired" in out["html"] or "尚未修复" in out["html"]


def test_pr548_surfaced_from_real_sealed_gap_string():
    # Critical-2 Path B: the real #548 gap is the exact dependency_owned_elsewhere gap
    # decision_snapshot_sources.py emits, sealed to a string — not a live object.
    #
    # A bare "#548" substring check is not discriminating on its own: the gap table renders
    # the raw gap content (including the literal "Mastermind PR #548" owner field) regardless
    # of whether the pr548-detection `.some(...)` actually fired, so that assertion alone
    # would still pass even if the detection path silently regressed back to rejecting
    # strings. The second assertion checks the dependency-NOTE's distinctive copy, which only
    # renders when `pr548` is actually true.
    gap = _seal_gap(
        code="DEPENDENCY_OWNED_ELSEWHERE",
        source_id="macro.sector_rotation",
        owner="Mastermind PR #548",
        detail="non-lossy Sector Central reader is owned by PR #548; S0 captures receipt only",
    )
    out = _run_renderer({"status": "PARTIAL", "snapshot": _base_snapshot(gaps=[gap])})
    assert "#548" in out["html"]
    assert "not repaired" in out["html"] or "尚未修复" in out["html"]


def test_pr548_absent_when_no_dependency_signal():
    snap = _base_snapshot()
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    assert "#548" not in out["html"]


def test_fixture_domains_match_the_checked_in_contract():
    """Anti-drift: the UI fixture vocabulary must come from the real spec table, not a
    hand-rolled guess — this is the guard that would have caught both #548 Criticals at
    write time, by failing the moment a fixture's (source_id, domains) pair diverges from
    ``decision_snapshot_sources.EXTERNAL_SOURCE_SPECS``."""
    from portfolio.decision_snapshot_sources import EXTERNAL_SOURCE_SPECS
    spec = next(s for s in EXTERNAL_SOURCE_SPECS if s.source_id == "macro.sector_rotation")
    assert "macro.sector_rotation" not in spec.domains
    assert spec.domains == ("market_structure",)


def test_unknown_receipt_coverage_is_not_relabelled_partial():
    # Important-2: UNKNOWN is a distinct COVERAGE_STATES member (coverage not known) — the
    # domain-aggregation rule must not report more knowledge than the receipts support.
    snap = _base_snapshot(sources=[
        _receipt("a", ["market_structure"], coverage_state="UNKNOWN"),
        _receipt("b", ["market_structure"], coverage_state="UNKNOWN"),
    ])
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    idx = out["html"].index("market_structure")
    window = out["html"][idx:idx + 200]
    assert "UNKNOWN" in window
    assert "PARTIAL" not in window


def test_rendered_output_contains_no_forbidden_copy():
    snap = _base_snapshot()
    out = _run_renderer({"status": "PARTIAL", "snapshot": snap})
    lowered = out["html"].lower()
    for phrase in _FORBIDDEN_COPY:
        assert phrase not in lowered

"""Static product-contract tests for the Chairman Control Room's read-only
Attention Frontier section.

These mirror the autonomy-section tests in
``tests/test_chairman_control_room_ui_x1.py``.  They validate the private-local
presentation surface only: the section renders the already-composed
``control_room.attention_frontier`` projection and is granted no admission,
authority, ordering or action authority of its own.

The laws pinned here come from the F0G consolidated contract
(``research/MASTERMIND_EXECUTIVE_ATTENTION_ECONOMICS_F0G_CONSOLIDATED_V1_CONTRACT_2026-08-30.md``):

* §13 — the seven-group primary composition and the ten-slot card order;
* §3.1 — authority is a partition, resolved before attention ordering;
* §3.2/§3.3 — attention pressure and serviceability are orthogonal, so red
  urgency may never imply permission and grey blocked may never imply calm;
* §4/§11 — an unanswered admission plane is reported as unknown, never as an
  empty desk, because unknown is not zero, healthy or harmless;
* §9/§3.4 — fairness sentinels stay visible and every compacted demand keeps a
  receipt.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static" / "chairman_control"
INDEX = STATIC / "index.html"
JS = STATIC / "control_room.js"
CSS = STATIC / "control_room.css"


class _MarkupProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.inline_scripts = 0
        self.script_srcs: list[str | None] = []
        self.style_attrs: list[tuple[str, str]] = []
        self.nav_targets: list[str] = []
        self._script_without_src = False

    def handle_starttag(self, tag: str, attrs) -> None:
        row = dict(attrs)
        if row.get("id"):
            self.ids.append(row["id"])
        if row.get("data-nav"):
            self.nav_targets.append(row["data-nav"])
        if row.get("style") is not None:
            self.style_attrs.append((tag, row["style"]))
        if tag == "script":
            self.script_srcs.append(row.get("src"))
            self._script_without_src = row.get("src") is None

    def handle_data(self, data: str) -> None:
        if self._script_without_src and data.strip():
            self.inline_scripts += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._script_without_src = False


def _frontier_js() -> str:
    """The section's own banner-delimited block."""
    source = JS.read_text(encoding="utf-8")
    start = source.index("  // attention frontier ---")
    end = source.index("  // state ---", start)
    return source[start:end]


def _frontier_code() -> str:
    """The section block with its whole-line ``//`` commentary removed.

    Used where an assertion must be about what the section *does*, not about
    the presentation law written above it — a banner comment that names a
    forbidden pattern in order to forbid it is not an occurrence of it.
    """
    return "\n".join(
        line for line in _frontier_js().splitlines() if not line.lstrip().startswith("//")
    )


def _frontier_css() -> str:
    styles = CSS.read_text(encoding="utf-8")
    start = styles.index("/* attention frontier — pressure")
    end = styles.index("/* autonomy — responsibilities", start)
    return styles[start:end]


def _css_theme_blocks() -> tuple[str, str]:
    source = CSS.read_text(encoding="utf-8")
    light_start = source.index('html[data-theme="light"] {')
    root = source[source.index(":root {") : light_start]
    light = source[light_start : source.index("\n}", light_start)]
    return root, light


def _declared(block: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("--af-") and ":" in line:
            name, _, value = line.partition(":")
            rows[name.strip()] = value.strip().rstrip(";")
    return rows


def _ordered(block: str, needles: list[str]) -> None:
    previous = -1
    for needle in needles:
        found = block.index(needle)
        assert found > previous, f"{needle!r} is out of contract order"
        previous = found


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------
def test_frontier_has_one_mount_point_and_one_nav_entry() -> None:
    markup = INDEX.read_text(encoding="utf-8")
    probe = _MarkupProbe()
    probe.feed(markup)

    assert 'id="attention-frontier"' in markup
    assert 'id="ccr-attention-frontier"' in markup
    assert 'data-nav="attention-frontier"' in markup
    assert 'id="nav-attention-frontier-count"' in markup
    assert {"attention-frontier", "ccr-attention-frontier", "nav-attention-frontier-count"}.issubset(set(probe.ids))

    # Exactly one mount and exactly one nav entry — a second cockpit is not a
    # second view, it is a second truth.
    assert markup.count('id="ccr-attention-frontier"') == 1
    assert probe.nav_targets.count("attention-frontier") == 1
    assert probe.ids.count("attention-frontier") == 1
    assert len(probe.ids) == len(set(probe.ids)), "duplicate DOM ids make navigation ambiguous"

    assert probe.script_srcs == ["/static/control_room.js"]
    assert probe.inline_scripts == 0
    assert probe.style_attrs == []

    # The section shell participates in the shared view/scroll system.
    section = markup[markup.index('id="attention-frontier"') - 60 : markup.index('id="ccr-attention-frontier"')]
    assert 'class="ccr-view-section ccr-af-section"' in section

    # Composed by the shared renderer, never by page markup.
    for row_class in ("ccr-af-card", "ccr-af-group", "ccr-af-band", "ccr-af-partition"):
        assert row_class not in markup


def test_frontier_renders_only_from_the_canonical_projection_key() -> None:
    source = JS.read_text(encoding="utf-8")
    assert "renderAttentionFrontier(doc.attention_frontier)" in source
    # One canonical key, one read.  No second endpoint and no local truth store.
    assert source.count("doc.attention_frontier") == 1

    block = _frontier_js()
    assert "function renderAttentionFrontier(projection)" in block
    assert 'var mount = document.getElementById("ccr-attention-frontier")' in block
    assert "if (!mount) return;" in block
    # The section never fabricates freshness or randomness locally and never
    # defines a transport call of its own.  It is a pure read of an
    # already-composed projection.
    for forbidden in ("postJSON(", "getJSON(", "fetch(", "Date.now()", "Math.random("):
        assert forbidden not in block
    assert ".innerHTML" not in block
    assert "document.write" not in block
    assert "eval(" not in block


def test_frontier_absent_projection_is_source_qualified_not_an_error() -> None:
    block = _frontier_js()
    assert "function afNotWired(mount)" in block
    assert "Not wired yet" in block
    assert "No attention frontier projection was returned." in block
    # Absent is explicitly not "nothing needs you".
    assert "this is not a reading that nothing needs your attention" in block
    assert "ccr-af-quiet" in block
    assert "if (!STATE.frontier) {" in block
    # The not-yet-wired branch must not borrow the degraded-source alarm.
    assert "ccr-alarm" not in block
    assert "ccr-problem" not in block

    styles = CSS.read_text(encoding="utf-8")
    quiet = styles[styles.index(".ccr-af-quiet {") : styles.index(".ccr-af-quiet-title")]
    assert "var(--af-quiet-border)" in quiet
    assert "--danger" not in quiet


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------
def test_frontier_renders_all_seven_f0g_groups_in_contract_order() -> None:
    block = _frontier_js()
    _ordered(block, [
        'name: "Interrupts now"',
        'name: "Focus now"',
        'name: "Context batches next"',
        'name: "Intentional waits"',
        'name: "Autonomous continuation"',
        '"Source & action-path issues"',
        '"Concurrent executive pressure"',
    ])
    # The first five groups are the closed attention classes; the last two are
    # not classes and have their own readers, appended after them.
    render = block[block.index("function renderAttentionFrontier(projection)") :]
    _ordered(render, [
        "AF_GROUPS.forEach(",
        "afIssuesGroup(STATE.frontier, frontier, items)",
        "afConcurrentGroup(frontier, coverage)",
    ])
    for token in ("INTERRUPT_NOW", "FOCUS_NOW", "BATCH_NEXT", "VALID_WAIT", "AUTONOMOUS_CONTINUE"):
        assert f'key: "{token}"' in block


def test_frontier_empty_group_is_a_coverage_statement_not_an_all_clear() -> None:
    block = _frontier_js()
    group = block[block.index("function afGroup(group, items, frontier)") : block.index("function afFold(")]
    assert "ccr-af-group-empty" in group
    # Every group is drawn even when it holds nothing.
    assert "if (!members.length) {" in group
    assert "return section;" in group

    assert "That is a statement about what the sources reported" in block
    assert "uncovered rather than absent" in block
    # An empty group never claims the desk is clear.
    rendered = _frontier_code().lower()
    for forbidden in ("all clear", "nothing to do", "you are clear", "all good"):
        assert forbidden not in rendered


def test_frontier_partitions_by_authority_with_chairman_and_sol_as_headlines() -> None:
    block = _frontier_js()
    assert 'var AF_AUTHORITY_ORDER = [\n    "CHAIRMAN", "SOL",' in block
    assert "var AF_HEADLINE_AUTHORITY = { CHAIRMAN: true, SOL: true };" in block
    for token in ("COO_OR_WORKER", "EXECUTIVE_PLACEMENT", "ADMIN_OR_EXTERNAL", "NONE", "UNKNOWN"):
        assert token in block

    group = block[block.index("function afGroup(group, items, frontier)") : block.index("function afFold(")]
    assert "item.authority_requirement" in group
    assert "AF_HEADLINE_AUTHORITY[authority]" in group
    # An authority the closed order does not name is still shown, never dropped.
    assert "if (order.indexOf(authority) === -1) order.push(authority);" in group
    # Partition, not promotion: nothing moves between authority partitions.
    assert "never becomes Chairman work" in block


def test_frontier_card_follows_the_exact_f0g_slot_order() -> None:
    block = _frontier_js()
    card = block[block.index("function afCard(item, frontier)") : block.index("function afGroupHead(")]
    _ordered(card, [
        'className: "ccr-af-title"',              # 1 decision / action needed
        "AF_CLASS_VARIANT[item.attention_class]",  # 2 attention pressure
        'afLabelled(identity, "Authority"',        # 3 authority
        '"Can act now?"',                          # 4 can act now + exact target
        "item.exact_action_target",
        '"Why now"',                               # 5 why now
        '"What can continue"',                     # 6 what can continue
        '"What it unblocks"',                      # 7 what it unblocks
        '"Evidence"',                              # 8 evidence / freshness
        '"Bundle / root"',                         # 9 bundle / root context
        "afOpenDetail(item, openBtn)",             # 10 forensic receipts
    ])
    assert "item.downstream_unblocks" in card
    assert "item.factor_vector" in card
    assert "item.projection_relation" in card


# ---------------------------------------------------------------------------
# the two orthogonal readings
# ---------------------------------------------------------------------------
def test_frontier_keeps_pressure_and_serviceability_on_separate_tracks() -> None:
    """F0G §3.3: a demand may be ``INTERRUPT_NOW + BLOCKED``.  Blocked never
    means unimportant and urgent never means permission, so the two readings
    may not share ink in either direction."""
    block = _frontier_js()

    pressure = block[block.index("var AF_CLASS_VARIANT = {") : block.index("var AF_SERVICE_NAME")]
    assert 'INTERRUPT_NOW: "is-danger"' in pressure

    service = block[block.index("var AF_SERVICE_VARIANT = {") : block.index("var AF_SERVICE_SENTENCE")]
    # The serviceability chip never reaches for the urgency tone.
    assert "is-danger" not in service
    assert 'BLOCKED: "is-slate"' in service

    # And the blocked reading explicitly refuses to speak about urgency.
    assert "This says nothing about how urgent the demand is." in block
    # A blocked interrupt still reads as an interrupt.
    assert "This is a blocked interrupt." in block
    assert "does not lower the pressure" in block
    assert "does not grant permission" in block

    card = block[block.index("function afCard(item, frontier)") : block.index("function afGroupHead(")]
    assert 'if (afIsInterrupt(item)) cls += " is-interrupt";' in card
    assert 'if (item.serviceability === "BLOCKED") cls += " is-blocked";' in card

    section = _frontier_css()
    # Pressure owns the danger rail on the leading edge; the action path owns a
    # separate neutral rail on the other edge.  Both can be read at once.
    assert ".ccr-af-card.is-interrupt::before { background: var(--danger);" in section
    assert ".ccr-af-card.is-blocked::after" in section
    blocked_rule = section[section.index(".ccr-af-card.is-blocked::after") : section.index(".ccr-af-identity")]
    assert "var(--af-blocked-rail)" in blocked_rule
    assert "--danger" not in blocked_rule
    root, light = _css_theme_blocks()
    for block_text in (root, light):
        rail = block_text[block_text.index("--af-blocked-rail:") :].splitlines()[0]
        assert "--slate" in rail and "--danger" not in rail


def test_frontier_shows_actor_can_act_as_an_honest_tri_state() -> None:
    block = _frontier_js()
    can_act = block[block.index("function afCanAct(item)") : block.index("function afIsInterrupt(item)")]
    assert "item.actor_can_act === true" in can_act
    assert "item.actor_can_act === false" in can_act
    assert '"CAN ACT: UNKNOWN"' in can_act
    # Unknown falls through to its own reading; it is never folded into "no".
    assert "Unknown is not no." in can_act
    assert can_act.index("actor_can_act === false") < can_act.index("CAN ACT: UNKNOWN")
    # No truthiness test anywhere: `if (item.actor_can_act)` would read the
    # string "unknown" as yes.
    assert "if (item.actor_can_act)" not in block
    assert "!item.actor_can_act" not in block

    assert "Whether the required action path is usable is unknown. Unknown is not no." in block


def test_frontier_never_guesses_an_exact_action_target() -> None:
    block = _frontier_js()
    assert "No exact action target is available. None is guessed." in block
    assert "Candidate action targets conflict; none is picked." in block
    assert "item.exact_action_target" in block


# ---------------------------------------------------------------------------
# coverage honesty
# ---------------------------------------------------------------------------
def test_frontier_reports_admission_confidence_and_names_a_dark_source_plane() -> None:
    """F0G §4/§11: an empty frontier means one of two completely different
    things, and only admission confidence tells them apart."""
    block = _frontier_js()
    assert "coverage.admission_confidence" in block
    assert "AF_CONFIDENCE[confidence]" in block
    for token in ("NO_SOURCE", "GATES_ONLY", "SOURCED"):
        assert token in block

    no_source = block[block.index("NO_SOURCE: {") : block.index("GATES_ONLY: {")]
    assert "No admission source answered" in no_source
    assert "This frontier is empty because no admission source answered" in no_source
    assert "It is NOT a reading that nothing needs executive attention." in no_source
    # The alarm styling stays out of it: this is a truthful coverage statement.
    assert "is-danger" not in no_source

    gates_only = block[block.index("GATES_ONLY: {") : block.index("SOURCED: {")]
    assert "No Executive Inbox or Wake obligation answered this read." in gates_only

    # Unknown is not zero: the nav tally publishes a number only when the
    # projection said how much of the admission plane answered.  A dark,
    # unrecorded or unrecognized plane gets an em dash, never a confident 0.
    assert "function afTallyIsPublishable(coverage)" in block
    assert 'coverage.admission_confidence === "SOURCED" || coverage.admission_confidence === "GATES_ONLY"' in block
    assert 'afTallyIsPublishable(coverage) ? String(items.length) : "—"' in block

    band = block[block.index("function afCoverageBand(doc, coverage, items)") : block.index("function afRenderDetail(item)")]
    for key in (
        "coverage.admitted_demands",
        "coverage.visible_roots",
        "coverage.omitted_with_receipt",
        "coverage.interrupts",
        "coverage.blocked",
        "coverage.serviceability_unknown",
        "coverage.authority_unknown",
        "coverage.ready_age_unknown",
        "coverage.scan_reduction",
    ):
        assert key in band
    # A missing count is drawn as an em dash, never as zero.
    assert 'typeof pair[1] === "number" ? String(pair[1]) : "—"' in band


def test_frontier_shows_per_authority_concurrent_demand_with_its_receipts() -> None:
    block = _frontier_js()
    concurrent = block[block.index("function afConcurrentGroup(frontier, coverage)") : block.index("function afCoverageBand(")]
    assert "frontier.authority_frontiers" in concurrent
    assert "row.concurrent_demand" in concurrent
    assert "row.service_feasibility" in concurrent
    assert "row.feasibility_receipts" in concurrent
    assert "row.interrupt_root_count" in concurrent
    assert "row.interrupt_member_count" in concurrent
    assert "no feasibility receipt recorded" in concurrent
    # Congestion is congestion; it never becomes permission.
    assert "never grants delegation, target transfer or authority escalation" in concurrent

    for token in ("NONE", "SINGLE", "MULTIPLE_INDEPENDENT", "PROVEN_WINDOW_COLLISION", "FEASIBILITY_UNKNOWN"):
        assert token in block[block.index("var AF_CONCURRENT = {") : block.index("var AF_CONCURRENT_VARIANT")]
    for token in ("NOT_APPLICABLE", "UNKNOWN", "PROVEN_COLLISION"):
        assert token in block[block.index("var AF_FEASIBILITY = {") : block.index("var AF_AUTONOMOUS")]

    # An absent partition list is uncovered, never zero pressure.
    assert "concurrent executive pressure is uncovered rather than zero" in concurrent


def test_frontier_shows_fairness_sentinels_and_every_omission_reason() -> None:
    block = _frontier_js()
    concurrent = block[block.index("function afConcurrentGroup(frontier, coverage)") : block.index("function afCoverageBand(")]
    assert "frontier.fairness_sentinels" in concurrent
    assert "service protection, never added pressure" in concurrent
    assert "No oldest-ready sentinel was raised in this read." in concurrent
    # Unknown ready time is a coverage gap, not an age of zero (F0G §9).
    assert "coverage || {}).ready_age_unknown" in concurrent
    assert "never an age of zero" in concurrent
    assert "is_fairness_sentinel" in block

    issues = block[block.index("function afIssuesGroup(doc, frontier, items)") : block.index("function afConcurrentGroup(")]
    assert "frontier.omissions" in issues
    # Each omission carries relation, what covers it, and its exact reason.
    assert "row.relation" in issues
    assert "row.covered_by" in issues
    assert 'safeText(row.reason, "no reason recorded")' in issues
    assert "Compacted demands, each with its receipt" in issues
    # Every other coverage gap the projection reported stays reachable too.
    for key in ("doc.degraded", "item.issues", "admission.declined", "admission.steward_issue_codes"):
        assert key in issues
    # NON_ACTIONABLE demands are never silently dropped off the surface.
    assert '"NON_ACTIONABLE"' in issues


def test_frontier_drilldown_reuses_the_shared_drawer_and_receipt_fold() -> None:
    block = _frontier_js()
    assert 'auReceiptFold("Contributing sources", item.source_receipts)' in block
    # The shared drawer, not a second one.
    assert 'document.getElementById("ccr-detail-drawer")' in block
    assert 'document.getElementById("ccr-detail-body")' in block
    assert 'document.getElementById("ccr-detail-title")' in block
    assert "detailRail(rails," in block
    assert "detailLine(node," in block
    # The section does not re-implement the receipt row format: owner · ref ·
    # observed time · freshness is auReceiptFold's contract, reached by name.
    assert ".observed_at" not in _frontier_code()
    assert "receipt.owner" not in _frontier_code()

    source = JS.read_text(encoding="utf-8")
    fold = source[source.index("function auReceiptFold(name, rows)") : source.index("function auRuntimeRail(")]
    for field in ("row.owner", "row.ref", "row.observed_at", "row.freshness"):
        assert field in fold

    # A re-render keeps an open drawer on the demand it was opened for.
    assert "if (STATE.selectedFrontier) afRenderDetail(STATE.selectedFrontier);" in source
    for opener in ("openDetail", "openAutonomyDetail", "openAttentionDetail", "closeDetail"):
        fn = source[source.index(f"function {opener}(") :]
        fn = fn[: fn.index("\n  }\n")]
        assert "STATE.selectedFrontier = null;" in fn, f"{opener} must release the frontier drawer"


# ---------------------------------------------------------------------------
# material
# ---------------------------------------------------------------------------
def test_frontier_is_designed_for_two_themes_not_one_token_swap() -> None:
    root, light = _css_theme_blocks()
    dark_tokens = _declared(root)
    light_tokens = _declared(light)

    assert dark_tokens, "the attention frontier section must declare its own material tokens"
    assert set(dark_tokens) == set(light_tokens), (
        "every attention-frontier token needs a value in both theme blocks; a "
        "colour whose only definition lives inside one theme block is a skin, "
        "not a design"
    )

    for token in (
        "--af-card-bg",
        "--af-card-shadow",
        "--af-card-hover",
        "--af-band-fill",
        "--af-band-shadow",
        "--af-group-rule",
        "--af-interrupt-stripe",
        "--af-interrupt-glow",
        "--af-blocked-rail",
        "--af-partition-weight",
        "--af-body-ink",
        "--af-secondary-ink",
        "--af-quiet-border",
    ):
        assert dark_tokens[token] != light_tokens[token], f"{token} is identical in both themes"

    # Dark carries a halo on the one thing allowed to raise its voice; light
    # prints the rule heavier instead.
    assert "0 0 12px" in dark_tokens["--af-interrupt-glow"]
    assert light_tokens["--af-interrupt-glow"] == "none"
    # Light carries a cast shadow; dark uses an inset highlight instead.
    assert dark_tokens["--af-card-shadow"].startswith("inset")
    assert not light_tokens["--af-card-shadow"].startswith("inset")


def test_frontier_keeps_the_house_semantic_colour_law() -> None:
    section = _frontier_css()
    # Green is reserved for narrow verified/openable success; this section never
    # claims organizational health, so it must not reach for --ok at all.
    assert "--ok" not in section
    assert "var(--brass)" in section
    assert "var(--slate)" in section
    assert "var(--danger)" in section
    # No parallel palette: only tokens, never raw product hex.
    body = "\n".join(line for line in section.splitlines() if not line.strip().startswith("*"))
    assert "#" not in body


def test_frontier_is_responsive_at_every_existing_breakpoint() -> None:
    styles = CSS.read_text(encoding="utf-8")
    compact = styles[styles.index("@media (max-width: 1280px)") : styles.index("@media (max-width: 1050px)")]
    dockless = styles[styles.index("@media (max-width: 1050px)") : styles.index("@media (max-width: 760px)")]
    mobile = styles[styles.index("@media (max-width: 760px)") :]

    assert ".ccr-af-card { grid-template-columns:" in compact
    assert ".ccr-af-counts { grid-template-columns:" in compact
    assert ".ccr-af-right { grid-column: 1 / -1; }" in dockless
    assert ".ccr-af-card { grid-template-columns: 1fr;" in mobile
    assert ".ccr-af-count-value { font-size: 20px; }" in mobile
    assert ".ccr-af-demand-track { grid-template-columns: 1fr; }" in mobile
    # The sixth nav section takes its own full-width row rather than leaving a
    # ragged one-of-five cell.
    assert ".ccr-nav-group .ccr-nav-link:nth-child(6) { grid-column: 1 / -1; }" in mobile

    reduced = styles[styles.index("@media (prefers-reduced-motion: reduce)") :]
    assert ".ccr-af-card { transition: none; }" in reduced[: reduced.index("}\n") + 2]


def test_frontier_copy_stays_inside_the_front_facing_vocabulary_law() -> None:
    block = _frontier_code().lower()
    # No synthesized health, ordering weight or model judgement of any kind.
    for forbidden in ("score", "health", "rank", "priority", "falsifier", "refuted", "thesis", "证伪"):
        assert forbidden not in block
    # This surface reads a projection; it never claims to have decided anything.
    for forbidden in ("we recommend", "you should", "best option", "top "):
        assert forbidden not in block


def test_frontier_javascript_parses_with_node_when_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed on this test host")
    subprocess.run([node, "--check", str(JS)], check=True, capture_output=True, text=True)

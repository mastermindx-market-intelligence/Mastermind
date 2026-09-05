"""Static product-contract tests for Chairman Control Room X1.

These tests deliberately validate the private-local presentation surface only.
They do not grant the UI lifecycle, attention, identity, or completion authority.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from control_plane import chairman_control_room_remote as remote


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static" / "chairman_control"
INDEX = STATIC / "index.html"
JS = STATIC / "control_room.js"
CSS = STATIC / "control_room.css"
REMOTE = STATIC / "remote.html"

#: Fix 5 (final adversarial review, 2026-09-01): every other test in this
#: module is a string-literal assertion against ``control_room.js``'s
#: source text — none of them would notice a stray/missing/mismatched
#: bracket, and ``test_x1_javascript_parses_with_node_when_available``
#: below skips outright on a node-less runner.  On such a runner a
#: grossly malformed ``control_room.js`` would ship green.  This is a
#: deliberately conservative, pure-Python (no ``node`` dependency)
#: structural check — NOT a JS parser — that skips over string/template
#: literals, ``//``/``/* */`` comments, and regex literals, and reports
#: whether every ``(){}[]`` nests correctly outside of them.  Regex-vs-
#: division disambiguation uses the standard heuristic: a ``/`` opens a
#: regex literal when the last significant token before it is punctuation/
#: operator-shaped (an opening bracket, comma, colon, assignment, etc.)
#: or one of a small set of keywords that can only be followed by a value
#: expression (``return``, ``typeof``, ``case``, ...); it reads as
#: ordinary division after a value-shaped token (an identifier, number,
#: ``)``, or ``]``).  Good enough to catch a grossly malformed file; not a
#: substitute for ``node --check`` when node is available, which stays the
#: stronger gate below.
_JS_REGEX_PRECURSOR_PUNCT = set("([{,;:=!&|?+-*%^~<>")
_JS_REGEX_PRECURSOR_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete",
    "void", "throw", "case", "yield", "do", "else",
}


def _js_structural_balance_ok(text: str) -> bool:
    """``True`` iff ``text``'s ``(){}[]`` nest correctly outside of
    strings/templates/comments/regex literals; ``False`` on any
    imbalance or any unterminated string/template/comment/regex."""
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    opens = set(pairs.values())
    n = len(text)
    i = 0
    last_word = ""
    last_char = ""
    while i < n:
        c = text[i]
        if c in "\"'":
            quote = c
            i += 1
            closed = False
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    closed = True
                    break
                if text[i] == "\n":
                    break
                i += 1
            if not closed:
                return False
            last_word = ""
            last_char = quote
            continue
        if c == "`":
            i += 1
            closed = False
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "`":
                    i += 1
                    closed = True
                    break
                if text[i] == "$" and i + 1 < n and text[i + 1] == "{":
                    depth = 1
                    i += 2
                    while i < n and depth > 0:
                        if text[i] == "{":
                            depth += 1
                        elif text[i] == "}":
                            depth -= 1
                        i += 1
                    continue
                i += 1
            if not closed:
                return False
            last_word = ""
            last_char = "`"
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                return False
            i = j + 2
            continue
        if c == "/":
            is_regex = (
                last_char == ""
                or last_char in _JS_REGEX_PRECURSOR_PUNCT
                or last_word in _JS_REGEX_PRECURSOR_KEYWORDS
            )
            if is_regex:
                j = i + 1
                in_class = False
                closed = False
                while j < n:
                    ch = text[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "\n":
                        break
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        j += 1
                        closed = True
                        break
                    j += 1
                if not closed:
                    return False
                while j < n and text[j].isalpha():
                    j += 1
                i = j
                last_word = ""
                last_char = "/"
                continue
            i += 1
            last_word = ""
            last_char = "/"
            continue
        if c in opens:
            stack.append(c)
            i += 1
            last_word = ""
            last_char = c
            continue
        if c in pairs:
            if not stack or stack[-1] != pairs[c]:
                return False
            stack.pop()
            i += 1
            last_word = ""
            last_char = c
            continue
        if c.isspace():
            i += 1
            continue
        if c.isalnum() or c in "_$":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            last_word = text[i:j]
            last_char = text[j - 1]
            i = j
            continue
        last_word = ""
        last_char = c
        i += 1
    return not stack


class _MarkupProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.inline_scripts = 0
        self.script_srcs: list[str | None] = []
        self.style_attrs: list[tuple[str, str]] = []
        self._script_without_src = False

    def handle_starttag(self, tag: str, attrs) -> None:
        row = dict(attrs)
        if row.get("id"):
            self.ids.append(row["id"])
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


def test_x1_command_deck_has_one_closed_static_shell() -> None:
    probe = _MarkupProbe()
    probe.feed(INDEX.read_text(encoding="utf-8"))

    required = {
        "ccr-command",
        "needs-you",
        "ccr-focus-list",
        "ccr-work-list",
        "ccr-surface-dock",
        "ccr-detail-drawer",
        "ccr-palette",
        "system",
        "discover-run",
        "bind-form",
        "refresh-builds",
    }
    assert required.issubset(set(probe.ids))
    assert len(probe.ids) == len(set(probe.ids)), "duplicate DOM ids make navigation ambiguous"
    assert probe.script_srcs == ["/static/control_room.js"]
    assert probe.inline_scripts == 0
    assert probe.style_attrs == []


def test_x1_client_stays_on_existing_local_control_room_contract() -> None:
    source = JS.read_text(encoding="utf-8")
    for endpoint in (
        "/api/state",
        "/api/open",
        "/api/discover",
        "/api/refresh-builds",
        "/api/bind",
        "/api/unbind",
    ):
        assert endpoint in source

    assert ".innerHTML" not in source
    assert "innerHTML =" not in source
    assert "document.write" not in source
    assert "eval(" not in source
    assert '"X-CCR-Token"' in source


def test_x1_focus_is_a_closed_deterministic_view_not_an_ai_priority_score() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function focusReasons(card)")
    end = source.index("function isFocus(card)", start)
    focus = source[start:end]

    assert "attention_ids" in focus
    assert "disagreements" in focus
    assert '=== "blocked"' in focus
    assert "unmet_dependencies" in focus
    assert "cardFailedJobs" in focus
    for forbidden in ("fetch(", "postJSON", "score", "priority", "rank"):
        assert forbidden not in focus


def test_x1_coordination_chain_is_attention_and_addressability_only() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function renderChain(card)")
    end = source.index("function renderMissionRow(card)", start)
    chain = source[start:end]

    assert "cardAttentionTargets(card)" in chain
    assert "card.bindings" in chain
    for forbidden in (
        "capabilities",
        "running",
        "process",
        "installed",
        "card.executive",
        "cardFailedJobs",
    ):
        assert forbidden not in chain


def test_x1_human_attention_keeps_visual_precedence_over_machine_danger() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function renderMissionRow(card)")
    end = source.index("function workMatches(card, query)", start)
    row = source[start:end]

    assert "hasHumanAttention" in row
    assert "targets.chairman || targets.ceo || targets.coo" in row
    assert "(failed || disagreements) && !hasHumanAttention" in row


def test_x1_attention_receipts_remain_forensically_reachable() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function attentionEvidenceFold(item)")
    end = source.index("// bindings", start)
    attention = source[start:end]

    assert "item.evidence" in attention
    assert "Object.keys(entry)" in attention
    assert "function renderAttentionDetail(item, target)" in attention
    assert "function openAttentionDetail(item, target, opener)" in attention
    assert 'button("Inspect"' in attention
    assert "openAttentionDetail(item, \"chairman\", inspectBtn)" in attention

    detail_start = source.index("function renderDetail(card)")
    detail_end = source.index("function openDetail(card, opener)", detail_start)
    detail = source[detail_start:detail_end]
    assert "attentionEvidenceFold(entry.item)" in detail


def test_x1_source_pulse_displays_clocks_without_inventing_freshness_sla() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function sourcePulsePill")
    end = source.index("function renderDegraded", start)
    pulse = source[start:end]

    assert "6 * 60" not in pulse
    assert "DB present" in pulse
    assert '"connected"' not in pulse


def test_x1_topbar_names_source_clocks_and_canonical_read_only_boundary() -> None:
    source = INDEX.read_text(encoding="utf-8")

    assert 'aria-label="Source clocks"' in source
    assert "Local · canonical read-only" in source
    assert 'aria-label="Source freshness"' not in source
    assert "Local · read only" not in source


def test_x1_quick_open_sol_requires_one_unambiguous_destination() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function uniqueBinding")
    end = source.index("function attentionEvidenceFold", start)
    binding = source[start:end]

    assert "rows.length === 1" in binding
    assert "return rows.length === 1 ? rows[0] : null;" in binding


def test_x1_chatgpt_binding_is_addressable_but_not_openable_before_p0b() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function bindingConfidence(binding)")
    end = source.index("function openBinding(binding", start)
    confidence = source[start:end]

    assert 'binding.provider === "chatgpt"' in confidence
    assert 'state: "UNSUPPORTED"' in confidence
    assert "openable: false" in confidence
    assert "current P0B navigation actuator is not supported" in confidence


def test_x1_palette_never_attempts_an_unsupported_surface_open() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function rebuildPaletteIndex()")
    end = source.index("function paletteSearch(query)", start)
    palette = source[start:end]

    assert "var confidence = bindingConfidence(binding)" in palette
    assert 'actionLabel: confidence.openable ? "Open" : "Inspect"' in palette
    assert "if (confidence.openable)" in palette
    assert "else if (relatedCard)" in palette


def test_x1_binding_conflicts_preserve_exact_claimant_ids() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function renderLooseEnds(doc)")
    end = source.index("// command palette", start)
    loose = source[start:end]

    assert "row.binding_ids" in loose
    assert 'claimantIds.join(", ")' in loose
    assert "claimants unknown" in loose


def test_x1_cursor_discovery_note_survives_system_projection() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function renderDiscoverResults(doc)")
    end = source.index("function updateBindFieldVisibility", start)
    discovery = source[start:end]

    assert "doc.cursor" in discovery
    assert "cursor.note" in discovery
    assert "Cursor native thread discovery is unsupported" in discovery


def test_x1_remembered_dock_collapse_cannot_reserve_hidden_responsive_space() -> None:
    source = JS.read_text(encoding="utf-8")
    start = source.index("function desktopDockVisible()")
    end = source.index('document.getElementById("discover-run")', start)
    dock = source[start:end]

    assert 'matchMedia("(max-width: 1050px)")' in dock
    assert "var activeCollapsed = collapsed && desktopDockVisible()" in dock
    assert 'classList.toggle("ccr-dock-collapsed", activeCollapsed)' in dock
    assert 'window.addEventListener("resize", applyDockState)' in dock


def test_x1_desktop_surfaces_nav_targets_the_real_dock() -> None:
    source = JS.read_text(encoding="utf-8")
    assert 'name === "surfaces" && desktopDockVisible()' in source
    assert 'dock.focus({ preventScroll: true })' in source
    assert 'window.localStorage.setItem(DOCK_KEY, "0")' in source

    markup = INDEX.read_text(encoding="utf-8")
    assert 'id="ccr-surface-dock"' in markup
    assert 'tabindex="-1"' in markup


def test_x1_drawer_and_palette_are_modal_focus_scopes_with_return() -> None:
    source = JS.read_text(encoding="utf-8")
    markup = INDEX.read_text(encoding="utf-8")
    styles = CSS.read_text(encoding="utf-8")

    assert 'id="ccr-detail-drawer" class="ccr-detail-drawer" role="dialog" aria-modal="true"' in markup
    assert 'id="ccr-palette" class="ccr-palette-wrap" role="dialog" aria-modal="true"' in markup
    assert "[hidden] { display: none !important; }" in styles
    assert "function trapFocus(event, container)" in source
    assert "LAST_DRAWER_OPENER" in source
    assert "LAST_PALETTE_OPENER" in source
    assert "restoreFocus(opener)" in source
    assert 'drawer.classList.contains("is-open")' in source


def test_x1_keeps_mastermind_semantic_palette_and_responsive_breakpoints() -> None:
    source = CSS.read_text(encoding="utf-8")
    for token in ("--brass:", "--slate:", "--danger:", "--font-mono:"):
        assert token in source
    assert ".ccr-detail-rail" in source
    assert ".ccr-chain-node.is-attention" in source
    assert ".ccr-layout.ccr-dock-collapsed" in source
    compact_desktop = source[source.index("@media (max-width: 1280px)") : source.index("@media (max-width: 1050px)")]
    assert ".ccr-source-pulse { display: none; }" in compact_desktop
    mobile = source[source.index("@media (max-width: 760px)") :]
    assert "grid-template-columns: minmax(0,1fr) auto auto" in mobile
    assert ".ccr-refresh-banner { position: static; }" in mobile
    assert ".ccr-view-section { scroll-margin-top: calc(var(--topbar) + 50px); }" in mobile
    assert '#ccr-theme::before { content: "◐"' in mobile
    assert "@media (prefers-reduced-motion: reduce)" in source


def test_x1_javascript_parses_with_node_when_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed on this test host")
    subprocess.run([node, "--check", str(JS)], check=True, capture_output=True, text=True)


def test_x1_structural_balance_check_catches_a_missing_closing_bracket() -> None:
    """Fix 5: the pure-Python check must actually fail on malformed input
    — a missing ``]`` before the statement-ending ``;``."""
    malformed = "function foo() {\n  var x = [1, 2, 3;\n}\n"
    assert _js_structural_balance_ok(malformed) is False


def test_x1_structural_balance_check_catches_an_extra_closing_brace() -> None:
    malformed = "function foo() { return 1; } }\n"
    assert _js_structural_balance_ok(malformed) is False


def test_x1_structural_balance_check_catches_an_unterminated_string() -> None:
    malformed = "var x = \"unterminated string;\nvar y = 1;\n"
    assert _js_structural_balance_ok(malformed) is False


def test_x1_structural_balance_check_passes_well_formed_code_with_regex_and_template() -> None:
    """Exercises every kind of span the check must skip over rather than
    balance-count: a regex literal containing an escaped ``/`` (would look
    unbalanced if mistaken for division/strings), a single-quoted string
    containing bare brace/bracket characters, a template literal with a
    nested ``${...}`` expression, and ordinary division (``/``) right
    after a value-shaped token, which must NOT be read as a regex."""
    well_formed = (
        "function foo(a, b) {\n"
        "  var re = /[a-z]+\\/g/;\n"
        "  var s = 'a string with { and } and [ chars';\n"
        "  var t = `template ${a + b} literal`;\n"
        "  return (a + b) / 2;\n"
        "}\n"
    )
    assert _js_structural_balance_ok(well_formed) is True


def test_x1_structural_balance_check_passes_on_the_real_control_room_js() -> None:
    """The check that actually runs regardless of whether node is
    installed — proving it agrees with node on the real, current file."""
    source = JS.read_text(encoding="utf-8")
    assert _js_structural_balance_ok(source) is True


def test_x1_structural_balance_check_does_not_depend_on_node(monkeypatch) -> None:
    """Fix 5's whole point: this must still run — and still pass on the
    real file — even where node is unavailable and the sibling node-based
    test above self-skips."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert shutil.which("node") is None  # sanity: the node test would skip here
    source = JS.read_text(encoding="utf-8")
    assert _js_structural_balance_ok(source) is True


def test_remote_shell_is_one_shared_renderer_without_local_authority() -> None:
    source = REMOTE.read_text(encoding="utf-8")
    probe = _MarkupProbe()
    probe.feed(source)

    assert '<html lang="en" data-control-room-mode="remote-read-only">' in source
    assert "Remote · read-only" in source
    assert probe.script_srcs == ["/static/control_room.js"]
    assert '/static/control_room.css' in source
    assert 'name="ccr-token"' not in source
    assert probe.inline_scripts == 0
    assert probe.style_attrs == []
    for forbidden in (
        "refresh-builds", "discover-run", "bind-form", "unbind",
        "bind-provider", "bind-locator", "ccr-surface-dock", "locator",
        "provider census",
    ):
        assert forbidden not in source.lower()


def _run_transport_harness(mode: str) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed on this test host")
    source = JS.read_text(encoding="utf-8")
    exposed = source.rsplit("})();", 1)[0] + "globalThis.__transport={getJSON:getJSON,postJSON:postJSON,remote:REMOTE_READ_ONLY};})();"
    harness = f"""
const calls = [];
global.document = {{
  documentElement: {{ getAttribute: () => {mode!r} }},
  querySelector: () => ({{ getAttribute: () => 'local-token' }}),
  addEventListener: () => null
}};
global.fetch = (path, options) => {{ calls.push({{path, options}}); return Promise.resolve({{json: () => Promise.resolve({{ok:true}})}}); }};
eval({exposed!r});
(async () => {{
  await global.__transport.getJSON('/api/state');
  let postError = null;
  try {{ await global.__transport.postJSON('/api/bind', {{x:1}}); }} catch (err) {{ postError = String(err && err.message || err); }}
  process.stdout.write(JSON.stringify({{remote:global.__transport.remote,calls,postError}}));
}})();
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    import json
    return json.loads(result.stdout)


def test_remote_transport_performs_one_credentialless_get_and_cannot_construct_post() -> None:
    result = _run_transport_harness("remote-read-only")
    assert result["remote"] is True
    assert result["calls"] == [{
        "path": "/api/state",
        "options": {"method": "GET", "credentials": "same-origin", "headers": {}},
    }]
    assert result["postError"] == "remote_read_only"


def test_local_transport_retains_token_and_post_contract() -> None:
    result = _run_transport_harness("")
    assert result["remote"] is False
    assert result["calls"][0] == {
        "path": "/api/state",
        "options": {
            "method": "GET", "credentials": "same-origin",
            "headers": {"X-CCR-Token": "local-token"},
        },
    }
    assert result["calls"][1]["path"] == "/api/bind"
    assert result["calls"][1]["options"]["method"] == "POST"
    assert result["calls"][1]["options"]["headers"] == {
        "Content-Type": "application/json", "X-CCR-Token": "local-token",
    }
    assert result["postError"] is None


def test_remote_mode_renders_remote_identity_and_freshness_without_local_fields() -> None:
    source = JS.read_text(encoding="utf-8")
    assert "REMOTE_READ_ONLY" in source
    assert "doc.source_freshness" in source
    assert "doc.code_identity" in source
    assert 'if (!REMOTE_READ_ONLY)' in source
    assert 'rel: "noopener noreferrer"' in source
    remote_branch = source[source.index("function renderEverything(body)") : source.index("function loadState()")]
    assert "doc.sources" in remote_branch  # preserved local branch
    assert "doc.source_freshness" in remote_branch
    assert "doc.bindings" not in remote_branch


def test_remote_layout_has_explicit_embed_and_narrow_viewport_rules() -> None:
    styles = CSS.read_text(encoding="utf-8")
    assert 'html[data-control-room-mode="remote-read-only"]' in styles
    assert ".ccr-remote-badge" in styles
    assert "overflow-x: hidden" in styles
    remote_rules = styles[styles.index('html[data-control-room-mode="remote-read-only"]') :]
    assert "minmax(0,1fr)" in remote_rules
    assert "@media (max-width: 760px)" in remote_rules


# --- autonomy responsibilities section ------------------------------------
#
# These pin the presentation contract of the Autonomy section only. They do not
# grant it projection, lifecycle, identity or completion authority, and they do
# not assert anything about the server-side projection module.


def _autonomy_js() -> str:
    source = JS.read_text(encoding="utf-8")
    start = source.index("  // autonomy ---")
    end = source.index("  // state ---", start)
    return source[start:end]


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
        if line.startswith("--au-") and ":" in line:
            name, _, value = line.partition(":")
            rows[name.strip()] = value.strip().rstrip(";")
    return rows


def test_x1_autonomy_has_one_mount_point_and_one_nav_entry() -> None:
    markup = INDEX.read_text(encoding="utf-8")
    probe = _MarkupProbe()
    probe.feed(markup)

    assert 'id="autonomy"' in markup
    assert 'id="ccr-autonomy"' in markup
    assert 'data-nav="autonomy"' in markup
    assert 'id="nav-autonomy-count"' in markup
    assert {"autonomy", "ccr-autonomy", "nav-autonomy-count"}.issubset(set(probe.ids))
    assert len(probe.ids) == len(set(probe.ids))
    assert probe.script_srcs == ["/static/control_room.js"]
    assert probe.style_attrs == []
    # The section is composed by the shared renderer, never by page markup.
    assert "ccr-au-row" not in markup


def test_x1_autonomy_renders_only_from_the_canonical_projection_key() -> None:
    source = JS.read_text(encoding="utf-8")
    assert "renderAutonomy(doc.autonomy)" in source

    block = _autonomy_js()
    assert "function renderAutonomy(projection)" in block
    assert 'var mount = document.getElementById("ccr-autonomy")' in block
    assert "if (!mount) return;" in block
    # The section never fabricates freshness or randomness locally, and it
    # never defines a raw transport call of its own — no section-local
    # fetch()/postJSON()/getJSON() literal, no invented Date.now()/
    # Math.random() reading. This is narrower than "never talks to the
    # server": the section's one legitimate write path (opening a binding)
    # is asserted, with its indirection traced, below.
    for forbidden in ("postJSON(", "getJSON(", "fetch(", "Date.now()", "Math.random("):
        assert forbidden not in block


def test_x1_autonomy_writes_only_through_the_audited_binding_open_never_ad_hoc() -> None:
    """The previous version of this test asserted "the section never talks
    to the server or re-derives truth" by grepping literal spellings inside
    the sliced autonomy block alone — but the section's binding-open action
    (auOwedBinding -> openBindingButton -> openBinding -> postJSON) and its
    post-open refresh (loadState -> getJSON) are all defined OUTSIDE that
    slice and reached only by name, so that assertion proved nothing about
    the real call chain. This test traces the indirection instead: the
    section calls openBindingButton by name, and openBindingButton's own
    definition (elsewhere in the file) is the only place that reaches
    postJSON/getJSON on the section's behalf."""
    source = JS.read_text(encoding="utf-8")
    block = _autonomy_js()

    # The autonomy path adds strict source context to the same provider-owned
    # endpoint. Global address-book opens retain the existing helper.
    assert "b5OwedButton(card, binding," in block
    helper = _extract_fn("b5OwedButton")
    assert 'postJSON("/api/open", { binding_id: binding.binding_id, owed_context: context })' in helper
    assert "b5OwedContext(card, binding)" in helper
    assert "loadState()" in helper
    assert 'postJSON("/api/open", { binding_id: binding.binding_id })' in _extract_fn("openBinding")


def test_x1_autonomy_absent_projection_is_source_qualified_not_an_error() -> None:
    block = _autonomy_js()
    assert "function auNotWired(mount)" in block
    assert "Not wired yet" in block
    assert "No autonomy projection was returned. Its availability and current responsibility state are unknown." in block
    assert "ccr-au-quiet" in block
    assert 'if (!STATE.autonomy) {' in block
    # The not-yet-wired branch must not borrow the degraded-source alarm.
    assert "ccr-alarm" not in block
    assert "ccr-problem" not in block

    styles = CSS.read_text(encoding="utf-8")
    quiet = styles[styles.index(".ccr-au-quiet {") : styles.index(".ccr-au-quiet-title")]
    assert "var(--au-quiet-border)" in quiet
    assert "--danger" not in quiet


def test_x1_autonomy_never_presents_a_stale_card_as_live() -> None:
    block = _autonomy_js()
    assert 'return card.actionability_reason === "stale_history" || card.freshness === "stale";' in block
    marks = block[block.index("function auMarks(card)") : block.index("function auRow(card)")]
    # LIVE is not gated on is_actionable alone.  The projection currently
    # refuses to mark a stale card actionable, but the UI must not depend on
    # a server invariant it does not itself restate: a card that reads as
    # history can never also wear the LIVE chip, whatever the server sent.
    live = marks[marks.index('chip("LIVE"') - 120 : marks.index('chip("LIVE"')]
    assert "card.is_actionable === true" in live
    assert "!auIsHistory(card)" in live
    assert 'else if (auIsHistory(card)) marks.appendChild(chip("HISTORY"' in marks
    assert 'else marks.appendChild(chip("NOT ACTIONABLE"' in marks

    row = block[block.index("function auRow(card)") : block.index("function auLedger(projection)")]
    assert 'if (auIsHistory(card)) cls += " is-history";' in row

    styles = CSS.read_text(encoding="utf-8")
    # History recedes by ink and a closed rail, never by an owed-turn stripe.
    assert ".ccr-au-row.is-history::before" in styles
    assert ".ccr-au-row.is-history .ccr-au-title { color: var(--muted)" in styles


def test_x1_autonomy_placement_not_observable_is_never_shown_as_a_capability() -> None:
    block = _autonomy_js()
    chip_fn = block[block.index("function auPlacementChip(card)") : block.index("function auMarks(card)")]
    assert 'placement.observable !== true' in chip_fn
    assert 'placement.value === "not_observable"' in chip_fn
    assert 'return chip("PLACEMENT NOT OBSERVABLE", "is-dim");' in chip_fn
    # No token is ever synthesized locally; the map only relabels a supplied value.
    assert "AU_PLACEMENT[value] || value.replace" in chip_fn

    detail = block[block.index("function renderAutonomyDetail(card)") : block.index("function openAutonomyDetail")]
    assert "Not observable from canonical sources." in detail


def test_x1_autonomy_effect_unknown_bars_retry_and_failover() -> None:
    block = _autonomy_js()
    assert 'placement.value === "EFFECT_UNKNOWN" || worker.effect_state === "effect_unknown"' in block
    assert (
        "Effect not confirmed — retry and failover are not permitted "
        "until a canonical source reads the effect."
    ) in block
    # The bar is stated in the row and again in the detail drawer.
    assert block.count("retry and failover are not permitted") == 2
    for forbidden in ("Retry", "Failover", "Force ", "Override"):
        assert forbidden not in block


def test_x1_autonomy_composition_leads_with_owed_action_not_event_volume() -> None:
    block = _autonomy_js()
    render = block[block.index("function renderAutonomy(projection)") :]
    decisions = render.index("auDecisions(STATE.autonomy, byRef)")
    ledger = render.index("auLedger(STATE.autonomy)")
    listing = render.index('el("div", { className: "ccr-au-list" })')
    gaps = render.index("auGapFold(STATE.autonomy)")
    assert decisions < ledger < listing < gaps

    ledger_fn = block[block.index("function auLedger(projection)") : block.index("function auDecisions")]
    # Sol addendum 3 (2026-09-03) moved the ledger's source: it previously
    # rendered the raw all-history `projection.owed_by_seat`, which let an
    # all-stale packet display seat counts and light the Chairman cell while
    # the reading beside it said history 40 / live 0.  The ledger is a
    # CURRENT-ACTION surface, so its turns are derived from actionable cards.
    # This assertion moved with that ruling; the ordering, seat-order and
    # reading pins around it are unchanged.
    assert "projection.responsibilities" in ledger_fn
    assert "card.is_actionable !== true" in ledger_fn
    assert 'AU_SEAT_ORDER.forEach' in ledger_fn
    for pair in ('["live", unknownCurrent ? null : liveCount]', '["history", counts.stale]', '["gated", counts.blocked]'):
        assert pair in ledger_fn
    # No synthesized health, score or ranking of the organization.
    for forbidden in ("score", "health", "rank", "priority"):
        assert forbidden not in block


def test_x1_autonomy_ledger_gated_and_declared_are_separately_rendered() -> None:
    """Fix 2 (final adversarial review, 2026-09-01): the ledger must not
    let the Chairman read "0 gated" while a declared block is visible on
    a card/unmapped row beneath it — "gated" (Steward-owned,
    ``counts.blocked``) and "declared" (Agent-OS-declared,
    ``counts.declared_blocked``) are wired as two SEPARATE reading items,
    never merged into one number."""
    block = _autonomy_js()
    ledger_fn = block[block.index("function auLedger(projection)") : block.index("function auDecisions")]
    assert '["gated", counts.blocked]' in ledger_fn
    assert '["declared", counts.declared_blocked]' in ledger_fn
    # Never merged/summed into a single combined figure.
    for forbidden in ("counts.blocked + counts.declared_blocked", "counts.declared_blocked + counts.blocked"):
        assert forbidden not in ledger_fn


def test_x1_autonomy_chairman_decision_band_names_the_reason() -> None:
    block = _autonomy_js()
    band = block[block.index("function auDecisions(projection, byRef)") : block.index("function auGapFold")]
    assert "projection.chairman_decisions" in band
    assert "card.chairman_decision_reason" in band
    assert "No Chairman decision is recorded in this projection. Check source-read issues before treating it as current." in band
    assert "This reference is not in the loaded responsibility list." in band


def test_x1_autonomy_source_loss_is_bounded_and_named() -> None:
    block = _autonomy_js()
    gaps = block[block.index("function auGapFold(projection)") : block.index("function auReceiptFold")]
    assert "projection.source_failures" in gaps
    assert "projection.issues" in gaps
    assert "row.owner" in gaps
    assert (
        "Losing a source removes detail; it never changes what the canonical "
        "sources above already recorded."
    ) in gaps
    assert "Every contributing source answered." in gaps


def test_x1_autonomy_unmapped_responsibilities_render_bounded_and_empty_safe() -> None:
    """Blast-radius repair packet, 2026-09-01: an unrecognized-owner
    workstream is surfaced inside the existing bounded "what could not be
    read" fold — never as a card, never as an alarm — with copy naming why
    it is absent and stating it does not affect anything shown above, and
    it renders nothing at all when the list is empty."""
    block = _autonomy_js()
    gaps = block[block.index("function auGapFold(projection)") : block.index("function auReceiptFold")]

    assert "projection.unmapped_responsibilities" in gaps
    assert "row.responsibility_ref" in gaps
    assert "row.reason" in gaps
    assert (
        "These workstreams are not shown as responsibility cards because "
        "their recorded owner is not a recognized seat. This does not "
        "affect any responsibility shown above."
    ) in gaps

    # Rendered only inside a guard on unmapped.length — nothing when empty.
    assert "if (unmapped.length) {" in gaps
    unmapped_block = gaps[gaps.index("if (unmapped.length) {") :]
    assert 'chip("NOT MAPPED", "is-dim")' in unmapped_block
    # Bounded, never an alarm: the unmapped rows never borrow the
    # SOURCE-FAILED danger styling used for genuine source outages above.
    assert "is-danger" not in unmapped_block
    # The raw owner value is never rendered here either.
    assert "row.owner" not in unmapped_block


def test_x1_autonomy_disagreements_keep_both_readings_and_both_owners() -> None:
    block = _autonomy_js()
    detail = block[block.index("function renderAutonomyDetail(card)") : block.index("function openAutonomyDetail")]
    assert "Source drift — both readings kept" in detail
    assert "(entry.values || []).join" in detail
    assert "(entry.sources || []).forEach" in detail
    for forbidden in ("winner", "vote", "prefer", "average"):
        assert forbidden not in block


def test_x1_autonomy_owed_action_reuses_the_existing_binding_law() -> None:
    block = _autonomy_js()
    binding = block[block.index("function auOwedBinding(card)") : block.index("function auTurnTrack(seat)")]
    assert "if (REMOTE_READ_ONLY) return null;" in binding
    assert "uniqueBinding(work, seat)" in binding
    assert "bindingConfidence(binding).openable ? binding : null" in binding
    # A responsibility with no unambiguous, openable destination offers no jump.
    assert 'if (seat === "unknown") return null;' in binding


def test_x1_autonomy_copy_stays_inside_the_front_facing_vocabulary_law() -> None:
    block = _autonomy_js().lower()
    for forbidden in ("falsifier", "refuted", "thesis", "证伪", "validated"):
        assert forbidden not in block
    assert "conditions are still being watched" in block


def test_x1_autonomy_is_designed_for_two_themes_not_one_token_swap() -> None:
    root, light = _css_theme_blocks()
    dark_tokens = _declared(root)
    light_tokens = _declared(light)

    assert dark_tokens, "the autonomy section must declare its own material tokens"
    assert set(dark_tokens) == set(light_tokens), (
        "every autonomy token needs a value in both theme blocks; a colour whose "
        "only definition lives inside one theme block is a skin, not a design"
    )

    # These are the mechanisms that must genuinely differ between the command
    # centre reading and the research workspace reading.
    for token in (
        "--au-cell-bg",
        "--au-cell-shadow",
        "--au-band-fill",
        "--au-marker-core",
        "--au-marker-ring",
        "--au-marker-glow",
        "--au-row-hover",
        "--au-body-ink",
        "--au-hold-weight",
        "--au-gate-rule",
    ):
        assert dark_tokens[token] != light_tokens[token], f"{token} is identical in both themes"

    # Dark carries a halo; light must not.
    assert "0 0 13px" in dark_tokens["--au-marker-glow"]
    assert "0 0 13px" not in light_tokens["--au-marker-glow"]
    # Light carries a cast shadow; dark uses an inset highlight instead.
    assert dark_tokens["--au-cell-shadow"].startswith("inset")
    assert not light_tokens["--au-cell-shadow"].startswith("inset")


def test_x1_autonomy_is_responsive_at_every_existing_breakpoint() -> None:
    styles = CSS.read_text(encoding="utf-8")
    compact = styles[styles.index("@media (max-width: 1280px)") : styles.index("@media (max-width: 1050px)")]
    dockless = styles[styles.index("@media (max-width: 1050px)") : styles.index("@media (max-width: 760px)")]
    mobile = styles[styles.index("@media (max-width: 760px)") :]

    assert ".ccr-au-row { grid-template-columns:" in compact
    assert ".ccr-au-right { grid-column: 1 / -1; justify-items: start; }" in dockless
    assert ".ccr-au-row { grid-template-columns: 1fr;" in mobile
    assert ".ccr-nav-group { display: grid; grid-template-columns: repeat(5,1fr); }" in mobile
    assert ".ccr-au-ledger-count { font-size: 20px; }" in mobile

    reduced = styles[styles.index("@media (prefers-reduced-motion: reduce)") :]
    assert ".ccr-au-row { transition: none; }" in reduced[: reduced.index("}\n")+2] or ".ccr-au-row { transition: none; }" in reduced[:400]


def test_x1_autonomy_keeps_the_house_semantic_colour_law() -> None:
    styles = CSS.read_text(encoding="utf-8")
    section = styles[styles.index("/* autonomy — responsibilities") : styles.index("\n/* responsive */")]
    # Green is reserved for narrow verified/openable success; the section never
    # claims organizational health, so it must not reach for --ok at all.
    assert "--ok" not in section
    assert "var(--brass)" in section
    assert "var(--slate)" in section
    assert "var(--danger)" in section
    # No parallel palette: only tokens, never raw product hex.
    body = "\n".join(line for line in section.splitlines() if not line.strip().startswith("*"))
    assert "#" not in body


def test_x1_autonomy_declared_blocker_is_rendered_and_labelled_as_agent_os() -> None:
    """``declared_blocker`` (bug-fix packet, 2026-09-01) is plain data,
    honestly Agent-OS-owned — never the Steward-owned ``blocker`` field.
    The gate area and the detail drawer must render it from its own card
    field, visibly labelled as declared by Agent OS, and it must reuse the
    house tokens (never --ok, never raw hex) rather than a parallel
    palette."""
    block = _autonomy_js()

    row = block[block.index("function auRow(card)") : block.index("function auLedger(projection)")]
    assert "card.declared_blocker" in row
    assert "auDeclaredBlockerNote" in row
    # Rendered inside the same gate area as the Steward-owned blocker, from
    # a distinct card field — never merged into `blocker`.
    assert "var blocker = card.blocker || null;" in row
    assert "gate.appendChild(auDeclaredBlockerNote(card.declared_blocker))" in row

    note_fn = block[block.index("function auDeclaredBlockerNote(declared)") : block.index("function auRow(card)")]
    assert "Agent OS declared" in note_fn
    assert "declared.target_seat" in note_fn

    detail = block[block.index("function renderAutonomyDetail(card)") : block.index("function openAutonomyDetail")]
    assert "card.declared_blocker" in detail
    assert "Agent OS declared:" in detail
    # The receipt fold shows it alongside the card's other source receipts.
    assert 'auReceiptFold("Agent OS declared blocker", [card.declared_blocker.source])' in detail

    styles = CSS.read_text(encoding="utf-8")
    assert ".ccr-au-declared {" in styles
    assert ".ccr-au-declared-label {" in styles
    section = styles[styles.index("/* autonomy — responsibilities") : styles.index("\n/* responsive */")]
    assert "--ok" not in section
    declared_rules = "\n".join(
        line for line in section.splitlines()
        if ".ccr-au-declared" in line and not line.strip().startswith("*")
    )
    assert "#" not in declared_rules


# ---------------------------------------------------------------------------
# Sol review addenda 2 + 3 (2026-09-03): the action surface shows CURRENT work
#
# On the real all-stale packet the ledger lit the Chairman cell "is-yours" and
# cards still offered an owed-action "Open" jump, both built from recorded
# history, directly beside a reading that said history 40 / live 0.
# ---------------------------------------------------------------------------


def test_addendum2_no_owed_action_jump_from_a_non_actionable_card() -> None:
    """Repair B: an owed-action Open is a present-tense instruction."""
    block = _autonomy_js()
    binding = block[block.index("function auOwedBinding(") :]
    binding = binding[: binding.index("\n  }")]

    # the actionability gate exists and precedes any destination lookup
    assert "card.is_actionable !== true" in binding
    assert binding.index("card.is_actionable !== true") < binding.index("auOwedSeat(card)")
    # the older EFFECT_UNKNOWN hold suppression is retained, not replaced
    assert "auIsHold(card)" in binding
    # Detail stays reachable for forensic inspection of stale cards
    assert 'text: "Detail"' in block or '"Detail"' in block


def test_addendum3_seat_ledger_counts_only_currently_actionable_turns() -> None:
    """Repair C: the ledger is a current-action surface, not a history tally."""
    block = _autonomy_js()
    ledger = block[block.index("function auLedger(") :]
    ledger = ledger[: ledger.index("\n  }")]

    # per-seat turns are derived from actionable cards, not raw owed_by_seat
    assert "projection.responsibilities" in ledger
    assert "card.is_actionable !== true" in ledger
    # the raw all-history map is no longer the displayed allocation
    assert "projection.owed_by_seat || {}" not in ledger
    # the urgent Chairman treatment still keys off the derived count
    assert 'seat === "chairman" && value > 0' in ledger
    # history is preserved in the reading, not erased
    assert '["history", counts.stale]' in ledger
    assert '["carried", counts.total]' in ledger


def test_addendum_turn_reason_token_matches_the_backend() -> None:
    """Repair D: the UI keyed a token the backend never emits."""
    js = JS.read_text(encoding="utf-8")
    projection = (
        ROOT / "control_plane" / "autonomy_control_room_projection.py"
    ).read_text(encoding="utf-8")

    assert '"reason": "worker_runtime_present"' in projection
    assert "worker_runtime_present:" in js
    # Dead drift removed: the map KEY is gone, so nothing silently falls
    # through to the default any more.  Both files still mention the old
    # spelling in prose that explains why it was wrong, which is exactly the
    # kind of note that stops the drift being reintroduced — so this asserts
    # on the code, not on the word appearing anywhere in the file.
    assert "worker_runtime_active:" not in js
    assert '"worker_runtime_active"' not in projection


# ---------------------------------------------------------------------------
# BEHAVIOURAL cover for the addendum repairs (independent review, 2026-09-03)
#
# The three addendum tests above assert on control_room.js's SOURCE TEXT, and
# that method cannot see a mutation that keeps the text and removes the
# effect.  Measured: rewriting Repair B's guard as
#     if (card.is_actionable !== true) { void 0; }
# fully restores the stale-card owed-action jump while all three still pass,
# because the substring is present and its index still precedes
# auOwedSeat(card).  These tests EXECUTE the real extracted functions under
# node against fixtures instead, so a neutered guard changes the answer and
# reddens the suite.  The source assertions are retained as the node-less
# fallback; this is the gate that actually discriminates.
# ---------------------------------------------------------------------------


def _extract_fn(name: str) -> str:
    """The real source of one top-level `function <name>(` in control_room.js."""
    js = JS.read_text(encoding="utf-8")
    start = js.index("  function %s(" % name)
    end = js.index("\n  }", start) + len("\n  }")
    return js[start:end]


def _run_node(script: str):
    node = shutil.which("node")
    if node is None:  # pragma: no cover - host-dependent
        pytest.skip("node is not installed on this host")
    proc = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    import json

    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_attention_empty_copy_is_source_qualified_when_runtime_or_inbox_is_not_current() -> None:
    """Empty Inbox arrays are not a complete operational-clear signal."""
    harness = """
    var REMOTE_READ_ONLY = false;
    %s
    %s
    console.log(JSON.stringify({
      healthy: [attentionReadState({attention:{chairman:[],ceo:[],coo:[]}, sources:{runtime_db_present:true}, degraded:[]}, {}), emptyAttentionText("current", "Clear")],
      runtime: [attentionReadState({attention:{chairman:[],ceo:[],coo:[]}, sources:{runtime_db_present:false}, degraded:[]}, {}), emptyAttentionText("runtime_unavailable", "Clear")],
      inbox: [attentionReadState({attention:{chairman:[],ceo:[],coo:[]}, sources:{runtime_db_present:true}, degraded:["executive_inbox: unavailable"]}, {}), emptyAttentionText("unavailable", "Clear")],
      refresh: [attentionReadState({attention:{chairman:[],ceo:[],coo:[]}, sources:{runtime_db_present:true}, degraded:[]}, {refresh_in_flight:true}), emptyAttentionText("unavailable", "Clear")]
    }));
    """ % (_extract_fn("attentionReadState"), _extract_fn("emptyAttentionText"))
    out = _run_node(harness)
    assert out["healthy"] == ["current", "Clear"]
    assert out["runtime"] == ["runtime_unavailable", "No recorded Inbox items. Executive runtime unavailable."]
    assert out["inbox"] == ["unavailable", "Attention unavailable — refresh canonical sources."]
    assert out["refresh"] == ["unavailable", "Attention unavailable — refresh canonical sources."]


def test_remote_attention_uses_its_published_runtime_freshness_not_local_sources() -> None:
    """A remote document has no local sources; only its closed freshness receipt decides clear copy."""
    fresh = remote.SourceFreshness("fresh", "2026-09-04T00:00:00Z", "2026-09-04T00:00:00Z", None).state
    stale = remote.SourceFreshness("stale", "2026-09-04T00:00:00Z", "2026-09-03T00:00:00Z", "over_age").state
    unavailable = remote.SourceFreshness("unavailable", "2026-09-04T00:00:00Z", None, "missing").state
    harness = """
    var REMOTE_READ_ONLY = true;
    %s
    function state(value) { return attentionReadState({
      attention:{chairman:[],ceo:[],coo:[]},
      source_freshness:{executive_runtime:{state:value}}, degraded:[]
    }, {}); }
    console.log(JSON.stringify({fresh:state(%r), stale:state(%r), unavailable:state(%r), invalidCurrent:state("current")}));
    """ % (_extract_fn("attentionReadState"), fresh, stale, unavailable)
    assert _run_node(harness) == {
        "fresh": "current", "stale": "unavailable",
        "unavailable": "unavailable", "invalidCurrent": "unavailable",
    }


def test_runtime_unavailable_nonempty_attention_stays_visible_with_a_qualification() -> None:
    """An existing row survives degraded Runtime proof and receives the actual qualifier."""
    harness = """
    var rows = [];
    rows.appendChild = function(v) { rows.push(v); };
    function el(tag, opts) {
      var node = {tag:tag, text:(opts || {}).text || "", className:(opts || {}).className || "", children:[]};
      node.appendChild = function(v) { this.children.push(v); };
      node.addEventListener = function() {};
      return node;
    }
    function clear(list) { list.length = 0; }
    var document = { querySelector:function() { return rows; } };
    function attentionSummary(item) { return item.summary; }
    function findCardForAttention() { return null; }
    function safeText(value, fallback) { return value || fallback; }
    function openAttentionDetail() {}
    %s
    %s
    renderMiniAttention("sol-attention", [{summary:"existing item", workstream:"WS:X"}], "runtime_unavailable");
    console.log(JSON.stringify(rows.map(function(row) { return {text:row.text, className:row.className, children:row.children.length}; })));
    """ % (_extract_fn("appendAttentionFreshnessNote"), _extract_fn("renderMiniAttention"))
    out = _run_node(harness)
    assert out[0]["className"] == "ccr-mini-item"
    assert out[0]["children"] == 2
    assert out[1]["text"] == "Attention may be incomplete — Executive runtime unavailable."


def test_attention_read_state_preserves_nonempty_current_attention() -> None:
    """A real non-empty Inbox remains current even while the new empty-state guard exists."""
    harness = """
    var REMOTE_READ_ONLY = false;
    %s
    console.log(JSON.stringify(attentionReadState({
      attention:{chairman:[{attention_id:"a"}],ceo:[],coo:[]},
      sources:{runtime_db_present:true}, degraded:[]
    }, {})));
    """ % _extract_fn("attentionReadState")
    assert _run_node(harness) == "current"


def test_state_refusal_or_network_failure_preserves_previous_attention_and_degraded_state() -> None:
    """A parsed 503, malformed envelope, or rejected fetch cannot replace a real prior state."""
    source = JS.read_text(encoding="utf-8")
    state_helpers = source[source.index("  var STATE_LOAD_GENERATION") : source.index("\n  function indexState")]
    load_state = source[source.index("  function readState(") : source.index("\n  function hasUsableStateEnvelope")] + _b5_transport_stubs()
    harness = """
    var STATE;
    var responses;
    var calls;
    var nav;
    var document = { getElementById:function(id) { return id === "nav-today-count" ? nav : { textContent:"" }; } };
    function getJSON() { return responses.shift(); }
    function renderEverything(body) { calls.rendered.push(body); STATE.doc = body.control_room; }
    function renderDegraded(items) { calls.degraded = items; }
    function renderNeedsYou(items, state) { calls.chairman = [items, state]; }
    function renderMiniAttention(id, items, state) { calls[id] = [items, state]; }
    function setTally(name, value) { calls.tallies[name] = value; }
    var healthy = {control_room:{
      degraded:["executive_runtime: cache unavailable"],
      attention:{chairman:[{attention_id:"chairman-existing"}], ceo:[{attention_id:"ceo-existing"}], coo:[{attention_id:"coo-existing"}]}
    }};
    function run(refusal) {
      calls = {rendered:[], tallies:{}};
      nav = {textContent:""};
      STATE = {doc:{}};
      responses = [Promise.resolve(healthy), refusal];
      return loadState().then(function() {
        return loadState();
      }).then(function() { calls.nav = nav.textContent; return calls; });
    }
    %s
    var scenarios = [
      function() { return Promise.resolve({ok:false, error:{code:"state_unavailable"}}); },
      function() { return Promise.resolve({ok:true}); },
      function() { return Promise.resolve({control_room:{}}); },
      function() { return Promise.reject(new Error("offline")); }
    ];
    var results = [];
    function next(index) {
      if (index === scenarios.length) { console.log(JSON.stringify(results)); return; }
      run(scenarios[index]()).then(function(result) { results.push(result); next(index + 1); });
    }
    next(0);
    """ % (_extract_fn("hasUsableStateEnvelope") + state_helpers + load_state)
    out = _run_node(harness)
    for result in out:
        assert result["rendered"] == [{
            "control_room": {
                "degraded": ["executive_runtime: cache unavailable"],
                "attention": {
                    "chairman": [{"attention_id": "chairman-existing"}],
                    "ceo": [{"attention_id": "ceo-existing"}],
                    "coo": [{"attention_id": "coo-existing"}],
                },
            },
        }]
        assert result["chairman"] == [[{"attention_id": "chairman-existing"}], "unavailable"]
        assert result["sol-attention"] == [[{"attention_id": "ceo-existing"}], "unavailable"]
        assert result["coo"] == [[{"attention_id": "coo-existing"}], "unavailable"]
        assert result["degraded"] == [
            "executive_runtime: cache unavailable",
            "control_room_api: unavailable — current state could not be read",
        ]
        assert result["tallies"] == {"chairman": "—", "ceo": "—", "coo": "—"}
        assert result["nav"] == "—"


def test_refresh_follow_up_reloads_once_then_cancels_or_fails_closed() -> None:
    """A stale cache gets one bounded retry chain; superseded or hung reads cannot render late."""
    source = JS.read_text(encoding="utf-8")
    helpers = source[source.index("  var STATE_LOAD_GENERATION") : source.index("\n  function indexState")]
    reader = source[source.index("  function readState(") : source.index("\n  function hasUsableStateEnvelope")] + _b5_transport_stubs()
    harness = """
    var STATE;
    var responses;
    var calls;
    var timers = [];
    var nextTimer = 1;
    function setTimeout(fn, delay) { var item = {id:nextTimer++, fn:fn, delay:delay, cancelled:false}; timers.push(item); return item.id; }
    function clearTimeout(id) { timers.forEach(function(item) { if (item.id === id) item.cancelled = true; }); }
    function runNextTimer() {
      var pending = timers.filter(function(item) { return !item.cancelled; }).sort(function(a, b) { return a.delay - b.delay; });
      if (!pending.length) throw new Error("no timer");
      pending[0].cancelled = true;
      pending[0].fn();
      return pending[0].delay;
    }
    var nav;
    var document = {getElementById:function(id) { return id === "nav-today-count" ? nav : {textContent:""}; }};
    function getJSON() { calls.gets += 1; return responses.shift(); }
    function renderEverything(body) { calls.rendered.push(body.tag); STATE.doc = body.control_room; }
    function renderDegraded(items) { calls.degraded.push(items[items.length - 1]); }
    function renderNeedsYou() {}
    function renderMiniAttention() {}
    function setTally() {}
    var refreshing = {tag:"refreshing", refresh_in_flight:true, control_room:{attention:{chairman:[],ceo:[],coo:[]}, degraded:[]}};
    var fresh = {tag:"fresh", refresh_in_flight:false, control_room:{attention:{chairman:[],ceo:[],coo:[]}, degraded:[]}};
    function reset(queue) {
      STATE = {doc:{attention:{chairman:[{attention_id:"retained"}],ceo:[],coo:[]}, degraded:[]}};
      responses = queue.slice(); calls = {gets:0, rendered:[], degraded:[]}; nav = {textContent:""}; timers = []; nextTimer = 1;
    }
    %s
    %s
    %s
    %s
    reset([Promise.resolve(refreshing), Promise.resolve(fresh)]);
    loadState().then(function() {
      var retryDelay = runNextTimer();
      return Promise.resolve().then(function() { return {complete:{gets:calls.gets, rendered:calls.rendered, retryDelay:retryDelay, pending:timers.filter(function(item){return !item.cancelled;}).length}}; });
    }).then(function(complete) {
      reset([Promise.resolve(refreshing), Promise.resolve(fresh)]);
      return loadState().then(function() {
        return loadState();
      }).then(function() { return {complete:complete.complete, superseded:{gets:calls.gets, rendered:calls.rendered, pending:timers.filter(function(item){return !item.cancelled;}).length}}; });
    }).then(function(first) {
      reset([Promise.resolve(refreshing), new Promise(function() {})]);
      return loadState().then(function() {
        runNextTimer();
        runNextTimer();
        return Promise.resolve().then(function() { return {timedOut:{gets:calls.gets, rendered:calls.rendered, degraded:calls.degraded, pending:timers.filter(function(item){return !item.cancelled;}).length}}; });
      }).then(function(second) { console.log(JSON.stringify({complete:first.complete, superseded:first.superseded, timedOut:second.timedOut})); });
    });
    """ % (helpers, reader, _extract_fn("hasUsableStateEnvelope"), "")
    out = _run_node(harness)
    assert out["complete"] == {"gets": 2, "rendered": ["refreshing", "fresh"], "retryDelay": 1000, "pending": 0}
    assert out["superseded"] == {"gets": 2, "rendered": ["refreshing", "fresh"], "pending": 0}
    assert out["timedOut"] == {
        "gets": 2, "rendered": ["refreshing"],
        "degraded": ["control_room_api: state read timed out — current state could not be read"], "pending": 0,
    }


def _deadline_clock_probe(mode: str, *, wall_offset: int = 0, consumed_at: int = 0,
                          clock: str = "valid") -> dict:
    """Run the real reader with independently controlled clocks and deferred timer delivery."""
    source = JS.read_text(encoding="utf-8")
    helpers = source[source.index("  var STATE_LOAD_GENERATION") : source.index("\n  function indexState")]
    reader = source[source.index("  function readState(") : source.index("\n  function hasUsableStateEnvelope")] + _b5_transport_stubs()
    options = json.dumps({"mode": mode, "wall_offset": wall_offset,
                          "consumed_at": consumed_at, "clock": clock})
    harness = r"""
    var options = %s;
    var elapsed = 0, wallOffset = 0, nextTimer = 1, timers = [], resolveResponse;
    var calls = {gets:0, rendered:[], degraded:[], attention:[]};
    var STATE = {doc:{attention:{chairman:[{attention_id:"retained"}],ceo:[],coo:[]}, degraded:[]}};
    var performance = {now:function() { return elapsed; }};
    if (options.clock === "missing") performance = undefined;
    if (options.clock === "invalid") performance.now = function() { return NaN; };
    if (options.clock === "throws") performance.now = function() { throw new Error("clock unavailable"); };
    Date.now = function() { return 1700000000000 + elapsed + wallOffset; };
    function setTimeout(fn, delay) {
      if (!Number.isFinite(delay) || delay < 0) throw new Error("invalid timer delay");
      var timer = {id:nextTimer++, fn:fn, due:elapsed + delay, cancelled:false};
      timers.push(timer); return timer.id;
    }
    function clearTimeout(id) { timers.forEach(function(t) { if (t.id === id) t.cancelled = true; }); }
    var document = {getElementById:function() { return {textContent:"",hidden:true}; }};
    function body(refreshing) {
      return {tag:refreshing ? "refreshing":"fresh", refresh_in_flight:refreshing,
        control_room:{attention:{chairman:[],ceo:[],coo:[]},degraded:[]}};
    }
    function getJSON() {
      calls.gets++;
      if (options.mode === "refreshing") return Promise.resolve(body(true));
      return new Promise(function(resolve) { resolveResponse = resolve; });
    }
    function renderEverything(value) { calls.rendered.push({tag:value.tag,at:elapsed}); STATE.doc = value.control_room; }
    function renderDegraded(items) { calls.degraded.push({reason:items[items.length - 1],at:elapsed}); }
    function renderNeedsYou(items, state) { calls.attention.push({ids:items.map(function(x){return x.attention_id;}),state:state}); }
    function renderMiniAttention() {} function setTally() {}
    %s
    %s
    %s
    async function drain() { for (var i = 0; i < 8; i++) await Promise.resolve(); }
    async function advanceTo(cutoff) {
      for (var steps = 0; steps < 1000; steps++) {
        var timer = timers.filter(function(t) { return !t.cancelled && t.due <= cutoff; })
          .sort(function(a,b) { return a.due - b.due || a.id - b.id; })[0];
        if (!timer) { elapsed = cutoff; await drain(); return; }
        elapsed = timer.due; timer.cancelled = true; timer.fn(); await drain();
      }
      throw new Error("unbounded timer chain");
    }
    (async function() {
      var completion = loadState();
      if (options.mode === "refreshing") {
        await completion;
        wallOffset = options.wall_offset;
        await advanceTo(250000);
      } else if (resolveResponse) {
        // Deliver the response microtask before running any overdue timer task.
        elapsed = options.consumed_at;
        if (options.clock === "lost") performance = undefined;
        resolveResponse(body(false)); await completion; await drain();
      } else {
        await completion; await drain();
      }
      console.log(JSON.stringify({calls:calls,
        pending:timers.filter(function(t){return !t.cancelled;}).length,
        active:ACTIVE_STATE_READ !== null,
        retained:STATE.doc.attention.chairman.map(function(x){return x.attention_id;})}));
    })();
    """ % (options, helpers, reader, _extract_fn("hasUsableStateEnvelope"))
    return _run_node(harness)


@pytest.mark.parametrize("wall_offset", [-600000, 600000])
def test_refresh_deadline_ignores_wall_clock_changes(wall_offset: int) -> None:
    """Mutable calendar time cannot extend or prematurely expire the elapsed read budget."""
    out = _deadline_clock_probe("refreshing", wall_offset=wall_offset)
    assert out["calls"]["gets"] == 13
    assert len(out["calls"]["degraded"]) == 1
    assert out["calls"]["degraded"][0]["at"] == 250000
    assert "timed out" in out["calls"]["degraded"][0]["reason"]
    assert out["pending"] == 0
    assert out["active"] is False


@pytest.mark.parametrize("consumed_at", [249000, 250000, 251000])
def test_state_response_must_meet_deadline_before_timer_callback(consumed_at: int) -> None:
    """A due but unprocessed timer cannot be cancelled by a late successful response."""
    out = _deadline_clock_probe("response", consumed_at=consumed_at)
    assert out["calls"]["gets"] == 1
    assert out["pending"] == 0
    assert out["active"] is False
    if consumed_at == 249000:
        assert out["calls"]["rendered"] == [{"tag": "fresh", "at": 249000}]
        assert out["calls"]["degraded"] == []
    else:
        assert out["calls"]["rendered"] == []
        assert len(out["calls"]["degraded"]) == 1
        assert "timed out" in out["calls"]["degraded"][0]["reason"]
        assert out["retained"] == ["retained"]
        assert out["calls"]["attention"] == [{"ids": ["retained"], "state": "unavailable"}]


@pytest.mark.parametrize("clock", ["missing", "invalid", "throws", "lost"])
def test_state_read_fails_closed_without_reliable_elapsed_clock(clock: str) -> None:
    """An unavailable elapsed clock cannot silently restore a wall-clock deadline."""
    out = _deadline_clock_probe("response", clock=clock, consumed_at=1000)
    assert out["calls"]["gets"] == (1 if clock == "lost" else 0)
    assert out["calls"]["rendered"] == []
    assert len(out["calls"]["degraded"]) == 1
    assert out["calls"]["attention"] == [{"ids": ["retained"], "state": "unavailable"}]
    assert out["retained"] == ["retained"]
    assert out["pending"] == 0
    assert out["active"] is False


def test_refresh_follow_up_uses_the_explicit_load_deadline_not_a_second_window() -> None:
    """An in-flight body received at 249 seconds cannot start a new 250-second follow-up budget."""
    source = JS.read_text(encoding="utf-8")
    helpers = source[source.index("  var STATE_LOAD_GENERATION") : source.index("\n  function indexState")]
    reader = source[source.index("  function readState(") : source.index("\n  function hasUsableStateEnvelope")] + _b5_transport_stubs()
    harness = """
    var STATE; var calls = {gets:0, rendered:[], degraded:[]}; var resolveInitial; var nav = {textContent:""};
    var now = 0; var timers = []; var timerId = 1;
    Date.now = function() { return now; };
    var performance = {now:function() { return now; }};
    function setTimeout(fn, delay) { var timer = {id:timerId++, fn:fn, due:now + delay, cancelled:false}; timers.push(timer); return timer.id; }
    function clearTimeout(id) { timers.forEach(function(timer) { if (timer.id === id) timer.cancelled = true; }); }
    function runNextTimer() { var timer = timers.filter(function(item){return !item.cancelled;}).sort(function(a,b){return a.due-b.due;})[0]; now = timer.due; timer.cancelled = true; timer.fn(); }
    var document = {getElementById:function(id) { return id === "nav-today-count" ? nav : {textContent:""}; }};
    function getJSON() { calls.gets += 1; return new Promise(function(resolve) { resolveInitial = resolve; }); }
    function renderEverything(body) { calls.rendered.push(body.tag); STATE.doc = body.control_room; }
    function renderDegraded(items) { calls.degraded.push(items[items.length - 1]); }
    function renderNeedsYou() {} function renderMiniAttention() {} function setTally() {}
    var refreshing = {tag:"refreshing", refresh_in_flight:true, control_room:{attention:{chairman:[],ceo:[],coo:[]}, degraded:[]}};
    %s
    %s
    %s
    STATE = {doc:{}};
    loadState();
    now = 249000;
    resolveInitial(refreshing);
    Promise.resolve().then(function() {
      runNextTimer();
      return Promise.resolve().then(function() { console.log(JSON.stringify({now:now, gets:calls.gets, rendered:calls.rendered, degraded:calls.degraded, pending:timers.filter(function(timer){return !timer.cancelled;}).length})); });
    });
    """ % (helpers, reader, _extract_fn("hasUsableStateEnvelope"))
    assert _run_node(harness) == {
        "now": 250000, "gets": 1, "rendered": ["refreshing"],
        "degraded": ["control_room_api: state read timed out — current state could not be read"], "pending": 0,
    }


def test_refresh_follow_up_refused_or_malformed_response_preserves_known_rows() -> None:
    """A terminal follow-up refusal cannot replace the prior stale composition with a false clear."""
    source = JS.read_text(encoding="utf-8")
    helpers = source[source.index("  var STATE_LOAD_GENERATION") : source.index("\n  function indexState")]
    reader = source[source.index("  function readState(") : source.index("\n  function hasUsableStateEnvelope")] + _b5_transport_stubs()
    harness = """
    var STATE; var responses; var calls; var timer; var nav;
    function setTimeout(fn, delay) { timer = {fn:fn, delay:delay, cancelled:false}; return 1; }
    function clearTimeout() { if (timer) timer.cancelled = true; }
    var document = {getElementById:function(id) { return id === "nav-today-count" ? nav : {textContent:""}; }};
    function getJSON() { return responses.shift(); }
    function renderEverything(body) { calls.rendered.push(body.tag); STATE.doc = body.control_room; }
    function renderDegraded(items) { calls.degraded = items; }
    function renderNeedsYou(items, state) { calls.chairman = [items, state]; }
    function renderMiniAttention() {}
    function setTally() {}
    var refreshing = {tag:"refreshing", refresh_in_flight:true, control_room:{attention:{chairman:[{attention_id:"retained"}],ceo:[],coo:[]}, degraded:["executive_runtime: unavailable"]}};
    function run(refusal) {
      STATE = {doc:{}}; nav = {textContent:""}; calls = {rendered:[]}; timer = null;
      responses = [Promise.resolve(refreshing), Promise.resolve(refusal)];
      return loadState().then(function() { timer.fn(); return Promise.resolve(); }).then(function() { return calls; });
    }
    %s
    %s
    %s
    run({ok:false, error:{code:"state_unavailable"}}).then(function(refused) {
      return run({control_room:{}}).then(function(malformed) { console.log(JSON.stringify({refused:refused, malformed:malformed})); });
    });
    """ % (helpers, reader, _extract_fn("hasUsableStateEnvelope"))
    out = _run_node(harness)
    for result in out.values():
        assert result["rendered"] == ["refreshing"]
        assert result["chairman"] == [[{"attention_id": "retained"}], "unavailable"]
        assert result["degraded"] == [
            "executive_runtime: unavailable",
            "control_room_api: unavailable — current state could not be read",
        ]


def test_refresh_follow_up_invalidates_late_reads_and_pagehide_uses_that_same_fence() -> None:
    """A cancelled request's late success or failure cannot overwrite the newer explicit read."""
    source = JS.read_text(encoding="utf-8")
    helpers = source[source.index("  var STATE_LOAD_GENERATION") : source.index("\n  function indexState")]
    reader = source[source.index("  function readState(") : source.index("\n  function hasUsableStateEnvelope")] + _b5_transport_stubs()
    wiring = source[source.index('document.addEventListener("DOMContentLoaded"') :]
    assert 'window.addEventListener("pagehide"' in wiring
    assert "invalidateStateReads();" in wiring
    harness = """
    var STATE; var calls; var queue; var firstResolve; var firstReject; var nav;
    var timers = []; var timerId = 1;
    function setTimeout(fn, delay) { var timer = {id:timerId++, fn:fn, delay:delay, cancelled:false}; timers.push(timer); return timer.id; }
    function clearTimeout(id) { timers.forEach(function(timer) { if (timer.id === id) timer.cancelled = true; }); }
    function AbortController() { this.signal = {}; this.abort = function() { calls.aborts += 1; }; }
    var document = {getElementById:function(id) { return id === "nav-today-count" ? nav : {textContent:""}; }};
    function getJSON() { calls.gets += 1; return queue.shift(); }
    function renderEverything(body) { calls.rendered.push(body.tag); STATE.doc = body.control_room; }
    function renderDegraded() { calls.degraded += 1; }
    function renderNeedsYou() {} function renderMiniAttention() {} function setTally() {}
    var fresh = {tag:"fresh", refresh_in_flight:false, control_room:{attention:{chairman:[],ceo:[],coo:[]}, degraded:[]}};
    function run(lateFailure) {
      STATE = {doc:{}}; nav = {textContent:""}; calls = {gets:0, aborts:0, rendered:[], degraded:0}; timers = []; timerId = 1;
      var pending = new Promise(function(resolve, reject) { firstResolve = resolve; firstReject = reject; });
      queue = [pending, Promise.resolve(fresh)];
      loadState();
      return loadState().then(function() {
        if (lateFailure) firstReject(new Error("late failure")); else firstResolve({tag:"late", refresh_in_flight:true, control_room:fresh.control_room});
        return Promise.resolve().then(function() { return {gets:calls.gets, aborts:calls.aborts, rendered:calls.rendered, degraded:calls.degraded, pending:timers.filter(function(timer){return !timer.cancelled;}).length}; });
      });
    }
    %s
    %s
    %s
    run(false).then(function(success) { return run(true).then(function(failure) { console.log(JSON.stringify({success:success, failure:failure})); }); });
    """ % (helpers, reader, _extract_fn("hasUsableStateEnvelope"))
    out = _run_node(harness)
    assert out["success"] == {"gets": 2, "aborts": 1, "rendered": ["fresh"], "degraded": 0, "pending": 0}
    assert out["failure"] == {"gets": 2, "aborts": 1, "rendered": ["fresh"], "degraded": 0, "pending": 0}


def test_refresh_follow_up_never_polls_a_current_state_or_a_fired_cancelled_callback() -> None:
    """A normal response is one read, and a timer that fires after teardown cannot begin another."""
    source = JS.read_text(encoding="utf-8")
    helpers = source[source.index("  var STATE_LOAD_GENERATION") : source.index("\n  function indexState")]
    reader = source[source.index("  function readState(") : source.index("\n  function hasUsableStateEnvelope")] + _b5_transport_stubs()
    harness = """
    var STATE; var calls; var responses; var nav; var timers = []; var timerId = 1;
    function setTimeout(fn, delay) { var timer = {id:timerId++, fn:fn, delay:delay, cancelled:false}; timers.push(timer); return timer.id; }
    function clearTimeout(id) { timers.forEach(function(timer) { if (timer.id === id) timer.cancelled = true; }); }
    var document = {getElementById:function(id) { return id === "nav-today-count" ? nav : {textContent:""}; }};
    function getJSON() { calls.gets += 1; return responses.shift(); }
    function renderEverything(body) { calls.rendered.push(body.tag); STATE.doc = body.control_room; }
    function renderDegraded() {} function renderNeedsYou() {} function renderMiniAttention() {} function setTally() {}
    var fresh = {tag:"fresh", refresh_in_flight:false, control_room:{attention:{chairman:[],ceo:[],coo:[]}, degraded:[]}};
    var refreshing = {tag:"refreshing", refresh_in_flight:true, control_room:fresh.control_room};
    function reset(queue) { STATE = {doc:{}}; calls = {gets:0, rendered:[]}; responses = queue; nav = {textContent:""}; timers = []; timerId = 1; }
    %s
    %s
    %s
    reset([Promise.resolve(fresh)]);
    loadState().then(function() {
      var current = {gets:calls.gets, rendered:calls.rendered, timers:timers.filter(function(timer){return !timer.cancelled;}).length};
      reset([Promise.resolve(refreshing), Promise.resolve(fresh)]);
      return loadState().then(function() {
        var retry = timers.filter(function(timer){return !timer.cancelled && timer.delay === 1000;})[0];
        invalidateStateReads();
        retry.fn();
        return Promise.resolve().then(function() { console.log(JSON.stringify({current:current, cancelled:{gets:calls.gets, rendered:calls.rendered, timers:timers.filter(function(timer){return !timer.cancelled;}).length}})); });
      });
    });
    """ % (helpers, reader, _extract_fn("hasUsableStateEnvelope"))
    out = _run_node(harness)
    assert out["current"] == {"gets": 1, "rendered": ["fresh"], "timers": 0}
    assert out["cancelled"] == {"gets": 1, "rendered": ["refreshing"], "timers": 0}


def test_state_envelope_accepts_local_and_remote_success_contracts_only_when_inbox_is_complete() -> None:
    """Local success has no ok field; remote success does, and both require the actual Inbox shape."""
    harness = """
    %s
    var document = {attention:{chairman:[], ceo:[], coo:[]}};
    console.log(JSON.stringify({
      local:hasUsableStateEnvelope({control_room:document, capabilities:{}}),
      remote:hasUsableStateEnvelope({ok:true, control_room:document}),
      refusedWithDocument:hasUsableStateEnvelope({ok:false, control_room:document}),
      missingInbox:hasUsableStateEnvelope({control_room:{attention:{chairman:[], ceo:[]}}}),
      emptyDocument:hasUsableStateEnvelope({control_room:{}})
    }));
    """ % _extract_fn("hasUsableStateEnvelope")
    assert _run_node(harness) == {
        "local": True, "remote": True, "refusedWithDocument": False,
        "missingInbox": False, "emptyDocument": False,
    }


def test_addendum_behavioural_owed_binding_is_withheld_from_stale_cards() -> None:
    """Repair B, executed: a non-actionable card yields NO destination."""
    harness = """
    var REMOTE_READ_ONLY = false;
    function auIsHold(card) { return card.__hold === true; }
    function auOwedSeat(card) { return card.owed_turn.seat; }
    var STATE = { workByRef: { "WS:X": { work_ref: "WS:X" } } };
    function uniqueBinding(work, seat) { return { seat: seat, target: "dest" }; }
    function bindingConfidence(b) { return { openable: true }; }
    // AD-CR1A dispatch-consumption groundwork: none of these fixture cards
    // carry a `dispatch` field, so the real auDispatchUnsafe would also
    // return false for every one of them — this stub is behaviourally
    // equivalent, not a weakened substitute (see the dedicated
    // test_dispatch_behavioural_* tests below for the real function).
    function auDispatchUnsafe(card) { return false; }
    %s
    var stale = { responsibility_ref: "WS:X", is_actionable: false,
                  owed_turn: { seat: "sol" } };
    var live  = { responsibility_ref: "WS:X", is_actionable: true,
                  owed_turn: { seat: "sol" } };
    var hold  = { responsibility_ref: "WS:X", is_actionable: true, __hold: true,
                  owed_turn: { seat: "sol" } };
    console.log(JSON.stringify({
      stale: auOwedBinding(stale),
      live: auOwedBinding(live) ? auOwedBinding(live).seat : null,
      hold: auOwedBinding(hold)
    }));
    """ % ("function b5Allows() { return true; }\n" + _extract_fn("auOwedBinding"))
    out = _run_node(harness)

    assert out["stale"] is None, "a stale/non-actionable card must offer no owed-action jump"
    assert out["live"] == "sol", "a currently actionable card must still route"
    assert out["hold"] is None, "the pre-existing EFFECT_UNKNOWN hold suppression survives"


def test_addendum_behavioural_ledger_counts_only_actionable_turns() -> None:
    """Repair C, executed: an all-stale packet shows zero live turns."""
    harness = """
    var AU_SEAT_ORDER = ["chairman", "ceo", "coo", "worker", "unknown"];
    var AU_SEAT_SHORT = { chairman: "You", ceo: "Sol", coo: "Fable", worker: "Worker" };
    function el(tag, opts) {
      opts = opts || {};
      var node = { tag: tag, className: opts.className || "", text: opts.text || "",
                   children: [] };
      node.appendChild = function (c) { node.children.push(c); return c; };
      return node;
    }
    %s
    function cells(ledger) {
      var track = ledger.children[0], out = {};
      track.children.forEach(function (c) {
        out[c.children[1].text] = { n: c.children[0].text, yours: /is-yours/.test(c.className) };
      });
      return out;
    }
    var allStale = { counts: { actionable: 0, stale: 2, total: 2 },
      owed_by_seat: { chairman: 1, coo: 1, unknown: 0 },
      responsibilities: [
        { is_actionable: false, owed_turn: { seat: "chairman" } },
        { is_actionable: false, owed_turn: { seat: "coo" } }] };
    var mixed = { counts: { actionable: 2, stale: 1, total: 3 },
      owed_by_seat: { chairman: 5, coo: 5, unknown: 5 },
      responsibilities: [
        { is_actionable: true,  owed_turn: { seat: "chairman" } },
        { is_actionable: true,  owed_turn: { seat: "worker" } },
        { is_actionable: false, owed_turn: { seat: "coo" } }] };
    console.log(JSON.stringify({ allStale: cells(auLedger(allStale)),
                                 mixed: cells(auLedger(mixed)) }));
    """ % ("function b5Allows() { return true; }\n" + _extract_fn("auLedger"))
    out = _run_node(harness)

    # an all-stale packet: nobody owes a LIVE turn, and "You" is not urgent —
    # even though owed_by_seat records a chairman turn in history.
    stale_cells = out["allStale"]
    assert stale_cells["You"] == {"n": "0", "yours": False}
    assert all(cell["n"] == "0" for cell in stale_cells.values())

    # a mixed packet: only the actionable cards are counted, and the stale
    # coo card does NOT become a live turn.
    mixed_cells = out["mixed"]
    assert mixed_cells["You"] == {"n": "1", "yours": True}
    assert mixed_cells["Worker"]["n"] == "1"
    assert mixed_cells["Fable"]["n"] == "0", "a stale card must not count as a live turn"


def _extract_var(name: str) -> str:
    """The real source of one top-level `var NAME = {...};` in control_room.js."""
    js = JS.read_text(encoding="utf-8")
    start = js.index("  var %s = " % name)
    end = js.index("\n  };", start) + len("\n  };")
    return js[start:end]


def test_dispatch_behavioural_state_renders_visibly() -> None:
    """AD-CR1A dispatch-consumption groundwork: the state is VISIBLE — a
    chip renders naming it, using the real AU_DISPATCH/AU_DISPATCH_VARIANT
    data and the real auDispatchChip function, not a source-text guess."""
    harness = """
    function isBlank(v) { return v === null || v === undefined || v === ""; }
    function el(tag, opts) {
      opts = opts || {};
      return { tag: tag, className: opts.className || "", text: opts.text || "" };
    }
    %s
    %s
    %s
    var returned = { dispatch: { dispatch_state: "RETURNED", historical: false } };
    var unconsumed = { dispatch: { dispatch_state: "DELIVERY_UNCONSUMED", historical: false } };
    var noEvidence = {};
    console.log(JSON.stringify({
      returned: auDispatchChip(returned),
      unconsumed: auDispatchChip(unconsumed),
      noEvidence: auDispatchChip(noEvidence)
    }));
    """ % (
        _extract_fn("chip"),
        _extract_var("AU_DISPATCH") + "\n" + _extract_var("AU_DISPATCH_VARIANT"),
        _extract_fn("auDispatchChip"),
    )
    out = _run_node(harness)

    assert out["returned"]["text"] == "RETURNED — AWAITING SOL"
    assert out["returned"]["className"] == "ccr-chip is-brass"
    assert out["unconsumed"]["text"] == "DELIVERED, NEVER PICKED UP"
    assert out["unconsumed"]["className"] == "ccr-chip is-danger"
    assert out["noEvidence"] is None, "no dispatch evidence yet must render nothing, not a guess"


def test_cr1a_proof_dimensions_render_as_distinct_list_chips() -> None:
    """Runtime-root, C2 carrier, and W3C truth stay visibly distinct.

    In particular, the current protected-base C2 hold must never be flattened
    into a generic dispatch UNKNOWN chip that could hide which owner is absent.
    """
    harness = """
    function isBlank(v) { return v === null || v === undefined || v === ""; }
    function el(tag, opts) {
      opts = opts || {};
      return { tag: tag, className: opts.className || "", text: opts.text || "" };
    }
    %s
    %s
    %s
    %s
    %s
    %s
    var held = {
      runtime_root_state: "RESOLVED",
      dispatch: {
        carrier: { state: "OWNER_HELD", reason: "C2_POSITIVE_OWNER_HELD" },
        w3c: { state: "UNAVAILABLE", terminal_state: "UNAVAILABLE",
               wake_state: "UNAVAILABLE", source_receipt: null }
      }
    };
    console.log(JSON.stringify({
      root: auRuntimeRootChip(held),
      carrier: auCarrierChip(held),
      w3c: auW3cChip(held)
    }));
    """ % (
        _extract_fn("chip"),
        _extract_var("AU_RUNTIME_ROOT"),
        _extract_var("AU_CARRIER"),
        _extract_var("AU_W3C"),
        _extract_fn("auRuntimeRootChip"),
        _extract_fn("auCarrierChip") + "\n" + _extract_fn("auW3cChip"),
    )
    out = _run_node(harness)

    assert out["root"]["text"] == "ROOT RESOLVED"
    assert out["root"]["className"] == "ccr-chip is-ok"
    assert out["carrier"]["text"] == "C2 OWNER HELD"
    assert out["carrier"]["className"] == "ccr-chip is-dim"
    assert out["w3c"]["text"] == "W3C UNAVAILABLE"
    assert out["w3c"]["className"] == "ccr-chip is-dim"


def test_cr1a_detail_exposes_canonical_source_receipt_without_raw_payload() -> None:
    js = JS.read_text(encoding="utf-8")
    detail = _extract_fn("renderAutonomyDetail")

    assert 'b5Allows(card, "dispatch") ? "Dispatch proof" : "Dispatch proof as of source read"' in detail
    assert 'dispatch.w3c.source_receipt' in detail
    assert 'evidence.runtime_generation_state' in detail
    assert 'evidence.runtime_generation_before' in detail
    assert 'evidence.runtime_generation_after' in detail
    assert '"snapshot " + safeText(receipt.snapshot_digest' in detail
    assert '"terminal owner " + safeText(receipt.terminal_source_owner' in detail
    assert '"wake owner " + safeText(receipt.wake_source_owner' in detail
    assert "terminal_return_state" not in detail
    assert "EXECUTIVE_TERMINAL_RETURN_APPLIED" not in js


def test_dispatch_behavioural_unsafe_states_expose_no_open_control() -> None:
    """FROZEN SPEC UI law, proven behaviourally: 'No owed-action Open
    control may render for a stale, unacknowledged, watch-unproven,
    binding-reconciliation or effect-unknown state.' Source-text assertions
    alone are insufficient and have already failed this project once."""
    harness = """
    var REMOTE_READ_ONLY = false;
    function auIsHold(card) { return false; }
    function auOwedSeat(card) { return "worker"; }
    var STATE = { workByRef: { "WS:X": { work_ref: "WS:X" } } };
    function uniqueBinding(work, seat) { return { seat: seat, target: "dest" }; }
    function bindingConfidence(b) { return { openable: true }; }
    %s
    %s
    %s
    function mk(state, historical) {
      return { responsibility_ref: "WS:X", is_actionable: true,
               owed_turn: { seat: "worker" },
               dispatch: state ? { dispatch_state: state, historical: !!historical } : undefined };
    }
    console.log(JSON.stringify({
      safeStarted: auOwedBinding(mk("STARTED", false)) ? auOwedBinding(mk("STARTED", false)).seat : null,
      unconsumed: auOwedBinding(mk("DELIVERY_UNCONSUMED", false)),
      watchUnproven: auOwedBinding(mk("WATCH_UNPROVEN", false)),
      reconciliation: auOwedBinding(mk("RUNTIME_BINDING_RECONCILIATION_REQUIRED", false)),
      effectUnknown: auOwedBinding(mk("EFFECT_UNKNOWN", false)),
      unknown: auOwedBinding(mk("UNKNOWN", false)),
      staleReturned: auOwedBinding(mk("RETURNED", true)),
      liveReturned: auOwedBinding(mk("RETURNED", false)) ? "present" : null,
      noEvidence: auOwedBinding(mk(null)) ? "present" : null
    }));
    """ % (
        _extract_var("AU_DISPATCH_UNSAFE"),
        _extract_fn("auDispatchUnsafe"),
        "function b5Allows() { return true; }\n" + _extract_fn("auOwedBinding"),
    )
    out = _run_node(harness)

    assert out["safeStarted"] == "worker", "a safe dispatch state must not lose the existing Open control"
    assert out["unconsumed"] is None
    assert out["watchUnproven"] is None
    assert out["reconciliation"] is None
    assert out["effectUnknown"] is None
    assert out["unknown"] is None
    assert out["staleReturned"] is None, "stale (historical) evidence must suppress the Open control too"
    assert out["liveReturned"] == "present", "a fresh RETURNED card keeps its owed-action Open control"
    assert out["noEvidence"] == "present", "absent dispatch evidence must not newly suppress anything"


def _b5_core_js():
    text = JS.read_text() if hasattr(JS, "read_text") else ""
    assert "// B5 finite source permission" in text
    return text[text.index("  // B5 finite source permission"):].split("  // DOM ---", 1)[0]


def test_b5_browser_paired_elapsed_and_nonrenewable_component_bounds():
    core = _b5_core_js()
    result = _run_node(r"""
let m=1000, w=1788566400000;
const document={visibilityState:'visible'};
const performance={now:()=>m,timeOrigin:100};
Date.now=()=>w;
const STATE={};
const STATE_LOAD_GENERATION=1;
const clearTimeout=()=>{}; const setTimeout=()=>1;
""" + core + r"""
const anchor=b5Sample();
function sample(dm,dw){m=1000+dm; w=1788566400000+dw; return b5Sample();}
const a=b5Elapsed(anchor,sample(100,108),anchor);
const b=b5Elapsed(anchor,sample(100,109),anchor);
const bound={budget:1000,anchor,previous:anchor,invalid:false};
const near=b5Remaining(bound,sample(983,983));
const zero=b5Remaining(bound,sample(984,984));
const rollback=b5Remaining(bound,sample(0,0));
console.log(JSON.stringify({a,b,near,zero,rollback}));
""")
    assert result == {"a": 100, "b": None, "near": 1, "zero": 0, "rollback": None}


def _b5_transport_stubs():
    # These older tests isolate #486's transport generation/deadline. B5
    # source permission executes without stubs in the dedicated tests below.
    return "function b5Sample(){return null;} function b5Accept(){} function b5Schedule(){}"


def _b5_http_envelope(tmp_path, monkeypatch):
    # Actual mapper -> compositor -> generation cache -> authenticated HTTP.
    # The fixture provider and files belong only to this test.
    from test_chairman_control_room_server import (
        _b5_navigation_fixture, _running_server, _get, _auth_headers,
    )
    config, clock, binding = _b5_navigation_fixture(tmp_path, monkeypatch)
    providers = []
    config.open_binding_fn = lambda *a, **k: providers.append(a) or {"ok": False}
    with _running_server(config) as (_httpd, port):
        status, _, raw = _get(port, "/api/state", headers=_auth_headers(config))
    assert status == 200 and providers == []
    return json.loads(raw), binding


def _b5_behavior_script(envelope, binding):
    return r"""
let m=1000, w=1788566400000;
const document={visibilityState:'visible'};
const performance={now:()=>m,timeOrigin:100};
Date.now=()=>w;
const STATE={body:null,workByRef:{'WS:B5':{}}};
let timers=[], renders=0, posts=[], reads=0, settle;
function setTimeout(fn,delay){timers.push({fn,delay});return timers.length;}
function clearTimeout(id){if(timers[id-1])timers[id-1].cancelled=true;}
function renderAutonomy(){renders++;B5.active.forEach(e=>e.renderedCurrent=false);}
function renderAutonomyDetail(){}
function button(label,cls,fn){return {textContent:label,disabled:false,click:()=>fn({stopPropagation(){}})};}
function postJSON(url,payload){posts.push({url,payload});return new Promise(resolve=>settle=resolve);}
function loadState(){reads++;return Promise.resolve();}
const REMOTE_READ_ONLY=false;
function auIsHold(c){return c.placement_state?.value==='EFFECT_UNKNOWN';}
function auDispatchUnsafe(c){return ['EFFECT_UNKNOWN','UNKNOWN'].includes(c.dispatch?.dispatch_state);}
function auOwedSeat(c){return c.owed_turn.seat;}
function uniqueBinding(){return binding;}
function bindingConfidence(){return {openable:true};}
""" + "const original=" + json.dumps(envelope) + ";const binding=" + json.dumps(binding) + ";" + _b5_core_js() + _extract_fn("auOwedBinding") + r"""
function qualified(body){
 body.source_validity.browser_qualification={schema:'mastermind.browser_qualification.v1',boundary:'owned_test_fixture',
 profile:B5_PROFILE,time_origin:100,product:'Chrome/152.0.7977.82',revision:'d04cdb24d67b081f6cf80200ffc5233f44b61109',configuration:'b5-default-throttling-bfcache-v1'};
 return body;
}
function copy(){return JSON.parse(JSON.stringify(original));}
function accept(body){const a=b5Sample();b5Accept(body,a);STATE.body=body;STATE.doc=body.control_room;return body.control_room.autonomy.responsibilities[0];}
function advance(ms,offset=0){m+=ms;w+=ms+offset;}
function reset(){B5.bounds=new Map();B5.active=new Map();B5.publication=0;m=1000;w=1788566400000;document.visibilityState='visible';}
function allows(card){return B5_COMPONENTS.map(name=>b5Allows(card,name));}
"""


def test_b5_actual_http_to_browser_components_are_independent_and_legacy_refuses(tmp_path, monkeypatch):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    result = _run_node(_b5_behavior_script(envelope, binding) + r"""
const unchanged=JSON.stringify(original);
const legacy=allows(accept(copy()));
reset(); let body=qualified(copy());
B5_COMPONENTS.forEach((name,i)=>body.source_validity.cards[0].components[name].remaining_ms=100+i*100);
let card=accept(body);
let phases=[allows(card)], opens=[!!auOwedBinding(card)];
for(let i=0;i<4;i++){advance(i===0?84:100);phases.push(allows(card));opens.push(!!auOwedBinding(card));}
console.log(JSON.stringify({legacy,phases,opens,unchanged:unchanged===JSON.stringify(original)}));
""")
    assert result == {"legacy": [False]*4, "phases": [
        [True, True, True, True], [False, True, True, True],
        [False, False, True, True], [False, False, False, True], [False]*4],
        "opens": [True, False, False, False, False], "unchanged": True}


@pytest.mark.parametrize("component", ["decision_current", "dispatch", "owed_open_age"])
def test_b5_independent_expiry_never_suppresses_unrelated_current_component(tmp_path, monkeypatch, component):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    result = _run_node(_b5_behavior_script(envelope, binding) + "const component=" + json.dumps(component) + r""";
let body=qualified(copy());body.source_validity.cards[0].components[component].remaining_ms=100;
const card=accept(body);advance(84);
console.log(JSON.stringify({allows:allows(card),open:!!auOwedBinding(card)}));
""")
    expected = [True]*4
    expected[["card", "decision_current", "dispatch", "owed_open_age"].index(component)] = False
    assert result == {"allows": expected, "open": component == "decision_current"}


def test_b5_browser_same_proof_omission_minimum_and_new_proof_recovery(tmp_path, monkeypatch):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    result = _run_node(_b5_behavior_script(envelope, binding) + r"""
let card=accept(qualified(copy()));advance(800);
card=accept(qualified(copy()));const before=allows(card)[0];advance(168);const expired=allows(card)[0];
let missing=qualified(copy());delete missing.source_validity.cards[0].components.card;
const omitted=allows(accept(missing))[0];
let same=qualified(copy());same.source_validity.publication_seq+=1;
const repeated=allows(accept(same))[0];
let changed=qualified(copy());changed.source_validity.publication_seq+=2;
changed.source_validity.cards[0].components.card.proof_ref='b'.repeat(64);
changed.control_room.autonomy.responsibilities[0].validity.card.proof_ref='b'.repeat(64);
const recovered=allows(accept(changed))[0];
console.log(JSON.stringify({before,expired,omitted,repeated,recovered}));
""")
    assert result == {"before": True, "expired": False, "omitted": False, "repeated": False, "recovered": True}


@pytest.mark.parametrize("race", ["expiry", "hidden", "replacement", "discontinuity"])
def test_b5_owed_async_finally_cannot_restore_old_permission(tmp_path, monkeypatch, race):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    result = _run_node(_b5_behavior_script(envelope, binding) + "const race=" + json.dumps(race) + r""";
const card=accept(qualified(copy()));const btn=b5OwedButton(card,binding,'Open Sol');btn.click();
if(race==='expiry')advance(968);
if(race==='hidden'){document.visibilityState='hidden';b5Invalidate();}
if(race==='replacement')accept(qualified(copy()));
if(race==='discontinuity')advance(100,9);
settle({ok:true,verified:true});
Promise.resolve().then(()=>Promise.resolve()).then(()=>Promise.resolve()).then(()=>{
 console.log(JSON.stringify({posts:posts.length,context:posts[0].payload.owed_context.schema,disabled:btn.disabled}));
});
""")
    assert result == {"posts": 1, "context": "mastermind.owed_navigation.v1", "disabled": True}


def test_b5_expired_click_and_late_timer_cannot_actuate_or_replace_new_page(tmp_path, monkeypatch):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    result = _run_node(_b5_behavior_script(envelope, binding) + r"""
const card=accept(qualified(copy()));const btn=b5OwedButton(card,binding,'Open Sol');b5Schedule();
const oldTimer=timers[timers.length-1].fn;advance(968);btn.click();
accept(qualified(copy()));const before=renders;oldTimer();
console.log(JSON.stringify({posts:posts.length,disabled:btn.disabled,oldTimerInert:renders===before}));
""")
    assert result == {"posts": 0, "disabled": True, "oldTimerInert": True}


def _b5_owned_page_document(binding, reference, attention_stamp):
    # Match the exact owner instance held by the server fixture, even when
    # separate optional-release import probes have replaced package attributes.
    from test_chairman_control_room_server import server_mod
    ccr = server_mod.ccr
    from control_plane import surface_bindings as sb
    return ccr.compose_control_room(
        inbox={"schema": ccr.EXECUTIVE_INBOX_SCHEMA, "generated_at": attention_stamp,
               "attention": [
                   {"attention_id": "ATTENTION-B5", "kind": "decision", "target": "ceo",
                    "reason": "Review the harmless fixture", "workstream": "WS:B5"},
                   {"attention_id": "ATTENTION-DECISION", "kind": "decision", "target": "chairman",
                    "reason": "Harmless test decision only", "workstream": "WS:DECISION"}]},
        boot_packet=None, active_builds=None, bindings={"schema": sb.SCHEMA, "bindings": [binding]},
        binding_problems=(), generated_at=reference,
        runtime_jobs=[{"job_id": "JOB-"+key, "root_job_id": "JOB-"+key, "workstream": "WS:"+key}
                      for key in ("B5", "STABLE", "DECISION")],
        agent_os_state={"schema": "agent_os_state.v1", "generated_at": reference,
            "workstreams": [
                {"key": "B5", "title": "B5 expiring source", "owner": "ceo-sol", "status": "active"},
                {"key": "STABLE", "title": "Stable source control", "owner": "ceo-sol", "status": "active",
                 "blocked_by": ["Harmless stable test gate"]},
                {"key": "DECISION", "title": "Expiring Chairman decision", "owner": "chairman", "status": "active"}]},
        dispatch_evidence=[{"responsibility_ref": "WS:B5", "root_job_id": "JOB-B5",
            "runtime_root_state": "RESOLVED", "carrier_state": "OWNER_HELD", "w3c_state": "RESOLVED",
            "w3c_terminal_state": "APPLIED", "w3c_wake_state": "TARGET_ACKNOWLEDGED",
            "w3c_terminal_applied": "true", "w3c_source_observed_at": reference,
            "w3c_source_freshness": "SOURCE_EVIDENCE_TIME", "w3c_snapshot_digest": "a"*64,
            "w3c_terminal_source_owner": "executive_terminal_return", "w3c_wake_source_owner": "wake_ledger"}],
    )


@pytest.mark.parametrize("mutant", ["always_allow", "renew_same_proof", "keep_omitted", "ignore_lifecycle", "reenable_finally", "couple_decision", "ignore_dispatch"])
def test_b5_meaningful_guard_mutants_are_killed(tmp_path, monkeypatch, mutant):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    script = _b5_behavior_script(envelope, binding)
    if mutant == "always_allow":
        script = script.replace('function b5Allows(card, name) {', 'function b5Allows(card, name) { return true;', 1)
        probe = "const c=accept(qualified(copy()));advance(968);console.log(JSON.stringify(b5Allows(c,'card')));"
    elif mutant == "renew_same_proof":
        script = script.replace('if (before === null || (remaining !== null && before <= remaining)) bound = prior;', 'if (false) bound = prior;', 1)
        probe = "accept(qualified(copy()));advance(800);const c=accept(qualified(copy()));advance(168);console.log(JSON.stringify(b5Allows(c,'card')));"
    elif mutant == "keep_omitted":
        marker = 'function b5Accept(body, anchor) {'
        before, after = script.split(marker, 1)
        after = after.replace('B5.active = new Map();', '/* mutant retains active */', 1)
        script = before + marker + after
        probe = "const b=qualified(copy());const c=accept(b);delete b.source_validity.cards[0].components.card;accept(b);console.log(JSON.stringify(b5Allows(c,'card')));"
    elif mutant == "ignore_lifecycle":
        script = script.replace(_extract_fn("b5Invalidate"), 'function b5Invalidate() {}', 1)
        probe = "const c=accept(qualified(copy()));b5Invalidate();console.log(JSON.stringify(b5Allows(c,'card')));"
    elif mutant == "reenable_finally":
        script = script.replace('btn.disabled = !(epoch === B5.epoch && b5OwedContext(card, binding));', 'btn.disabled = false;', 1)
        probe = "const c=accept(qualified(copy()));const b=b5OwedButton(c,binding,'Open');b.click();advance(968);settle({ok:true});Promise.resolve().then(()=>Promise.resolve()).then(()=>Promise.resolve()).then(()=>console.log(JSON.stringify(!b.disabled)));"
    elif mutant == "couple_decision":
        script = script.replace('function b5Allows(card, name) {', 'function b5Allows(card, name) { if (name === "card" && !b5Allows(card,"decision_current")) return false;', 1)
        probe = "const b=qualified(copy());b.source_validity.cards[0].components.decision_current.remaining_ms=100;const c=accept(b);advance(84);console.log(JSON.stringify(!b5Allows(c,'card')));"
    else:
        script = script.replace(' || !b5Allows(card, "dispatch")', '', 1)
        probe = "const b=qualified(copy());b.source_validity.cards[0].components.dispatch.remaining_ms=100;const c=accept(b);advance(84);console.log(JSON.stringify(!!auOwedBinding(c)));"
    # Each otherwise executable mutant flips the dedicated safety assertion.
    # A parse error or harness crash fails this test; it is not a killed mutant.
    assert _run_node(script + probe) is True


def test_b5_clock_function_replacement_poisons_retained_permission(tmp_path, monkeypatch):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    result = _run_node(_b5_behavior_script(envelope, binding) + r"""
const card=accept(qualified(copy()));const wall=Date.now;Date.now=()=>w;
const overridden=b5Allows(card,'card');Date.now=wall;
const restored=b5Allows(card,'dispatch');
console.log(JSON.stringify({overridden,restored}));
""")
    assert result == {"overridden": False, "restored": False}


def test_b5_browser_accounting_capacity_never_evicts_to_renew(tmp_path, monkeypatch):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    result = _run_node(_b5_behavior_script(envelope, binding) + r"""
B5_MAX_PROOFS=4;accept(qualified(copy()));let b=qualified(copy());
b.source_validity.cards[0].components.card.proof_ref='b'.repeat(64);
b.control_room.autonomy.responsibilities[0].validity.card.proof_ref='b'.repeat(64);
accept(b);const c=accept(qualified(copy()));
console.log(JSON.stringify({size:B5.bounds.size,exhausted:B5.exhausted,allowed:b5Allows(c,'card')}));
""")
    assert result == {"size": 4, "exhausted": True, "allowed": False}


def _b5_actual_page_script():
    return r"""
'use strict';

/*
 * Owned B5 actual-page regression harness.
 *
 * Intended adaptation target:
 *   tests/test_chairman_control_room_ui_x1.py
 *
 * This harness is not source authority, a profile attestation service, or an
 * installed-service probe. It expects Root's owned loopback fixture server.
 * It never replaces Date.now(), performance.now(), timers, visibility, source
 * state, or the fixture server's canonical response body.
 */

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

const EXPECTED_PRODUCT = 'Chrome/152.0.7977.82';
const EXPECTED_REVISION = 'd04cdb24d67b081f6cf80200ffc5233f44b61109';
const PROFILE = 'b5.darwin-chrome-paired-v1';
const CONFIGURATION = 'b5-default-throttling-bfcache-v1';
const CHROME_DEFAULTS_TO_KEEP_ENABLED = [
  '--disable-background-timer-throttling',
  '--disable-backgrounding-occluded-windows',
  '--disable-back-forward-cache',
  '--disable-renderer-backgrounding',
];
const FORBIDDEN_PROFILE_OR_CLOCK_SWITCHES = [
  '--virtual-time-budget',
  '--deterministic-mode',
  '--run-all-compositor-stages-before-draw',
  '--profile-directory',
  '--clock-profile',
  '--b5-',
];
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 834, height: 1194 },
  { name: 'mobile', width: 390, height: 844 },
];

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error('missing required environment: ' + name);
  return value;
}

const chromeExecutable = requiredEnv('B5_CHROME_EXECUTABLE');
const playwrightModule = requiredEnv('B5_PLAYWRIGHT_MODULE');
const testUrl = new URL(requiredEnv('B5_TEST_URL'));
const artifactRoot = requiredEnv('B5_ARTIFACT_DIR');

if (testUrl.protocol !== 'http:' ||
    !['127.0.0.1', 'localhost'].includes(testUrl.hostname)) {
  throw new Error('B5_TEST_URL must be an owned loopback HTTP fixture');
}

const { chromium } = require(playwrightModule);
const runStamp = new Date().toISOString().replace(/[:.]/g, '-');
const outputDir = path.join(artifactRoot, 'b5-browser-' + runStamp);
fs.mkdirSync(outputDir, { recursive: false });

const report = {
  schema: 'mastermind.b5_browser_fixture_proof.v1',
  started_at: new Date().toISOString(),
  authority_claimed: false,
  fixture: { origin: testUrl.origin, pathname: testUrl.pathname },
  expected: {
    product: EXPECTED_PRODUCT,
    revision: EXPECTED_REVISION,
    profile: PROFILE,
    configuration: CONFIGURATION,
  },
  route_events: [],
  state_responses: [],
  screenshots: [],
  observations: {},
  lifecycle: [],
  pids: [],
  server_started_by_harness: false,
  clocks_overridden: false,
  browser_profile_switch_added: false,
  limits: [
    'Conditional Q premise is not empirically proved.',
    'BFCache is qualified only when pageshow.persisted is actually observed.',
    'Fixture state is synthetic canonical mapper/cache evidence, not installed Runtime or Business proof.',
  ],
};

let browser = null;
let context = null;
let page = null;
let sibling = null;
let launcherQualified = false;
let stateMode = 'pass';
let baselineMode = false;
let pendingRoutes = [];
let ownedPids = [];
let capFired = false;

function sha256(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

function processExists(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error && error.code === 'EPERM';
  }
}

function ownedChromeProcesses() {
  const proc = spawnSync('/bin/ps', ['-axo', 'pid=,ppid=,command='], {
    encoding: 'utf8',
    timeout: 1000,
    maxBuffer: 1024 * 1024,
  });
  if (proc.status !== 0) throw new Error('owned process census unavailable');
  const rows = proc.stdout.split('\n').map(function (line) {
    const match = line.match(/^\s*(\d+)\s+(\d+)\s+(.*)$/);
    return match && {
      pid: Number(match[1]),
      ppid: Number(match[2]),
      command: match[3],
    };
  }).filter(Boolean);
  const owned = new Set([process.pid]);
  let changed = true;
  while (changed) {
    changed = false;
    rows.forEach(function (row) {
      if (owned.has(row.ppid) && !owned.has(row.pid)) {
        owned.add(row.pid);
        changed = true;
      }
    });
  }
  return rows.filter(function (row) {
    return owned.has(row.pid) &&
      row.command.includes('/Applications/Google Chrome.app/');
  });
}

function verifyActualCommandLine(rows) {
  const root = rows.find(function (row) {
    return row.command.startsWith(chromeExecutable + ' ');
  });
  assert.ok(root, 'exact owned Chrome root process not found');

  CHROME_DEFAULTS_TO_KEEP_ENABLED.forEach(function (flag) {
    assert.equal(root.command.includes(flag), false,
      'invalidating Playwright default remained: ' + flag);
  });
  assert.equal(
    /--disable-features=[^\n]*\bBackForwardCache\b/.test(root.command),
    false,
    'BackForwardCache was disabled through --disable-features'
  );
  FORBIDDEN_PROFILE_OR_CLOCK_SWITCHES.forEach(function (flag) {
    assert.equal(root.command.includes(flag), false,
      'test-profile or clock override switch present: ' + flag);
  });
  assert.ok(root.command.includes('--headless'), 'headless configuration not bound');
  assert.ok(root.command.includes('--user-data-dir='),
    'ephemeral Playwright user-data directory not observed');
  const switchNames = root.command.split(/\s+/).filter(function (part) {
    return part.startsWith('--');
  }).map(function (part) {
    return part.split('=', 1)[0];
  }).sort();
  return {
    root_pid: root.pid,
    root_command_sha256: sha256(root.command),
    excluded_defaults_absent: true,
    profile_or_clock_switch_absent: true,
    headless: true,
    ephemeral_user_data_dir_observed: true,
    observed_switch_names: switchNames,
  };
}

function boundedError(error) {
  const value = String(error && error.message || error || 'unknown error');
  return value.replaceAll(testUrl.href, testUrl.origin + testUrl.pathname)
    .slice(0, 1200);
}

function boundedPathname(rawUrl) {
  try {
    return new URL(rawUrl).pathname;
  } catch (_error) {
    return 'invalid-url';
  }
}

async function releasePendingRoutes() {
  const rows = pendingRoutes;
  pendingRoutes = [];
  for (const row of rows) {
    try {
      await row.route.abort('failed');
    } finally {
      row.release();
    }
  }
}

async function handleRoute(route) {
  const request = route.request();
  const url = new URL(request.url());
  const event = {
    method: request.method(),
    pathname: url.pathname,
    same_origin: url.origin === testUrl.origin,
    mode: stateMode,
  };
  report.route_events.push(event);

  if (url.origin !== testUrl.origin) {
    event.result = 'ABORT_OUTSIDE_ORIGIN';
    await route.abort('blockedbyclient');
    return;
  }
  if (request.method() !== 'GET') {
    event.result = 'ABORT_NON_GET';
    await route.abort('blockedbyclient');
    return;
  }
  if (url.pathname === '/b5-inert') {
    event.result = 'INERT_DOCUMENT';
    await route.fulfill({
      status: 200,
      contentType: 'text/html; charset=utf-8',
      body: '<!doctype html><meta charset="utf-8"><title>B5 inert</title>',
    });
    return;
  }
  if (baselineMode && url.pathname.endsWith('/control_room.js')) {
    const basePath = requiredEnv('B5_BASE_JS_FILE');
    const bytes = fs.readFileSync(basePath);
    report.baseline_js_sha256 = sha256(bytes);
    await route.fulfill({status:200,contentType:'text/javascript',body:bytes});
    return;
  }
  if (url.pathname !== '/api/state') {
    event.result = 'CONTINUE_REAL_ASSET';
    await route.continue();
    return;
  }

  assert.equal(launcherQualified, true,
    'state request occurred before launcher qualification');
  if (stateMode === 'refuse') {
    event.result = 'ABORT_CONTROLLED_REFUSAL';
    await route.abort('failed');
    return;
  }
  if (stateMode === 'hang') {
    event.result = 'HOLD_CONTROLLED_HANG';
    await new Promise(function (resolve) {
      pendingRoutes.push({ route: route, release: resolve });
    });
    return;
  }

  const upstream = await route.fetch();
  const raw = await upstream.body();
  const original = JSON.parse(raw.toString('utf8'));
  const frame = request.frame();
  const timeOrigin = await frame.evaluate(function () {
    return performance.timeOrigin;
  });
  assert.equal(Number.isFinite(timeOrigin), true,
    'page performance.timeOrigin is not finite');

  const serializedBefore = JSON.stringify(original);
  assert.ok(original.source_validity, 'missing real server validity envelope');
  assert.equal(original.source_validity.browser_qualification, null);
  const qualified = JSON.parse(serializedBefore);
  qualified.source_validity.browser_qualification = {
    schema: 'mastermind.browser_qualification.v1', boundary: 'owned_test_fixture',
    profile: PROFILE, time_origin: timeOrigin, product: EXPECTED_PRODUCT,
    revision: EXPECTED_REVISION, configuration: CONFIGURATION,
  };
  const preservationCheck = JSON.parse(JSON.stringify(qualified));
  preservationCheck.source_validity.browser_qualification = null;
  assert.equal(JSON.stringify(preservationCheck), serializedBefore,
    'raw fixture envelope changed outside controlled browser qualification');

  const body = JSON.stringify(qualified);
  const headers = Object.assign({}, upstream.headers());
  delete headers['content-length'];
  delete headers['content-encoding'];
  headers['content-type'] = 'application/json; charset=utf-8';

  report.state_responses.push({
    status: upstream.status(),
    raw_sha256: sha256(raw),
    qualified_sha256: sha256(body),
    raw_bytes: raw.length,
    qualified_bytes: Buffer.byteLength(body),
    time_origin: timeOrigin,
    preserved_except_browser_qualification: true,
  });
  event.result = 'FETCH_REAL_ENVELOPE_ADD_QUALIFICATION';
  await route.fulfill({
    response: upstream,
    headers: headers,
    body: body,
  });
}

async function cardState(ref) {
  const row = page.locator('.ccr-au-row').filter({ hasText: ref }).first();
  const count = await row.count();
  if (!count) return { ref: ref, present: false };
  const text = (await row.innerText()).replace(/\s+/g, ' ').trim().slice(0, 900);
  const buttons = row.locator('button');
  const open = buttons.filter({ hasText: /^Open\b/ });
  return {
    ref: ref,
    present: true,
    text: text,
    live: await row.getByText('LIVE', { exact: true }).count() > 0,
    your_call: await row.getByText('YOUR CALL', { exact: true }).count() > 0,
    needs_current_read: /Needs a current read/i.test(text),
    open_count: await open.count(),
    enabled_open_count: await open.evaluateAll(function (nodes) {
      return nodes.filter(function (node) { return !node.disabled; }).length;
    }),
  };
}

async function compactState(label) {
  const rows = {};
  for (const ref of ['WS:B5', 'WS:STABLE', 'WS:DECISION']) {
    rows[ref] = await cardState(ref);
  }
  const bodyText = (await page.locator('body').innerText())
    .replace(/\s+/g, ' ').trim().slice(0, 1600);
  const state = {
    label: label,
    at: new Date().toISOString(),
    page_visibility: await page.evaluate(function () {
      return document.visibilityState;
    }),
    rows: rows,
    decision_needs_current_read:
      /Needs a current read/i.test(bodyText) &&
      bodyText.includes('WS:DECISION'),
  };
  report.observations[label] = state;
  return state;
}

async function screenshotPhase(phase) {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    const file = path.join(
      outputDir,
      phase + '-' + viewport.name + '-' + viewport.width + 'x' +
        viewport.height + '.png'
    );
    await page.locator('#ccr-autonomy').evaluate(node => {
      node.scrollIntoView({behavior:'instant',block:'start'});
      const center = innerWidth / 2;
      const overlays = Array.from(document.querySelectorAll('.ccr-topbar,.ccr-sidebar')).map(n=>n.getBoundingClientRect())
        .filter(r=>r.left<=center && r.right>=center && r.top>=0 && r.top<140 && r.height<160);
      const bottom = Math.max(0,...overlays.map(r=>r.bottom));
      scrollBy({top:-bottom-12,behavior:'instant'});
    });
    await page.screenshot({ path: file, fullPage: false });
    const geometry = await page.evaluate(() => ({width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
      overflow: Array.from(document.querySelectorAll('body *')).map(node => ({tag:node.tagName,cls:node.className,
        left:node.getBoundingClientRect().left,right:node.getBoundingClientRect().right})).filter(row=>row.right>innerWidth+1 || row.left < -1).slice(0,12)}));
    (report.geometry ||= []).push({phase,viewport:viewport.name,...geometry});
    report.screenshots.push({
      phase: phase,
      viewport: viewport,
      file: path.basename(file),
      sha256: sha256(fs.readFileSync(file)),
    });
  }
}

async function waitForExpiredRows(timeout) {
  await page.waitForFunction(function () {
    function row(ref) {
      return Array.from(document.querySelectorAll('.ccr-au-row')).find(
        function (node) { return node.textContent.includes(ref); }
      );
    }
    const b5 = row('WS:B5');
    const stable = row('WS:STABLE');
    const decision = row('WS:DECISION');
    if (!b5 || !stable || !decision) return false;
    return /Needs a current read/i.test(b5.textContent) &&
      Array.from(stable.querySelectorAll('span')).some(node => node.textContent === 'LIVE') &&
      /Needs a current read/i.test(decision.textContent);
  }, null, { timeout: timeout });
}

async function waitForRecoveredRows(timeout) {
  await page.waitForFunction(function () {
    function row(ref) {
      return Array.from(document.querySelectorAll('.ccr-au-row')).find(
        function (node) { return node.textContent.includes(ref); }
      );
    }
    const b5 = row('WS:B5');
    const stable = row('WS:STABLE');
    const decision = row('WS:DECISION');
    if (!b5 || !stable || !decision) return false;
    return Array.from(b5.querySelectorAll('span')).some(node => node.textContent === 'LIVE') &&
      Array.from(stable.querySelectorAll('span')).some(node => node.textContent === 'LIVE') &&
      !/Needs a current read/i.test(decision.textContent);
  }, null, { timeout: timeout });
}

async function visibilityCycle(label) {
  const priorStateRequests = report.route_events.filter(function (event) {
    return event.pathname === '/api/state';
  }).length;

  await sibling.bringToFront();
  await page.waitForFunction(function () {
    return document.visibilityState === 'hidden';
  }, null, { timeout: 2500 });
  const hidden = await compactState(label + '_hidden');
  assert.equal(hidden.page_visibility, 'hidden');

  await page.bringToFront();
  await page.waitForFunction(function () {
    return document.visibilityState === 'visible';
  }, null, { timeout: 2500 });
  const visible = await compactState(label + '_visible');

  const afterStateRequests = report.route_events.filter(function (event) {
    return event.pathname === '/api/state';
  }).length;
  report.lifecycle.push({
    kind: 'visibility_cycle',
    label: label,
    hidden_observed: true,
    visible_observed: true,
    state_requests_during_cycle: afterStateRequests - priorStateRequests,
  });
  return {
    visible: visible,
    state_requests: afterStateRequests - priorStateRequests,
  };
}

async function bfcacheCycle() {
  await page.goto(new URL('/b5-inert', testUrl).toString(), {
    waitUntil: 'domcontentloaded',
    timeout: 5000,
  });
  await page.goBack({ waitUntil: 'commit', timeout: 5000 });
  await page.waitForSelector('.ccr-au-row', { timeout: 5000 });

  const events = await page.evaluate(function () {
    try {
      return JSON.parse(sessionStorage.getItem('__b5Lifecycle') || '[]');
    } catch (_error) {
      return [];
    }
  });
  const persisted = events.some(function (event) {
    return event.type === 'pageshow' && event.persisted === true;
  });
  const pagehideObserved = events.some(function (event) {
    return event.type === 'pagehide';
  });
  const pageshowObserved = events.some(function (event) {
    return event.type === 'pageshow';
  });
  assert.equal(pagehideObserved, true, 'actual pagehide was not observed');
  assert.equal(pageshowObserved, true, 'actual pageshow was not observed');
  const returned = await compactState('navigation_return');
  if (persisted) {
    for (const ref of ['WS:B5','WS:STABLE','WS:DECISION']) {
      assert.equal(returned.rows[ref].live, false, 'BFCache must withdraw retained current cues');
      assert.equal(returned.rows[ref].enabled_open_count, 0, 'BFCache must withdraw retained navigation');
    }
  }
  report.lifecycle.push({
    kind: 'navigation_back',
    pagehide_observed: pagehideObserved,
    pageshow_observed: pageshowObserved,
    bfcache_persisted_observed: persisted,
    qualification: persisted ? 'BFCACHE_OBSERVED' : 'BFCACHE_NOT_OBSERVED',
  });
}

async function main() {
  const cap = setTimeout(function () {
    capFired = true;
    if (browser) void browser.close();
  }, 38000);

  try {
    browser = await chromium.launch({
      executablePath: chromeExecutable,
      headless: true,
      timeout: 10000,
      ignoreDefaultArgs: CHROME_DEFAULTS_TO_KEEP_ENABLED,
      args: [
        '--disable-background-networking',
        '--disable-component-update',
        '--disable-sync',
        '--disable-default-apps',
        '--no-first-run',
        '--no-default-browser-check',
        '--no-proxy-server',
      ],
    });

    const cdp = await browser.newBrowserCDPSession();
    const version = await cdp.send('Browser.getVersion');
    assert.equal(version.product, EXPECTED_PRODUCT);
    assert.equal(
      String(version.revision).replace(/^@/, ''),
      EXPECTED_REVISION
    );

    const processes = ownedChromeProcesses();
    assert.ok(processes.length > 0, 'no owned Chrome descendants');
    ownedPids = Array.from(new Set(processes.map(function (row) {
      return row.pid;
    })));
    report.pids = ownedPids;
    report.browser = version;
    report.launch = verifyActualCommandLine(processes);
    launcherQualified = true;
    await cdp.detach();

    context = await browser.newContext({
      serviceWorkers: 'block',
      viewport: { width: 1440, height: 900 },
    });
    await context.addInitScript(function () {
      function appendLifecycle(type, event) {
        let rows = [];
        try {
          rows = JSON.parse(sessionStorage.getItem('__b5Lifecycle') || '[]');
        } catch (_error) {}
        rows.push({
          type: type,
          persisted: !!(event && event.persisted),
          visibility: document.visibilityState,
        });
        sessionStorage.setItem('__b5Lifecycle', JSON.stringify(rows.slice(-20)));
      }
      window.addEventListener('pagehide', function (event) {
        appendLifecycle('pagehide', event);
      });
      window.addEventListener('pageshow', function (event) {
        appendLifecycle('pageshow', event);
      });
      document.addEventListener('visibilitychange', function () {
        appendLifecycle('visibilitychange', null);
      });
    });
    await context.route('**/*', handleRoute);
    page = await context.newPage();
    page.setDefaultTimeout(4000);
    page.on("pageerror", error => { (report.page_errors ||= []).push(boundedError(error)); });
    page.on('response', response => {
      const pathname = boundedPathname(response.url());
      if (!baselineMode && (pathname.endsWith('.js') || pathname.endsWith('.css'))) {
        response.body().then(bytes => { (report.assets ||= []).push({pathname,sha256:sha256(bytes)}); }).catch(()=>{});
      }
    });
    sibling = await context.newPage();
    sibling.setDefaultTimeout(4000);
    await sibling.goto(new URL('/b5-inert', testUrl).toString(), {
      waitUntil: 'domcontentloaded',
      timeout: 5000,
    });

    await page.bringToFront();
    await page.goto(testUrl.toString(), {
      waitUntil: 'domcontentloaded',
      timeout: 7000,
    });
    assert.equal(await page.evaluate(function () {
      return document.visibilityState;
    }), 'visible', 'Chairman page did not start visible');
    await page.waitForSelector('.ccr-au-row', { timeout: 5000 });
    const initial = await compactState('initial');
    assert.equal(initial.rows['WS:B5'].live, true);
    assert.equal(initial.rows['WS:STABLE'].live, true);
    assert.equal(initial.rows['WS:DECISION'].present, true);
    assert.equal(initial.rows['WS:DECISION'].your_call, true);
    await screenshotPhase('initial');


    await waitForExpiredRows(16000);
    const expired = await compactState('expired');
    assert.equal(expired.rows['WS:B5'].live, false);
    assert.equal(expired.rows['WS:B5'].enabled_open_count, 0);
    assert.equal(expired.rows['WS:STABLE'].live, true);
    assert.equal(expired.rows['WS:DECISION'].your_call, false);
    await screenshotPhase('expired');

    stateMode = 'refuse';
    await page.locator('#ccr-autonomy-read').click();
    await page.waitForFunction(() => document.body.textContent.includes('current state could not be read'));
    const refused = await compactState('refused');
    assert.equal(refused.rows['WS:B5'].live, false);
    assert.equal(refused.rows['WS:STABLE'].live, true);
    await screenshotPhase('refused');

    stateMode = 'hang';
    await page.locator('#ccr-autonomy-read').click();
    await new Promise(resolve => setTimeout(resolve, 200));
    assert.equal(pendingRoutes.length, 1, 'no actual held state request');
    const hanging = await compactState('hanging_pending');
    assert.equal(hanging.rows['WS:B5'].live, false);
    assert.equal(hanging.rows['WS:STABLE'].live, true);
    await releasePendingRoutes();
    stateMode = 'pass';
    const harnessAge = Date.now() - Date.parse(report.started_at);
    if (harnessAge < 16000) {
      await new Promise(function (resolve) {
        setTimeout(resolve, 16000 - harnessAge);
      });
    }
    await page.locator('#ccr-autonomy-read').click();
    await waitForRecoveredRows(7000);
    const recovered = await compactState('recovered');
    assert.equal(recovered.rows['WS:B5'].live, true);
    assert.equal(recovered.rows['WS:STABLE'].live, true);
    assert.equal(recovered.rows['WS:DECISION'].your_call, true);
    await screenshotPhase('recovered');

    // Natural expiry and transport retention above do not invalidate the
    // stable clock domain. Lifecycle uncertainty below deliberately does.
    try {
      const cycle = await visibilityCycle('post_recovery');
      assert.equal(cycle.state_requests, 1, 'visible resume must issue one bounded read');
    } catch (error) {
      if (!String(error).includes('Timeout')) throw error;
      report.lifecycle.push({kind:'visibility_cycle',qualification:'VISIBILITY_NOT_OBSERVED',error:boundedError(error)});
      await page.bringToFront();
    }
    await bfcacheCycle();
    assert.deepEqual(report.page_errors || [], []);
    if (process.env.B5_BASE_JS_FILE) {
      baselineMode = true;
      await page.reload({waitUntil:'domcontentloaded',timeout:5000});
      await page.waitForSelector('.ccr-au-row');
      await screenshotPhase('immutable-base-geometry');
      report.baseline_comparison = 'READ_ONLY_GEOMETRY_ONLY_NOT_B5_PROOF';
    }

    assert.equal(
      report.route_events.filter(function (event) {
        return event.method === 'POST';
      }).length,
      0,
      'a POST escaped the read-only harness'
    );
    assert.equal(
      report.route_events.filter(function (event) {
        return event.same_origin === false;
      }).length,
      0,
      'the page attempted an outside-origin request'
    );

    report.status =
      'PROFILE_CONFIGURATION_MATCH_OBSERVABLE_CAPABILITY_PASS_CONDITIONAL_Q_PREMISE_UNPROVEN';
  } catch (error) {
    report.status = 'UNQUALIFIED_HARNESS_FAILURE';
    report.error = boundedError(error);
    if (page && !page.isClosed()) { try { await compactState('failure'); } catch (_) {} }
    process.exitCode = 1;
  } finally {
    clearTimeout(cap);
    try { ownedPids = Array.from(new Set(ownedPids.concat(ownedChromeProcesses().map(row => row.pid)))); } catch (_) {}
    await releasePendingRoutes().catch(function () {});
    if (sibling) await sibling.close().catch(function () {});
    if (page) await page.close().catch(function () {});
    if (context) await context.close().catch(function () {});
    if (browser) await browser.close().catch(function () {});
    await new Promise(function (resolve) { setTimeout(resolve, 250); });

    report.cap_fired = capFired;
    report.cleanup = {
      browser_disconnected: !browser || !browser.isConnected(),
      owned_pids_remaining: ownedPids.filter(processExists),
      fixture_server_started_or_stopped_by_harness: false,
      named_user_profile_used: false,
      ephemeral_playwright_profile_used: browser !== null,
    };
    if (capFired ||
        !report.cleanup.browser_disconnected ||
        report.cleanup.owned_pids_remaining.length) {
      report.status = 'UNQUALIFIED_CLEANUP_OR_TIME_BOUND';
      process.exitCode = 2;
    }
    report.finished_at = new Date().toISOString();
    const destination = path.join(outputDir, 'result.json');
    fs.writeFileSync(destination, JSON.stringify(report, null, 2) + '\n');
    process.stdout.write(JSON.stringify({
      status: report.status,
      output_dir: outputDir,
      result_sha256: sha256(fs.readFileSync(destination)),
      screenshots: report.screenshots.length,
      state_responses: report.state_responses.length,
      cleanup: report.cleanup,
    }) + '\n');
  }
}

void main();

"""


def test_b5_actual_page_chrome152_profile_and_lifecycle(tmp_path, monkeypatch):
    import os
    import signal
    import socket
    import sys
    import threading
    import time
    from datetime import datetime, timedelta, timezone
    from test_chairman_control_room_server import _make_config, _running_server
    from control_plane import surface_bindings as sb
    from scripts import chairman_control_room as server

    strict = os.environ.get("B5_REQUIRE_CHROME_PROFILE") == "1"
    chrome = os.environ.get("B5_CHROME_EXECUTABLE")
    playwright = os.environ.get("B5_PLAYWRIGHT_MODULE")
    node = shutil.which("node")
    supported = bool(sys.platform == "darwin" and chrome and Path(chrome).is_file() and
                     playwright and Path(playwright).is_dir() and node and server._source_clock_sample())
    if not supported:
        if strict: pytest.fail("Required B5 Darwin/Chrome152 fixture profile unavailable")
        pytest.skip("B5 actual browser profile unqualified on this host; deterministic tests are separate")
    started = time.monotonic()
    artifact_dir = Path(os.environ.get("B5_ARTIFACT_DIR", str(tmp_path)))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    config = _make_config(tmp_path)
    config.static_dir = STATIC
    config.now_fn = server._utc_now_z
    config.validity_sample_fn = server._source_clock_sample
    config.state_cache["capabilities"] = {"cursor_agent": {"state": "SUPPORTED", "detail": "owned fake provider only"}}
    providers = []
    config.open_binding_fn = lambda *a, **k: providers.append(a) or {"ok": False, "verified": False}
    initial = datetime.now(timezone.utc)
    old_attention = (initial - timedelta(hours=48) + timedelta(seconds=12)).isoformat()
    binding = sb.new_binding(work_ref="WS:B5", role="ceo", provider="cursor_agent",
        locator_kind="cursor_agent_thread", locator={"chat_id": "b5-owned-fake-only", "workspace_dir": None},
        observed_at=initial.isoformat().replace("+00:00", "Z"), last_verified_at=None,
        binding_id="55555555-5555-4555-8555-555555555555")
    sb.save_bindings({"schema": sb.SCHEMA, "bindings": [binding]}, config.bindings_path)
    before_binding = config.bindings_path.read_bytes()
    phase = {"recovered": False, "gathers": 0}
    def compose(*args, **kwargs):
        phase["gathers"] += 1
        stamp = server._utc_now_z()
        return _b5_owned_page_document(binding, stamp, stamp if phase["recovered"] else old_attention)
    monkeypatch.setattr(server, "_compose_state_doc", compose)
    script = tmp_path / "b5-owned-page.cjs"
    script.write_text(_b5_actual_page_script())
    timer = None
    process = None
    outcome = None
    return_code = None
    error_text = ""
    with _running_server(config) as (httpd, port):
        def publish_fresh():
            phase["recovered"] = True
            server._refresh_state_cache(config, timeout=1, generation=server._reserve_composition(config),
                                        include_capabilities=False)
        timer = threading.Timer(15, publish_fresh)
        timer.start()
        try:
            process = subprocess.Popen([node, str(script)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, env=dict(os.environ, B5_CHROME_EXECUTABLE=chrome,
                B5_PLAYWRIGHT_MODULE=playwright, B5_TEST_URL=f"http://127.0.0.1:{port}/",
                B5_ARTIFACT_DIR=str(artifact_dir)))
            stdout, stderr = process.communicate(timeout=max(1, 42 - (time.monotonic()-started)))
            rows = [line for line in stdout.splitlines() if line.startswith("{")]
            assert rows, stderr[-2000:]
            outcome = json.loads(rows[-1])
            return_code = process.returncode
            error_text = stderr[-2000:]
        finally:
            timer.cancel()
            timer.join(timeout=2)
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try: process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=1)
    cleanup = {"server_closed": httpd.fileno() == -1, "timer_alive": timer.is_alive(),
               "provider_calls": len(providers), "binding_bytes_unchanged": config.bindings_path.read_bytes() == before_binding,
               "gathers": phase["gathers"], "elapsed_seconds": time.monotonic()-started,
               "python": sys.version, "platform": sys.platform,
               "clock_resolution": time.clock_getres(time.CLOCK_MONOTONIC_RAW)}
    if outcome:
        (Path(outcome["output_dir"]) / "fixture-cleanup.json").write_text(json.dumps(cleanup, indent=2))
    assert cleanup["server_closed"] and not cleanup["timer_alive"]
    assert cleanup["provider_calls"] == 0 and cleanup["binding_bytes_unchanged"]
    assert cleanup["elapsed_seconds"] < 45
    assert return_code == 0, {"outcome": outcome, "stderr": error_text}
    assert cleanup["gathers"] == 2


def test_b5_expired_decision_copy_retains_recorded_demand(tmp_path, monkeypatch):
    _, binding = _b5_http_envelope(tmp_path, monkeypatch)
    doc = _b5_owned_page_document(binding, "2026-09-05T00:00:00Z", "2026-09-03T00:00:12Z")
    assert doc["autonomy"]["chairman_decisions"] == ["WS:DECISION"]
    harness = r"""
function el(tag,opts={}){return {text:opts.text||'',children:[],appendChild(c){this.children.push(c);}};}
function button(label){return el('button',{text:label});}
function b5Allows(){return false;}
function safeText(value,fallback){return value||fallback;}
""" + _extract_fn("auDecisions") + "const projection=" + json.dumps(doc["autonomy"]) + r""";
const byRef=Object.fromEntries(projection.responsibilities.map(c=>[c.responsibility_ref,c]));
const band=auDecisions(projection,byRef);
function words(n){return n.text+' '+n.children.map(words).join(' ');}
console.log(JSON.stringify(words(band)));
"""
    text = _run_node(harness)
    assert "No Chairman decision is recorded" not in text
    assert "Current decision count is unknown" in text
    assert "Recorded decisions need a current read" in text


def test_b5_post_render_clock_failure_repaints_before_timer_is_lost(tmp_path, monkeypatch):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    result = _run_node(_b5_behavior_script(envelope, binding) + r"""
const c=accept(qualified(copy()));b5Allows(c,'card');Date.now=()=>w;
b5Schedule();console.log(JSON.stringify({renders,active:B5.active.size,pending:timers.filter(t=>!t.cancelled).length}));
""")
    assert result == {"renders": 1, "active": 0, "pending": 0}


@pytest.mark.parametrize("event", ["hidden", "pagehide", "freeze"])
def test_b5_actual_lifecycle_wiring_withdraws_and_bounds_resume_read(tmp_path, monkeypatch, event):
    envelope, binding = _b5_http_envelope(tmp_path, monkeypatch)
    source = JS.read_text()
    wiring = source.split('document.addEventListener("DOMContentLoaded", function () {', 1)[1].split('    var dock =', 1)[0]
    result = _run_node(_b5_behavior_script(envelope, binding) + r"""
const window={events:{},addEventListener(name,fn){this.events[name]=fn;}};
document.events={};document.addEventListener=(name,fn)=>document.events[name]=fn;
let ACTIVE_STATE_READ=null, invalidations=0;
function invalidateStateReads(){invalidations++;ACTIVE_STATE_READ=null;}
function applyTheme(){} function readTheme(){}
loadState=function(){reads++;ACTIVE_STATE_READ={};return Promise.resolve();};
""" + wiring + "const event=" + json.dumps(event) + r""";
reads=0;ACTIVE_STATE_READ=null;const card=accept(qualified(copy()));const btn=b5OwedButton(card,binding,'Open');
if(event==='hidden'){document.visibilityState='hidden';document.events.visibilitychange();}
if(event==='pagehide')window.events.pagehide({persisted:true});
if(event==='freeze')document.events.freeze();
const withdrawn=allows(card);document.visibilityState='visible';document.events.visibilitychange();
window.events.pageshow({persisted:true});btn.click();
console.log(JSON.stringify({withdrawn,reads,invalidations,posts:posts.length}));
""")
    assert result == {"withdrawn": [False]*4, "reads": 1, "invalidations": 1, "posts": 0}

"""Static product-contract tests for Chairman Control Room X1.

These tests deliberately validate the private-local presentation surface only.
They do not grant the UI lifecycle, attention, identity, or completion authority.
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

    # The section's only write-capable call site.
    assert "openBindingButton(binding," in block

    helper_start = source.index("function openBindingButton(binding, label)")
    helper_end = source.index("function allBindings()")
    helper = source[helper_start:helper_end]
    assert "openBinding(binding, null, btn)" in helper
    assert "loadState()" in helper

    open_start = source.index("function openBinding(binding")
    open_end = source.index("function openBindingButton")
    open_fn = source[open_start:open_end]
    assert 'postJSON("/api/open"' in open_fn


def test_x1_autonomy_absent_projection_is_calm_and_truthful_not_an_error() -> None:
    block = _autonomy_js()
    assert "function auNotWired(mount)" in block
    assert "Not wired yet" in block
    assert "Nothing is hidden and nothing has failed" in block
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
    for pair in ('["live", counts.actionable]', '["history", counts.stale]', '["gated", counts.blocked]'):
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
    assert "Nothing here needs your decision." in band
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
    """ % _extract_fn("auOwedBinding")
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
    """ % _extract_fn("auLedger")
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

    assert 'detailRail(rails, "Dispatch proof"' in detail
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
        _extract_fn("auOwedBinding"),
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

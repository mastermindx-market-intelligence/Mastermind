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

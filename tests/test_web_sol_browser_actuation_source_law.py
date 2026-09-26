from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT / "docs" / "EXECUTIVE_BROWSER_ACTUATION_LAW.md"
DESIGN = ROOT / "docs" / "superpowers" / "specs" / "2026-09-04-web-sol-browser-actuation-fabric-design.md"
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-09-04-web-sol-browser-actuation-fabric.md"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing BRA source record: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def test_bra_source_records_exist_and_remain_production_inert():
    for path in (LAW, DESIGN, PLAN):
        text = _text(path)
        assert "PRODUCTION_INERT" in text
        assert "WS:CHAIRMAN-CONTROL-ROOM" in text


def test_bra_preserves_canonical_authority_and_no_duplicate_control_plane():
    law = _text(LAW)
    required = (
        "Executive OS owns Job / Attempt / Worker / Event lifecycle",
        "RuntimeBinding / SessionTarget owners determine exact actionable runtime targets",
        "Agent OS owns durable organizational workstreams",
        "Secure MCP Tunnel, when used, is transport only",
        "second lifecycle",
        "browser-session authority",
    )
    for phrase in required:
        assert phrase in law


def test_bra_keeps_chatgpt_semantics_out_of_generic_browser_tools():
    law = _text(LAW)
    assert "mastermind.web_sol_surface_action.v1" in law
    assert "INSPECT | FOREGROUND" in law
    assert "mastermind.browser_actuation.v1" in law
    assert "mastermind.web_sol_semantic_action.v2+" in law
    assert "A generic browser primitive is never authority-equivalent to a semantic Web-Sol action." in law
    assert "Generic browser actuation must not be used to smuggle ChatGPT prompt submission" in law


def test_bra_effect_unknown_is_sticky_and_non_retryable():
    law = _text(LAW)
    assert "EFFECT_UNKNOWN" in law
    assert "blocks blind retry" in law
    assert "blocks target/session/account failover" in law
    assert "permits read-only reconciliation only" in law


def test_bra_refuses_ui_heuristic_target_selection():
    law = _text(LAW)
    for phrase in (
        "newest or most recently active tab",
        "browser/window order",
        "title similarity",
        "visible model output",
        "model-selected account/profile/project",
    ):
        assert phrase in law


def test_bra_secret_boundary_forbids_browser_credential_extraction():
    law = _text(LAW)
    for phrase in (
        "cookies or storage values",
        "auth/session/OAuth tokens",
        "password-manager values",
        "raw browser profile contents",
        "private provider network payloads",
        "bulk ChatGPT transcripts/model outputs",
    ):
        assert phrase in law


def test_bra_managed_chairman_seats_remain_p0b_gated():
    law = _text(LAW)
    plan = _text(PLAN)
    assert "CHAIRMAN_MANAGED_BROWSER_SEAT" in law
    assert "existing P0B/MAS-115 program independently proves" in law
    assert "BRA-M1" in plan
    assert "P0B must first establish" in plan


def test_bra_remote_transport_is_not_runtime_identity():
    law = _text(LAW)
    design = _text(DESIGN)
    assert "Tunnel identity" in law
    assert "must never elect or replace RuntimeBinding" in law
    assert "Correlation IDs may appear in diagnostic receipts as transport evidence but never as company identity." in design


def test_bra_first_modifying_proof_is_disposable_not_chairman_chatgpt():
    plan = _text(PLAN)
    assert "BRA-A1" in plan
    assert "exact disposable browser" in plan
    assert "No Chairman seat. No ChatGPT prompt submission." in plan


def test_bra_records_reject_super_mcp_and_remote_desktop_rebuild():
    design = _text(DESIGN)
    assert "Mastermind-hosted generic remote-desktop relay" in design
    assert "central browser-session database" in design
    assert "super-MCP combining Executive, browser, filesystem and shell powers" in design
    assert "generic `execute_javascript`/raw-CDP model tools" in design


# Documentation-only discriminators for reviews 5125853519 and 5126242660.
# These tests read the three records; they do not enforce a browser, network,
# Executive transaction, permission, or at-most-once runtime invariant.
import re

import pytest


def _section(text: str, heading: str) -> str:
    marker = heading + "\n"
    assert text.count(marker) == 1, f"missing/duplicate section: {heading}"
    start = text.index(marker) + len(marker)
    level = len(heading) - len(heading.lstrip("#"))
    rest = text[start:]
    end = re.search(r"(?m)^#{1," + str(level) + r"} ", rest)
    return rest if end is None else rest[:end.start()]


def _table(text: str, heading: str, columns: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    section = _section(text, heading)
    lines = [line for line in section.splitlines() if line.startswith("|")]
    assert len(lines) >= 2, f"missing table in {heading}"
    parsed = [tuple(cell.strip().strip("`") for cell in line.strip("|").split("|")) for line in lines]
    assert parsed[0] == columns, f"wrong table columns in {heading}"
    assert all(re.fullmatch(r":?-{3,}:?", cell) for cell in parsed[1])
    rows: dict[str, tuple[str, ...]] = {}
    for cells in parsed[2:]:
        assert len(cells) == len(columns), f"wrong row width in {heading}"
        assert cells[0] and cells[0] not in rows, f"duplicate or empty key in {heading}"
        rows[cells[0]] = cells[1:]
    return rows


def test_bra_a1_names_existing_effect_owner_and_future_only_extension():
    rows = _table(_text(LAW), "### 5.1 BRA-A1 existing owner", ("Property", "Required value"))
    assert rows == {
        "Durable owner": ("Executive OS immutable Event plane",),
        "Aggregate type": ("operator_operation",),
        "Aggregate identity": ("owner-minted OperationId.command_id",),
        "Browser operation kind": ("future additive BROWSER_ACTION-equivalent; NOT_IMPLEMENTED_BY_F0",),
        "Gateway and browser receipts": ("EVIDENCE_ONLY",),
        "Gateway durable effect store": ("FORBIDDEN",),
    }
    section = _section(_text(LAW), "### 5.1 BRA-A1 existing owner")
    for event in ("INTENT", "APPLIED", "REFUSED", "EFFECT_UNKNOWN", "RECONCILED"):
        assert f"OPERATOR_OPERATION_{event}" in section
    assert "BRA-S1 must name its own existing semantic effect owner" in section
    assert "BRA-M1 does not inherit this Attempt-local owner" in section


def test_bra_action_reference_binds_every_consequential_identity():
    section = _section(_text(LAW), "### 5.2 Owner-minted action reference and issuance")
    identities = {
        "attempt_id", "worker_id", "session_epoch_id", "process_generation_id",
        "target_fingerprint", "target_generation", "action_version", "normalized_arguments",
        "capability_generation", "app_generation", "tool_schema_generation",
        "network_policy_generation", "network_policy_digest", "issued_at", "deadline",
        "precondition_digest", "principal", "authority_policy_hash",
        "logical_operation_key", "normalized_effect_digest",
    }
    assert identities <= set(re.findall(r"`([a-z_]+)`", section))
    assert "The caller cannot mint or substitute this reference" in section


def test_bra_intent_precedes_fresh_fence_and_single_dispatch():
    section = _section(_text(LAW), "### 5.2 Owner-minted action reference and issuance")
    block = re.search(r"```text\n(.*?)\n```", section, re.S)
    assert block, "missing ordered issuance contract"
    assert block.group(1).splitlines() == [
        "OWNER_VALIDATES_ACTION_AND_PRIOR_EFFECT",
        "-> OPERATOR_OPERATION_INTENT_COMMITTED_IN_BEGIN_IMMEDIATE",
        "-> REREAD_ATTEMPT_AUTHORITY_WRITER_GENERATION_TARGET_POLICY_PRIOR_EFFECT",
        "-> EXISTING_OWNER_AT_MOST_ONCE_ISSUANCE",
        "-> ONE_NATIVE_ADAPTER_DISPATCH",
        "-> OWNER_VALIDATES_POSTCONDITION_AND_APPENDS_RECEIPT",
    ]
    assert "Re-entering an existing INTENT never grants another dispatch" in section
    assert "Concurrent matching requests cannot both issue" in section


@pytest.mark.parametrize("condition,disposition,dispatch", [
    ("Same action with terminal receipt", "RETURN_EXISTING_EVIDENCE", "ZERO"),
    ("Changed action, target, policy or precondition", "CONFLICT_BEFORE_EFFECT", "ZERO"),
    ("INTENT with possible dispatch and no terminal proof", "EFFECT_UNKNOWN", "ZERO"),
    ("Unresolved EFFECT_UNKNOWN", "READ_ONLY_SAME_COMMAND_RECONCILIATION", "ZERO"),
    ("Positive canonical postcondition", "APPEND_RECONCILED_TO_SAME_COMMAND", "ZERO"),
    ("Missing evidence or retention loss", "EFFECT_UNKNOWN", "ZERO"),
])
def test_bra_replay_table_never_mints_a_second_effect(condition, disposition, dispatch):
    rows = _table(_text(LAW), "### 5.3 Replay and reconciliation", ("Condition", "Owner disposition", "Second dispatch"))
    assert len(rows) == 6
    assert condition in rows, f"missing replay rule: {condition}"
    assert rows[condition] == (disposition, dispatch)
    body = _section(_text(LAW), "### 5.3 Replay and reconciliation")
    for surface in ("target", "session", "account", "host", "tunnel", "gateway"):
        assert surface in body
    assert "replacement operation" in body
    assert "Restart cannot reset the Executive Event history" in body


def test_bra_common_effect_truth_is_not_browser_status():
    rows = _table(_text(LAW), "### 5.4 Response status and common effect truth", ("Response status", "effect_state", "Evidence requirement"))
    assert rows == {
        "REFUSED": ("NOT_APPLIED", "authoritative proof of no dispatch/effect"),
        "NO_EFFECT": ("NOT_APPLIED", "authoritative proof of no effect"),
        "APPLIED_VERIFIED": ("APPLIED", "exact canonical postcondition"),
        "AMBIGUOUS_AFTER_POSSIBLE_DISPATCH": ("EFFECT_UNKNOWN", "missing authoritative terminal proof"),
    }
    assert {row[0] for row in rows.values()} == {"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"}
    text = _section(_text(LAW), "### 5.4 Response status and common effect truth")
    assert "RECONCILED is a receipt/lineage status, not a fourth effect_state" in text
    assert "Driver success without the required postcondition is not APPLIED" in text


def test_bra_first_target_policy_has_no_model_navigation():
    rows = _table(_text(LAW), "### 6.1 First-vertical target policy", ("Boundary", "Required disposition"))
    assert rows == {
        "A1 target": ("owner-created and owner-loaded synthetic page before reference minting",),
        "A1 allowed origin": ("http://127.0.0.1:<leased-port> selected by the owner",),
        "A1 model-visible browser_navigate": ("FORBIDDEN",),
        "O1 navigation": ("FORBIDDEN",),
        "W1 generic navigation and network inspection": ("FORBIDDEN",),
        "Model-selected scheme, host, port, proxy, DNS, path root or allowlist": ("FORBIDDEN",),
        "Enforcement boundary": ("resource/process/network boundary",),
        "Playwright allowedOrigins alone": ("DEFENSE_IN_DEPTH_NOT_SECURITY_BOUNDARY",),
    }


@pytest.mark.parametrize("family", [
    "other loopback ports; IPv6; hostnames/DNS; private; link-local; public; DNS rebinding",
    "cross-origin redirects; frames; popups; new windows; subresources",
    "service workers; WebSockets",
    "file:; data:; blob:; javascript:; about:; chrome:; chrome-extension:; devtools:",
    "downloads; uploads; file chooser; clipboard transfer",
    "auth challenges; credential-bearing URLs; proxy/network setting changes",
    "model-selected raw URL; arbitrary fetch; unrestricted console/network payloads; secret headers/bodies",
])
def test_bra_egress_families_are_explicitly_refused(family):
    rows = _table(_text(LAW), "### 6.2 Closed egress and local-surface refusals", ("Destination or capability family", "Disposition"))
    assert len(rows) == 7
    assert family in rows, f"missing refusal family: {family}"
    assert rows[family] == ("REFUSED",)


def test_bra_later_navigation_invalidates_previous_target_epoch():
    text = _section(_text(LAW), "### 6.3 Later navigation is a different admitted policy")
    for phrase in (
        "separately reviewed policy generation and real canary",
        "increments the canonical navigation/target epoch",
        "invalidates prior element handles, preconditions and capability references",
        "fresh exact-target and policy evidence before another action",
    ):
        assert phrase in text


def test_bra_design_does_not_reintroduce_navigation_or_stateless_replay():
    text = _text(DESIGN)
    tools = _section(text, "### Generic actuation")
    assert "- `browser_navigate`" not in tools
    assert "BRA-A1 exposes no model-visible browser_navigate" in tools
    machine = _section(text, "## State machine for one modifying browser operation")
    for phrase in (
        "OPERATOR_OPERATION_INTENT_COMMITTED_IN_BEGIN_IMMEDIATE",
        "REREAD_CURRENT_AUTHORITY_TARGET_POLICY_AND_PRIOR_EFFECT",
        "EXISTING_OWNER_AT_MOST_ONCE_ISSUANCE",
        "ONE_NATIVE_ADAPTER_DISPATCH",
        "NOT_APPLIED | APPLIED | EFFECT_UNKNOWN",
        "Reconciled evidence never authorizes a second dispatch",
    ):
        assert phrase in machine
    assert machine.index("OPERATOR_OPERATION_INTENT_COMMITTED_IN_BEGIN_IMMEDIATE") < machine.index("ONE_NATIVE_ADAPTER_DISPATCH")
    assert "before EFFECT_DISPATCHED failure => NO_EFFECT/REFUSED" not in machine
    assert "resource/process/network boundary" in _section(text, "## First-vertical confinement")


def test_bra_plan_carries_the_existing_owner_and_required_negative_proofs():
    text = _section(_text(PLAN), "## BRA-A1 — one generic modifying actuation vertical")
    for phrase in (
        "Executive OS immutable Event plane", "operator_operation", "OperationId.command_id",
        "BROWSER_ACTION-equivalent is future additive work, not implemented by F0",
        "INTENT in BEGIN IMMEDIATE", "fresh authority/target/policy/prior-effect fence",
        "at most one native adapter dispatch", "NOT_APPLIED | APPLIED | EFFECT_UNKNOWN",
        "no model-visible browser_navigate", "http://127.0.0.1:<leased-port>",
        "resource/process/network boundary", "same-action replay", "changed-action replay",
        "concurrent duplicate", "gateway restart", "missing terminal evidence",
        "redirect/frame/popup/subresource", "navigation epoch",
    ):
        assert phrase in text
    assert "one exact fill+click synthetic interaction" in text
    assert "No Chairman seat. No ChatGPT prompt submission." in text


def test_bra_four_path_tests_remain_documentation_only():
    for path in (LAW, DESIGN, PLAN):
        assert "These source-law tests prove documentation consistency, not runtime enforcement" in _text(path)


def test_bra_persistent_authenticated_profile_is_dedicated_and_secret_free():
    law = _text(LAW)
    design = _text(DESIGN)
    for phrase in (
        "PERSISTENT_AUTHENTICATED_BROWSER_PROFILE",
        "dedicated automation Chrome profile",
        "stable home host",
        "must not copy the user's default Chrome profile",
        "cookie database",
        "raw CDP/DevTools",
        "one active mutating controller",
    ):
        assert phrase in law or phrase in design
    assert "newest-tab, title, window-order, or screen-coordinate targeting" in law


def test_bra_persistent_auth_readiness_is_typed_and_challenges_stay_human_gated():
    law = _text(LAW)
    plan = _text(PLAN)
    for state in (
        "READY", "LOGIN_REQUIRED", "MFA_REQUIRED", "HUMAN_CHALLENGE_REQUIRED",
        "PROFILE_LOCKED", "PROFILE_IN_USE", "HOST_OFFLINE", "STALE_GENERATION",
    ):
        assert state in law
    assert "credential-owning helper" in law
    assert "model receives only a non-secret outcome" in law
    assert "does not automate CAPTCHA solving or bypass a provider challenge" in law
    assert "BRA-P1" in plan
    assert "restart persistence" in plan


def test_bra_human_browser_is_attended_enrollment_not_production_identity():
    law = _text(LAW)
    design = _text(DESIGN)
    for phrase in (
        "attended enrollment or recovery surface",
        "not production target identity",
        "profile_generation",
        "browser_process_generation",
        "navigation epoch",
    ):
        assert phrase in law or phrase in design
    assert "existing human Chrome window" in law

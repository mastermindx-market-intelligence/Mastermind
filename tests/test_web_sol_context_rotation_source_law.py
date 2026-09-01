from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW_PATH = "docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md"
SPEC_PATH = (
    "docs/superpowers/specs/2026-09-01-web-sol-chat-context-continuity-design.md"
)
PLAN_PATH = (
    "docs/superpowers/plans/2026-09-01-web-sol-chat-context-continuity.md"
)
HIERARCHY_PATH = "docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md"
SESSION_TARGETS_PATH = "control_plane/session_targets.py"
ACTION_TARGET_PATH = "control_plane/sol_action_target.py"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_context_rotation_source_carriers_exist_and_remain_records_only() -> None:
    for path in (LAW_PATH, SPEC_PATH, PLAN_PATH):
        assert (ROOT / path).exists(), f"missing context-rotation source carrier: {path}"

    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))
    plan = _normalized(_read(PLAN_PATH))

    required = (
        "web-sol-chat-context-continuity-20260901-chairman-001",
        "web-sol-chat-context-continuity-cr-f0-20260901-sol-001",
        "RECORDS_ONLY",
        "SPEC_ONLY",
        "PRODUCTION_INERT",
        "WS:CHAIRMAN-CONTROL-ROOM",
        "MAS-198",
    )
    for phrase in required:
        assert phrase in law, f"law omits release identity/state: {phrase}"
        assert phrase in spec, f"spec omits release identity/state: {phrase}"

    assert "No browser/runtime implementation is authorized by CR-F0" in law
    assert "No browser/runtime implementation is authorized by CR-F0" in plan


def test_sol_identity_is_stable_while_chat_and_runtime_binding_rotate() -> None:
    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))
    hierarchy = _normalized(_read(HIERARCHY_PATH))

    required = (
        "THE SOL IDENTITY IS NOT THE CHAT CONVERSATION",
        "responsibility_ref",
        "session_alias",
        "ChatGPT conversation",
        "provider conversation id",
        "RuntimeBinding generation",
        "conversation URL",
        "TITLE IS NOT IDENTITY",
        "Project/predecessor chat history is advisory only",
    )
    for phrase in required:
        assert phrase in law, f"law omits stable/rotating identity boundary: {phrase}"
        assert phrase in spec, f"spec omits stable/rotating identity boundary: {phrase}"

    assert "Personal-Pro Chat remains the primary Sol cognition plane" in hierarchy
    assert "A chat conversation is replaceable working memory" in hierarchy


def test_owner_boundaries_extend_existing_planes_without_new_registry_or_memory() -> None:
    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))
    session_targets = _normalized(_read(SESSION_TARGETS_PATH))
    action_target = _normalized(_read(ACTION_TARGET_PATH))

    required = (
        "Executive OS owns Job / Attempt / Worker / Event lifecycle and CEO admission",
        "Agent OS owns durable continuation, decisions, discoveries and handoffs",
        "SessionTargetRegistry / RuntimeBinding owns the logical target and rotating exact runtime binding",
        "surface_bindings remains navigation-only",
        "Web-Sol is the closed browser actuator",
        "GitHub owns implementation and immutable evidence",
        "no Chat session registry",
        "no transcript memory database",
        "no second RuntimeBinding store",
        "no rollover queue",
        "no retry ledger",
        "no browser-tab authority plane",
    )
    for phrase in required:
        assert phrase in law, f"law omits canonical owner/no-rebuild boundary: {phrase}"
        assert phrase in spec, f"spec omits canonical owner/no-rebuild boundary: {phrase}"

    assert "binding_id is durable and opaque" in session_targets
    assert "A read-composed binding snapshot; never a binding registry or writer" in action_target


def test_web_sol_action_surface_is_closed_and_project_only() -> None:
    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))

    allowed = (
        "INSPECT",
        "FOREGROUND",
        "CREATE_SUCCESSOR",
        "DELIVER_CONTINUATION_BOOTSTRAP",
        "VERIFY_SUCCESSOR",
    )
    forbidden = (
        "CLICK",
        "TYPE",
        "SEND_TEXT",
        "NAVIGATE_URL",
        "EXECUTE_JS",
        "QUERY_SELECTOR",
        "READ_TRANSCRIPT",
        "READ_MODEL_OUTPUT",
        "COPY_CHAT",
        "SELECT_ACCOUNT",
    )
    for phrase in allowed:
        assert phrase in law, f"law omits closed semantic action: {phrase}"
        assert phrase in spec, f"spec omits closed semantic action: {phrase}"
    for phrase in forbidden:
        assert phrase in law, f"law omits forbidden public primitive: {phrase}"
        assert phrase in spec, f"spec omits forbidden public primitive: {phrase}"

    required_scope = (
        "/g/g-p-<project>/c/<conversation>",
        "same approved managed-browser profile",
        "same ChatGPT Project",
        "different new conversation identity",
        "NON_PROJECT_CONVERSATION_UNSUPPORTED",
        "No caller-selected project/account/profile URL",
    )
    for phrase in required_scope:
        assert phrase in law, f"law omits initial provider scope: {phrase}"
        assert phrase in spec, f"spec omits initial provider scope: {phrase}"


def test_rotation_classifier_never_equates_generic_provider_error_with_context_limit() -> None:
    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))

    states = (
        "SESSION_HEALTHY",
        "ROTATION_SUSPECTED",
        "ROTATION_REQUIRED",
        "AUTH_REQUIRED",
        "PROVIDER_TRANSIENT",
        "SURFACE_UNUSABLE",
        "UNKNOWN",
    )
    reasons = (
        "MANUAL_RETIREMENT",
        "CONTEXT_LIMIT_SUSPECTED",
        "REPEATED_TERMINAL_GENERATION_FAILURE",
        "SURFACE_UNUSABLE",
        "UNKNOWN",
    )
    for phrase in states + reasons:
        assert phrase in law, f"law omits closed rotation state/reason: {phrase}"
        assert phrase in spec, f"spec omits closed rotation state/reason: {phrase}"

    required = (
        "Thinking failed != context exhausted",
        "Never export raw provider error text",
        "If exact context exhaustion cannot be proven, preserve suspicion or surface-unusable uncertainty",
    )
    for phrase in required:
        assert phrase in law, f"law omits classifier truth boundary: {phrase}"
        assert phrase in spec, f"spec omits classifier truth boundary: {phrase}"


def test_continuation_bootstrap_is_deterministic_bounded_and_canonical_state_first() -> None:
    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))

    required = (
        "SOL CONTINUATION",
        "Logical responsibility:",
        "Reason:",
        "Predecessor:",
        "Current continuation record:",
        "Current protected source:",
        "Recover current canonical state using COLD_START",
        "Do not restart completed work",
        "Recover any open reciprocal worker dialogue before creating replacement work",
        "Do not submit arbitrary model/user text through Web-Sol",
        "Predecessor title is advisory only",
        "bounded continuation manifest",
    )
    for phrase in required:
        assert phrase in law, f"law omits bootstrap contract: {phrase}"
        assert phrase in spec, f"spec omits bootstrap contract: {phrase}"


def test_succession_sequence_effect_fences_and_semantic_readiness_are_explicit() -> None:
    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))

    sequence = (
        "1. ROTATION REQUEST",
        "2. EFFECT FENCE",
        "3. DURABLE CONTINUATION",
        "4. EXACT TARGET RESOLUTION",
        "5. CREATE ONE SUCCESSOR",
        "6. DELIVER BOOTSTRAP",
        "7. VERIFY SURFACE",
        "8. SEMANTIC READINESS",
        "9. RUNTIMEBINDING SUCCESSION",
        "10. NAVIGATION UPDATE",
        "11. POST-CUTOVER INSPECT",
        "12. CONTINUE",
    )
    for phrase in sequence:
        assert phrase in law, f"law omits exact succession step: {phrase}"
        assert phrase in spec, f"spec omits exact succession step: {phrase}"

    required = (
        "EFFECT_UNKNOWN blocks modifying continuation",
        "Never blindly create another successor",
        "Never blindly submit the bootstrap twice",
        "visible generated text is not PICKUP_ACK or START",
        "semantic readiness must reuse an accepted Agent Relay / Company Dialogue / continuation ACK owner",
    )
    for phrase in required:
        assert phrase in law, f"law omits effect/readiness boundary: {phrase}"
        assert phrase in spec, f"spec omits effect/readiness boundary: {phrase}"


def test_runtime_binding_succession_is_cas_aba_safe_and_navigation_cannot_roll_it_back() -> None:
    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))

    required = (
        "generation N",
        "generation N+1",
        "preserve the same session_alias and responsibility_ref",
        "fence predecessor generation N",
        "CAS/ABA-safe",
        "stale predecessor remains non-authoritative even if it later becomes responsive",
        "authority remains with the successor",
        "navigation degraded/stale",
        "Do not roll authority backward merely to make navigation agree",
    )
    for phrase in required:
        assert phrase in law, f"law omits RuntimeBinding succession invariant: {phrase}"
        assert phrase in spec, f"spec omits RuntimeBinding succession invariant: {phrase}"


def test_provider_falsifier_failure_matrix_and_proof_ladder_are_release_gates() -> None:
    law = _normalized(_read(LAW_PATH))
    spec = _normalized(_read(SPEC_PATH))
    plan = _normalized(_read(PLAN_PATH))

    falsifiers = (
        "duplicate predecessor titles",
        "renamed predecessor title",
        "exact predecessor reference/URL",
        "synthetic fact that existed ONLY in the predecessor",
        "Project membership is essential",
    )
    failures = (
        "wrong ChatGPT Project",
        "wrong managed profile/account",
        "two candidate new conversations",
        "successor responds visibly but semantic ACK is absent",
        "RuntimeBinding generation race / ABA",
        "extension service worker restarts during rotation",
        "native transport disconnects during each effect boundary",
        "predecessor already totally dead before checkpoint",
        "ChatGPT Project history unavailable",
        "Agent OS continuation record unavailable/stale",
        "stale predecessor later becomes responsive again",
    )
    for phrase in falsifiers + failures:
        assert phrase in spec, f"spec omits required falsifier/failure: {phrase}"
        assert phrase in plan, f"plan omits required falsifier/failure: {phrase}"

    ladder = (
        "CR-F0",
        "CR-P1",
        "CR-B1",
        "CR-D1",
        "CR-PROD1",
        "Zero Chairman click/type/message shuttling",
        "Do not call the program PROVEN_LIVE before CR-PROD1",
    )
    for phrase in ladder:
        assert phrase in law, f"law omits release/proof boundary: {phrase}"
        assert phrase in plan, f"plan omits release/proof boundary: {phrase}"


def test_implementation_plan_preserves_open_carriers_and_one_capability_per_pr() -> None:
    plan = _normalized(_read(PLAN_PATH))

    required = (
        "PR #306",
        "sol/wsx-r1-self-reconstitution-20260901",
        "PR #308",
        "sol/wsx-t1-transport-hardening-20260901",
        "Do not absorb or replace either existing carrier",
        "one independently useful capability per PR",
        "RED -> GREEN -> exact-head CI/security -> independent review -> production proof",
        "RuntimeBinding writer discovery gate",
        "semantic ACK owner discovery gate",
        "provider continuation falsifier",
        "disposable/non-sensitive ChatGPT Project",
        "real approved Project Sol rotation",
    )
    for phrase in required:
        assert phrase in plan, f"implementation plan omits required boundary: {phrase}"

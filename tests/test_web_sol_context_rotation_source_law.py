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
    assert "context rotation preserves responsibility and fences the predecessor" in hierarchy


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

    assert "``binding_id`` is durable and opaque" in session_targets
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


# SR-F0 session-reliability and adaptive-mode source contracts.
def test_session_reliability_skill_is_enrolled_and_compatible() -> None:
    path = ROOT / "docs/sol_skills/SESSION_RELIABILITY.md"
    assert path.exists()
    skill = _read("docs/sol_skills/SESSION_RELIABILITY.md")
    index = _normalized(_read("docs/sol_skills/INDEX.md"))
    for phrase in (
        "schema: mastermind.sol_skillpack.v1",
        "skillpack_version: 1.0.1",
        "minimum_bootstrap_major: 1",
        "skill: session_reliability",
    ):
        assert phrase in skill
    assert "### `SESSION_RELIABILITY.md`" in index
    assert "distinguishes bounded mode recovery from context rotation" in index


def test_session_reliability_preserves_budgets_and_emergency_frontier() -> None:
    skill = _normalized(_read("docs/sol_skills/SESSION_RELIABILITY.md"))
    for phrase in (
        "8 KiB or 150 lines",
        "16 KiB",
        "100 matches",
        "32 KiB",
        "six material tool calls",
        "15 seconds",
        "30 seconds",
        "12 KiB / 1500 words",
        "NOT_CANONICALLY_PERSISTED",
        "last durable ref",
        "A successor must reconcile and persist",
    ):
        assert phrase in skill


def test_isolated_failure_allows_only_bounded_mode_recovery() -> None:
    law = _normalized(_read(LAW_PATH))
    skill = _normalized(_read("docs/sol_skills/SESSION_RELIABILITY.md"))
    for phrase in (
        "Thinking failed != context exhausted",
        "low context pressure",
        "at most one bounded recovery",
        "different user-visible reasoning mode such as Extra High",
        "not proof of cause, carrier failover, or context rotation",
        "never bypasses a safety/permission denial",
    ):
        assert phrase in law
    assert "a relevant mode change may be part of that recovery" in skill
    assert "already heavy/unstable enough that continuing is unsafe" in skill


def test_compact_project_kernel_carries_adaptive_mode_and_rotation_boundary() -> None:
    kernel = _normalized(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md"))
    for phrase in (
        "Sol owns mode recommendations",
        "Pro may support writes, lack specific tools/actions, or lose access mid-session",
        "Extra High is a recovery candidate, not guaranteed access",
        "Text cannot self-switch",
        "No unchanged retry/reconnect loops",
        "Tool failure is not chat corruption",
        "HARD_ROTATION after repeated thinking/session failure",
        "NOT_CANONICALLY_PERSISTED",
        "MODE_SWITCH/FRESH_CHAT are human-gate reasons, not lifecycle states",
    ):
        assert phrase in kernel


def test_session_reliability_budgets_are_pressure_indicators_not_productivity_ceilings() -> None:
    skill = _normalized(_read("docs/sol_skills/SESSION_RELIABILITY.md"))
    for phrase in (
        "pressure indicators and checkpoint prompts",
        "never hard productivity ceilings",
        "healthy long turn",
        "same bounded phase",
        "Depth is allowed; breadth is fenced",
    ):
        assert phrase in skill


def test_session_reliability_distinguishes_stream_turn_session_and_workspace_failures() -> None:
    skill = _normalized(_read("docs/sol_skills/SESSION_RELIABILITY.md"))
    for phrase in (
        "STREAM_ATTACHMENT_UNCERTAIN",
        "TURN_EXECUTION_ENDED",
        "SESSION_UNSTABLE",
        "WORKSPACE_OR_EFFECT_UNCERTAIN",
        "do not duplicate Continue or effects",
        "same conversation",
        "fresh same-mode chat",
    ):
        assert phrase in skill


def test_session_reliability_preserves_long_mode_specific_work() -> None:
    skill = _normalized(_read("docs/sol_skills/SESSION_RELIABILITY.md"))
    for phrase in (
        "Astra Pro",
        "10–20+ minute",
        "30–50m+",
        "mode stickiness",
        "not a timer law",
        "Do not bounce",
    ):
        assert phrase in skill


def test_compact_kernel_projects_phase_fence_and_mode_stickiness() -> None:
    kernel = _normalized(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md"))
    for phrase in (
        "mode stickiness",
        "active semantic phase",
        "Depth allowed; breadth fenced",
        "same healthy chat",
        "mission is incomplete",
        "fresh same-mode chat",
    ):
        assert phrase in kernel


def test_stream_attachment_uncertainty_does_not_imply_context_rotation() -> None:
    law = _normalized(_read(LAW_PATH))
    for phrase in (
        "client stream detachment is not session death",
        "STREAM_ATTACHMENT_UNCERTAIN",
        "does not establish `ROTATION_REQUIRED`",
        "reacquire the exact conversation/request state",
        "Do not duplicate `Continue` or any modifying effect",
    ):
        assert phrase in law


def _section_text(text: str, heading: str, next_heading: str) -> str:
    start = text.index(heading)
    end = text.index(next_heading, start + len(heading))
    return " ".join(text[start:end].split())


def _sr_f0_semantic_guard_errors(*, law: str, skill: str, active: str) -> list[str]:
    errors: list[str] = []
    norm_law = " ".join(law.split())
    norm_skill = " ".join(skill.split())
    norm_active = " ".join(active.split())
    suspected = _section_text(skill, "### `ROTATION_SUSPECTED`", "### `ROTATION_REQUIRED`")
    phase = _section_text(
        active,
        "The reliability invariant is the **recovery gap**, not runtime:",
        "## Step 8 — Final-response gate",
    )
    law_threshold = "two consecutive terminal generation failures in the exact conversation with no successful intervening turn"
    skill_threshold = "two consecutive terminal generation failures with no successful intervening turn"
    if law_threshold not in norm_law or skill_threshold not in norm_skill:
        errors.append("two-failure-threshold")
    if "cumulative raw output approaching the turn budget;" in suspected:
        errors.append("budget-alone-rotation")
    if "output pressure alone does not require a turn boundary" not in phase:
        errors.append("pressure-only-turn-boundary")
    if "surface remains healthy, **start that next phase in the same turn**" not in phase:
        errors.append("healthy-phase-continuation")
    if "a specific chunk boundary alone is no longer sufficient" not in norm_active:
        errors.append("chunk-boundary-not-stop")
    return errors


def test_output_pressure_alone_does_not_force_recovery_or_rotation() -> None:
    skill = _read("docs/sol_skills/SESSION_RELIABILITY.md")
    active = _read("docs/sol_skills/ACTIVE_EXECUTION.md")
    active_normalized = " ".join(active.split())
    suspected = _section_text(skill, "### `ROTATION_SUSPECTED`", "### `ROTATION_REQUIRED`")
    assert "cumulative raw output approaching the turn budget;" not in suspected
    assert "output pressure plus a stale durable frontier or inability to keep further output bounded" in suspected
    assert "Output pressure alone does not change `SESSION_HEALTHY`" in skill
    assert "output pressure alone does not require a turn boundary" in active_normalized


def test_persistence_failure_maps_to_existing_truthful_dispositions() -> None:
    skill = " ".join(_read("docs/sol_skills/SESSION_RELIABILITY.md").split())
    kernel = " ".join(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md").split())
    for phrase in (
        "`EFFECT_UNKNOWN` only for an ambiguous checkpoint write",
        "`EXACT_HUMAN_GATE` only for a real human/admin ceremony",
        "proven pre-dispatch persistence/platform outage",
        "`ALL_SCOPED_LANES_BLOCKED`",
        "safe independent work remains",
        "`MORE_WORK_EXISTS`",
    ):
        assert phrase in skill
    assert "Classify by observed cause; never invent HUMAN_GATE/EFFECT_UNKNOWN" in kernel


def test_semantic_mutation_guard_rejects_threshold_and_healthy_phase_reversal() -> None:
    law = _read(LAW_PATH)
    skill = _read("docs/sol_skills/SESSION_RELIABILITY.md")
    active = _read("docs/sol_skills/ACTIVE_EXECUTION.md")
    assert _sr_f0_semantic_guard_errors(law=law, skill=skill, active=active) == []

    bad_law = law.replace(
        "two consecutive terminal generation failures in the\nexact conversation with no successful intervening turn",
        "twenty consecutive terminal generation failures in the\nexact conversation with no successful intervening turn",
    )
    bad_skill = skill.replace(
        "two consecutive terminal generation failures with no successful intervening turn",
        "twenty consecutive terminal generation failures with no successful intervening turn",
    )
    assert "two-failure-threshold" in _sr_f0_semantic_guard_errors(
        law=bad_law, skill=bad_skill, active=active
    )

    bad_active = active.replace(
        "surface remains healthy, **start that next phase in the same turn**",
        "surface remains healthy, **stop the current turn immediately**",
    )
    assert "healthy-phase-continuation" in _sr_f0_semantic_guard_errors(
        law=law, skill=skill, active=bad_active
    )

    bad_chunk_gate = active.replace(
        "a specific chunk boundary alone is no longer sufficient",
        "a specific chunk boundary alone is sufficient",
    )
    assert "chunk-boundary-not-stop" in _sr_f0_semantic_guard_errors(
        law=law, skill=skill, active=bad_chunk_gate
    )


def test_rotation_law_persistence_frontier_uses_cause_based_disposition_mapping() -> None:
    law = " ".join(_read(LAW_PATH).split())
    assert "under the genuine human/effect gate" not in law
    for phrase in (
        "ACTIVE_EXECUTION Step 8",
        "`EFFECT_UNKNOWN` only for an ambiguous checkpoint write",
        "`EXACT_HUMAN_GATE` only for a real human/admin ceremony",
        "confirmed pre-dispatch persistence/platform outage",
        "`ALL_SCOPED_LANES_BLOCKED`",
        "safe independent work remains",
        "`MORE_WORK_EXISTS`",
        "`NOT_CANONICALLY_PERSISTED`",
    ):
        assert phrase in law


def test_cross_phase_continuation_is_projected_into_session_reliability_and_kernel() -> None:
    skill = " ".join(_read("docs/sol_skills/SESSION_RELIABILITY.md").split())
    kernel_raw = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")
    kernel = " ".join(kernel_raw.split())
    for phrase in (
        "Completing a checkpoint, task, or semantic phase does not itself end the turn",
        "start the next bounded safe critical-path phase in the same healthy turn",
        "A clean phase boundary is not continuity pressure",
        "start it rather than yielding merely because the previous phase ended",
    ):
        assert phrase in skill
    for phrase in (
        "After any task/phase completes, verify/save it, reassess the mission",
        "WAITING_EXTERNAL/review/CI/messages are lane-local",
        "`DURABLE_EXECUTION_RUNNING` requires proven STARTED/RUNNING + lawful return",
        "Other Step-8 stops still apply",
        "A clean phase boundary is not a stop",
        "MORE_WORK_EXISTS means the mission is incomplete: do not finalize while healthy useful work remains",
        "task/phase/checkpoint completion alone never qualifies",
    ):
        assert phrase in kernel
    project_block = kernel_raw.split("```text\n", 1)[1].split("```", 1)[0]
    assert len(project_block) < 8000


def test_cross_phase_mutation_guard_rejects_phase_boundary_as_stop() -> None:
    law = _read(LAW_PATH)
    skill = _read("docs/sol_skills/SESSION_RELIABILITY.md")
    active = _read("docs/sol_skills/ACTIVE_EXECUTION.md")
    bad_active = active.replace(
        "surface remains healthy, **start that next phase in the same turn**",
        "surface remains healthy, **stop at this phase boundary**",
    )
    assert "healthy-phase-continuation" in _sr_f0_semantic_guard_errors(
        law=law, skill=skill, active=bad_active
    )

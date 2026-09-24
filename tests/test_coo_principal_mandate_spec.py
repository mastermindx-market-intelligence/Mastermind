import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-09-24-coo-principal-mandate-v1.md"
FIXTURE = ROOT / "research" / "fixtures" / "coo_principal_mandate_acceptance_2026-09-24.json"


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_acceptance_corpus_is_closed_and_explicitly_inert():
    doc = _fixture()
    assert set(doc) == {
        "schema",
        "status",
        "is_runtime_configuration",
        "is_production_authority",
        "cases",
    }
    assert doc["schema"] == "mastermind.coo_principal_mandate_acceptance.v1"
    assert doc["status"] == "SPEC_ONLY"
    assert doc["is_runtime_configuration"] is False
    assert doc["is_production_authority"] is False

    cases = doc["cases"]
    assert len(cases) == 36
    assert [row["id"] for row in cases] == [f"M{i:02d}" for i in range(1, 37)]
    assert len({row["id"] for row in cases}) == len(cases)
    assert all(set(row) == {"id", "class", "scenario", "expected"} for row in cases)
    assert {row["class"] for row in cases} == {
        "allow",
        "refuse",
        "unknown",
        "acceptance",
    }


def test_corpus_preserves_broad_coo_judgment_not_worker_grade_micromanagement():
    by_id = {row["id"]: row for row in _fixture()["cases"]}
    assert by_id["M01"]["expected"] == "DECIDE_CONTINUE"
    assert by_id["M02"]["expected"] == "DECIDE_CONTINUE"
    assert by_id["M03"]["expected"] == "ALLOW_SUCCESSOR_ROOT"
    assert by_id["M04"]["expected"] == "ALLOW_SOURCE_RELEASE"
    assert by_id["M05"]["expected"] == "DECIDE_CONTINUE"
    assert by_id["M06"]["expected"] == "CONTINUE_INDEPENDENT_LANE"


def test_corpus_keeps_only_constitutional_boundaries_above_fable():
    by_id = {row["id"]: row for row in _fixture()["cases"]}
    assert by_id["M08"]["expected"] == "REFUSE_WRONG_SEAT"
    assert by_id["M09"]["expected"] == "REFUSE_WRONG_SEAT"
    assert by_id["M10"]["expected"] == "REFUSE_RECONCILE_REQUIRED"
    assert by_id["M11"]["expected"] == "REFUSE_RESERVED_BOUNDARY"
    assert by_id["M12"]["expected"] == "REFUSE_RESERVED_BOUNDARY"
    assert by_id["M13"]["expected"] == "REFUSE_OUTCOME_AUTHORITY"
    assert by_id["M14"]["expected"] == "REFUSE_SELF_AUTHORITY_EXPANSION"
    assert by_id["M15"]["expected"] == "REFUSE_PLACEMENT_BYPASS"


def test_spec_separates_principal_ceiling_from_worker_and_cycle_ceilings():
    text = SPEC.read_text(encoding="utf-8")
    assert "Worker ceilings are not principal ceilings" in text
    assert "unbounded program judgment over bounded, receipt-backed concrete effects" in text
    assert "coo_cycle_policy" in text
    assert "do **not** cap the total scale of a Fable-owned programme" in text
    assert "Successor roots remain ordinary Executive roots" in text


def test_spec_grants_normal_source_completion_without_granting_blanket_admin():
    text = SPEC.read_text(encoding="utf-8")
    assert "AUTONOMOUS_SOURCE_RELEASE_WITH_GATES" in text
    assert "branch write/push, PR create/update and merge/release" in text
    assert "RESERVED_RELEASE" in text
    for boundary in (
        "credential creation/rotation/custody changes",
        "destructive data operations",
        "security-boundary weakening",
        "company Charter/north-star/objective-set changes",
        "authority/governance edits that widen the principal's own power",
    ):
        assert boundary in text


def test_spec_reuses_existing_authority_and_lifecycle_owners():
    text = SPEC.read_text(encoding="utf-8")
    assert "Mandate is a projection, never a durable authority store" in text
    assert "There is no `fable_mandates` table, file, cache, queue, token store or session database." in text
    assert "#955 owns the authenticated Claude client edge." in text
    assert "#676 is accepted SPEC_ONLY evidence" in text
    assert "Executive Runtime/COO owns Job/Attempt/effect progression." in text
    assert "Capacity/Model Router owns exact execution placement." in text
    assert "Agent OS owns long-horizon workstream continuity." in text


def test_spec_refuses_caller_asserted_role_and_fake_session_authority():
    text = SPEC.read_text(encoding="utf-8")
    assert "without accepting a caller-provided `actor`, `seat`, account name, model name or chat title as authority" in text
    assert "Exact Claude conversation binding is NOT assumed" in text
    assert "Modern MCP is stateless" in text
    assert "Surface bindings are also explicitly navigation-only" in text
    assert "Claude Code hooks do expose a provider session identifier" in text
    assert "future binding input" in text

    by_id = {row["id"]: row for row in _fixture()["cases"]}
    assert by_id["M07"]["expected"] == "REFUSE_CALLER_ASSERTED_ROLE"
    assert by_id["M17"]["expected"] == "REFUSE_MCP_CLIENTINFO_AUTHORITY"
    assert by_id["M18"]["expected"] == "REFUSE_NAVIGATION_AS_AUTHORITY"
    assert by_id["M19"]["expected"] == "SESSION_ISOLATION_NOT_PROVEN"


def test_end_to_end_acceptance_requires_independent_judgment_not_tool_demo():
    text = SPEC.read_text(encoding="utf-8")
    assert "The decisive canary is a meaningful project, not a tool demo." in text
    assert "make at least one nontrivial reversible architecture/product judgment without asking" in text
    assert "Acceptance fails if routine preference questions or manual prompt carriage are required." in text


def test_spec_freezes_local_plugin_packaging_without_public_executive_exposure():
    text = SPEC.read_text(encoding="utf-8")
    assert "Claude packaging boundary" in text
    assert "private **Mastermind Executive** Claude plugin/desktop extension" in text
    assert "do not make the private Executive loopback service public" in text
    assert "Claude Code 2.1.275" in text
    assert "2.1.273 minimum" in text
    assert "Plugin installation is capability availability, not mission authority." in text


def test_spec_keeps_hook_session_id_as_falsifier_not_grant():
    text = SPEC.read_text(encoding="utf-8")
    assert "current MCP 2026-07-28 specification is intentionally stateless" in text
    assert "session_id" in text
    assert "CLAUDE_ENV_FILE" in text
    assert "viable investigation seam, not the final security design" in text


def test_spec_uses_broad_mission_authority_with_fail_closed_tool_capabilities():
    text = SPEC.read_text(encoding="utf-8")
    assert "Authorization semantics — broad mission law, explicit technical capabilities" in text
    assert "do not enumerate every ordinary action Fable is allowed to take" in text
    assert "Adding a new reversible implementation technique does not require adding another COO permission token." in text
    assert "A rich principal profile therefore uses explicit tool/package grants" in text
    assert "MAY Fable make this decision?" in text
    assert "CAN this surface execute it now?" in text
    assert "A technical absence does not shrink Fable's organizational mandate" in text


def test_spec_separates_fable_coo_oauth_scope_from_ceo_submit_scope():
    text = SPEC.read_text(encoding="utf-8")
    assert "OAuth scope separation from the CEO seat" in text
    assert "must not inherit `mastermind.executive.intent.submit`" in text
    assert "mastermind.executive.coo.act" in text
    assert "a token carrying the COO action scope must not pass the CEO submit route or vice versa" in text


def test_implementation_packet_preserves_one_sink_one_service_and_replay_identity():
    text = SPEC.read_text(encoding="utf-8")
    assert "Implementation packet — preserve one mutation sink and one installed service" in text
    assert "extend the **existing `ceo_intent.submit_intent` mutation sink**" in text
    assert "Do not fingerprint current dynamic mandate/runtime state." in text
    assert "one installed process, two static role surfaces" in text
    assert "Do not replace the current CEO MCP profile and do not run a second Executive daemon." in text
    assert "Do **not** add `submit_coo_ruling` until its exact canonical effect owner is identified." in text
    assert "Do not add `OPEN_PR`, `PUSH_BRANCH` or `MERGE` to `executive_worker_policy`" in text

    by_id = {row["id"]: row for row in _fixture()["cases"]}
    assert by_id["M21"]["expected"] == "REFUSE_CROSS_SEAT_SCOPE"
    assert by_id["M22"]["expected"] == "ONE_SERVICE_DISTINCT_ROLE_SURFACES"
    assert by_id["M23"]["expected"] == "REPLAY_PRESERVES_ACCEPTED_EFFECT"


def test_session_falsifier_is_optional_and_never_trusts_model_or_mcp_environment():
    text = SPEC.read_text(encoding="utf-8")
    assert "Exact-session falsifier — optional hardening, not the V1 autonomy gate" in text
    assert "PreToolUse" in text and "updatedInput" in text
    assert "never `permissionDecision=allow` as an authority grant" in text
    assert "must **not** be silently reused for COO session assertions" in text
    assert "COO_PRINCIPAL_MISSION_BOUND" in text
    assert "COO_PRINCIPAL_PROVIDER_SESSION_BOUND" in text
    assert "COO_PRINCIPAL_CRYPTOGRAPHIC_SESSION_BOUND" in text
    assert "differed from the identifier delivered to hooks/Bash" in text

    by_id = {row["id"]: row for row in _fixture()["cases"]}
    assert by_id["M24"]["expected"] == "REFUSE_MODEL_SESSION_ASSERTION"
    assert by_id["M25"]["expected"] == "PROVIDER_SESSION_BINDING_CANDIDATE"
    assert by_id["M26"]["expected"] == "REFUSE_MCP_SESSION_ENV_AUTHORITY"
    assert by_id["M27"]["expected"] == "CAPABILITY_UNAVAILABLE_NO_AUTHORITY_FALLBACK"
    assert by_id["M28"]["expected"] == "REFUSE_SESSION_HARDENING_UNPROVEN"


def test_mandate_projection_reuses_mission_workspace_v3_without_faking_claude_runtime_binding():
    text = SPEC.read_text(encoding="utf-8")
    assert "Primary organizational input: the existing Mission Workspace v3 projection." in text
    assert "Do not make the mandate reducer reacquire Control Room, Fabric, Runtime or Agent OS independently." in text
    assert "read_state.state=CURRENT" in text
    assert "owner observation `SAME`" in text
    assert "it does not expose a dedicated `current_coo_target` RuntimeBinding" in text
    assert "Do not fabricate a Claude RuntimeBinding inside the mandate reducer." in text

    by_id = {row["id"]: row for row in _fixture()["cases"]}
    assert by_id["M29"]["expected"] == "MISSION_V3_IS_PRIMARY_ORGANIZATIONAL_INPUT"
    assert by_id["M30"]["expected"] == "REFUSE_UNQUALIFIED_MISSION_STATE"
    assert by_id["M31"]["expected"] == "MISSION_BOUND_WITH_SESSION_HARDENING_DEFERRED"


def test_principal_submit_contract_stays_high_level_and_role_correct():
    text = SPEC.read_text(encoding="utf-8")
    assert "P2-B.1 — `submit_principal_intent` public request and receipt" in text
    assert "`workstream` is required" in text
    assert "`research_only | bounded_code_change`" in text
    assert "strict-v2 COO root ceiling (1..2, default 2)" in text
    assert "does **not** narrow Fable's organizational autonomy" in text
    assert "`dispatched=false` remains load-bearing" in text
    assert "CEO request identities and COO principal request identities never collide" in text

    by_id = {row["id"]: row for row in _fixture()["cases"]}
    assert by_id["M32"]["expected"] == "ACCEPT_HIGH_LEVEL_PRINCIPAL_REQUEST"
    assert by_id["M33"]["expected"] == "REFUSE_PRIVILEGED_CALLER_FIELDS"
    assert by_id["M34"]["expected"] == "REFUSE_MISSION_IDENTITY_MISMATCH"
    assert by_id["M35"]["expected"] == "RECONCILE_ONE_ACCEPTED_JOB"
    assert by_id["M36"]["expected"] == "REFUSE_PRINCIPAL_REQUEST_CONFLICT"

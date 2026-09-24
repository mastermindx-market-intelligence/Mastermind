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
    assert len(cases) == 20
    assert [row["id"] for row in cases] == [f"M{i:02d}" for i in range(1, 21)]
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

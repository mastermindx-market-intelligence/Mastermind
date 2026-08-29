"""RED-first contract tests for the pure Executive Steward read core.

The Steward is a deterministic composer over already-authoritative facts.  It
does not gather, persist, route, dispatch, mutate, or infer identity.  These
tests deliberately construct the typed dependency seams directly so every
join and refusal can be exercised without touching a runtime database, local
surface store, Slack, Wake, Linear, a provider, or the network.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import importlib.util
from pathlib import Path

import pytest

_MODULE_NAME = "control_plane.executive_steward"
_MODULE_PATH = Path(__file__).parents[1] / "control_plane" / "executive_steward.py"


def _module():
    spec = importlib.util.find_spec(_MODULE_NAME)
    assert spec is not None, "Executive Steward production module is not implemented"
    module = importlib.import_module(_MODULE_NAME)
    required = {
        "BlockerFact",
        "CapacityState",
        "EffectState",
        "ExecutiveStewardSnapshot",
        "Freshness",
        "QueryStatus",
        "ResponsibilityFact",
        "RuntimeFact",
        "Seat",
        "SourceFailure",
        "SourceOwner",
        "SourceRef",
        "SurfaceFact",
        "AttentionFact",
    }
    missing = sorted(name for name in required if not hasattr(module, name))
    assert not missing, f"Executive Steward API missing: {missing}"
    return module


def _source(
    module,
    owner: str,
    ref: str,
    *,
    observed_at: str = "2026-08-29T04:40:00Z",
    freshness: str = "CURRENT",
):
    return module.SourceRef(
        owner=getattr(module.SourceOwner, owner),
        ref=ref,
        observed_at=observed_at,
        freshness=getattr(module.Freshness, freshness),
    )


def _responsibility(
    module,
    ref: str = "WS:OCR-6",
    *,
    title: str = "Executive Steward read core",
    accountable_seat: str = "CEO",
    state: str | None = "in_progress",
    root_job_id: str | None = "JOB-OCR6",
    observed_at: str = "2026-08-29T04:40:00Z",
    freshness: str = "CURRENT",
):
    return module.ResponsibilityFact(
        responsibility_ref=ref,
        title=title,
        accountable_seat=getattr(module.Seat, accountable_seat),
        state=state,
        root_job_id=root_job_id,
        source=_source(
            module,
            "AGENT_OS",
            f"agentos/workstreams/{ref.replace(':', '-')}.md",
            observed_at=observed_at,
            freshness=freshness,
        ),
    )


def _attention(
    module,
    attention_id: str,
    *,
    ref: str = "WS:OCR-6",
    target: str = "CEO",
    kind: str = "review_required",
    reason: str = "Sol review is required before merge.",
    observed_at: str = "2026-08-29T04:41:00Z",
    freshness: str = "CURRENT",
):
    return module.AttentionFact(
        attention_id=attention_id,
        responsibility_ref=ref,
        target_seat=getattr(module.Seat, target),
        kind=kind,
        reason=reason,
        source=_source(
            module,
            "EXECUTIVE_INBOX",
            f"executive-inbox:{attention_id}",
            observed_at=observed_at,
            freshness=freshness,
        ),
    )


def _runtime(
    module,
    *,
    ref: str = "WS:OCR-6",
    root_job_id: str = "JOB-OCR6",
    seat: str = "CEO",
    attempt_id: str = "ATT-OCR6-2",
    worker_id: str = "WORKER-SOL-2",
    status: str = "RUNNING",
    observed_at: str = "2026-08-29T04:42:00Z",
    freshness: str = "CURRENT",
    executive_observed_at: str | None = None,
    executive_freshness: str | None = None,
    binding_observed_at: str | None = None,
    binding_freshness: str | None = None,
    effect_state: str = "NONE",
    capacity_state: str = "UNKNOWN",
):
    return module.RuntimeFact(
        responsibility_ref=ref,
        root_job_id=root_job_id,
        seat=getattr(module.Seat, seat),
        attempt_id=attempt_id,
        worker_id=worker_id,
        status=status,
        session_alias="EXECUTIVE-CEO-SOL",
        runtime_binding_id="bind-ocr6-sol-0001",
        binding_generation=2,
        continuation_state="ACKNOWLEDGED",
        effect_state=getattr(module.EffectState, effect_state),
        capacity_state=getattr(module.CapacityState, capacity_state),
        previous_attempt_id="ATT-OCR6-1",
        movement_reason_code="RATE_LIMITED_REALM_MOVE",
        executive_source=_source(
            module,
            "EXECUTIVE_OS",
            f"executive-runtime:{attempt_id}",
            observed_at=executive_observed_at or observed_at,
            freshness=executive_freshness or freshness,
        ),
        binding_source=_source(
            module,
            "RUNTIME_BINDING",
            f"runtime-binding:{attempt_id}",
            observed_at=binding_observed_at or observed_at,
            freshness=binding_freshness or freshness,
        ),
    )


def _blocker(
    module,
    *,
    ref: str = "WS:OCR-6",
    code: str = "SOL_REVIEW_REQUIRED",
    explanation: str = "The exact built head awaits Sol review and may not merge.",
    target: str = "CEO",
    observed_at: str = "2026-08-29T04:43:00Z",
    freshness: str = "CURRENT",
    effect_state: str = "NONE",
):
    return module.BlockerFact(
        responsibility_ref=ref,
        code=code,
        explanation=explanation,
        target_seat=getattr(module.Seat, target),
        effect_state=getattr(module.EffectState, effect_state),
        source=_source(
            module,
            "EXECUTIVE_OS",
            f"executive-event:{code}",
            observed_at=observed_at,
            freshness=freshness,
        ),
    )


def _surface(
    module,
    *,
    ref: str = "WS:OCR-6",
    role: str = "CEO",
    seat_ref: str | None = "chatgpt2",
    surface_ref: str = "11111111-1111-4111-8111-111111111111",
    reviewed_at: str | None = "2026-08-29T04:44:00Z",
    observed_at: str = "2026-08-29T04:44:00Z",
    freshness: str = "CURRENT",
):
    return module.SurfaceFact(
        responsibility_ref=ref,
        role=getattr(module.Seat, role),
        seat_ref=seat_ref,
        surface_ref=surface_ref,
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        reviewed_at=reviewed_at,
        source=_source(
            module,
            "SURFACE_BINDINGS",
            f"surface-binding:{surface_ref}",
            observed_at=observed_at,
            freshness=freshness,
        ),
    )


def _snapshot(module, **overrides):
    values = {
        "responsibilities": (_responsibility(module),),
        "attention": (),
        "runtimes": (),
        "blockers": (),
        "surfaces": (),
        "source_failures": (),
    }
    values.update(overrides)
    return module.ExecutiveStewardSnapshot(**values)


def test_authority_fence_keeps_the_steward_stdlib_only_and_actionless():
    module = _module()
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module != "__future__"
    )
    assert imports <= {"collections", "dataclasses", "enum", "typing"}

    identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    forbidden = {
        "create_job",
        "requeue_job",
        "claim_job",
        "complete_job",
        "complete_attempt",
        "rate_limit_attempt",
        "dispatch",
        "send_message",
        "start",
        "resume",
        "select_capacity",
        "open",
        "write_text",
        "write_bytes",
        "connect",
        "request",
    }
    assert identifiers.isdisjoint(forbidden), sorted(identifiers & forbidden)

    public = {
        name
        for name in dir(module.ExecutiveStewardSnapshot)
        if not name.startswith("_")
    }
    assert public == {
        "blockers",
        "explain_blocker",
        "get_attention",
        "get_current_runtime",
        "get_responsibility",
        "list_responsibilities",
        "resolve_surface",
        "responsibilities",
        "runtimes",
        "source_failures",
        "surfaces",
        "attention",
    }


def test_snapshot_and_facts_are_frozen_and_hold_only_immutable_sequences():
    module = _module()
    snapshot = _snapshot(module)
    assert isinstance(snapshot.responsibilities, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.responsibilities = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.responsibilities[0].title = "changed"


def test_list_responsibilities_is_exact_sorted_and_preserves_source_metadata():
    module = _module()
    alpha = _responsibility(
        module,
        "WS:ALPHA",
        title="Alpha responsibility",
        observed_at="2026-08-29T04:10:00Z",
    )
    alphax = _responsibility(
        module,
        "WS:ALPHA-X",
        title="Alpha responsibility newer",
        observed_at="2026-08-29T04:59:00Z",
        accountable_seat="CHAIRMAN",
        root_job_id="JOB-ALPHA-X",
    )
    result = _snapshot(module, responsibilities=(alphax, alpha)).list_responsibilities()

    assert result.status is module.QueryStatus.OK
    assert [fact.responsibility_ref for fact in result.data] == [
        "WS:ALPHA",
        "WS:ALPHA-X",
    ]
    encoded = result.to_dict()
    assert encoded["data"][0]["source"] == {
        "owner": "agent_os",
        "ref": "agentos/workstreams/WS-ALPHA.md",
        "observed_at": "2026-08-29T04:10:00Z",
        "freshness": "current",
    }


def test_responsibility_lookup_never_uses_title_similarity_or_recency():
    module = _module()
    exact = _responsibility(
        module,
        "WS:ALPHA",
        title="Same visible title",
        observed_at="2026-08-29T04:10:00Z",
    )
    newer_similar = _responsibility(
        module,
        "WS:ALPHA-X",
        title="Same visible title",
        observed_at="2026-08-29T04:59:00Z",
        root_job_id="JOB-ALPHA-X",
    )
    snapshot = _snapshot(module, responsibilities=(newer_similar, exact))

    result = snapshot.get_responsibility("WS:ALPHA")
    assert result.status is module.QueryStatus.OK
    assert result.data is exact
    assert (
        snapshot.get_responsibility("Same visible title").status
        is module.QueryStatus.REFUSED
    )


def test_ambiguous_responsibility_join_refuses_without_selecting_newest():
    module = _module()
    older = _responsibility(module, observed_at="2026-08-29T04:10:00Z")
    newer = _responsibility(module, observed_at="2026-08-29T04:59:00Z", state="blocked")
    result = _snapshot(module, responsibilities=(older, newer)).get_responsibility(
        "WS:OCR-6"
    )

    assert result.status is module.QueryStatus.REFUSED
    assert result.data is None
    assert [issue.code for issue in result.issues] == ["ambiguous_responsibility_join"]
    assert {source.observed_at for source in result.issues[0].sources} == {
        "2026-08-29T04:10:00Z",
        "2026-08-29T04:59:00Z",
    }


def test_missing_and_stale_responsibility_states_remain_typed():
    module = _module()
    missing = _snapshot(module, responsibilities=()).get_responsibility("WS:MISSING")
    stale_fact = _responsibility(module, freshness="STALE")
    stale = _snapshot(module, responsibilities=(stale_fact,)).get_responsibility(
        "WS:OCR-6"
    )

    assert missing.status is module.QueryStatus.UNKNOWN
    assert missing.data is None
    assert stale.status is module.QueryStatus.DEGRADED
    assert stale.data is stale_fact
    assert stale.to_dict()["data"]["source"]["freshness"] == "stale"


def test_attention_answers_exact_sol_and_chairman_needs_without_ranking():
    module = _module()
    ceo = _attention(module, "att-sol", target="CEO")
    chairman = _attention(
        module, "att-chair", target="CHAIRMAN", reason="Chairman ruling required."
    )
    coo = _attention(module, "att-coo", target="COO")
    snapshot = _snapshot(module, attention=(coo, chairman, ceo))

    sol_result = snapshot.get_attention(target_seat=module.Seat.CEO)
    chair_result = snapshot.get_attention(target_seat=module.Seat.CHAIRMAN)
    assert sol_result.status is module.QueryStatus.OK
    assert [item.attention_id for item in sol_result.data] == ["att-sol"]
    assert [item.attention_id for item in chair_result.data] == ["att-chair"]


def test_attention_staleness_is_visible_and_not_replaced_by_last_good():
    module = _module()
    stale = _attention(module, "att-stale", freshness="STALE")
    result = _snapshot(module, attention=(stale,)).get_attention()

    assert result.status is module.QueryStatus.DEGRADED
    assert result.data == (stale,)
    assert [issue.code for issue in result.issues] == ["stale_attention_fact"]


def test_attention_without_exact_agent_os_responsibility_is_not_returned():
    module = _module()
    orphan = _attention(module, "att-orphan", ref="WS:ORPHAN")
    result = _snapshot(
        module,
        responsibilities=(),
        attention=(orphan,),
    ).get_attention()

    assert result.status is module.QueryStatus.DEGRADED
    assert result.data == ()
    assert [issue.code for issue in result.issues] == [
        "attention_responsibility_unknown"
    ]


def test_current_runtime_uses_only_exact_responsibility_and_seat_join():
    module = _module()
    exact = _runtime(
        module,
        ref="WS:ALPHA",
        root_job_id="JOB-ALPHA",
        seat="CEO",
        attempt_id="ATT-EXACT",
    )
    same_provider_newer_wrong_ref = _runtime(
        module,
        ref="WS:ALPHA-X",
        root_job_id="JOB-ALPHA-X",
        seat="CEO",
        attempt_id="ATT-NEWER-WRONG-REF",
        observed_at="2026-08-29T04:59:00Z",
    )
    wrong_seat = _runtime(
        module,
        ref="WS:ALPHA",
        root_job_id="JOB-ALPHA",
        seat="COO",
        attempt_id="ATT-WRONG-SEAT",
    )
    snapshot = _snapshot(
        module,
        responsibilities=(
            _responsibility(module, "WS:ALPHA", root_job_id="JOB-ALPHA"),
            _responsibility(module, "WS:ALPHA-X", root_job_id="JOB-ALPHA-X"),
        ),
        runtimes=(same_provider_newer_wrong_ref, wrong_seat, exact),
    )

    result = snapshot.get_current_runtime("WS:ALPHA", module.Seat.CEO)
    assert result.status is module.QueryStatus.OK
    assert result.data.attempt_id == "ATT-EXACT"
    assert result.to_dict()["data"]["capacity_state"] == "unknown"


def test_runtime_fact_rejects_runtime_binding_as_lifecycle_authority():
    module = _module()
    with pytest.raises(ValueError, match="executive_source owner must be executive_os"):
        dataclasses.replace(
            _runtime(module),
            executive_source=_source(
                module,
                "RUNTIME_BINDING",
                "runtime-binding:cannot-author-lifecycle",
            ),
        )


def test_runtime_fact_rejects_executive_os_as_binding_authority():
    module = _module()
    with pytest.raises(
        ValueError, match="binding_source owner must be runtime_binding"
    ):
        dataclasses.replace(
            _runtime(module),
            binding_source=_source(
                module,
                "EXECUTIVE_OS",
                "executive-runtime:cannot-author-binding",
            ),
        )


def test_runtime_fact_rejects_swapped_source_owner_labels():
    module = _module()
    runtime = _runtime(module)
    with pytest.raises(ValueError, match="executive_source owner must be executive_os"):
        dataclasses.replace(
            runtime,
            executive_source=runtime.binding_source,
            binding_source=runtime.executive_source,
        )


@pytest.mark.parametrize("missing_field", ("executive_source", "binding_source"))
def test_runtime_fact_requires_both_exact_source_halves(missing_field):
    module = _module()
    with pytest.raises(TypeError, match=rf"{missing_field} must be SourceRef"):
        dataclasses.replace(_runtime(module), **{missing_field: None})


@pytest.mark.parametrize(
    ("stale_field", "stale_owner"),
    (
        ("executive_source", "EXECUTIVE_OS"),
        ("binding_source", "RUNTIME_BINDING"),
    ),
)
def test_stale_runtime_source_half_never_claims_a_current_operator(
    stale_field, stale_owner
):
    module = _module()
    runtime = _runtime(module)
    stale_source = _source(
        module,
        stale_owner,
        f"{stale_owner.lower()}:stale",
        freshness="STALE",
    )
    result = _snapshot(
        module,
        runtimes=(dataclasses.replace(runtime, **{stale_field: stale_source}),),
    ).get_current_runtime("WS:OCR-6", module.Seat.CEO)

    assert result.status is module.QueryStatus.DEGRADED
    assert result.data is None
    assert [issue.code for issue in result.issues] == ["stale_runtime_join"]
    assert {source.owner for source in result.issues[0].sources} == {
        module.SourceOwner.AGENT_OS,
        module.SourceOwner.EXECUTIVE_OS,
        module.SourceOwner.RUNTIME_BINDING,
    }


@pytest.mark.parametrize(
    ("ambiguous_field", "owner"),
    (
        ("executive_source", "EXECUTIVE_OS"),
        ("binding_source", "RUNTIME_BINDING"),
    ),
)
def test_ambiguous_runtime_source_half_refuses_without_selecting_a_winner(
    ambiguous_field, owner
):
    module = _module()
    first = _runtime(module)
    alternate_source = _source(
        module,
        owner,
        f"{owner.lower()}:alternate",
        observed_at="2026-08-29T04:59:00Z",
    )
    second = dataclasses.replace(first, **{ambiguous_field: alternate_source})
    result = _snapshot(module, runtimes=(first, second)).get_current_runtime(
        "WS:OCR-6", module.Seat.CEO
    )

    assert result.status is module.QueryStatus.REFUSED
    assert result.data is None
    assert [issue.code for issue in result.issues] == ["ambiguous_runtime_join"]
    assert {source.owner for source in result.issues[0].sources} == {
        module.SourceOwner.EXECUTIVE_OS,
        module.SourceOwner.RUNTIME_BINDING,
    }


def test_runtime_wrong_root_refuses_even_when_workstream_seat_and_provider_match():
    module = _module()
    responsibility = _responsibility(module, root_job_id="JOB-OCR6")
    wrong_root = _runtime(module, root_job_id="JOB-DIFFERENT")
    result = _snapshot(
        module,
        responsibilities=(responsibility,),
        runtimes=(wrong_root,),
    ).get_current_runtime("WS:OCR-6", module.Seat.CEO)

    assert result.status is module.QueryStatus.REFUSED
    assert result.data is None
    assert [issue.code for issue in result.issues] == ["runtime_root_mismatch"]


def test_ambiguous_or_stale_runtime_never_claims_a_current_operator():
    module = _module()
    first = _runtime(module, attempt_id="ATT-1")
    second = _runtime(module, attempt_id="ATT-2", observed_at="2026-08-29T04:59:00Z")
    ambiguous = _snapshot(module, runtimes=(first, second)).get_current_runtime(
        "WS:OCR-6", module.Seat.CEO
    )
    stale = _snapshot(
        module,
        runtimes=(_runtime(module, freshness="STALE"),),
    ).get_current_runtime("WS:OCR-6", module.Seat.CEO)

    assert ambiguous.status is module.QueryStatus.REFUSED
    assert ambiguous.data is None
    assert [issue.code for issue in ambiguous.issues] == ["ambiguous_runtime_join"]
    assert stale.status is module.QueryStatus.DEGRADED
    assert stale.data is None
    assert {source.freshness for source in stale.issues[0].sources} == {
        module.Freshness.CURRENT,
        module.Freshness.STALE,
    }


def test_effect_unknown_runtime_is_reconciliation_required_and_not_current():
    module = _module()
    runtime = _runtime(module, effect_state="EFFECT_UNKNOWN")
    result = _snapshot(module, runtimes=(runtime,)).get_current_runtime(
        "WS:OCR-6", module.Seat.CEO
    )

    assert result.status is module.QueryStatus.REFUSED
    assert result.data is None
    assert [issue.code for issue in result.issues] == ["reconciliation_required"]


def test_missing_optional_capacity_stays_unknown_without_degrading_runtime():
    module = _module()
    runtime = _runtime(module, capacity_state="UNKNOWN")
    result = _snapshot(module, runtimes=(runtime,)).get_current_runtime(
        "WS:OCR-6", module.Seat.CEO
    )

    assert result.status is module.QueryStatus.OK
    assert result.data.capacity_state is module.CapacityState.UNKNOWN


def test_current_runtime_preserves_opaque_where_running_facts_without_using_them_as_keys():
    module = _module()
    runtime = dataclasses.replace(
        _runtime(module),
        reasoning_surface="chatgpt-sol",
        account_label="chatgpt-seat-2",
        host_ref="host-opaque-studio",
        provider_session_id_present=True,
    )
    result = _snapshot(module, runtimes=(runtime,)).get_current_runtime(
        "WS:OCR-6", module.Seat.CEO
    )

    assert result.status is module.QueryStatus.OK
    expected = {
        "reasoning_surface": "chatgpt-sol",
        "account_label": "chatgpt-seat-2",
        "host_ref": "host-opaque-studio",
        "provider_session_id_present": True,
    }
    assert expected.items() <= result.to_dict()["data"].items()


def test_capacity_source_failure_is_attributed_without_erasing_exact_runtime():
    module = _module()
    failure = module.SourceFailure(
        owner=module.SourceOwner.CAPACITY,
        code="capacity_source_unavailable",
        explanation="Optional capacity evidence could not be read.",
        source_ref="capacity:projection",
        observed_at="2026-08-29T04:45:00Z",
    )
    result = _snapshot(
        module,
        runtimes=(_runtime(module),),
        source_failures=(failure,),
    ).get_current_runtime("WS:OCR-6", module.Seat.CEO)

    assert result.status is module.QueryStatus.DEGRADED
    assert result.data.attempt_id == "ATT-OCR6-2"
    assert result.data.capacity_state is module.CapacityState.UNKNOWN
    assert [issue.code for issue in result.issues] == ["capacity_source_unavailable"]


def test_current_source_ref_requires_an_observation_timestamp():
    module = _module()
    with pytest.raises(ValueError, match="observed_at"):
        module.SourceRef(
            owner=module.SourceOwner.AGENT_OS,
            ref="agentos/workstreams/WS-OCR-6.md",
            observed_at=None,
            freshness=module.Freshness.CURRENT,
        )

    unknown = module.SourceRef(
        owner=module.SourceOwner.AGENT_OS,
        ref="agent-os:unavailable",
        observed_at=None,
        freshness=module.Freshness.UNKNOWN,
    )
    assert unknown.observed_at is None


def test_blocker_explanation_returns_only_source_authored_reason_and_movement_code():
    module = _module()
    blocker = _blocker(
        module,
        code="RATE_LIMITED_REALM_MOVE",
        explanation="The previous Attempt ended RATE_LIMITED; the exact replacement is awaiting review.",
    )
    result = _snapshot(module, blockers=(blocker,)).explain_blocker("WS:OCR-6")

    assert result.status is module.QueryStatus.OK
    assert result.data is blocker
    assert result.to_dict()["data"]["code"] == "RATE_LIMITED_REALM_MOVE"
    assert "awaiting review" in result.to_dict()["data"]["explanation"]


def test_effect_unknown_blocker_preserves_explanation_but_requires_reconciliation():
    module = _module()
    blocker = _blocker(module, effect_state="EFFECT_UNKNOWN")
    result = _snapshot(module, blockers=(blocker,)).explain_blocker("WS:OCR-6")

    assert result.status is module.QueryStatus.REFUSED
    assert result.data is blocker
    assert [issue.code for issue in result.issues] == ["reconciliation_required"]


def test_stale_responsibility_degrades_source_authored_blocker_explanation():
    module = _module()
    blocker = _blocker(module)
    result = _snapshot(
        module,
        responsibilities=(_responsibility(module, freshness="STALE"),),
        blockers=(blocker,),
    ).explain_blocker("WS:OCR-6")

    assert result.status is module.QueryStatus.DEGRADED
    assert result.data is blocker
    assert [issue.code for issue in result.issues] == ["stale_blocker_join"]


def test_surface_resolution_returns_one_exact_reviewed_binding_only():
    module = _module()
    exact = _surface(module, ref="WS:ALPHA", seat_ref="chatgpt2")
    newer_wrong_ref = _surface(
        module,
        ref="WS:ALPHA-X",
        seat_ref="chatgpt2",
        surface_ref="22222222-2222-4222-8222-222222222222",
        observed_at="2026-08-29T04:59:00Z",
    )
    result = _snapshot(
        module,
        responsibilities=(
            _responsibility(module, "WS:ALPHA", root_job_id="JOB-ALPHA"),
        ),
        surfaces=(newer_wrong_ref, exact),
    ).resolve_surface("WS:ALPHA", module.Seat.CEO, seat_ref="chatgpt2")

    assert result.status is module.QueryStatus.OK
    assert result.data is exact
    assert result.to_dict()["data"]["surface_ref"] == exact.surface_ref


def test_unreviewed_stale_or_ambiguous_surface_returns_no_surface_ref():
    module = _module()
    unreviewed = _snapshot(
        module,
        surfaces=(_surface(module, reviewed_at=None),),
    ).resolve_surface("WS:OCR-6", module.Seat.CEO)
    stale = _snapshot(
        module,
        surfaces=(_surface(module, freshness="STALE"),),
    ).resolve_surface("WS:OCR-6", module.Seat.CEO)
    ambiguous = _snapshot(
        module,
        surfaces=(
            _surface(module, surface_ref="11111111-1111-4111-8111-111111111111"),
            _surface(module, surface_ref="22222222-2222-4222-8222-222222222222"),
        ),
    ).resolve_surface("WS:OCR-6", module.Seat.CEO)

    assert unreviewed.status is module.QueryStatus.REFUSED
    assert stale.status is module.QueryStatus.DEGRADED
    assert ambiguous.status is module.QueryStatus.REFUSED
    assert unreviewed.data is stale.data is ambiguous.data is None
    for result in (unreviewed, stale, ambiguous):
        assert result.to_dict()["data"] is None


def test_exact_seat_ref_disambiguates_reviewed_surfaces_without_guessing():
    module = _module()
    seat_one = _surface(
        module,
        seat_ref="chatgpt1",
        surface_ref="11111111-1111-4111-8111-111111111111",
    )
    seat_two = _surface(
        module,
        seat_ref="chatgpt2",
        surface_ref="22222222-2222-4222-8222-222222222222",
    )
    snapshot = _snapshot(module, surfaces=(seat_two, seat_one))

    without_seat = snapshot.resolve_surface("WS:OCR-6", module.Seat.CEO)
    with_seat = snapshot.resolve_surface(
        "WS:OCR-6", module.Seat.CEO, seat_ref="chatgpt2"
    )
    assert without_seat.status is module.QueryStatus.REFUSED
    assert without_seat.data is None
    assert with_seat.status is module.QueryStatus.OK
    assert with_seat.data.surface_ref == seat_two.surface_ref


def test_named_source_failure_degrades_instead_of_fabricating_last_good():
    module = _module()
    failure = module.SourceFailure(
        owner=module.SourceOwner.RUNTIME_BINDING,
        code="source_unavailable",
        explanation="RuntimeBinding source could not be read.",
        source_ref="runtime-binding:reader",
        observed_at="2026-08-29T04:45:00Z",
    )
    result = _snapshot(
        module,
        runtimes=(),
        source_failures=(failure,),
    ).get_current_runtime("WS:OCR-6", module.Seat.CEO)

    assert result.status is module.QueryStatus.DEGRADED
    assert result.data is None
    assert result.to_dict()["issues"] == [
        {
            "code": "source_unavailable",
            "message": "RuntimeBinding source could not be read.",
            "sources": [
                {
                    "owner": "runtime_binding",
                    "ref": "runtime-binding:reader",
                    "observed_at": "2026-08-29T04:45:00Z",
                    "freshness": "unknown",
                }
            ],
        }
    ]


def test_agent_os_source_failure_degrades_runtime_identity_join():
    module = _module()
    failure = module.SourceFailure(
        owner=module.SourceOwner.AGENT_OS,
        code="source_unavailable",
        explanation="Agent OS responsibility source could not be read.",
        source_ref="agent-os:reader",
        observed_at="2026-08-29T04:45:00Z",
    )
    result = _snapshot(
        module,
        responsibilities=(),
        runtimes=(_runtime(module),),
        source_failures=(failure,),
    ).get_current_runtime("WS:OCR-6", module.Seat.CEO)

    assert result.status is module.QueryStatus.DEGRADED
    assert result.data is None
    assert [issue.code for issue in result.issues] == ["source_unavailable"]


def test_stale_responsibility_prevents_surface_resolution():
    module = _module()
    result = _snapshot(
        module,
        responsibilities=(_responsibility(module, freshness="STALE"),),
        surfaces=(_surface(module),),
    ).resolve_surface("WS:OCR-6", module.Seat.CEO)

    assert result.status is module.QueryStatus.DEGRADED
    assert result.data is None
    assert [issue.code for issue in result.issues] == ["stale_surface_join"]


def test_same_facts_in_different_input_order_produce_identical_results():
    module = _module()
    responsibilities = (
        _responsibility(module, "WS:ALPHA", root_job_id="JOB-ALPHA"),
        _responsibility(module, "WS:BETA", root_job_id="JOB-BETA"),
    )
    attention = (
        _attention(module, "att-b", ref="WS:BETA"),
        _attention(module, "att-a", ref="WS:ALPHA"),
    )
    left = _snapshot(module, responsibilities=responsibilities, attention=attention)
    right = _snapshot(
        module,
        responsibilities=tuple(reversed(responsibilities)),
        attention=tuple(reversed(attention)),
    )

    assert (
        left.list_responsibilities().to_dict()
        == right.list_responsibilities().to_dict()
    )
    assert left.get_attention().to_dict() == right.get_attention().to_dict()

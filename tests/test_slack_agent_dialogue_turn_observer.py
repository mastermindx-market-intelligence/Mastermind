from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from dataclasses import replace
from unittest.mock import patch

from control_plane.session_targets import load_session_targets, route_obligation
from control_plane.dialogue_source_resolution import (
    DialogueDelayedAckReconciler,
    DialogueSourceObservation,
    DialogueSourceReconciler,
    DialogueSourceSnapshot,
)
from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    PARENT_DISCRIMINATOR_V2,
    TURN_WATCH_MODE_V1,
    build_message_v2,
    build_parent_v2,
    render_message_v2,
    render_parent_v2,
)
from integrations.slack_agent_dialogue.engine import DialoguePolicy, SlackMessage
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.turn_observer import (
    DialogueTurnObserver,
    ObservationOutcome,
    WakeCarrierState,
)
from integrations.slack_agent_dialogue.turn_wake_adapter import (
    attention_to_wake_obligation,
)
from integrations.slack_agent_dialogue.turn_watcher import (
    AgentDialogueAttention,
    TurnAction,
    TurnDecision,
    TurnRoutingFacts,
    classify_turn,
)


REPO = "mastermindx-market-intelligence/Mastermind"
PARENT_TS = "1787961600.000001"
PARENT_USER = "U0PARENT001"
SOL_USER = "U0BRETDUAS2"
RELAY_USER = "U0RELAY001"
CHANNEL = "C0DIALOGUE1"


def _commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "c" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
    }


def _parent() -> dict[str, object]:
    return build_parent_v2(
        {
            "schema": "mastermind.agent_dialogue_parent.v2",
            "work_ref": "WS:WORKER-PRESENCE",
            "commission_ref": _commission(),
            "session_ref": "asd-session-turnwatch0002",
            "operation_key": "worker-presence-dialogue-wptw2-20260829-001",
            "watch_mode": TURN_WATCH_MODE_V1,
            "allowed_sol_user_ids": [SOL_USER],
            "created_at": "2026-08-29T01:00:00Z",
        }
    )


def _context(parent: dict[str, object]) -> DialogueContextV2:
    return DialogueContextV2(
        work_ref=str(parent["work_ref"]),
        commission_ref=copy.deepcopy(parent["commission_ref"]),
        session_ref=str(parent["session_ref"]),
        operation_key=str(parent["operation_key"]),
        watch_mode=str(parent["watch_mode"]),
        actor_ref={
            "kind": "executive_surface",
            "seat": "coo",
            "reasoning_surface": "claude",
        },
        applies_to={
            "kind": "repository",
            "repository": REPO,
            "head_sha": "a" * 40,
            "pr": f"{REPO}#209",
        },
    )


def _routing(parent: dict[str, object]) -> TurnRoutingFacts:
    return TurnRoutingFacts(
        bound_operation_key=str(parent["operation_key"]),
        bound_commission_fingerprint=str(parent["fingerprint"]),
        root_job_id="JOB-001",
        routing_workstream=None,
        source_workstream="WS:WORKER-PRESENCE",
        ceo_target_bound=True,
        coo_target_bound=True,
    )


def _policy() -> DialoguePolicy:
    return DialoguePolicy(
        workspace_id="T0DIALOGUE1",
        channel_id=CHANNEL,
        relay_bot_user_id=RELAY_USER,
        allowed_sol_user_ids=(SOL_USER,),
        allowed_parent_user_ids=(PARENT_USER,),
        max_channel_history=10,
        max_thread_history=10,
        method_timeout_seconds=1.0,
    )


def _client(
    parent: dict[str, object], *, parent_author: str = PARENT_USER
) -> InMemorySlackClient:
    client = InMemorySlackClient(relay_bot_user_id=RELAY_USER)
    client.add_parent(
        SlackMessage(
            ts=PARENT_TS,
            author_user_id=parent_author,
            text=render_parent_v2(parent),
        )
    )
    return client


def _result(
    parent: dict[str, object],
    *,
    applies_to: dict[str, object] | None = None,
) -> dict[str, object]:
    message_applies_to = applies_to or {
        "kind": "repository",
        "repository": REPO,
        "head_sha": "a" * 40,
        "pr": f"{REPO}#209",
    }
    return build_message_v2(
        {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": "asd-result-00000002",
            "message_type": "RESULT",
            "work_ref": parent["work_ref"],
            "commission_ref": copy.deepcopy(parent["commission_ref"]),
            "session_ref": parent["session_ref"],
            "actor_ref": {
                "kind": "executive_surface",
                "seat": "coo",
                "reasoning_surface": "claude",
            },
            "reply_to_message_key": None,
            "applies_to": copy.deepcopy(message_applies_to),
            "summary": "The bounded classifier passed.",
            "body": {
                "status": "PASS",
                "result": "WP-TW1 source classification is complete.",
            },
            "evidence_refs": [
                f"https://github.com/{REPO}/pull/209",
            ],
            "requires_response": False,
            "created_at": "2026-08-29T01:01:00Z",
        }
    )


def _client_with_result(parent: dict[str, object]) -> InMemorySlackClient:
    client = _client(parent)
    client.add_reply(
        SlackMessage(
            ts="1787961600.000002",
            author_user_id=RELAY_USER,
            text=render_message_v2(_result(parent)),
            thread_ts=PARENT_TS,
        )
    )
    return client


def _registry():
    return load_session_targets().with_root_job_bindings(
        {
            "JOB-001": {
                "ceo": "EXECUTIVE-CEO-A",
                "coo": "EXECUTIVE-COO-A",
            }
        }
    )


@dataclass
class RecordingWakeCarrier:
    reconciliation: WakeCarrierState = WakeCarrierState.MISSING
    effect_unknown: bool = False
    reconcile_calls: list[tuple[object, object]] = field(default_factory=list)
    submit_calls: list[tuple[object, object]] = field(default_factory=list)

    async def reconcile(self, obligation, route) -> WakeCarrierState:
        self.reconcile_calls.append((obligation, route))
        return self.reconciliation

    async def submit(self, obligation, route) -> None:
        self.submit_calls.append((obligation, route))
        if self.effect_unknown:
            raise WakeEffectUnknownError("provider result is ambiguous")


class SourceAwareRecordingWakeCarrier(DialogueSourceReconciler, RecordingWakeCarrier):
    def __init__(self, source_state: str) -> None:
        RecordingWakeCarrier.__init__(self)
        self.source_state = source_state
        self.source_calls: list[DialogueSourceSnapshot] = []

    async def reconcile_dialogue_sources(self, snapshot: object) -> object:
        assert type(snapshot) is DialogueSourceSnapshot
        self.source_calls.append(snapshot)
        return {"state": self.source_state, "reason": "TEST_SOURCE_STATE"}

    async def reconcile_from_source(self, _source, obligation, route) -> WakeCarrierState:
        return await self.reconcile(obligation, route)

    async def submit_from_source(self, _source, obligation, route) -> None:
        await self.submit(obligation, route)


class DelayedAckRecordingCarrier(
    DialogueDelayedAckReconciler, SourceAwareRecordingWakeCarrier
):
    def __init__(self, source: DialogueSourceObservation) -> None:
        SourceAwareRecordingWakeCarrier.__init__(self, "ACK_REQUIRED")
        self.source = source
        self.delayed_ack_calls = []

    async def reconcile_dialogue_sources(self, snapshot: object) -> object:
        self.source_calls.append(snapshot)
        return {
            "state": "ACK_REQUIRED", "reason": "DELIVERED_ACK_PENDING",
            "source_observation": self.source,
        }

    async def reconcile_delayed_ack(self, source_observation):
        self.delayed_ack_calls.append(source_observation)
        return {"state": "RECORDED", "reason": "ACK_RECORDED"}


def test_observer_echoes_server_selected_delayed_ack_once_then_holds() -> None:
    async def scenario() -> None:
        parent = _parent()
        source = DialogueSourceObservation(
            workspace_id="T0BRD2AQXQV", channel_id="C0BSBM78V1N",
            thread_ts=PARENT_TS, predecessor_message_key="asd-old-source-01",
            predecessor_message_fingerprint="e" * 64,
        )
        carrier = DelayedAckRecordingCarrier(source)
        observer = DialogueTurnObserver(
            policy=_policy(), client=_client_with_result(parent),
            registry=_registry(), wake_carrier=carrier,
        )
        result = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        assert result.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
        assert result.reason == "DIALOGUE_SOURCE_RECONCILIATION_REQUIRED"
        assert carrier.delayed_ack_calls == [source]
        assert len(carrier.source_calls) == 1
        assert carrier.reconcile_calls == []
        assert carrier.submit_calls == []

    asyncio.run(scenario())


def _attention() -> AgentDialogueAttention:
    return AgentDialogueAttention(
        schema="mastermind.agent_dialogue_attention.v1",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "a" * 64,
        source_dialogue_schema="mastermind.agent_dialogue.v2",
        message_key="asd-result-00000001",
        message_fingerprint="b" * 64,
        commission_fingerprint="c" * 64,
        operation_key="worker-presence-dialogue-wptw2-20260829-001",
        target_seat="ceo",
        attention_kind="dialogue_turn_pending",
        root_job_id="JOB-001",
        routing_workstream=None,
        source_workstream="WS:WORKER-PRESENCE",
        evidence_refs=(
            "https://github.com/mastermindx-market-intelligence/Mastermind/pull/209",
        ),
    )


def test_attention_adapts_to_one_deterministic_canonical_wake_obligation() -> None:
    attention = _attention()

    first = attention_to_wake_obligation(
        attention,
        emitted_at="2026-08-29T01:00:00Z",
    )
    restarted = attention_to_wake_obligation(
        attention,
        emitted_at="2026-08-29T01:05:00Z",
    )

    assert first.source_kind.value == "agent_dialogue_attention"
    assert first.wake_kind.value == "dialogue_turn_pending"
    assert first.source_ref == attention.source_ref
    assert first.declared_target_seat == "ceo"
    assert first.root_job_id == "JOB-001"
    assert first.workstream is None
    assert first.source_workstream == "WS:WORKER-PRESENCE"
    assert first.evidence_refs == (attention.source_ref, "JOB-001")
    assert first.obligation_id == restarted.obligation_id
    assert first.emitted_at != restarted.emitted_at


def test_adapter_preserves_existing_root_workstream_seat_routing_precedence() -> None:
    root_attention = _attention()
    root_obligation = attention_to_wake_obligation(
        root_attention, emitted_at="2026-08-29T01:00:00Z"
    )
    root_route = route_obligation(root_obligation, _registry())
    assert root_route.session_alias == "EXECUTIVE-CEO-A"
    assert root_route.root_job_id == "JOB-001"

    workstream_attention = replace(
        root_attention,
        source_ref="agent_dialogue_attention:" + "e" * 64,
        target_seat="coo",
        root_job_id=None,
        routing_workstream="terminal",
    )
    workstream_obligation = attention_to_wake_obligation(
        workstream_attention, emitted_at="2026-08-29T01:00:00Z"
    )
    workstream_route = route_obligation(workstream_obligation, load_session_targets())
    assert workstream_route.session_alias == "TERMINAL-COO-A"
    assert workstream_route.workstream == "terminal"

    seat_attention = replace(
        root_attention,
        source_ref="agent_dialogue_attention:" + "f" * 64,
        root_job_id=None,
        routing_workstream=None,
    )
    seat_obligation = attention_to_wake_obligation(
        seat_attention, emitted_at="2026-08-29T01:00:00Z"
    )
    seat_route = route_obligation(seat_obligation, load_session_targets())
    assert seat_route.session_alias == "EXECUTIVE-CEO-A"
    assert seat_route.root_job_id is None
    assert seat_route.workstream is None


def test_observer_reconstructs_initial_turn_and_submits_one_canonical_wake() -> None:
    async def scenario() -> None:
        parent = _parent()
        carrier = RecordingWakeCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent),
            registry=_registry(),
            wake_carrier=carrier,
            emitted_at=lambda: "2026-08-29T01:02:00Z",
        )

        result = await observer.reconcile_once(
            context=_context(parent),
            routing=_routing(parent),
        )

        assert result.outcome is ObservationOutcome.WAKE_SUBMITTED
        assert result.obligation is not None
        assert result.obligation.wake_kind.value == "dialogue_turn_pending"
        assert result.route is not None
        assert result.route.target_seat == "coo"
        assert len(carrier.reconcile_calls) == 1
        assert carrier.submit_calls == [(result.obligation, result.route)]

    asyncio.run(scenario())


def test_nominal_source_reconciler_receives_exact_history_before_wake_decision() -> None:
    async def scenario() -> None:
        parent = _parent()
        carrier = SourceAwareRecordingWakeCarrier("NO_RESOLUTION_REQUIRED")
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent),
            registry=_registry(),
            wake_carrier=carrier,
            emitted_at=lambda: "2026-08-29T01:02:00Z",
        )
        result = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        assert result.outcome is ObservationOutcome.WAKE_SUBMITTED
        assert len(carrier.source_calls) == 1
        snapshot = carrier.source_calls[0]
        assert snapshot.workspace_id == _policy().workspace_id
        assert snapshot.channel_id == _policy().channel_id
        assert snapshot.thread_ts == PARENT_TS
        assert snapshot.parent_fingerprint == parent["fingerprint"]
        assert snapshot.operation_key == parent["operation_key"]
        assert snapshot.messages == ()
        assert len(carrier.submit_calls) == 1

        held = SourceAwareRecordingWakeCarrier("ACK_REQUIRED")
        held_observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client_with_result(parent),
            registry=_registry(),
            wake_carrier=held,
            emitted_at=lambda: "2026-08-29T01:02:00Z",
        )
        held_result = await held_observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        assert held_result.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
        assert held_result.reason == "DIALOGUE_SOURCE_RECONCILIATION_REQUIRED"
        assert len(held.source_calls) == 1
        assert [
            item.to_dict()["message_key"] for item in held.source_calls[0].messages
        ] == ["asd-result-00000002"]
        assert held.reconcile_calls == []
        assert held.submit_calls == []

    asyncio.run(scenario())


def test_configured_relay_authored_parent_reaches_existing_classifier_and_wake() -> None:
    async def scenario() -> None:
        parent = _parent()
        carrier = RecordingWakeCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent, parent_author=RELAY_USER),
            registry=_registry(),
            wake_carrier=carrier,
            emitted_at=lambda: "2026-08-29T01:02:00Z",
        )

        result = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert result.outcome is ObservationOutcome.WAKE_SUBMITTED
        assert result.obligation is not None
        assert len(carrier.reconcile_calls) == 1
        assert carrier.submit_calls == [(result.obligation, result.route)]

    asyncio.run(scenario())


def test_legacy_and_relay_duplicate_full_parent_identity_is_ambiguous_without_wake() -> None:
    async def scenario() -> None:
        parent = _parent()
        client = _client(parent)
        client.add_parent(
            SlackMessage(
                ts="1787961600.000003",
                author_user_id=RELAY_USER,
                text=render_parent_v2(parent),
            )
        )
        carrier = RecordingWakeCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(), client=client, registry=_registry(), wake_carrier=carrier
        )

        result = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert result.outcome is ObservationOutcome.REFUSED
        assert result.reason == "THREAD_BINDING_AMBIGUOUS"
        assert carrier.reconcile_calls == []
        assert carrier.submit_calls == []

    asyncio.run(scenario())


def test_arbitrary_bot_and_malformed_relay_parent_refuse_without_wake() -> None:
    async def scenario() -> None:
        parent = _parent()
        for author, text, reason in (
            ("U0ARBITRARYBOT", render_parent_v2(parent), "THREAD_BINDING_AMBIGUOUS"),
            (RELAY_USER, f"{PARENT_DISCRIMINATOR_V2}{{malformed", "PARENT_MESSAGE_INVALID"),
        ):
            client = InMemorySlackClient(relay_bot_user_id=RELAY_USER)
            client.add_parent(
                SlackMessage(ts=PARENT_TS, author_user_id=author, text=text)
            )
            carrier = RecordingWakeCarrier()
            observer = DialogueTurnObserver(
                policy=_policy(),
                client=client,
                registry=_registry(),
                wake_carrier=carrier,
            )

            result = await observer.reconcile_once(
                context=_context(parent), routing=_routing(parent)
            )

            assert result.outcome is ObservationOutcome.REFUSED
            assert result.reason == reason
            assert carrier.reconcile_calls == []
            assert carrier.submit_calls == []

    asyncio.run(scenario())


def test_relay_parent_without_creation_mutation_evidence_refuses_without_wake() -> None:
    async def scenario() -> None:
        parent = _parent()
        for edited, deleted in ((True, False), (False, True)):
            client = InMemorySlackClient(relay_bot_user_id=RELAY_USER)
            client.add_parent(
                SlackMessage(
                    ts=PARENT_TS,
                    author_user_id=RELAY_USER,
                    text=render_parent_v2(parent),
                    edited=edited,
                    deleted=deleted,
                    created_text=None,
                )
            )
            carrier = RecordingWakeCarrier()
            observer = DialogueTurnObserver(
                policy=_policy(),
                client=client,
                registry=_registry(),
                wake_carrier=carrier,
            )

            result = await observer.reconcile_once(
                context=_context(parent), routing=_routing(parent)
            )

            assert result.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
            assert result.reason == "MUTATION_RECONCILIATION_INCOMPLETE"
            assert carrier.reconcile_calls == []
            assert carrier.submit_calls == []

    asyncio.run(scenario())


def test_relay_parent_with_creation_mutation_evidence_uses_original_and_wakes() -> None:
    async def scenario() -> None:
        parent = _parent()
        for edited, deleted in ((True, False), (False, True)):
            client = InMemorySlackClient(relay_bot_user_id=RELAY_USER)
            client.add_parent(
                SlackMessage(
                    ts=PARENT_TS,
                    author_user_id=RELAY_USER,
                    text=f"{PARENT_DISCRIMINATOR_V2}{{malformed",
                    edited=edited,
                    deleted=deleted,
                    created_text=render_parent_v2(parent),
                )
            )
            carrier = RecordingWakeCarrier()
            observer = DialogueTurnObserver(
                policy=_policy(),
                client=client,
                registry=_registry(),
                wake_carrier=carrier,
            )

            result = await observer.reconcile_once(
                context=_context(parent), routing=_routing(parent)
            )

            assert result.outcome is ObservationOutcome.WAKE_SUBMITTED
            assert result.obligation is not None
            assert len(carrier.reconcile_calls) == 1
            assert carrier.submit_calls == [(result.obligation, result.route)]

    asyncio.run(scenario())


def test_observer_refuses_valid_foreign_repository_pr_before_wake_carrier() -> None:
    async def scenario() -> None:
        parent = _parent()
        client = _client(parent)
        client.add_reply(
            SlackMessage(
                ts="1787961600.000002",
                author_user_id=RELAY_USER,
                text=render_message_v2(
                    _result(
                        parent,
                        applies_to={
                            "kind": "repository",
                            "repository": "mastermindx-market-intelligence/macro",
                            "head_sha": "d" * 40,
                            "pr": "mastermindx-market-intelligence/macro#999",
                        },
                    )
                ),
                thread_ts=PARENT_TS,
            )
        )
        carrier = RecordingWakeCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=client,
            registry=_registry(),
            wake_carrier=carrier,
        )

        result = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert result.outcome is ObservationOutcome.REFUSED
        assert result.reason == "DIALOGUE_APPLICABILITY_CARRIER_MISMATCH"
        assert result.decision is None
        assert carrier.reconcile_calls == []
        assert carrier.submit_calls == []

    asyncio.run(scenario())


def test_duplicate_polling_and_restart_reconcile_by_identity_not_cursor() -> None:
    async def scenario() -> None:
        parent = _parent()
        carrier = RecordingWakeCarrier()
        first_life = DialogueTurnObserver(
            policy=_policy(),
            client=_client_with_result(parent),
            registry=_registry(),
            wake_carrier=carrier,
            emitted_at=lambda: "2026-08-29T01:02:00Z",
        )

        first = await first_life.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        duplicate_poll = await first_life.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert first.outcome is ObservationOutcome.WAKE_SUBMITTED
        assert duplicate_poll.outcome is ObservationOutcome.DUPLICATE_SUPPRESSED
        assert first.obligation is not None
        assert duplicate_poll.obligation is not None
        assert first.obligation.obligation_id == duplicate_poll.obligation.obligation_id
        assert len(carrier.submit_calls) == 1

        carrier.reconciliation = WakeCarrierState.RECORDED
        restarted = DialogueTurnObserver(
            policy=_policy(),
            client=_client_with_result(parent),
            registry=_registry(),
            wake_carrier=carrier,
            emitted_at=lambda: "2026-08-29T01:10:00Z",
        )
        after_restart = await restarted.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert after_restart.outcome is ObservationOutcome.DUPLICATE_SUPPRESSED
        assert after_restart.obligation is not None
        assert after_restart.obligation.obligation_id == first.obligation.obligation_id
        assert len(carrier.submit_calls) == 1

    asyncio.run(scenario())


def test_active_waiter_suppresses_only_the_exact_attention_target() -> None:
    async def scenario() -> None:
        parent = _parent()
        attention = classify_turn(
            parent=parent,
            messages=(),
            routing=_routing(parent),
        ).attention
        assert attention is not None
        probes: list[tuple[str, str]] = []

        def exact_waiter(source_ref: str, target_seat: str) -> bool:
            probes.append((source_ref, target_seat))
            return (source_ref, target_seat) == (
                attention.source_ref,
                attention.target_seat,
            )

        carrier = RecordingWakeCarrier()
        suppressed = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent),
            registry=_registry(),
            wake_carrier=carrier,
            has_active_waiter=exact_waiter,
        )
        result = await suppressed.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert result.outcome is ObservationOutcome.ACTIVE_WAITER_SUPPRESSED
        assert probes == [(attention.source_ref, "coo")]
        assert carrier.reconcile_calls == []
        assert carrier.submit_calls == []

        wrong_target_waiter = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent),
            registry=_registry(),
            wake_carrier=carrier,
            has_active_waiter=lambda source_ref, target_seat: (
                source_ref,
                target_seat,
            )
            == (attention.source_ref, "ceo"),
        )
        not_suppressed = await wrong_target_waiter.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        assert not_suppressed.outcome is ObservationOutcome.WAKE_SUBMITTED
        assert len(carrier.submit_calls) == 1

    asyncio.run(scenario())


def test_incomplete_bounded_history_refuses_before_wake_carrier() -> None:
    async def scenario() -> None:
        parent = _parent()
        client = _client(parent)
        client.thread_history_complete = False
        carrier = RecordingWakeCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=client,
            registry=_registry(),
            wake_carrier=carrier,
        )

        result = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert result.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
        assert result.reason == "BOUNDED_HISTORY_INCOMPLETE"
        assert carrier.reconcile_calls == []
        assert carrier.submit_calls == []

    asyncio.run(scenario())


def test_source_outage_and_text_only_reply_cannot_prove_source_absence() -> None:
    async def scenario() -> None:
        parent = _parent()

        class OutageClient(InMemorySlackClient):
            async def fetch_channel_history(self, *_args, **_kwargs):
                raise TimeoutError("diagnostic Slack outage")

        outage_carrier = SourceAwareRecordingWakeCarrier("RECORDED")
        outage = DialogueTurnObserver(
            policy=_policy(),
            client=OutageClient(relay_bot_user_id=RELAY_USER),
            registry=_registry(),
            wake_carrier=outage_carrier,
        )
        outage_result = await outage.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        assert outage_result.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
        assert outage_result.reason == "TRANSPORT_UNAVAILABLE"
        assert outage_carrier.source_calls == []
        assert outage_carrier.reconcile_calls == []
        assert outage_carrier.submit_calls == []

        text_client = _client(parent)
        text_client.add_reply(
            SlackMessage(
                ts="1787961600.000004",
                author_user_id=RELAY_USER,
                text="Completed successfully without a canonical V2 frame.",
                thread_ts=PARENT_TS,
            )
        )
        text_carrier = SourceAwareRecordingWakeCarrier("ACK_REQUIRED")
        text_observer = DialogueTurnObserver(
            policy=_policy(),
            client=text_client,
            registry=_registry(),
            wake_carrier=text_carrier,
        )
        text_result = await text_observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        assert text_result.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
        assert len(text_carrier.source_calls) == 1
        assert text_carrier.source_calls[0].messages == ()
        assert text_carrier.reconcile_calls == []
        assert text_carrier.submit_calls == []

    asyncio.run(scenario())


def test_unbound_root_target_refuses_without_seat_fallback_or_carrier_call() -> None:
    async def scenario() -> None:
        parent = _parent()
        carrier = RecordingWakeCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent),
            registry=load_session_targets(),
            wake_carrier=carrier,
        )

        result = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert result.outcome is ObservationOutcome.REFUSED
        assert result.reason.startswith("DIALOGUE_WAKE_TARGET_UNBOUND:")
        assert "root_job_id JOB-001 has no binding for seat coo" in result.reason
        assert carrier.reconcile_calls == []
        assert carrier.submit_calls == []

    asyncio.run(scenario())


def test_effect_unknown_holds_same_identity_and_never_retries_submit() -> None:
    async def scenario() -> None:
        parent = _parent()
        carrier = RecordingWakeCarrier(effect_unknown=True)
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent),
            registry=_registry(),
            wake_carrier=carrier,
        )

        first = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        held = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert first.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
        assert held.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
        assert first.obligation is not None and held.obligation is not None
        assert first.obligation.obligation_id == held.obligation.obligation_id
        assert len(carrier.reconcile_calls) == 1
        assert len(carrier.submit_calls) == 1

        carrier.effect_unknown = False
        carrier.reconciliation = WakeCarrierState.EFFECT_UNKNOWN
        restarted = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent),
            registry=_registry(),
            wake_carrier=carrier,
        )
        reconciled = await restarted.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        assert reconciled.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
        assert reconciled.obligation is not None
        assert reconciled.obligation.obligation_id == first.obligation.obligation_id
        assert len(carrier.reconcile_calls) == 2
        assert len(carrier.submit_calls) == 1

    asyncio.run(scenario())


def test_pre_submit_failure_retries_same_identity_and_submits_on_next_poll() -> None:
    class FailOncePreSubmitCarrier(RecordingWakeCarrier):
        def __init__(self) -> None:
            super().__init__()
            self.failures_remaining = 1

        async def submit(self, obligation, route) -> None:
            self.submit_calls.append((obligation, route))
            if self.failures_remaining:
                self.failures_remaining -= 1
                raise WakePreSubmitError("target was unavailable before submit")

    async def scenario() -> None:
        parent = _parent()
        carrier = FailOncePreSubmitCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent, parent_author=RELAY_USER),
            registry=_registry(),
            wake_carrier=carrier,
        )

        first = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
        retried = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert first.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
        assert first.reason == "WAKE_TARGET_UNAVAILABLE"
        assert retried.outcome is ObservationOutcome.WAKE_SUBMITTED
        assert first.obligation is not None and retried.obligation is not None
        assert first.obligation.obligation_id == retried.obligation.obligation_id
        assert len(carrier.reconcile_calls) == 2
        assert len(carrier.submit_calls) == 2

    asyncio.run(scenario())


def test_unavailable_wake_reconciliation_fails_closed_before_submit() -> None:
    class UnavailableCarrier(RecordingWakeCarrier):
        async def reconcile(self, obligation, route) -> WakeCarrierState:
            self.reconcile_calls.append((obligation, route))
            raise TimeoutError("carrier status unavailable")

    async def scenario() -> None:
        parent = _parent()
        carrier = UnavailableCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client(parent),
            registry=_registry(),
            wake_carrier=carrier,
        )

        result = await observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )

        assert result.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
        assert result.reason == "WAKE_CARRIER_RECONCILIATION_UNAVAILABLE"
        assert len(carrier.reconcile_calls) == 1
        assert carrier.submit_calls == []

    asyncio.run(scenario())


def test_same_seat_source_to_target_is_refused_as_self_loop() -> None:
    async def scenario() -> None:
        parent = _parent()
        message = _result(parent)
        ordinary = classify_turn(
            parent=parent,
            messages=(message,),
            routing=_routing(parent),
        )
        assert ordinary.attention is not None
        forged_attention = replace(
            ordinary.attention,
            source_ref="agent_dialogue_attention:" + "d" * 64,
            target_seat="coo",
        )
        forged = TurnDecision(
            action=TurnAction.WAKE_COO,
            attention=forged_attention,
            reason="DIALOGUE_TURN_PENDING",
            refusal_code=None,
        )
        carrier = RecordingWakeCarrier()
        observer = DialogueTurnObserver(
            policy=_policy(),
            client=_client_with_result(parent),
            registry=_registry(),
            wake_carrier=carrier,
        )

        with patch(
            "integrations.slack_agent_dialogue.turn_observer.classify_turn",
            return_value=forged,
        ):
            result = await observer.reconcile_once(
                context=_context(parent), routing=_routing(parent)
            )

        assert result.outcome is ObservationOutcome.REFUSED
        assert result.reason == "DIALOGUE_SELF_LOOP_REFUSED"
        assert carrier.reconcile_calls == []
        assert carrier.submit_calls == []

    asyncio.run(scenario())

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _flat(path: str) -> str:
    return " ".join(_read(path).split())


def test_universal_dialogue_law_has_resource_classes_and_model_wake_floor() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "Class E",
        "Class T",
        "Class M",
        "Default interval: 60 minutes",
        "Absolute minimum interval: 15 minutes",
        "15m -> 30m -> 60m",
        "principals, not polling daemons",
    ):
        assert phrase in law


def test_universal_dialogue_law_makes_watcher_attention_not_scope() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "watcher prompt is not a scope fence",
        "cannot override a later valid same-operation carrier edge",
        "qualifying carrier event",
        "re-enter normal worker procedure",
        "notification-only anti-pattern",
    ):
        assert phrase in law


def test_universal_dialogue_law_requires_fresh_read_before_substantive_write() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "Fresh-read the exact bound carrier/thread in the same interactive turn",
        "after the latest local evidence-producing action",
        "WATCH_ARMED",
        "never satisfies this freshness fence",
        "Pickup ACK",
    ):
        assert phrase in law


def test_aggregate_watcher_resource_survives_child_stop() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "Watcher resource lifetime and watched-source lifetime are distinct",
        "permanent seat inbox",
        "principal lane",
        "sibling sources",
        "aggregate resource remains ACTIVE",
        "Zero remaining child sources is quiescent, not seat termination",
        "explicit seat/principal deregistration",
        "WATCH_STOP_FAILED",
        "keep child A terminal",
        "continue observing child B",
    ):
        assert phrase in law


def test_exact_native_wake_is_attention_only_and_never_fails_over() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "exact-native-task wake/resume action",
        "verified current RuntimeBinding/native task",
        "never choose the newest visible tab/session",
        "never fall back to a different task",
        "native nudge is attention only",
        "SESSION_LOST / RUNTIME_BINDING_RECONCILIATION_REQUIRED",
        "treating Slack delivery as consumption",
    ):
        assert phrase in law


def test_commission_wave_rejects_fastest_supported_reasoning_polling() -> None:
    commission = _flat("docs/sol_skills/COMMISSION_WAVE.md")
    assert "fastest lawful/practical cadence" not in commission
    for phrase in (
        "Default Class-M interval is 60 minutes",
        "hard floor is 15 minutes",
        "15m -> 30m -> 60m",
        "watcher prompt is not a scope fence",
        "re-enter normal worker procedure",
    ):
        assert phrase in commission


def test_commission_wave_child_stop_is_source_local_not_resource_shutdown() -> None:
    commission = _flat("docs/sol_skills/COMMISSION_WAVE.md")
    for phrase in (
        "exact `operation_key + carrier` child source",
        "keep that aggregate resource active",
        "Whole-resource shutdown requires",
        "cannot remove/suppress the exact terminal child source",
        "keep any independently valid aggregate seat/principal/sibling watcher resource active",
        "Terminal completion closes that child source/cycle",
    ):
        assert phrase in commission
    assert "the temporary watcher must be disarmed" not in commission


def test_slack_reciprocal_edges_are_bound_to_exact_thread_root_not_channel() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "workspace + conversation/channel + thread-root timestamp",
        "top-level post in the same channel is a carrier-root mismatch",
        "PICKUP_ACK",
        "must be replies under that exact parent",
    ):
        assert phrase in law


def test_terminal_stop_consumes_receiver_assignment_for_that_child() -> None:
    index = _flat("docs/sol_skills/INDEX.md")
    routing = _flat("docs/sol_skills/WORKER_AVENUE_ROUTING.md")
    for text in (index, routing):
        for phrase in (
            "Receiver assignment is child-specific",
            "terminal STOP consumes that child assignment",
            "standing program instruction does not self-assign a successor child",
            "fresh Sol/Chairman delivery or canonical placement edge",
        ):
            assert phrase in text


def test_exact_session_required_does_not_equate_slack_seat_with_native_session() -> None:
    routing = _flat("docs/sol_skills/WORKER_AVENUE_ROUTING.md")
    for phrase in (
        "Slack user/seat identity is not exact native-session identity",
        "RECEIVER_SESSION_MISMATCH",
        "delivery to a different session is not PICKUP_ACK",
        "do not spawn or substitute another session",
    ):
        assert phrase in routing


def test_exact_session_slack_delivery_requires_proven_native_addressability() -> None:
    routing = _flat("docs/sol_skills/WORKER_AVENUE_ROUTING.md")
    for phrase in (
        "Slack mention alone is not an exact-session delivery mechanism",
        "production-proven exact native wake/resume path",
        "WAITING_EXACT_SESSION / wake_unavailable",
        "do not emit an account-targeted DIRECT_TARGETED packet",
    ):
        assert phrase in routing


def test_buried_direct_targeted_new_child_reply_cannot_originate_a_child() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    index = _flat("docs/sol_skills/INDEX.md")
    routing = _flat("docs/sol_skills/WORKER_AVENUE_ROUTING.md")

    for phrase in (
        "DIRECT_TARGETED — NEW CHILD",
        "buried reply under an unrelated parent/program/previous-child root",
        "cannot by itself originate a new independent child",
        "cannot by itself become that child's receiver-assignment event",
        "Sol-authored top-level child commission root",
        "eligible command-create event",
        "deliberate current live delivery into the actual provider interaction",
        "production-proven exact native wake/resume path",
        "binds that child to an exact root",
    ):
        assert phrase in law

    for phrase in (
        "CONTINUE`, `RULING`, and `STOP` remain reciprocal continuation/terminal edges",
        "exact root of an already-ACKed child",
    ):
        assert phrase in routing

    assert "never makes that buried reply a successor-child assignment" in index


def test_unacked_slack_delivery_is_unconsumed_prestart_not_active_work() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    index = _flat("docs/sol_skills/INDEX.md")
    routing = _flat("docs/sol_skills/WORKER_AVENUE_ROUTING.md")

    for text in (law, index, routing):
        for phrase in (
            "DELIVERY_SENT or a Slack mention without a valid receiver PICKUP_ACK",
            "DELIVERY_UNCONSUMED / PRE_START",
            "must not be projected as active, STARTED, executing, waiting-on-worker, or watcher-consumed",
        ):
            assert phrase in text

    for phrase in (
        "PICKUP_ACK and START are separate edges",
        "Executive OS remains the lifecycle owner",
    ):
        assert phrase in law


def test_root_worker_bootstraps_carry_codex_continuation_invariant() -> None:
    for path in ("AGENTS.md", "CLAUDE.md"):
        text = _flat(path)
        for phrase in (
            "Reciprocal dialogue and watcher invariant",
            "watcher prompt is not a scope fence",
            "Default Class-M interval is 60 minutes",
            "hard floor is 15 minutes",
            "fresh-read the exact bound carrier",
            "Slack delivery is not target consumption",
            "aggregate seat/principal watcher resource",
        ):
            assert phrase in text

"""TeamLinkMessage.v1 / ContextPacket.v1 contract tests (TEAMLINK_DESIGN.md).

Shape adoption + the pure rules the design attaches to the shapes: the
deterministic id mint, same-key-changed-content REFUSED, monotonic delivery
with `unknown` outside the chain, hop math, expiry, the wake gate, the echo
guard and answers-settle.  No transport exists here to test — by design."""
from datetime import datetime, timedelta, timezone

import pytest

from control_plane.teamlink_contracts import (
    DELIVERY_UNKNOWN,
    MAX_HOPS_CEILING,
    TeamLinkContractError,
    advance_delivery,
    followup_requires_new_key,
    is_expired,
    is_ping_pong_echo,
    may_forward,
    mint_message_id,
    requires_model_turn,
    validate_context_packet,
    validate_team_link_message,
    verify_duplicate,
)

NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
LATER = "2026-11-09T18:00:00Z"


def message(**over):
    msg = {
        "schema": "TeamLinkMessage.v1",
        "message_id": "tlm-" + "0" * 32,
        "operation_key": "wo19-teamlink-check-1",
        "correlation": {"root_run_ref": None, "immediate_parent_run_ref": None,
                        "logical_child_key": None, "preview_id": None,
                        "decision_id": "dec-42", "attempt_ref": None,
                        "fence_counter": 3, "request_digest": "ab" * 32},
        "from": {"side": "hermes_profile", "id": "engineering", "thread_ref": None},
        "to": {"side": "t3_host_thread", "id": "m2studio", "thread_ref": "th_ready_9"},
        "kind": "instruction",
        "intent": "actionable",
        "body": "Run the WO-19 dry-run and report the unattributed count.",
        "context_refs": ["DEC:TEAMLINK-V1-DESIGN"],
        "reply_to": None,
        "hop_count": 0,
        "max_hops": 3,
        "delivery_state": "admitted",
        "expires_at": LATER,
    }
    msg.update(over)
    return msg


def packet(**over):
    base = {
        "schema": "ContextPacket.v1",
        "packet_id": "tlp-" + "1" * 32,
        "objective": "Finish the Hermes Rev5 roster lane.",
        "accepted_decisions": [
            {"decision_id": "dec-42", "summary": "TeamLink v1 shapes adopted",
             "ledger_row": "job_execution_decision:918"},
            {"decision_id": "dec-43", "ledger_row": None},
        ],
        "outstanding_dependencies": [
            {"what": "Executive MCP seam on 8731 revived", "owner": "gateway-oncall",
             "ref": "TEAMLINK_CENSUS row 3"}],
        "source_revision": {"branch": "t3/hermes-roster-continuity", "head": "bbfad42da"},
        "active_work_ownership": [
            {"work_ref": "PR-2180-native-path", "owner": "director-b",
             "lease_expires_at": LATER},
            {"work_ref": "wo19-prep", "owner": "director-a", "lease_expires_at": None}],
        "unresolved_effects": [
            {"effect_ref": "PR-2182-publication", "state": "EFFECT_UNKNOWN",
             "rule": "do not retry or publish through another account"}],
        "next_action": "Adopt the design field names; no transport.",
        "since_packet_id": "tlp-" + "f" * 32,
        "delta": {"added": ["dec-43"], "changed": [], "removed": []},
        "expires_at": LATER,
    }
    base.update(over)
    return base


# ── shape validation ─────────────────────────────────────────────────────────


class TestMessageShape:
    def test_full_message_roundtrips(self):
        assert validate_team_link_message(message())["kind"] == "instruction"

    def test_reply_to_is_optional_and_principals_may_omit_thread_ref(self):
        msg = message()
        del msg["reply_to"]
        del msg["to"]["thread_ref"]
        assert validate_team_link_message(msg) is msg

    @pytest.mark.parametrize("mutation", [
        {"schema": "TeamLinkMessage.v2"},
        {"message_id": "tlm-XYZ"},
        {"message_id": "tlm-" + "0" * 31},
        {"operation_key": "bad key with spaces"},
        {"operation_key": "_leading-underscore"},
        {"kind": "rumour"},
        {"intent": "urgent"},
        {"body": ""},
        {"body": "x" * 4097},
        {"context_refs": [f"r{i}" for i in range(33)]},
        {"context_refs": [""]},
        {"reply_to": "tlm-nothex"},
        {"hop_count": -1},
        {"max_hops": MAX_HOPS_CEILING + 1},
        {"delivery_state": "delivered"},
        {"expires_at": "next tuesday"},
        {"correlation": {"root_run_ref": None, "invented_key": "x"}},
        {"correlation": {"fence_counter": -1}},
        {"correlation": {"request_digest": "ab" * 31}},
        {"correlation": {"request_digest": "AB" * 32}},
        {"from": {"side": "slack_workspace", "id": "acme"}},
        {"from": {"side": "hermes_profile"}},
        {"to": {"side": "t3_host_thread", "id": "", "thread_ref": None}},
    ])
    def test_closed_set_rejects_drift(self, mutation):
        with pytest.raises(TeamLinkContractError):
            validate_team_link_message(message(**mutation))

    def test_unknown_top_level_field_rejected(self):
        with pytest.raises(TeamLinkContractError):
            validate_team_link_message(message(**{"priority": "high"}))

    def test_missing_required_field_rejected(self):
        msg = message()
        del msg["intent"]
        with pytest.raises(TeamLinkContractError):
            validate_team_link_message(msg)

    def test_all_null_correlation_is_a_lawful_pre_admission_status_ping(self):
        msg = message(correlation={key: None for key in (
            "root_run_ref", "immediate_parent_run_ref", "logical_child_key",
            "preview_id", "decision_id", "attempt_ref", "fence_counter",
            "request_digest")}, kind="status", intent="informational")
        assert validate_team_link_message(msg)["kind"] == "status"


class TestPacketShape:
    def test_full_packet_roundtrips(self):
        assert validate_context_packet(packet())["packet_id"].startswith("tlp-")

    def test_minimum_packet_omits_since_and_delta(self):
        base = packet()
        del base["since_packet_id"]
        del base["delta"]
        assert validate_context_packet(base)["objective"]

    @pytest.mark.parametrize("mutation", [
        {"schema": "ContextPacket.v2"},
        {"packet_id": "tlm-" + "1" * 32},
        {"objective": "x" * 2049},
        {"accepted_decisions": [{"summary": "no decision_id"}]},
        {"accepted_decisions": [{"decision_id": "d", "summary": "x" * 513}]},
        {"outstanding_dependencies": [{"what": "w"}]},
        {"outstanding_dependencies": [{"owner": "o"}]},
        {"source_revision": {"branch": "b"}},
        {"active_work_ownership": [{"work_ref": "w", "lease_expires_at": LATER}]},
        {"active_work_ownership": [{"work_ref": "w", "owner": "o",
                                    "lease_expires_at": "soon"}]},
        {"unresolved_effects": [{"effect_ref": "e", "state": "RESOLVED", "rule": "r"}]},
        {"unresolved_effects": [{"effect_ref": "e", "state": "EFFECT_UNKNOWN",
                                 "rule": "x" * 1025}]},
        {"next_action": "x" * 1025},
        {"since_packet_id": "tlp-nothex"},
        {"delta": {"added": ["a"], "changed": ["c"], "removed": [], "moved": ["m"]}},
        {"delta": {"added": ["a", ""]}},
        {"expires_at": "eventually"},
    ])
    def test_closed_set_rejects_drift(self, mutation):
        with pytest.raises(TeamLinkContractError):
            validate_context_packet(packet(**mutation))

    def test_row_and_list_caps_enforced(self):
        with pytest.raises(TeamLinkContractError):
            validate_context_packet(packet(accepted_decisions=[
                {"decision_id": f"d{i}"} for i in range(65)]))
        with pytest.raises(TeamLinkContractError):
            validate_context_packet(packet(active_work_ownership=[
                {"work_ref": f"w{i}", "owner": "o"} for i in range(33)]))


# ── deterministic mint + duplicate law ───────────────────────────────────────


class TestMintAndDuplicates:
    def test_fixed_vectors(self):
        # Cross-language parity vectors: the TS mirror test hardcodes the
        # same ids; both languages must keep minting them.
        assert mint_message_id(
            "engineering", "wo19-teamlink-check-1",
            "Run the WO-19 dry-run and report the unattributed count.",
            ["DEC:COMMERCIAL-DATA-RIGHTS-CHAIRMAN-ATTESTATION-20261023",
             "sha256:" + "ab" * 32]) == "tlm-0b0e68856ac4439993fac4b6e166b593"
        assert mint_message_id("coo-bot", "roundtrip-a3", "状态 status ping 中文",
                               []) == "tlm-64a95e24a3ae74fba98f72b2f2aa1352"

    def test_same_content_same_id_different_content_different_id(self):
        once = mint_message_id("engineering", "op-1", "body", ["r1"])
        again = mint_message_id("engineering", "op-1", "body", ["r1"])
        changed = mint_message_id("engineering", "op-1", "body2", ["r1"])
        other_sender = mint_message_id("coo-bot", "op-1", "body", ["r1"])
        assert once == again
        assert once not in (changed, other_sender)

    def test_duplicate_law(self):
        original = message()
        repeat = message()  # same operation_key + same deterministic id
        assert verify_duplicate(original, repeat) == "same_message"
        altered = message(body="Run something else entirely.")
        altered["message_id"] = mint_message_id(
            altered["from"]["id"], altered["operation_key"], altered["body"],
            altered["context_refs"])
        assert verify_duplicate(original, altered) == "refused_content_changed"
        fresh = message(operation_key="a-new-key-for-new-work")
        assert verify_duplicate(original, fresh) == "different_operation_key"


# ── delivery states, hops, expiry, wake gate, echo, settle ───────────────────


class TestDeliveryStates:
    def test_chain_is_monotonic_and_same_state_is_a_noop(self):
        state = "admitted"
        for target in ("picked_up", "executed", "replied", "consumed"):
            state = advance_delivery(state, target)
        assert advance_delivery("consumed", "consumed") == "consumed"

    def test_regression_raises(self):
        with pytest.raises(TeamLinkContractError) as exc:
            advance_delivery("executed", "admitted")
        assert exc.value.code == "DELIVERY_REGRESSION"

    def test_unknown_is_outside_the_chain_and_never_auto_retries(self):
        assert advance_delivery("picked_up", DELIVERY_UNKNOWN) == DELIVERY_UNKNOWN
        assert advance_delivery(DELIVERY_UNKNOWN, DELIVERY_UNKNOWN) == DELIVERY_UNKNOWN
        # reconciliation observed the truth on the ORIGINAL operation key:
        assert advance_delivery(DELIVERY_UNKNOWN, "executed") == "executed"

    def test_bogus_states_rejected(self):
        for pair in (("delivered", "admitted"), ("admitted", "sent")):
            with pytest.raises(TeamLinkContractError):
                advance_delivery(*pair)


class TestHopsExpiryWake:
    def test_default_chain_of_three_hops(self):
        first = message(hop_count=0, max_hops=3)
        assert may_forward(first, NOW) == (True, "")
        second = message(hop_count=1, max_hops=3)
        assert may_forward(second, NOW) == (True, "")
        third = message(hop_count=2, max_hops=3)  # next leg would reach 3
        assert may_forward(third, NOW) == (False, "hop_breach")

    def test_zero_max_hops_forbids_any_forward_and_ceiling_is_eight(self):
        assert may_forward(message(hop_count=0, max_hops=0), NOW) == (False, "hop_breach")
        assert may_forward(message(hop_count=6, max_hops=8), NOW) == (True, "")

    def test_expired_message_is_dead_even_below_max_hops(self):
        dead = message(expires_at="2026-11-09T11:00:00Z")
        assert is_expired(dead, NOW) is True
        assert may_forward(dead, NOW) == (False, "expired")
        assert may_forward(message(), NOW) == (True, "")
        assert is_expired(message(expires_at=LATER), NOW) is False

    def test_unreadable_expiry_is_expired(self):
        assert is_expired({"expires_at": None}, NOW) is True

    def test_only_actionable_requires_a_turn(self):
        assert requires_model_turn(message()) is True
        assert requires_model_turn(message(intent="informational")) is False


class TestEchoAndSettle:
    def test_mirror_of_what_we_just_sent_is_an_echo(self):
        sent = message()
        # the echo arrives FROM the peer we just sent TO, mirroring
        # (kind, intent, reply_to):
        echo = message(**{"from": dict(sent["to"]), "to": dict(sent["from"])})
        assert is_ping_pong_echo(sent, echo) is True

    def test_answer_or_new_kind_is_not_an_echo(self):
        sent = message()
        answer = message(kind="answer")
        assert is_ping_pong_echo(sent, answer) is False
        reply = message(reply_to=sent["message_id"])
        assert is_ping_pong_echo(sent, reply) is False

    def test_answers_settle_requiring_a_new_operation_key(self):
        question = message(kind="question")
        requestion = message(kind="question")  # same subject, same key
        assert followup_requires_new_key(question, requestion) is True
        new_work = message(kind="question", operation_key="fresh-work-key")
        assert followup_requires_new_key(question, new_work) is False


def test_packet_is_a_cache_expired_means_refetch():
    fresh = packet(expires_at=LATER)
    stale = packet(expires_at="2026-11-09T11:00:00Z")
    assert is_expired(fresh, NOW) is False
    assert is_expired(stale, NOW) is True  # re-fetch, never act on it

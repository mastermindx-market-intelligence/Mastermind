from __future__ import annotations

import copy
import json

import pytest

from integrations.slack_agent_dialogue.contract import (
    A0_PROVEN_CHATGPT_TRAILER,
    DialogueContractError,
    MAX_FRAME_BYTES,
    MESSAGE_DISCRIMINATOR,
    MESSAGE_SCHEMA,
    PARENT_SCHEMA,
    adjudicate_reply,
    build_message,
    build_parent,
    parse_message_frame,
    parse_parent_frame,
    render_message,
    render_parent,
    semantic_fingerprint,
    validate_message,
)

REPO = "mastermindx-market-intelligence/Mastermind"


class FixedAuthorityPolicy:
    def __init__(self, minimum: str, *, continuation: bool = True) -> None:
        self.minimum = minimum
        self.continuation = continuation

    def minimum_authority(self, *, request, option) -> str:
        return self.minimum

    def allows_continuation(self, *, request, reply) -> bool:
        return self.continuation


class ExactContinuationPolicy(FixedAuthorityPolicy):
    def allows_continuation(self, *, request, reply) -> bool:
        return (
            request["message_type"] == "PROGRESS"
            and request["body"]
            == {
                "stage": "contract",
                "completed": "Contract vectors are complete.",
                "next": "Run the hostile matrix.",
            }
            and reply["body"]
            == {
                "instruction": "Continue within the frozen scope.",
                "stop_condition": "Stop if commission or head changes.",
                "scope_change": False,
            }
        )


def commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "a" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
    }


def applies(head: str = "c" * 40) -> dict[str, object]:
    return {"repository": REPO, "head_sha": head, "pr": f"{REPO}#125"}


def raw(message_type: str = "ACK") -> dict[str, object]:
    bodies: dict[str, object] = {
        "ACK": {"acknowledged": True},
        "DECISION_REQUEST": {
            "question": "Which option should be selected?",
            "outcome_impact": "The choice changes only the bounded implementation path.",
            "options": [
                {
                    "id": "opt-continue",
                    "summary": "Continue the bounded path.",
                    "consequence": "The same implementation continues.",
                    "disposition": "CONTINUE",
                    "authority_effect": "NONE",
                },
                {
                    "id": "opt-amend",
                    "summary": "Use a canonical amendment.",
                    "consequence": "Work remains paused until exact accepted bytes exist.",
                    "disposition": "STOP",
                    "authority_effect": "CANONICAL_REF_REQUIRED",
                },
                {
                    "id": "opt-chairman",
                    "summary": "Escalate to the Chairman.",
                    "consequence": "No continuation occurs without Chairman authority.",
                    "disposition": "STOP",
                    "authority_effect": "CHAIRMAN_REQUIRED",
                },
            ],
            "recommendation": "opt-continue",
            "work_paused": True,
        },
        "BLOCKED": {
            "blocker_code": "AUTH_REQUIRED",
            "reason": "A bounded dependency is unavailable.",
            "needed_from": "sol",
            "work_paused": True,
        },
        "PROGRESS": {
            "stage": "contract",
            "completed": "Contract vectors are complete.",
            "next": "Run the hostile matrix.",
        },
        "RESULT": {"status": "PASS", "result": "The bounded wave passed."},
        "RULING": {
            "authority_class": "WITHIN_COMMISSION",
            "selected_option": "opt-continue",
            "decision": "Select the bounded continue option.",
            "rationale": "It preserves the accepted commission.",
            "canonical_ref": None,
        },
        "CONTINUE": {
            "instruction": "Continue within the frozen scope.",
            "stop_condition": "Stop if commission or head changes.",
            "scope_change": False,
        },
        "STOP": {"reason": "Stop at the current gate.", "next_authority": "sol"},
        "AMENDMENT_AVAILABLE": {
            "canonical_ref": f"https://github.com/{REPO}/commit/" + "d" * 40,
            "summary": "A canonical amendment is available.",
        },
    }
    sol_type = message_type in {"RULING", "CONTINUE", "STOP", "AMENDMENT_AVAILABLE"}
    return {
        "schema": MESSAGE_SCHEMA,
        "message_key": f"asd-{message_type.lower().replace('_', '-')}-0001",
        "message_type": message_type,
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": commission(),
        "session_ref": "asd-session-fable0001",
        "seat_ref": "sol" if sol_type else "fable",
        "reply_to_message_key": "asd-decision-request-0001" if sol_type else None,
        "applies_to": applies(),
        "summary": "Bounded dialogue message.",
        "body": bodies[message_type],
        "evidence_refs": [f"https://github.com/{REPO}/pull/125"],
        "requires_response": message_type in {"DECISION_REQUEST", "BLOCKED"},
        "created_at": "2026-08-23T08:00:00Z",
    }


def message(message_type: str = "ACK") -> dict[str, object]:
    return build_message(raw(message_type))


def parent() -> dict[str, object]:
    return build_parent(
        {
            "schema": PARENT_SCHEMA,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "allowed_sol_user_ids": ["U0BRETDUAS2", "U0BSB73JWNL"],
            "created_at": "2026-08-23T08:00:00Z",
        }
    )


@pytest.mark.parametrize(
    "kind",
    [
        "ACK",
        "DECISION_REQUEST",
        "BLOCKED",
        "PROGRESS",
        "RESULT",
        "RULING",
        "CONTINUE",
        "STOP",
        "AMENDMENT_AVAILABLE",
    ],
)
def test_closed_types_round_trip(kind: str) -> None:
    value = message(kind)
    assert parse_message_frame(render_message(value)) == value


def test_parent_and_known_hosted_trailer_round_trip() -> None:
    assert parse_parent_frame(render_parent(parent())) == parent()
    framed = render_message(message()) + "\n" + A0_PROVEN_CHATGPT_TRAILER
    assert parse_message_frame(framed) == message()


@pytest.mark.parametrize(
    "suffix",
    [
        "\nSent using ChatGPT",
        "\n*Sent using* <@U0BRGTF1H26|Other>",
        "\n*Sent using* <@U0BRGTF1H26|ChatGPT>\nextra",
    ],
)
def test_unknown_trailer_refuses(suffix: str) -> None:
    with pytest.raises(DialogueContractError):
        parse_message_frame(render_message(message()) + suffix)


def test_unproven_chatgpt_identity_trailer_refuses() -> None:
    with pytest.raises(DialogueContractError) as exc:
        parse_message_frame(
            render_message(message())
            + "\n*Sent using* <@U0BRETDUAS2|ChatGPT>"
        )
    assert exc.value.code == "TRAILER_REFUSED"


def test_literal_ack_vector_and_fingerprint_exclusion() -> None:
    value = message()
    assert (
        value["fingerprint"]
        == "875cf7057fede1c8293b4d14e4d4fc800d0adb5c2359d6f14b48f56fee27acb5"
    )
    clock_only = copy.deepcopy(value)
    clock_only["created_at"] = "2026-08-23T08:00:01Z"
    assert semantic_fingerprint(value) == semantic_fingerprint(clock_only)
    clock_only["summary"] = "Different bounded summary."
    assert semantic_fingerprint(value) != semantic_fingerprint(clock_only)


def test_duplicate_or_noncanonical_json_refuses() -> None:
    value = message()
    noncanonical = MESSAGE_DISCRIMINATOR + "\n" + json.dumps(value, sort_keys=True)
    with pytest.raises(DialogueContractError):
        parse_message_frame(noncanonical)
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    duplicate = canonical[:-1] + ',"schema":"mastermind.agent_dialogue.v1"}'
    with pytest.raises(DialogueContractError):
        parse_message_frame(MESSAGE_DISCRIMINATOR + "\n" + duplicate)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.update({"extra": True}),
        lambda value: value.update({"seat_ref": "sol"}),
        lambda value: value.update({"requires_response": True}),
        lambda value: value.update({"work_ref": "WS:bad"}),
        lambda value: value["commission_ref"].update({"path": "../secret"}),
        lambda value: value.update({"evidence_refs": ["https://example.com/"]}),
    ],
)
def test_closed_contract_refuses_widening(mutator) -> None:
    value = message()
    mutator(value)
    value["fingerprint"] = semantic_fingerprint(value)
    with pytest.raises(DialogueContractError):
        validate_message(value)


def test_secret_shaped_and_control_text_refuse() -> None:
    for forbidden in (
        "".join(("xo", "xb-", "123456789012-", "abcdefghijklmnopqrstuvwxyz")),
        "github_pat_" + "a" * 30,
        "ghp_" + "b" * 30,
        "sk-" + "c" * 30,
        "line one\nline two",
    ):
        value = raw()
        value["summary"] = forbidden
        with pytest.raises(DialogueContractError):
            build_message(value)


@pytest.mark.parametrize("location", ["stage", "path", "url", "option"])
def test_secret_shaped_structured_string_leaves_refuse(location: str) -> None:
    secret = "xoxb-abcdefghij"
    value = raw("DECISION_REQUEST" if location == "option" else "PROGRESS")
    if location == "stage":
        value["body"]["stage"] = secret
    elif location == "path":
        value["commission_ref"]["path"] = f"research/{secret}"
    elif location == "url":
        value["evidence_refs"] = [
            f"https://github.com/{secret}/repo/pull/125"
        ]
    else:
        value["body"]["options"][0]["id"] = f"opt-{secret}"
        value["body"]["recommendation"] = f"opt-{secret}"
    with pytest.raises(DialogueContractError) as exc:
        build_message(value)
    assert exc.value.code == "MESSAGE_INVALID"


def test_hash_and_sha_identifiers_remain_valid_under_recursive_secret_guard() -> None:
    value = message("PROGRESS")
    assert value["commission_ref"]["commit"] == "a" * 40
    assert value["commission_ref"]["content_sha256"] == "b" * 64
    assert value["applies_to"]["head_sha"] == "c" * 40


def request_with_effect(effect: str) -> dict[str, object]:
    request = message("DECISION_REQUEST")
    request["body"]["options"][0]["authority_effect"] = effect
    request["fingerprint"] = semantic_fingerprint(request)
    return validate_message(request)


def ruling_for(
    request: dict[str, object], authority: str, canonical_ref: str | None = None
) -> dict[str, object]:
    value = raw("RULING")
    value["reply_to_message_key"] = request["message_key"]
    value["body"] = {
        "authority_class": authority,
        "selected_option": "opt-continue",
        "decision": "Apply only the declared authority effect.",
        "rationale": "Slack may not widen the commission.",
        "canonical_ref": canonical_ref,
    }
    return build_message(value)


@pytest.mark.parametrize(
    ("trusted", "effect", "authority", "disposition", "executable"),
    [
        ("WITHIN_COMMISSION", "NONE", "WITHIN_COMMISSION", "CONTINUE", True),
        (
            "WITHIN_COMMISSION",
            "NONE",
            "CANONICAL_REF_REQUIRED",
            "CANONICAL_REF_REQUIRED",
            False,
        ),
        (
            "WITHIN_COMMISSION",
            "NONE",
            "CHAIRMAN_REQUIRED",
            "CHAIRMAN_REQUIRED",
            False,
        ),
        (
            "CANONICAL_REF_REQUIRED",
            "NONE",
            "CANONICAL_REF_REQUIRED",
            "CANONICAL_REF_REQUIRED",
            False,
        ),
        (
            "WITHIN_COMMISSION",
            "CANONICAL_REF_REQUIRED",
            "CANONICAL_REF_REQUIRED",
            "CANONICAL_REF_REQUIRED",
            False,
        ),
        (
            "CHAIRMAN_REQUIRED",
            "NONE",
            "CHAIRMAN_REQUIRED",
            "CHAIRMAN_REQUIRED",
            False,
        ),
    ],
)
def test_trusted_floor_and_model_escalation_allow_sol_to_escalate(
    trusted: str,
    effect: str,
    authority: str,
    disposition: str,
    executable: bool,
) -> None:
    request = request_with_effect(effect)
    canonical_ref = (
        f"https://github.com/{REPO}/commit/" + "d" * 40
        if authority == "CANONICAL_REF_REQUIRED"
        else None
    )
    result = adjudicate_reply(
        request,
        ruling_for(request, authority, canonical_ref),
        authority_policy=FixedAuthorityPolicy(trusted),
    )
    assert result["disposition"] == disposition
    assert result["executable"] is executable


@pytest.mark.parametrize(
    ("trusted", "effect"),
    [
        ("CANONICAL_REF_REQUIRED", "NONE"),
        ("CHAIRMAN_REQUIRED", "NONE"),
        ("WITHIN_COMMISSION", "CANONICAL_REF_REQUIRED"),
    ],
)
def test_model_authored_authority_cannot_launder_or_downgrade(
    trusted: str, effect: str
) -> None:
    request = request_with_effect(effect)
    with pytest.raises(DialogueContractError) as exc:
        adjudicate_reply(
            request,
            ruling_for(request, "WITHIN_COMMISSION"),
            authority_policy=FixedAuthorityPolicy(trusted),
        )
    assert exc.value.code == "AUTHORITY_REFUSED"


@pytest.mark.parametrize("invalid", ["NONE", "", "within_commission"])
def test_invalid_trusted_authority_policy_refuses(invalid: str) -> None:
    request = request_with_effect("NONE")
    with pytest.raises(DialogueContractError) as exc:
        adjudicate_reply(
            request,
            ruling_for(request, "WITHIN_COMMISSION"),
            authority_policy=FixedAuthorityPolicy(invalid),
        )
    assert exc.value.code == "AUTHORITY_REFUSED"


def test_sol_cannot_continue_chairman_owned_blocker() -> None:
    blocked = message("BLOCKED")
    blocked["body"]["needed_from"] = "chairman"
    blocked["fingerprint"] = semantic_fingerprint(blocked)
    reply = raw("CONTINUE")
    reply["reply_to_message_key"] = blocked["message_key"]
    reply = build_message(reply)
    with pytest.raises(DialogueContractError) as exc:
        adjudicate_reply(
            blocked,
            reply,
            authority_policy=FixedAuthorityPolicy("WITHIN_COMMISSION"),
        )
    assert exc.value.code == "AUTHORITY_REFUSED"


def test_positive_continue_requires_exact_trusted_commission_semantics() -> None:
    request = message("PROGRESS")
    reply = raw("CONTINUE")
    reply["reply_to_message_key"] = request["message_key"]
    reply = build_message(reply)
    result = adjudicate_reply(
        request,
        reply,
        authority_policy=ExactContinuationPolicy("WITHIN_COMMISSION"),
    )
    assert result == {
        "disposition": "CONTINUE",
        "executable": True,
        "selected_option": None,
        "canonical_ref": None,
    }


@pytest.mark.parametrize("failure", ["widened", "policy_raises"])
def test_positive_continue_fails_closed_on_widening_or_policy_error(
    failure: str,
) -> None:
    request = message("PROGRESS")
    reply = raw("CONTINUE")
    reply["reply_to_message_key"] = request["message_key"]
    reply["body"]["instruction"] = "Merge, deploy, and widen the commission."
    reply = build_message(reply)
    authority_policy = ExactContinuationPolicy("WITHIN_COMMISSION")
    if failure == "policy_raises":
        class RaisingPolicy(ExactContinuationPolicy):
            def allows_continuation(self, *, request, reply) -> bool:
                raise RuntimeError("untrusted policy failure detail")

        authority_policy = RaisingPolicy("WITHIN_COMMISSION")
    with pytest.raises(DialogueContractError) as exc:
        adjudicate_reply(
            request,
            reply,
            authority_policy=authority_policy,
        )
    assert exc.value.code == "AUTHORITY_REFUSED"


def test_exact_4500_byte_boundary() -> None:
    value = raw("DECISION_REQUEST")
    value["summary"] = "s" * 391
    value["body"]["question"] = "q" * 700
    value["body"]["outcome_impact"] = "i"
    value["body"]["options"] = [
        {
            "id": f"opt-option-{index}",
            "summary": "x" * 250,
            "consequence": "y" * 350,
            "disposition": "CONTINUE" if index < 2 else "STOP",
            "authority_effect": "NONE",
        }
        for index in range(3)
    ]
    value["body"]["recommendation"] = "opt-option-0"
    value["evidence_refs"] = [
        f"https://github.com/{REPO}/commit/{index:040x}" for index in range(1, 4)
    ]
    exact = build_message(value)
    assert len(render_message(exact).encode("utf-8")) == MAX_FRAME_BYTES
    exact["body"]["outcome_impact"] += "z"
    exact["fingerprint"] = semantic_fingerprint(exact)
    with pytest.raises(DialogueContractError) as exc:
        render_message(exact)
    assert exc.value.code == "FRAME_TOO_LARGE"

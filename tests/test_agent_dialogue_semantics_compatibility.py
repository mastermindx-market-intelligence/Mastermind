from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

EXPORTS = json.loads(r'''{"contract":{"all":["A0_PROVEN_CHATGPT_TRAILER","AUTHORITY_CLASSES","DialogueContractError","ERROR_CODES","FABLE_MESSAGE_TYPES","MAX_FRAME_BYTES","MESSAGE_DISCRIMINATOR","MESSAGE_SCHEMA","MESSAGE_TYPES","PARENT_DISCRIMINATOR","PARENT_SCHEMA","SOL_MESSAGE_TYPES","TrustedAuthorityPolicy","adjudicate_reply","build_message","build_parent","parse_message_frame","parse_parent_frame","render_message","render_parent","same_context","semantic_fingerprint","validate_applies_to","validate_commission_ref","validate_evidence_ref","validate_message","validate_parent"],"before_blob":"e274b69130d417a0d6a6e2a77764d8ba5867cd8c","explicit_exports":["A0_PROVEN_CHATGPT_TRAILER","AUTHORITY_CLASSES","Any","CommissionRefError","DialogueContractError","ERROR_CODES","FABLE_MESSAGE_TYPES","MAX_EVIDENCE_REFS","MAX_FRAME_BYTES","MAX_OPTIONS","MAX_SUMMARY_CHARS","MAX_TEXT_CHARS","MESSAGE_DISCRIMINATOR","MESSAGE_KEYS","MESSAGE_SCHEMA","MESSAGE_TYPES","Mapping","PARENT_DISCRIMINATOR","PARENT_KEYS","PARENT_SCHEMA","Protocol","REPLY_DISPOSITIONS","SOL_MESSAGE_TYPES","TrustedAuthorityPolicy","__all__","adjudicate_reply","annotations","build_message","build_parent","datetime","hashlib","json","normalize_commission_ref","parse_message_frame","parse_parent_frame","re","render_message","render_parent","same_context","semantic_fingerprint","urlsplit","validate_applies_to","validate_body","validate_commission_ref","validate_evidence_ref","validate_message","validate_parent"],"path":"integrations/slack_agent_dialogue/contract.py","public_names":["A0_PROVEN_CHATGPT_TRAILER","AUTHORITY_CLASSES","Any","CommissionRefError","DialogueContractError","ERROR_CODES","FABLE_MESSAGE_TYPES","MAX_EVIDENCE_REFS","MAX_FRAME_BYTES","MAX_OPTIONS","MAX_SUMMARY_CHARS","MAX_TEXT_CHARS","MESSAGE_DISCRIMINATOR","MESSAGE_KEYS","MESSAGE_SCHEMA","MESSAGE_TYPES","Mapping","PARENT_DISCRIMINATOR","PARENT_KEYS","PARENT_SCHEMA","Protocol","REPLY_DISPOSITIONS","SOL_MESSAGE_TYPES","TrustedAuthorityPolicy","adjudicate_reply","annotations","build_message","build_parent","datetime","hashlib","json","normalize_commission_ref","parse_message_frame","parse_parent_frame","re","render_message","render_parent","same_context","semantic_fingerprint","urlsplit","validate_applies_to","validate_body","validate_commission_ref","validate_evidence_ref","validate_message","validate_parent"]},"contract_v2":{"all":null,"before_blob":"8583898048a0ddebf1731a062831f1943a7bb77a","explicit_exports":["A0_PROVEN_CHATGPT_TRAILER","Any","DialogueContractError","FABLE_MESSAGE_TYPES","MAX_EVIDENCE_REFS","MAX_FRAME_BYTES","MAX_SUMMARY_CHARS","MESSAGE_DISCRIMINATOR_V2","MESSAGE_KEYS_V2","MESSAGE_SCHEMA_V2","MESSAGE_TYPES","Mapping","PARENT_DISCRIMINATOR_V2","PARENT_KEYS_V2","PARENT_SCHEMA_V2","SOL_MESSAGE_TYPES","TURN_WATCH_MODE_V1","_MESSAGE_KEY_RE","annotations","build_message_v2","build_parent_v2","datetime","hashlib","json","parse_message_frame_v2","parse_parent_frame_v2","presentation_label","re","render_message_v2","render_parent_v2","semantic_fingerprint","validate_actor_ref","validate_applies_to","validate_applies_to_v2","validate_body","validate_commission_ref","validate_evidence_ref","validate_message_v2","validate_parent_v2"],"path":"integrations/slack_agent_dialogue/contract_v2.py","public_names":["A0_PROVEN_CHATGPT_TRAILER","Any","DialogueContractError","FABLE_MESSAGE_TYPES","MAX_EVIDENCE_REFS","MAX_FRAME_BYTES","MAX_SUMMARY_CHARS","MESSAGE_DISCRIMINATOR_V2","MESSAGE_KEYS_V2","MESSAGE_SCHEMA_V2","MESSAGE_TYPES","Mapping","PARENT_DISCRIMINATOR_V2","PARENT_KEYS_V2","PARENT_SCHEMA_V2","SOL_MESSAGE_TYPES","TURN_WATCH_MODE_V1","annotations","build_message_v2","build_parent_v2","datetime","hashlib","json","parse_message_frame_v2","parse_parent_frame_v2","presentation_label","re","render_message_v2","render_parent_v2","semantic_fingerprint","validate_actor_ref","validate_applies_to","validate_applies_to_v2","validate_body","validate_commission_ref","validate_evidence_ref","validate_message_v2","validate_parent_v2"]},"turn_watcher":{"all":["ATTENTION_SCHEMA","ATTENTION_SOURCE_KIND","ATTENTION_WAKE_KIND","TURN_WATCH_MODE_V1","AgentDialogueAttention","TurnAction","TurnDecision","TurnRoutingFacts","classify_turn"],"before_blob":"0e338a1d822a65753c1465dbcf10d6071f13ed1d","explicit_exports":["ATTENTION_SCHEMA","ATTENTION_SOURCE_KIND","ATTENTION_WAKE_KIND","AgentDialogueAttention","Any","DialogueContractError","Enum","MESSAGE_SCHEMA_V2","Mapping","PARENT_SCHEMA_V2","Sequence","TURN_WATCH_MODE_V1","TurnAction","TurnDecision","TurnRoutingFacts","__all__","_canonical_identity","annotations","classify_turn","dataclass","hashlib","json","validate_message_v2","validate_parent_v2"],"path":"integrations/slack_agent_dialogue/turn_watcher.py","public_names":["ATTENTION_SCHEMA","ATTENTION_SOURCE_KIND","ATTENTION_WAKE_KIND","AgentDialogueAttention","Any","DialogueContractError","Enum","MESSAGE_SCHEMA_V2","Mapping","PARENT_SCHEMA_V2","Sequence","TURN_WATCH_MODE_V1","TurnAction","TurnDecision","TurnRoutingFacts","annotations","classify_turn","dataclass","hashlib","json","validate_message_v2","validate_parent_v2"]}}''')
GOLDEN = json.loads(r'''{"attention_identity":"{\"attention_kind\":\"dialogue_turn_pending\",\"commission_fingerprint\":\"6f11388fb58cc9913963f056e4adc794286d7fec4478c635fd17301914c4f048\",\"message_key\":\"asd-blocked-001\",\"source_kind\":\"agent_dialogue_attention\",\"target_seat\":\"ceo\"}","attention_source_ref":"agent_dialogue_attention:ca8be05a774c189ffcf14fe31486693a8389ea4e77314989e3d064145f3b30e8","decision":"WAKE_CEO","errors":{"v1_duplicate":{"code":"FRAME_INVALID","message":"FRAME_INVALID"},"v1_nan":{"code":"MESSAGE_INVALID","message":"MESSAGE_INVALID"},"v2_duplicate":{"code":"FRAME_INVALID","message":"FRAME_INVALID"},"v2_nan":{"code":"FRAME_INVALID","message":"FRAME_INVALID"}},"grant":{"binding_generation":7,"binding_id":"bind-sol-exec-0001","expires_at_epoch_seconds":1788585711,"installed_release_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","obligation_id":"WAKE-33333333333333333333333333333333","operation_key":"worker-presence-dialogue-wptw1-20260829-001","policy_digest":"5555555555555555","process_generation_id":"generation:sol:0007","schema":"mastermind.dialogue_wake_canary_activation.v1","source_attempt_id":"ATT-11111111111111111111111111111111","source_job_id":"JOB-101","source_root_job_id":"JOB-100","source_semantic_digest":"2222222222222222222222222222222222222222222222222222222222222222","source_worker_id":"WORKER-SOL-1","target_attempt_id":"ATT-44444444444444444444444444444444","target_seat":"ceo","target_session_alias":"SOL-EXEC","valid_from_epoch_seconds":1788585591},"head":"f93f7f411acee9b6111ec2adcb535e133a6b4f0c","source_request":{"operation":"RECONCILE_DIALOGUE_SOURCES","parent":{"allowed_sol_user_ids":["U0BRETDUAS2"],"commission_ref":{"commit":"cccccccccccccccccccccccccccccccccccccccc","content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","path":"research/commission.md","repository":"mastermindx-market-intelligence/Mastermind"},"created_at":"2026-08-29T00:00:00Z","fingerprint":"6f11388fb58cc9913963f056e4adc794286d7fec4478c635fd17301914c4f048","operation_key":"worker-presence-dialogue-wptw1-20260829-001","schema":"mastermind.agent_dialogue_parent.v2","session_ref":"asd-session-turnwatch0001","watch_mode":"turn_watch_v1","work_ref":"WS:CHAIRMAN-CONTROL-ROOM"},"schema":"mastermind.dialogue_source_reconcile_request/v1","snapshot":{"channel_id":"C0BSBM78V1N","complete":true,"messages":[{"actor_ref":{"kind":"executive_surface","reasoning_surface":"claude","seat":"coo"},"applies_to":{"head_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","kind":"repository","pr":"mastermindx-market-intelligence/Mastermind#177","repository":"mastermindx-market-intelligence/Mastermind"},"body":{"blocker_code":"SOURCE_MOVED","needed_from":"sol","reason":"The protected source moved.","work_paused":true},"commission_ref":{"commit":"cccccccccccccccccccccccccccccccccccccccc","content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","path":"research/commission.md","repository":"mastermindx-market-intelligence/Mastermind"},"created_at":"2026-08-29T00:01:00Z","evidence_refs":["https://github.com/mastermindx-market-intelligence/Mastermind/pull/177"],"fingerprint":"17fae2568b98b47ab5c626bc8b58b3abefedb0cee9e1c0a73488b947f7244cd8","message_key":"asd-blocked-001","message_type":"BLOCKED","reply_to_message_key":null,"requires_response":true,"schema":"mastermind.agent_dialogue.v2","session_ref":"asd-session-turnwatch0001","summary":"One accepted dialogue event.","work_ref":"WS:CHAIRMAN-CONTROL-ROOM"}],"operation_key":"worker-presence-dialogue-wptw1-20260829-001","parent_fingerprint":"6f11388fb58cc9913963f056e4adc794286d7fec4478c635fd17301914c4f048","thread_ts":"1788000000.123456","workspace_id":"T0BRD2AQXQV"}},"v1_message":{"applies_to":{"head_sha":"cccccccccccccccccccccccccccccccccccccccc","pr":"mastermindx-market-intelligence/Mastermind#125","repository":"mastermindx-market-intelligence/Mastermind"},"body":{"acknowledged":true},"commission_ref":{"commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","path":"research/commission.md","repository":"mastermindx-market-intelligence/Mastermind"},"created_at":"2026-08-23T08:00:00Z","evidence_refs":["https://github.com/mastermindx-market-intelligence/Mastermind/pull/125"],"fingerprint":"875cf7057fede1c8293b4d14e4d4fc800d0adb5c2359d6f14b48f56fee27acb5","message_key":"asd-ack-0001","message_type":"ACK","reply_to_message_key":null,"requires_response":false,"schema":"mastermind.agent_dialogue.v1","seat_ref":"fable","session_ref":"asd-session-fable0001","summary":"Bounded dialogue message.","work_ref":"WS:CHAIRMAN-CONTROL-ROOM"},"v1_message_frame":"MMX/AGENT_DIALOGUE_V1\n{\"applies_to\":{\"head_sha\":\"cccccccccccccccccccccccccccccccccccccccc\",\"pr\":\"mastermindx-market-intelligence/Mastermind#125\",\"repository\":\"mastermindx-market-intelligence/Mastermind\"},\"body\":{\"acknowledged\":true},\"commission_ref\":{\"commit\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"content_sha256\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"path\":\"research/commission.md\",\"repository\":\"mastermindx-market-intelligence/Mastermind\"},\"created_at\":\"2026-08-23T08:00:00Z\",\"evidence_refs\":[\"https://github.com/mastermindx-market-intelligence/Mastermind/pull/125\"],\"fingerprint\":\"875cf7057fede1c8293b4d14e4d4fc800d0adb5c2359d6f14b48f56fee27acb5\",\"message_key\":\"asd-ack-0001\",\"message_type\":\"ACK\",\"reply_to_message_key\":null,\"requires_response\":false,\"schema\":\"mastermind.agent_dialogue.v1\",\"seat_ref\":\"fable\",\"session_ref\":\"asd-session-fable0001\",\"summary\":\"Bounded dialogue message.\",\"work_ref\":\"WS:CHAIRMAN-CONTROL-ROOM\"}","v1_parent":{"allowed_sol_user_ids":["U0BRETDUAS2","U0BSB73JWNL"],"commission_ref":{"commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","path":"research/commission.md","repository":"mastermindx-market-intelligence/Mastermind"},"created_at":"2026-08-23T08:00:00Z","fingerprint":"49342927f19c7fdbf0f938718bb36694417cc061ae87d05631cc049655470168","schema":"mastermind.agent_dialogue_parent.v1","session_ref":"asd-session-fable0001","work_ref":"WS:CHAIRMAN-CONTROL-ROOM"},"v1_parent_frame":"MMX/AGENT_DIALOGUE_PARENT_V1\n{\"allowed_sol_user_ids\":[\"U0BRETDUAS2\",\"U0BSB73JWNL\"],\"commission_ref\":{\"commit\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"content_sha256\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"path\":\"research/commission.md\",\"repository\":\"mastermindx-market-intelligence/Mastermind\"},\"created_at\":\"2026-08-23T08:00:00Z\",\"fingerprint\":\"49342927f19c7fdbf0f938718bb36694417cc061ae87d05631cc049655470168\",\"schema\":\"mastermind.agent_dialogue_parent.v1\",\"session_ref\":\"asd-session-fable0001\",\"work_ref\":\"WS:CHAIRMAN-CONTROL-ROOM\"}","v2_message":{"actor_ref":{"kind":"executive_surface","reasoning_surface":"claude","seat":"coo"},"applies_to":{"head_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","kind":"repository","pr":"mastermindx-market-intelligence/Mastermind#177","repository":"mastermindx-market-intelligence/Mastermind"},"body":{"blocker_code":"SOURCE_MOVED","needed_from":"sol","reason":"The protected source moved.","work_paused":true},"commission_ref":{"commit":"cccccccccccccccccccccccccccccccccccccccc","content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","path":"research/commission.md","repository":"mastermindx-market-intelligence/Mastermind"},"created_at":"2026-08-29T00:01:00Z","evidence_refs":["https://github.com/mastermindx-market-intelligence/Mastermind/pull/177"],"fingerprint":"17fae2568b98b47ab5c626bc8b58b3abefedb0cee9e1c0a73488b947f7244cd8","message_key":"asd-blocked-001","message_type":"BLOCKED","reply_to_message_key":null,"requires_response":true,"schema":"mastermind.agent_dialogue.v2","session_ref":"asd-session-turnwatch0001","summary":"One accepted dialogue event.","work_ref":"WS:CHAIRMAN-CONTROL-ROOM"},"v2_message_frame":"MMX/AGENT_DIALOGUE_V2\n{\"actor_ref\":{\"kind\":\"executive_surface\",\"reasoning_surface\":\"claude\",\"seat\":\"coo\"},\"applies_to\":{\"head_sha\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"kind\":\"repository\",\"pr\":\"mastermindx-market-intelligence/Mastermind#177\",\"repository\":\"mastermindx-market-intelligence/Mastermind\"},\"body\":{\"blocker_code\":\"SOURCE_MOVED\",\"needed_from\":\"sol\",\"reason\":\"The protected source moved.\",\"work_paused\":true},\"commission_ref\":{\"commit\":\"cccccccccccccccccccccccccccccccccccccccc\",\"content_sha256\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"path\":\"research/commission.md\",\"repository\":\"mastermindx-market-intelligence/Mastermind\"},\"created_at\":\"2026-08-29T00:01:00Z\",\"evidence_refs\":[\"https://github.com/mastermindx-market-intelligence/Mastermind/pull/177\"],\"fingerprint\":\"17fae2568b98b47ab5c626bc8b58b3abefedb0cee9e1c0a73488b947f7244cd8\",\"message_key\":\"asd-blocked-001\",\"message_type\":\"BLOCKED\",\"reply_to_message_key\":null,\"requires_response\":true,\"schema\":\"mastermind.agent_dialogue.v2\",\"session_ref\":\"asd-session-turnwatch0001\",\"summary\":\"One accepted dialogue event.\",\"work_ref\":\"WS:CHAIRMAN-CONTROL-ROOM\"}","v2_parent":{"allowed_sol_user_ids":["U0BRETDUAS2"],"commission_ref":{"commit":"cccccccccccccccccccccccccccccccccccccccc","content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","path":"research/commission.md","repository":"mastermindx-market-intelligence/Mastermind"},"created_at":"2026-08-29T00:00:00Z","fingerprint":"6f11388fb58cc9913963f056e4adc794286d7fec4478c635fd17301914c4f048","operation_key":"worker-presence-dialogue-wptw1-20260829-001","schema":"mastermind.agent_dialogue_parent.v2","session_ref":"asd-session-turnwatch0001","watch_mode":"turn_watch_v1","work_ref":"WS:CHAIRMAN-CONTROL-ROOM"},"v2_parent_frame":"MMX/AGENT_DIALOGUE_PARENT_V2\n{\"allowed_sol_user_ids\":[\"U0BRETDUAS2\"],\"commission_ref\":{\"commit\":\"cccccccccccccccccccccccccccccccccccccccc\",\"content_sha256\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"path\":\"research/commission.md\",\"repository\":\"mastermindx-market-intelligence/Mastermind\"},\"created_at\":\"2026-08-29T00:00:00Z\",\"fingerprint\":\"6f11388fb58cc9913963f056e4adc794286d7fec4478c635fd17301914c4f048\",\"operation_key\":\"worker-presence-dialogue-wptw1-20260829-001\",\"schema\":\"mastermind.agent_dialogue_parent.v2\",\"session_ref\":\"asd-session-turnwatch0001\",\"watch_mode\":\"turn_watch_v1\",\"work_ref\":\"WS:CHAIRMAN-CONTROL-ROOM\"}"}''')
SEALED_PROBE = r'''import importlib.abc, sys, json, tempfile
class SealedBoundary(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'integrations', 'mcp'}:
            raise AssertionError('FORBIDDEN_IMPORT:' + fullname)
assert not any(n.split('.')[0] in {'integrations', 'mcp'} for n in sys.modules)
sys.meta_path.insert(0, SealedBoundary())
g = json.load(sys.stdin)
from control_plane.dialogue_source_resolution import attention_source_ref
assert attention_source_ref(parent_fingerprint=g['v2_parent']['fingerprint'],
    message_key=g['v2_message']['message_key'], target_seat='ceo') == g['attention_source_ref']
from control_plane.executive_dialogue_observation import parse_source_reconcile_request
request = parse_source_reconcile_request(json.dumps(g['source_request']).encode())
from common.agent_dialogue_turn_watcher import classify_turn, TurnRoutingFacts, TurnAction
decision = classify_turn(parent=g['v2_parent'], messages=[g['v2_message']],
    routing=TurnRoutingFacts(g['v2_parent']['operation_key'], g['v2_parent']['fingerprint'],
        g['grant']['source_root_job_id'], None, g['v2_parent']['work_ref'], True, True))
assert decision.action is TurnAction.WAKE_CEO
assert decision.attention.target_seat == 'ceo'
from control_plane.executive_service import ExecutiveDialogueWakeBridge
from control_plane.executive_runtime import Runtime
from control_plane.dialogue_wake_canary_activation import DialogueWakeCanaryActivationGrant, DialogueWakeCanaryProfile
from control_plane.wake_ledger import WakeRetryPolicy
def forbidden_effect(*args, **kwargs):
    raise AssertionError('UNEXPECTED_EFFECT')
bridge = ExecutiveDialogueWakeBridge(target_provider=forbidden_effect,
    retry_policy=WakeRetryPolicy(), carrier_factory=forbidden_effect,
    canary_profile=DialogueWakeCanaryProfile(DialogueWakeCanaryActivationGrant.from_dict(g['grant'])),
    canary_current_facts_for=forbidden_effect, canary_now_epoch_seconds=lambda: 1788585651,
    historical_target_for=forbidden_effect)
with tempfile.TemporaryDirectory() as directory:
    runtime = Runtime.at(directory)
    result = bridge.reconcile_dialogue_sources(runtime, request)
    assert result == {'state': 'ACK_REQUIRED', 'reason': 'ADVANCED_WITHOUT_REQUEST'}, result
    from control_plane.wake_persist import WakeLedgerRepository
    with runtime.store.transaction() as connection:
        assert WakeLedgerRepository(runtime).list_ledger_records_on_connection(
            connection, g['grant']['obligation_id']) == ()
assert not any(n.split('.')[0] in {'integrations', 'mcp'} for n in sys.modules)
print('ACTUAL_LAZY_SOURCE_CLASSIFICATION_SEALED')
'''


@pytest.mark.parametrize("short", ["contract", "contract_v2", "turn_watcher"])
def test_facade_preserves_exact_object_identity(short: str) -> None:
    old = importlib.import_module("integrations.slack_agent_dialogue." + short)
    new = importlib.import_module("common.agent_dialogue_" + short)
    for name in EXPORTS[short]["explicit_exports"]:
        assert getattr(old, name) is getattr(new, name), name
    expected_all = EXPORTS[short]["all"]
    if expected_all is None:
        assert not hasattr(old, "__all__")
    else:
        assert old.__all__ == expected_all
    assert sorted(name for name in vars(old) if not name.startswith("_")) == EXPORTS[short]["public_names"]


def test_frozen_frames_and_attention_identity_remain_byte_exact() -> None:
    v1 = importlib.import_module("common.agent_dialogue_contract")
    v2 = importlib.import_module("common.agent_dialogue_contract_v2")
    watcher = importlib.import_module("common.agent_dialogue_turn_watcher")
    assert v1.render_parent(GOLDEN["v1_parent"]) == GOLDEN["v1_parent_frame"]
    assert v1.render_message(GOLDEN["v1_message"]) == GOLDEN["v1_message_frame"]
    assert v1.parse_parent_frame(GOLDEN["v1_parent_frame"]) == GOLDEN["v1_parent"]
    assert v1.parse_message_frame(GOLDEN["v1_message_frame"]) == GOLDEN["v1_message"]
    assert v2.render_parent_v2(GOLDEN["v2_parent"]) == GOLDEN["v2_parent_frame"]
    assert v2.render_message_v2(GOLDEN["v2_message"]) == GOLDEN["v2_message_frame"]
    assert v2.parse_parent_frame_v2(GOLDEN["v2_parent_frame"]) == GOLDEN["v2_parent"]
    assert v2.parse_message_frame_v2(GOLDEN["v2_message_frame"]) == GOLDEN["v2_message"]
    assert watcher._canonical_identity(
        commission_fingerprint=GOLDEN["v2_parent"]["fingerprint"],
        message_key=GOLDEN["v2_message"]["message_key"],
        target_seat="ceo",
    ) == GOLDEN["attention_identity"].encode("ascii")


def _duplicate_last_key(frame: str, key: str, value: object) -> str:
    prefix, payload = frame.split("\n", 1)
    assert payload.endswith("}")
    return prefix + "\n" + payload[:-1] + "," + json.dumps(key) + ":" + json.dumps(value) + "}"


def test_frozen_duplicate_and_nonfinite_error_codes_remain_distinct() -> None:
    v1 = importlib.import_module("common.agent_dialogue_contract")
    v2 = importlib.import_module("common.agent_dialogue_contract_v2")
    cases = (
        (v1.parse_message_frame, _duplicate_last_key(GOLDEN["v1_message_frame"], "schema", GOLDEN["v1_message"]["schema"]), "v1_duplicate"),
        (v2.parse_message_frame_v2, _duplicate_last_key(GOLDEN["v2_message_frame"], "schema", GOLDEN["v2_message"]["schema"]), "v2_duplicate"),
    )
    for parser, frame, expected in cases:
        with pytest.raises(v1.DialogueContractError) as caught:
            parser(frame)
        assert caught.value.code == GOLDEN["errors"][expected]["code"]
        assert str(caught.value) == GOLDEN["errors"][expected]["message"]
    for module, expected in ((v1, "v1_nan"), (v2, "v2_nan")):
        with pytest.raises(v1.DialogueContractError) as caught:
            module._canonical_json({"nonfinite": float("nan")})
        assert caught.value.code == GOLDEN["errors"][expected]["code"]
        assert str(caught.value) == GOLDEN["errors"][expected]["message"]


def test_actual_lazy_source_classification_is_sealed_from_integrations_and_mcp() -> None:
    repo = Path(__file__).parents[1]
    completed = subprocess.run(
        [sys.executable, "-c", SEALED_PROBE],
        input=json.dumps(GOLDEN),
        text=True,
        capture_output=True,
        cwd=repo,
        timeout=60,
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert completed.stdout.rstrip().endswith("ACTUAL_LAZY_SOURCE_CLASSIFICATION_SEALED")

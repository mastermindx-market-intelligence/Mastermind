"""Offline launch-input proof: no provider, account or real tool calls."""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from ops.fabric_launch import context as c

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 10, 6, 21, 0, tzinfo=dt.timezone.utc)
STAMP = NOW.isoformat()


@pytest.fixture
def launch_input():
    request = json.loads((ROOT / 'research/worker_craft/examples/ceo-commission-request.json').read_text())
    request['role'] = 'backend'
    ref = request['authority_ref']
    return {
        'schema': c.SCHEMA,
        'commission': request,
        'context': {'schema': c.CONTEXT_SCHEMA, 'mission_ref': ref, 'degraded': [], 'facts': [
            {'owner': 'github', 'ref': 'repo:fixture', 'revision': 'commit:fixture',
             'observed_at': STAMP, 'content': 'The assigned parser uses UTC dates.', 'required': True},
        ]},
        'tools': {'required': ['workspace.read'], 'optional': ['github.read']},
        'observations': {'schema': c.OBSERVATION_SCHEMA, 'mission_ref': ref,
                         'scope_ref': 'local:fixture:/workspace', 'items': [
            {'tool': 'workspace.read', 'state': 'CALLABLE', 'evidence_ref': 'fixture:read-proof', 'observed_at': STAMP},
        ]},
    }


def test_reuses_actual_compiler_and_preserves_original_input(launch_input):
    before = copy.deepcopy(launch_input)
    result = c.prepare(launch_input, now=NOW)
    assert launch_input == before
    assert result['state'] == 'PREPARED_NOT_ADMITTED'
    assert result['execution_authority'] is False
    assert result['native_skill_attested'] is False
    assert result['source_state'] == 'SOURCE_CANDIDATE'
    assert 'ADVISORY PROJECT FACT' in result['instructions_markdown']
    assert 'The assigned parser uses UTC dates.' in result['instructions_markdown']
    assert result['degraded'] == ['github.read:UNKNOWN']
    assert result['compiler_sha256'] == c.digest((ROOT / 'research/worker_craft/mastermind-craft/scripts/brief.py').read_bytes())
    assert c.verify_packet(result, now=NOW) == result


@pytest.mark.parametrize('role', ['orchestrator','designer','frontend','backend','researcher','data-scientist','reviewer','verifier'])
def test_all_eight_existing_craft_roles(launch_input, role):
    launch_input['commission']['role'] = role
    result = c.prepare(launch_input, now=NOW)
    assert result['role'] == role
    assert result['commission_sha256'] == c.digest(result['instructions_markdown'].encode())


@pytest.mark.parametrize('state', ['UNKNOWN','MISSING','AUTH_REQUIRED','DENIED'])
def test_required_tools_fail_before_delivery(launch_input, state):
    launch_input['observations']['items'][0]['state'] = state
    with pytest.raises(c.LaunchInputError, match='REQUIRED_TOOL_UNREADY'):
        c.prepare(launch_input, now=NOW)


@pytest.mark.parametrize('seconds', [901, 3600, -31])
def test_stale_or_future_tool_observation_refuses(launch_input, seconds):
    launch_input['observations']['items'][0]['observed_at'] = (NOW - dt.timedelta(seconds=seconds)).isoformat()
    with pytest.raises(c.LaunchInputError, match='workspace.read:STALE'):
        c.prepare(launch_input, now=NOW)


@pytest.mark.parametrize('where', ['context', 'observations'])
def test_foreign_mission_cannot_supply_context_or_tool_evidence(launch_input, where):
    launch_input[where]['mission_ref'] = 'other-mission'
    with pytest.raises(c.LaunchInputError, match='MISSION_MISMATCH'):
        c.prepare(launch_input, now=NOW)


def test_required_stale_context_refuses_optional_stale_context_is_named(launch_input):
    fact = launch_input['context']['facts'][0]
    fact['observed_at'] = (NOW - dt.timedelta(hours=1)).isoformat()
    with pytest.raises(c.LaunchInputError, match='REQUIRED_CONTEXT_UNAVAILABLE:STALE'):
        c.prepare(launch_input, now=NOW)
    fact['required'] = False
    result = c.prepare(launch_input, now=NOW)
    assert result['omitted_context'] == [{'ref': 'repo:fixture', 'revision': 'commit:fixture', 'reason': 'STALE'}]
    assert 'The assigned parser uses UTC dates.' not in result['instructions_markdown']
    assert 'EXPLICIT CONTEXT/TOOL GAPS' in result['instructions_markdown']


def test_required_context_budget_is_not_silent_truncation(launch_input):
    launch_input['context']['facts'] = [
        dict(launch_input['context']['facts'][0], ref='source:'+str(i), content='x'*2900)
        for i in range(3)
    ]
    with pytest.raises(c.LaunchInputError, match='REQUIRED_CONTEXT_UNAVAILABLE:OMITTED_BUDGET'):
        c.prepare(launch_input, now=NOW)


@pytest.mark.parametrize('key', ['provider','account','credential','worker','host','runtime_admission','execution_authority','transcript'])
def test_no_new_control_fields_or_transcript_store(launch_input, key):
    launch_input[key] = 'not-admitted'
    with pytest.raises(c.LaunchInputError, match='LAUNCH_FIELDS_INVALID'):
        c.prepare(launch_input, now=NOW)


@pytest.mark.parametrize('data', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'[]', b'\xff', b''])
def test_json_parser_rejects_ambiguous_or_malformed_inputs(data):
    with pytest.raises(c.LaunchInputError):
        c.parse(data)


def test_forged_packet_claims_do_not_survive_recompilation(launch_input):
    packet = c.prepare(launch_input, now=NOW)
    packet['execution_authority'] = True
    packet['packet_sha256'] = c.digest(c.canonical({k:v for k,v in packet.items() if k!='packet_sha256'}))
    with pytest.raises(c.LaunchInputError, match='PACKET_SOURCE_OR_INPUT_DRIFT'):
        c.verify_packet(packet, now=NOW)


def test_packet_expiry_is_rechecked_at_delivery(launch_input):
    packet = c.prepare(launch_input, now=NOW)
    with pytest.raises(c.LaunchInputError, match='REQUIRED_TOOL_UNREADY'):
        c.verify_packet(packet, now=NOW+dt.timedelta(minutes=16))


def test_tampered_prompt_or_method_is_not_delivered(launch_input):
    packet = c.prepare(launch_input, now=NOW)
    packet['instructions_markdown'] += ' modified'
    with pytest.raises(c.LaunchInputError, match='PACKET_DIGEST_MISMATCH'):
        c.verify_packet(packet, now=NOW)


def test_repeated_sources_and_tools_refuse(launch_input):
    launch_input['context']['facts'].append(copy.deepcopy(launch_input['context']['facts'][0]))
    with pytest.raises(c.LaunchInputError, match='CONTEXT_DUPLICATE_SOURCE'):
        c.prepare(launch_input, now=NOW)
    launch_input['context']['facts'].pop()
    launch_input['observations']['items'].append(copy.deepcopy(launch_input['observations']['items'][0]))
    with pytest.raises(c.LaunchInputError, match='OBSERVATION_TOOL_OR_STATE_INVALID'):
        c.prepare(launch_input, now=NOW)


@pytest.mark.parametrize('tool', ['unknown','github.admin','permissions.disable','secrets.read'])
def test_unregistered_tools_do_not_become_capabilities(launch_input, tool):
    launch_input['tools']['required'] = [tool]
    with pytest.raises(c.LaunchInputError, match='TOOL_REQUIREMENT_INVALID'):
        c.prepare(launch_input, now=NOW)


def test_malformed_tool_state_is_bounded(launch_input):
    launch_input['observations']['items'][0]['state'] = {}
    with pytest.raises(c.LaunchInputError):
        c.prepare(launch_input, now=NOW)


@pytest.mark.parametrize('task,role', [('build','backend'),('review','reviewer'),('design','designer'),('domain_orchestration','orchestrator'),('not-classified',None)])
def test_compatibility_delivery_does_not_rewrite_original_assignment(task, role):
    original = 'Repair only parser.py. Preserve unicode: \u4e2d\u6587.\nNo extra files.'
    prompt, receipt = c.augment_plain_prompt(original, task)
    assert prompt.endswith(original)
    assert receipt['role'] == role
    assert receipt['native_skill_attested'] is False
    assert receipt['project_context'] == 'NOT_SUPPLIED'
    assert 'Leaf workers do not spawn helpers' in prompt
    if role is not None:
        assert '<<<MASTERMIND_CRAFT_METHOD_V1>>>' in prompt


def test_credential_like_project_fact_refuses(launch_input):
    launch_input['context']['facts'][0]['content'] = 'ghp_' + 'A'*32
    with pytest.raises(c.LaunchInputError, match='CREDENTIAL_LIKE'):
        c.prepare(launch_input, now=NOW)


def test_omitted_context_no_answer_is_visible_not_invented(launch_input):
    launch_input['context']['facts'] = []
    launch_input['context']['degraded'] = ['Agent OS query unresolved; exact workstream required.']
    result = c.prepare(launch_input, now=NOW)
    assert 'context:Agent OS query unresolved' in result['degraded'][1]
    assert result['retained_context_refs'] == []

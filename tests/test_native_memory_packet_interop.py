"""Actual native-builder-issued synthetic vector; no full Linux issuer claim.

Supplier source0016d273/testfd24/native7PASS/review29f36 and preserved fixture
premises are retained with this exact vector. Native installation/auth/current
source grant/executor remain unimplemented; these tests prove byte interop only.
"""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from common import memory_participant_view as view
from common.memory_native_wire import canonical

ROOT=Path(__file__).parent/'fixtures/native_memory_packet_20261106'

def test_actual_native_builder_input_and_all_ten_descriptors_match_exactly():
    packet=(ROOT/'participant-input.bin').read_bytes()
    expected=(ROOT/'selected-descriptors.json').read_bytes()
    assert hashlib.sha256(packet).hexdigest()=='f4213c04dc827819ac476859803d462b27ddf4badb3d5855c52dbf701acd641f'
    assert hashlib.sha256(expected).hexdigest()=='8a445b7cabd4251a7228ca299bb2ae257f0893b3463f7cef68e44c8446f9f3e1'
    actual=view.selected_descriptors(packet)
    assert len(actual)==10 and canonical(actual)==expected
    raw=canonical({'schema':'research_factory.market_memory_e0_participant_result.v1',
        'answer':'Untrusted interoperability result','citations':[actual[-1],actual[0]]})
    result=view.project_original_result(packet,raw,attempt_id='actual-original-fixture-attempt')
    assert result['citations']==[actual[-1],actual[0]]
    assert all(v is False for v in result['verification'].values())
    assert result['scientific_admission'] is False and result['actual_blinding_established'] is False


def test_other_arm_descriptor_cannot_enter_real_native_packet_result_view():
    packet=(ROOT/'participant-input.bin').read_bytes()
    reference=copy.deepcopy(view.selected_descriptors(packet)[0]);reference['context_id']='absent-other-arm'
    raw=canonical({'schema':'research_factory.market_memory_e0_participant_result.v1',
        'answer':'Untrusted','citations':[reference]})
    with pytest.raises(view.ParticipantViewRefused):view.project_original_result(packet,raw,attempt_id='original')

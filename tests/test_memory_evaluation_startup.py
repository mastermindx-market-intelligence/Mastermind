"""Actual closed Control loader; explicit temporary installation DATA only."""
import copy
import pytest
from scripts import executive_os_phase1c as cli
from control_plane import protected_memory_evaluation_source as source
from tests.test_memory_v3_wire_configuration import stanzas
from tests.test_ceo_submit_armed_composition import _raw,_write
from tests.test_memory_evaluation_contract import ref


def document(tmp_path):
    value=stanzas()
    value['memory_evaluation']=dict(schema=source.CONFIG_SCHEMA,armed=True,coo_config=str(tmp_path/'coo.json'),coo_source=str(tmp_path/('a'*40)),work_ref='WS:INERT',source_protocol='memory.e0.evaluation_issuer.v1',profiles=[dict(id='inert-model',profile=copy.deepcopy(value['protected_memory_execution']),credential_binding_ref=ref('inert-binding'),credential_document_sha256='b'*64)])
    return value


def test_actual_loader_accepts_closed_evaluation_without_runtime_or_provider_effect(tmp_path):
    data=document(tmp_path)
    parsed=cli.load_control_config(_write(tmp_path,_raw(tmp_path,**data)))
    assert parsed['memory_evaluation']==data['memory_evaluation']
    assert not (tmp_path/'runtime').exists() and not (tmp_path/'coo.json').exists()


@pytest.mark.parametrize('fault',['extra-field','relative-config','foreign-credential-slot','missing-transport'])
def test_actual_loader_refuses_evaluation_configuration_drift(tmp_path,fault):
    data=document(tmp_path);value=data['memory_evaluation']
    if fault=='extra-field':value['trusted']=True
    elif fault=='relative-config':value['coo_config']='caller.json'
    elif fault=='foreign-credential-slot':value['profiles'][0]['profile']['credential_slot']='any-path'
    else:del data['memory_native_issuer']
    with pytest.raises(cli.ServiceError):cli.load_control_config(_write(tmp_path,_raw(tmp_path,**data)))
    assert not (tmp_path/'runtime').exists()

"""Causal inert model-harness checks: no Macro prepare/provider/SSH call."""
import base64
import json
import os
from pathlib import Path
import socket
import pytest
from common import memory_native_wire as wire
from common.protected_memory_model_input import compile_memory_model_input
from common.memory_participant_view import selected_descriptors
from control_plane import protected_memory_execution as execution
from tests.test_protected_memory_execution import joined
from tests.test_protected_memory_profile import configured
from tests.test_protected_memory_peer import installed
from tests.test_protected_memory_economic import economy

@pytest.mark.parametrize('foreign_body',[False,True])
def test_inert_model_fixture_exact_supplied_packet_and_error_is_terminal(joined,foreign_body):
    _,_,_,actions,_,done,errors,state,run=joined
    value=json.loads((Path(__file__).parent/'fixtures/memory_native_v3_9fb08/03-prepare.response.json').read_text())
    supplied=wire.packet(value['input'],value['locator']);old=state['native_packet']
    assert supplied!=old
    state['native_packet']=supplied
    body=compile_memory_model_input(old if foreign_body else supplied,model='glm-5.3-flash')
    envelope=wire.canonical({'input_base64':base64.b64encode(supplied).decode(),
        'body_base64':base64.b64encode(body).decode()})
    left,right=socket.socketpair();output=run/'inert-model-harness-result'
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        assert execution.subprocess.Popen.__name__=='Process' # actual inert fixture only
        process=execution.subprocess.Popen(['inert-fixture-only'],pass_fds=(right.fileno(),),stdout=fd,env={})
        assert left.recv(6)==b'READY\n'
        left.sendall(len(envelope).to_bytes(4,'big')+envelope);left.shutdown(socket.SHUT_WR)
        assert done.wait(3)
        assert process.poll()==(1 if foreign_body else 0)
        if foreign_body:
            assert len(errors)==1 and output.read_bytes()==b''
        else:
            assert errors==[] and json.loads(output.read_bytes())['citations']==[selected_descriptors(supplied)[0]]
        assert actions==[] # no qualification, source prepare, read or transport
    finally:os.close(fd);left.close();right.close()

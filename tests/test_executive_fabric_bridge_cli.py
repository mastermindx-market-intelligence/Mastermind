"""CLI/activation fixtures only; no real socket, launchd, install or credentials."""
import asyncio
import json
import socket
import pytest
from tests.test_executive_fabric_bridge_broker import config, Backend
try:
    from scripts import executive_fabric_bridge as cli
except ImportError:
    cli=None


def api():
    assert cli is not None, 'assigned optional bridge CLI is not implemented'
    return cli


class Activated:
    family=socket.AF_UNIX
    def __init__(self,path='/var/run/mastermind/fabric-bridge.sock'):self.path=path;self.closed=False
    def getsockname(self):return self.path
    def getsockopt(self,level,option):assert (level,option)==(socket.SOL_SOCKET,socket.SO_ACCEPTCONN);return 1
    def close(self):self.closed=True


class Server:
    def __init__(self):self.closed=False
    def close(self):self.closed=True
    async def wait_closed(self):pass


def test_check_config_has_no_activation_or_backend_construction(tmp_path,monkeypatch,capsys):
    m=api();cfg=config(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'load_config',lambda path:cfg)
    def forbidden(*args,**kwargs):pytest.fail('check-config attempted activation or backend construction')
    assert m.main(['check-config','--config',str(tmp_path/'config.json')],backend_factory=forbidden,activate_socket=forbidden)==0
    output=json.loads(capsys.readouterr().out)
    assert output['config_sha256']==cfg.source_sha256
    assert output['activated'] is False


def test_serve_without_reviewed_backend_fails_before_activation(tmp_path,monkeypatch,capsys):
    m=api();cfg=config(tmp_path,monkeypatch);monkeypatch.setattr(m,'load_config',lambda path:cfg)
    def forbidden(*args,**kwargs):pytest.fail('missing backend attempted activation')
    assert m.main(['serve','--config',str(tmp_path/'config.json')],activate_socket=forbidden)==2
    assert 'BackendNotConfiguredError' in capsys.readouterr().err


def test_cli_refuses_payload_selected_factory_or_shell():
    with pytest.raises(SystemExit):api().parser().parse_args(['serve','--config','/trusted/config','--backend-factory','untrusted'])


def test_serve_accepts_only_existing_fixed_unix_socket_and_never_sweeps(tmp_path,monkeypatch):
    m=api();cfg=config(tmp_path,monkeypatch);monkeypatch.setattr(m.os,'geteuid',lambda:501)
    active=Activated();server=Server();calls=[]
    async def create(handler,**kwargs):
        calls.append(kwargs)
        assert kwargs['sock'] is active and 'path' not in kwargs
        return server
    monkeypatch.setattr(m.asyncio,'start_unix_server',create)
    async def scenario():
        stop=asyncio.Event();stop.set()
        await m.serve(cfg,Backend(),stop_event=stop,activate_socket=lambda name:active)
    asyncio.run(scenario())
    assert active.closed and server.closed and len(calls)==1


@pytest.mark.parametrize('path',['/other/socket',''])
def test_serve_refuses_socket_binding_mismatch(tmp_path,monkeypatch,path):
    m=api();cfg=config(tmp_path,monkeypatch);monkeypatch.setattr(m.os,'geteuid',lambda:501)
    active=Activated(path)
    async def forbidden(*args,**kwargs):pytest.fail('unbound socket started serving')
    monkeypatch.setattr(m.asyncio,'start_unix_server',forbidden)
    with pytest.raises(m.BridgeProtocolError,match='SocketBindingError'):
        asyncio.run(m.serve(cfg,Backend(),activate_socket=lambda name:active))
    assert active.closed


def test_serve_refuses_wrong_uid_before_claiming_socket(tmp_path,monkeypatch):
    m=api();cfg=config(tmp_path,monkeypatch);monkeypatch.setattr(m.os,'geteuid',lambda:450)
    def forbidden(*args,**kwargs):pytest.fail('wrong UID attempted activation')
    with pytest.raises(m.BridgeProtocolError,match='BridgeIdentityError'):
        asyncio.run(m.serve(cfg,Backend(),activate_socket=forbidden))

"""Local kernel/ASGI fixtures; not Caddy UID, systemd or real ReadService proof."""
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest
from integrations.research_read_mcp.citation_transport import (
    ACTIVATION_NAME, CitationDispatcher, ListenerBundle, RuntimeBindings, TransportRefused,
    UnixSocketPolicy, adopt_systemd_unix, build_citation_consumer, run_dual_server,
)

def listening_fixture(value):
    # Darwin SO_ACCEPTCONN is unavailable. Fixture-only actual connection probe,
    # never a production fallback or Linux/systemd permission attestation.
    probe=socket.socket(value.family,socket.SOCK_STREAM);probe.settimeout(0.5)
    try:probe.connect(value.getsockname());return True
    except OSError:return False
    finally:probe.close()

@pytest.fixture(autouse=True)
def mac_listening_fixture(monkeypatch):
    if sys.platform=='darwin':
        import integrations.research_read_mcp.citation_transport as module
        monkeypatch.setattr(module,'_is_listening',listening_fixture)

ID='rvitem.v1.'+'a'*64
PATH='/os/research/evidence/'+ID

@pytest.fixture
def bundle():
    # A short, secure user-owned runtime fixture, not project source/worktree.
    with tempfile.TemporaryDirectory(prefix='rv-socket-',dir=Path.home()) as temporary:
        directory=Path(temporary);path=str(directory/'citation.sock')
        tcp=socket.socket();tcp.bind(('127.0.0.1',0));tcp.listen()
        unix=socket.socket(socket.AF_UNIX);unix.bind(path);os.chmod(path,0o600);unix.listen()
        policy=UnixSocketPolicy(path,os.getuid(),os.getuid(),os.getgid())
        listeners=ListenerBundle(tcp,unix,policy=policy,tcp_address=tcp.getsockname())
        try:yield listeners
        finally:listeners.close()


def scope(bundle,**changes):
    value=dict(type='http',method='GET',scheme='http',path=PATH,raw_path=PATH.encode(),
        query_string=b'',root_path='',server=(bundle.policy.path,None),
        headers=[(b'host',b'mcp.mastermind-x.com'),(b'accept',b'application/json'),
                 (b'authorization',b'Bearer fixture-not-a-real-token')])
    value.update(changes);return value


def dispatch(bundle,request):
    observed=[];sent=[]
    async def mcp(s,r,w):observed.append(('mcp',s))
    async def citation(s,r,w):observed.append(('citation',s))
    async def receive():return {'type':'http.request','body':b''}
    async def send(value):sent.append(value)
    app=CitationDispatcher(mcp_app=mcp,citation_app=citation,listeners=bundle)
    asyncio.run(app(request,receive,send));return observed,sent


def test_exact_unix_scope_and_bearer_preservation(bundle):
    request=scope(bundle);observed,sent=dispatch(bundle,request)
    assert observed[0][0]=='citation' and not sent
    selected=observed[0][1]
    assert selected['scheme']=='https' and selected['server']==('mcp.mastermind-x.com',443)
    assert selected['headers'] is request['headers'] and request['scheme']=='http'


def test_tcp_forged_selector_never_reaches_citation(bundle):
    request=scope(bundle,server=bundle.tcp_address,headers=[(b'host',b'mcp.mastermind-x.com'),
        (b'x-forwarded-proto',b'https'),(b'forwarded',b'proto=https')])
    observed,_=dispatch(bundle,request)
    assert observed==[('mcp',request)] and request['scheme']=='http'

@pytest.mark.parametrize('changes',[
    {'server':None},{'server':('/wrong.sock',None)},{'server':('mcp.mastermind-x.com',443)},
    {'method':'POST'},{'scheme':'https'},{'path':'/mcp/research/v1'},
    {'path':'/.well-known/oauth-protected-resource'},{'query_string':b'x=1'},
    {'root_path':'/proxy'},{'raw_path':PATH.replace('rvitem','%72vitem').encode()},
])
def test_selector_refused_before_consumer(bundle,changes):
    observed,sent=dispatch(bundle,scope(bundle,**changes))
    assert not observed and sent[0]['status']==404

@pytest.mark.parametrize('header',[
    (b'Forwarded',b'proto=https'),(b'X-Forwarded-Proto',b'https'),(b'X-Forwarded-For',b'127.0.0.1'),
    (b'X-Real-IP',b'127.0.0.1'),(b'Host',b'foreign.invalid'),(b'Accept',b'text/html'),
    (b'Authorization',b'Bearer second'),(b'Content-Length',b'1'),(b'Origin',b'https://foreign.invalid'),
])
def test_header_injection_refused(bundle,header):
    request=scope(bundle);request['headers']+=[header]
    observed,sent=dispatch(bundle,request)
    assert not observed and sent[0]['status']==404


def test_socket_mode_drift_and_replacement_fail_closed(bundle):
    request=scope(bundle)
    os.chmod(bundle.policy.path,0o660)
    with pytest.raises(TransportRefused):bundle.verify()
    os.chmod(bundle.policy.path,0o600)
    os.unlink(bundle.policy.path)
    replacement=socket.socket(socket.AF_UNIX)
    try:
        replacement.bind(bundle.policy.path);os.chmod(bundle.policy.path,0o600);replacement.listen()
        with pytest.raises(TransportRefused):bundle.verify()
        # Constructing a new dispatcher also refuses the retained old descriptor.
        with pytest.raises(TransportRefused):dispatch(bundle,request)
    finally:replacement.close()


def test_wrong_owner_symlink_and_insecure_directory(bundle):
    wrong=UnixSocketPolicy(bundle.policy.path,os.getuid(),os.getuid()+1,os.getgid())
    with pytest.raises(TransportRefused):wrong.snapshot()
    directory=Path(bundle.policy.path).parent
    link=directory/'alias';link.symlink_to(bundle.policy.path)
    with pytest.raises(TransportRefused):UnixSocketPolicy(str(link),os.getuid(),os.getuid(),os.getgid()).snapshot()
    directory.chmod(0o770)
    with pytest.raises(TransportRefused):bundle.policy.snapshot()
    directory.chmod(0o700)

@pytest.mark.parametrize('changes',[
    {'LISTEN_PID':'1'}, {'LISTEN_FDS':'2'}, {'LISTEN_FDNAMES':'another'}, {'LISTEN_FDS':'01'},
])
def test_activation_labels_are_closed_and_do_not_close_unknown_fd(bundle,changes):
    raw=os.dup(bundle.unix.fileno())
    environment=dict(LISTEN_PID=str(os.getpid()),LISTEN_FDS='1',LISTEN_FDNAMES=ACTIVATION_NAME)
    environment.update(changes)
    try:
        with pytest.raises(TransportRefused):adopt_systemd_unix(bundle.policy,environment=environment,first_fd=raw)
        os.fstat(raw)
    finally:os.close(raw)


def test_activation_qualifies_actual_fd_and_does_not_rebind(bundle):
    raw=os.dup(bundle.unix.fileno())
    activated=adopt_systemd_unix(bundle.policy,environment=dict(LISTEN_PID=str(os.getpid()),
        LISTEN_FDS='1',LISTEN_FDNAMES=ACTIVATION_NAME),first_fd=raw)
    try:
        assert activated.getsockname()==bundle.policy.path and not activated.get_inheritable()
        with pytest.raises(OSError):os.fstat(raw)
    finally:activated.close()
    assert Path(bundle.policy.path).exists()


def test_labeled_tcp_fd_cannot_be_adopted_as_unix(bundle):
    raw=os.dup(bundle.tcp.fileno())
    try:
        with pytest.raises(TransportRefused):adopt_systemd_unix(bundle.policy,environment=dict(
            LISTEN_PID=str(os.getpid()),LISTEN_FDS='1',LISTEN_FDNAMES=ACTIVATION_NAME),first_fd=raw)
        os.fstat(raw)
    finally:os.close(raw)


def test_shared_parent_link_count_change_preserves_qualified_bundle(bundle, monkeypatch):
    original = Path.lstat
    shared_parent = Path(bundle.policy.path).parent.parent

    def sibling_directory_created(path):
        info = original(path)
        if path == shared_parent:
            return SimpleNamespace(**{name: getattr(info, name) for name in
                ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')},
                st_nlink=info.st_nlink + 1)
        return info

    monkeypatch.setattr(Path, 'lstat', sibling_directory_created)
    bundle.verify()


def test_invalid_activation_fd_closes_only_owned_duplicate(bundle, monkeypatch):
    import integrations.research_read_mcp.citation_transport as module
    original_dup = os.dup
    acquired = []

    def record_duplicate(fd):
        duplicate = original_dup(fd)
        acquired.append(duplicate)
        return duplicate

    with tempfile.TemporaryFile() as original:
        monkeypatch.setattr(module.os, 'dup', record_duplicate)
        try:
            with pytest.raises(TransportRefused):
                adopt_systemd_unix(bundle.policy, environment=dict(
                    LISTEN_PID=str(os.getpid()), LISTEN_FDS='1',
                    LISTEN_FDNAMES=ACTIVATION_NAME), first_fd=original.fileno())
            os.fstat(original.fileno())
            assert len(acquired) == 1
            with pytest.raises(OSError):
                os.fstat(acquired[0])
        finally:
            for fd in acquired:
                try:
                    os.close(fd)
                except OSError:
                    pass


def test_unresolved_adapter_seam_never_constructs_an_auth_owner():
    service=SimpleNamespace();adapter=SimpleNamespace(service=service)
    with pytest.raises(TransportRefused):build_citation_consumer(None,RuntimeBindings(service,adapter,None,None,None,None))


def test_one_server_config_and_startup_failure_close_both(bundle):
    observed=[]
    class Failed:
        def __init__(self,config):
            assert config.proxy_headers is False and config.http=='h11' and config.loop=='asyncio'
            assert config.lifespan=='on' and config.workers==1
            observed.append(config)
        def run(self,*,sockets):
            assert len(sockets)==2
            raise RuntimeError('synthetic startup failure')
    async def probe(*args):pass
    with pytest.raises(RuntimeError):run_dual_server(mcp_app=probe,citation_app=probe,listeners=bundle,server_factory=Failed)
    assert len(observed)==1 and bundle.tcp.fileno()==bundle.unix.fileno()==-1
    assert Path(bundle.policy.path).exists()


def request(address,uri=PATH,headers=None,unix=False):
    client=socket.socket(socket.AF_UNIX if unix else socket.AF_INET)
    client.settimeout(3)
    try:
        client.connect(address)
        lines=[f'GET {uri} HTTP/1.1','Host: mcp.mastermind-x.com','Accept: application/json','Connection: close']
        lines+=headers or []
        client.sendall(('\r\n'.join(lines)+'\r\n\r\n').encode())
        raw=b''
        while True:
            chunk=client.recv(4096)
            if not chunk:break
            raw+=chunk
        return raw
    finally:client.close()


def test_real_uvicorn_two_listeners_one_lifespan_sigterm_and_drain(bundle,tmp_path):
    trace=tmp_path/'trace.jsonl'
    script=tmp_path/'serve_fixture.py'
    script.write_text('''import asyncio,json,os,socket,sys
from pathlib import Path
from integrations.research_read_mcp.citation_transport import ListenerBundle,UnixSocketPolicy,run_dual_server
if sys.platform=='darwin':
 import integrations.research_read_mcp.citation_transport as module
 def fixture_listening(value):
  probe=socket.socket(value.family,socket.SOCK_STREAM);probe.settimeout(0.5)
  try:probe.connect(value.getsockname());return True
  except OSError:return False
  finally:probe.close()
 module._is_listening=fixture_listening
trace=Path(sys.argv[4])
def record(value):
 with trace.open('a') as f:f.write(json.dumps(value)+'\\n')
tcp=socket.socket(fileno=int(sys.argv[1]));unix=socket.socket(fileno=int(sys.argv[2]))
bundle=ListenerBundle(tcp,unix,policy=UnixSocketPolicy(sys.argv[3],os.getuid(),os.getuid(),os.getgid()),tcp_address=tcp.getsockname())
async def reply(scope,receive,send,branch):
 record({'branch':branch,'scheme':scope['scheme'],'server':scope['server']})
 await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
 await send({'type':'http.response.body','body':json.dumps({'branch':branch,'scheme':scope['scheme']}).encode()})
async def mcp(scope,receive,send):
 if scope['type']=='lifespan':
  while True:
   message=await receive()
   if message['type']=='lifespan.startup':record({'lifecycle':'startup'});await send({'type':'lifespan.startup.complete'})
   elif message['type']=='lifespan.shutdown':record({'lifecycle':'shutdown'});await send({'type':'lifespan.shutdown.complete'});return
 else:await reply(scope,receive,send,'mcp')
async def citation(scope,receive,send):await reply(scope,receive,send,'citation')
run_dual_server(mcp_app=mcp,citation_app=citation,listeners=bundle)
record({'audit':'closed_after_server'})
''')
    process=subprocess.Popen([sys.executable,str(script),str(bundle.tcp.fileno()),str(bundle.unix.fileno()),
        bundle.policy.path,str(trace)],pass_fds=(bundle.tcp.fileno(),bundle.unix.fileno()),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=os.environ.copy())
    address=bundle.tcp_address;path=bundle.policy.path
    bundle.close() # the child now solely owns both inherited listener descriptors
    try:
        deadline=time.monotonic()+15
        while not trace.exists():
            if process.poll() is not None:raise AssertionError(process.communicate()[1].decode())
            if time.monotonic()>deadline:raise AssertionError('fixture did not start')
            time.sleep(0.02)
        # Startup event precedes the final listen registration by a few ms.
        deadline=time.monotonic()+5
        while True:
            try:tcp=request(address,headers=['X-Forwarded-Proto: https']);break
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(0.02)
        assert b'"branch": "mcp"' in tcp and b'"scheme": "http"' in tcp
        unix=request(path,unix=True)
        assert b'"branch": "citation"' in unix and b'"scheme": "https"' in unix
        assert b'404' in request(path,headers=['X-Forwarded-Proto: https'],unix=True)
        assert b'404' in request(path,uri='/mcp/research/v1',unix=True)
        process.send_signal(signal.SIGTERM)
        out,err=process.communicate(timeout=10)
        assert process.returncode == 0,err.decode()
        rows=[json.loads(line) for line in trace.read_text().splitlines()]
        assert [row['lifecycle'] for row in rows if 'lifecycle' in row]==['startup','shutdown']
        assert rows[-1]=={'audit':'closed_after_server'}
        for destination,is_unix in ((address,False),(path,True)):
            with pytest.raises(OSError):request(destination,unix=is_unix)
        assert Path(path).exists() # no automatic stale-file deletion
    finally:
        if process.poll() is None:process.terminate();process.communicate(timeout=10)


def test_signal_owner_restores_handlers_and_retains_force_exit():
    import uvicorn
    from integrations.research_read_mcp.citation_transport import _draining_server_type
    server = _draining_server_type()(uvicorn.Config(lambda *args: None))
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    with server.capture_signals():
        for sig in before:
            assert signal.getsignal(sig) == server.handle_exit
        server.handle_exit(signal.SIGINT, None)
        assert server.should_exit and not server.force_exit
        server.handle_exit(signal.SIGINT, None)
        assert server.force_exit
    assert {sig: signal.getsignal(sig) for sig in before} == before


def test_unqualified_uvicorn_version_refused(monkeypatch):
    import uvicorn
    from integrations.research_read_mcp.citation_transport import _draining_server_type
    monkeypatch.setattr(uvicorn, '__version__', 'unqualified')
    with pytest.raises(TransportRefused):
        _draining_server_type()


@pytest.mark.parametrize('address', [('127.0.0.1',8767), ('::1',8768), ('localhost',8769)])
def test_single_mcp_mode_uses_same_draining_owner_and_loopback_contract(address):
    from integrations.research_read_mcp.citation_transport import run_mcp_server, MCP_ADDRESS
    seen = []
    class Server:
        started = True
        def __init__(self, config):
            assert (config.host, config.port) == address
            assert config.proxy_headers is False and config.workers == 1
            assert config.loop == 'asyncio' and config.http == 'h11'
        def run(self):
            seen.append('single-server')
    run_mcp_server(app=lambda *args: None, host=address[0], port=address[1], server_factory=Server)
    assert seen == ['single-server']
    with pytest.raises(TransportRefused):
        run_mcp_server(app=lambda *args: None, host='0.0.0.0', port=MCP_ADDRESS[1], server_factory=Server)

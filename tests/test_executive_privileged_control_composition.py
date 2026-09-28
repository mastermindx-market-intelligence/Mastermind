"""Default-off composition and real Unix-socket vertical; no host effects."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_privileged_client as client
from control_plane.executive_privileged_authority import PrivilegedReadinessController
from control_plane.executive_service import ExecutiveControlService, send_control_request
from scripts import executive_os_phase1c as cli
from test_c1_installer_control_config import _embedded_control_config_generator
from test_c1_ceo_ingress_composition import _raw
from test_executive_privileged_controller import setup, BOOT, RELEASE
from test_executive_service import _config, _FakeSupervisor

ROOT = Path(__file__).resolve().parents[1]
SOCKET = '/var/run/mastermind-executive/privileged.sock'


@pytest.mark.parametrize('armed,path,valid', [(False,None,True),(True,SOCKET,True),
    (True,None,False),(False,SOCKET,False),(True,'/tmp/alternate.sock',False),
    (1,SOCKET,False),(True,'/var/run/mastermind-executive/../privileged.sock',False)])
def test_closed_arm_configuration(tmp_path, armed, path, valid):
    if valid:
        cfg = _config(tmp_path, privileged_readiness_armed=armed, privileged_broker_socket_path=path)
        assert cfg.privileged_readiness_armed is armed
    else:
        with pytest.raises(ValueError):
            _config(tmp_path, privileged_readiness_armed=armed, privileged_broker_socket_path=path)


@pytest.mark.parametrize('armed,injected', [(False,True),(True,False)])
def test_arm_and_factory_must_agree(tmp_path, armed, injected):
    cfg = _config(tmp_path, privileged_readiness_armed=armed, privileged_broker_socket_path=SOCKET if armed else None)
    with pytest.raises(ValueError):
        ExecutiveControlService(cfg, supervisor_factory=_FakeSupervisor,
            privileged_readiness_controller_factory=(lambda rt: object()) if injected else None)


@pytest.mark.parametrize('armed', [False, True])
def test_production_factory_uses_one_existing_runtime_and_release(tmp_path, monkeypatch, armed):
    raw = _raw(tmp_path)
    raw.update(privileged_readiness_armed=armed, privileged_broker_socket_path=SOCKET if armed else None)
    captured = {}
    class Capture:
        def __init__(self, config, **kwargs): captured.update(config=config, **kwargs)
    monkeypatch.setattr(cli, 'ExecutiveControlService', Capture)
    monkeypatch.setattr(cli, 'activate_launchd_socket', lambda name: object())
    cli._service_from_config(raw)
    factory = captured['privileged_readiness_controller_factory']
    if armed:
        rt = object(); controller = factory(rt)
        assert controller.runtime is rt and controller.release_sha == raw['proof_base_sha']
    else: assert factory is None


@pytest.mark.parametrize('lost', [False, True])
def test_real_control_and_broker_sockets_recover_one_effect(setup, tmp_path, lost):
    runtime, request, broker, _, clock = setup
    broker.mode = 'lost' if lost else 'terminal'
    with tempfile.TemporaryDirectory(prefix='p703-', dir='/tmp') as short:
        root = Path(short)
        cfg = _config(tmp_path, socket_root=root, runtime_root=tmp_path,
            privileged_readiness_armed=True, privileged_broker_socket_path=SOCKET)
        transport = SimpleNamespace(send_effect=partial(client.send_effect, socket_path=root/'broker.sock'),
            send_status=partial(client.send_status, socket_path=root/'broker.sock'),
            validate_effect_response=client.validate_effect_response,
            validate_status_response=client.validate_status_response)
        built = []
        def factory(rt):
            assert rt is runtime
            value = PrivilegedReadinessController(rt, release_sha=RELEASE,
                boot_observer=lambda: BOOT, broker_client=transport)
            built.append(value)
            return value
        def service():
            return ExecutiveControlService(cfg, runtime_factory=lambda _root: runtime,
                supervisor_factory=_FakeSupervisor, privileged_readiness_controller_factory=factory)
        async def handle(reader, writer):
            try:
                wire = json.loads(await reader.readline())
                try:
                    result = broker.send_effect(wire) if 'action' in wire else broker.send_status(wire)
                except TimeoutError: return  # The fake broker completed but lost the reply.
                writer.write((json.dumps(result)+'\n').encode()); await writer.drain()
            finally:
                writer.close(); await writer.wait_closed()
        async def run():
            server = await asyncio.start_unix_server(handle, path=str(root/'broker.sock'))
            first = service(); await first.start()
            try:
                responses = await asyncio.gather(*(send_control_request(cfg.socket_path, 'check-current-worker-login', request) for _ in range(8)))
                assert all(r['ok'] for r in responses)
                assert all(r['result']['state'] == ('EFFECT_UNKNOWN' if lost else 'TERMINAL') for r in responses)
                assert len(broker.effects) == 1
                for changed in [dict(request, worker_id='codex-01'), dict(request, fence_generation=True), dict(request, fence_generation=99)]:
                    rejected = await send_control_request(cfg.socket_path, 'check-current-worker-login', changed)
                    assert rejected['ok'] is False
                first._service_state = 'AWAITING_CANARY'
                assert not (await send_control_request(cfg.socket_path, 'check-current-worker-login', request))['ok']
            finally: await first.close()
            assert built[0]._closed
            # Restart after lease expiry: existing-family evidence must bypass new authority.
            clock[0] += 60_000
            second = service(); await second.start()
            try:
                process = await asyncio.create_subprocess_exec(sys.executable, str(ROOT/'scripts/executive_os_phase1c.py'),
                    '--socket', str(cfg.socket_path), 'check-current-worker-login', request['job_id'], request['attempt_id'], str(request['fence_generation']),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await asyncio.wait_for(process.communicate(), 15)
                assert process.returncode == 0, stderr.decode()
                result = json.loads(stdout)['result']
                assert result['state'] == 'TERMINAL' and result['replayed'] is True
                assert result['observation_scope'] == 'LOGIN_STATUS_ONLY_NO_READY_ASSERTION'
                assert not {'ready', 'READY', 'lease_token'} & result.keys()
                assert len(broker.effects) == 1 and len(broker.queries) == (1 if lost else 0)
            finally:
                await second.close(); server.close(); await server.wait_closed()
        asyncio.run(asyncio.wait_for(run(), 30))


def render_config(tmp_path, arm, source=''):
    destination = tmp_path/'control.json'
    args = [str(ROOT),str(destination),str(source),'/private/runtime','/private/admin','/private/workspaces',
        'a'*40,'/private/backups','/private/receipts','/private/home','/private/runs','/private/canary.json',
        '/private/attestation.json','450','451','451','501','b'*64,'0.147.0',arm]
    result = subprocess.run([sys.executable,'-c',_embedded_control_config_generator(),*args], capture_output=True,text=True)
    return result, destination


@pytest.mark.parametrize('arm', ['0','1'])
def test_installer_derives_arm_and_refuses_source_override(tmp_path, arm):
    result, destination = render_config(tmp_path, arm)
    assert result.returncode == 0, result.stderr
    config = json.loads(destination.read_text())
    assert config['privileged_readiness_armed'] is (arm == '1')
    assert config['privileged_broker_socket_path'] == (SOCKET if arm == '1' else None)
    original = dict(config)
    for field, value in [('privileged_readiness_armed',arm != '1'),('privileged_broker_socket_path','/tmp/other')]:
        source = tmp_path/'override.json'; source.write_text(json.dumps(dict(original, **{field:value})))
        rejected, _ = render_config(tmp_path, arm, source)
        assert rejected.returncode != 0 and 'conflicts' in rejected.stderr


def test_installed_wrapper_executes_only_three_fixed_arguments(tmp_path):
    source = (ROOT/'ops/executive_os/install.sh').read_text()
    start = source.index("  /usr/bin/printf '%s\\n' '#!/bin/bash' 'set -eu'")
    end = source.index('  /usr/sbin/chown root:wheel "$MMX_CONTROL_TEMP"', start)
    body = source[start:end]
    assert source.index('PRIVILEGED_BROKER_LIVE="1"', source.index('if [ "$ARM_PRIVILEGED_BROKER" = "1" ]; then', source.index('release_manifest.py" verify'))) < start
    executable = tmp_path/'capture-python'
    captured = tmp_path/'argv.json'
    executable.write_text('#!'+sys.executable+'\nimport json,sys\nopen('+repr(str(captured))+',"w").write(json.dumps(sys.argv[1:]))\n')
    executable.chmod(0o755)
    wrapper = tmp_path/'mmx-control'
    env = dict(os.environ,PYTHON_BINARY=str(executable), RELEASE_ROOT=str(tmp_path/'exact release'),MMX_CONTROL_TEMP=str(wrapper))
    subprocess.run(['/bin/bash','-c',body],env=env,check=True)
    good = ['JOB-001','ATT-'+'1'*32,'1']
    subprocess.run(['/bin/bash',str(wrapper),*good],check=True)
    assert json.loads(captured.read_text()) == ['-I','-S','-B',str(tmp_path/'exact release/scripts/executive_os_phase1c.py'),
        '--socket','/var/run/mastermind-executive/control.sock','check-current-worker-login',*good]
    before = captured.read_bytes()
    for bad in [[],good+['extra'],['--socket',*good[1:]],[good[0],'--force',good[2]],[*good[:2],'-1']]:
        assert subprocess.run(['/bin/bash',str(wrapper),*bad]).returncode == 64
        assert captured.read_bytes() == before


def test_worker_slot_import_from_isolated_release_root():
    code = 'import sys; sys.path.insert(0,sys.argv[1]); from ops.executive_os.provider_worker_slots import get_slot; print(get_slot("codex-01").slot_id)'
    result = subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(ROOT)],cwd='/',capture_output=True,text=True)
    assert result.returncode == 0 and result.stdout.strip() == 'codex-01'

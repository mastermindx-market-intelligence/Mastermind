"""Fixed root-parent metadata helper; incumbent paid owners retain all effects.

No caller-selected path, route, broker, module, packet, credential or result.
Only an inherited kernel-root socket from the actual parent is accepted.
"""
from __future__ import annotations
import os
from pathlib import Path
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))


def main():
    if os.geteuid()!=501 or len(sys.argv)!=2 or not sys.argv[1].isdigit(): return 75
    from control_plane.executive_peer_identity import capture_peer_identity, _current_capture
    from control_plane.protected_memory_economic_owner import qualify_helper_source, OWNER, SCHEMA, ACTIONS
    from common import memory_native_wire as wire
    channel=socket.socket(fileno=int(sys.argv[1])); channel.settimeout(25)
    parent=capture_peer_identity(channel)
    if parent.euid!=0 or parent.pid!=os.getppid(): return 75
    _current_capture(parent); qualify_helper_source()
    raw=bytearray()
    while len(raw)<=16388:
        part=channel.recv(min(4096,16389-len(raw)))
        if not part: break
        raw.extend(part)
    if len(raw)<5 or int.from_bytes(raw[:4],'big')!=len(raw)-4: return 75
    value=wire.parse(bytes(raw[4:]),16384)
    wire.exact(value,'schema action selector route arguments controller_pid delegation')
    if type(value['controller_pid']) is not int or value['controller_pid']<=0:return 75
    if value['schema']!=SCHEMA or value['action'] not in ACTIONS: return 75
    # Check existing namespace BEFORE Broker's historical mkdir/init behavior.
    import stat
    for path in (OWNER/'broker/leases.sqlite',OWNER/'broker/leases.lock'):
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=501 or info.st_mode&0o022: return 75
    native=ROOT/'ops/native_fabric/provider_plans/memory118/native_owner'
    sys.path[:0]=[str(native),str(ROOT/'ops/native_fabric/quota_continuity/candidate'),
                  str(ROOT/'ops/native_fabric/quota_continuity/source')]
    import lease_broker
    import pool_ledger
    from fabric_operator_owner import OperatorOwner
    from protected_memory_economic import ProtectedMemoryEconomicOwner,root_helper_invocation
    kit=OWNER.parent
    # All incumbent quota/fairness/external gates remain ON. No provider probe,
    # relaxed check_pid, alternate account/host or new cache/allowance exists.
    broker=lease_broker.Broker(db_path=str(OWNER/'broker/leases.sqlite'),
        lock_path=str(OWNER/'broker/leases.lock'),accounts_path=str(kit/'orch/fabric/accounts.yaml'),
        status_json=str(kit/'orch/fabric/status.json'),hosts_path=str(OWNER/'hosts.json'),
        host_state_dir=str(OWNER/'state/hosts'),host_validator_path=str(OWNER/'glm_keys.py'),existing_only=True)
    expected_ledger=kit/'orch/fabric/ledger.jsonl'
    pool_ledger.LEDGER_PATH=str(expected_ledger)
    owner=ProtectedMemoryEconomicOwner(OperatorOwner(here=OWNER),broker)
    _current_capture(parent)
    action=value['action']; selector=value['selector']; args=value['arguments']
    if action!='acquire': owner.require_route(selector,value['route'],ready=action!='settle')
    if action=='acquire':
        wire.exact(value['delegation'],'token task_class task_complexity model')
        request=dict(schema='mastermind.fabric_protected_memory_pre_input.v1',**selector,model=value['route']['model'],
            task_class=value['delegation']['task_class'],task_complexity=value['delegation']['task_complexity'])
        authority=root_helper_invocation(channel,request)
        receipt=owner.acquire(selector,value['route'],controller_pid=value['controller_pid'],
            delegation=value['delegation'],authority=authority)
    elif action in ('current','heartbeat'): receipt=getattr(owner,action)(selector)
    else: receipt=getattr(owner,action)(selector,args)
    _current_capture(parent)
    encoded=wire.canonical({'schema':SCHEMA,'receipt':receipt})
    if len(encoded)>16384:return 75
    channel.sendall(len(encoded).to_bytes(4,'big')+encoded)
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception: raise SystemExit(75)

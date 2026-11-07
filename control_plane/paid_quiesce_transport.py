"""One closed Root-broker receipt-FD operation on the existing paid socket.

No caller JSON is an administrative credential. The receiver requires an
actual kernel Root connection and the original read-only inflight descriptor;
the sender requires the original production broker's live private context.
"""
from __future__ import annotations
import array
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import time
from uuid import UUID

from control_plane.executive_worker_broker import BROKER_REQUEST_SCHEMA_VERSION, BROKER_RESPONSE_SCHEMA_VERSION
from control_plane.executive_fabric_bridge_broker import _strict_json, _canonical

READY=b'PAID_STOP_FD_READY_V1\n'
SOCKET=Path('/var/run/mastermind-executive/fabric-glm-paid-01.sock')
MAX_FRAME=65536


def _refuse():
    raise ValueError('canonical_paid_quiesce_unconfirmed')


def _recv_fd_frame(connection):
    deadline=time.monotonic()+5
    raw=bytearray();fds=[]
    try:
        while not raw.endswith(b'\n'):
            remaining=deadline-time.monotonic()
            if remaining<=0:_refuse()
            connection.settimeout(remaining)
            data,ancillary,flags,_=connection.recvmsg(MAX_FRAME+1-len(raw),socket.CMSG_SPACE(2*array.array('i').itemsize))
            malformed=False
            for level,kind,body in ancillary:
                if level!=socket.SOL_SOCKET or kind!=socket.SCM_RIGHTS:
                    malformed=True
                    continue
                values=array.array('i')
                aligned=len(body)-len(body)%values.itemsize
                values.frombytes(body[:aligned]);fds.extend(values)
                if aligned!=len(body):malformed=True
            # Collect every delivered descriptor before rejecting ancillary
            # framing, so the error path also closes later SCM_RIGHTS entries.
            for fd in fds:os.set_inheritable(fd,False)
            if malformed:_refuse()
            if flags & (socket.MSG_CTRUNC|socket.MSG_TRUNC):_refuse()
            if not data or len(raw)+len(data)>MAX_FRAME:_refuse()
            raw.extend(data)
        if len(fds)!=1 or bytes(raw).count(b'\n')!=1:_refuse()
        result=_strict_json(bytes(raw))
        fd=fds.pop()
        return result,fd
    finally:
        for fd in fds:
            try:os.close(fd)
            except OSError:pass


def _root_exchange(broker,connection):
    received=None
    response=None
    nonce=None
    try:
        request,received=_recv_fd_frame(connection)
        if (type(request) is not dict or set(request)!={'schema_version','request_id','operation','payload'}
                or request['schema_version']!=BROKER_REQUEST_SCHEMA_VERSION
                or request['operation']!='service-quiesce'
                or type(request['request_id']) is not str
                or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',request['request_id']) is None):_refuse()
        payload=request['payload']
        if type(payload) is not dict:_refuse()
        fields={'nonce','stop_intent','phase'} | ({'fence_id'} if payload.get('phase') in {'revalidate','release'} else set())
        if set(payload)!=fields or payload['phase'] not in {'acquire','revalidate','release'}:_refuse()
        nonce=payload['nonce']
        if type(nonce) is not str or re.fullmatch(r'[0-9a-f]{32}',nonce) is None:_refuse()
        from control_plane.paid_stop_authority import qualify_stop_receipt
        authority=qualify_stop_receipt(received,connection,stop_intent=payload['stop_intent'])
        os.close(received);received=None
        broker.require_service_identity()
        result=broker.backend.service_quiesce(authority,stop_intent=payload['stop_intent'],
            phase=payload['phase'],fence_id=payload.get('fence_id'))
        response=dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,request_id=request['request_id'],
            operation='service-quiesce',ok=True,result=dict(result,nonce=nonce))
    except Exception:
        response=dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,request_id=None,
            operation='service-quiesce',ok=False,error={'code':'EFFECT_UNKNOWN'})
    finally:
        if received is not None:os.close(received)
    raw=_canonical(response)+b'\n'
    if len(raw)>MAX_FRAME:_refuse()
    connection.settimeout(5)
    connection.sendall(raw)
    deadline=time.monotonic()+5
    if response['ok'] is True:
        ack=bytearray()
        while len(ack)<33:
            remaining=deadline-time.monotonic()
            if remaining<=0:_refuse()
            connection.settimeout(remaining)
            chunk=connection.recv(33-len(ack))
            if not chunk:_refuse()
            ack.extend(chunk)
        if bytes(ack)!=nonce.encode()+b'\n':_refuse()


async def handle_root_quiesce(broker,reader,writer):
    """Pause ordinary byte reads before the explicit ancillary handshake."""
    connection=None
    try:
        transport=writer.transport
        transport.pause_reading()
        original=writer.get_extra_info('socket')
        if original is None:_refuse()
        connection=original.dup()
        # Actual proof is captured afresh by the opaque receipt owner after
        # recvmsg. No constructed PeerCredentials is transported as authority.
        from control_plane.executive_worker_broker import get_peer_credentials
        if get_peer_credentials(connection).uid!=0:_refuse()
        writer.write(READY);await writer.drain()
        await asyncio.to_thread(_root_exchange,broker,connection)
    finally:
        if connection is not None:connection.close()
        writer.close()
        try:await writer.wait_closed()
        except (OSError,ConnectionError):pass


def _read_frame(connection,limit):
    raw=bytearray()
    deadline=time.monotonic()+5
    while not raw.endswith(b'\n'):
        remaining=deadline-time.monotonic()
        if remaining<=0:_refuse()
        connection.settimeout(remaining)
        data=connection.recv(min(4096,limit+1-len(raw)))
        if not data or len(raw)+len(data)>limit:_refuse()
        raw.extend(data)
    if bytes(raw).count(b'\n')!=1:_refuse()
    return bytes(raw)


def quiesce_paid_service(phase,expected_release_sha,expected_definition_sha256,*,fence=None):
    from control_plane.executive_privileged_broker import (
        require_paid_lifecycle_owner,paid_lifecycle_intent,paid_lifecycle_receipt_fd)
    require_paid_lifecycle_owner('stop',expected_release_sha,expected_definition_sha256)
    if phase not in {'acquire','revalidate','release'}:_refuse()
    if (phase=='acquire' and fence is not None or phase!='acquire' and (
            type(fence) is not str or re.fullmatch(r'[0-9a-f]{64}',fence) is None)):_refuse()
    intent=paid_lifecycle_intent('stop',expected_release_sha,expected_definition_sha256)
    fd=paid_lifecycle_receipt_fd('stop',expected_release_sha,expected_definition_sha256)
    try:
        before=SOCKET.lstat()
        if (not stat.S_ISSOCK(before.st_mode) or (before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode),before.st_nlink)!=(0,450,0o660,1)):_refuse()
        nonce=secrets.token_hex(16);request_id='paid-quiesce-'+nonce
        payload=dict(nonce=nonce,stop_intent=intent,phase=phase)
        if fence is not None:payload['fence_id']=fence
        request=dict(schema_version=BROKER_REQUEST_SCHEMA_VERSION,request_id=request_id,
                     operation='service-quiesce',payload=payload)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(5);connection.connect(str(SOCKET))
            if _read_frame(connection,64)!=READY:_refuse()
            wire=_canonical(request)+b'\n'
            if connection.sendmsg([wire],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])!=len(wire):_refuse()
            response=_strict_json(_read_frame(connection,MAX_FRAME))
            if (type(response) is not dict or set(response)!={'schema_version','request_id','operation','ok','result'}
                    or response['schema_version']!=BROKER_RESPONSE_SCHEMA_VERSION
                    or response['request_id']!=request_id or response['operation']!='service-quiesce'
                    or response['ok'] is not True):_refuse()
            from control_plane.executive_peer_identity import capture_peer_identity,_current_capture
            from control_plane.codex_worker import ProcessInspector
            peer=capture_peer_identity(connection);_current_capture(peer)
            boot=ProcessInspector().boot_session_id()
            if (type(boot) is not str or str(UUID(boot))!=boot.lower()
                    or peer.euid!=501 or UUID(boot).int==0):_refuse()
            result=response['result']
            if type(result) is not dict or type(result.get('process')) is not dict:_refuse()
            if (type(result) is not dict or set(result)!={'schema_version','stop_intent','fence_id','process',
                    'quiesced','broker_process','receipt_sha256','nonce'}
                    or result['nonce']!=nonce or result['stop_intent']!=intent or result['quiesced'] is not True
                    or result['process'].get('pid')!=peer.pid or result['process'].get('boot_id')!=boot
                    or result['schema_version']!='mastermind.canonical_paid_quiescence/v1'
                    or type(result['fence_id']) is not str or re.fullmatch(r'[0-9a-f]{64}',result['fence_id']) is None
                    or type(result['receipt_sha256']) is not str or re.fullmatch(r'[0-9a-f]{64}',result['receipt_sha256']) is None
                    or type(result['broker_process']) is not dict
                    or set(result['broker_process'])!={'pid','pidversion','euid','audit_identity_digest','boot_id'}
                    or result['broker_process']['pid']!=os.getpid() or result['broker_process']['euid']!=0
                    or result['broker_process']['boot_id']!=boot
                    or (fence is not None and result['fence_id']!=fence)):_refuse()
            if hashlib.sha256(os.pread(fd,65537,0)).hexdigest()!=result['receipt_sha256']:_refuse()
            _current_capture(peer)
            after=SOCKET.lstat()
            identity=lambda x:(x.st_dev,x.st_ino,x.st_uid,x.st_gid,x.st_mode,x.st_nlink)
            if identity(before)!=identity(after):_refuse()
            connection.sendall(nonce.encode()+b'\n')
            result={key:value for key,value in result.items() if key!='nonce'}
            result['kernel_peer']=dict(euid=peer.euid,pid=peer.pid,pidversion=peer.pidversion,
                audit_identity_digest=peer.audit_identity_digest,boot_id=boot)
            require_paid_lifecycle_owner('stop',expected_release_sha,expected_definition_sha256)
            return result
    finally:os.close(fd)

"""One sealed exact-input model request for the incumbent protected Control owner.

No CLI path/endpoint/account/model selector. The private parent channel binds
actual input/profile; fixed root-owned enrollment supplies provider identity.
This executable is source-only until installed/qualified; it never enrolls or
refreshes anything and never retries. Diagnostic output is fixed and secret-free.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from common import memory_native_wire as wire
from common.protected_memory_model_input import decode_memory_model_input
from control_plane import protected_memory_profile as profile


def _credential(expected, *, evaluation_profile=None):
    from control_plane.codex_provider_realm import _native_open
    path=profile.CREDENTIAL
    if evaluation_profile is not None:
        from control_plane import protected_memory_evaluation_source as evaluation
        path=evaluation.SLOTS[expected['credential_slot']]
    with _native_open(path) as (fd,info):
        import stat
        if (info.st_uid!=0 or info.st_gid!=450 or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode)!=0o440 or info.st_nlink!=1 or not 1<=info.st_size<=8192):raise ValueError
        raw=os.read(fd,8193)
        identity=lambda s:(s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if len(raw)!=info.st_size or identity(info)!=identity(os.fstat(fd)):raise ValueError
    value=profile._json(raw)
    if evaluation_profile is not None and hashlib.sha256(raw).hexdigest()!=evaluation_profile['credential_document_sha256']:raise ValueError
    wire.exact(value,'schema account_ref api_key')
    if (value['schema']!='mastermind.protected_memory_model_credential.v1'
            or value['account_ref']!=expected['account_ref'] or type(value['api_key']) is not str
            or not 16<=len(value['api_key'])<=4096 or any(ord(c)<33 or ord(c)>126 for c in value['api_key'])):raise ValueError
    return value['api_key']

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('fixed_provider_origin_required')


def _post(profile_value,body,key):
    # Preserve the native packet as the SINGLE user-message content; no schema,
    # system prompt, history, tools, provider envelope or instruction append.
    value=json.loads(body)
    chat={'model':value['model'],'messages':[{'role':'user','content':value['input']}],
        'stream':False,'max_tokens':8192}
    request=urllib.request.Request(profile_value['api_origin']+'/chat/completions',
        data=wire.canonical(chat),headers={'Authorization':'Bearer '+key,
        'Content-Type':'application/json','Accept':'application/json'},method='POST')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(request,timeout=600) as response:
        if response.status!=200:raise ValueError
        raw=response.read(262145)
        if len(raw)>262144:raise ValueError
    reply=profile._json(raw)
    if type(reply) is not dict or type(reply.get('choices')) is not list or len(reply['choices'])!=1:raise ValueError
    choice=reply['choices'][0]
    if type(choice) is not dict or choice.get('finish_reason')!='stop':raise ValueError
    message=choice.get('message')
    if type(message) is not dict or message.get('role')!='assistant' or type(message.get('content')) is not str:raise ValueError
    if any(message.get(k) for k in ('tool_calls','function_call')):raise ValueError
    result=message['content'].encode('utf-8')
    if not 1<=len(result)<=65536:raise ValueError
    return result


def main():
    if os.geteuid()!=450 or len(sys.argv)!=2 or not sys.argv[1].isdigit():return 75
    channel=socket.socket(fileno=int(sys.argv[1]))
    channel.settimeout(125)
    from control_plane.executive_peer_identity import capture_peer_identity, require_installed_service_peer
    from control_plane.executive_installed_peer import qualify_installed_peer
    parent=capture_peer_identity(channel)
    if parent.pid!=os.getppid() or parent.euid!=450:return 75
    binding=qualify_installed_peer(parent,role='control')
    context=require_installed_service_peer(parent,binding)
    if context.service_label!='com.mastermind.executive.control':return 75
    # Child is inspected by parent BEFORE this handshake releases any input,
    # credential or provider call. No public socket/listener exists.
    channel.sendall(b'READY\n')
    chunks=bytearray()
    while len(chunks)<=400004:
        part=channel.recv(min(65536,400005-len(chunks)))
        if not part:break
        chunks.extend(part)
    if len(chunks)<5 or int.from_bytes(chunks[:4],'big')!=len(chunks)-4:return 75
    value=wire.parse(bytes(chunks[4:]),400000)
    evaluation_profile=None
    if value.get('schema')=='mastermind.protected_memory_evaluation_model_request.v1':
        wire.exact(value,'schema profile_id profile_sha256 input_sha256 input_base64 body_base64')
    else:
        wire.exact(value,'schema profile_sha256 input_sha256 input_base64 body_base64')
        if value['schema']!='mastermind.protected_memory_model_request.v1':return 75
    import base64
    packet=base64.b64decode(value['input_base64'],validate=True)
    body=base64.b64decode(value['body_base64'],validate=True)
    if hashlib.sha256(packet).hexdigest()!=value['input_sha256']:return 75
    config=profile._json(profile._read_config());selected=config.get('protected_memory_execution')
    if value['schema']=='mastermind.protected_memory_evaluation_model_request.v1':
        from control_plane import protected_memory_evaluation_source as evaluation
        rows=[r for r in evaluation.configured(config)['profiles'] if r['id']==value['profile_id']]
        if len(rows)!=1:return 75
        evaluation_profile=rows[0];selected=evaluation.profile_document(evaluation_profile['profile'])
    if type(selected) is not dict or hashlib.sha256(profile.canonical(selected)).hexdigest()!=value['profile_sha256']:return 75
    decode_memory_model_input(body,expected_packet=packet,expected_model=selected['model'])
    require_installed_service_peer(parent,binding)
    # No provider call can precede exact profile/body checks and parent release.
    result=_post(selected,body,_credential(selected,evaluation_profile=evaluation_profile))
    sys.stdout.buffer.write(result);sys.stdout.buffer.flush()
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        # Never put upstream response bodies, keys, packet or exception text in
        # process logs. Nonzero/transport loss remains original UNKNOWN.
        sys.stderr.write('PROTECTED_MEMORY_MODEL_UNAVAILABLE\n')
        raise SystemExit(75)

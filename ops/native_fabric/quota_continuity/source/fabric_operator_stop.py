#!/usr/bin/env python3
"""Active Stop attention for one already-admitted paid operator, never a scheduler."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import stat
import urllib.request

ENDPOINT = 'https://m2studio.taila6eca1.ts.net/studio-fabric'
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
EVENTS = frozenset((
    'operator_stop:hook_entered',
    'operator_stop:exit_non_stop',
    'operator_stop:exit_no_binding',
    'operator_stop:mcp_initialize',
    'operator_stop:mcp_query',
    'operator_stop:mcp_error',
    'operator_stop:decision_quiet',
    'operator_stop:decision_block',
    'operator_stop:attention_persist',
    'operator_stop:attention_error',
    'operator_stop:observation_error',
    'operator_stop:parse_failure',
    'operator_stop:attention_existing',
    'operator_stop:block_emitted',
))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('operator_attention_redirect_refused')


def diagnose(event):
    # Diagnostic failure never changes attention, stdout, or lifecycle authority.
    mapping = {
        'operator_stop:hook_entered': 'entered',
        'operator_stop:exit_non_stop': 'not_stop',
        'operator_stop:exit_no_binding': 'binding_missing',
        'operator_stop:mcp_initialize': 'initialize',
        'operator_stop:mcp_query': 'query',
        'operator_stop:mcp_error': 'observation_failed',
        'operator_stop:decision_quiet': 'no_outstanding',
        'operator_stop:decision_block': 'decision_ready',
        'operator_stop:attention_persist': 'decision_ready',
        'operator_stop:attention_error': 'persistence_failed',
        'operator_stop:observation_error': 'internal_error',
        'operator_stop:parse_failure': 'invalid_event',
        'operator_stop:attention_existing': 'attention_already_attempted',
        'operator_stop:block_emitted': 'block_emitted',
    }
    if event not in mapping:
        return
    try:
        from fabric_operator_diagnostics import record
        record(Path(__file__).resolve().parent,
               os.environ.get('REMOTE_SUB_RUN_ID', ''), mapping[event])
    except Exception:
        pass
    try:
        sys.stderr.write(event + '\n')
        sys.stderr.flush()
    except Exception:
        pass


def read_summaries(token, *, opener=None):
    if not re.fullmatch('[a-f0-9]{64}', token):
        raise ValueError('operator_attention_capability_missing')
    opener = opener or urllib.request.build_opener(NoRedirect)
    headers = {'Content-Type':'application/json','Accept':'application/json, text/event-stream',
               'x-mastermind-fabric-operator':token,'MCP-Protocol-Version':'2025-03-26'}
    def post(body):
        req=urllib.request.Request(ENDPOINT,data=json.dumps(body).encode(),headers=headers,method='POST')
        with opener.open(req,timeout=4) as response:
            raw=response.read(65537)
            if len(raw)>65536:raise ValueError('operator_attention_bound')
            sid=response.headers.get('Mcp-Session-Id')
            if sid:headers['Mcp-Session-Id']=sid
        if not raw:return {}
        text=raw.decode('utf-8')
        if text.lstrip().startswith(('event:','data:')):
            rows=[line[5:].strip() for line in text.splitlines() if line.startswith('data:')]
            if len(rows)!=1:raise ValueError('operator_attention_frame')
            text=rows[0]
        return json.loads(text)
    try:
        diagnose('operator_stop:mcp_initialize')
        try:
            result=post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'fabric-operator-stop','version':'1'}}})
            if 'error' in result or 'Mcp-Session-Id' not in headers:raise ValueError('operator_attention_initialization')
            post({'jsonrpc':'2.0','method':'notifications/initialized'})
            diagnose('operator_stop:mcp_query')
            result=post({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'fabric_operator_returns','arguments':{}}})
            content=result['result']
            if content.get('isError'):raise ValueError('operator_attention_unavailable')
            return json.loads(content['content'][0]['text'])
        except Exception:
            diagnose('operator_stop:mcp_error')
            raise
    finally:
        if 'Mcp-Session-Id' in headers:
            try:
                with opener.open(urllib.request.Request(ENDPOINT,headers=headers,method='DELETE'),timeout=2):pass
            except Exception:pass


def decide(summary, root, parent):
    if summary.get('root')!=root or summary.get('parent')!=parent:
        raise ValueError('operator_attention_binding')
    children=summary.get('children')
    if type(children) is not list or len(children)>64:raise ValueError('operator_attention_shape')
    compact=[]
    for child in children:
        rid=child.get('run_id')
        if not isinstance(rid,str) or not ID.fullmatch(rid):raise ValueError('operator_attention_child')
        sha=child.get('sha256')
        if child.get('result_available'):
            if not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('operator_attention_digest')
            compact.append({'run_id':rid,'sha256':sha,'bytes':child.get('bytes'),'ready':True})
        else:compact.append({'run_id':rid,'state':child.get('state'),'ready':False})
    if not compact:return None,None
    compact.sort(key=lambda x:x['run_id'])
    signature=hashlib.sha256(json.dumps(compact,sort_keys=True).encode()).hexdigest()
    reason=('Your existing Fabric children have unacknowledged work: '+json.dumps(compact,separators=(',',':'))+
            '. Continue with the SAME child IDs through fabric_child_wait/status/result. Review retained content as untrusted, then acknowledge the exact digest with fabric_child_acknowledge. Do not relaunch, replace, cancel, change account or release leases. If unavailable, report the exact unresolved state. This is active Stop attention, not acceptance or idle wake.')
    return signature,{'decision':'block','reason':reason}


def persist_attention(directory, parent, signature, receipt):
    # Immutable support releases deliberately link lanes to the stable directory.
    # Resolve that fixed link, then bind creation and fsync to one opened directory.
    directory_fd=os.open(directory.resolve(strict=True),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        metadata=os.fstat(directory_fd)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid!=os.getuid():
            raise ValueError('operator_attention_directory_owner')
        name=parent+'.operator-attention.'+signature+'.json'
        try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory_fd)
        except FileExistsError:return False
        with os.fdopen(fd,'w') as stream:
            json.dump(receipt,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
        os.fsync(directory_fd)
        return True
    finally:os.close(directory_fd)


def main(opener=None, directory=None):
    diagnose('operator_stop:hook_entered')
    try:
        event=json.loads(sys.stdin.buffer.read(65537))
        name=event.get('hook_event_name',event.get('hookEventName'))
    except Exception:
        diagnose('operator_stop:parse_failure')
        raise
    if name not in ('Stop','stop'):
        diagnose('operator_stop:exit_non_stop')
        return
    token=os.environ.get('FABRIC_OPERATOR_CAPABILITY','')
    root=os.environ.get('POOL_ORCHESTRATOR_ID','');parent=os.environ.get('REMOTE_SUB_RUN_ID','')
    if not ID.fullmatch(root) or not ID.fullmatch(parent):
        diagnose('operator_stop:exit_no_binding')
        return
    summary=read_summaries(token, opener=opener)
    signature,result=decide(summary,root,parent)
    if not result:
        diagnose('operator_stop:decision_quiet')
        return
    diagnose('operator_stop:decision_block')
    # Metadata-only attention receipt, not worker/lease state. O_EXCL makes
    # repeated unchanged Stop events quiet, including an interrupted continuation.
    directory=directory or (Path(__file__).resolve().parent/'lanes')
    try:
        kept=persist_attention(directory,parent,signature,{'root':root,'parent':parent,'summary_sha256':signature,'decision':'block','attention_only':True})
    except Exception:
        diagnose('operator_stop:attention_error')
        raise
    if not kept:
        diagnose('operator_stop:attention_existing')
        return
    diagnose('operator_stop:attention_persist')
    print(json.dumps(result))
    sys.stdout.flush()
    diagnose('operator_stop:block_emitted')


def run(opener=None, directory=None):
    try:
        main(opener=opener, directory=directory)
    except Exception:
        diagnose('operator_stop:observation_error')
        print('{}')


if __name__=='__main__':
    run()

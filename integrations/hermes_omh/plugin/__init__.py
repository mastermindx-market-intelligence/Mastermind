"""Hermes-native read-only bridge to an exact installed Mastermind CLI release.

No provider keys, runtime grants, worker dispatcher, retries or memory provider. The
native registry/lease owns registration; the descriptor is operator installation
metadata, never authentication or a model-supplied command/configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

TOOL_NAME='mmx_omh'
TOOLSET='mmx_omh'
RUNTIME_SCHEMA='mastermind.hermes_omh.local_runtime/v1'
MAX_BYTES=131072
CAPACITY_SERVER='mastermind-fabric-capacity'
CAPACITY_TOOL='fabric_route_preview'
# Wire-schema values from the existing read-only Capacity bridge, not routing
# policy. The caller states task requirements; OMH categories are not complexity.
TASK_CLASSES=frozenset(('execute','fix_build','mechanical','review','census','audit',
    'verify','build','high_level','architecture','integration','domain_orchestration','orchestration'))
COMPLEXITIES=frozenset(('C0_MECHANICAL','C1_ROUTINE_BOUNDED','C2_COMPLEX_BOUNDED','C3_FRONTIER_JUDGMENT'))
PREVIEW_FIELDS=frozenset(('pool','model','mode','host','state','reason','reserved',
                         'selection_rechecked_at_request','proof','authority','route_preview'))
SOURCE_FILES=frozenset({
    'integrations/__init__.py','integrations/hermes_omh/__init__.py',
    'integrations/hermes_omh/__main__.py','integrations/hermes_omh/adapter.py',
    'integrations/hermes_omh/json_input.py','integrations/hermes_omh/bridge_cli.py',
    'integrations/hermes_omh/recommendations.py',
    'integrations/hermes_omh/vendor/__init__.py','integrations/hermes_omh/vendor/dag_core.py',
    'control_plane/__init__.py','control_plane/executive_orchestration_result.py','control_plane/flags.py',
    'common/__init__.py','common/product_acceptance_contract.py','common/commission_ref.py','common/redaction.py',
    'scripts/__init__.py','scripts/ohf/__init__.py','scripts/ohf/redaction.py',
})
_BOOT='import runpy,sys; root,home=sys.argv[1:]; sys.path.insert(0,root); sys.argv=["mmx_omh","--omh-home",home]; runpy.run_module("integrations.hermes_omh.bridge_cli",run_name="__main__")'
TOOL_SCHEMA={
    'name':TOOL_NAME,
    'description':'Mastermind read-only OMH bridge. Prepare a graph, obtain OMH advice, or preview the canonical Fabric route for explicit task_class and complexity. OMH candidates never override Fabric models or pools. Never admits, starts, retries or accepts work. Use the existing authorized Executive/Fabric tools for execution.',
    'parameters':{
        'type':'object','additionalProperties':False,'required':['action'],
        'properties':{'action':{'type':'string','enum':['status','plan','recommend','route']},
                      'proposal':{'type':'object','description':'Same closed nodes/policies/root_job_id/plan_attempt_id proposal as the Mastermind OMH CLI; identity strings are not authority.'},
                      'message':{'type':'string','maxLength':4000},
                      'category':{'type':'string','maxLength':128},
                      'task_class':{'type':'string','enum':sorted(TASK_CLASSES)},
                      'complexity':{'type':'string','enum':sorted(COMPLEXITIES)}},
    },
}


class NativeBridgeError(RuntimeError):
    pass


class CapacityPreviewError(NativeBridgeError):
    def __init__(self, reason, owner_reason=None):
        self.reason=reason
        self.owner_reason=owner_reason
        super().__init__(reason)


def _owner_reason(value):
    return value if type(value) is str and re.fullmatch('[A-Z][A-Z0-9_]{1,63}',value) else None


def _capacity_preview(ctx, requirements):
    """One existing native MCP call, with its existing trust and profile gates."""
    try:
        envelope=ctx.call_mcp(CAPACITY_SERVER,CAPACITY_TOOL,dict(requirements),timeout=20)
    except PermissionError:
        raise CapacityPreviewError('NATIVE_CAPACITY_NOT_AUTHORIZED') from None
    except Exception:
        raise CapacityPreviewError('NATIVE_CAPACITY_UNAVAILABLE') from None
    try:
        _bound(envelope)
        if type(envelope) is not dict:raise ValueError('envelope')
        if envelope.get('ok') is False:
            raise CapacityPreviewError('NATIVE_CAPACITY_REFUSED',_owner_reason(envelope.get('error')))
        if envelope.get('ok') is not True or envelope.get('truncated',False) is not False:
            raise ValueError('envelope')
        result=envelope.get('result')
        if type(result) is str:result=json.loads(result,object_pairs_hook=_pairs)
        _bound(result)
        if type(result) is not dict or not set(result)<=PREVIEW_FIELDS:raise ValueError('shape')
        if result.get('state')=='NO_ELIGIBLE_ROUTE':
            raise CapacityPreviewError('NATIVE_CAPACITY_NO_ELIGIBLE_ROUTE',_owner_reason(result.get('reason')))
        if (result.get('state')!='PREVIEW_ONLY' or result.get('reserved') is not False
                or result.get('selection_rechecked_at_request') is not True
                or result.get('proof')!='PREVIEW_ONLY_NO_RESERVATION_OR_DISPATCH'):
            raise ValueError('proof')
        # WO-07 OQ-10 re-point: the shared-law route_preview composition rides
        # along when the bridge serves it. Both fields stay optional so an
        # installed release still serving the owner-only shape keeps passing.
        if 'authority' in result and result.get('authority')!='NONE_SOURCE_PREVIEW_ONLY':
            raise ValueError('authority')
        if 'route_preview' in result:
            record=result.get('route_preview')
            if (type(record) is not dict or record.get('schema')!='RoutePreview.v1'
                    or record.get('authority')!='NONE_SOURCE_PREVIEW_ONLY'
                    or record.get('production_armed') is not False
                    or record.get('capacity_knowledge') not in ('observed','configured_only','unknown')
                    or record.get('rank_basis') not in ('suitability_only','observed_headroom','bounded_unknown')):
                raise ValueError('route_preview')
        for key in ('pool','model'):
            value=result.get(key)
            if type(value) is not str or re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}',value) is None:
                raise ValueError('route')
        for key in ('mode','host','reason'):
            if key in result and (type(result[key]) is not str or len(result[key])>512):
                raise ValueError('metadata')
        return result
    except (ValueError,TypeError,RecursionError,UnicodeError):
        raise CapacityPreviewError('NATIVE_CAPACITY_OUTPUT_INVALID') from None


@dataclass(frozen=True)
class Runtime:
    release_commit:str
    source_root:str
    python_executable:str
    profile_home:str
    omh_home:str
    source_files:tuple[tuple[str,str],...]
    descriptor_path:str
    descriptor_sha256:str


def _pairs(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise ValueError('duplicate key')
        d[k]=v
    return d


def _bound(value):
    stack=[(value,0)];count=0
    while stack:
        v,depth=stack.pop();count+=1
        if depth>12 or count>4096:raise ValueError('bound')
        if type(v) is dict:
            if len(v)>4096 or any(type(k) is not str for k in v):raise ValueError('object')
            if len(stack)+2*len(v)+count>4096:raise ValueError('bound')
            stack.extend((x,depth+1) for p in v.items() for x in p)
        elif type(v) is list:
            if len(stack)+len(v)+count>4096:raise ValueError('bound')
            stack.extend((x,depth+1) for x in v)
        elif type(v) is str:
            if len(v)>8192:raise ValueError('string')
            v.encode('utf-8')
        elif type(v) not in (type(None),bool,int):raise ValueError('plain data')
        elif type(v) is int and v.bit_length()>63:raise ValueError('integer')


def _safe_bytes(path:Path,maximum=MAX_BYTES):
    flags=os.O_RDONLY|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0)
    if not hasattr(os,'O_NOFOLLOW'):raise NativeBridgeError('NATIVE_FILE_CONTRACT_UNAVAILABLE')
    fd=os.open(path,flags|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size>maximum or st.st_uid!=os.getuid() or st.st_mode&0o022:
            raise NativeBridgeError('NATIVE_SOURCE_UNSAFE')
        with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read(maximum+1)
        after=os.fstat(fd)
        if len(raw)>maximum or (st.st_size,st.st_mtime_ns,st.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise NativeBridgeError('NATIVE_SOURCE_CHANGED')
        return raw
    finally:os.close(fd)


def load_runtime():
    path=Path(__file__).with_name('_runtime.json')
    try:
        raw=_safe_bytes(path)
        d=json.loads(raw,object_pairs_hook=_pairs);_bound(d)
        fields={'schema','release_commit','source_root','python_executable','profile_home','omh_home','source_files'}
        if type(d) is not dict or set(d)!=fields or d['schema']!=RUNTIME_SCHEMA:
            raise ValueError('descriptor')
        if type(d['release_commit']) is not str or re.fullmatch('[0-9a-f]{40}',d['release_commit']) is None:
            raise ValueError('revision')
        for k in ('source_root','python_executable','profile_home','omh_home'):
            if type(d[k]) is not str or not Path(d[k]).is_absolute() or '\x00' in d[k]:raise ValueError('path')
        files=d['source_files']
        if type(files) is not dict or set(files)!=SOURCE_FILES:raise ValueError('closure')
        if any(type(v) is not str or re.fullmatch('[0-9a-f]{64}',v) is None for v in files.values()):raise ValueError('digest')
        if not os.access(d['python_executable'],os.X_OK):raise ValueError('interpreter')
        binding=Runtime(d['release_commit'],d['source_root'],d['python_executable'],d['profile_home'],d['omh_home'],
                        tuple(sorted(files.items())),str(path),hashlib.sha256(raw).hexdigest())
        if not verify_sources(binding):raise ValueError('source')
        return binding
    except (OSError,ValueError,TypeError,KeyError,RecursionError):
        raise NativeBridgeError('NATIVE_DESCRIPTOR_INVALID') from None


def verify_sources(binding):
    try:
        if hashlib.sha256(_safe_bytes(Path(binding.descriptor_path))).hexdigest()!=binding.descriptor_sha256:return False
        root=Path(binding.source_root)
        if root.is_symlink():return False
        return all(hashlib.sha256(_safe_bytes(root/p,1048576)).hexdigest()==sha for p,sha in binding.source_files)
    except (OSError,NativeBridgeError):return False


def _refusal(reason, capacity_reason=None):
    result=dict(state='REFUSED',reason=reason,admitted=False,dispatched=False)
    if capacity_reason is not None:result['capacity_reason']=capacity_reason
    return json.dumps(result,sort_keys=True)


def _valid_request(arguments):
    _bound(arguments)
    if type(arguments) is not dict:raise ValueError('request')
    action=arguments.get('action')
    expected={'status':{'action'},'plan':{'action','proposal'},'recommend':{'action','message','category'},
              'route':{'action','message','category','task_class','complexity'}}
    if type(action) is not str or action not in expected or set(arguments)!=expected[action]:raise ValueError('action')
    if action=='route':
        if (type(arguments['task_class']) is not str or arguments['task_class'] not in TASK_CLASSES
                or type(arguments['complexity']) is not str or arguments['complexity'] not in COMPLEXITIES):
            raise ValueError('requirements')
    raw=json.dumps(arguments,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
    if len(raw)>MAX_BYTES:raise ValueError('bound')
    return raw


def register(ctx):
    """Native loader entry. One tool, no hooks/provider/config writer."""
    from tools.registry import registry
    from registration_lifecycle import replacement_coordinator
    binding=load_runtime()
    scope=getattr(getattr(ctx,'_manager',None),'scope_key',None)
    if type(scope) is not str or Path(scope).resolve()!=Path(binding.profile_home).resolve():
        raise NativeBridgeError('NATIVE_PROFILE_MISMATCH')

    def handler(arguments,*,session_id=None,task_id=None):
        try:
            raw=_valid_request(arguments)
            if arguments['action']=='route':
                raw=_valid_request(dict(action='recommend',message=arguments['message'],category=arguments['category']))
        except (ValueError,TypeError,RecursionError,UnicodeEncodeError):return _refusal('NATIVE_REQUEST_INVALID')
        if type(session_id) is not str or not 1<=len(session_id)<=256:return _refusal('NATIVE_SESSION_UNBOUND')
        import hermes_constants
        if Path(hermes_constants.get_hermes_home()).resolve()!=Path(binding.profile_home).resolve():return _refusal('NATIVE_PROFILE_MISMATCH')
        try:entry=registry.snapshot_registration(TOOL_NAME,scope=scope)
        except Exception:return _refusal('NATIVE_REGISTRATION_UNAVAILABLE')
        if entry is None or entry.handler is not handler:return _refusal('NATIVE_REGISTRATION_STALE')
        if not verify_sources(binding):return _refusal('NATIVE_SOURCE_CHANGED')
        try:
            # Deterministic local CLI only. No shell, provider credential, PATH
            # discovery, arbitrary script or automatic retry. The route action
            # subsequently uses only the existing native read-only MCP client.
            result=subprocess.run(
                [binding.python_executable,'-I','-B','-c',_BOOT,binding.source_root,binding.omh_home],
                input=raw,capture_output=True,timeout=20,cwd=binding.source_root,
                env={'PATH':'/usr/bin:/bin','HOME':binding.profile_home,'HERMES_HOME':binding.profile_home,
                     'OMH_HOME':binding.omh_home,'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},
                check=False,
            )
        except subprocess.TimeoutExpired:return _refusal('NATIVE_LOCAL_TIMEOUT')
        except OSError:return _refusal('NATIVE_LOCAL_UNAVAILABLE')
        try:current=registry.snapshot_registration(TOOL_NAME,scope=scope)
        except Exception:return _refusal('NATIVE_REGISTRATION_UNAVAILABLE')
        if current is None or current.handler is not handler:return _refusal('NATIVE_REGISTRATION_STALE')
        if Path(hermes_constants.get_hermes_home()).resolve()!=Path(binding.profile_home).resolve():return _refusal('NATIVE_PROFILE_MISMATCH')
        if result.stderr or len(result.stdout)>MAX_BYTES+1:return _refusal('NATIVE_LOCAL_OUTPUT_INVALID')
        try:
            out=json.loads(result.stdout,object_pairs_hook=_pairs);_bound(out)
            if type(out) is not dict:raise ValueError('result')
            if result.returncode==2 and set(out)=={'state','reason'} and out['state']=='REFUSED':
                # Never forward arbitrary stderr/reason values from a subprocess.
                if type(out['reason']) is str and re.fullmatch('[A-Z][A-Z_]{1,63}',out['reason']):
                    return _refusal(out['reason'])
                raise ValueError('reason')
            states={'status':'LOCAL_BRIDGE_READY','plan':'PREPARED_NOT_ADMITTED','recommend':'RECOMMENDED_NOT_ADMITTED',
                    'route':'RECOMMENDED_NOT_ADMITTED'}
            if (result.returncode!=0 or out.get('state')!=states[arguments['action']]
                    or out.get('admitted') is not False or out.get('dispatched') is not False):raise ValueError('state')
            if not verify_sources(binding):return _refusal('NATIVE_SOURCE_CHANGED')
            out['bridge_release_commit']=binding.release_commit
            if arguments['action']=='status':
                out['actions']=['plan','recommend','route','status']
            if arguments['action']=='route':
                requirements={key:arguments[key] for key in ('task_class','complexity')}
                try:preview=_capacity_preview(ctx,requirements)
                except CapacityPreviewError as exc:return _refusal(exc.reason,exc.owner_reason)
                # The external native call is a second currentness boundary.
                try:current=registry.snapshot_registration(TOOL_NAME,scope=scope)
                except Exception:return _refusal('NATIVE_REGISTRATION_UNAVAILABLE')
                if current is None or current.handler is not handler:return _refusal('NATIVE_REGISTRATION_STALE')
                if Path(hermes_constants.get_hermes_home()).resolve()!=Path(binding.profile_home).resolve():return _refusal('NATIVE_PROFILE_MISMATCH')
                if not verify_sources(binding):return _refusal('NATIVE_SOURCE_CHANGED')
                out=dict(schema='mastermind.hermes_omh.route_preview/v1',
                         state='ROUTE_PREVIEW_NOT_ADMITTED',admitted=False,dispatched=False,
                         selected_model=None,availability='NOT_RESERVED',
                         routing_requirements=requirements,recommendation=out,capacity_preview=preview,
                         execution_owner='Mastermind Executive and Capacity/Fabric',
                         bridge_release_commit=binding.release_commit)
            return json.dumps(out,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
        except (ValueError,TypeError,RecursionError,UnicodeError):return _refusal('NATIVE_LOCAL_OUTPUT_INVALID')

    commands=getattr(ctx._manager,'_plugin_commands',None)
    if type(commands) is not dict or not callable(getattr(ctx,'register_command',None)):
        raise NativeBridgeError('NATIVE_COMMAND_CONTRACT_UNAVAILABLE')

    def command_handler(raw_args,*,session_id=None,session_key=None,source=None,platform=None):
        current=commands.get('mmx-omh')
        if type(current) is not dict or current.get('handler') is not command_handler:
            return _refusal('NATIVE_COMMAND_STALE')
        if type(raw_args) is not str or len(raw_args)>4400:
            return _refusal('NATIVE_REQUEST_INVALID')
        text=raw_args.strip()
        if text in ('','status'):
            request={'action':'status'}
        elif text.split(None,1)[0]=='route':
            parts=text.split(None,4)
            if len(parts)!=5:return _refusal('NATIVE_REQUEST_INVALID')
            request=dict(action='route',task_class=parts[1],complexity=parts[2],category=parts[3],message=parts[4])
        else:
            parts=text.split(None,1)
            if len(parts)!=2:return _refusal('NATIVE_REQUEST_INVALID')
            request={'action':'recommend','category':parts[0],'message':parts[1]}
        # Both IDs are native command-context fields, never parsed from text.
        # They remain correlation, not provider/execution authority.
        native_session=session_id or session_key
        return handler(request,session_id=native_session)

    with replacement_coordinator.transaction():
        if 'mmx-omh' in commands:raise NativeBridgeError('NATIVE_COMMAND_COLLISION')
        if registry.get_entry(TOOL_NAME,scope=scope) is not None:raise NativeBridgeError('NATIVE_TOOL_COLLISION')
        try:
            handle=ctx.register_tool(name=TOOL_NAME,toolset=TOOLSET,schema=TOOL_SCHEMA,handler=handler,description=TOOL_SCHEMA['description'])
        except Exception:
            # The original native loader owns any partially registered leases.
            # No blind retry or deletion of a guessed registration.
            raise NativeBridgeError('NATIVE_REGISTRATION_EFFECT_UNKNOWN') from None
        if handle is None:raise NativeBridgeError('NATIVE_TOOL_NOT_REGISTERED')
        try:
            entry=registry.snapshot_registration(TOOL_NAME,scope=scope)
            if entry is None or entry.handler is not handler or entry.toolset!=TOOLSET or entry.schema!=TOOL_SCHEMA:
                raise NativeBridgeError('NATIVE_TOOL_READBACK_FAILED')
        except Exception:
            try:handle.dispose()
            except Exception:raise NativeBridgeError('NATIVE_TOOL_ROLLBACK_UNKNOWN') from None
            raise NativeBridgeError('NATIVE_TOOL_READBACK_FAILED') from None
        try:
            command_handle=ctx.register_command('mmx-omh',command_handler,
                description='Read-only OMH advice and canonical Fabric route preview; never executes work.',
                args_hint='status | <category> <task> | route <task_class> <complexity> <category> <task>',argument_mode='text')
        except Exception:
            raise NativeBridgeError('NATIVE_REGISTRATION_EFFECT_UNKNOWN') from None
        try:
            registered=commands.get('mmx-omh')
            if command_handle is None or type(registered) is not dict or registered.get('handler') is not command_handler:
                raise NativeBridgeError('NATIVE_COMMAND_READBACK_FAILED')
        except Exception:
            try:
                if command_handle is not None:command_handle.dispose()
                handle.dispose()
            except Exception:raise NativeBridgeError('NATIVE_TOOL_ROLLBACK_UNKNOWN') from None
            raise NativeBridgeError('NATIVE_COMMAND_READBACK_FAILED') from None
        return handle

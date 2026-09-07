"""Proposed descriptor-relative source observation primitive, not an authority.

Only current, already-granted scopes supplied by the existing caller may be used.
This module opens no root by name, issues no grant/reference, writes no file,
spawns no process, and owns no catalogue, index, cache, lease, or history.
The Windows path is deliberately unqualified. An observation is not a lock.
"""
from __future__ import annotations
from dataclasses import dataclass, fields
import hashlib
import json
import os
import re
import stat
from typing import Callable

MAX_FILE_BYTES = 1024 * 1024
MAX_TEXT_BYTES = 32768
MAX_LINES = 512
READ_CHUNK = 65536
_DIRFD_SUPPORTED = os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
_HEX64 = re.compile(r'[0-9a-f]{64}')
_HEX40 = re.compile(r'[0-9a-f]{40}')
_CODES = frozenset({'INVALID_REQUEST','SCOPE_UNAVAILABLE','SCOPE_EXPIRED','SCOPE_CHANGED',
    'ROOT_IDENTITY_CHANGED','PATH_NOT_ALLOWED','PLATFORM_UNQUALIFIED','UNSAFE_DIRECTORY',
    'UNSAFE_FILE_TYPE','FILE_UNAVAILABLE','FILE_IDENTITY_CHANGED','FILE_CHANGED',
    'ANCESTRY_CHANGED','FILE_TOO_LARGE','TEXT_UNREPRESENTABLE','PREIMAGE_MISMATCH',
    'RANGE_OUT_OF_BOUNDS','LINE_TOO_LARGE','CLOCK_UNAVAILABLE'})

@dataclass(frozen=True)
class ReadScope:
    """Internal caller input. A constructed instance is NOT an authenticated grant."""
    root_fd: int
    root_device: int
    root_inode: int
    context_ref: str
    owner_ref: str
    generation: str
    allowed_paths: tuple[str, ...]
    expires_at_ms: int
    committed_head: str | None = None

class ReadRefusal(ValueError):
    def __init__(self, code: str):
        if code not in _CODES:
            raise ValueError('unknown observation refusal')
        self.code=code
        super().__init__(code)

def _refuse(code: str):
    raise ReadRefusal(code)

def _path(value: object) -> tuple[str, ...]:
    if type(value) is not str or not value or value.startswith(('/', '~')) or '\\' in value or ':' in value:
        _refuse('INVALID_REQUEST')
    if any(ord(c)<32 or ord(c)==127 for c in value):
        _refuse('INVALID_REQUEST')
    try:
        if len(value.encode('utf-8'))>512:
            _refuse('INVALID_REQUEST')
        parts=value.split('/')
        if len(parts)>16 or any(p in ('','.','..') or len(p.encode('utf-8'))>255 for p in parts):
            _refuse('INVALID_REQUEST')
    except UnicodeError:
        _refuse('INVALID_REQUEST')
    return tuple(parts)

def _request(value: object) -> dict:
    if type(value) is not dict or set(value)-{'relative_path','start_line','max_lines','max_content_bytes','expected_sha256'}:
        _refuse('INVALID_REQUEST')
    _path(value.get('relative_path'))
    out=dict(value)
    for key,default,lo,hi in [('start_line',0,0,MAX_FILE_BYTES),('max_lines',128,1,MAX_LINES),('max_content_bytes',MAX_TEXT_BYTES,1,MAX_TEXT_BYTES)]:
        v=value.get(key,default)
        if type(v) is not int or not lo<=v<=hi:
            _refuse('INVALID_REQUEST')
        out[key]=v
    if 'expected_sha256' in out and (type(out['expected_sha256']) is not str or _HEX64.fullmatch(out['expected_sha256']) is None):
        _refuse('INVALID_REQUEST')
    return out

def _now(clock: Callable[[],int]) -> int:
    try: value=clock()
    except Exception: _refuse('CLOCK_UNAVAILABLE')
    if type(value) is not int or not 0<=value<2**63:
        _refuse('CLOCK_UNAVAILABLE')
    return value

def _scope(resolver: Callable[[],ReadScope], now: int) -> ReadScope:
    try: s=resolver()
    except Exception: _refuse('SCOPE_UNAVAILABLE')
    if type(s) is not ReadScope:
        _refuse('SCOPE_UNAVAILABLE')
    if any(type(getattr(s,n)) is not int or getattr(s,n)<0 for n in ('root_fd','root_device','root_inode','expires_at_ms')):
        _refuse('SCOPE_UNAVAILABLE')
    for n in ('context_ref','owner_ref','generation'):
        v=getattr(s,n)
        if type(v) is not str or not 0<len(v)<=256 or any(ord(c)<32 or ord(c)==127 for c in v):
            _refuse('SCOPE_UNAVAILABLE')
        try:v.encode('utf-8')
        except UnicodeError:_refuse('SCOPE_UNAVAILABLE')
    if type(s.allowed_paths) is not tuple or not 0<len(s.allowed_paths)<=64:
        _refuse('SCOPE_UNAVAILABLE')
    try:
        for p in s.allowed_paths:_path(p)
    except ReadRefusal:_refuse('SCOPE_UNAVAILABLE')
    if len(set(s.allowed_paths))!=len(s.allowed_paths):_refuse('SCOPE_UNAVAILABLE')
    if s.committed_head is not None and (type(s.committed_head) is not str or _HEX40.fullmatch(s.committed_head) is None):
        _refuse('SCOPE_UNAVAILABLE')
    if s.expires_at_ms<=now:_refuse('SCOPE_EXPIRED')
    return s

def _scope_key(s:ReadScope) -> tuple:
    return tuple(getattr(s,f.name) for f in fields(s) if f.name!='root_fd')

def _dir_identity(s:os.stat_result) -> tuple:
    return s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid

def _file_identity(s:os.stat_result) -> tuple:
    return s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns

def _digest(value:object) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()

def observe_file(arguments:dict, resolve_scope:Callable[[],ReadScope], *, clock_ms:Callable[[],int],
                 _before_file_open=None,_between_chunks=None,_before_final=None) -> dict:
    """Read one allowed file; return only after source and scope fences pass.

    Private hooks are deterministic test seams, not model-visible inputs.
    The callback must perform real current auth/permission checks externally.
    Returning `ReadScope` alone does not prove its provenance or revocation.
    """
    req=_request(arguments)
    s=_scope(resolve_scope,_now(clock_ms))
    if req['relative_path'] not in s.allowed_paths:_refuse('PATH_NOT_ALLOWED')
    flags=[getattr(os,n,0) for n in ('O_NOFOLLOW','O_DIRECTORY','O_NONBLOCK','O_CLOEXEC')]
    if not _DIRFD_SUPPORTED or not all(flags):_refuse('PLATFORM_UNQUALIFIED')
    nofollow,directory,nonblock,cloexec=flags
    fds=[]; ancestry=[]
    try:
        root=os.dup(s.root_fd);fds.append(root)
        rs=os.fstat(root)
        if not stat.S_ISDIR(rs.st_mode) or (rs.st_dev,rs.st_ino)!=(s.root_device,s.root_inode):
            _refuse('ROOT_IDENTITY_CHANGED')
        root_ident=_dir_identity(rs);parent=root
        parts=_path(req['relative_path'])
        for atom in parts[:-1]:
            before=os.stat(atom,dir_fd=parent,follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or before.st_dev!=s.root_device:_refuse('UNSAFE_DIRECTORY')
            child=os.open(atom,os.O_RDONLY|nofollow|directory|cloexec,dir_fd=parent);fds.append(child)
            opened=os.fstat(child)
            if _dir_identity(before)!=_dir_identity(opened):_refuse('ANCESTRY_CHANGED')
            ancestry.append((parent,atom,child,_dir_identity(opened)))
            parent=child
        leaf=parts[-1]
        pre=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
        if not stat.S_ISREG(pre.st_mode) or pre.st_nlink!=1 or pre.st_dev!=s.root_device:_refuse('UNSAFE_FILE_TYPE')
        if pre.st_size>MAX_FILE_BYTES:_refuse('FILE_TOO_LARGE')
        if _before_file_open is not None:_before_file_open()
        fd=os.open(leaf,os.O_RDONLY|nofollow|nonblock|cloexec,dir_fd=parent);fds.append(fd)
        opened=os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink!=1:_refuse('UNSAFE_FILE_TYPE')
        if _file_identity(opened)!=_file_identity(pre):_refuse('FILE_IDENTITY_CHANGED')
        chunks=[];count=0
        while True:
            chunk=os.read(fd,min(READ_CHUNK,pre.st_size-count+1))
            if not chunk:break
            count+=len(chunk)
            if count>pre.st_size:_refuse('FILE_CHANGED')
            chunks.append(chunk)
            if _between_chunks is not None:_between_chunks(count)
        if count!=pre.st_size:_refuse('FILE_CHANGED')
        raw=b''.join(chunks)
        sha=hashlib.sha256(raw).hexdigest()
        if 'expected_sha256' in req and req['expected_sha256']!=sha:_refuse('PREIMAGE_MISMATCH')
        try:
            text=raw.decode('utf-8')
            if '\0' in text:_refuse('TEXT_UNREPRESENTABLE')
        except UnicodeError:_refuse('TEXT_UNREPRESENTABLE')
        # Count and seek without allocating one object per line. A file with a
        # million short lines must stay within the full-file byte budget.
        total_lines=raw.count(b'\n')+(1 if raw and not raw.endswith(b'\n') else 0)
        start=req['start_line']
        if start>total_lines:_refuse('RANGE_OUT_OF_BOUNDS')
        pos=0
        for _ in range(start):
            found=raw.find(b'\n',pos)
            pos=found+1 if found>=0 else len(raw)
        selected=[];used=0;end=start
        for _ in range(min(req['max_lines'],total_lines-start)):
            found=raw.find(b'\n',pos)
            stop=found+1 if found>=0 else len(raw)
            width=stop-pos
            if used+width>req['max_content_bytes']:
                if not selected:_refuse('LINE_TOO_LARGE')
                break
            selected.append(raw[pos:stop]);used+=width;end+=1;pos=stop
        content=b''.join(selected).decode('utf-8')
        if _before_final is not None:_before_final()
        observed_at=_now(clock_ms)
        final_scope=_scope(resolve_scope,observed_at)
        if _scope_key(s)!=_scope_key(final_scope):_refuse('SCOPE_CHANGED')
        if _dir_identity(os.fstat(root))!=root_ident or _dir_identity(os.fstat(final_scope.root_fd))!=root_ident:
            _refuse('ROOT_IDENTITY_CHANGED')
        for par,atom,child,identity in ancestry:
            if _dir_identity(os.fstat(child))!=identity or _dir_identity(os.stat(atom,dir_fd=par,follow_symlinks=False))!=identity:
                _refuse('ANCESTRY_CHANGED')
        final=os.fstat(fd)
        if _file_identity(final)!=_file_identity(pre) or _file_identity(os.stat(leaf,dir_fd=parent,follow_symlinks=False))!=_file_identity(pre):
            _refuse('FILE_CHANGED')
        identity_digest=_digest(_file_identity(pre))
        result={'status':'OK','relative_path':req['relative_path'],'context_ref':s.context_ref,
            'owner_ref':s.owner_ref,'generation':s.generation,'view_kind':'WORKING_TREE',
            'committed_head':s.committed_head,'file_sha256':sha,'file_identity_digest':identity_digest,
            'file_bytes':len(raw),'content':content,'content_bytes':used,'total_lines':total_lines,
            'line_start':start,'line_end':end,'truncated':end<total_lines,'next_line':end if end<total_lines else None,
            'observed_at_ms':observed_at,'index_status':'NOT_OBSERVED','atomic_workspace_snapshot':False}
        result['observation_digest']=_digest({k:v for k,v in result.items() if k!='content'})
        return result
    except ReadRefusal:raise
    except (OSError,TypeError,ValueError,OverflowError):_refuse('FILE_UNAVAILABLE')
    finally:
        for fd in reversed(fds):
            try:os.close(fd)
            except OSError:pass

"""Pure event-only dependency metadata; parsed bytes grant no installed authority."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import PurePosixPath

SCHEMA = 'mastermind.executive_control_aead_closure.v1'
VERSIONS = {'cffi':'2.1.1','cryptography':'50.0.1','pycparser':'3.0'}
SHA = re.compile(r'[0-9a-f]{64}')
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 8192

class AeadContractError(ValueError):
    pass

def _fail():
    raise AeadContractError('control AEAD contract unavailable')

def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()

def parse_lock(data):
    if type(data) is not bytes or len(data)>32768: _fail()
    try: text=data.decode('utf-8')
    except UnicodeError: _fail()
    result={};current=None
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        line=line.removesuffix('\\').strip()
        package=re.fullmatch(r'([a-z]+)==([0-9.]+)',line)
        if package:
            name,version=package.groups()
            if name in result or VERSIONS.get(name)!=version: _fail()
            result[name]={'version':version,'hashes':[]};current=name
        else:
            digest=re.fullmatch(r'--hash=sha256:([0-9a-f]{64})',line)
            if digest is None or current is None: _fail()
            value=digest.group(1)
            if value in result[current]['hashes']: _fail()
            result[current]['hashes'].append(value)
    if set(result)!=set(VERSIONS) or any(not p['hashes'] for p in result.values()): _fail()
    return {n:{'version':p['version'],'hashes':tuple(p['hashes'])} for n,p in result.items()}

def allowed_profile_path(value):
    if type(value) is not str or not value or len(value)>512 or '\\' in value or any(ord(c)<32 or ord(c)==127 for c in value): return False
    path=PurePosixPath(value)
    if path.is_absolute() or value!=path.as_posix() or any(c in ('','.', '..') for c in value.split('/')): return False
    if any(c=='__pycache__' or c in ('sitecustomize.py','usercustomize.py') or c.endswith(('.pth','.pyc','.pyo')) for c in path.parts): return False
    roots=set(VERSIONS)|{f'{n}-{v}.dist-info' for n,v in VERSIONS.items()}
    if len(path.parts)>=2 and path.parts[0] in roots: return True
    return len(path.parts)==1 and re.fullmatch(r'_cffi_backend(?:\.[A-Za-z0-9_-]+)*\.so',value) is not None

def manifest_bytes(lock_sha256,entries):
    if type(lock_sha256) is not str or SHA.fullmatch(lock_sha256) is None or type(entries) is not list or not 1<=len(entries)<=MAX_FILES: _fail()
    paths=[]
    for e in entries:
        if (type(e) is not dict or set(e)!={'path','bytes','sha256','mode'} or not allowed_profile_path(e['path'])
                or type(e['bytes']) is not int or not 0<=e['bytes']<=MAX_BYTES
                or type(e['mode']) is not int or e['mode'] not in (0o444,0o555)
                or type(e['sha256']) is not str or SHA.fullmatch(e['sha256']) is None): _fail()
        paths.append(e['path'])
    if paths!=sorted(paths) or len(set(paths))!=len(paths) or sum(e['bytes'] for e in entries)>2*MAX_BYTES: _fail()
    return canonical({'schema':SCHEMA,'lock_sha256':lock_sha256,'files':entries})

def parse_manifest(data,expected_lock_sha256):
    if type(data) is not bytes or not data or len(data)>32*1024*1024: _fail()
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj: _fail()
            obj[key]=value
        return obj
    try:
        obj=json.loads(data,object_pairs_hook=unique)
        if (type(obj) is not dict or set(obj)!={'schema','lock_sha256','files'} or obj['schema']!=SCHEMA
                or obj['lock_sha256']!=expected_lock_sha256
                or manifest_bytes(obj['lock_sha256'],obj['files'])!=data): _fail()
        return obj
    except (UnicodeError,TypeError,KeyError,json.JSONDecodeError): _fail()

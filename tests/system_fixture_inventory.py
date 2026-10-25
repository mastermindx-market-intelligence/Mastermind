"""Bounded CI-only public structural DATA; never a platform qualification."""
import json
import os
import posixpath
import re
import stat
import time

SCHEMA='mastermind.inert_public_stdlib_inventory.v1'
MAX_NODES=20000
MAX_RECORDS=64
MAX_BYTES=16384
ROOT='/usr/lib/python3.12'
KINDS=('REGULAR','DIRECTORY','SYMLINK','FIFO','SOCKET','CHARACTER','BLOCK','UNKNOWN')
REASONS=('SYMLINK','FOREIGN_OWNER','WRITABLE','UNSUPPORTED_TYPE','METADATA_REFUSED')
INCOMPLETE=('ROOT_REFUSED','METADATA_UNAVAILABLE','NAMESPACE_CHANGED','UNQUALIFIED_DIRECTORY',
    'NODE_LIMIT','DEPTH_LIMIT','TIME_LIMIT','RECORD_LIMIT','OUTPUT_LIMIT','UNREPRESENTABLE_NAME')


def relative_name(value):
    return (type(value)is str and 0<len(value)<=240 and len(value.split('/'))<=8
        and all(part not in ('.','..')and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.+-]{0,95}',part)is not None for part in value.split('/')))


def kind(info):
    return next((name for check,name in ((stat.S_ISREG,'REGULAR'),(stat.S_ISDIR,'DIRECTORY'),
        (stat.S_ISLNK,'SYMLINK'),(stat.S_ISFIFO,'FIFO'),(stat.S_ISSOCK,'SOCKET'),
        (stat.S_ISCHR,'CHARACTER'),(stat.S_ISBLK,'BLOCK'))if check(info.st_mode)),'UNKNOWN')


def target_metadata(node,raw):
    if not relative_name(node)or type(raw)is not str or not 0<len(raw)<=4096 or any(ord(c)<32 or ord(c)>126 or c=='\\'for c in raw):
        return dict(state='UNKNOWN',form=None,relative_name=None)
    form='ABSOLUTE'if raw.startswith('/')else'RELATIVE'
    resolved=posixpath.normpath(raw if raw.startswith('/')else posixpath.join(ROOT,posixpath.dirname(node),raw))
    if not resolved.startswith('/usr/lib/'):return dict(state='OUTSIDE',form=form,relative_name=None)
    name=resolved[len('/usr/lib/'):]
    if not relative_name(name):return dict(state='UNKNOWN',form=form,relative_name=None)
    return dict(state='WITHIN_USR_LIB',form=form,relative_name=name)


def identity(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def collect():
    value=dict(schema=SCHEMA,scope='FIXED_STDLIB_EXCLUDING_SITE_ROOTS',complete=True,overflow=False,nodes_seen=0,reasons=[],records=[])
    opened=[];root_bindings=[];started=time.monotonic()
    def incomplete(reason):
        value['complete']=False
        if reason not in value['reasons']:value['reasons'].append(reason)
    def record(name,node_kind,reasons,target=None):
        if len(value['records'])>=MAX_RECORDS:
            value['overflow']=True;incomplete('RECORD_LIMIT');return
        value['records'].append(dict(relative_name=name,kind=node_kind,reasons=reasons,target=target))
    def walk(fd,parent_name,depth):
        if depth>8:incomplete('DEPTH_LIMIT');return
        before=identity(os.fstat(fd))
        try:
            with os.scandir(fd)as entries:
                for entry in entries:
                    if time.monotonic()-started>5:incomplete('TIME_LIMIT');return
                    if value['nodes_seen']>=MAX_NODES:incomplete('NODE_LIMIT');return
                    name=parent_name+'/'+entry.name if parent_name else entry.name
                    if not relative_name(name):incomplete('UNREPRESENTABLE_NAME');continue
                    value['nodes_seen']+=1
                    try:info=entry.stat(follow_symlinks=False)
                    except OSError:
                        record(name,'UNKNOWN',['METADATA_REFUSED']);incomplete('METADATA_UNAVAILABLE');continue
                    node_kind=kind(info)
                    if node_kind=='DIRECTORY'and entry.name in ('site-packages','dist-packages'):continue
                    reasons=[];target=None
                    if node_kind=='SYMLINK':
                        reasons.append('SYMLINK')
                        try:
                            target=target_metadata(name,os.readlink(entry.name,dir_fd=fd))
                            if identity(os.stat(entry.name,dir_fd=fd,follow_symlinks=False))!=identity(info):incomplete('NAMESPACE_CHANGED')
                        except OSError:
                            target=dict(state='UNKNOWN',form=None,relative_name=None);incomplete('METADATA_UNAVAILABLE')
                    elif node_kind not in ('DIRECTORY','REGULAR'):reasons.append('UNSUPPORTED_TYPE')
                    if info.st_uid!=0:reasons.append('FOREIGN_OWNER')
                    if node_kind!='SYMLINK'and info.st_mode&0o022:reasons.append('WRITABLE')
                    if reasons:record(name,node_kind,reasons,target)
                    if node_kind=='DIRECTORY':
                        if info.st_uid!=0 or info.st_mode&0o022:incomplete('UNQUALIFIED_DIRECTORY');continue
                        child=None
                        try:
                            child=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                            if identity(os.fstat(child))!=identity(info):incomplete('NAMESPACE_CHANGED');continue
                            walk(child,name,depth+1)
                            if identity(os.fstat(child))!=identity(info)or identity(os.stat(entry.name,dir_fd=fd,follow_symlinks=False))!=identity(info):incomplete('NAMESPACE_CHANGED')
                        except OSError:incomplete('METADATA_UNAVAILABLE')
                        finally:
                            if child is not None:os.close(child)
        except OSError:incomplete('METADATA_UNAVAILABLE')
        if identity(os.fstat(fd))!=before:incomplete('NAMESPACE_CHANGED')
    try:
        parent=None
        for name in ('/','usr','lib','python3.12'):
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,**({}if parent is None else{'dir_fd':parent}))
            opened.append(fd);info=os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode)or info.st_uid!=0 or info.st_mode&0o022:
                incomplete('ROOT_REFUSED');return value
            root_bindings.append((fd,parent,name,identity(info)));parent=fd
        walk(parent,'',0)
        for fd,parent,name,before in root_bindings:
            if identity(os.fstat(fd))!=before or(parent is not None and identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=before):incomplete('NAMESPACE_CHANGED')
    except OSError:incomplete('ROOT_REFUSED')
    finally:
        for fd in reversed(opened):
            try:os.close(fd)
            except OSError:incomplete('METADATA_UNAVAILABLE')
    value['records'].sort(key=lambda row:row['relative_name'])
    return value


def safe(value):
    if(type(value)is not dict or set(value)!={'schema','scope','complete','overflow','nodes_seen','reasons','records'}
        or type(value['schema'])is not str or value['schema']!=SCHEMA or type(value['scope'])is not str or value['scope']!='FIXED_STDLIB_EXCLUDING_SITE_ROOTS'
        or type(value['complete'])is not bool or type(value['overflow'])is not bool
        or type(value['nodes_seen'])is not int or not 0<=value['nodes_seen']<=MAX_NODES
        or type(value['reasons'])is not list or len(value['reasons'])>len(INCOMPLETE)
        or any(type(x)is not str or x not in INCOMPLETE for x in value['reasons'])
        or type(value['records'])is not list or len(value['records'])>MAX_RECORDS):return False
    if value['complete']!=(not value['overflow']and not value['reasons'])or len(value['records'])>value['nodes_seen']:return False
    for row in value['records']:
        if(type(row)is not dict or set(row)!={'relative_name','kind','reasons','target'}
            or not relative_name(row['relative_name'])or type(row['kind'])is not str or row['kind']not in KINDS
            or type(row['reasons'])is not list or not 0<len(row['reasons'])<=3
            or any(type(x)is not str or x not in REASONS for x in row['reasons'])):return False
        target=row['target']
        if target is not None:
            if(type(target)is not dict or set(target)!={'state','form','relative_name'}or row['kind']!='SYMLINK'
                or type(target['state'])is not str or target['state']not in ('UNKNOWN','OUTSIDE','WITHIN_USR_LIB')
                or (target['form']is not None and type(target['form'])is not str)or target['form']not in (None,'ABSOLUTE','RELATIVE')):return False
            if target['state']=='WITHIN_USR_LIB':
                if target['form']is None or not relative_name(target['relative_name']):return False
            elif target['relative_name']is not None:return False
    return True


def encode(value):
    if not safe(value):return None
    # Detached bounded DATA; output truncation never pretends completeness.
    value=json.loads(json.dumps(value,ensure_ascii=True,allow_nan=False))
    while True:
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
        if len(raw.encode())<=MAX_BYTES:return raw
        if not value['records']:return None
        value['records'].pop();value['complete']=False;value['overflow']=True
        if 'OUTPUT_LIMIT'not in value['reasons']:value['reasons'].append('OUTPUT_LIMIT')


def unavailable():
    return dict(schema=SCHEMA,scope='FIXED_STDLIB_EXCLUDING_SITE_ROOTS',complete=False,overflow=False,nodes_seen=0,reasons=['METADATA_UNAVAILABLE'],records=[])

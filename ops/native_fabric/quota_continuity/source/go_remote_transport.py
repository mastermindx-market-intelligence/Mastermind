#!/usr/bin/env python3
"""One run's scoped Go tunnel. Admission and worker settlement remain remote_sub's."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import stat
import subprocess
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from lane_runtime import _terminate_verified_group, cleanup_receipt_is_proven

IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
CAPABILITY = re.compile(r'v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')
SCOPE = ('root','lease_id','account','run_id','host','model')
SOURCES = {'go_shim.py','go_lease_capability.py','go_lease_gateway.py'}
FIELDS = set(SCOPE) | {'schema','ssh_alias','child_timeout','ttl','remote_port','remote_support','controller_token_path','source_sha256'}

class Refused(ValueError): pass

def require(value):
    if not value: raise Refused('transport refused')

def pairs(items):
    value = {}
    for k,v in items:
        require(k not in value);value[k] = v
    return value

def constant(_): raise Refused('transport refused')
def parse(raw):
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    require(isinstance(value,dict));return value

def private_read(path,limit):
    require(Path(path).is_absolute())
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and stat.S_IMODE(a.st_mode)==0o600 and 0<a.st_size<=limit)
        chunks=[];size=0
        while size<limit+1:
            b=os.read(fd,limit+1-size)
            if not b:break
            chunks.append(b);size+=len(b)
        z=os.fstat(fd)
        require(size==a.st_size and (a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_size,z.st_mtime_ns,z.st_ctime_ns))
        return b''.join(chunks)
    finally:os.close(fd)

def load_spec(path):
    x=parse(private_read(path,16384))
    require(set(x)==FIELDS and x['schema']=='mastermind.go.transport.v1')
    for k in (*SCOPE,'ssh_alias'):require(isinstance(x[k],str) and IDENT.fullmatch(x[k]))
    for k in ('remote_support','controller_token_path'):
        require(isinstance(x[k],str) and Path(x[k]).is_absolute() and '\x00' not in x[k] and '\n' not in x[k])
    for k in ('child_timeout','ttl','remote_port'):require(type(x[k]) is int)
    require(1<=x['child_timeout']<=240 and x['child_timeout']+30<=x['ttl']<=300 and 1024<=x['remote_port']<=65535)
    require(isinstance(x['source_sha256'],dict) and set(x['source_sha256'])==SOURCES)
    require(all(isinstance(v,str) and re.fullmatch(r'[0-9a-f]{64}',v) for v in x['source_sha256'].values()))
    return x

def private_write(path,value):
    require(Path(path).is_absolute())
    data=(json.dumps(value,separators=(',',':'))+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        os.fchmod(fd,0o600);remaining=memoryview(data)
        while remaining:
            n=os.write(fd,remaining);require(n>0);remaining=remaining[n:]
        os.fsync(fd);s=os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode)==0o600 and s.st_uid==os.getuid() and s.st_size==len(data))
    finally:os.close(fd)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise Refused('transport refused')

def request_json(url,*,body=None,bearer=None):
    headers={'Accept':'application/json'}
    if bearer is not None:headers['Authorization']='Bearer '+bearer
    data=None
    if body is not None:data=json.dumps(body).encode();headers['Content-Type']='application/json'
    opener=build_opener(ProxyHandler({}),NoRedirect())
    with opener.open(Request(url,data=data,headers=headers),timeout=3) as r:
        require(r.status==200);raw=r.read(16385);require(len(raw)<=16384)
    return parse(raw)

def mint(spec,controller='http://127.0.0.1:4142',request=request_json):
    # Alternate loopback port is an in-process synthetic-test seam, not a CLI option.
    require(re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}',controller))
    health=request(controller+'/health')
    require(health.get('worker_capabilities')=='lease-v1' and health.get('source_sha256')==spec['source_sha256'])
    token=private_read(spec['controller_token_path'],4096).decode('ascii').strip()
    require(token and all(33<=ord(c)<=126 for c in token))
    value=request(controller+'/worker-capabilities',body={k:spec[k] for k in ('lease_id','root','model','run_id','host','ttl')},bearer=token)
    require(set(value)==set(SCOPE)|{'token','expires_at'})
    require(all(value[k]==spec[k] for k in SCOPE))
    require(isinstance(value['token'],str) and len(value['token'])<=4096 and CAPABILITY.fullmatch(value['token']) and value['token']!=token)
    require(type(value['expires_at']) in (int,float) and math.isfinite(value['expires_at']))
    remaining=value['expires_at']-time.time()
    require(spec['child_timeout']+5<remaining<=spec['ttl']+1)
    return {'schema':'mastermind.go.worker-launch.v1',**value,'endpoint':'http://127.0.0.1:'+str(spec['remote_port']),'source_sha256':spec['source_sha256']}

# Fixed receiver code. Only nonsecret admission metadata appears in its argv.
RECEIVER = r'''
import json,os,select,stat,subprocess,sys,time
from pathlib import Path
meta=json.loads(sys.argv[1]);scope={k:meta[k] for k in ('root','lease_id','account','run_id','host','model')}
sys.path.insert(0,meta['remote_support'])
from go_remote_capsule import load_capsule
from go_remote_codex import probe
parent=directory=None;created=False;capsule_inode=None;directory_inode=None;ready=False;success=False
name='go-'+meta['run_id'];path=None;phase='capsule_read'

def emit(kind,**fields):
    x={'schema':'mastermind.go.remote-'+kind.lower()+'.v1','status':kind,'run_id':meta['run_id'],'host':meta['host'],'lease_id':meta['lease_id'],'receiver_pid':os.getpid(),**fields}
    print(kind+' '+json.dumps(x,separators=(',',':')),flush=True)

def loopback_listener():
    port=str(meta['remote_port'])
    if sys.platform=='darwin':
        p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:'+port,'-sTCP:LISTEN','-Fn'],capture_output=True,text=True,timeout=3,check=True)
        addresses=[line[1:] for line in p.stdout.splitlines() if line.startswith('n')]
        return addresses and all(a=='127.0.0.1:'+port for a in addresses)
    p=subprocess.run(['ss','-H','-ltn','sport = :'+port],capture_output=True,text=True,timeout=3,check=True)
    addresses=[line.split()[3] for line in p.stdout.splitlines() if len(line.split())>=5]
    return addresses and all(a=='127.0.0.1:'+port for a in addresses)

try:
    raw=b'';deadline=time.monotonic()+12
    while not raw.endswith(b'\n'):
        if len(raw)>=8192 or time.monotonic()>=deadline:raise ValueError()
        if not select.select([sys.stdin],[],[],.2)[0]:continue
        b=os.read(sys.stdin.fileno(),1)
        if not b:raise ValueError()
        raw+=b
    # Anchor deletion to an opened directory and the exact created inode.
    phase='private_parent'
    tmp=(Path.home()/'lanes/tmp').resolve(strict=True)
    parent=os.open(tmp,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    ps=os.fstat(parent)
    if ps.st_uid!=os.getuid() or ps.st_mode&0o022:raise ValueError()
    phase='private_directory'
    os.mkdir(name,0o700,dir_fd=parent);created=True
    directory=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    ds=os.fstat(directory);directory_inode=(ds.st_dev,ds.st_ino)
    if ds.st_uid!=os.getuid() or stat.S_IMODE(ds.st_mode)!=0o700:raise ValueError()
    phase='private_file'
    fd=os.open('capability.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    try:
        os.fchmod(fd,0o600);owned=os.fstat(fd);capsule_inode=(owned.st_dev,owned.st_ino);view=memoryview(raw)
        while view:
            n=os.write(fd,view)
            if n<=0:raise ValueError()
            view=view[n:]
        os.fsync(fd);fs=os.fstat(fd);capsule_inode=(fs.st_dev,fs.st_ino)
    finally:os.close(fd)
    path=str(tmp/name/'capability.json')
    phase='validate_capsule'
    value=load_capsule(path,expected=scope,now=time.time())
    if value['source_sha256']!=meta['source_sha256'] or value['endpoint']!='http://127.0.0.1:'+str(meta['remote_port']):raise ValueError()
    phase='listener_census'
    if not loopback_listener():raise ValueError()
    phase='health_probe'
    probe(value,meta['child_timeout'])
    emit('READY',capsule_file=path);ready=True;phase='wait_close'
    limit=time.monotonic()+meta['ttl'];command=b''
    while time.monotonic()<limit:
        if not select.select([sys.stdin],[],[],min(.2,max(0,limit-time.monotonic())))[0]:continue
        b=os.read(sys.stdin.fileno(),16)
        if not b:break
        command+=b
        if command==b'CLOSE\n':success=True;phase=None;break
        if len(command)>6 or not b'CLOSE\n'.startswith(command):raise ValueError()
except BaseException:
    pass
finally:
    removed=not created;dir_removed=not created
    try:
        if created and directory is not None:
            try:
                current=os.stat('capability.json',dir_fd=directory,follow_symlinks=False)
                if capsule_inode is None or (current.st_dev,current.st_ino)!=capsule_inode:raise ValueError()
                os.unlink('capability.json',dir_fd=directory)
            except FileNotFoundError:pass
            removed=True
        if created:
            current=os.stat(name,dir_fd=parent,follow_symlinks=False)
            if directory_inode is None or (current.st_dev,current.st_ino)!=directory_inode:raise ValueError()
            os.rmdir(name,dir_fd=parent);dir_removed=True
    except BaseException:pass
    for fd in (directory,parent):
        if fd is not None:os.close(fd)
    emit('CLOSED',capsule_removed=removed,directory_removed=dir_removed,error_phase=phase)
    sys.exit(0 if ready and success and removed and dir_removed else 78)
'''

def ssh_options():
    pairs_=(('BatchMode','yes'),('ConnectTimeout','8'),('ControlMaster','no'),('ControlPath','none'),('ControlPersist','no'),('ExitOnForwardFailure','yes'),('ServerAliveInterval','10'),('ServerAliveCountMax','1'),('ForwardAgent','no'),('ForwardX11','no'),('PermitLocalCommand','no'))
    return [part for key,value in pairs_ for part in ('-o',key+'='+value)]

def ssh_command(spec,controller='http://127.0.0.1:4142'):
    meta={k:spec[k] for k in (*SCOPE,'remote_support','remote_port','child_timeout','ttl','source_sha256')}
    command='python3 -u -c '+shlex.quote(RECEIVER)+' '+shlex.quote(json.dumps(meta,separators=(',',':')))
    local_port=controller.rsplit(':',1)[1]
    return ['ssh',*ssh_options(),'-T','-R','127.0.0.1:'+str(spec['remote_port'])+':127.0.0.1:'+local_port,spec['ssh_alias'],command]

def check_ssh_config(spec):
    r=subprocess.run(['ssh',*ssh_options(),'-G',spec['ssh_alias']],capture_output=True,text=True,timeout=3,check=True)
    # Refuse inherited forwards rather than accidentally create extra listeners.
    require(not any(line.split(' ',1)[0] in {'localforward','remoteforward','dynamicforward','remotecommand'} and line.split(' ',1)[-1] not in {'none',''} for line in r.stdout.splitlines()))

class Events:
    def __init__(self,proc):
        self.proc=proc;self.selector=selectors.DefaultSelector();self.pending=b'';self.total=0;self.events=[]
        for f in (proc.stdout,proc.stderr):os.set_blocking(f.fileno(),False);self.selector.register(f,selectors.EVENT_READ)
        os.set_blocking(proc.stdin.fileno(),False)
    def write(self,data,seconds=3):
        stop=time.monotonic()+seconds
        while data:
            require(self.proc.poll() is None and time.monotonic()<stop)
            try:n=os.write(self.proc.stdin.fileno(),data);require(n>0);data=data[n:]
            except BlockingIOError:self.pump(.02)
    def pump(self,seconds=.1):
        for key,_ in self.selector.select(seconds):
            raw=os.read(key.fileobj.fileno(),8192)
            if not raw:self.selector.unregister(key.fileobj);continue
            self.total+=len(raw);require(self.total<=32768)
            if key.fileobj is self.proc.stderr:continue # Never persist untrusted stderr.
            self.pending+=raw;require(len(self.pending)<=8192)
            while b'\n' in self.pending:
                line,self.pending=self.pending.split(b'\n',1)
                prefix,sep,body=line.partition(b' ');require(sep and prefix in (b'READY',b'CLOSED'))
                self.events.append((prefix.decode(),parse(body)));require(len(self.events)<=2)
    def close(self):self.selector.close()

def verify_event(kind,event,spec,receiver_pid=None):
    extra={'capsule_file'} if kind=='READY' else {'capsule_removed','directory_removed','error_phase'}
    require(set(event)=={'schema','status','run_id','host','lease_id','receiver_pid'}|extra)
    require(event['schema']=='mastermind.go.remote-'+kind.lower()+'.v1' and event['status']==kind)
    require(all(event[k]==spec[k] for k in ('run_id','host','lease_id')))
    require(type(event['receiver_pid']) is int and event['receiver_pid']>1)
    if receiver_pid is not None:require(event['receiver_pid']==receiver_pid)
    if kind=='READY':
        path=event['capsule_file'];require(isinstance(path,str) and Path(path).is_absolute() and path.endswith('/go-'+spec['run_id']+'/capability.json'))
    else:
        require(event['capsule_removed'] is True and event['directory_removed'] is True)
        require(event['error_phase'] in {None,'capsule_read','private_parent','private_directory','private_file','validate_capsule','listener_census','health_probe','wait_close'})


def serve(spec_path,ready_path,receipt_path,*,controller='http://127.0.0.1:4142',ssh_factory=None,config_check=check_ssh_config,request=request_json):
    spec=load_spec(spec_path)
    for p in (ready_path,receipt_path):require(Path(p).is_absolute() and not os.path.lexists(p))
    require(ready_path!=receipt_path)
    stopped=[False];parent=os.getppid();saved={}
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        saved[sig]=signal.signal(sig,lambda *_:stopped.__setitem__(0,True))
    proc=events=None;ready=None;closed=None;failure=None;local=None;normal_close=False
    started=time.monotonic()
    try:
        config_check(spec);capsule=mint(spec,controller,request)
        env={k:os.environ[k] for k in ('HOME','PATH','USER','LOGNAME','LANG','LC_ALL','SSH_AUTH_SOCK') if k in os.environ}
        factory=ssh_factory or subprocess.Popen
        proc=factory(ssh_command(spec,controller),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env=env)
        events=Events(proc);events.write((json.dumps(capsule,separators=(',',':'))+'\n').encode())
        ready_deadline=time.monotonic()+15;deadline=started+spec['ttl']
        while time.monotonic()<deadline and not stopped[0] and os.getppid()==parent:
            events.pump()
            while events.events:
                kind,value=events.events.pop(0);verify_event(kind,value,spec,ready['receiver_pid'] if ready else None)
                if kind=='READY':
                    require(ready is None and proc.poll() is None);ready=value
                    private_write(ready_path,{'schema':'mastermind.go.transport-ready.v1','status':'READY','run_id':spec['run_id'],'host':spec['host'],'lease_id':spec['lease_id'],'helper_pid':os.getpid(),'ssh_pid':proc.pid,'remote_port':spec['remote_port'],'capsule_file':ready['capsule_file']})
                else:closed=value
            if proc.poll() is not None or closed is not None:break
            if ready is None and time.monotonic()>ready_deadline:raise Refused('transport refused')
        normal_close=bool(ready and stopped[0] and os.getppid()==parent)
    except Exception as error:
        failure=type(error).__name__ # Never persist exception text, capsule or stderr.
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:events.write(b'CLOSE\n',1)
                until=time.monotonic()+5
                while time.monotonic()<until:
                    events.pump(.05)
                    while events.events:
                        kind,value=events.events.pop(0);verify_event(kind,value,spec,ready['receiver_pid'] if ready else None)
                        if kind=='CLOSED':require(closed is None);closed=value
                        else:raise Refused('transport refused')
                    if proc.poll() is not None and not events.selector.get_map():break
            except Exception as error:failure=failure or type(error).__name__
            for f in (proc.stdin,):
                try:f.close()
                except OSError:pass
            local=_terminate_verified_group(proc,proc.pid,grace=1,reason='go_transport_settlement')
            if events:events.close()
        else:local={'status':'not_needed','not_started':True,'identity_verified':True,'census_proven':True,'residual_count':0}
        for sig,previous in saved.items():signal.signal(sig,previous)
    remote_clean=proc is None or closed is not None
    clean=remote_clean and cleanup_receipt_is_proven(local)
    state='COMPLETE' if clean and normal_close and failure is None and proc.returncode==0 else ('REFUSED' if clean and ready is None else 'EFFECT_UNKNOWN')
    receipt={'schema':'mastermind.go.transport-receipt.v1','status':state,'run_id':spec['run_id'],'host':spec['host'],'lease_id':spec['lease_id'],'helper_pid':os.getpid(),'ssh_pid':proc.pid if proc else None,'remote_port':spec['remote_port'],'ready_published':ready is not None,'local_cleanup':local,'remote_cleanup_proven':remote_clean,'cleanup_proven':clean,'error_class':failure,'remote_error_phase':closed.get('error_phase') if closed else None,'ssh_returncode':proc.returncode if proc else None,'duration_s':round(time.monotonic()-started,3)}
    private_write(receipt_path,receipt)
    return 0 if state=='COMPLETE' else 75

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('command',choices=['serve']);p.add_argument('--spec',required=True);p.add_argument('--ready',required=True);p.add_argument('--receipt',required=True);args=p.parse_args(argv)
    try:return serve(args.spec,args.ready,args.receipt)
    except Exception:print('GO_TRANSPORT_REFUSED',file=__import__('sys').stderr);return 78

if __name__=='__main__':raise SystemExit(main())

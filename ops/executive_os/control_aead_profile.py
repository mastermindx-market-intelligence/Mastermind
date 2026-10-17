"""Event-only sealed AEAD profile consumed by the existing control installer.

No listener, account, key, config or lifecycle owner. Bundle construction is
public artifact preparation. Materialization is a subroutine of install.sh;
the incumbent installer owns maintenance, source admission and publication.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

_ROOT=Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path: sys.path.insert(0,str(_ROOT))
from control_plane.fs_security import has_macos_acl
from ops.executive_os.control_aead_contract import (
    AeadContractError, VERSIONS, MAX_BYTES, allowed_profile_path, manifest_bytes,
    parse_lock, parse_manifest, canonical,
)

SYSTEM_ROOT=Path('/Library/Application Support/MastermindExecutive')
LOCK_RELATIVE='requirements/executive-control-aead-macos-arm64-py312.lock'
MANIFEST='.control-aead-closure.json'

class AeadProfileError(ValueError):
    pass

def refuse(): raise AeadProfileError('sealed control AEAD profile unavailable')
def _checkpoint(check):
    if check is not None: check()

def digest(data, *, check=None):
    value=hashlib.sha256()
    for start in range(0,len(data),1024*1024):
        _checkpoint(check);value.update(memoryview(data)[start:start+1024*1024])
    _checkpoint(check)
    return value.hexdigest()

def secure_data(path, *, uid=0, mode=0o444, maximum=2*MAX_BYTES, check=None):
    _checkpoint(check)
    path=Path(path);before=path.lstat()
    if (before.st_uid!=uid or not stat.S_ISREG(before.st_mode) or before.st_nlink!=1
            or stat.S_IMODE(before.st_mode)!=mode or not 0<=before.st_size<=maximum): refuse()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        opened=os.fstat(fd)
        if (before.st_dev,before.st_ino,before.st_uid,before.st_gid,before.st_mode,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(opened.st_dev,opened.st_ino,opened.st_uid,opened.st_gid,opened.st_mode,opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns) or has_macos_acl(path,expected_identity=before,descriptor=fd): refuse()
        data=bytearray()
        while len(data)<=maximum:
            _checkpoint(check)
            chunk=os.read(fd,min(1024*1024,maximum+1-len(data)))
            _checkpoint(check)
            if not chunk:break
            data.extend(chunk)
        after=os.fstat(fd)
        if len(data)>maximum or (opened.st_dev,opened.st_ino,opened.st_uid,opened.st_gid,opened.st_mode,opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_uid,after.st_gid,after.st_mode,after.st_size,after.st_mtime_ns,after.st_ctime_ns): refuse()
        _checkpoint(check)
        return bytes(data)
    finally:os.close(fd)

def sealed_directory(path, *, mode=None, check=None):
    path=Path(path)
    if not path.is_absolute(): refuse()
    for node in (path,*path.parents):
        _checkpoint(check)
        info=node.lstat()
        if (info.st_uid!=0 or not stat.S_ISDIR(info.st_mode) or info.st_mode&0o022
                or has_macos_acl(node,expected_identity=info)): refuse()
        if node==path and mode is not None and stat.S_IMODE(info.st_mode)!=mode: refuse()
    _checkpoint(check)

def _archive_data(archive, info, *, check=None):
    """Bound each decompression step by the same caller budget."""
    parts=[];size=0
    with archive.open(info) as member:
        while True:
            _checkpoint(check)
            block=member.read(1024*1024)
            _checkpoint(check)
            if not block:break
            size+=len(block)
            if size>MAX_BYTES:refuse()
            parts.append(block)
    return b''.join(parts)

def _directory_identity(info):
    return tuple(getattr(info,key) for key in ('st_dev','st_ino','st_uid','st_gid',
                 'st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))

def _require_root_directory(info):
    if info.st_uid!=0 or not stat.S_ISDIR(info.st_mode):refuse()

def create_profile_parent(parent):
    # Keep the installer's restrictive umask. Only an exclusively created,
    # root-owned, ACL-free descriptor may be widened; existing occupants are
    # untouched and must pass the caller's exact sealed-directory guard.
    parent=Path(parent)
    before=parent.parent.lstat()
    grandparent=os.open(parent.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        opened=os.fstat(grandparent);_require_root_directory(opened)
        if (opened.st_mode&0o022 or _directory_identity(before)!=_directory_identity(opened)
                or has_macos_acl(parent.parent,expected_identity=before,descriptor=grandparent)):refuse()
        try:
            os.mkdir(parent.name,mode=0o700,dir_fd=grandparent)
        except FileExistsError:return
        created=os.stat(parent.name,dir_fd=grandparent,follow_symlinks=False)
        _require_root_directory(created)
        if stat.S_IMODE(created.st_mode)&~0o700:refuse()
        fresh=os.open(parent.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=grandparent)
        try:
            if (_directory_identity(created)!=_directory_identity(os.fstat(fresh))
                    or has_macos_acl(parent,expected_identity=created,descriptor=fresh)
                    or _directory_identity(created)!=_directory_identity(os.stat(parent.name,dir_fd=grandparent,follow_symlinks=False))):refuse()
            os.fchmod(fresh,0o755)
            info=os.fstat(fresh);_require_root_directory(info)
            if (stat.S_IMODE(info.st_mode)!=0o755
                    or _directory_identity(info)!=_directory_identity(os.stat(parent.name,dir_fd=grandparent,follow_symlinks=False))
                    or has_macos_acl(parent,expected_identity=info,descriptor=fresh)):refuse()
            os.fsync(fresh)
        finally:os.close(fresh)
        os.fsync(grandparent)
    finally:os.close(grandparent)

def wheel_files(name, data, lock, *, check=None):
    # Lock hashes authorize wheel bytes, never a caller-built package manifest.
    match=re.fullmatch(r'(cffi|cryptography|pycparser)-([0-9.]+)-(.+)\.whl',name)
    if match is None: refuse()
    distribution,version,tags=match.groups()
    if version!=lock[distribution]['version'] or digest(data,check=check) not in lock[distribution]['hashes']: refuse()
    if distribution=='pycparser':
        if tags!='py3-none-any': refuse()
    elif distribution=='cffi':
        if not re.fullmatch(r'cp312-cp312-macosx_[0-9]+_[0-9]+_arm64',tags): refuse()
    elif not re.fullmatch(r'cp3(?:11|12)-abi3-macosx_[0-9]+_[0-9]+_(?:arm64|universal2)',tags): refuse()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            files={}
            for info in wheel.infolist():
                _checkpoint(check)
                if info.is_dir():continue
                if (not allowed_profile_path(info.filename) or info.filename in files
                        or info.file_size>MAX_BYTES or stat.S_ISLNK(info.external_attr>>16)): refuse()
                content=_archive_data(wheel,info,check=check)
                files[info.filename]=content
            # The lock authorizes every locked platform's bytes, so only the
            # internal WHEEL tags bind those bytes to the filename's platform.
            wheel_metadata=f'{distribution}-{version}.dist-info/WHEEL'
            if wheel_metadata not in files:refuse()
            observed=[]
            for line in files[wheel_metadata].decode('utf-8').splitlines():
                if re.match(r'\s*tag(?:\s|:|$)',line,re.IGNORECASE) is None:continue
                tag=re.fullmatch(r'Tag: (\S+)',line)
                if tag is None:refuse()
                observed.append(tag.group(1))
            if len(observed)!=1 or observed[0]!=tags:refuse()
            metadata=f'{distribution}-{version}.dist-info/METADATA'
            if metadata not in files:refuse()
            lines=files[metadata].decode('utf-8').splitlines()
            if lines.count('Name: '+distribution)!=1 or lines.count('Version: '+version)!=1:refuse()
            if sum(map(len,files.values()))>2*MAX_BYTES:refuse()
            return distribution,files
    except (zipfile.BadZipFile,UnicodeError,RuntimeError):refuse()

def bundle_files(data, lock_bytes, *, check=None):
    _checkpoint(check)
    lock=parse_lock(lock_bytes)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            infos=bundle.infolist()
            if len(infos)!=3 or any(i.is_dir() or i.file_size>MAX_BYTES or stat.S_ISLNK(i.external_attr>>16) for i in infos):refuse()
            wheels={};packages={};distributions=set()
            for info in infos:
                _checkpoint(check)
                if '/' in info.filename or '\\' in info.filename or info.filename in wheels:refuse()
                payload=_archive_data(bundle,info,check=check)
                distribution,files=wheel_files(info.filename,payload,lock,check=check)
                if distribution in distributions or set(packages)&set(files):refuse()
                distributions.add(distribution);packages.update(files);wheels[info.filename]=payload
            if distributions!=set(VERSIONS):refuse()
            entries=[{'path':p,'bytes':len(b),'sha256':digest(b,check=check),'mode':0o555 if p.endswith('.so') else 0o444} for p,b in sorted(packages.items())]
            return wheels,packages,manifest_bytes(digest(lock_bytes),entries)
    except (zipfile.BadZipFile,RuntimeError):refuse()

def build_bundle(wheels, lock_bytes):
    lock=parse_lock(lock_bytes)
    if len(wheels)!=3:refuse()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(map(Path,wheels)):
            data=path.read_bytes();wheel_files(path.name,data,lock)
            info=zipfile.ZipInfo(path.name,date_time=(1980,1,1,0,0,0));info.external_attr=0o100444<<16
            archive.writestr(info,data)
    result=output.getvalue();bundle_files(result,lock_bytes)
    return result

def profile_root(lock_bytes):return SYSTEM_ROOT/'control-dependencies'/digest(lock_bytes)

def verify_profile(release_root, *, check=None):
    _checkpoint(check)
    release_root=Path(release_root)
    sealed_directory(release_root,check=check)
    sealed_directory((release_root/LOCK_RELATIVE).parent,check=check)
    lock_bytes=secure_data(release_root/LOCK_RELATIVE,mode=0o644,maximum=32768,check=check)
    root=profile_root(lock_bytes);sealed_directory(root,mode=0o555,check=check)
    sealed_directory(root/'packages',mode=0o555,check=check);sealed_directory(root/'wheels',mode=0o555,check=check)
    wheel_paths=sorted((root/'wheels').iterdir())
    if len(wheel_paths)!=3:refuse()
    contents=io.BytesIO()
    with zipfile.ZipFile(contents,'w',compression=zipfile.ZIP_STORED) as archive:
        for path in wheel_paths:
            _checkpoint(check)
            archive.writestr(path.name,secure_data(path,maximum=MAX_BYTES,check=check))
    wheels,packages,expected=bundle_files(contents.getvalue(),lock_bytes,check=check)
    manifest=secure_data(root/MANIFEST,maximum=32*1024*1024,check=check)
    parse_manifest(manifest,digest(lock_bytes))
    if manifest!=expected:refuse()
    actual=set()
    for path in (root/'packages').rglob('*'):
        _checkpoint(check)
        relative=path.relative_to(root/'packages').as_posix();info=path.lstat()
        if stat.S_ISDIR(info.st_mode):sealed_directory(path,mode=0o555,check=check);continue
        if relative not in packages:refuse()
        actual.add(relative)
        payload=secure_data(path,mode=0o555 if relative.endswith('.so') else 0o444,maximum=MAX_BYTES,check=check)
        if payload!=packages[relative]:refuse()
    if actual!=set(packages) or {p.name for p in root.iterdir()}!={'packages','wheels',MANIFEST}:refuse()
    _checkpoint(check)
    return {'root':str(root),'packages':str(root/'packages'),'lock_sha256':digest(lock_bytes),'manifest_sha256':digest(manifest)}

def materialize_bundle(bundle, release_root, *, operator_uid):
    if os.geteuid()!=0:refuse()
    release_root=Path(release_root);sealed_directory(release_root)
    sealed_directory((release_root/LOCK_RELATIVE).parent)
    lock_bytes=secure_data(release_root/LOCK_RELATIVE,mode=0o644)
    data=secure_data(bundle,uid=operator_uid,mode=0o600)
    wheels,packages,manifest=bundle_files(data,lock_bytes)
    root=profile_root(lock_bytes)
    if root.exists():return verify_profile(release_root) # Never replace a same-profile occupant.
    sealed_directory(root.parent.parent)
    create_profile_parent(root.parent);sealed_directory(root.parent,mode=0o755)
    stage=root.parent/('.stage-'+os.urandom(16).hex());stage.mkdir(mode=0o700)
    try:
        (stage/'wheels').mkdir();(stage/'packages').mkdir()
        for name,data in wheels.items():
            path=stage/'wheels'/name;path.write_bytes(data);path.chmod(0o444)
        for name,data in packages.items():
            path=stage/'packages'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o555 if name.endswith('.so') else 0o444)
        (stage/MANIFEST).write_bytes(manifest);(stage/MANIFEST).chmod(0o444)
        for path in sorted(stage.rglob('*'),reverse=True):
            if path.is_dir():path.chmod(0o555)
        stage.chmod(0o555)
        # Existing install.sh owns serialized publication; refusal preserves stage.
        from ops.executive_os.capacity_host_artifacts import _rename_exclusive
        parent_fd=os.open(root.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            _rename_exclusive(parent_fd,stage.name,parent_fd,root.name)
            os.fsync(parent_fd)
        finally:os.close(parent_fd)
        return verify_profile(release_root)
    except BaseException:
        # Never delete an unresolved published/partial artifact or another owner.
        raise

def enrolled(raw):
    value=raw.get('reply_events')
    return type(value) is dict and value.get('armed') is True

def observe_if_enrolled(raw, release_root, *, check=None):
    if not enrolled(raw):return None
    if raw.get('proof_base_sha')!=Path(release_root).name or type(raw.get('control_uid')) is not int or raw['control_uid']!=450:refuse()
    return verify_profile(release_root,check=check) if check is not None else verify_profile(release_root)

def activate_if_enrolled(raw, release_root):
    observation=observe_if_enrolled(raw,release_root)
    if observation is None:return None
    if os.geteuid()!=raw['control_uid']:refuse()
    package_root=Path(observation['packages'])
    def require_origins():
        for name,module in tuple(sys.modules.items()):
            if name.split('.')[0] in {'cryptography','cffi','pycparser','_cffi_backend'}:
                origin=getattr(module,'__file__',None)
                if type(origin) is not str or package_root not in Path(origin).resolve(strict=True).parents:refuse()
    require_origins()
    if str(package_root) not in sys.path:sys.path.insert(0,str(package_root))
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag
        require_origins()
        # Fixed synthetic self-test, no host storage key, request or secret.
        cipher=AESGCM(bytes(range(32)));nonce=bytes(range(12));message=b'executive-control-aead-profile'
        sealed=cipher.encrypt(nonce,message,b'profile')
        if cipher.decrypt(nonce,sealed,b'profile')!=message:refuse()
        try:cipher.decrypt(nonce,sealed[:-1]+bytes([sealed[-1]^1]),b'profile')
        except InvalidTag:pass
        else:refuse()
        if verify_profile(release_root)!=observation:refuse()
        return observation
    except BaseException:
        if str(package_root) in sys.path:sys.path.remove(str(package_root))
        raise

def committed_lock(source_repo, expected_sha):
    from ops.executive_os.install_source_policy import _git
    if type(expected_sha) is not str or re.fullmatch(r'[0-9a-f]{40}',expected_sha) is None:refuse()
    if _git(Path(source_repo),'rev-parse','HEAD').stdout.strip()!=expected_sha:refuse()
    result=_git(Path(source_repo),'show',expected_sha+':'+LOCK_RELATIVE)
    data=result.stdout.encode('utf-8');parse_lock(data)
    return data

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('operation',choices=('build-bundle','check-bundle','materialize','verify'));p.add_argument('--release-root',type=Path,required=True);p.add_argument('--bundle',type=Path);p.add_argument('--wheel',action='append',type=Path,default=[]);p.add_argument('--operator-uid',type=int);p.add_argument('--expected-sha');args=p.parse_args(argv)
    if args.operation=='build-bundle':
        if args.bundle is None or args.bundle.exists():refuse()
        args.bundle.write_bytes(build_bundle(args.wheel,(args.release_root/LOCK_RELATIVE).read_bytes()));args.bundle.chmod(0o600);print(canonical({'bundle_sha256':digest(args.bundle.read_bytes())}).decode(),end='')
    elif args.operation=='check-bundle':
        if args.bundle is None or args.operator_uid is None:refuse()
        lock=committed_lock(args.release_root,args.expected_sha);data=secure_data(args.bundle,uid=args.operator_uid,mode=0o600);bundle_files(data,lock);print(canonical({'bundle_sha256':digest(data),'lock_sha256':digest(lock)}).decode(),end='')
    elif args.operation=='materialize':
        if args.bundle is None or args.operator_uid is None:refuse()
        print(canonical(materialize_bundle(args.bundle,args.release_root,operator_uid=args.operator_uid)).decode(),end='')
    else:print(canonical(verify_profile(args.release_root)).decode(),end='')
    return 0

if __name__=='__main__':raise SystemExit(main())

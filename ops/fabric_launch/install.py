"""Stage immutable prompt content and CAS-update the existing pool wrapper.

This does not install a native CapabilityPackage, change provider homes, add MCP
authority, or arm Executive OS. The release is explicitly SOURCE_CANDIDATE content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ('ops/fabric_launch/', 'research/worker_craft/mastermind-craft/', 'skills/mastermind-worker-bootstrap/')
EXACT_FILES = {'control_plane/__init__.py', 'control_plane/worker_craft.py', 'control_plane/worker_execution_contract.py'}
BEGIN = '# BEGIN MASTERMIND WORKER BOOTSTRAP'
END = '# END MASTERMIND WORKER BOOTSTRAP'
STUDIO_CONSUMER_ROOT = Path.home() / '.local/share/studio-direct-mcp/private'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_files(repository, commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('SOURCE_COMMIT_INVALID')
    entries = subprocess.check_output(['git','-C',str(repository),'ls-tree','-r','-z',commit],timeout=15).split(b'\0')
    names=[]
    for entry in entries:
        if not entry:continue
        metadata,raw_name=entry.split(b'\t',1)
        name=raw_name.decode('utf-8')
        if name not in EXACT_FILES and not name.startswith(PREFIXES):continue
        mode,kind,_=metadata.split(b' ')
        if mode not in (b'100644',b'100755') or kind!=b'blob':
            raise ValueError('SOURCE_FILE_NOT_REGULAR')
        names.append(name)
    if not EXACT_FILES.issubset(names) or len(names) > 64:
        raise ValueError('SOURCE_CLOSURE_INVALID')
    files = {}
    for name in names:
        if '..' in Path(name).parts or Path(name).is_absolute():
            raise ValueError('SOURCE_PATH_INVALID')
        value = subprocess.check_output(['git','-C',str(repository),'show',commit+':'+name],timeout=10)
        if len(value)>1024*1024:
            raise ValueError('SOURCE_FILE_TOO_LARGE')
        files[name]=value
    return files


def wrapper_content(original, release):
    if not isinstance(original, bytes):
        raise ValueError('WRAPPER_BYTES_REQUIRED')
    source=original.decode('utf-8')
    quoted=shlex.quote(str(release))
    block=(BEGIN+'\n'+
        'case "$CMD" in\n'+
        '  prepare|doctor|render|context)\n'+
        '    exec env PYTHONDONTWRITEBYTECODE=1 python3 '+quoted+'/ops/fabric_launch/cli.py "$CMD" "$@" ;;\n'+
        '  run|remote)\n'+
        '    exec env PYTHONDONTWRITEBYTECODE=1 python3 '+quoted+'/ops/fabric_launch/pool_entry.py --kit "$KIT_DIR" "$CMD" "$@" ;;\n'+
        'esac\n'+END+'\n')
    if BEGIN in source or END in source:
        if source.count(BEGIN)!=1 or source.count(END)!=1:
            raise ValueError('WRAPPER_MARKERS_INVALID')
        start=source.index(BEGIN); finish=source.index(END,start)+len(END)
        source=source[:start]+block.rstrip('\n')+source[finish:]
    else:
        needle='case "$CMD" in\n'
        if source.count(needle)!=1:
            raise ValueError('WRAPPER_SHAPE_UNREVIEWED')
        source=source.replace(needle,block+'\n'+needle,1)
    return source.encode('utf-8')


def stage(repository, commit, destination):
    files=source_files(repository,commit)
    expected={n:sha(b) for n,b in files.items()}
    manifest={'schema':'mastermind.fabric_boot_content.v1','source_commit':commit,
              'source_state':'SOURCE_CANDIDATE','execution_authority':False,
              'native_skill_attested':False,'files':expected}
    destination=Path(destination)
    if destination.exists():
        if destination.is_symlink() or (destination/'manifest.json').is_symlink() or json.loads((destination/'manifest.json').read_text())!=manifest:
            raise ValueError('EXISTING_RELEASE_MISMATCH')
        expected_names=set(files)|{'manifest.json'}
        actual_names=set()
        for path in destination.rglob('*'):
            if path.is_symlink():raise ValueError('EXISTING_RELEASE_LINK_REFUSED')
            if path.is_file():actual_names.add(str(path.relative_to(destination)))
        if actual_names!=expected_names:raise ValueError('EXISTING_RELEASE_EXTRA_OR_MISSING_FILES')
        for name,value in files.items():
            path=destination/name
            if path.is_symlink() or not path.is_file() or path.read_bytes()!=value:
                raise ValueError('EXISTING_RELEASE_DRIFT')
        return manifest
    destination.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.boot-stage-',dir=destination.parent))
    # On interruption, leave this exact unpublished staging tree for diagnosis.
    for name,value in files.items():
        path=temp/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(value)
        path.chmod(0o444)
    (temp/'manifest.json').write_text(json.dumps(manifest,sort_keys=True)+'\n')
    (temp/'manifest.json').chmod(0o444)
    for name,wanted in expected.items():
        if sha((temp/name).read_bytes())!=wanted:raise ValueError('STAGING_READBACK_FAILED')
    # Only this own, new content release is moved. No existing provider data changes.
    os.rename(temp,destination)
    for directory,_,_ in os.walk(destination,topdown=False):os.chmod(directory,0o555)
    return manifest


def pinned_consumers(wrapper, proposed_sha):
    """Read the existing Studio owner's pins; never rewrite or weaken them."""
    target=str(Path(wrapper).absolute())
    conflicts=[]
    paths=list(STUDIO_CONSUMER_ROOT.glob('*/config.json'))
    if len(paths)>32:raise ValueError('CONSUMER_CENSUS_UNBOUNDED')
    for path in paths:
        if path.is_symlink() or path.stat().st_size>1024*1024:
            raise ValueError('CONSUMER_CONFIG_UNSAFE')
        try:value=json.loads(path.read_bytes())
        except (ValueError,UnicodeError):raise ValueError('CONSUMER_CONFIG_UNREADABLE') from None
        config=value.get('fleetStatus',{}) if isinstance(value,dict) else {}
        if not isinstance(config,dict):raise ValueError('CONSUMER_CONFIG_UNREADABLE')
        if config.get('enabled') is True and config.get('fabricLauncherPath')==target:
            if config.get('fabricLauncherSha256')!=proposed_sha:
                conflicts.append(path.parent.name)
    return conflicts


def stage_wrapper_candidate(wrapper, release, expected_sha, output):
    wrapper=Path(wrapper)
    if wrapper.is_symlink() or not wrapper.is_file():raise ValueError('WRAPPER_NOT_REGULAR')
    original=wrapper.read_bytes()
    if sha(original)!=expected_sha:raise ValueError('WRAPPER_PREIMAGE_CHANGED')
    candidate=wrapper_content(original,release)
    with Path(output).open('xb') as stream:
        stream.write(candidate)
        stream.flush()
        os.fchmod(stream.fileno(),0o600)
        os.fsync(stream.fileno())
    subprocess.run(['bash','-n',str(output)],check=True,timeout=10)
    if Path(output).read_bytes()!=candidate:raise ValueError('WRAPPER_CANDIDATE_READBACK_FAILED')
    return {'state':'WRAPPER_CANDIDATE_NOT_INSTALLED','original_sha256':expected_sha,
            'candidate_sha256':sha(candidate),'pinned_consumer_count':len(pinned_consumers(wrapper,sha(candidate)))}


def activate(wrapper, release, expected_sha):
    wrapper=Path(wrapper)
    before=wrapper.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:
        raise ValueError('WRAPPER_NOT_REGULAR')
    data=wrapper.read_bytes()
    if sha(data)!=expected_sha:raise ValueError('WRAPPER_PREIMAGE_CHANGED')
    updated=wrapper_content(data,release)
    if updated==data:return {'state':'ALREADY_CURRENT','wrapper_sha256':expected_sha}
    if pinned_consumers(wrapper,sha(updated)):
        raise ValueError('PINNED_CONSUMER_RELEASE_REQUIRED')
    backup=wrapper.with_name(wrapper.name+'.pre-worker-bootstrap-'+expected_sha[:12])
    if backup.exists():
        if backup.is_symlink() or backup.read_bytes()!=data:raise ValueError('BACKUP_CONFLICT')
    else:
        with backup.open('xb') as stream:stream.write(data)
        backup.chmod(stat.S_IMODE(before.st_mode))
    fd,name=tempfile.mkstemp(prefix='.pool-worker-bootstrap-',dir=wrapper.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(updated);stream.flush();os.fchmod(stream.fileno(),stat.S_IMODE(before.st_mode));os.fsync(stream.fileno())
        subprocess.run(['bash','-n',name],check=True,timeout=10)
        after=wrapper.lstat()
        if (before.st_dev,before.st_ino,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_mtime_ns) or wrapper.read_bytes()!=data:
            raise ValueError('WRAPPER_CHANGED_DURING_PREPARE')
        os.replace(name,wrapper)
        if wrapper.read_bytes()!=updated:raise ValueError('WRAPPER_READBACK_FAILED')
        return {'state':'PROMPT_HOOK_INSTALLED','wrapper_sha256':sha(updated),'backup':str(backup)}
    finally:
        if os.path.exists(name):os.unlink(name)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-sha',required=True);p.add_argument('--destination',required=True)
    p.add_argument('--wrapper');p.add_argument('--expected-wrapper-sha');p.add_argument('--apply',action='store_true')
    p.add_argument('--candidate-output')
    args=p.parse_args(argv)
    try:
        files=source_files(ROOT,args.source_sha)
        if not args.apply:
            print(json.dumps({'state':'DRY_RUN','files':len(files),'source_commit':args.source_sha,'authority_granted':False}));return 0
        stage(ROOT,args.source_sha,Path(args.destination))
        result={'state':'CONTENT_STAGED','source_commit':args.source_sha,'authority_granted':False}
        if args.wrapper:
            if not args.expected_wrapper_sha:raise ValueError('EXPECTED_PREIMAGE_REQUIRED')
            if args.candidate_output:
                result.update(stage_wrapper_candidate(args.wrapper,Path(args.destination),args.expected_wrapper_sha,args.candidate_output))
            else:
                result.update(activate(args.wrapper,Path(args.destination),args.expected_wrapper_sha))
        print(json.dumps(result,sort_keys=True));return 0
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print('BOOT_INSTALL_REFUSED '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__),file=sys.stderr);return 78


if __name__=='__main__':raise SystemExit(main())

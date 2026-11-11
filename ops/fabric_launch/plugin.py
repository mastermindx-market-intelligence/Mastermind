"""Reproducible distributable from existing skills, not a capability registry.

This creates a candidate artifact only. Source admission, native installation,
model loading and any existing MCP authorization remain separate gates.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ops.fabric_launch.install import source_files

MAP={
    'research/worker_craft/mastermind-craft/':'skills/mastermind-craft/',
    'skills/mastermind-worker-bootstrap/':'skills/mastermind-worker-bootstrap/',
    'skills/mastermind-fabric-orchestration/':'skills/mastermind-fabric-orchestration/',
}

ORCHESTRATION_ROLE_FILES = (
    'SKILL.md',
    'references/meta-ceo.md',
    'references/program-ceo.md',
    'references/operator.md',
    'references/worker.md',
    'references/reviewer.md',
)


def assemble(files, source_commit, *, docs=False):
    result={}
    source_map={}
    for original,data in files.items():
        for prefix,target in MAP.items():
            if original.startswith(prefix):
                name=target+original[len(prefix):]
                if Path(name).is_absolute() or '..' in Path(name).parts or name in result:
                    raise ValueError('PLUGIN_SOURCE_PATH_INVALID')
                result[name]=data
                source_map[name]={'path':original,'sha256':hashlib.sha256(data).hexdigest()}
    for name in ('mastermind-craft','mastermind-worker-bootstrap'):
        if 'skills/'+name+'/SKILL.md' not in result:
            raise ValueError('PLUGIN_SKILL_MISSING')
    for role_file in ORCHESTRATION_ROLE_FILES:
        if 'skills/mastermind-fabric-orchestration/'+role_file not in result:
            raise ValueError('PLUGIN_SKILL_MISSING')
    role_prefix = 'skills/mastermind-fabric-orchestration/'
    packaged_roles = {name[len(role_prefix):] for name in result
                      if name.startswith(role_prefix)}
    if packaged_roles != set(ORCHESTRATION_ROLE_FILES):
        raise ValueError('PLUGIN_ROLE_CLOSURE_INVALID')
    variant='public-docs' if docs else 'skills-only'
    manifest={'name':'mastermind-workforce','version':'0.1.0-candidate.g'+source_commit[:12]+'.'+variant,
              'description':'Scoped worker boot, Craft methods and pinned operator-first role instructions.',
              'skills':'./skills/'}
    if docs:
        manifest['mcpServers']='./.mcp.json'
        result['.mcp.json']=(json.dumps({'mcpServers':{'openaiDeveloperDocs':{
            'type':'http','url':'https://developers.openai.com/mcp'}}},sort_keys=True)+'\n').encode()
    result['.codex-plugin/plugin.json']=(json.dumps(manifest,sort_keys=True)+'\n').encode()
    claude={**manifest,'author':{'name':'Mastermind'}}
    result['.claude-plugin/plugin.json']=(json.dumps(claude,sort_keys=True)+'\n').encode()
    result['BUILD.json']=(json.dumps({
        'schema':'mastermind.workforce_plugin_artifact.v1','source_commit':source_commit,'variant':variant,
        'source_state':'SOURCE_CANDIDATE','native_skill_attested':False,
        'execution_authority':False,'canonical_source_files':source_map,
        'mcp_servers':['openaiDeveloperDocs'] if docs else [],
    },sort_keys=True)+'\n').encode()
    result['README.md']=b'''# Mastermind Workforce candidate package

This derives existing Mastermind Craft, Worker Bootstrap, and the six-source-file
Fabric Orchestration role package from ONE exact commit. For a consequential
project, the assigned principal retains original intent and final acceptance
while an admitted operator owns ordinary decomposition, delivery, independent
review and bounded repair. Role files are guidance, not role authentication.
The actual parent/role must be supplied by an accepted commission; never infer
organizational authority from a model label or an installed Skill.

The source in BUILD.json is a candidate, not a protected CapabilityPackage.
The package does not install itself, inherit Web connector credentials, select a
provider/model/account, start children, or change Executive and Company policy.
Publication, account installation, fresh-session loading, Runtime admission and
product-path acceptance are separate gates. Merging source alone proves none.

The optional docs variant includes only OpenAI's public documentation MCP.
It requires network reachability but no API token. It is not an OpenAI inference
or organization-admin capability. All other tools come from an independently
admitted native tool/profile or the existing pool/Executive owners.

pool prepare/doctor/context/render require the separately installed launch helper
on the controlling host; packaging these skills does not install those commands.
Use source review and the existing capability-package owner before native default
selection. Do not reinterpret this artifact's hash as permission or proof of use.
'''
    return result


WORKSPACE_PLUGIN_NAME = 'mastermind-worker-bootstrap'
WORKSPACE_INTERFACE_FIELDS = frozenset({
    'capabilities', 'category', 'developerName', 'displayName',
    'longDescription', 'shortDescription',
})
WORKSPACE_MANIFEST_FIELDS = frozenset({
    'name', 'version', 'description', 'skills', 'author', 'interface',
})


def assemble_existing_workspace_update(files, source_commit, *, current_manifest_bytes):
    """Prepare an identity-preserving candidate for an existing workspace plugin.

    Input manifest bytes must come from the CURRENT release owner. This never
    invokes Plugin Creator, enrolls a seat, changes a capability or installs.
    The publisher must separately supply an observed current release ID for CAS.
    """
    if (type(source_commit) is not str
            or not re.fullmatch(r'[0-9a-f]{40}', source_commit)):
        raise ValueError('EXACT_SOURCE_COMMIT_REQUIRED')
    if type(current_manifest_bytes) is not bytes or len(current_manifest_bytes) > 65536:
        raise ValueError('WORKSPACE_MANIFEST_INVALID')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('WORKSPACE_MANIFEST_INVALID')
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError('WORKSPACE_MANIFEST_INVALID')
    try:
        original = json.loads(current_manifest_bytes, object_pairs_hook=unique,
                              parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise ValueError('WORKSPACE_MANIFEST_INVALID') from None
    if (type(original) is not dict or set(original) != WORKSPACE_MANIFEST_FIELDS
            or original.get('name') != WORKSPACE_PLUGIN_NAME
            or original.get('skills') != './skills/'
            or type(original.get('description')) is not str
            or not original['description']
            or type(original.get('author')) is not dict
            or type(original.get('interface')) is not dict
            or set(original['interface']) != WORKSPACE_INTERFACE_FIELDS
            or original['interface'].get('capabilities') != ['Read']
            or set(original['author']) != {'name', 'email'}
            or not all(type(v) is str and v for v in original['author'].values())
            or any(k in original for k in ('mcpServers', 'hooks', 'permissions', 'auth'))):
        raise ValueError('WORKSPACE_PLUGIN_IDENTITY_OR_GRANTS_INVALID')
    current_version = original.get('version')
    if type(current_version) is not str or len(current_version) > 128:
        raise ValueError('WORKSPACE_PLUGIN_VERSION_INVALID')
    match = re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.+-]+)?', current_version)
    if match is None:
        raise ValueError('WORKSPACE_PLUGIN_VERSION_INVALID')
    major, minor, patch = map(int, match.groups())
    if max(major, minor, patch) > 100000:
        raise ValueError('WORKSPACE_PLUGIN_VERSION_INVALID')
    result = assemble(files, source_commit, docs=False)
    # Preserve presentation, author, identity, original tool grants, App fields.
    # Advance patch semver only; release-id CAS is required at update time.
    updated = dict(original)
    updated['version'] = f'{major}.{minor}.{patch+1}-candidate.g{source_commit[:12]}'
    result['.codex-plugin/plugin.json'] = (json.dumps(updated, sort_keys=True)+'\n').encode()
    result.pop('.claude-plugin/plugin.json')  # the existing ChatGPT plugin has no Claude manifest
    build = json.loads(result['BUILD.json'])
    build['variant'] = 'existing-workspace-update'
    build['existing_plugin_name'] = WORKSPACE_PLUGIN_NAME
    build['existing_plugin_version'] = current_version
    build['release_id_cas_required'] = True
    result['BUILD.json'] = (json.dumps(build, sort_keys=True)+'\n').encode()
    return result


def zip_bytes(files, *, package_root='mastermind-workforce'):
    if package_root not in ('mastermind-workforce', WORKSPACE_PLUGIN_NAME):
        raise ValueError('PLUGIN_PACKAGE_ROOT_INVALID')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(package_root+'/'+name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(0o100644 << 16)
            archive.writestr(info,data)
    return stream.getvalue()



def read_workspace_manifest_file(path):
    """Read one literal regular-file snapshot without following replacement links."""
    target = Path(path)
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns)
    try:
        initial = target.lstat()
        if (not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1
                or not 0 < initial.st_size <= 65536):
            raise ValueError('WORKSPACE_MANIFEST_UNSAFE')
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if identity(opened) != identity(initial):
                raise ValueError('WORKSPACE_MANIFEST_CHANGED')
            content = stream.read(65537)
            finished = os.fstat(stream.fileno())
        if (identity(finished) != identity(initial)
                or identity(target.lstat()) != identity(initial)
                or len(content) != initial.st_size):
            raise ValueError('WORKSPACE_MANIFEST_CHANGED')
        return content
    except OSError:
        raise ValueError('WORKSPACE_MANIFEST_UNSAFE') from None


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-sha',required=True);p.add_argument('--output',required=True)
    p.add_argument('--with-public-docs',action='store_true')
    p.add_argument('--existing-workspace-manifest',help='current plugin manifest file; candidate only')
    args=p.parse_args(argv)
    try:
        source = source_files(ROOT,args.source_sha,include_orchestration=True)
        if args.existing_workspace_manifest:
            if args.with_public_docs:
                raise ValueError('WORKSPACE_DOCS_VARIANT_REFUSED')
            files = assemble_existing_workspace_update(
                source,args.source_sha,current_manifest_bytes=read_workspace_manifest_file(args.existing_workspace_manifest))
            data=zip_bytes(files,package_root=WORKSPACE_PLUGIN_NAME)
        else:
            files=assemble(source,args.source_sha,docs=args.with_public_docs)
            data=zip_bytes(files)
        with Path(args.output).open('xb') as f:f.write(data)
        if Path(args.output).read_bytes()!=data:raise ValueError('PLUGIN_READBACK_FAILED')
        print(json.dumps({'state':'PACKAGED_NOT_INSTALLED','source_commit':args.source_sha,
                          'files':len(files),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                          'native_skill_attested':False,'execution_authority':False},sort_keys=True))
        return 0
    except (ValueError,OSError) as exc:
        print('PLUGIN_PACKAGE_REFUSED '+type(exc).__name__,file=sys.stderr);return 78


if __name__=='__main__':raise SystemExit(main())

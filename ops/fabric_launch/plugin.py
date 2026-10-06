"""Reproducible distributable from existing skills, not a capability registry.

This creates a candidate artifact only. Source admission, native installation,
model loading and any existing MCP authorization remain separate gates.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ops.fabric_launch.install import source_files

MAP={
    'research/worker_craft/mastermind-craft/':'skills/mastermind-craft/',
    'skills/mastermind-worker-bootstrap/':'skills/mastermind-worker-bootstrap/',
}


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
    manifest={'name':'mastermind-workforce','version':'0.1.0-candidate.g'+source_commit[:12],
              'description':'Scoped worker boot, eight Craft methods and exact context/tool/return contracts.',
              'skills':'./skills/'}
    if docs:
        manifest['mcpServers']='./.mcp.json'
        result['.mcp.json']=(json.dumps({'mcpServers':{'openaiDeveloperDocs':{
            'type':'http','url':'https://developers.openai.com/mcp'}}},sort_keys=True)+'\n').encode()
    result['.codex-plugin/plugin.json']=(json.dumps(manifest,sort_keys=True)+'\n').encode()
    claude={**manifest,'author':{'name':'Mastermind'}}
    result['.claude-plugin/plugin.json']=(json.dumps(claude,sort_keys=True)+'\n').encode()
    result['BUILD.json']=(json.dumps({
        'schema':'mastermind.workforce_plugin_artifact.v1','source_commit':source_commit,
        'source_state':'SOURCE_CANDIDATE','native_skill_attested':False,
        'execution_authority':False,'canonical_source_files':source_map,
        'mcp_servers':['openaiDeveloperDocs'] if docs else [],
    },sort_keys=True)+'\n').encode()
    result['README.md']=b'''# Mastermind Workforce candidate package

This is a derived distribution of the existing Mastermind Craft skill plus the
Worker Bootstrap skill. Choose exactly one Craft role for a bounded assignment.
The source in BUILD.json is a candidate, not a protected CapabilityPackage.
The package does not install itself, inherit Web connector credentials, select a
provider/model/account, start children, or change Executive and Company policy.

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


def zip_bytes(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo('mastermind-workforce/'+name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(0o100644 << 16)
            archive.writestr(info,data)
    return stream.getvalue()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-sha',required=True);p.add_argument('--output',required=True)
    p.add_argument('--with-public-docs',action='store_true')
    args=p.parse_args(argv)
    try:
        files=assemble(source_files(ROOT,args.source_sha),args.source_sha,docs=args.with_public_docs)
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

"""Four fixed immutable source files and a typed held-marker predicate projection.

No CLI paths, process inspection, environment read, provider results, owner import,
lease operation, census or settlement. Embedded by the incumbent read transport
with the separately pinned, accepted inspector module supplied by that owner.
"""
from __future__ import annotations
import base64
import os
import socket

SCHEMA='mastermind.native_host_review_source_read.v1'
RUN_ID='native-host-review-22f77378-01a0e0c7'
ROOT_ID='01a0e0c7-1ed2-7fa0-a4b4-890d30ea6311'
SUPPORT='3df14e1a295570df7519adec21acf65eba6dccee80b5ab9c1e6a68a570dfb4c9'
HASHES={
    'remote_sub_exec.py':'61095d9a2664b3d2f95e994ebe53ae65a9b893ad4275a87a1dfe56efb691e77b',
    'lane_runtime.py':'ae4682dbf613eb463d16c29ed84a068b656f2b5f7292089e73828c5688b0289d',
    'native_remote.py':'788c7575a5b72a72ada4c17f30ada2b8cdf47d7873cc47142ec8a16b918afd00',
    'RELEASE.json':'ab11099a469366744b2db6201f4061a6781c141ec83a5bad458c80d3218c7b8c'}
NAMES=tuple(HASHES)
MANIFEST_BYTES=3411
MAX_SOURCE_TOTAL=128*1024
MAX_BASE64_TOTAL=192*1024
LIMITS=['Only fixed immutable support source bytes and typed marker predicate fields',
        'Not an atomic cross-file snapshot',
        'Source bytes do not attest historical execution or surviving process absence',
        'Marker projection omits the admission snapshot and is not a complete original lease',
        'No settlement eligibility, acceptance, lease clearance, retry or release decision']


def _path(name):
    prefix=('lanes','support-releases',SUPPORT)
    return (*prefix,name) if name=='RELEASE.json' else (*prefix,'ext',name)


def _collect(reader,inspector,contract):
    """Private injectable seam used only by inert fixtures."""
    code={};metadata={};total=0
    for name in NAMES:
        raw,info=reader.read(_path(name),min(MAX_SOURCE_TOTAL-total,65536 if name=='RELEASE.json' else MAX_SOURCE_TOTAL),
                             mode=0o444 if name=='RELEASE.json' else 0o555)
        total+=len(raw)
        inspector._require(inspector._sha(raw)==HASHES[name] and total<=MAX_SOURCE_TOTAL,'fixed_source_hash_or_limit')
        if name=='RELEASE.json':inspector._require(len(raw)==MANIFEST_BYTES,'fixed_manifest_size')
        else:raw.decode('utf-8')
        code[name]=raw;metadata[name]=inspector._metadata(info)
    verified=inspector._support(reader,contract)
    inspector._require(verified['digest']==SUPPORT and verified['manifest_sha256']==HASHES['RELEASE.json']
                       and verified['verified_source_sha256']=={n:HASHES[n] for n in NAMES if n!='RELEASE.json'},
                       'fixed_support_join')
    checked=inspector._marker(reader,contract)
    marker,info=reader.read(('lanes','ext','active',RUN_ID),65536)
    inspector._require(inspector._sha(marker)==checked['sha256'],'fixed_marker_changed')
    value=inspector.strict_json(marker);original=value['original_lease']
    binding=dict(schema='mastermind.native_host_review_marker_projection.v1',file=inspector._metadata(info),
        marker_sha256=checked['sha256'],
        hold={key:value[key] for key in ('schema','key','reason','held_at','host')},
        original_lease={key:original[key] for key in ('schema','key','label','pid','started_at','host',
                                                     'source_sha256','reconcile_unreleased')},
        original_lease_complete=False,root_identity_proven=False,lease_identity_proven=False)
    reader.verify()
    output=[];encoded_total=0
    for name in NAMES:
        encoded=base64.b64encode(code[name]).decode('ascii');encoded_total+=len(encoded)
        inspector._require(encoded_total<=MAX_BASE64_TOTAL,'fixed_encoded_limit')
        output.append(dict(name=name,path='/home/ubuntu2/'+'/'.join(_path(name)),status='RETRIEVED',
                           bytes=len(code[name]),sha256=HASHES[name],file=metadata[name],content_b64=encoded))
    reader.verify()
    return output,binding


def host_read_sources(inspector):
    """The caller is fixed embedded owner code, never a request-provided module."""
    out=dict(schema=SCHEMA,run_id=RUN_ID,root_id=ROOT_ID,host='ubuntu2',support_digest=SUPPORT,
             status='unavailable',files=[],marker_binding=None,limits=LIMITS.copy(),
             execution_replayed=False,effect_state_changed=False,settlement_eligible=False,accepted=False)
    try:
        inspector._require(os.getuid()==1000 and socket.gethostname().split('.')[0]=='ubuntu2'
                           and os.uname().sysname=='Linux','fixed_host_account')
        with inspector._Reader('/home/ubuntu2',1000) as reader:
            files,binding=_collect(reader,inspector,inspector._Contract())
            reader.verify();out.update(status='observed',files=files,marker_binding=binding)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,OverflowError,RecursionError,SyntaxError):
        out.update(reason='source_or_marker_unavailable',request_stopped=True)
    return out

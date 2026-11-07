"""Fixed pure-source read for independent review; incumbent transport/publication only."""
from __future__ import annotations
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import time
import artifact_delivery as delivery
import native_host_review_delivery as inspection

SCHEMA='mastermind.native_host_review_source_read.v1'
REQUEST=dict(inspection.REQUEST,schema=SCHEMA,action='read_source')
READER_SHA='b9404a097e306135c27e638d7d6b6202d0028343e6a0d62c9bac99767915c1c7'
INSPECTOR_SHA='afedcb6a13407ba75cea91109d720c522f8986763dca820acb06611cce33227a'
INSPECTION_DELIVERY_SHA='e2a72999dae71d31862ab26f0f8f8e54c0a5b08ca045d91ee86036ffc371c7b7'
RECEIPT_PATH=Path('/Volumes/Mastermind/evidence/native-codex-ceo-01a12a08/review-preexec-inspection-20261011/receipt.json')
RECEIPT_SHA='494efd4ea7901c1613d8fe6e0594ec183c7b9273f9e4bf7824eadfaf60610486'
HASHES={
 'remote_sub_exec.py':'61095d9a2664b3d2f95e994ebe53ae65a9b893ad4275a87a1dfe56efb691e77b',
 'lane_runtime.py':'ae4682dbf613eb463d16c29ed84a068b656f2b5f7292089e73828c5688b0289d',
 'native_remote.py':'788c7575a5b72a72ada4c17f30ada2b8cdf47d7873cc47142ec8a16b918afd00',
 'RELEASE.json':'ab11099a469366744b2db6201f4061a6781c141ec83a5bad458c80d3218c7b8c'}
NAMES=tuple(HASHES)
MAX_RESPONSE=256*1024
MAX_SOURCE_TOTAL=128*1024
MAX_BASE64_TOTAL=192*1024
LIMITS=['Only fixed immutable support source bytes and typed marker predicate fields',
 'Not an atomic cross-file snapshot',
 'Source bytes do not attest historical execution or surviving process absence',
 'Marker projection omits the admission snapshot and is not a complete original lease',
 'No settlement eligibility, acceptance, lease clearance, retry or release decision']


def _require(ok,reason):
    if not ok:raise ValueError(reason)


def _canonical(value):return inspection.canonical(value)
def _sha(raw):return hashlib.sha256(raw).hexdigest()

def validate_request(request):
    _require(type(request) is dict and request==REQUEST and all(type(v) is str for v in request.values()),'source_read_request_mismatch')


def request_for(run_id,root_id):
    _require((run_id,root_id)==(inspection.RUN_ID,inspection.ROOT_ID)
             and type(run_id) is str and type(root_id) is str,'source_read_scope')
    return REQUEST.copy()


def _remote_path(name):
    root='/home/ubuntu2/lanes/support-releases/'+inspection.SUPPORT+'/'
    return root+name if name=='RELEASE.json' else root+'ext/'+name


def qualify(request):
    validate_request(request)
    evidence=inspection.qualify(inspection.REQUEST)
    _require(type(evidence.get('ssh_alias')) is str and inspection.re.fullmatch(
             r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',evidence['ssh_alias']) is not None,'source_read_host_alias')
    _require(evidence['evidence_sha256']['delivery_source']==INSPECTION_DELIVERY_SHA
             and evidence['inspector_sha256']==INSPECTOR_SHA,'accepted_inspection_head_changed')
    paths=dict(inspection_receipt=RECEIPT_PATH,source_reader=delivery.HERE/'native_host_review_source_reader.py',
               source_delivery=Path(__file__).absolute())
    raw={name:delivery.local_file(path,65536) for name,path in paths.items()}
    _require(_sha(raw['inspection_receipt'])==RECEIPT_SHA and _sha(raw['source_reader'])==READER_SHA,'source_read_evidence_changed')
    receipt=inspection._strict_json(raw['inspection_receipt'])
    _require(type(receipt) is dict and receipt.get('state')=='OBSERVED' and receipt.get('request')==inspection.REQUEST
             and receipt.get('execution_replayed') is False and receipt.get('effect_state_changed') is False
             and receipt.get('outcome_accepted') is False and receipt.get('settlement_eligible') is False,
             'inspection_receipt_binding')
    # Validate the retained report through the already accepted closed validator.
    report=inspection.validate_response(_canonical(dict(schema=inspection.SCHEMA,
        request_sha256=_sha(_canonical(inspection.REQUEST)),source_sha256=INSPECTOR_SHA,report=receipt['report'])),inspection.REQUEST)
    support=report['observations']['support']
    _require(report['status']=='observed' and support['verified_source_sha256']=={n:HASHES[n] for n in NAMES if n!='RELEASE.json'}
             and support['manifest_sha256']==HASHES['RELEASE.json'] and support['manifest_file']['bytes']==3411,
             'historical_source_hash_join')
    _require(all(delivery.local_file(path,65536)==raw[name] for name,path in paths.items())
             and inspection.qualify(inspection.REQUEST)==evidence,'source_read_snapshot_changed')
    return dict(ssh_alias=evidence['ssh_alias'],original_evidence=evidence,
                source_sha256={name:_sha(value) for name,value in raw.items()},
                inspector_sha256=INSPECTOR_SHA,source_reader_sha256=READER_SHA,
                original_support_digest=inspection.SUPPORT,
                authority='exact immutable source bytes for review; no settlement or historical execution attestation')


def code_for_request(request,*,expected_hash):
    validate_request(request)
    _require(type(expected_hash) is str and expected_hash==READER_SHA,'source_reader_head_binding')
    sources=dict(inspector=delivery.local_file(delivery.HERE/'native_host_review_reconcile.py',65536),
                 reader=delivery.local_file(delivery.HERE/'native_host_review_source_reader.py',65536))
    _require(_sha(sources['inspector'])==INSPECTOR_SHA and _sha(sources['reader'])==READER_SHA,'source_read_embedded_head_changed')
    code='import sys,json,hashlib,types\n'
    for name,source in sources.items():
        digest=INSPECTOR_SHA if name=='inspector' else READER_SHA
        code+=(name+'_raw='+repr(source)+'\n'
               'assert hashlib.sha256('+name+'_raw).hexdigest()=='+repr(digest)+'\n'
               +name+'=types.ModuleType("_fixed_source_'+name+'")\n'
               'sys.modules['+name+'.__name__]='+name+'\n'
               'exec(compile('+name+'_raw,"fixed_'+name+'.py","exec"),'+name+'.__dict__)\n')
    return (code+'raw=sys.stdin.buffer.read(8193)\nassert len(raw)<=8192\n'
            'request=inspector.strict_json(raw)\nassert request=='+repr(REQUEST)+'\n'
            'report=reader.host_read_sources(inspector)\n'
            'canonical=lambda value:json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()\n'
            'wrapped={"schema":'+repr(SCHEMA)+',"request_sha256":hashlib.sha256(canonical(request)).hexdigest(),'
            '"inspector_sha256":'+repr(INSPECTOR_SHA)+',"source_reader_sha256":'+repr(READER_SHA)+',"report":report}\n'
            'print(canonical(wrapped).decode())\n')


def _marker(binding):
    keys={'schema','file','marker_sha256','hold','original_lease','original_lease_complete','root_identity_proven','lease_identity_proven'}
    _require(type(binding) is dict and set(binding)==keys and binding['schema']=='mastermind.native_host_review_marker_projection.v1'
             and binding['marker_sha256']==inspection.MARKER_SHA and all(binding[k] is False for k in (
             'original_lease_complete','root_identity_proven','lease_identity_proven')),'source_marker_projection')
    inspection._file(binding['file'],size=647)
    _require(binding['file']['device']==66307 and binding['file']['inode']==24547401,'source_marker_inode')
    hold=binding['hold'];original=binding['original_lease']
    _require(type(hold) is dict and set(hold)=={'schema','key','reason','held_at','host'}
             and hold['schema']=='mastermind.local_lane_reconciliation_hold.v1' and hold['key']==inspection.RUN_ID
             and hold['reason']=='worker_cleanup_unproven' and hold['host']=='ubuntu2','source_hold_binding')
    _require(type(original) is dict and set(original)=={'schema','key','label','pid','started_at','host','source_sha256','reconcile_unreleased'}
             and original['schema']=='mastermind.local_lane_lease.v1' and original['key']==original['label']==inspection.RUN_ID
             and original['host']=='ubuntu2' and type(original['pid']) is int and original['pid']==2553528
             and original['source_sha256'] is None and original['reconcile_unreleased'] is True,'source_original_binding')
    _require(inspection._timestamp(original['started_at'])==inspection._timestamp('2026-10-11T05:47:53.290Z')
             and inspection._timestamp(hold['held_at'])==inspection._timestamp('2026-10-11T05:47:53.297Z'),'source_marker_time')


def validate_response(raw,request):
    validate_request(request)
    _require(type(raw) is bytes and len(raw)<=MAX_RESPONSE,'source_response_limit')
    value=inspection._strict_json(raw)
    _require(type(value) is dict and set(value)=={'schema','request_sha256','inspector_sha256','source_reader_sha256','report'}
             and value['schema']==SCHEMA and value['request_sha256']==_sha(_canonical(request))
             and value['inspector_sha256']==INSPECTOR_SHA and value['source_reader_sha256']==READER_SHA,'source_response_binding')
    report=value['report'];flags={'execution_replayed','effect_state_changed','settlement_eligible','accepted'}
    keys={'schema','run_id','root_id','host','support_digest','status','files','marker_binding','limits'}|flags
    _require(type(report) is dict and keys<=set(report) and not set(report)-keys-{'reason','request_stopped'}
             and all(report[k]==request[k] and type(report[k]) is str for k in ('schema','run_id','root_id','host','support_digest'))
             and report['limits']==LIMITS and all(report[k] is False for k in flags),'source_report_shape')
    if report['status']=='unavailable':
        _require(set(report)==keys|{'reason','request_stopped'} and report['files']==[] and report['marker_binding'] is None
                 and report['reason']=='source_or_marker_unavailable' and report['request_stopped'] is True,'source_unavailable_shape')
        return report,[]
    _require(report['status']=='observed' and set(report)==keys and type(report['files']) is list
             and len(report['files'])==4,'source_report_status')
    _marker(report['marker_binding']);output=[];total=0;encoded_total=0
    for name,row in zip(NAMES,report['files']):
        _require(type(row) is dict and set(row)=={'name','path','status','bytes','sha256','file','content_b64'}
                 and row['name']==name and row['path']==_remote_path(name) and row['status']=='RETRIEVED'
                 and type(row['bytes']) is int and 0<row['bytes']<=MAX_SOURCE_TOTAL and row['sha256']==HASHES[name]
                 and type(row['content_b64']) is str and row['content_b64'].isascii(),'fixed_source_file_shape')
        encoded_total+=len(row['content_b64']);_require(encoded_total<=MAX_BASE64_TOTAL,'source_base64_limit')
        data=base64.b64decode(row['content_b64'],validate=True);total+=len(data)
        _require(len(data)==row['bytes'] and _sha(data)==HASHES[name] and total<=MAX_SOURCE_TOTAL,'fixed_source_content_join')
        inspection._file(row['file'],size=len(data),mode=0o444 if name=='RELEASE.json' else 0o555)
        if name=='RELEASE.json':
            _require(len(data)==3411,'source_manifest_size')
            manifest=inspection._strict_json(data)
            _require(type(manifest) is dict and set(manifest)=={'schema','files','digest','links'}
                     and manifest['schema']=='remote-support-code.v1' and manifest['digest']==inspection.SUPPORT
                     and type(manifest['files']) is dict and type(manifest['links']) is dict
                     and _sha(_canonical({'schema':manifest['schema'],'files':manifest['files']}))==inspection.SUPPORT
                     and all(manifest['files'].get(n)==HASHES[n] for n in NAMES if n!='RELEASE.json'),'source_manifest_canonical_join')
        else:ast.parse(data.decode('utf-8'))
        entry={k:row[k] for k in ('path','status','bytes','sha256')};entry['local_name']=name
        output.append((entry,data))
    return report,output


def export_sources(request,destination):
    evidence=qualify(request);chain=delivery.reserve_destination(destination)
    paths={'paths':[_remote_path(n) for n in NAMES]}
    receipt=dict(schema='mastermind.native_host_review_source_export_receipt.v1',request=request,evidence=evidence,
                 state='READ_PENDING',files=[],marker_binding=None,immutable_support_source_matched=False,
                 historical_execution_attested=False,execution_replayed=False,outcome_accepted=False,
                 effect_state_changed=False,settlement_eligible=False,read_transport_state='MAY_START_AFTER_THIS_INTENT')
    def unchanged():
        try:_require(qualify(request)==evidence,'source_export_snapshot_changed')
        except (OSError,ValueError,TypeError,KeyError,RecursionError):
            receipt.update(state='UNAVAILABLE',marker_binding=None,immutable_support_source_matched=False)
            raise
    try:
        delivery.write_exclusive(chain.fd,'request.json',_canonical(receipt))
        try:
            unchanged();chain.verify();receipt['read_transport_state']='ATTEMPTED_UNCONFIRMED'
            raw=delivery.transport(evidence['ssh_alias'],request,observer_source_hash=READER_SHA)
            receipt['read_transport_state']='RESPONSE_RECEIVED'
            report,files=validate_response(raw,request);unchanged();chain.verify()
            if report['status']=='observed':
                for entry,data in files:
                    delivery.write_exclusive(chain.fd,entry['local_name'],data);receipt['files'].append(entry)
                    delivery.verify_delivered(chain,receipt['files'])
                receipt.update(state='COMPLETE',marker_binding=report['marker_binding'],immutable_support_source_matched=True)
            else:delivery.unavailable(receipt,paths)
        except (OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,SyntaxError,delivery.subprocess.SubprocessError):
            delivery.unavailable(receipt,paths);receipt.update(marker_binding=None,immutable_support_source_matched=False)
        receipt['observed_at_epoch']=time.time()
        delivery.publish_receipt(chain,receipt,paths,verify_source=unchanged)
        return receipt
    finally:chain.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run_id')
    parser.add_argument('--root',required=True);parser.add_argument('--destination',required=True);args=parser.parse_args(argv)
    try:
        receipt=export_sources(request_for(args.run_id,args.root),args.destination)
        print(_canonical(receipt).decode());return 0 if receipt['state']=='COMPLETE' else 76
    except (OSError,ValueError,TypeError,KeyError,RecursionError,delivery.subprocess.SubprocessError):
        print('{"state":"REFUSED","reason":"original_source_export_unconfirmed"}');return 75

if __name__=='__main__':raise SystemExit(main())

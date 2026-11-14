"""One attended capture through the incumbent immutable Tiingo archive owner.

No provider installation, key export, repeated job, alternate route or auto-retry.
The original per-request receipts survive interruption. Never replay an ambiguous
request; inspect its original archive and request state first.
"""
from __future__ import annotations
import argparse,gzip,hashlib,importlib.util,json,sys
from datetime import datetime,timezone
from pathlib import Path

ORIGIN='2026-11-13'
START='2023-06-01'


def load_owner(path):
    spec=importlib.util.spec_from_file_location('_phase6_incumbent_tiingo_archive',path)
    if spec is None or spec.loader is None:raise ValueError('Installed owner unavailable')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module


def main(root,owner_path):
    root=Path(root);owner_path=Path(owner_path)
    if not owner_path.is_file():raise FileNotFoundError('Installed archive owner not found')
    state_path=root/'FORWARD_CAPTURE_RECEIPT.json'
    if state_path.exists():raise RuntimeError('Existing capture: reconcile original requests instead of replay')
    m=json.loads((root/'INPUT_MANIFEST.json').read_text());symbols=sorted(set(sum(m['groups'].values(),[])+m['comparators']))
    owner=load_owner(owner_path)
    state={'status':'PREFLIGHT','source_owner_sha256':hashlib.sha256(owner_path.read_bytes()).hexdigest(),
        'requested_symbols':symbols,'start_date':START,'origin':ORIGIN,'started_at':datetime.now(timezone.utc).isoformat(),
        'requests':[],'retries':0,'permission_changes':False,'production_changed':False}
    def save():state_path.write_text(json.dumps(state,indent=2))
    save()
    try:
        archive=owner.Archive() # original external-mount and reserve checks
        key=owner.read_key()    # operator-owned existing credential, never serialized
    except Exception as exc:
        state.update(status='PREFLIGHT_BLOCKED',error_type=type(exc).__name__,safe_error=str(exc)[:180]);save()
        print('FORWARD_CAPTURE_BLOCKED',state['error_type'],state['safe_error'],flush=True);return
    state['archive_root']=str(archive.root);state['status']='CAPTURING';save()
    for symbol in symbols:
        request={'instrument':symbol,'status':'REQUESTING','request_path':owner.request_path('eod-bars',symbol,{'startDate':START,'endDate':ORIGIN}),
                 'started_at':datetime.now(timezone.utc).isoformat()}
        state['requests'].append(request);save()
        try:
            result=owner.collect_one(archive,'eod-bars',symbol,key,{'startDate':START,'endDate':ORIGIN})
            raw_path=archive.root/result['path'];raw=gzip.decompress(raw_path.read_bytes())
            if hashlib.sha256(raw).hexdigest()!=result['raw_sha256']:raise ValueError('Original raw readback mismatch')
            payload=json.loads(raw)
            if not isinstance(payload,list):raise ValueError('EOD payload is not an array')
            stem=raw_path.name.removesuffix('.raw.gz');day=result['path'].split('/')[2]
            receipt_path=archive.root/'receipts'/'eod-bars'/day/(stem+'.json')
            receipt=json.loads(receipt_path.read_text());owner.validate_receipt(receipt)
            if receipt['receipt_id']!=result['receipt_id']:raise ValueError('Original receipt identity mismatch')
            request.update(status='CAPTURED_READBACK_VERIFIED',result=result,receipt_path=str(receipt_path),raw_path=str(raw_path),
                observed_at=receipt['observed_at_utc'],rows=len(payload),latest_date=max((str(x.get('date',''))[:10] for x in payload),default=None))
            print('FORWARD_CAPTURED',symbol,len(payload),request['latest_date'],flush=True)
        except Exception as exc:
            # Owner errors are sanitized; do not expose arbitrary HTTP bodies or keys.
            safe=str(exc)[:180] if isinstance(exc,(owner.TiingoArchiveError,ValueError)) else type(exc).__name__
            request.update(status='CAPTURE_FAILED_RECONCILE_ORIGINAL',safe_error=safe,error_type=type(exc).__name__)
            state['status']='CAPTURE_STOPPED';save();print('FORWARD_CAPTURE_STOPPED',symbol,safe,flush=True);return
        save()
    key=None
    state.update(status='COMPLETE',finished_at=datetime.now(timezone.utc).isoformat());save()
    print('FORWARD_CAPTURE_COMPLETE',len(symbols),'original_owner','no_background_job',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(Path(__file__).parent));p.add_argument('--owner',required=True);a=p.parse_args();main(a.root,a.owner)

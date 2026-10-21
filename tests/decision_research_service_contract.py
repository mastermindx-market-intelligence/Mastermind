"""Verify the Bot producer against the exact existing #1147 pure I/O owner.

Run with the independently acquired source file as the sole argument. Its exact
SHA256 is checked before import. No service, network, credential or worker call.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from brain import decision_research as research
from control_plane.wake_events import canonical_json_bytes
from test_decision_research import fixture

EXPECTED_SOURCE_SHA256='41cc42d8ccef50584063468f0a0320f31fe03698b679f9d2df1f85f2b1f65115'
SOURCE_REF='b832ee7d67f7a5060d7088dcb5a257328728f041'


def main():
    if len(sys.argv)!=2:raise SystemExit('Usage: decision_research_service_contract.py EXACT_UPSTREAM_IO_FILE')
    source=Path(sys.argv[1]);raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SOURCE_SHA256:
        raise SystemExit('Refusing a different upstream implementation')
    spec=importlib.util.spec_from_file_location('mmx_upstream_inference_io_verification',source)
    if spec is None or spec.loader is None:raise SystemExit('Cannot load exact verification source')
    owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
    assert owner.MAX_REQUEST_BYTES==research.MAX_REQUEST_BYTES
    assert owner.MAX_OUTPUT_CHARS==research.MAX_OUTPUT_CHARS
    cases=[]
    for rows in [1,10,45,100]:
        for selected in [1,5,10]:
            for output in [1,16384,131072]:
                context=research.prepare_context(fixture(rows=rows),question='Extract evidence and missingness; do not suggest a position size.',section_ids=['book_truth','risk_truth'],rows_per_section=selected)
                request=research.inference_request(context,max_output_chars=output)
                normalized=owner.normalize_request(request)
                assert normalized==request
                assert len(owner.canonical_bytes(normalized))<=owner.MAX_REQUEST_BYTES
                assert json.loads(normalized['input_text'])==context
                cases.append({'rows_per_domain':rows,'selected_limit':selected,'output_limit':output,'request_bytes':len(owner.canonical_bytes(request)),'passed':True})
    request=research.inference_request(research.prepare_context(fixture(),question='Extract facts.',section_ids=['book_truth']))
    for field in ['provider','model','host','worker_id','command','execution_authority']:
        try:owner.normalize_request({**request,field:'forbidden-selector'})
        except owner.InferenceIOError:cases.append({'unknown_field_rejected':field,'passed':True})
        else:raise AssertionError('owner accepted a new selector '+field)
    result={'scope':'Exact pure service request-shape compatibility only; not wired client, admission, dispatch, result or production proof',
            'upstream_ref':SOURCE_REF,'upstream_path':'control_plane/executive_inference_io.py','upstream_sha256':EXPECTED_SOURCE_SHA256,
            'producer_sha256':hashlib.sha256(Path(research.__file__).read_bytes()).hexdigest(),'cases':cases,'passed':len(cases)}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

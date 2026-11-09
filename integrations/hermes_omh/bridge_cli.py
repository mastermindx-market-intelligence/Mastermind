"""Fixed local native bridge protocol; bounded JSON in/out, no service or queue."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from control_plane.executive_orchestration_result import canonical_bytes
from .adapter import MAX_BYTES,ProposalError,prepare_execution_plan
from .json_input import decode_plain_json
from .recommendations import RecommendationError,recommend


def process_request(raw: bytes, *, omh_home: Path, backend=None) -> dict:
    request=decode_plain_json(raw)
    if type(request) is not dict:raise ProposalError('INVALID_INPUT')
    action=request.get('action')
    if action=='plan' and set(request)=={'action','proposal'}:
        data=request['proposal']
        if type(data) is not dict or set(data)!={'nodes','policies','root_job_id','plan_attempt_id'}:
            raise ProposalError('INVALID_INPUT')
        return prepare_execution_plan(**data)
    if action=='recommend' and set(request)=={'action','message','category'}:
        return recommend(request['message'],request['category'],omh_home=omh_home,backend=backend)
    if action=='status' and set(request)=={'action'}:
        return dict(schema='mastermind.hermes_omh.bridge/v1',state='LOCAL_BRIDGE_READY',
                    actions=['plan','recommend','status'],admitted=False,dispatched=False,
                    memory_replaced=False,capacity_selected=False)
    raise ProposalError('INVALID_INPUT')


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise ProposalError('INVALID_INPUT')


def main(argv=None):
    parser=_Parser(allow_abbrev=False,description='Read-only native OMH bridge; never admits or dispatches work.')
    parser.add_argument('--omh-home',required=True)
    try:
        args=parser.parse_args(argv)
        if not Path(args.omh_home).is_absolute():raise ProposalError('INVALID_INPUT')
        result=process_request(sys.stdin.buffer.read(MAX_BYTES+1),omh_home=Path(args.omh_home))
    except (ProposalError,RecommendationError) as exc:
        result=dict(state='REFUSED',reason=exc.reason)
    except (OSError,ValueError):result=dict(state='REFUSED',reason='INPUT_UNAVAILABLE')
    raw=canonical_bytes(result)
    if len(raw)>MAX_BYTES:raw=canonical_bytes(dict(state='REFUSED',reason='OUTPUT_OVER_BUDGET'))
    sys.stdout.buffer.write(raw+b'\n')
    return 2 if result['state']=='REFUSED' else 0


if __name__=='__main__':raise SystemExit(main())

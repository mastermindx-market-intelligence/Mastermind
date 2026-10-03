#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from control_plane.project_recovery import assess_recovery,render_assessment
from control_plane.project_recovery_contract import ProjectRecoveryContractError

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--session-truth",required=True); p.add_argument("--agentos-state",required=True); p.add_argument("--as-of",required=True); p.add_argument("--observed-at",required=True)
    g=p.add_mutually_exclusive_group(required=True); g.add_argument("--json",action="store_true"); g.add_argument("--text",action="store_true")
    a=p.parse_args()
    try:
        st=json.loads(Path(a.session_truth).read_text()); ao=json.loads(Path(a.agentos_state).read_text()); result=assess_recovery(st,ao,as_of=a.as_of,observed_at=a.observed_at)
    except (OSError,json.JSONDecodeError,ProjectRecoveryContractError,ValueError) as exc:
        print(f"project recovery input error: {exc}",file=sys.stderr); return 2
    print(json.dumps(result,sort_keys=True,separators=(",",":")) if a.json else render_assessment(result),end="\n" if a.json else ""); return 0
if __name__=="__main__": raise SystemExit(main())

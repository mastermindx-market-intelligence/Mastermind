#!/usr/bin/env python3
"""Fail-closed source-only qualifier for selected M2 native generation 33."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent / "m2_current_profile"))
import qualify_m2_current as q
PROFILE_ID = "m2-1771-20261105-exact-selected-code"

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installed-ext",required=True)
    p.add_argument("--owner-modules-root",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--verify-only",action="store_true")
    a=p.parse_args(argv)
    try:
        result=q.qualify(installed_ext=Path(a.installed_ext),
            owner_modules_root=Path(a.owner_modules_root),
            output=Path(a.output),verify_only=a.verify_only,
            profile_dir=HERE,expected_profile_id=PROFILE_ID)
    except q.compose.CompositionRefused as exc:
        print(str(exc),file=sys.stderr)
        return 78
    print(json.dumps(result,sort_keys=True,separators=(",",":")))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

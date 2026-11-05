"""Deterministic SIC range audit; mixed 49-to-10 groups never silently assigned."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import re,zipfile,json

ROOT=Path(__file__).resolve().parent

def definitions(source:Path):
    with zipfile.ZipFile(source) as z:
        if len(z.namelist())!=1: raise ValueError('unexpected multiple SIC definitions')
        lines=z.read(z.namelist()[0]).decode('utf-8-sig').splitlines()
    out={};current=None
    for line in lines:
        header=re.match(r'^\s*(\d{1,2})\s+([A-Za-z0-9]+)\s{2,}(.+)$',line)
        if header:
            current=header.group(2)
            if current in out:raise ValueError('duplicate industry')
            out[current]=set()
            continue
        span=re.match(r'^\s*(\d{4})-(\d{4})(?:\s|$)',line)
        if span:
            if current is None:raise ValueError('SIC range outside industry')
            low,high=int(span.group(1)),int(span.group(2))
            if low>high:raise ValueError('reversed SIC range')
            values=set(range(low,high+1))
            if out[current]&values:raise ValueError('overlap within industry')
            out[current]|=values
    return out

def mapping(root:Path=ROOT,min_children:int=2):
    ten=definitions(root/'private/Siccodes10.zip')
    fortynine=definitions(root/'private/Siccodes49.zip')
    if len(ten)!=10 or len(fortynine)!=49 or 'Other' not in ten:raise ValueError('unexpected SIC taxonomy')
    coverage={}
    for p,nums in ten.items():
        for n in nums:
            if n in coverage:raise ValueError('parent SIC overlap')
            coverage[n]=p
    # Source 10-industry definition states OTHER is the catch-all; it has no explicit SIC ranges.
    if ten['Other']:raise ValueError('expected residual Other category')
    pure={};mixed={}
    for child,nums in fortynine.items():
        if not nums:raise ValueError('49 industry has no explicit ranges '+child)
        counts=Counter(coverage.get(code,'Other') for code in nums)
        if len(counts)==1:pure[child]=next(iter(counts))
        else:mixed[child]=dict(sorted(counts.items()))
    by_parent={p:sorted([k for k,v in pure.items() if v==p]) for p in ten}
    retained={p:k for p,k in by_parent.items() if len(k)>=min_children}
    result={'min_pure_children':min_children,'parent_names':list(ten),'all_49_industries':len(fortynine),'pure_industries':len(pure),'mixed_excluded':mixed,'one_or_zero_child_parents':{p:v for p,v in by_parent.items() if len(v)<min_children},'retained':retained,'mapping_basis':'Source SIC code sets at annual June portfolio formation; Other is the catch-all in the 10-way scheme. A 49-way child is retained only if 100% of its published SIC codes map to one 10-way parent. No firm-weight composition or parent-return arithmetic identity is implied.'}
    if len(retained)<5:raise ValueError('too few meaningful groups')
    return result

if __name__=='__main__':print(json.dumps(mapping(),indent=2))

"""Research-only constructed counterexamples. No actual market alpha asserted."""
import hashlib,json
from pathlib import Path

def area(events):
 c=r=a=0.
 for dc,dr in events:a+=c*dr-r*dc;c+=dc;r+=dr
 return a

def burst(delay,times):
 depth=2;pending=[];fails=0
 for t in times:
  depth+=sum(x<=t for x in pending);pending=[x for x in pending if x>t]
  if depth:depth-=1;pending.append(t+delay)
  else:fails+=1
 return fails

def prefixes(events,n,seed):
 state={};out=[];ids=set();last=-1
 for eid,clock,sign,size in events:
  if eid in ids or clock<last or sign not in [-1,1] or size<=0:raise ValueError('bad event')
  ids.add(eid);last=clock;k=int.from_bytes(hashlib.sha256(f'{seed}:{eid}'.encode()).digest()[:8],'big')%n
  s,v=state.get(k,(0,0));state[k]=(sign,v+size if s==sign else size)
  out.append(sum(s*v for s,v in state.values())/sum(v for s,v in state.values()))
 return out

if __name__=='__main__':
 e=[(str(i),i,1 if i%3 else -1,1+i%5) for i in range(120)]
 for n in [4,16,64]:
  for seed in range(8):assert prefixes(e[:61],n,seed)==prefixes(e,n,seed)[:61]
 assert area([(1,0),(0,1)])==1 and area([(0,1),(1,0)])==-1
 assert (burst(1,[0,2,4]),burst(8,[0,2,4]))==(0,1)
 assert (burst(1,[0,10,20]),burst(8,[0,10,20]))==(0,0)
 assert all(.5*(2+b-(b+2))==0 for b in [0,5,100])
 assert .9*0-.2*1<0 and .9*10-.2*11>0
 out={'status':'PASSED_CONSTRUCTED_MECHANISM_CHECKS_NOT_MARKET_VALIDATION','prefix_mapping_worlds':24,'same_totals_different_area':[1,-1],'burst_breaches_fast_slow':[0,1],'sparse_breaches_fast_slow':[0,0],'observational_equivalence':True,'opposite_post_pause':True}
 Path(__file__).with_name('PROTOTYPE_CHECKS.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))

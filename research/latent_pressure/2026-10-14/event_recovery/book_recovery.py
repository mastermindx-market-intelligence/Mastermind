"""Research-only recovery engine for EXPLICIT, normalized synthetic order events.
No DEEP+ book decoder, broker, network, production schema or probability authority.
'LEVEL_DEPLETED' is loss of displayed quantity at a price, NOT a trade-price break.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass,asdict
from statistics import median

@dataclass(frozen=True)
class Event:
    sequence:int
    received_ns:int
    kind:str # ADD, MODIFY, DELETE, EXECUTE
    order_id:int
    side:int # +1 resting bid, -1 resting ask
    price:int # integer price ticks; current order price on DELETE/EXECUTE
    quantity:int # total remaining on ADD/MODIFY, executed amount on EXECUTE

@dataclass
class Response:
    side:int
    level:int
    start_ns:int
    start_sequence:int
    original_depth:int
    shock_quantity:int
    initial_remaining:int
    state:str='PENDING'
    completed_ns:int|None=None
    completion_sequence:int|None=None

class RecoveryBook:
    def __init__(self, *, horizon_ns:int=10_000_000_000, shock_fraction:float=.5):
        if horizon_ns<=0 or not 0<shock_fraction<=1:raise ValueError('invalid measurement parameters')
        self.horizon_ns=horizon_ns;self.shock_fraction=shock_fraction
        self.orders={};self.pending={};self.history=[];self.sequence=-1;self.time=-1;self.valid=True
        self.skipped_immediate_depletions=0
    def depth(self,side,price):return sum(q for s,p,q in self.orders.values() if s==side and p==price)
    def best(self,side):
        p=[p for s,p,q in self.orders.values() if s==side and q>0]
        return (max(p) if side==1 else min(p)) if p else None
    def _finish(self,side,state,t,seq):
        r=self.pending.pop(side);r.state=state;r.completed_ns=t;r.completion_sequence=seq;self.history.append(r)
    def _expire(self,t,seq):
        for side,r in list(self.pending.items()):
            if t>r.start_ns+self.horizon_ns:self._finish(side,'HORIZON_ENDED_UNRECOVERED',r.start_ns+self.horizon_ns,seq)
    def invalidate(self):
        self.valid=False
        for side in list(self.pending):self._finish(side,'SOURCE_GAP_CENSORED',self.time,self.sequence)
    def apply(self,e:Event):
        if not self.valid:raise ValueError('source invalidated; no continuing inference')
        if not all(type(x) is int for x in [e.sequence,e.received_ns,e.order_id,e.side,e.price,e.quantity]):raise ValueError('exact integer fields required')
        if e.sequence<=self.sequence or e.received_ns<self.time:raise ValueError('out-of-order observation')
        if e.side not in [-1,1] or e.price<=0 or e.quantity<0:raise ValueError('bad price/side/quantity')
        old=self.orders.get(e.order_id)
        if e.kind=='ADD':
            if old or e.quantity<=0:raise ValueError('duplicate/empty add')
        elif e.kind in ['MODIFY','DELETE','EXECUTE']:
            if old is None:raise ValueError('unknown order, source cannot be reconstructed')
            if old[0]!=e.side:raise ValueError('side mutation not in normalized contract')
            if e.kind in ['DELETE','EXECUTE'] and old[1]!=e.price:raise ValueError('price reference mismatch')
            if e.kind=='EXECUTE' and not 0<e.quantity<=old[2]:raise ValueError('overexecution')
            if e.kind=='DELETE' and e.quantity:raise ValueError('delete quantity must be zero')
        else:raise ValueError('unknown kind')
        self._expire(e.received_ns,e.sequence)
        pre_depth=self.depth(e.side,e.price);pre_best=self.best(e.side)
        if e.kind in ['ADD','MODIFY']:
            if e.quantity:self.orders[e.order_id]=(e.side,e.price,e.quantity)
            else:self.orders.pop(e.order_id)
        elif e.kind=='DELETE':self.orders.pop(e.order_id)
        else:
            remaining=old[2]-e.quantity
            if remaining:self.orders[e.order_id]=(old[0],old[1],remaining)
            else:self.orders.pop(e.order_id)
        # Resolve previously open measurements only from now-observed state.
        for side,r in list(self.pending.items()):
            d=self.depth(side,r.level)
            if d==0:self._finish(side,'LEVEL_DEPLETED',e.received_ns,e.sequence)
            elif d>=r.original_depth:self._finish(side,'RECOVERED',e.received_ns,e.sequence)
        remaining_depth=self.depth(e.side,e.price)
        if e.kind=='EXECUTE' and pre_best==e.price and pre_depth and e.quantity/pre_depth>=self.shock_fraction and e.side not in self.pending:
            if remaining_depth==0:self.skipped_immediate_depletions+=1
            else:self.pending[e.side]=Response(e.side,e.price,e.received_ns,e.sequence,pre_depth,e.quantity,remaining_depth)
        self.sequence=e.sequence;self.time=e.received_ns
    def snapshot(self,cutoff_ns:int):
        if type(cutoff_ns) is not int or cutoff_ns<self.time:raise ValueError('past snapshot requires replay of original prefix')
        b=deepcopy(self);b._expire(cutoff_ns,b.sequence)
        sides={}
        for side in [1,-1]:
            done=[x for x in b.history if x.side==side][-20:];rec=[x for x in done if x.state=='RECOVERED'];r=b.pending.get(side)
            sides['bid' if side==1 else 'ask']={'pending':asdict(r) if r else None,'elapsed_ns':cutoff_ns-r.start_ns if r else None,'current_level_depth':b.depth(side,r.level) if r else None,'past_recoveries':len(rec),'past_level_depletions':sum(x.state=='LEVEL_DEPLETED' for x in done),'right_censored':sum(x.state in ['HORIZON_ENDED_UNRECOVERED','SOURCE_GAP_CENSORED'] for x in done),'median_completed_recovery_ns':median([x.completed_ns-x.start_ns for x in rec]) if rec else None}
        return {'schema':'research_snapshot_not_production','cutoff_ns':str(cutoff_ns),'last_received_ns':str(b.time),'last_sequence':str(b.sequence),'input_origin':'SYNTHETIC_NORMALIZED_FIXTURE','source_integrity':b.valid,'sides':sides,'immediate_depletions_not_predicted':b.skipped_immediate_depletions,'inferred_institution':None,'forecast_probability':None,'forecast_authority':'NONE'}

def decode_iex_book_event(*args,**kwargs):
    raise NotImplementedError('DEEPPLUS_BOOK_FIELDS_UNVERIFIED: no guessing side/modify/delete semantics. Use only the separately qualified L-only research path.')

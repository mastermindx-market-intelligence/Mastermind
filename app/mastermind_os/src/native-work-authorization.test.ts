import {expect,it,vi} from 'vitest';
import {decodeWorkAuthorization,bindNativeWorkAuthorization} from './native-work-authorization';
import type {RawClient} from './host';
const eligible={schema:'mastermind.native_work_authorization.v1',state:'ELIGIBLE',reason:'WORK_NOT_ESTABLISHED',generation:3};
it('accepts only the three closed native observation variants',()=>{
 for(const [state,reason] of [['ELIGIBLE','WORK_NOT_ESTABLISHED'],['INELIGIBLE','NOT_ELIGIBLE'],['ADMIN_ACTION_REQUIRED','AUTHORIZATION_REFUSED']])expect(Object.isFrozen(decodeWorkAuthorization({...eligible,state,reason}))).toBe(true);
});
it('refuses extra/accessor/prototype/mixed tuple/unsafe-generation metadata',()=>{
 const getter=Object.defineProperty({...eligible},'generation',{get(){throw Error('PRIVATE_GETTER');}});
 for(const value of [{...eligible,token:'no'},{...eligible,state:'ADMIN_ACTION_REQUIRED'},{...eligible,generation:NaN},{...eligible,generation:2**53},{...eligible,generation:-1},getter,Object.create(eligible),null])expect(()=>decodeWorkAuthorization(value)).toThrow();
});
function setup(){let epoch=1,hostEpoch=2;const raw={getState:()=>({status:'signed_in',reason:null,acquisition:true,content:true}),invalidationGeneration:()=>epoch,readWorkAuthorization:vi.fn(async()=>eligible),signInForWork:vi.fn(async()=>{})} as unknown as RawClient;const owner=bindNativeWorkAuthorization(raw,()=>hostEpoch)!;return {raw,owner,bump:()=>{epoch++;hostEpoch++;}};}
it('requires a qualified current read before one fixed command',async()=>{const x=setup();await expect(x.owner.signIn()).rejects.toThrow();await x.owner.read({signal:new AbortController().signal});await x.owner.signIn();expect(x.raw.signInForWork).toHaveBeenCalledWith();await expect(x.owner.signIn()).rejects.toThrow();expect(x.raw.signInForWork).toHaveBeenCalledTimes(1);});
it.each(['raw','host'] as const)('withholds late %s-generation read and command',async()=>{const x=setup();let finish!:(v:unknown)=>void;x.raw.readWorkAuthorization=()=>new Promise(r=>{finish=r;});const owner=bindNativeWorkAuthorization(x.raw,x.raw.invalidationGeneration!)!;const pending=owner.read({signal:new AbortController().signal});x.bump();finish(eligible);await expect(pending).rejects.toThrow();await expect(owner.signIn()).rejects.toThrow();});
it('does not dispatch held refusal and retains ambiguous handoff',async()=>{const x=setup();x.raw.readWorkAuthorization=async()=>({...eligible,state:'ADMIN_ACTION_REQUIRED',reason:'AUTHORIZATION_REFUSED'});const owner=bindNativeWorkAuthorization(x.raw,()=>1)!;await owner.read({signal:new AbortController().signal});await expect(owner.signIn()).rejects.toThrow();expect(x.raw.signInForWork).not.toHaveBeenCalled();
 const y=setup();y.raw.signInForWork=vi.fn(async()=>{throw Error('LOST');});const held=bindNativeWorkAuthorization(y.raw,()=>1)!;await held.read({signal:new AbortController().signal});await expect(held.signIn()).rejects.toThrow();await expect(held.read({signal:new AbortController().signal})).rejects.toThrow();expect(y.raw.signInForWork).toHaveBeenCalledTimes(1);
});

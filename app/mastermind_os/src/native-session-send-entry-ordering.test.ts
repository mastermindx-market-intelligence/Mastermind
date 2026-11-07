import {expect,it,vi} from 'vitest';
import {createNativeClient,type RawClient} from './host';
import fixture from './fixtures/native-session-send-producer.json';

// Supported single-RawClient producer ordering only. The native auth command
// is inert here; no nativeGeneration/private-token equivalence is fabricated.
it.each(['signIn','signOut'] as const)('%s withdraws the old session transport before entering native auth, even without an auth event',async(action)=>{
 let raw!:RawClient;
 let atNativeEntry:Promise<unknown>|undefined;
 let finish!:(value:unknown)=>void;
 const held=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn((command:string):Promise<unknown>=>{
  if(command==='executive_auth_status')return Promise.resolve({generation:1,available:true});
  if(command==='auth_status')return Promise.resolve({status:'signed_in',reason:null,acquisition:true,content:true});
  if(command==='sign_in'||command==='sign_out'){
   atNativeEntry=raw.executiveSession!.send!(fixture.arguments,new AbortController().signal)
    .then(()=>({unexpected:'sent'}),error=>(error as Error).message);
   return held;
  }
  if(command==='executive_session_send')return Promise.resolve(fixture.sent);
  return Promise.reject(Error('SOURCE_NOT_SUPPLIED'));
 });
 raw=await createNativeClient(invoke as never,async()=>()=>{});
 expect(raw.executiveSession!.available()).toBe(true);
 const pending=raw[action]();
 expect(await atNativeEntry).toBe('EXECUTIVE_UNAVAILABLE');
 await expect(raw.executiveSession!.send!(fixture.arguments,new AbortController().signal)).rejects.toThrow('EXECUTIVE_UNAVAILABLE');
 expect(invoke.mock.calls.filter(([command])=>command==='executive_session_send')).toHaveLength(0);
 finish({status:'signed_out',reason:'USER_SIGNED_OUT',acquisition:false,content:false});
 await pending;
});

import type {RawClient} from './host';
export type WorkAuthorization = Readonly<{schema:'mastermind.native_work_authorization.v1';state:'ELIGIBLE'|'INELIGIBLE'|'ADMIN_ACTION_REQUIRED';reason:'WORK_NOT_ESTABLISHED'|'NOT_ELIGIBLE'|'AUTHORIZATION_REFUSED';generation:number}>;
export interface NativeWorkAuthorizationOwner {read(request:{signal:AbortSignal}):Promise<WorkAuthorization>;signIn():Promise<void>;}
export function decodeWorkAuthorization(raw:unknown):WorkAuthorization {
 const fail=():never=>{throw Error('WORK_AUTHORIZATION_UNAVAILABLE');};
 if(!raw||typeof raw!=='object'||Object.getPrototypeOf(raw)!==Object.prototype)return fail();
 const d=Object.getOwnPropertyDescriptors(raw),keys=Reflect.ownKeys(raw);if(keys.length!==4||!['schema','state','reason','generation'].every(k=>d[k]&&'value'in d[k]))return fail();
 const v=raw as WorkAuthorization;
 if(v.schema!=='mastermind.native_work_authorization.v1'||!Number.isSafeInteger(v.generation)||v.generation<0||
 !((v.state==='ELIGIBLE'&&v.reason==='WORK_NOT_ESTABLISHED')||(v.state==='INELIGIBLE'&&v.reason==='NOT_ELIGIBLE')||(v.state==='ADMIN_ACTION_REQUIRED'&&v.reason==='AUTHORIZATION_REFUSED')))return fail();
 return Object.freeze({schema:v.schema,state:v.state,reason:v.reason,generation:v.generation});
}
/** Metadata is observation, not clearance. Native recomputes eligibility atomically. */
export function bindNativeWorkAuthorization(client:RawClient,hostEpoch:()=>number):NativeWorkAuthorizationOwner|undefined {
 const read=client.readWorkAuthorization,command=client.signInForWork,state=client.getState,generation=client.invalidationGeneration;
 if(!read||!command||!generation)return;
 let frame:(()=>boolean)|null=null,busy=false,uncertain=false;
 const acquire=()=>{const epoch=hostEpoch(),g=generation.call(client),s=JSON.stringify(state.call(client));return()=>{
  try {const a=state.call(client);return client.readWorkAuthorization===read&&client.signInForWork===command&&client.getState===state&&client.invalidationGeneration===generation&&Number.isSafeInteger(g)&&g>=0&&generation.call(client)===g&&hostEpoch()===epoch&&JSON.stringify(a)===s&&a.status==='signed_in'&&a.acquisition&&a.content;}catch{return false;}
 };};
 return {async read({signal}) {frame=null;const current=acquire();if(uncertain||busy||signal.aborted||!current())throw Error('WORK_AUTHORIZATION_UNAVAILABLE');
  const value=decodeWorkAuthorization(await read.call(client));if(signal.aborted||!current()||busy||uncertain)throw Error('WORK_AUTHORIZATION_UNAVAILABLE');if(value.state==='ELIGIBLE')frame=current;return value;
 },async signIn(){const current=frame;frame=null;if(busy||uncertain||!current?.())throw Error('WORK_AUTHORIZATION_INELIGIBLE');busy=true;
  try {await command.call(client);}catch(error){uncertain=true;throw error;}finally{busy=false;}
 }};
}

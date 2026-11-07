export interface CompanyPriorities {
 readonly schema:"mastermind.company_priorities.v1";
 readonly source:{readonly owner:"STRATEGIC_STATE";readonly revision:string;readonly path:"config/strategic_state.yml";readonly observed_at:string};
 readonly owner_context:{readonly principal_scope:string;readonly verified_expiry:number};
 readonly authority:"advisory_and_orientation_only";readonly as_of:string;readonly company_phase:string;
 readonly north_star:readonly string[];
 readonly priorities:readonly {readonly id:string;readonly department:string;readonly objective:string;readonly status:"active"|"paused"|"achieved"|"retired"}[];
 readonly phase_review_criteria:Readonly<Record<string,{readonly purpose:string;readonly criteria:readonly string[];readonly on_pass:string}>>;
}
export interface CompanyPrioritiesOwner {
 generation():number;available():boolean;subscribe(listener:()=>void):()=>void;
 read(signal:AbortSignal):Promise<CompanyPriorities>;
}
const bad=():never=>{throw new Error("COMPANY_PRIORITIES_INVALID")};
const exact=(v:unknown,keys:readonly string[]):v is Record<string,unknown>=>!!v&&typeof v==="object"&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
function detach(v:unknown,depth=0):unknown{
 if(depth>12)return bad();
 if(v===null||typeof v==="string"||typeof v==="boolean"||(typeof v==="number"&&Number.isFinite(v)))return v;
 if(!v||typeof v!=="object"||(!Array.isArray(v)&&![Object.prototype,null].includes(Object.getPrototypeOf(v))))return bad();
 if(Reflect.ownKeys(v).some(k=>typeof k!=="string"))return bad();
 const own=Reflect.ownKeys(v);if(own.length!==Object.keys(v).length+(Array.isArray(v)?1:0))return bad();
 const out:Record<string,unknown>|unknown[]=Array.isArray(v)?[]:{};
 for(const key of Object.keys(v)){const d=Object.getOwnPropertyDescriptor(v,key);if(!d||!("value" in d)||!d.enumerable||key==="__proto__")return bad();(out as Record<string,unknown>)[key]=detach(d.value,depth+1)}
 if(Array.isArray(v)&&Object.keys(v).length!==v.length)return bad();
 return out;
}
const text=(v:unknown)=>typeof v==="string"&&v.trim().length>0&&v.length<=8192;
const texts=(v:unknown,max:number)=>Array.isArray(v)&&v.length>0&&v.length<=max&&v.every(text);
function freeze<T>(v:T):T {if(v&&typeof v==="object"){Object.values(v).forEach(freeze);Object.freeze(v)}return v}
export function decodeCompanyPriorities(raw:unknown,now=Date.now()):CompanyPriorities{
 const v=detach(raw);
 if(new TextEncoder().encode(JSON.stringify(v)).length>65536||!exact(v,["schema","source","owner_context","authority","as_of","company_phase","north_star","priorities","phase_review_criteria"])||v.schema!=="mastermind.company_priorities.v1"||v.authority!=="advisory_and_orientation_only")return bad();
 if(!exact(v.source,["owner","revision","path","observed_at"])||v.source.owner!=="STRATEGIC_STATE"||v.source.path!=="config/strategic_state.yml"||typeof v.source.revision!=="string"||! /^[a-f0-9]{40}$/.test(v.source.revision)||!text(v.source.observed_at)||!Number.isFinite(Date.parse(v.source.observed_at as string)))return bad();
 if(!exact(v.owner_context,["principal_scope","verified_expiry"])||typeof v.owner_context.principal_scope!=="string"||! /^[a-f0-9]{64}$/.test(v.owner_context.principal_scope)||!Number.isSafeInteger(v.owner_context.verified_expiry)||Number(v.owner_context.verified_expiry)*1000<=now)return bad();
 if(typeof v.as_of!=="string"||! /^\d{4}-\d{2}-\d{2}$/.test(v.as_of)||!Number.isFinite(Date.parse(v.as_of))||!text(v.company_phase)||!texts(v.north_star,32)||!Array.isArray(v.priorities)||v.priorities.length<1||v.priorities.length>128)return bad();
 const ids=new Set();for(const p of v.priorities){if(!exact(p,["id","department","objective","status"])||typeof p.id!=="string"||! /^[A-Z][A-Z0-9_]{0,127}$/.test(p.id)||ids.has(p.id)||!text(p.department)||!text(p.objective)||!["active","paused","achieved","retired"].includes(p.status as string))return bad();ids.add(p.id)}
 const gates=v.phase_review_criteria;if(!gates||typeof gates!=="object"||Array.isArray(gates)||Object.keys(gates).length<1||Object.keys(gates).length>16)return bad();
 for(const [name,g] of Object.entries(gates)){if(! /^[A-Z][A-Z0-9_]{0,63}$/.test(name)||!exact(g,["purpose","criteria","on_pass"])||!text(g.purpose)||!text(g.on_pass)||!texts(g.criteria,32))return bad()}
 return freeze(v as unknown as CompanyPriorities);
}

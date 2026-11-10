import {canonicalJson} from './operation-key';
import {decodeFreshConversationReference,type FreshConversationReference} from '../conversations/fresh-conversation-reference';

export type FreshConversationOriginalSelector=Readonly<{work_ref:string;operation_key:string}>|
  Readonly<{work_ref:string;reference:FreshConversationReference}>;
/** Ordinary client correlation only; recovery never calls this function. */
export function mintFreshConversationCommandKey(kind:'conversation_consume'|'conversation_turn'):string|null {
  if(kind!=='conversation_consume'&&kind!=='conversation_turn')return null;
  try {const source=globalThis.crypto,method=source?.getRandomValues;
    if(typeof method!=='function')return null;
    const bytes=new Uint8Array(20),filled=method.call(source,bytes);
    if(!(filled instanceof Uint8Array)||filled!==bytes||filled.length!==20)return null;
    return `mmos-${kind.replace('_','-')}-`+Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  }catch{return null;}
}
/** Lookup DATA only. No digest, message, preview, grant or executable target. */
export function freshConversationOriginalSelector(value:unknown):FreshConversationOriginalSelector|null {
  try {
    if(!value||typeof value!=='object'||![Object.prototype,null].includes(Object.getPrototypeOf(value)))return null;
    const fields=Object.getOwnPropertyDescriptors(value),keys=Reflect.ownKeys(fields);
    if(keys.length!==2||keys.some(k=>typeof k!=='string')||Object.values(fields).some(d=>!('value'in d)))return null;
    const work=fields.work_ref?.value;
    if(typeof work!=='string'||/^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}$/.exec(work)?.[0]!==work)return null;
    if(fields.operation_key){const key=fields.operation_key.value;
      return typeof key==='string'&&/^mmos-conversation-create-[0-9a-f]{40}$/.exec(key)?.[0]===key
        ?Object.freeze({work_ref:work,operation_key:key}):null;}
    return fields.reference?Object.freeze({work_ref:work,reference:decodeFreshConversationReference(fields.reference.value,work)}):null;
  }catch{return null;}
}
export function freshConversationTarget(value:unknown):string|null {
  const selector=freshConversationOriginalSelector(value);return selector?canonicalJson(selector):null;
}
export function parseFreshConversationTarget(value:unknown):FreshConversationOriginalSelector|null {
  if(typeof value!=='string'||value.length>2048)return null;
  try{const parsed=freshConversationOriginalSelector(JSON.parse(value));
    return parsed&&canonicalJson(parsed)===value?parsed:null;}catch{return null;}
}

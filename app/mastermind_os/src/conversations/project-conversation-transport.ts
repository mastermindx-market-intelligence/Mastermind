import {validateProjectConversationSelection} from './project-conversation-catalogue-contract';
import {decodeFreshConversationReference} from './fresh-conversation-reference';
import {decodeProjectExecutionReference} from './project-execution-history-contract';

export type ProjectConversationReadOperation='catalogue'|'read'|'fresh_references'|'fresh_read'|'execution_references'|'execution_read';
export interface ProjectConversationFixedReadTransport {
  request(operation:ProjectConversationReadOperation,arguments_:unknown,signal:AbortSignal):Promise<unknown>;
}
export function projectConversationArguments(operation:ProjectConversationReadOperation,value:unknown):unknown|null {
  try {
    if(!value||typeof value!=='object'||![Object.prototype,null].includes(Object.getPrototypeOf(value)))return null;
    const fields=Object.getOwnPropertyDescriptors(value);
    if(Reflect.ownKeys(fields).some(k=>typeof k!=='string')||Object.values(fields).some(d=>!('value'in d)))return null;
    const keys=Object.keys(fields).sort().join(','),work=fields.work_ref?.value;
    if(operation==='read')return validateProjectConversationSelection(value);
    if(operation==='fresh_read')return typeof work==='string'?decodeFreshConversationReference(value,work):null;
    if(operation==='execution_read')return typeof work==='string'?decodeProjectExecutionReference(value,work):null;
    if(operation!=='catalogue'&&operation!=='fresh_references'&&operation!=='execution_references')return null;
    if(typeof work!=='string'||(operation!=='fresh_references'
      ? /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(work)?.[0]!==work||work.length<5||work.length>67
      : /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}$/.exec(work)?.[0]!==work))return null;
    if(keys==='work_ref')return Object.freeze({work_ref:work});
    if(operation!=='catalogue'||keys!=='cursor,work_ref')return null;
    const cursor=fields.cursor.value;
    if(cursor!==null&&(typeof cursor!=='string'||/^[A-Za-z0-9_=-]{1,2048}$/.exec(cursor)?.[0]!==cursor))return null;
    return Object.freeze({work_ref:work,cursor});
  }catch{return null;}
}

export const PROJECT_CONVERSATION_READ_PATHS=Object.freeze({
  catalogue:'session/conversations',read:'session/conversation-read',
  fresh_references:'session/fresh-conversations',fresh_read:'session/fresh-conversation-read',
  execution_references:'session/project-executions',execution_read:'session/project-execution-read',
});

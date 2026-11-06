import {createProjectConversationCatalogueOwner} from './project-conversation-catalogue-owner';
import {createProjectConversationHistoryOwner,type ProjectConversationHistoryTransport,
  type ProjectConversationHistoryReaderSelection} from './project-conversation-history-owner';
export type ProjectConversationCatalogueReaderFactory=(selection:ProjectConversationHistoryReaderSelection)=>
  ReturnType<typeof createProjectConversationCatalogueReader>;
export function createProjectConversationCatalogueReader(input:{transport:ProjectConversationHistoryTransport;
  selection:ProjectConversationHistoryReaderSelection}) {
  const raw=input.transport,selected=input.selection,read=raw.projectConversations,request=read?.request;
  if(!read||!request)throw new Error('PROJECT_CONVERSATION_UNAVAILABLE');
  const work=()=>selected.currentWorkRef()===selected.workRef?selected.workRef:null;
  const contextOwner=createProjectConversationHistoryOwner({transport:raw,workRef:work,
    selectionGeneration:selected.selectionGeneration});
  // Context is identity only. Each fixed server READ authenticates separately.
  const current=()=>raw.projectConversations===read&&read.request===request&&work()!==null;
  const owner=createProjectConversationCatalogueOwner({workRef:work,selectionGeneration:selected.selectionGeneration,
    transport:{context:()=>{const c=contextOwner.owner.context();return current()&&c?{...c,workRef:selected.workRef}:null;},
      authGeneration:()=>raw.authGeneration(),available:()=>current()&&raw.available(),
      subscribe:listener=>contextOwner.subscribe(listener),refreshContext:()=>contextOwner.refresh(),
      catalogue:(args,signal)=>current()?request.call(read,'catalogue',args,signal):Promise.reject(new Error('PROJECT_CONVERSATION_UNAVAILABLE')),
      read:(args,signal)=>current()?request.call(read,'read',args,signal):Promise.reject(new Error('PROJECT_CONVERSATION_UNAVAILABLE')),
      freshReferences:(args,signal)=>current()?request.call(read,'fresh_references',args,signal):Promise.reject(new Error('PROJECT_CONVERSATION_UNAVAILABLE')),
      readFreshReference:(args,signal)=>current()?request.call(read,'fresh_read',args,signal):Promise.reject(new Error('PROJECT_CONVERSATION_UNAVAILABLE')),
      executionReferences:(args,signal)=>current()?request.call(read,'execution_references',args,signal):Promise.reject(new Error('PROJECT_CONVERSATION_UNAVAILABLE')),
      readExecutionReference:(args,signal)=>current()?request.call(read,'execution_read',args,signal):Promise.reject(new Error('PROJECT_CONVERSATION_UNAVAILABLE')),
    }});
  return Object.freeze({owner,dispose(){owner.dispose();contextOwner.dispose();}});
}
export function createProjectConversationCatalogueReaderFactory(transport:ProjectConversationHistoryTransport):
  ProjectConversationCatalogueReaderFactory|undefined {
  if(!transport.projectConversations||typeof transport.projectConversations.request!=='function'||
    typeof transport.historyContext!=='function'||typeof transport.projectReferences!=='function'||typeof transport.reply!=='function')return undefined;
  return selection=>createProjectConversationCatalogueReader({transport,selection});
}

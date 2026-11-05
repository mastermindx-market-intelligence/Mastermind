import { decodeProjectConversationCatalogue, decodeProjectConversationRead, validateProjectConversationSelection,
  type ProjectConversationCatalogue } from './project-conversation-catalogue-contract';

export interface ProjectConversationReadScope { readonly workRef:string; readonly principalScope:string; readonly generation:string; }
export interface ProjectConversationCatalogueTransport {
  /** Current authenticated identity/context only; never a catalogue/read grant.
   * Each fixed server operation independently authorizes the original scope. */
  context():ProjectConversationReadScope|null;
  authGeneration():number;
  available():boolean;
  subscribe(listener:()=>void):()=>void;
  refreshContext?():Promise<void>;
  catalogue(selection:{work_ref:string;cursor?:string},signal:AbortSignal):Promise<unknown>;
  read(selection:ReturnType<typeof validateProjectConversationSelection>,signal:AbortSignal):Promise<unknown>;
}

/** One selected-project acquisition owner. No effects on mount, no global
 * fanout, automatic body read, store, command port, Send or session lifecycle. */
export function createProjectConversationCatalogueOwner(input:{transport:ProjectConversationCatalogueTransport;
  workRef:()=>string|null;selectionGeneration:()=>string}) {
  const transport=input.transport;
  const methods={context:transport.context,auth:transport.authGeneration,available:transport.available,
    subscribe:transport.subscribe,refresh:transport.refreshContext,catalogue:transport.catalogue,read:transport.read};
  let retired=false,epoch=0,pageTicket=0;
  let members=new Map<string,ProjectConversationCatalogue['conversations'][number]>();
  let membershipContext:ReturnType<typeof capture>=null;
  const pending=new Set<AbortController>(),listeners=new Set<()=>void>();
  const fail=():never=>{throw new Error('PROJECT_CONVERSATION_UNAVAILABLE');};
  function sameMethods(){return transport.context===methods.context&&transport.authGeneration===methods.auth&&
    transport.available===methods.available&&transport.subscribe===methods.subscribe&&transport.refreshContext===methods.refresh&&
    transport.catalogue===methods.catalogue&&transport.read===methods.read;}
  function capture(){
    try{
      const context=methods.context.call(transport),auth=methods.auth.call(transport),selection=input.selectionGeneration();
      if(retired||!sameMethods()||!methods.available.call(transport)||!context||input.workRef()!==context.workRef||
        !Number.isSafeInteger(auth)||!context.generation||!/^[0-9a-f]{64}$/.test(context.principalScope))return null;
      return Object.freeze({...context,auth,selection,epoch});
    }catch{return null;}
  }
  function current(captured:ReturnType<typeof capture>){const now=capture();return !!now&&!!captured&&
    now.workRef===captured.workRef&&now.principalScope===captured.principalScope&&now.generation===captured.generation&&
    now.auth===captured.auth&&now.selection===captured.selection&&now.epoch===captured.epoch;}
  function invalidate(){epoch++;pageTicket++;members.clear();membershipContext=null;for(const c of pending)c.abort();pending.clear();for(const listener of listeners)listener();}
  const unsubscribe=methods.subscribe.call(transport,invalidate);
  async function bounded<T>(signal:AbortSignal,operation:(signal:AbortSignal)=>Promise<T>){
    if(signal.aborted)fail();const controller=new AbortController();pending.add(controller);
    const abort=()=>controller.abort();signal.addEventListener('abort',abort,{once:true});
    try{const value=await operation(controller.signal);if(controller.signal.aborted)fail();return value;}
    finally{pending.delete(controller);signal.removeEventListener('abort',abort);}
  }
  return Object.freeze({
    context:capture,
    current,
    subscribe(listener:()=>void){listeners.add(listener);return()=>{listeners.delete(listener);};},
    async refresh(){
      const work=input.workRef(),selection=input.selectionGeneration(),auth=methods.auth.call(transport);
      invalidate();
      if(retired||!sameMethods()||!methods.available.call(transport)||!work)fail();
      if(methods.refresh)await methods.refresh.call(transport);
      if(retired||!sameMethods()||input.workRef()!==work||input.selectionGeneration()!==selection||methods.auth.call(transport)!==auth||!capture())fail();
    },
    async catalogue(args:{workRef:string;cursor?:string;signal:AbortSignal}){
      const captured=capture(),ticket=++pageTicket;members.clear();membershipContext=null;
      if(!captured||args.workRef!==captured.workRef)fail();
      const page=await bounded(args.signal,async signal=>decodeProjectConversationCatalogue(
        await methods.catalogue.call(transport,{work_ref:args.workRef,...(args.cursor?{cursor:args.cursor}:{})},signal),args.workRef));
      if(ticket!==pageTicket||!current(captured))fail();
      members=new Map(page.conversations.map(row=>[row.conversation_ref,row]));membershipContext=captured;return page;
    },
    async read(selection:unknown,signal:AbortSignal){
      const requested=validateProjectConversationSelection(selection),captured=membershipContext;
      const row=members.get(requested.conversation_ref),ticket=pageTicket;
      if(!captured||!current(captured)||requested.work_ref!==captured.workRef||!row||row.revision!==requested.revision||
        JSON.stringify(row.requests)!==JSON.stringify(requested.requests))fail();
      const value=await bounded(signal,async child=>decodeProjectConversationRead(await methods.read.call(transport,requested,child),
        {workRef:requested.work_ref,conversationRef:requested.conversation_ref,revision:requested.revision,requests:requested.requests}));
      if(!current(captured)||ticket!==pageTicket||members.get(requested.conversation_ref)!==row)fail();return value;
    },
    dispose(){if(retired)return;retired=true;invalidate();unsubscribe();listeners.clear();},
  });
}
export type ProjectConversationCatalogueOwner=ReturnType<typeof createProjectConversationCatalogueOwner>;

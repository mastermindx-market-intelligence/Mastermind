import { decodeProjectConversationCatalogue, decodeProjectConversationRead, validateProjectConversationSelection,
  type ProjectConversationCatalogue } from './project-conversation-catalogue-contract';
import {decodeProjectExecutionCatalogue,decodeProjectExecutionReference,decodeProjectExecutionWindow,
  type ProjectExecutionHistoryCatalogue,type ProjectExecutionReference,type ProjectExecutionHistoryWindow} from './project-execution-history-contract';
import {decodeFreshConversationHistoryCatalogue as decodeFreshConversationCatalogue,decodeFreshConversationReference,
  decodeFreshConversationHistoryWindow as decodeFreshConversationWindow,freshConversationInitialDigest,freshConversationNextPage,
  decodeFreshConversationInputFragment,sameFreshConversationInput,type FreshNativeInput,type FreshNativeResult,
  type FreshConversationHistoryCatalogue as FreshConversationCatalogue,type FreshConversationReadRequest,
  type FreshConversationHistoryWindow as FreshConversationWindow} from './fresh-conversation-reference';
import {sha256Hex,canonicalJson} from '../orchestration/operation-key';
import {decodeFreshNativeContent,decodeFreshNativeAnswer,type FreshNativeContent,type FreshNativeAnswer} from './fresh-native-content';

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
  /** Separate actual S34 READ owner. The identity context's old reply booleans
   * authorize neither callback. Absence remains a partial source population. */
  freshReferences?(selection:{work_ref:string},signal:AbortSignal):Promise<unknown>;
  readFreshReference?(reference:FreshConversationReadRequest,signal:AbortSignal):Promise<unknown>;
  executionReferences?(selection:{work_ref:string},signal:AbortSignal):Promise<unknown>;
  readExecutionReference?(reference:ProjectExecutionReference,signal:AbortSignal):Promise<unknown>;
}

/** One selected-project acquisition owner. No effects on mount, no global
 * fanout, automatic body read, store, command port, Send or session lifecycle. */
export function createProjectConversationCatalogueOwner(input:{transport:ProjectConversationCatalogueTransport;
  workRef:()=>string|null;selectionGeneration:()=>string}) {
  const transport=input.transport;
  const methods={context:transport.context,auth:transport.authGeneration,available:transport.available,
    subscribe:transport.subscribe,refresh:transport.refreshContext,catalogue:transport.catalogue,read:transport.read,
    freshReferences:transport.freshReferences,readFreshReference:transport.readFreshReference,
    executionReferences:transport.executionReferences,readExecutionReference:transport.readExecutionReference};
  let retired=false,epoch=0,pageTicket=0;
  let members=new Map<string,ProjectConversationCatalogue['conversations'][number]>();
  let membershipContext:ReturnType<typeof capture>=null;
  let freshTicket=0,freshContext:ReturnType<typeof capture>=null;
  let freshMembers=new Map<string,FreshConversationCatalogue['entries'][number]>();
  let freshReadEpoch=0,freshHistoryTicket=0,freshInputTicket=0;
  let lastFreshRead:{window:FreshConversationWindow;context:NonNullable<ReturnType<typeof capture>>;
    pageTicket:number;nextBefore:number|null;row:FreshConversationCatalogue['entries'][number];historyPage?:FreshConversationWindow}|null=null;
  let executionTicket=0,executionReadEpoch=0,executionContext:ReturnType<typeof capture>=null;
  let executionMembers=new Map<string,ProjectExecutionHistoryCatalogue['entries'][number]>();
  let lastExecutionRead:{window:ProjectExecutionHistoryWindow;context:NonNullable<ReturnType<typeof capture>>;
    pageTicket:number;row:ProjectExecutionHistoryCatalogue['entries'][number]}|null=null;
  const pending=new Set<AbortController>(),listeners=new Set<()=>void>();
  function fail():never{throw new Error('PROJECT_CONVERSATION_UNAVAILABLE');}
  function sameMethods(){return transport.context===methods.context&&transport.authGeneration===methods.auth&&
    transport.available===methods.available&&transport.subscribe===methods.subscribe&&transport.refreshContext===methods.refresh&&
    transport.catalogue===methods.catalogue&&transport.read===methods.read&&
    transport.freshReferences===methods.freshReferences&&transport.readFreshReference===methods.readFreshReference&&
    transport.executionReferences===methods.executionReferences&&transport.readExecutionReference===methods.readExecutionReference;}
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
  function invalidateFreshRead(){freshReadEpoch++;lastFreshRead=null;for(const listener of listeners)listener();}
  function invalidate(){epoch++;pageTicket++;freshTicket++;members.clear();membershipContext=null;freshMembers.clear();freshContext=null;
    freshReadEpoch++;lastFreshRead=null;executionTicket++;executionReadEpoch++;executionMembers.clear();executionContext=null;lastExecutionRead=null;
    for(const c of pending)c.abort();pending.clear();for(const listener of listeners)listener();}
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
    /** Data-currentness only. Neither an acknowledgement nor a write grant. */
    currentFresh(window:FreshConversationWindow){const value=lastFreshRead;return !!value&&value.window===window&&
      current(value.context)&&value.pageTicket===freshTicket&&freshMembers.get(window.reference.root_job_id)===value.row;},
    invalidateFreshRead,
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
    async freshCatalogue(args:{workRef:string;signal:AbortSignal}){
      const captured=capture(),ticket=++freshTicket;freshMembers.clear();freshContext=null;freshReadEpoch++;lastFreshRead=null;
      if(!captured||args.workRef!==captured.workRef||!methods.freshReferences||!methods.readFreshReference)fail();
      const page=await bounded(args.signal,async signal=>decodeFreshConversationCatalogue(
        await methods.freshReferences!.call(transport,{work_ref:args.workRef},signal),args.workRef));
      if(ticket!==freshTicket||!current(captured))fail();
      freshMembers=new Map(page.entries.map(row=>[row.reference.root_job_id,row]));freshContext=captured;return page;
    },
    async readFresh(reference:unknown,signal:AbortSignal){
      const captured=freshContext;
      if(!captured||!current(captured)||!methods.readFreshReference)fail();
      const requested=decodeFreshConversationReference(reference,captured.workRef),row=freshMembers.get(requested.root_job_id),ticket=freshTicket;
      if(!row||JSON.stringify(row.reference)!==JSON.stringify(requested))fail();
      const readEpoch=++freshReadEpoch;lastFreshRead=null;
      const result=await bounded(signal,async child=>decodeFreshConversationWindow(
        await methods.readFreshReference!.call(transport,requested,child),requested));
      if(!current(captured)||ticket!==freshTicket||readEpoch!==freshReadEpoch||freshMembers.get(requested.root_job_id)!==row||!sameFreshConversationInput(result,row))fail();
      lastFreshRead={window:result,context:captured,pageTicket:ticket,nextBefore:freshConversationNextPage(result),row};return result;
    },
    /** Older display pages retain the issued initial witness. They grant no
     * continuation and cannot outlive its original/auth/selection generation. */
    async readFreshOlder(window:FreshConversationWindow,before:number,signal:AbortSignal){
      const issued=lastFreshRead,readEpoch=freshReadEpoch,ticket=++freshHistoryTicket;
      if(!issued||issued.window!==window||!current(issued.context)||!methods.readFreshReference||
        issued.pageTicket!==freshTicket||freshMembers.get(window.reference.root_job_id)!==issued.row||
        !Number.isSafeInteger(before)||before<1||issued.nextBefore!==before)fail();
      const requested={...window.reference,before_event_id:before};
      const result=await bounded(signal,async child=>decodeFreshConversationWindow(
        await methods.readFreshReference!.call(transport,requested,child),requested));
      if(lastFreshRead!==issued||readEpoch!==freshReadEpoch||ticket!==freshHistoryTicket||
        !current(issued.context)||issued.pageTicket!==freshTicket||issued.nextBefore!==before||
        freshMembers.get(window.reference.root_job_id)!==issued.row||!sameFreshConversationInput(result,window)||
        freshConversationInitialDigest(result)!==freshConversationInitialDigest(window)||
        JSON.stringify(result.locator)!==JSON.stringify(window.locator)||
        JSON.stringify(result.initial_consumption)!==JSON.stringify(window.initial_consumption))fail();
      issued.nextBefore=freshConversationNextPage(result);issued.historyPage=result;return result;
    },
    /** Reconstruct only an input already witnessed in this exact displayed
     * history page. Every range uses the incumbent READ and auth lifetime. */
    async readFreshInput(window:FreshConversationWindow,input:FreshNativeInput,turnKey:string|undefined,signal:AbortSignal){
      const issued=lastFreshRead,readEpoch=freshReadEpoch,ticket=++freshInputTicket;
      const page=issued?.historyPage??window;
      function check(){
        if(!issued||issued.window!==window||lastFreshRead!==issued||readEpoch!==freshReadEpoch||
          ticket!==freshInputTicket||!current(issued.context)||issued.pageTicket!==freshTicket||
          freshMembers.get(window.reference.root_job_id)!==issued.row||!methods.readFreshReference||
          (issued.historyPage??window)!==page||window.schema!=='mastermind.fresh_conversation_window.v3'||signal.aborted)fail();
        if(turnKey===undefined){if(window.initial_input!==input)fail();}
        else if(page.schema!=='mastermind.fresh_conversation_window.v3'||
          !page.turns.some(turn=>turn.turn_key===turnKey&&turn.input===input))fail();
      }
      check();
      if(input.complete)return input.preview;
      let assembled='',offset=0;
      for(let count=0;count<34;count++){
        check();
        const fragment={kind:turnKey===undefined?'initial_input' as const:'turn_input' as const,
          ...(turnKey===undefined?{}:{turn_key:turnKey}),source_event_id:input.source_event_id,
          source_event_sha256:input.source_event_sha256,sha256:input.sha256,offset_utf8:offset};
        const requested={...window.reference,fragment};
        const part=await bounded(signal,async child=>decodeFreshConversationInputFragment(
          await methods.readFreshReference!.call(transport,requested,child),requested));
        check();if(part.utf8_bytes!==input.utf8_bytes)fail();
        assembled+=part.text;
        if(part.next_offset_utf8===null){
          if(new TextEncoder().encode(assembled).length!==input.utf8_bytes||sha256Hex(assembled)!==input.sha256)fail();
          return assembled;
        }
        offset=part.next_offset_utf8;
      }
      fail();
    },
    /** Read one issued result via the same original READ ticket. No shared
     * transcript store, new Session, automatic replay or modifying carrier. */
    async readFreshResult(window:FreshConversationWindow,result:FreshNativeResult,signal:AbortSignal):Promise<FreshNativeAnswer>{
      const issued=lastFreshRead,readEpoch=freshReadEpoch,page=issued?.historyPage??window;
      function check(){
        if(!issued||issued.window!==window||lastFreshRead!==issued||readEpoch!==freshReadEpoch||
          !current(issued.context)||issued.pageTicket!==freshTicket||
          freshMembers.get(window.reference.root_job_id)!==issued.row||!methods.readFreshReference||
          (issued.historyPage??window)!==page||window.schema!=='mastermind.fresh_conversation_window.v3'||signal.aborted)fail();
        if(window.initial_result!==result&&(page.schema!=='mastermind.fresh_conversation_window.v3'||
          !page.turns.some(turn=>turn.result===result)))fail();
      }
      check();
      let first:FreshNativeContent|undefined,offset=0,digest:string|null=null,bytes:Uint8Array|undefined;
      for(let count=0;count<1024;count++){
        check();
        const requested:FreshConversationReadRequest={...window.reference,content:{native_ref:result.reference,offset_bytes:offset,expected_sha256:digest}};
        const content:FreshNativeContent=await bounded(signal,async child=>decodeFreshNativeContent(
          await methods.readFreshReference!.call(transport,requested,child),requested));
        check();
        if(!first){
          first=content;
          if(content.part===null)return Object.freeze({state:'NO_ANSWER',messages:Object.freeze([]),records:Object.freeze([])});
          digest=content.part.sha256;bytes=new Uint8Array(content.part.total_bytes);
        }
        if(content.part===null||!first.part||!bytes||canonicalJson(content.metadata)!==canonicalJson(first.metadata)||
          content.part.sha256!==digest||content.part.total_bytes!==bytes.length)fail();
        bytes.set(content.part.bytes,offset);
        if(content.part.next_offset_bytes===null){check();return decodeFreshNativeAnswer(bytes,first);}
        offset=content.part.next_offset_bytes;
      }
      fail();
    },
    currentExecution(window:ProjectExecutionHistoryWindow){const value=lastExecutionRead;return !!value&&value.window===window&&
      current(value.context)&&value.pageTicket===executionTicket&&executionMembers.get(window.reference.root_job_id)===value.row;},
    async executionCatalogue(args:{workRef:string;signal:AbortSignal}){
      const captured=capture(),ticket=++executionTicket;executionMembers.clear();executionContext=null;executionReadEpoch++;lastExecutionRead=null;
      if(!captured||args.workRef!==captured.workRef||!methods.executionReferences||!methods.readExecutionReference)fail();
      const page=await bounded(args.signal,async signal=>decodeProjectExecutionCatalogue(
        await methods.executionReferences!.call(transport,{work_ref:args.workRef},signal),args.workRef));
      if(ticket!==executionTicket||!current(captured))fail();
      executionMembers=new Map(page.entries.map(row=>[row.reference.root_job_id,row]));executionContext=captured;return page;
    },
    async readExecution(reference:unknown,signal:AbortSignal){
      const captured=executionContext;
      if(!captured||!current(captured)||!methods.readExecutionReference)fail();
      const requested=decodeProjectExecutionReference(reference,captured.workRef),row=executionMembers.get(requested.root_job_id),ticket=executionTicket;
      if(!row||JSON.stringify(row.reference)!==JSON.stringify(requested))fail();
      const readEpoch=++executionReadEpoch;lastExecutionRead=null;
      const result=await bounded(signal,async child=>decodeProjectExecutionWindow(
        await methods.readExecutionReference!.call(transport,requested,child),requested));
      if(!current(captured)||ticket!==executionTicket||readEpoch!==executionReadEpoch||
        executionMembers.get(requested.root_job_id)!==row||result.goal!==row.goal)fail();
      lastExecutionRead={window:result,context:captured,pageTicket:ticket,row};return result;
    },
    dispose(){if(retired)return;retired=true;invalidate();unsubscribe();listeners.clear();},
  });
}
export type ProjectConversationCatalogueOwner=ReturnType<typeof createProjectConversationCatalogueOwner>;

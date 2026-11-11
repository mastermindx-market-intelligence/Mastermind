import {useCallback,useRef,useState} from "react";
import type {OwnerContext} from "../../orchestration/operation-controller";
import {freshConversationTarget,parseFreshConversationTarget,type FreshConversationOriginalSelector} from "../../orchestration/fresh-conversation-target";
import type {FreshConversationDraftStateProps} from "./useFreshConversationDraftState";
import {decodeFreshConversationTurnResult,validateFreshConversationTurnRequest} from "./fresh-conversation-turn";

type Props=FreshConversationDraftStateProps;
type Actor={host:NonNullable<Props["host"]>;epoch:number;generation:number;owner:OwnerContext;
  auth:unknown;getState:unknown;generationMethod:unknown;transport:unknown;request:unknown;
  ownerGetter:Props["getExecutiveOwner"];epochGetter:Props["currentAuthRevision"]};
/** Opaque local text association, never an operation receipt or authority. */
export type FreshConversationTurnDraftCapture=Readonly<object>;
type Submission={token:FreshConversationTurnDraftCapture;key:string;text:string;author:Actor};
type Record={actor:Actor;selection:FreshConversationOriginalSelector;target:string;text:string;held:boolean;submission:Submission|null};
export interface FreshConversationTurnDraftState {
  readonly selection:FreshConversationOriginalSelector|null;
  readonly message:string;
  readonly draftOwner:OwnerContext|null;
  selectOriginal:(selection:FreshConversationOriginalSelector)=>boolean;
  onMessageChange:(message:string)=>void;
  hasUnsentDraft:()=>boolean;
  invalidateAuth:(preserve:boolean)=>void;
  discard:()=>void;
  readonly submittedTurnKey:string|null;
  captureSubmission:(turnKey:string,expectedMessage:string)=>FreshConversationTurnDraftCapture|null;
  submissionFor:(turnKey:string)=>FreshConversationTurnDraftCapture|null;
  /** Only a qualified original turn_read frame for the captured key can settle text. */
  settleSubmission:(capture:FreshConversationTurnDraftCapture,rawTurnRead:unknown)=>boolean;
}
function capture(p:Props):Actor|null {
  try{
    const host=p.host;if(!host||typeof window==="undefined"||window.MastermindMissionHost!==host||
      !Number.isSafeInteger(p.authRevision)||p.currentAuthRevision()!==p.authRevision)return null;
    const generation=host.invalidationGeneration?.(),auth=host.auth,transport=host.freshConversation;
    if(typeof generation!=="number"||!Number.isSafeInteger(generation)||generation<0||!auth||typeof auth.getState!=="function"||
      !transport||typeof transport.request!=="function")return null;
    const owner=p.getExecutiveOwner();
    if(!owner||typeof owner.principalScope!=="string"||!owner.principalScope||typeof owner.generation!=="string"||!owner.generation)return null;
    // The Executive getter owns E identity. Workspace sign-in is not a draft
    // identity or command permission; no Workspace status is promoted here.
    return {host,epoch:p.authRevision,generation,owner:Object.freeze({principalScope:owner.principalScope,generation:owner.generation}),auth,getState:auth.getState,
      generationMethod:host.invalidationGeneration,transport,request:transport.request,ownerGetter:p.getExecutiveOwner,epochGetter:p.currentAuthRevision};
  }catch{return null;}
}
function same(a:Actor|null,b:Actor|null){
  return !!a&&!!b&&a.host===b.host&&a.epoch===b.epoch&&a.generation===b.generation&&
    a.owner.principalScope===b.owner.principalScope&&a.owner.generation===b.owner.generation&&a.auth===b.auth&&
    a.getState===b.getState&&a.generationMethod===b.generationMethod&&a.transport===b.transport&&a.request===b.request&&
    a.ownerGetter===b.ownerGetter&&a.epochGetter===b.epochGetter;
}
function detached(value:FreshConversationOriginalSelector){
  const target=freshConversationTarget(value);if(!target)return null;
  const selection=parseFreshConversationTarget(target);if(!selection)return null;
  if("reference"in selection)Object.freeze(selection.reference);
  return {selection:Object.freeze(selection),target};
}
/** One App-lifetime ephemeral follow-up slot. No URL, effect lifecycle,
 * persistence, key mint, automatic source read or reference reinterpretation. */
export function useFreshConversationTurnDraftState(props:Props):FreshConversationTurnDraftState {
  const latest=useRef(props);latest.current=props;
  const record=useRef<Record|null>(null);
  const [,render]=useState(0);
  const actor=capture(props);
  const renderedTarget=record.current?.target??null;
  const update=(next:Record|null)=>{record.current=next;render(n=>n+1);};
  const visible=()=>{const value=record.current;return value&&!value.held&&same(value.actor,capture(latest.current))?value:null;};
  // These callbacks keep their render's actor/target. A later render cannot
  // re-authorize an older message/discard callback for another original.
  const selectOriginal=(value:FreshConversationOriginalSelector)=>{
    if(!actor||!same(actor,capture(latest.current)))return false;
    const selected=detached(value);if(!selected)return false;
    const old=record.current;
    if(old?.held)return false;
    if(old&&same(old.actor,actor)&&old.target===selected.target)return true;
    if(old?.text.length)return false;
    update({...selected,actor,text:"",held:false,submission:null});return true;
  };
  const onMessageChange=(message:string)=>{
    const old=visible();if(typeof message!=="string"||!old||old.target!==renderedTarget||!same(old.actor,actor))return;
    if(message!==old.text)update({...old,text:message,submission:null});
  };
  const discard=()=>{
    const old=visible();if(!old||old.target!==renderedTarget||!same(old.actor,actor))return;
    update(null);
  };
  const hasUnsentDraft=useCallback(()=>{
    const value=record.current;return !!value&&!value.held&&same(value.actor,capture(latest.current))&&value.text.length>0;
  },[]);
  const invalidateAuth=useCallback((preserve:boolean)=>{
    const old=record.current;
    record.current=preserve&&old?.text.length?{...old,held:true}:null;
    render(n=>n+1);
    // Quarantine alone never restores or exposes a body. S35's genuine native
    // boundary + E-author + exact original/facet closure is a separate join.
  },[]);
  const submissionFor=(turnKey:string)=>{
    const value=visible(),submission=value?.submission;
    return submission&&submission.key===turnKey&&submission.text===value!.text&&
      submission.author.host===value!.actor.host&&submission.author.owner.principalScope===value!.actor.owner.principalScope?submission.token:null;
  };
  const captureSubmission=(turnKey:string,expectedMessage:string)=>{
    const value=visible();
    if(!value||value.target!==renderedTarget||!same(value.actor,actor)||value.text!==expectedMessage||!value.text.length||
      !/^mmos-conversation-turn-[0-9a-f]{40}$/.test(turnKey))return null;
    const existing=submissionFor(turnKey);if(existing)return existing;
    const token=Object.freeze({});
    record.current={...value,submission:{token,key:turnKey,text:value.text,author:value.actor}};
    return token;
  };
  const settleSubmission=(token:FreshConversationTurnDraftCapture,rawTurnRead:unknown)=>{
    const value=visible(),submission=value?.submission;
    if(!value||!submission||submission.token!==token||submissionFor(submission.key)!==token)return false;
    const request=validateFreshConversationTurnRequest({...value.selection,turn_key:submission.key},"turn_read");
    const decoded=request?decodeFreshConversationTurnResult(rawTurnRead,"turn_read",request):null;
    if(!decoded?.ok||decoded.data.state!=="RECORDED"||decoded.data.effect!=="COMMITTED"||!decoded.data.result||
      record.current!==value||visible()!==value||submissionFor(submission.key)!==token)return false;
    update({...value,text:"",submission:null});return true;
  };
  return {get selection(){return visible()?.selection??null;},get message(){return visible()?.text??"";},
    get draftOwner(){const value=visible();return value?{...value.actor.owner}:null;},
    get submittedTurnKey(){const value=visible();return value?.submission&&submissionFor(value.submission.key)?value.submission.key:null;},
    selectOriginal,onMessageChange,hasUnsentDraft,invalidateAuth,discard,captureSubmission,submissionFor,settleSubmission};
}

import {useEffect,useLayoutEffect,useMemo} from "react";
import {freshConversationTarget} from "../../orchestration/fresh-conversation-target";
import type {OwnerContext} from "../../orchestration/operation-controller";
import type {FreshConversationWindow} from "../fresh-conversation-reference";
import type {FreshConversationOriginalRead} from "./fresh-conversation-attended-binding";
import type {FreshConversationTurnConsumption} from "./fresh-conversation-turn";
import {useFreshConversationContinuation,type FreshConversationContinuationProps as HookProps} from "./useFreshConversationContinuation";
import type {FreshConversationTurnDraftState} from "./useFreshConversationTurnDraftState";

export type FreshConversationContinuationEntry=
  |{kind:"initial";read:FreshConversationOriginalRead;initialConsumption?:FreshConversationTurnConsumption|null}
  |{kind:"reference";window:FreshConversationWindow;current:()=>boolean};
export interface FreshConversationContinuationProps extends Omit<HookProps,"read"|"selection"|"initialConsumption"|"message"|"draftOwner"|"onMessageChange">{
  entry:FreshConversationContinuationEntry;
  message?:string;
  draftOwner?:OwnerContext|null;
  onMessageChange?:(message:string)=>void;
  /** Existing App-lifetime owner. Association happens after commit only. */
  turnDraft?:Pick<FreshConversationTurnDraftState,"selection"|"message"|"draftOwner"|"selectOriginal"|"onMessageChange">&
    Partial<Pick<FreshConversationTurnDraftState,"captureSubmission"|"submissionFor"|"settleSubmission"|"submittedTurnKey">>;
  /** Stable, owner-guarded caller callback into its incumbent UI hold. False
   * withdraws this view's report; it never clears a durable original pointer. */
  onUnresolvedChange:(held:boolean)=>void;
  /** After-commit notification of the actual issued witness; never a new read. */
  onReadCurrent?:(read:FreshConversationOriginalRead|null)=>void;
}

/** Stable adapter around already issued reads. It does not mint a read ticket,
 * fetch a body, invent an operation key, or own private draft text. */
export function FreshConversationContinuation(props:FreshConversationContinuationProps){
  const {entry,onUnresolvedChange}=props;
  const source=entry.kind==="initial"?entry.read:entry.window;
  const witness=entry.kind==="reference"?entry.current:null;
  const read=useMemo<FreshConversationOriginalRead|null>(()=>{
    if(entry.kind==="initial")return entry.read;
    const {window,current}=entry,locator=window.locator;
    if(!window.initial_result||!locator.job_id||!locator.attempt_id)return null;
    return {selection:{work_ref:window.reference.work_ref,reference:window.reference},
      result:window.initial_result,locator:{work_ref:locator.work_ref,root_job_id:locator.root_job_id,
        job_id:locator.job_id,attempt_id:locator.attempt_id},current};
  },[entry.kind,source,witness]);
  const selection=entry.kind==="initial"?entry.read.selection:
    {work_ref:entry.window.reference.work_ref,reference:entry.window.reference};
  const sourceReadOnly=entry.kind==="reference"&&(entry.window.state!=="RETAINED"||!entry.window.epoch||entry.window.turns.length>0);
  const readIsCurrent=props.active&&read?.current()===true;
  useLayoutEffect(()=>{
    props.onReadCurrent?.(props.active&&read?.current()===true?read:null);
    return()=>{props.onReadCurrent?.(null);};
  },[props.onReadCurrent,read,props.active,readIsCurrent]);
  useLayoutEffect(()=>{
    if(props.active&&!props.readOnly&&!sourceReadOnly&&read?.current()===true)props.turnDraft?.selectOriginal(read.selection);
  });
  const matchesDraft=()=>!!read&&read.current()===true&&!!props.turnDraft&&
    freshConversationTarget(props.turnDraft.selection)===freshConversationTarget(read.selection);
  const associated=matchesDraft();
  const view=useFreshConversationContinuation({...props,read,selection,
    draftSubmission:associated&&props.turnDraft?.captureSubmission&&props.turnDraft.submissionFor&&props.turnDraft.settleSubmission
      ?{captureSubmission:props.turnDraft.captureSubmission,submissionFor:props.turnDraft.submissionFor,
        settleSubmission:props.turnDraft.settleSubmission,get submittedTurnKey(){return props.turnDraft?.submittedTurnKey??null;}}:props.draftSubmission,
    message:props.turnDraft?(associated?props.turnDraft.message:""):props.message??"",
    draftOwner:props.turnDraft?(associated?props.turnDraft.draftOwner:null):props.draftOwner??null,
    onMessageChange:message=>{if(props.turnDraft){if(matchesDraft())props.turnDraft.onMessageChange(message);}else props.onMessageChange?.(message);},
    initialConsumption:entry.kind==="reference"?entry.window.initial_consumption:entry.initialConsumption,
    readOnly:props.readOnly||sourceReadOnly});
  useEffect(()=>{onUnresolvedChange(view.hasUnresolvedOriginal);},[onUnresolvedChange,view.hasUnresolvedOriginal]);
  useEffect(()=>()=>{onUnresolvedChange(false);},[onUnresolvedChange]);
  // The existing recorded reader renders its own initial and later turns.
  // Only a genuine unresolved original contributes recovery controls here.
  return sourceReadOnly&&!view.hasUnresolvedOriginal?null:view.panel;
}

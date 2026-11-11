/** Explicit local insertion through the existing conversation draft owner.
 * No source publication, session creation, send or persistent draft is added. */
import {appendDraftSource,type ConversationDrafts,type DraftSource} from "../conversations/drafts";
import type {ProjectionContext} from "../meta-ceo/projection";
import {decodeStandingInstructions,type StandingInstructionSelection} from "./standing-instructions";
export function instructionDraftSource(value:unknown,project:StandingInstructionSelection,instruction_ref:string):DraftSource|null {
 const body=decodeStandingInstructions(value,project);
 if(body?.availability!=="AVAILABLE")return null;
 const row=body.instructions.find(item=>item.instruction_ref===instruction_ref);if(!row)return null;
 return {identity:JSON.stringify([project.work_ref,row.instruction_ref,row.revision,body.source.commit,body.source.content_sha256]),
  excerpt:row.text,label:`${row.instruction_ref} · ${body.source.path}@${body.source.commit}`};
}
export function appendInstructionToConversationDraft(state:ConversationDrafts,context:ProjectionContext,expectedRevision:number,value:unknown,instruction_ref:string):ConversationDrafts {
 if(!context.selection||context.authGeneration!==state.authGeneration)return state;
 const source=instructionDraftSource(value,{work_ref:context.selection.workRef},instruction_ref);
 return source?appendDraftSource(state,context,expectedRevision,source):state;
}

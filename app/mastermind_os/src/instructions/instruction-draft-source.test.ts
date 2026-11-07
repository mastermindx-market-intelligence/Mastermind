// @vitest-environment node
import {describe,it,expect} from "vitest";
import source from "./fixtures/standing-instructions-owner.json";
import {appendInstructionToConversationDraft,instructionDraftSource} from "./instruction-draft-source";
import {emptyDrafts,writeDraft,readDraft,readDraftRevision,readDraftInsertion,undoDraftSource} from "../conversations/drafts";
import type {ProjectionContext} from "../meta-ceo/projection";
const context:ProjectionContext={authGeneration:3,selection:{workRef:"WS:ONE",rootJobId:"JOB-1"},sessionRef:"existing-session",bindingGeneration:1,revisions:{mission:null,programs:null,conversation:null,result:null}};
const ref="INS:DAILY-ONE";
describe("instruction change through the original unsent draft owner",()=>{
 it("preserves the entire original draft and quotes the exact current instruction once",()=>{
  const before=writeDraft(emptyDrafts(3),context,"Original private question.\n第二行\n ");
  const after=appendInstructionToConversationDraft(before,context,1,source.cases.supplied,ref);
  expect(readDraft(after,context)).toBe(`${readDraft(before,context)}\n\n“复查项目 🎯”\nSource: ${ref} · ${source.cases.supplied.source.path}@${source.cases.supplied.source.commit}`);
  expect(readDraft(before,context)).toBe("Original private question.\n第二行\n ");
  expect(appendInstructionToConversationDraft(after,context,2,source.cases.supplied,ref)).toBe(after);
  expect(readDraftRevision(after,context)).toBe(2);
 });
 it("uses actual conditional Undo and never erases intervening typing",()=>{
  const before=writeDraft(emptyDrafts(3),context,"Exact previous text\n "),after=appendInstructionToConversationDraft(before,context,1,source.cases.supplied,ref),insertion=readDraftInsertion(after,context)!;
  expect(readDraft(undoDraftSource(after,context,2,insertion.source.identity),context)).toBe(readDraft(before,context));
  const edited=writeDraft(after,context,"My intervening change");expect(undoDraftSource(edited,context,3,insertion.source.identity)).toBe(edited);
 });
 it("refuses a foreign project, stale auth or revision, absent row and unavailable content",()=>{
  const before=writeDraft(emptyDrafts(3),context,"Keep my current draft");
  for(const changed of [{...context,selection:{workRef:"WS:OTHER",rootJobId:"JOB-2"}},{...context,authGeneration:4},{...context,selection:null}])expect(appendInstructionToConversationDraft(before,changed,1,source.cases.supplied,ref)).toBe(before);
  expect(appendInstructionToConversationDraft(before,context,0,source.cases.supplied,ref)).toBe(before);
  for(const body of [source.cases.empty,source.cases.absent,source.cases.unavailable])expect(appendInstructionToConversationDraft(before,context,1,body,ref)).toBe(before);
  expect(appendInstructionToConversationDraft(before,context,1,source.cases.supplied,"INS:OTHER")).toBe(before);
 });
 it("retains source identity but grants no send, publication or instruction state",()=>{
  const value=instructionDraftSource(source.cases.supplied,{work_ref:"WS:ONE"},ref)!;
  expect(Object.keys(value).sort()).toEqual(["excerpt","identity","label"]);expect(value.identity).toContain(source.cases.supplied.instructions[0].revision);
  expect(instructionDraftSource({...source.cases.supplied,permission:{pause:true}},{work_ref:"WS:ONE"},ref)).toBeNull();
 });
});

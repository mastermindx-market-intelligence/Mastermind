/** Native test composition only: no provider, installed account or company grant. */
import {Context} from "@deepseek-ai/cordis";
import SessionStore, {Session, SessionId} from "@deepseek-ai/dsh-session";
import AgentRegistry from "@deepseek-ai/dsh-agent";
import * as JsonlPersistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import TypertGatewayService from "@deepseek-ai/dsh-api-gateway";
import * as Connection from "@deepseek-ai/dsh-client-connection";
import {createUserMessage, createMessage} from "@deepseek-ai/dsh-llm";
import {mkdtemp, readdir, readFile, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {createHash} from "node:crypto";
import {createSessionTestController} from "mmx-native-test-remote";
import {provideBrowserCredentials} from "mmx-native-browser-credentials";
import {DONOR_SHA} from "./src/protocol";
import {attachExecutiveReadPort, inject, type InstalledNativeReadAssociation, type InstalledNativeReadSource} from "./src/executive-read-port";
import type {Duplex} from "node:stream";

export async function attachNativeTestPort(ctx:Context,port:Duplex,source:InstalledNativeReadSource) {
  let attached!:ReturnType<typeof attachExecutiveReadPort>;
  await ctx.plugin({inject,apply(child:Context){attached=attachExecutiveReadPort(child,port,source);}});
  return attached;
}

export const canonical = (value: unknown): string => JSON.stringify(value, (_key, item) =>
  item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
export const digest = (value: unknown): string => createHash("sha256").update(canonical(value)).digest("hex");
export const testAssociation = (extra = {}): InstalledNativeReadAssociation => ({
  schema: "mastermind.dsh.native_read_association.v1", work_ref: "WS:Company-native-read",
  root_job_id: "JOB-001", native_session_id: "company-bound-original",
  owner_principal_scope: "1".repeat(64), composition_sha256: "2".repeat(64),
  native_package_sha256: "3".repeat(64), donor_sha: DONOR_SHA, ...extra,
});
export function request(association = testAssociation(), extra = {}) {
  const now = Math.floor(Date.now() / 1000);
  return {schema: "mastermind.dsh.native_read.v1", request_id: "4".repeat(64),
    association_sha256: digest(association),
    principal: {principal_scope: association.owner_principal_scope, issued_at: now - 1, expires_at: now + 120},
    read: {kind: "snapshot"}, ...extra};
}
export async function disk(root: string): Promise<Record<string,string>> {
  const files: Record<string,string> = {};
  async function walk(path: string) {
    for (const entry of await readdir(path, {withFileTypes:true})) {
      const child = join(path, entry.name);
      if (entry.isDirectory()) await walk(child);
      else if (entry.isFile()) files[child.slice(root.length+1)] =
        createHash("sha256").update(await readFile(child)).digest("hex");
    }
  }
  await walk(root); return files;
}
export async function nativeFixture(answer = "Native answer retained — 原样保留", options: {blocked?: boolean; laterAnswer?: string; runtimeContext?: boolean; sessionId?: string; question?: string; emptyReason?: 'completed'|'aborted'} = {}) {
  const root = await mkdtemp(join(tmpdir(), "mmx-executive-native-read-"));
  const ctx = new Context();
  const id = SessionId(options.sessionId ?? "company-bound-original");
  try {
    await ctx.plugin(SessionStore); await ctx.plugin(AgentRegistry); await ctx.plugin(TypertRegistry);
    await ctx.plugin(JsonlPersistence, {root});
    const seed = Session.create(id);
    seed.append("turn/start", {turn:1});
    const originalMessage = createUserMessage({
      content:[{type:"text", text:options.question ?? "Original question — 原始问题"}], source:{kind:"user"},
    });
    if (!options.blocked && !options.emptyReason) {
      seed.append("step/start", {turn:1, step:1});
      seed.append("user/message", originalMessage, {surfaceOp:"append"});
      if (options.runtimeContext) seed.append("user/message", createUserMessage({
        content:[{type:"text",text:"Actual native runtime context"}], source:{kind:"runtime-context"},
      }), {surfaceOp:"append"});
      seed.append("assistant/message", {turn:1, step:1, message:createMessage({
        role:"assistant", content:[{type:"text", text:answer}],
        source:{kind:"model", provider:"fixture", model:"fixture"},
      }), stream:[{type:"text-chunks", time0:1, index:0, dt:[1,1],
        texts:["Native answer", " retained", " — 原样保留"]}]}, {surfaceOp:"append"});
      seed.append("step/end", {turn:1, step:1});
    }
    if (options.emptyReason === "aborted") {
      seed.append("step/start", {turn:1, step:1}); seed.append("step/end", {turn:1, step:1});
    }
    seed.append("turn/end", {turn:1, reason:options.emptyReason === "aborted" ?
      {kind:"aborted",reason:{kind:"user"}} : {kind:options.blocked ? "blocked" : "completed"}});
    if (options.laterAnswer !== undefined) {
      seed.append("turn/start", {turn:2}); seed.append("step/start", {turn:2, step:1});
      seed.append("user/message", createUserMessage({
        content:[{type:"text", text:"Later question"}], source:{kind:"user"},
      }), {surfaceOp:"append"});
      seed.append("assistant/message", {turn:2, step:1, message:createMessage({
        role:"assistant", content:[{type:"text", text:options.laterAnswer}],
        source:{kind:"model", provider:"fixture", model:"fixture"},
      }), stream:[{type:"text-chunks", time0:1, index:0, dt:[], texts:[options.laterAnswer]}]}, {surfaceOp:"append"});
      seed.append("step/end", {turn:2, step:1});
      seed.append("turn/end", {turn:2, reason:{kind:"completed"}});
    }
    const originalRecords = seed.snapshotEvents();

    const writer = await ctx.sessionPersistence.create({...seed.header, cwd:"/fixture/company-workspace"});
    try { await writer.append(seed.snapshotEvents()); await writer.flush(); }
    finally { await writer.close(); }
    // Mount the actual test Controller in an injecting native owner, so its
    // service view retains dependencies across the non-owner invocation scope.
    await ctx.plugin({inject:["sessions","agents","sessionPersistence","typert"],apply(child:Context){
      createSessionTestController(child, {
        defaultModelSelection:()=>({provider:"fixture", model:"fixture"}), cwd:"/fixture",
      });
    }});
    provideBrowserCredentials(ctx); await ctx.plugin(Connection); await ctx.plugin(TypertGatewayService);
    // This original native writer stays held during every company cold read.
    const held = await ctx.sessionPersistence.open(id, "write");
    return {ctx, root, id, originalMessage, originalRecords, before:await disk(root), async close() {
      await held.close(); await ctx.fiber.dispose(); await rm(root, {recursive:true, force:true});
    }};
  } catch (error) {
    await ctx.fiber.dispose(); await rm(root, {recursive:true, force:true}); throw error;
  }
}

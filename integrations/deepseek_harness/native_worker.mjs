#!/usr/bin/env node
/**
 * The enrolled Worker's same-process Web + ACP entry.
 * Owns no Session, credential, retry, queue or transcript. All effects stay in
 * the original profile services, ACP association and Worker process lifetime.
 */
import {createRequire} from "node:module";
import {createHash} from "node:crypto";
import {createReadStream,realpathSync} from "node:fs";
import {readFile,realpath,lstat} from "node:fs/promises";
import {dirname,join,resolve,sep} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {Socket} from "node:net";
import {Readable,Writable} from "node:stream";

const DONOR="687f282e8625c6b8d11ff58211a90524be2e4317";
const PROVIDER="deepseek-account";
const TOOLS=Object.freeze(["read","glob","grep"]);
const SHA=/^[0-9a-f]{64}$/;
const refused=()=>new Error("Native Worker owner or capability is no longer current");
const plain=x=>x!==null&&typeof x==="object"&&Object.getPrototypeOf(x)===Object.prototype;
const exact=(x,keys)=>plain(x)&&Reflect.ownKeys(x).length===keys.length&&keys.every(k=>Object.hasOwn(x,k));
const freeze=x=>{
  if(x&&typeof x==="object"){for(const value of Object.values(x))freeze(value);Object.freeze(x);}
  return x;
};
export const canonical=value=>JSON.stringify(value,(_key,item)=>
  plain(item)?Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])):item);
const digest=value=>createHash("sha256").update(canonical(value)).digest("hex");
async function hashFile(path){const h=createHash("sha256");for await(const block of createReadStream(path))h.update(block);return h.digest("hex");}
const nonempty=x=>typeof x==="string"&&x.length>0&&x.length<=256&&!/[\u0000-\u001f\u007f]/u.test(x);
export const nativeConfig=()=>({
  execution_surface:"dsh-native-web-acp",result_contract:"mastermind.dsh_native_conversation/v1",
  auth_realm:"dedicated-worker-account",sandbox_policy:"read-only",approval_policy:"never",
  network_policy:"disabled",write_capable:false,native_helper_policy:"DISABLED",
  skills:[],mcp_servers:[],resources:[],plugins:["mastermind-company"],forbidden:[],
});

/** Closed canonical requirements from the existing uniquely matched profile. */
export function parseExecutionPolicy(raw){
  try{
    if(typeof raw!=="string"||Buffer.byteLength(raw)>8192)throw refused();
    const value=JSON.parse(raw);
    if(!exact(value,["schema","profile_id","profile_digest","policy_digest","expected_config_digest","config","model"])||
      value.schema!=="mastermind.dsh.native_execution_policy.v1"||
      value.profile_id!=="operator.dsh.native-conversation.v1"||
      ![value.profile_digest,value.policy_digest,value.expected_config_digest].every(x=>typeof x==="string"&&SHA.test(x))||
      canonical(value)!==raw||canonical(value.config)!==canonical(nativeConfig())||
      digest(value.config)!==value.expected_config_digest||
      !exact(value.model,["provider","model"])||value.model.provider!==PROVIDER||!nonempty(value.model.model))
      throw refused();
    return freeze(value);
  }catch{throw new Error("Exact native execution requirements are unavailable");}
}
function literalTrue(fn){
  const value=fn();
  if(value!==true){if(value instanceof Promise)void value.catch(()=>{});throw refused();}
}
function capability(kind,name,toolSchema=null){
  return {kind,name,skill_content_digest:null,tool_schema_digest:toolSchema,mcp_server_identity:null,
    mcp_server_version:null,mcp_auth_status:null,resource_contract_digest:null};
}

/** Consumer bindings in the existing host; never creates or resumes an Agent. */
export function createNativeHostBindings({root,generation,policy,workspace,symbols,isAgentLoopRequest,sourceFacts}){
  if(root!==root.root||!(generation instanceof AbortController)||!policy||typeof workspace!=="string")throw refused();
  const normalize=value=>value?.[symbols.original]??value;
  let acpFiber,association,owners,provider,loaderCurrent;
  let candidate,modelStep,modelAssignment,observedSelection,accountObservation;
  const tools=new Map();
  const alive=()=>{generation.signal.throwIfAborted();return true;};
  const requireOwners=()=>{
    alive();
    if(!owners||!loaderCurrent)throw refused();
    for(const [key,value]of owners)if(normalize(root.get(key))!==value)throw refused();
    literalTrue(loaderCurrent);
    return true;
  };
  const requireAgent=agent=>{
    requireOwners();
    if(!association||association.agent!==agent||association.session!==agent.session||
      association.id!==agent.id||root.agents.get(agent.id)!==agent||root.sessions.get(agent.id)!==agent.session||
      agent.session.header.cwd!==workspace||association.caller.fiber!==acpFiber)throw refused();
    acpFiber.assertActive();return true;
  };
  const requireProviderRegistration=()=>{
    requireOwners();if(!provider)throw refused();literalTrue(()=>provider.assertCurrent());
    requireOwners();return true;
  };
  const requireAccountShape=held=>{
    const snapshot=held.snapshot,prototype=Object.getPrototypeOf(snapshot);
    if(prototype!==Object.prototype&&prototype!==null||Reflect.ownKeys(snapshot).length!==4)throw refused();
    const fields=Object.getOwnPropertyDescriptors(snapshot);
    for(const [key,value]of [["inferenceOrigin",held.origin],["userId",held.userId],
      ["isCurrent",held.current],["isInferenceCurrent",held.check]]){
      const field=fields[key];
      if(!field||!("value"in field)||!field.enumerable||field.value!==value)throw refused();
    }
  };
  const inferenceCurrent=held=>{
    requireAccountShape(held);
    const value=held.check.call(held.snapshot);
    requireAccountShape(held);
    if(value!==true&&value!==false){
      if(value instanceof Promise)void value.catch(()=>{});
      throw refused();
    }
    return value;
  };
  const captureAccount=snapshot=>{
    if(snapshot===null||typeof snapshot!=="object")throw refused();
    const fields=Object.getOwnPropertyDescriptors(snapshot);
    const held={snapshot,origin:fields.inferenceOrigin?.value,userId:fields.userId?.value,
      current:fields.isCurrent?.value,check:fields.isInferenceCurrent?.value};
    requireAccountShape(held);
    if(typeof held.current!=="function"||typeof held.check!=="function"||
      typeof held.origin!=="string"||!held.origin.isWellFormed()||
      Buffer.byteLength(held.origin)>32768)throw refused();
    let origin;try{origin=new URL(held.origin);}catch{throw refused();}
    if(!["http:","https:"].includes(origin.protocol)||origin.origin!==held.origin||
      origin.username||origin.password)throw refused();
    if(held.userId!==null&&(typeof held.userId!=="string"||!held.userId.length||
      !held.userId.isWellFormed()||Buffer.byteLength(held.userId)>32768||
      ["token","refresh","secret","auth.json","credential"].some(part=>held.userId.toLowerCase().includes(part))))
      throw refused();
    return Object.freeze(held);
  };
  const requireProvider=()=>{
    requireProviderRegistration();
    if(accountObservation){
      const held=accountObservation;
      if(owners.get("deepseekAccount").getLocalInferenceSnapshot!==held.snapshotMethod||
        !inferenceCurrent(held))throw refused();
      requireProviderRegistration();
      if(accountObservation!==held)throw refused();
    }
    return true;
  };
  const requireCeilings=agent=>{
    requireAgent(agent);
    if(root.sandboxPolicy.resolve({session:agent.session}).mode!=="read-only"||
      root.approval.policyFor(agent.session)!=="never")throw refused();
    for(const observed of tools.values())literalTrue(()=>observed.assertCurrent());
    requireAgent(agent);return true;
  };
  const requireTurn=agent=>{
    requireCeilings(agent);requireProvider();
    if(!candidate||candidate.agent!==agent||!candidate.consumed||!observedSelection||!modelStep||
      modelStep.agent!==agent||modelStep.session!==agent.session||agent.status!=="running")throw refused();
    modelStep.signal.throwIfAborted();return modelStep;
  };
  const input=Object.freeze({
    assertCurrent(){alive();if(!association||association.caller.fiber!==acpFiber)throw refused();acpFiber.assertActive();return true;},
    consume(attempt){
      requireAgent(attempt.agent);
      const held=candidate;
      if(!held||held.consumed||held.agent!==attempt.agent||attempt.session!==association.session||
        attempt.sessionSeq!==association.session.seq||attempt.target!=="next-turn"||
        attempt.start!==attempt.agent.inbox.nextTurn.length||attempt.removedCount!==0||
        attempt.inserted.length!==1||attempt.inserted[0]!==held.message||
        !attempt.send||attempt.send.message!==held.message||attempt.send.requestedTarget!=="next-turn"||
        attempt.send.wakeup!==true)throw refused();
      // The original Inbox owns the insertion; this consumes its one candidate.
      held.consumed=true;return true;
    },
  });
  const lifecycle=Object.freeze({admit(caller,operation,id){
    requireOwners();
    if(!acpFiber||caller.fiber!==acpFiber||association!==undefined||
      !["create","resume"].includes(operation)||root.agents.get(id)!==undefined||root.sessions.get(id)!==undefined)
      throw refused();
    // A failed first association is never reset into another attempt.
    const held=association={caller,operation,id,agent:undefined,session:undefined};
    return Object.freeze({signal:generation.signal,input,assertCurrent(){
      alive();caller.fiber.assertActive();
      if(association!==held||caller.fiber!==acpFiber)throw refused();return true;
    }});
  }});
  const toolAdmission=Object.freeze({signal:generation.signal,check(facts){
    alive();
    if(!owners)return false;
    const held=tools.get(facts.definition.name);
    if(!held)return false;
    if(facts.runtime!==owners.get("tools")||facts.registrationIdentity!==held.registrationIdentity||
      facts.definition!==held.definition||facts.execute!==held.execute||facts.ownerIdentity!==held.ownerIdentity)
      throw refused();
    if(!association?.agent||facts.scope!==association.agent)return false;
    requireAgent(association.agent);literalTrue(()=>held.assertCurrent());
    if(facts.phase==="dispatch"){
      const step=requireTurn(association.agent),exec=facts.execution;
      if(!exec||exec.agent!==step.agent||facts.originalCallerSignal!==step.signal||
        exec.parent!==undefined||exec.rootCallId!==exec.callId)throw refused();
      const call=step.toolCalls.get(exec.callId);
      if(!call||call.settled||call.event.data.name!==exec.name||
        canonical(exec.arguments)!==call.arguments||
        call.token!==undefined&&call.token!==exec.token)throw refused();
      exec.signal.throwIfAborted();
      if(requireTurn(step.agent)!==step)throw refused();
      call.token=exec.token;
    }else if(facts.phase!=="view")throw refused();
    return true;
  }});
  const llmAdmission=Object.freeze({signal:generation.signal,check(facts){
    requireProvider();
    const step=modelStep;
    if(!step)throw refused();
    requireTurn(step.agent);
    if(facts.runtime!==owners.get("llm")||facts.registrationIdentity!==provider.registrationIdentity||
      facts.adapterIdentity!==provider.adapterIdentity||facts.ownerIdentity!==provider.ownerIdentity||
      facts.config.provider!==PROVIDER||facts.config.model!==policy.model.model)throw refused();
    if(facts.phase==="prepare"){
      if(facts.agent!==step.agent||facts.session!==step.session||facts.turn!==step.turn||
        facts.step!==step.step||facts.signal!==step.signal)throw refused();
      step.prepared=true;
    }else{
      if(!step.prepared||!isAgentLoopRequest(facts.request)||facts.request.sessionId!==association.id||
        facts.request.signal!==step.signal||facts.request.purpose!==undefined||
        facts.request.provider!==PROVIDER||facts.request.model!==policy.model.model)throw refused();
      if(facts.phase==="dispatch"){
        if(step.request!==undefined&&step.request!==facts.request)throw refused();
        step.request=facts.request;
      }else if(facts.phase!=="write"||step.request!==facts.request)throw refused();
    }
    if(requireTurn(step.agent)!==step)throw refused();return true;
  }});
  root.provide("remoteAccessOwnerRestricted",true);
  root.provide("agentLifecycleAdmission",lifecycle);
  root.provide("nativeToolAdmission",toolAdmission);
  root.provide("nativeLlmAdmission",llmAdmission);
  root.provide("nativeSandboxCeiling",Object.freeze({mode:"read-only",signal:generation.signal,assertCurrent:alive}));
  root.provide("nativeApprovalCeiling",Object.freeze({policy:"never",signal:generation.signal,assertCurrent:alive}));
  root.provide("nativeSkillCeiling",Object.freeze({mode:"disabled",signal:generation.signal,assertCurrent:alive}));
  root.on("agent/created",({agent,source})=>{
    const held=association;
    if(!held||held.agent!==undefined||held.id!==agent.id||
      source!==(held.operation==="create"?"startup":"resume"))throw refused();
    held.agent=agent;held.session=agent.session;requireAgent(agent);
  },{global:true,prepend:true});
  root.on("agent/request",({agent,turn,step,signal},next)=>{
    requireCeilings(agent);requireProvider();
    if(!candidate?.consumed||candidate.agent!==agent||!observedSelection||signal.aborted)throw refused();
    modelStep={agent,session:agent.session,turn,step,signal,prepared:false,request:undefined,toolCalls:new Map()};
    return next();
  },{global:true,prepend:true});

  root.on("session/event",(session,event)=>{
    const step=modelStep;
    if(!step||step.session!==session||event.data.turn!==step.turn||event.data.step!==step.step)return;
    if(event.type==="tool/call"){
      let args;try{args=event.data.arguments?JSON.parse(event.data.arguments):{};}catch{args=event.data.arguments;}
      const existing=step.toolCalls.get(event.data.callId);
      if(existing){existing.settled=true;return;}
      step.toolCalls.set(event.data.callId,{event,arguments:canonical(args),settled:false,token:undefined});
    }else if(event.type==="tool/result"){
      const call=step.toolCalls.get(event.data.message.toolCallId);
      if(call&&event.sourceEventSeqs?.includes(call.event.seq))call.settled=true;
    }
  },{global:true,prepend:true});

  return Object.freeze({
    requireNativeReadOwner(agent){requireAgent(agent);},
    bindAcpFiber(fiber){alive();if(acpFiber!==undefined||!fiber)throw refused();acpFiber=fiber;},
    bindServices({requireLoaderCurrent,toolModules}){
      alive();if(owners!==undefined||typeof requireLoaderCurrent!=="function")throw refused();
      owners=new Map(["agents","sessions","llm","tools","credentials","deepseekAccount","skills","sandboxPolicy","approval"].map(key=>{
        const value=normalize(root.get(key));if(!value)throw refused();return[key,value];
      }));
      loaderCurrent=requireLoaderCurrent;requireOwners();
      provider=root.llm.observeRegistration(PROVIDER);requireProvider();
      for(const name of TOOLS){
        const observed=root.tools.observeRegistration(name);
        if(!observed||!toolModules(name,observed.ownerIdentity))throw refused();
        literalTrue(()=>observed.assertCurrent());tools.set(name,observed);
      }
      return true;
    },
    nativeModelAdmission(facts){
      requireAgent(facts.agent);requireProvider();
      if(observedSelection||candidate||modelAssignment||facts.configId!=="model"||
        facts.selection.provider!==PROVIDER||facts.selection.model!==policy.model.model||
        facts.value!==JSON.stringify([PROVIDER,policy.model.model]))throw refused();
      const held=modelAssignment={agent:facts.agent,requestId:facts.requestId,selection:facts.selection};
      return Object.freeze({signal:generation.signal,assertCurrent(){
        requireAgent(held.agent);requireProvider();
        if(modelAssignment!==held||candidate||observedSelection)throw refused();return true;
      }});
    },
    nativePromptAdmission(facts){
      if(facts.action==="retire"){
        if(candidate&&candidate.agent===facts.agent&&candidate.operationId===facts.operationId&&
          candidate.requestId===facts.requestId&&candidate.message===facts.message){
          candidate=undefined;modelStep=undefined;
        }
        return true;
      }
      requireAgent(facts.agent);
      if(!observedSelection)throw refused();
      if(facts.action==="admit"){
        if(candidate!==undefined)throw refused();
        requireCeilings(facts.agent);requireProvider();return true;
      }
      if(facts.action==="enqueue"){
        if(candidate!==undefined||facts.target!=="next-turn"||facts.wakeup!==true||
          !facts.message||!Object.isFrozen(facts.message))throw refused();
        requireCeilings(facts.agent);requireProvider();
        candidate={agent:facts.agent,operationId:facts.operationId,requestId:facts.requestId,
          message:facts.message,consumed:false};
        return true;
      }
      if(!["claim","cancel","settle"].includes(facts.action))throw refused();
      if(candidate===undefined)return facts.action==="settle";
      if(candidate.agent!==facts.agent||candidate.operationId!==facts.operationId||
        candidate.requestId!==facts.requestId)throw refused();
      return facts.action==="settle"||candidate.consumed;
    },
    async nativeObservation(facts,signal){
      requireAgent(facts.agent);requireProviderRegistration();signal.throwIfAborted();
      const agent=facts.agent,session=agent.session,selection=facts.selection,previous=accountObservation;
      if(!selection||selection.provider!==PROVIDER||selection.model!==policy.model.model||candidate)throw refused();
      const accountOwner=owners.get("deepseekAccount"),snapshotMethod=accountOwner.getLocalInferenceSnapshot;
      if(typeof snapshotMethod!=="function"||previous&&snapshotMethod!==previous.snapshotMethod)throw refused();
      const current=()=>{
        signal.throwIfAborted();requireCeilings(agent);requireProviderRegistration();
        if(agent.session!==session||normalize(root.deepseekAccount)!==accountOwner||
          accountOwner.getLocalInferenceSnapshot!==snapshotMethod||candidate||accountObservation!==previous)throw refused();
      };
      current();
      const accountSnapshot=await snapshotMethod.call(accountOwner);current();
      const fresh=captureAccount(accountSnapshot);
      const requireFresh=()=>{
        current();
        if(!inferenceCurrent(fresh))throw refused();
        current();literalTrue(()=>fresh.current.call(fresh.snapshot));
        requireAccountShape(fresh);current();
        if(!inferenceCurrent(fresh))throw refused();
        current();
      };
      const continuity=()=>{
        current();let identity=previous?.identityUserId??null;
        if(previous){
          const sameGrant=inferenceCurrent(previous);current();
          if(fresh.origin!==previous.origin||
            identity!==null&&fresh.userId!==null&&fresh.userId!==identity)throw refused();
          // A new grant in the same slot is insufficient. Renewal needs the
          // already observed original account identity on both grant lifetimes.
          if(!sameGrant&&(identity===null||fresh.userId!==identity))throw refused();
        }
        return identity??fresh.userId;
      };
      requireFresh();continuity();
      const skills=await root.skills.snapshot({scope:agent,cwd:workspace,signal});current();
      if(!skills.complete||skills.skills.length!==0)throw refused();
      const source=await sourceFacts();current();requireFresh();
      const schemas=root.tools.schemas(agent);
      if(schemas.length!==TOOLS.length||!TOOLS.every(name=>schemas.some(row=>row.name===name)))throw refused();
      const capabilities=TOOLS.map(name=>capability("tool",name,digest(tools.get(name).schema)));
      capabilities.push(capability("plugin","mastermind-company"));
      const effective=nativeConfig();
      effective.sandbox_policy=root.sandboxPolicy.resolve({session}).mode;
      effective.approval_policy=root.approval.policyFor(session);
      // "disabled" is the model's tool-network ceiling. It does not describe
      // the Web host's loopback listener or the original inference connection.
      if(digest(effective)!==policy.expected_config_digest)throw refused();
      const nextSelection=Object.freeze({...selection});
      // Account facts are part of the original sealed generation attestation.
      // Cache enrichment/renewal changes only its private live witness and
      // continuity anchor, never the original reported tuple or receipt.
      const admitted=previous?.admitted??Object.freeze({inference_origin:fresh.origin,user_id:fresh.userId});
      const result={
        agent_id:agent.id,session_cwd:session.header.cwd,...source,
        selection:{provider:nextSelection.provider,model:nextSelection.model,reasoning_effort:nextSelection.reasoningEffort??null},
        account:admitted,
        capabilities,effective_skills:[],effective_mcp:[],effective_plugins_or_apps:["mastermind-company"],
        sandbox_state:effective.sandbox_policy,approval_state:effective.approval_policy,
        network_state:effective.network_policy,effective_config_digest:digest(effective),
        supports_subagent_capability_ceiling:"FALSE",unknown_fields:[],
      };
      if(Buffer.byteLength(JSON.stringify({schema:"mastermind.dsh.native_owner_observation.v1",
        sessionId:agent.id,facts:result}))>32768)throw refused();
      const identityUserId=continuity();requireFresh();
      const next=Object.freeze({...fresh,snapshotMethod,identityUserId,admitted});
      current(); // one synchronous compare-and-swap, after all awaited/callback work
      accountObservation=next;observedSelection=nextSelection;
      return result;
    },
  });
}


/** Validate the original computed profile before any configuration expression or module runs. */
export function requireInstalledProfile({profile,resolution,app,home}){
  const inside=path=>typeof path==="string"&&realpathSync(path).startsWith(app+sep);
  if(profile.name!=="web"||profile.dir!==join(home,"profiles","web")||
    realpathSync(profile.dir)!==profile.dir||profile.skippedBundles.length!==0||
    profile.patches.length!==0||
    canonical(profile.layers.map(x=>x.packageName))!==canonical(["@deepseek-ai/dsh-base","@deepseek-ai/dsh-web-app"]))
    throw refused();
  for(const layer of profile.layers){
    if(!inside(layer.packageDir)||layer.patchPaths.length===0||!layer.patchPaths.every(inside))throw refused();
  }
  if(resolution&&(resolution.profileDir!==profile.dir||resolution.profilesDir!==join(home,"profiles")||
    resolution.localPackageNames.length!==0||resolution.linkedRoots.length!==0||
    resolution.entries.some(row=>row.scope!=="installation"||!inside(row.packageDir)||!inside(row.declarer))))
    throw refused();
}

/** Native-only policy on the original Loader, sealed after its qualified initial mount. */
export function createNativeLoaderAdmission({root,generation,symbols,app,companyEntry,resolvePluginResource,builtins}){
  const normalize=value=>value?.[symbols.original]??value;
  const loader=normalize(root.loader),internal=loader.internal;let sealed=false;
  if(!internal)throw refused();
  const current=()=>{
    generation.signal.throwIfAborted();
    if(normalize(root.loader)!==loader||loader.internal!==internal)throw refused();
  };
  const source=(name,parentURL)=>{
    current();
    const path=realpathSync(resolvePluginResource(name,parentURL));
    if(!(path.startsWith(app+sep)||[companyEntry,join(dirname(companyEntry),"company-peer.js"),
      join(dirname(companyEntry),"executive-read-port.js")].includes(path)))throw refused();
    current();return path;
  };
  const admission=Object.freeze({
    signal:generation.signal,
    update(_entry,_options,create){
      current();
      // The original shipped bundle inputs and exact installed overlays have
      // already been admitted. Later config edits cannot evaluate !!js first.
      if(sealed||create!==true)throw refused();
    },
    resolve(tree,name){
      current();
      if(name.startsWith("cordis:")){
        const key=name.slice(7);
        if(!Object.hasOwn(builtins,key)||loader.builtins[key]!==builtins[key])throw refused();
        return name;
      }
      return pathToFileURL(source(name,tree.ctx.baseUrl)).href;
    },
  });
  root.provide("nativeLoaderAdmission",admission);
  return Object.freeze({
    seal(){current();if(sealed)throw refused();sealed=true;},
    async importQualified(name,parentURL){
      current();const path=source(name,parentURL);
      const namespace=await internal.import(pathToFileURL(path).href,parentURL,{});current();return namespace;
    },
  });
}

/** Retain exact source-qualified Loader entries; later HMR/config changes retire use. */
export async function observeLoader(root,{companyEntry,importQualified,symbols,builtins}){
  const normalize=value=>value?.[symbols.original]??value;
  const loader=normalize(root.loader),entries=[...loader.entries()],held=[];
  let company;
  for(const entry of entries){
    const name=entry.options.name;
    const row={entry,options:canonical(entry.options),fiber:entry.fiber,disabled:entry.disabled,
      namespace:entry.moduleNamespace,state:entry.fiber?.state};
    if(!row.disabled){
      let imported;
      if(name.startsWith("cordis:")){
        const key=name.slice(7);
        if(!Object.hasOwn(builtins,key)||loader.builtins[key]!==builtins[key])throw refused();
        imported=builtins[key];
      }else imported=await importQualified(name,entry.parent.tree.ctx.baseUrl);
      if(imported!==row.namespace)throw new Error("Native Loader module source differs");
      if(name===companyEntry){if(company)throw refused();company=entry;}
    }
    held.push(row);
  }
  if(!company||company.disabled||!company.fiber)throw new Error("Original company plugin is unavailable");
  company.fiber.assertActive();
  const requireCurrent=()=>{
    if(normalize(root.loader)!==loader)throw refused();
    const live=[...loader.entries()];
    if(live.length!==held.length||live.some((entry,index)=>entry!==held[index].entry))throw refused();
    for(const row of held){
      const entry=row.entry;
      if(canonical(entry.options)!==row.options||entry.fiber!==row.fiber||entry.disabled!==row.disabled||
        entry.moduleNamespace!==row.namespace||entry.fiber?.state!==row.state)throw refused();
      if(entry.options.name.startsWith("cordis:")&&!row.disabled&&
        loader.builtins[entry.options.name.slice(7)]!==row.namespace)throw refused();
    }
    company.fiber.assertActive();return true;
  };
  requireCurrent();
  return {requireCurrent,toolModules(name,owner){
    requireCurrent();
    const wanted=name==="read"?"@deepseek-ai/dsh-tool-fs":"@deepseek-ai/dsh-tool-fs-search";
    return held.some(row=>!row.disabled&&row.entry.options.name===wanted&&owner.entry===row.entry);
  }};
}


/** Response custody on the original SDK writer and original socket.
 * This adds no queue or parser. Expiry substitutes the correlated content-free
 * reply at physical write rather than closing the Agent's shared connection. */
export function createNativeReadOutputGuard(socket){
  const originalWrite=socket.write;
  if(typeof originalWrite!=="function")throw refused();
  let pending,active,retired=false,wrapped=false;
  const check=held=>{
    if(retired||pending!==held||socket.write!==write)throw refused();
    const value=held.requireCurrent();
    if(value!==undefined){if(value instanceof Promise)void value.catch(()=>{});throw refused();}
    if(retired||pending!==held||socket.write!==write)throw refused();
  };
  function write(chunk,...args){
    const bytes=typeof chunk==="string"?Buffer.from(chunk):Buffer.from(chunk.buffer,chunk.byteOffset,chunk.byteLength);
    if(active&&bytes.equals(active.bytes)){
      try{check(active.held);}catch{chunk=active.fallback;}
    }
    return originalWrite.call(socket,chunk,...args);
  }
  socket.write=write;
  const finish=held=>{
    if(pending===held){pending=undefined;held.finish();}
  };
  return Object.freeze({
    register({requestId,response,unavailable,requireCurrent,finish:done}){
      if(retired||pending||typeof requireCurrent!=="function"||typeof done!=="function"||
        !(typeof requestId==="string"||Number.isSafeInteger(requestId))||
        !Object.isFrozen(response)||!Object.isFrozen(unavailable))throw refused();
      pending=Object.freeze({requestId,response,unavailable,requireCurrent,finish:done});
    },
    dispose(){retired=true;},
    wrap(stream){
      if(wrapped)throw refused();wrapped=true;
      const forward=(target,key)=>{const value=Reflect.get(target,key,target);return typeof value==="function"?value.bind(target):value;};
      return {readable:stream.readable,writable:new Proxy(stream.writable,{
        get(target,key){
          if(key!=="getWriter")return forward(target,key);
          return (...args)=>{
            const writer=target.getWriter(...args);
            return new Proxy(writer,{get(owner,property){
              if(property!=="write")return forward(owner,property);
              return async message=>{
                const held=pending;
                const matched=held&&message&&message.method===undefined&&
                  typeof message.id===typeof held.requestId&&message.id===held.requestId;
                if(!matched){
                  if(held&&message?.result===held.response)throw refused();
                  return owner.write(message);
                }
                if(active)throw refused();
                let outgoing=message;
                if(message.result!==undefined){
                  if(message.result!==held.response&&message.result!==held.unavailable)throw refused();
                  try{check(held);}catch{outgoing={jsonrpc:"2.0",id:message.id,result:held.unavailable};}
                  const bytes=Buffer.from(JSON.stringify(outgoing)+"\n");
                  const fallback=Buffer.from(JSON.stringify({jsonrpc:"2.0",id:message.id,result:held.unavailable})+"\n");
                  active={held,bytes,fallback};
                }
                try{return await owner.write(outgoing);}
                finally{active=undefined;finish(held);}
              };
            }});
          };
        },
      })};
    },
  });
}

export function createNativeReadAdmission({bindings,generation,bridge,executeRead,output,packageSha256}){
  if(!SHA.test(packageSha256)||typeof executeRead!=="function")throw refused();
  let busy=false;
  return async(facts,signal)=>{
    if(busy)throw refused();
    busy=true;let registered=false;
    try{
      const request=facts.request,selected=request.association,ownerCheck=facts.requireCurrent,agent=facts.agent;
      if(!plain(selected)||selected.native_session_id!==agent.id||selected.donor_sha!==DONOR||
        selected.native_package_sha256!==packageSha256||request.sessionId!==agent.id||typeof ownerCheck!=="function")
        throw refused();
      const current=()=>{
        generation.signal.throwIfAborted();signal.throwIfAborted();
        bindings.requireNativeReadOwner(agent);
        const value=ownerCheck();
        if(value!==undefined){if(value instanceof Promise)void value.catch(()=>{});throw refused();}
        if(facts.agent!==agent||facts.request!==request||facts.requireCurrent!==ownerCheck||
          request.association!==selected||selected.native_session_id!==agent.id||
          selected.native_package_sha256!==packageSha256||selected.donor_sha!==DONOR)throw refused();
        bindings.requireNativeReadOwner(agent);
      };
      current();
      const source=Object.freeze({association:selected,signal:generation.signal,requireCurrent:current});
      const prepared=await executeRead(bridge,source,request.request,signal,current);
      output.register({requestId:facts.requestId,response:prepared.response,unavailable:prepared.unavailable,
        requireCurrent(){current();prepared.requireCurrent();},finish(){busy=false;}});
      registered=true;
      return prepared.response;
    }finally{if(!registered)busy=false;}
  };
}

export async function main(){
  const entry=fileURLToPath(import.meta.url),release=dirname(entry),app=join(release,"app");
  if(process.argv.length!==2||await realpath(entry)!==entry||await realpath(release)!==release)throw refused();
  const rawPolicy=process.env.MMX_NATIVE_EXECUTION_POLICY,policy=parseExecutionPolicy(rawPolicy);
  const fd=process.env.MMX_NATIVE_COMPANY_FD;
  if(!/^(?:[3-9]|[1-9][0-9]+)$/.test(fd??"")||Number(fd)>2147483647)throw refused();
  const config=JSON.parse(await readFile(join(release,"app.json"),"utf8"));
  const entryHash=await hashFile(entry),binaryHash=await hashFile(process.execPath);
  if(config.schema!=="mastermind.dsh_attended_package.v1"||config.donor_sha!==DONOR||
    config.release!==release||config.node!==process.execPath||config.node_sha256!==binaryHash||
    config.port!==4180||config.public_url!=="https://chat.mastermind-x.com/"||
    config.native_worker?.entry!=="native_worker.mjs"||config.native_worker.sha256!==entryHash||
    await hashFile(join(release,"native_worker.patch.yml"))!==config.native_worker_patch_sha256||
    await hashFile(join(release,"company.patch.yml"))!==config.company_patch_sha256)throw refused();
  const workspace=await realpath(process.cwd());
  if(workspace!==process.cwd()||!process.env.HOME||!process.env.DSH_HOME||
    await realpath(process.env.DSH_HOME)!==process.env.DSH_HOME)throw refused();
  const nativeRequire=createRequire(join(app,"apps/cli/package.json"));
  const imported=new Map();
  const importNative=async name=>{
    let found=imported.get(name);if(found)return found;
    const path=await realpath(nativeRequire.resolve(name));
    if(!path.startsWith(app+sep))throw new Error("Native module is outside its qualified package");
    found=await import(pathToFileURL(path).href);imported.set(name,found);return found;
  };
  const [{runProfile},{createLaunchEnvironmentSnapshot},{symbols},{isAgentLoopRequest}]=await Promise.all([
    importNative("@deepseek-ai/dsh/profile-boot"),importNative("@deepseek-ai/dsh-launch-environment"),
    importNative("@deepseek-ai/cordis"),importNative("@deepseek-ai/dsh-llm"),
  ]);
  const {resolvePluginResource}=await importNative("@deepseek-ai/dsh-app-boot");
  const bootRequire=createRequire(join(app,"packages/boot/app-boot/package.json"));
  const builtinModules=await Promise.all(["include","group"].map(async key=>{
    const path=await realpath(bootRequire.resolve("@deepseek-ai/cordis-plugin-"+key));
    if(!path.startsWith(app+sep))throw refused();
    return[key,(await import(pathToFileURL(path).href)).default];
  }));
  const builtins=Object.freeze(Object.fromEntries(builtinModules));
  const companyEntry=join(release,"company_plugin/lib/index.js");
  const profileAdmission=Object.freeze({userLayer:false,check(profile,resolution){
    requireInstalledProfile({profile,resolution,app,home:process.env.DSH_HOME});
  }});
  const acpRequire=createRequire(join(app,"packages/acp/acp/package.json"));
  const Acp=await import(pathToFileURL(acpRequire.resolve("@deepseek-ai/dsh-acp")).href);
  const {ndJsonStream}=await import(pathToFileURL(acpRequire.resolve("@agentclientprotocol/sdk")).href);
  const socket=new Socket({fd:Number(fd),readable:true,writable:true}),generation=new AbortController();
  let running,bindings,root,shutdownTask,shutdownCode,nativeLoader;
  const shutdown=code=>{
    shutdownCode??=code;generation.abort(refused());
    if(running&&!shutdownTask)shutdownTask=running.shutdown.shutdown(shutdownCode);
    if(shutdownTask)void shutdownTask.catch(()=>{process.exitCode=1;});
  };
  socket.on("end",()=>shutdown(0));
  socket.on("close",()=>shutdown(shutdownCode??1));
  socket.on("error",()=>shutdown(1));
  const sourceFacts=async()=>{
    const cwd=process.cwd();
    if(cwd!==workspace)throw refused();
    const before=await lstat(cwd),actual=await realpath(cwd);
    const [binary,source]=await Promise.all([hashFile(process.execPath),hashFile(entry)]);
    const after=await lstat(workspace);
    if(process.cwd()!==cwd||await realpath(process.cwd())!==workspace||process.cwd()!==cwd||
      actual!==workspace||!after.isDirectory()||after.isSymbolicLink()||
      ["dev","ino","uid","gid","mode"].some(key=>before[key]!==after[key])||
      binary!==binaryHash||source!==entryHash)throw refused();
    return {
      process:{pid:process.pid,uid:process.geteuid(),gid:process.getegid(),exec_path:process.execPath,
        node_version:process.version,binary_sha256:binary},
      source:{entry_path:entry,entry_sha256:source},
      workspace:{workspace_path:workspace,device:after.dev,inode:after.ino,uid:after.uid,gid:after.gid},
    };
  };
  try{
    const environment=Object.fromEntries(["PATH","HOME","DSH_HOME","LANG"].map(key=>[key,process.env[key]]).filter(([,v])=>v!==undefined));
    running=await runProfile({
      environment:createLaunchEnvironmentSnapshot([{source:"process",values:environment}]),profile:"web",
      patchFiles:[join(release,"company.patch.yml"),join(release,"native_worker.patch.yml")],
      nativeProfileAdmission:profileAdmission,
      args:["--host","127.0.0.1","--port",String(config.port),"--public-url",config.public_url,
        "--trusted-host","chat.mastermind-x.com","--no-open"],
      initializeHost(ctx){
        if(root!==undefined||ctx!==ctx.root||ctx.get("profileContext").home!==process.env.DSH_HOME||
          ctx.get("profileContext").cwd!==workspace)throw refused();
        root=ctx;bindings=createNativeHostBindings({root,generation,policy,workspace,symbols,isAgentLoopRequest,sourceFacts});
        nativeLoader=createNativeLoaderAdmission({root,generation,symbols,app,companyEntry,resolvePluginResource,builtins});
      },
    });
    if(running.ctx!==root)throw refused();
    if(shutdownCode!==undefined){shutdown(shutdownCode);await shutdownTask;return;}
    nativeLoader.seal();
    const loader=await observeLoader(root,{companyEntry,symbols,builtins,importQualified:nativeLoader.importQualified});
    bindings.bindServices({requireLoaderCurrent:loader.requireCurrent,toolModules:loader.toolModules});
    generation.signal.throwIfAborted();
    const companyParent=pathToFileURL(companyEntry).href;
    const [{createCompanySessionReadBridge},{executeExecutiveNativeRead,inject:readInject}]=await Promise.all([
      nativeLoader.importQualified(join(dirname(companyEntry),"company-peer.js"),companyParent),
      nativeLoader.importQualified(join(dirname(companyEntry),"executive-read-port.js"),companyParent),
    ]);
    const packageSha256=await hashFile(join(release,"package-manifest.json"));
    const output=createNativeReadOutputGuard(socket);
    await root.plugin({name:"mastermind-native-acp",inject:[...Acp.inject,...readInject],apply(ctx){
      bindings.bindAcpFiber(ctx.fiber);
      const bridge=createCompanySessionReadBridge(ctx);
      const nativeReadAdmission=createNativeReadAdmission({bindings,generation,bridge,
        executeRead:executeExecutiveNativeRead,output,packageSha256});
      ctx.effect(()=>()=>output.dispose(),"mastermind: retained native READ replies");
      Acp.apply(ctx,{provider:PROVIDER,model:policy.model.model,
        stream:output.wrap(ndJsonStream(Writable.toWeb(socket),Readable.toWeb(socket))),
        nativePromptAdmission:bindings.nativePromptAdmission,nativeModelAdmission:bindings.nativeModelAdmission,
        nativeObservation:bindings.nativeObservation,nativeReadAdmission});
    }});
    generation.signal.throwIfAborted();
  }catch(error){
    shutdown(1);
    if(shutdownTask)await shutdownTask.catch(()=>{});
    socket.destroy();throw error;
  }
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  await main().catch(()=>{process.stderr.write("Native Worker admission failed\n");process.exitCode=1;});
}

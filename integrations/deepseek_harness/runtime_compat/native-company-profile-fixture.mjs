/** Explicit full-profile qualification fixture. Never an installed company launcher. */
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {join,resolve,dirname} from "node:path";
import {readFile,writeFile,realpath,stat} from "node:fs/promises";
import {createHash} from "node:crypto";
import {Socket} from "node:net";
import {Readable,Writable} from "node:stream";

const [supplyArg,stateArg,reportArg,mode,expectedId=""]=process.argv.slice(2);
if(process.argv.length!==6&&process.argv.length!==7)throw Error("Closed native company fixture arguments required");
if(!["new","resume"].includes(mode)||(mode==="new"?expectedId!=="":!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(expectedId)))
  throw Error("Exact fixture startup operation required");
const supply=await realpath(supplyArg),state=await realpath(stateArg);
if(supply!==resolve(supplyArg)||state!==resolve(stateArg)||resolve(reportArg)!==reportArg||dirname(reportArg)!==state)
  throw Error("Canonical independent fixture paths required");
const manifest=JSON.parse(await readFile(join(supply,"build-manifest.json"),"utf8"));
if(manifest.schema!=="mastermind.dsh_native_company_fixture.v1"||manifest.production_armed!==false||
  manifest.donor_sha!=="687f282e8625c6b8d11ff58211a90524be2e4317")throw Error("Full native fixture identity refused");
const hash=bytes=>createHash("sha256").update(bytes).digest("hex");
const app=join(supply,"app");
const ohfLifecycle=process.env.MMX_NATIVE_ACP_EXERCISE==="ohf-claim-stop-resume";
const lifecycle=ohfLifecycle||process.env.MMX_NATIVE_ACP_EXERCISE==="claim-stop-resume";
if(process.env.MMX_NATIVE_ACP_EXERCISE!==undefined&&!lifecycle)throw Error("Unknown native fixture scenario");
if(lifecycle){
  const expected=JSON.parse(await readFile(new URL("./native-acp-source.json",import.meta.url),"utf8"));
  if(manifest.native_acp_preparation?.patch_sha256!==expected.patch_sha256)throw Error("Native ACP patch not composed");
  const inventoryRaw=await readFile(join(supply,"runtime-inventory.json"));
  if(hash(inventoryRaw)!==manifest.runtime_inventory.sha256)throw Error("Native closure inventory changed");
  const inventory=JSON.parse(inventoryRaw);
  const name="packages/acp/acp/lib/index.js";
  if(hash(await readFile(join(app,name)))!==inventory[name]?.sha256)throw Error("Native ACP bundle differs");
}
for(const [relative,digest] of Object.entries(manifest.output_sha256)){
  if(relative.startsWith("/")||relative.split("/").includes("..")||
    hash(await readFile(join(app,relative)))!==digest)throw Error("Native fixture output changed");
}
const requiredFd=process.env.MMX_NATIVE_COMPANY_FD;
if(!/^(?:[3-9]|[1-9][0-9]+)$/.test(requiredFd??"")||Number(requiredFd)>2147483647)throw Error("Original connected fixture descriptor required");
const socket=new Socket({fd:Number(requiredFd),readable:true,writable:true});
const generation=new AbortController();
let shutdown,shutdownTask,root,acpFiber,selected=mode==="resume"?expectedId:undefined,agentCreates=0,modelCalls=0;
let stage="imports",modelOwner;
const report={schema:"mastermind.dsh_native_company_profile_proof.v1",production_armed:false,
  donor_sha:manifest.donor_sha,mode,actual_session_id:null,shared_agent:false,shared_session:false,
  pre_ready_owner_denied:false,company_page_observed:false,reader_retirement_keeps_owner:false,
  pre_admission_absent:false,native_start_source:null,isolated_native_home:false,
  native_close_settled:false,root_teardown_settled:false,model_calls:0,agent_creates:0,
  lifecycle,stream_partial:false,native_signal_aborted:false,model_stream_settled:false,native_observation_reads:0,
  interrupted_seq:null,interrupted_history:false,recovered_interrupted:false};
let reportTail=Promise.resolve();
const persist=()=>{
  const value=JSON.stringify({...report,model_calls:modelCalls,agent_creates:agentCreates},null,2)+"\n";
  return reportTail=reportTail.then(()=>writeFile(reportArg,value));
};
const requestShutdown=(code=0)=>{
  generation.abort(Error("Original fixture generation ended"));
  if(!shutdown)return;
  return shutdownTask??=(async()=>{
    const agents=root.agents,sessions=root.sessions;
    await shutdown.shutdown(code);
    // A timeout or rejected native disposer exits before this continuation.
    report.native_close_settled=agents.get(selected)===undefined&&sessions.get(selected)===undefined;
    report.root_teardown_settled=true;
    await persist();
  })();
};
let receivedEnd=false;
socket.on("end",()=>{receivedEnd=true;void requestShutdown();});
socket.on("close",()=>{if(!receivedEnd&&!shutdownTask){report.failure="private-acp-stream-closed";void requestShutdown(1);}});
socket.on("error",()=>{report.failure="private-acp-stream-error";void requestShutdown(1);});
const nativeRequire=createRequire(join(app,"apps/cli/package.json"));
const importNative=async name=>import(pathToFileURL(nativeRequire.resolve(name)).href);
const {runProfile}=await importNative("@deepseek-ai/dsh/profile-boot");
const {createLaunchEnvironmentSnapshot}=await importNative("@deepseek-ai/dsh-launch-environment");
const {LlmAdapter,isAgentLoopRequest}=await importNative("@deepseek-ai/dsh-llm");
const acpRequire=createRequire(join(app,"packages/acp/acp/package.json"));
const Acp=await import(pathToFileURL(acpRequire.resolve("@deepseek-ai/dsh-acp")).href);
const {ndJsonStream}=await import(pathToFileURL(acpRequire.resolve("@agentclientprotocol/sdk")).href);
const companyRoot=resolve(dirname(new URL(import.meta.url).pathname),"../company_plugin");
const companyManifest=JSON.parse(await readFile(join(companyRoot,"lib/build-manifest.json"),"utf8"));
const readerFile=join(companyRoot,"lib",companyManifest.host_exports["./company-peer"].file);
if(hash(await readFile(readerFile))!==companyManifest.host_exports["./company-peer"].sha256)
  throw Error("Original company reader artifact changed");
const {createCompanySessionReadBridge}=await import(pathToFileURL(readerFile).href);
try{
  stage="profile-boot";
  const running=await runProfile({
    environment:createLaunchEnvironmentSnapshot([]),profile:"web",patchFiles:[],
    args:["--host","127.0.0.1","--port","0","--no-open"],
    initializeHost(ctx){
      if(ctx!==ctx.root)throw Error("Original boot root required");
      root=ctx;
      if(process.env.HOME!==join(state,"home")||process.env.DSH_HOME!==join(state,"dsh")||
        process.env.DSH_AGENTS_HOME!==join(state,"agents")||ctx.get("profileContext").home!==join(state,"dsh")||
        ctx.get("profileContext").cwd!==join(state,"workspace"))throw Error("Isolated native home required");
      report.isolated_native_home=true;
      ctx.on("agent/request",({agent,turn,signal},next)=>{
        if(lifecycle){
          generation.signal.throwIfAborted();
          if(agent.id!==selected||ctx.agents.get(selected)!==agent||ctx.sessions.get(selected)!==agent.session)
            throw Error("Native fixture request owner differs");
          modelOwner={agent,turn,signal};
        }
        return next();
      },{global:true,prepend:true});
      ctx.on("llm/stream",(options,next)=>{
        if(!lifecycle){modelCalls++;throw Error("Fixture model dispatch forbidden");}
        generation.signal.throwIfAborted();
        if(!modelOwner||!isAgentLoopRequest(options)||options.provider!=="fixture"||options.model!=="fixture"||
          options.sessionId!==selected||options.signal!==modelOwner.signal||
          ctx.agents.get(selected)!==modelOwner.agent||ctx.sessions.get(selected)!==modelOwner.agent.session)
          throw Error("Unowned fixture model dispatch forbidden");
        return next();
      },{global:true,prepend:true});
      ctx.on("agent/assistant-stream",({agent,frame})=>{
        if(lifecycle&&agent===modelOwner?.agent&&frame.type==="chunk"&&frame.chunk.type==="text-delta"){
          report.stream_partial=true;void persist();
        }
      },{global:true});
      ctx.on("session/event",async(session,event)=>{
        if(!lifecycle||session.id!==selected||event.type!=="assistant/message"||event.data.interrupted!==true)return;
        report.interrupted_seq=event.seq;
        const lifetime=new AbortController();
        const reader=readBridge.open({principalScope:"fixture-native-principal",authorizationGeneration:"fixture-generation",
          workRef:"WS:native-company-fixture",sessionId:selected,signal:lifetime.signal,requireCurrent(){
            generation.signal.throwIfAborted();
            if(ctx.sessions.get(selected)!==session)throw Error("Native interrupted history owner changed");
          }});
        try{
          const page=await reader.page({throughSeq:event.seq,maxMessages:8});
          report.interrupted_history=page.records.some(row=>row.event.type==="assistant/message"&&
            row.event.data.interrupted===true&&row.event.data.message.content.some(block=>block.type==="text"&&block.text==="native interrupted prefix"));
        }finally{lifetime.abort();await reader.dispose();}
        await persist();
      },{global:true});
      ctx.provide("remoteAccessOwnerRestricted",true);
      ctx.provide("agentLifecycleAdmission",Object.freeze({admit(caller,operation,id){
        if(generation.signal.aborted||caller.fiber!==acpFiber||operation!==(mode==="new"?"create":"resume")||
          (selected!==undefined&&selected!==id))throw Error("Fixture original startup operation refused");
        if(ctx.agents.get(id)!==undefined||ctx.sessions.get(id)!==undefined)throw Error("Existing native owner cannot be adopted");
        report.pre_admission_absent=true;
        selected=id;
        return{signal:generation.signal,assertCurrent(){
          generation.signal.throwIfAborted();caller.fiber.assertActive();
          if(caller.fiber!==acpFiber||selected!==id)throw Error("Original fixture association retired");
          return true;
        }};
      }}));
      ctx.on("agent/created",async({agent,source})=>{
        agentCreates++;
        if(source!==(mode==="resume"?"resume":"startup"))throw Error("Native startup observation differs");
        report.native_start_source=source;
        if(agent.id!==selected||ctx.agents.get(selected)!==agent||ctx.sessions.get(selected)!==agent.session)
          throw Error("Native profile published another Session owner");
        report.actual_session_id=agent.session.id;report.shared_agent=true;report.shared_session=true;
        const result=await ctx.typertGateway.invoke({namespace:"session",method:"prompt",
          args:{request:{sessionId:selected,content:[{type:"text",text:"Must be refused"}]}},
          peer:ctx.connection.browserPeer}).then(()=>false,error=>error.code==="remote-access/denied");
        if(!result)throw Error("Stock owner reached a pre-ready native prompt");
        report.pre_ready_owner_denied=true;
        stage="native-web-agent-resolution";
        const webAgent=await ctx.get("sessionController").agents.resolveAgent(selected);
        if(webAgent.agent!==agent)throw Error("Native Web controller selected a different Agent");
        const lifetime=new AbortController();
        const reader=readBridge.open({principalScope:"fixture-native-principal",authorizationGeneration:"fixture-generation",
          workRef:"WS:native-company-fixture",sessionId:selected,signal:lifetime.signal,requireCurrent(){
            generation.signal.throwIfAborted();
            if(ctx.agents.get(selected)!==agent)throw Error("Original native fixture Agent changed");
          }});
        try{
          stage="native-company-history-page";
          const page=await reader.page({throughSeq:Number(agent.session.seq)-1,maxMessages:8});
          if(!Array.isArray(page.records))throw Error("Original native history page unavailable");
          report.company_page_observed=true;
          if(lifecycle&&mode==="resume"){
            report.recovered_interrupted=page.records.some(row=>row.event.type==="assistant/message"&&
              row.event.data.interrupted===true&&row.event.data.message.content.some(block=>block.type==="text"&&block.text==="native interrupted prefix"));
            if(!report.recovered_interrupted)throw Error("Original interrupted history was not recovered");
          }
        }finally{lifetime.abort();await reader.dispose();}
        if(ctx.agents.get(selected)!==agent)throw Error("Reader retirement displaced original Agent");
        report.reader_retirement_keeps_owner=true;await persist();
      });
      ctx.on("agent/disposed",async({agent})=>{
        if(agent.id===selected)await persist();
      });
    },
  });
  shutdown=running.shutdown;
  if(running.ctx!==root)throw Error("Profile bootstrap created a second Context");
  if(generation.signal.aborted){await requestShutdown();}
  else{
    class FixtureAdapter extends LlmAdapter{
      providerInfo(provider){return{id:provider,name:"Native profile fixture"};}
      async listModels(provider){return[{provider,id:"fixture",name:"Fixture",inputModalities:["text"]}];}
      async resolveModel(provider,model){return{provider,id:model,name:"Fixture",inputModalities:["text"]};}
      async *stream(options){
        if(!lifecycle||options.signal!==modelOwner?.signal||modelCalls!==0)throw Error("Native fixture model budget refused");
        modelCalls++;
        const text=mode==="new"?"native interrupted prefix":"native recovered answer";
        try{
          options.signal.throwIfAborted();
          yield{type:"block-start",index:0,blockType:"text"};
          yield{type:"text-delta",index:0,text};
          if(mode==="new")await new Promise((_resolve,reject)=>{
            const stopped=()=>{report.native_signal_aborted=true;reject(options.signal.reason);};
            if(options.signal.aborted)stopped();else options.signal.addEventListener("abort",stopped,{once:true});
          });
          yield{type:"block-end",index:0,block:{type:"text",text}};
          yield{type:"finish",reason:{kind:"stop"}};
        }finally{report.model_stream_settled=true;await persist();}
      }
    }
    root.llm.registerAdapter(["fixture"],new FixtureAdapter());
    // The same original non-owner company reader is composed into this Context.
    var readBridge=createCompanySessionReadBridge(root);
    stage="native-http-boundary";
    const origin="http://127.0.0.1:"+root.webServer.port;
    const before=await fetch(origin,{redirect:"manual"});
    const opened=await fetch(root.connection.authenticatedUrl(origin),{redirect:"manual"});
    const cookie=opened.headers.get("set-cookie")?.split(";",1)[0];
    if(!cookie)throw Error("Native fixture sign-in cookie missing");
    const index=await fetch(origin,{headers:{cookie},redirect:"manual"});
    const text=await index.text();
    const held=await fetch(origin+"/api/file?path=/fixture-held", {headers:{cookie}});
    const foreign=await fetch(origin+"/api/file?path=/fixture-held",{headers:{cookie,origin:"http://127.0.0.1.evil"}});
    report.http={unauthenticated:before.status,index:index.status,held_file:held.status,foreign_origin:foreign.status,
      title:text.includes("<title>Mastermind</title>"),owner_baseline_held:root.remoteAccess.snapshotFor({kind:"owner"}).owner===false};
    if(index.status!==200||held.status!==403||foreign.status!==403)
      throw Error("Native profile HTTP boundary differs");
    if(!report.http.owner_baseline_held)throw Error("Native profile owner baseline differs");
    await persist();
    stage="native-acp-composition";
    await root.plugin({name:"original-company-acp-fixture",inject:[...Acp.inject],apply(ctx){
      acpFiber=ctx.fiber;
      Acp.apply(ctx,{provider:"fixture",model:"fixture",stream:ndJsonStream(Writable.toWeb(socket),Readable.toWeb(socket)),
        ...ohfLifecycle?{async nativeObservation(facts,signal){
          // Explicit laboratory facts. This callback is never installed authority,
          // account verification, complete capability inventory or confinement.
          signal.throwIfAborted();generation.signal.throwIfAborted();ctx.fiber.assertActive();
          if(facts.agent.id!==selected||root.agents.get(selected)!==facts.agent||
            root.sessions.get(selected)!==facts.agent.session||facts.selection?.provider!=="fixture")
            throw Error("Original fixture observation owner differs");
          const workspace=await stat(join(state,"workspace")),binary=hash(await readFile(process.execPath));
          signal.throwIfAborted();generation.signal.throwIfAborted();ctx.fiber.assertActive();
          report.native_observation_reads++;
          return{served_model:facts.selection.model,harness_version:process.versions.node,
            harness_binary_digest:binary,capabilities:[],effective_skills:[],effective_mcp:[],effective_plugins_or_apps:[],
            sandbox_state:"laboratory-unconfined",approval_state:"laboratory-explicit",network_state:"laboratory-native-loopback",
            effective_config_digest:null,auth:{worker_id:"fixture-dsh",provider:"acp",auth_class:null,plan_type:null,
              nonsecret_provider_account_id:null,identity_confidence:"UNKNOWN",attestation_status:"ACCOUNT_REALM_ATTESTATION_UNPROVEN"},
            workspace:{workspace_path:join(state,"workspace"),base_sha:"b".repeat(40),device:workspace.dev,inode:workspace.ino,
              uid:workspace.uid,gid:workspace.gid},
            supports_subagent_capability_ceiling:"UNKNOWN",
            unknown_fields:["installed_authority","account","production_capability_inventory"]};
        }}:{},
        ...lifecycle?{nativePromptAdmission(facts){
          generation.signal.throwIfAborted();ctx.fiber.assertActive();
          return facts.agent.id===selected&&root.agents.get(selected)===facts.agent&&
            root.sessions.get(selected)===facts.agent.session&&facts.operationId===(ohfLifecycle?"ohf-op:":"")+"fixture-native-turn-"+mode;
        }}:{},
      });
    }});
  }
}catch{
  report.failure="fixture-failed:"+stage;await persist();
  if(shutdown)await requestShutdown(1);else{socket.destroy();process.exitCode=1;}
}

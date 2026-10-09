import {readFileSync,statSync} from "node:fs";
import {homedir,userInfo} from "node:os";
import {join} from "node:path";
export const POLICY_SCHEMA="mastermind.codex_computer_use_policy.v1";
export const READ_TOOLS=new Set(["get_app_state"]);
export const ACTION_TOOLS=new Set(["click","perform_secondary_action","set_value","select_text","scroll","drag","press_key","type_text"]);
export const ALLOWED_TOOLS=new Set(["list_apps",...READ_TOOLS,...ACTION_TOOLS]);
function refused(reason){throw new Error("COMPUTER_USE_POLICY_REFUSED: "+reason)}
export function compilePolicy(raw){
  if(!raw || typeof raw!=="object" || Array.isArray(raw) ||
    raw.schema!==POLICY_SCHEMA || !Array.isArray(raw.apps) ||
    raw.apps.length>20)refused("invalid policy schema or size");
  const apps=new Map();
  for(const row of raw.apps){
    if(!row || typeof row!=="object" ||
      typeof row.bundle_id!=="string" ||
      !/^[A-Za-z0-9][A-Za-z0-9.-]{2,127}$/.test(row.bundle_id) ||
      typeof row.display_name!=="string" ||
      !/^[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}$/.test(row.display_name) ||
      typeof row.elicitation!=="string" ||
      row.elicitation!=="Allow ChatGPT to use "+row.display_name+"?" ||
      typeof row.read!=="boolean" || typeof row.write!=="boolean" ||
      typeof row.preapproved!=="boolean" || (row.write && !row.read) ||
      apps.has(row.bundle_id))refused("malformed or duplicate application grant");
    apps.set(row.bundle_id,Object.freeze({...row}));
  }
  return apps;
}
export function loadPolicy(path=process.env.MMX_CUSE_POLICY_FILE ||
  join(homedir(),".config","mastermind","computer-use-policy.json")){
  let raw;
  try{
    const st=statSync(path);
    if(!st.isFile() || (st.mode&0o077)!==0 || st.uid!==userInfo().uid)
      refused("policy file must be owner-only (0600) and owned by current user");
    raw=JSON.parse(readFileSync(path,"utf8"));
  }catch(error){
    if(error?.code==="ENOENT")return new Map();
    if(String(error?.message).startsWith("COMPUTER_USE_POLICY_REFUSED"))throw error;
    refused("cannot read or parse owner policy");
  }
  return compilePolicy(raw);
}
export function authorizeCall(name,args,apps){
  if(name==="list_apps")return {ok:true,app:null};
  if(!ALLOWED_TOOLS.has(name) || !args || typeof args!=="object" ||
    Array.isArray(args) || typeof args.app!=="string")
    return {ok:false,reason:"TOOL_OR_APP_REFUSED"};
  const app=apps.get(args.app);
  if(!app)return {ok:false,reason:"APP_NOT_APPROVED"};
  if(!(READ_TOOLS.has(name)?app.read:app.write))
    return {ok:false,reason:"APP_ACTION_NOT_APPROVED"};
  return {ok:true,app:args.app};
}
export function authorizeElicitation(message,activeCall,apps){
  if(typeof message!=="string" || !activeCall?.app)return false;
  const app=apps.get(activeCall.app);
  return Boolean(app?.preapproved && message===app.elicitation);
}
export function projectedAppsResult(apps){
  const lines=[...apps.values()].map(app=>
    app.display_name+" — "+app.bundle_id+" [locally authorized; runtime state not verified]");
  return {content:[{type:"text",text:lines.join("\n") || "No applications are locally approved."}],isError:false};
}
export function filteredToolsResult(result,apps){
  if(!Array.isArray(result?.tools))refused("invalid upstream tool catalog");
  const hasReads=[...apps.values()].some(app=>app.read);
  const hasWrites=[...apps.values()].some(app=>app.write);
  const tools=result.tools.filter(t=>t && typeof t.name==="string" &&
    (t.name==="list_apps" || (t.name==="get_app_state" && hasReads) ||
      (ACTION_TOOLS.has(t.name) && hasWrites)));
  return {...result,tools};
}

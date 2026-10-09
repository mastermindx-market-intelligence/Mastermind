/**
 * Pure *consumer* facet for the existing authenticated Studio/SCF MCP owner.
 *
 * This is NOT a remote server, OAuth issuer, fleet placer, tool launcher,
 * permission authority, worker queue, or app-control lease. The caller must
 * inject native owner callbacks that authorize the present principal and
 * RuntimeBinding and execute on the original exact machine/carrier.
 */
const APP_ID=/^[A-Za-z0-9][A-Za-z0-9.-]{2,127}$/;
const stringProp=(description)=>({type:"string",description});
const tool=(name,description,properties={},required=[],write=false)=>({
  name,description,
  inputSchema:{type:"object",properties,required,additionalProperties:false},
  annotations:{
    readOnlyHint:!write,
    destructiveHint:write,
    openWorldHint:false,
  },
});
const APP={app:stringProp("Exact approved application bundle identifier")};
const CATALOG=Object.freeze([
  tool("cuse_list_apps","List only the applications permitted by this machine's owner-local Computer Use policy."),
  tool("cuse_get_app_state","Return accessibility state and a screenshot for one approved application.",APP,["app"]),
  tool("cuse_click","Click a permitted accessibility element or coordinate on the exact bound host.",
    {...APP,element_index:{type:"string"},x:{type:"number"},y:{type:"number"},
     click_count:{type:"integer",minimum:1,maximum:2},
     mouse_button:{type:"string",enum:["left","right","middle"]}},["app"],true),
  tool("cuse_type_text","Enter bounded text into a permitted application on the exact bound host.",
    {...APP,text:{type:"string",minLength:1,maxLength:2048}},["app","text"],true),
  tool("cuse_press_key","Send an approved key or shortcut into the bound application.",
    {...APP,key:{type:"string",minLength:1,maxLength:80}},["app","key"],true),
]);
const LOOKUP=new Map(CATALOG.map(x=>[x.name,x]));
const UPSTREAM=Object.freeze({
  cuse_list_apps:"list_apps",
  cuse_get_app_state:"get_app_state",
  cuse_click:"click",
  cuse_type_text:"type_text",
  cuse_press_key:"press_key",
});
const READ=new Set(["cuse_list_apps","cuse_get_app_state"]);
function refuse(message){throw new Error("COMPUTER_USE_FACET_REFUSED: "+message)}
function scrubArgs(name,args){
  if(!args || typeof args!=="object" || Array.isArray(args))refuse("invalid arguments");
  const t=LOOKUP.get(name);
  if(!t)refuse("unrecognized tool");
  for(const k of Object.keys(args)){
    if(!Object.hasOwn(t.inputSchema.properties,k))refuse("unexpected input field");
  }
  if(name==="cuse_list_apps"){
    if(Object.keys(args).length)refuse("inventory takes no arguments");
    return {};
  }
  if(typeof args.app!=="string"||!APP_ID.test(args.app))refuse("invalid app identifier");
  if(name==="cuse_click"){
    const index=args.element_index;
    if(index!==undefined && (typeof index!=="string"||!/^\d{1,5}$/.test(index)))
      refuse("invalid accessibility index");
    const hasCoords=Number.isFinite(args.x)&&Number.isFinite(args.y);
    if(index===undefined&&!hasCoords)refuse("click requires an index or both coordinates");
    if((args.x!==undefined||args.y!==undefined)&&!hasCoords)refuse("invalid click coordinates");
    if(hasCoords && (Math.abs(args.x)>16000||Math.abs(args.y)>16000))refuse("coordinate exceeds bound");
    if(args.click_count!==undefined && (![1,2].includes(args.click_count)))refuse("invalid click count");
    if(args.mouse_button!==undefined && !["left","right","middle"].includes(args.mouse_button))
      refuse("invalid mouse button");
  }
  if(name==="cuse_type_text"&&(typeof args.text!=="string"||
      args.text.length===0||args.text.length>2048))refuse("text exceeds accepted bound");
  if(name==="cuse_press_key"&&(typeof args.key!=="string"||
      args.key.length===0||args.key.length>80))refuse("invalid key");
  return {...args};
}
function validGrant(grant,mode){
  return Boolean(grant?.allowed===true &&
    typeof grant.principalRef==="string"&&grant.principalRef.length>0 &&
    typeof grant.bindingRef==="string"&&grant.bindingRef.length>0 &&
    typeof grant.operationRef==="string"&&grant.operationRef.length>0 &&
    (mode==="read"?grant.canRead===true:grant.canWrite===true));
}
/**
 * authorize(context, {mode,toolName,app}) -> current owner decision with:
 * {allowed,canRead,canWrite,principalRef,bindingRef,operationRef}
 * dispatch({context,principalRef,bindingRef,operationRef,toolName,arguments})
 *   -> standard MCP tool result from the *already selected and bound* host
 * recordUncertainEffect({context,principalRef,bindingRef,operationRef,toolName,cause})
 *   -> persists effect uncertainty to incumbent Executive/Agent owners, not
 *      to this adapter. Must be wired before write tools may be issued.
 */
export function createComputerUseFacet({authorize,dispatch,recordUncertainEffect}={}){
  if(typeof authorize!=="function"||typeof dispatch!=="function")refuse("owner callbacks required");
  const decision=(context,request)=>authorize(context,request);
  return {
    async listTools(context){
      if(!context||typeof context!=="object")return {tools:[]};
      const read=await decision(context,{mode:"read",toolName:"catalog",app:null});
      const write=await decision(context,{mode:"write",toolName:"catalog",app:null});
      return {tools:CATALOG.filter(tool=>
        (READ.has(tool.name)?validGrant(read,"read"):
          (validGrant(write,"write")&&typeof recordUncertainEffect==="function"))
      ).map(x=>({...x}))};
    },
    async callTool({name,arguments:input={}}={},context){
      if(!context||typeof context!=="object")refuse("missing caller context");
      const args=scrubArgs(name,input);
      const mode=READ.has(name)?"read":"write";
      if(mode==="write"&&typeof recordUncertainEffect!=="function")
        refuse("write effect owner unavailable");
      // Trust the incumbent owner only: never infer grant from app input or
      // from a previous listing/other session's permission.
      const grant=await decision(context,{mode,toolName:name,app:args.app??null});
      if(!validGrant(grant,mode))refuse("owner denied request or binding");
      if(name==="cuse_click"){
        // Pixel coordinates and non-left/multiple clicks are substantially
        // wider than a fresh AX element click. They require additional native
        // owner authorization; the model cannot elect these capabilities.
        if((args.x!==undefined||args.y!==undefined) &&
           grant.allowCoordinateClick!==true)refuse("coordinate click not owner-authorized");
        if(args.mouse_button!==undefined&&args.mouse_button!=="left" &&
           grant.allowAlternateButtons!==true)refuse("alternate button not owner-authorized");
        if(args.click_count!==undefined&&args.click_count!==1 &&
           grant.allowMultipleClicks!==true)refuse("multiple clicks not owner-authorized");
      }
      const invokeRequest={
        context,
        principalRef:grant.principalRef,
        bindingRef:grant.bindingRef,
        operationRef:grant.operationRef,
        toolName:UPSTREAM[name],
        arguments:args,
      };
      const ambiguous=async (cause)=>{
        try{
          await recordUncertainEffect({
            context,
            principalRef:grant.principalRef,bindingRef:grant.bindingRef,
            operationRef:grant.operationRef,toolName:UPSTREAM[name],
            cause:String(cause||"no_result").slice(0,120),
          });
        }catch{/* Absence of an ACK never clears uncertainty. */}
        throw new Error("COMPUTER_USE_EFFECT_UNKNOWN: reconcile original binding; no retry");
      };
      let result;
      try {result=await dispatch(invokeRequest);}
      catch(error){
        if(mode==="write")return await ambiguous(error?.name||"dispatch_failure");
        throw error;
      }
      if(!result||typeof result!=="object"||!Array.isArray(result.content)){
        if(mode==="write")return await ambiguous("malformed_response");
        refuse("malformed backend response");
      }
      if(mode==="write"&&result.isError===true)return await ambiguous("unconfirmed_tool_error");
      return result;
    },
  };
}
export const COMPUTER_USE_FACET_TOOLS=CATALOG;

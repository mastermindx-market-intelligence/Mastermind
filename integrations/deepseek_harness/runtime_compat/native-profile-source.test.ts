/** Source admission in the original Loader/profile owners, before evaluation. */
import {afterEach,expect,it} from "vitest";
import {Context,symbols} from "@deepseek-ai/cordis";
import {Loader} from "@deepseek-ai/cordis-plugin-loader";
import Group from "@deepseek-ai/cordis-plugin-group";
import {readProfilePatches,initProfile,composeEntries} from "@deepseek-ai/dsh-app-boot";
import {mkdtemp,mkdir,writeFile,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {pathToFileURL} from "node:url";
import {createNativeLoaderAdmission,observeLoader,requireInstalledProfile} from "../native_worker.mjs";

const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();});
async function files(){
  const home=await mkdtemp(join(tmpdir(),"mmx native profile "));
  cleanup.push(()=>rm(home,{recursive:true,force:true}));
  const app=join(home,"qualified-app"),profileDir=join(home,"profiles","web");
  await mkdir(app,{recursive:true});await mkdir(profileDir,{recursive:true});
  const layers=[];
  for(const [i,name] of ["@deepseek-ai/dsh-base","@deepseek-ai/dsh-web-app"].entries()){
    const dir=join(app,"node_modules",name);await mkdir(dir,{recursive:true});
    const patch=join(dir,"cordis.patch.yml");await writeFile(patch,"[]\n");
    await writeFile(join(dir,"package.json"),JSON.stringify({name,version:"0.0.0",type:"module",main:"./index.js",
      dependencies:{},dsh:{bundle:{patch:"./cordis.patch.yml"}}}));
    await writeFile(join(dir,"index.js"),"export const fixture=true;\n");
    layers.push({packageName:name,packageDir:dir,patchPaths:[patch],patches:[]});
  }
  await writeFile(join(app,"package.json"),JSON.stringify({name:"native-fixture",version:"0.0.0",type:"module",
    main:"./index.js",dependencies:Object.fromEntries(layers.map(x=>[x.packageName,"0.0.0"]))}));
  await writeFile(join(app,"index.js"),"export const fixture=true;\n");
  initProfile(profileDir,layers.map(x=>x.packageName));
  const profile={name:"web",dir:profileDir,patchPath:join(profileDir,"cordis.patch.yml"),
    layers,patches:[],skippedBundles:[]};
  const resolution={profileDir,profilesDir:join(home,"profiles"),localPackageNames:[],linkedRoots:[],
    entries:layers.map(x=>({name:x.packageName,packageDir:x.packageDir,declarer:join(x.packageDir,"package.json"),scope:"installation"}))};
  return{home,app,profile,resolution};
}
it("admits only the original installed web bundle and runtime-resolution source",async()=>{
  const f=await files();
  expect(()=>requireInstalledProfile(f)).not.toThrow();
  for(const changed of [
    {...f,profile:{...f.profile,layers:[...f.profile.layers].reverse()}},
    {...f,profile:{...f.profile,patches:[{id:"unqualified",disabled:{__jsExpr:"effect()"}}]}},
    {...f,profile:{...f.profile,skippedBundles:[{packageName:"missing",reason:"absent"}]}},
    {...f,resolution:{...f.resolution,localPackageNames:["foreign"]}},
    {...f,resolution:{...f.resolution,linkedRoots:[{name:"foreign",realPath:f.home}]}},
    {...f,resolution:{...f.resolution,entries:[{...f.resolution.entries[0],scope:"profile"}]}},
    {...f,resolution:{...f.resolution,entries:[{...f.resolution.entries[0],declarer:f.profile.dir}]}},
  ])expect(()=>requireInstalledProfile(changed)).toThrow();
});
it("native composition never reads either user patch layer",async()=>{
  const f=await files();
  // Invalid YAML proves these mutable layers are not parsed, not merely filtered later.
  await writeFile(f.profile.patchPath,"[invalid home-controlled YAML");
  await writeFile(join(f.home,"cordis.patch.yml"),"[invalid profile-controlled YAML");
  const nativeProfileAdmission=Object.freeze({userLayer:false as const,
    check:(profile:any,resolution?:any)=>requireInstalledProfile({...f,profile,resolution})});
  const context={name:"web",dir:f.profile.dir,patchPath:f.profile.patchPath,
    installAnchor:join(f.app,"package.json"),cwd:f.home,home:f.home,
    startedBundles:f.profile.layers.map(x=>x.packageName),overlays:[{id:"qualified-overlay",disabled:true}],
    telemetryDisabledEnv:undefined,nativeProfileAdmission};
  expect(readProfilePatches("fixture",context,f.profile)).toEqual([{id:"qualified-overlay",disabled:true}]);
  expect(()=>readProfilePatches("fixture",{...context,nativeProfileAdmission:undefined},f.profile)).toThrow();
});
async function loader(){
  const f=await files(),ctx=new Context(),generation=new AbortController();
  cleanup.push(()=>ctx.fiber.dispose());
  class MemoryLoader extends Loader{write(){}}
  await ctx.plugin(MemoryLoader,{baseUrl:pathToFileURL(f.app+"/").href});
  const companyEntry=join(f.home,"company.mjs");
  await writeFile(companyEntry,"export default {name:'native-company-fixture',apply(){}};\n");
  const builtins={group:Group};
  const resolvePluginResource=(name:string)=>name;
  const policy=createNativeLoaderAdmission({root:ctx,generation,symbols,app:f.app,
    companyEntry,resolvePluginResource,builtins});
  ctx.loader.builtins.group=Group;
  return{...f,ctx,generation,policy,companyEntry,builtins};
}
it("uses the original builtin value and traced Loader identity",async()=>{
  const h=await loader();
  await h.ctx.loader.create({id:"group",name:"cordis:group",group:true,config:[]});
  await h.ctx.loader.create({id:"company",name:h.companyEntry});
  h.policy.seal();
  const seen=await observeLoader(h.ctx,{companyEntry:h.companyEntry,symbols,builtins:h.builtins,
    importQualified:h.policy.importQualified});
  expect(seen.requireCurrent()).toBe(true);
  expect(h.ctx.loader).not.toBe(h.ctx.loader); // Traced wrappers, one original service.
  expect(seen.requireCurrent()).toBe(true);
  h.ctx.loader.builtins.group=class DifferentGroup{};
  expect(()=>seen.requireCurrent()).toThrow();
});
it("refuses a later changed row before its disabled expression evaluates",async()=>{
  const h=await loader();
  await h.ctx.loader.create({id:"company",name:h.companyEntry});h.policy.seal();
  const entry=[...h.ctx.loader.entries()][0],before=entry.options;
  const options={disabled:{__jsExpr:"(() => { throw Error('evaluated unqualified expression') })()"}};
  await expect(entry.update(options as any)).rejects.toThrow("Native Worker owner");
  expect(entry.options).toBe(before);expect(entry.options.disabled).toBeUndefined();
});
it("refuses an outside module before the original importer evaluates it",async()=>{
  const h=await loader(),outside=join(h.home,"outside.mjs");
  await writeFile(outside,"throw Error('evaluated outside module');\n");
  expect(()=>h.ctx.loader.import(outside)).toThrow("Native Worker owner");
});

it("native reload reads actual installed layers again without reintroducing either user layer",async()=>{
  const f=await files(),admitted:any[]=[];
  const nativeProfileAdmission=Object.freeze({userLayer:false as const,check(profile:any){
    expect(profile.skippedBundles).toEqual([]);
    expect(profile.layers.map(x=>x.packageName)).toEqual(f.profile.layers.map(x=>x.packageName));
    requireInstalledProfile({...f,profile,resolution:undefined});admitted.push(profile);
  }});
  const context={name:"web",dir:f.profile.dir,patchPath:f.profile.patchPath,
    installAnchor:join(f.app,"package.json"),cwd:f.home,home:f.home,
    startedBundles:f.profile.layers.map(x=>x.packageName),overlays:[],telemetryDisabledEnv:undefined,nativeProfileAdmission};
  await writeFile(f.profile.patchPath,"[invalid");
  await writeFile(join(f.home,"cordis.patch.yml"),"[invalid");
  expect(readProfilePatches("fixture",context)).toEqual([]);
  await writeFile(f.profile.layers[0].patchPaths[0],["- insert:","    - id: original-installed-row","      name: installed-row",""].join("\n"));
  const next=composeEntries([readProfilePatches("fixture",context)]);
  expect(next.map(x=>x.id)).toEqual(["original-installed-row"]);
  expect(admitted).toHaveLength(2);expect(admitted[0]).not.toBe(admitted[1]);
  await writeFile(join(f.profile.dir,"package.json"),JSON.stringify({dsh:{profile:{bundles:[]}}}));
  expect(()=>readProfilePatches("fixture",context)).toThrow();
});

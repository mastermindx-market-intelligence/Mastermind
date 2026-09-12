import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {atomicJson} from './monitor.mjs';

export function saveSession(file,deviceId,session){
 const current=JSON.parse(fs.readFileSync(file,'utf8'));
 if(current.deviceId!==deviceId)throw Error('device_identity_changed');
 if(!session?.access_token||!session?.refresh_token)throw Error('session_missing');
 atomicJson(file,{...current,session:{access_token:session.access_token,refresh_token:session.refresh_token}});
}
export function childMatches(saved,actual,uid,node,entry){
 return !!saved&&!!actual&&actual.pid===saved.pid&&actual.uid===uid&&saved.uid===uid&&
   actual.started===saved.started&&actual.command===saved.command&&actual.command===`${node} ${entry}`&&
   (actual.ppid===saved.ppid||actual.ppid===1);
}
export function processInfo(pid){
 if(!Number.isSafeInteger(pid)||pid<2)return null;
 const r=spawnSync('/bin/ps',['-p',String(pid),'-o','uid=,ppid=,lstart=,args='],{encoding:'utf8',timeout:3000});
 if(r.error)throw Error('process_observation_unavailable');
 if(r.status===1&&!r.stdout.trim())return null;
 if(r.status!==0)throw Error('process_observation_unavailable');
 const m=r.stdout.trim().match(/^(\d+)\s+(\d+)\s+(\w+\s+\w+\s+\d+\s+[\d:]+\s+\d+)\s+(.+)$/);
 if(!m)throw Error('process_observation_unavailable');
 return {pid,uid:Number(m[1]),ppid:Number(m[2]),started:m[3].replace(/\s+/g,' '),command:m[4]};
}
export function verifyManifest(root,manifest){
 if(!manifest||!Object.keys(manifest).length)throw Error('release_manifest_empty');
 for(const [relative,expected] of Object.entries(manifest)){
  if(path.isAbsolute(relative)||relative.split('/').includes('..'))throw Error('release_path');
  const file=path.join(root,relative);const stat=fs.lstatSync(file);
  if(expected.kind==='symlink'){
   if(!stat.isSymbolicLink()||fs.readlinkSync(file)!==expected.target)throw Error('release_integrity');
  }else{
   if(!stat.isFile()||createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==expected.sha256)throw Error('release_integrity');
  }
 }
}
export function fatalAuth(error){return [400,401,403].includes(error?.status);}
export function safeCall(call){
 if(!/^[a-f0-9-]{36}$/i.test(call?.id??'')||!/^[a-z][a-z0-9_]{0,63}$/.test(call?.tool_name??''))return null;
 return {id:call.id,tool:call.tool_name};
}

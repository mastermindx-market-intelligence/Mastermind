import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {saveSession, childMatches, verifyManifest, fatalAuth, safeCall} from '../safety.mjs';

test('session rotation updates only the existing canonical device record',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dc-auth-'));const file=path.join(root,'device.json');
 try{fs.writeFileSync(file,JSON.stringify({deviceId:'device-a',preserved:1,session:{access_token:'old',refresh_token:'old'}}));
 saveSession(file,'device-a',{access_token:'new',refresh_token:'rotated'});
 assert.deepEqual(fs.readdirSync(root),['device.json']);
 const x=JSON.parse(fs.readFileSync(file));assert.equal(x.session.refresh_token,'rotated');assert.equal(x.preserved,1);
 assert.equal(fs.statSync(file).mode&0o777,0o600);
 assert.throws(()=>saveSession(file,'device-b',{access_token:'new',refresh_token:'rotated'}),/device_identity_changed/);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
test('orphan cleanup requires exact child birth, command, user and parent',()=>{
 const saved={pid:12,uid:501,ppid:10,started:'Sun Sep 6 2026',command:'/node /vendor/dist/index.js'};
 assert.equal(childMatches(saved,{...saved,ppid:1},501,'/node','/vendor/dist/index.js'),true);
 for(const change of [{uid:502},{started:'different'},{command:'/node other.js'},{pid:13},{ppid:999}])
 assert.equal(childMatches(saved,{...saved,...change},501,'/node','/vendor/dist/index.js'),false);
});
test('manifest refuses changed vendor bytes and path escape',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dc-manifest-'));
 try{fs.writeFileSync(path.join(root,'code.js'),'safe');
 const m={'code.js':{kind:'file',sha256:createHash('sha256').update('safe').digest('hex')}};
 verifyManifest(root,m);fs.writeFileSync(path.join(root,'code.js'),'changed');assert.throws(()=>verifyManifest(root,m),/release_integrity/);
 assert.throws(()=>verifyManifest(root,{'../escape':m['code.js']}),/release_path/);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
test('auth revocation stops; ordinary network errors are not classified as revoked',()=>{
 for(const status of [400,401,403])assert.equal(fatalAuth({status}),true);
 for(const status of [429,500,503])assert.equal(fatalAuth({status}),false);
 assert.equal(fatalAuth(new TypeError('fetch failed')),false);
});
test('call metadata never includes arguments, outputs or malformed opaque IDs',()=>{
 const x=safeCall({id:'12345678-1234-1234-1234-123456789abc',tool_name:'start_process',tool_args:{password:'secret'}});
 assert.deepEqual(x,{id:'12345678-1234-1234-1234-123456789abc',tool:'start_process'});
 assert.equal(safeCall({id:'secret',tool_name:'evil\nsecret'}),null);
});
test('an absent or empty pin manifest fails closed',()=>{
 assert.throws(()=>verifyManifest('/tmp',{}),/release_manifest_empty/);
});

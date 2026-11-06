import {expect,it} from 'vitest';
import {sessionSendArguments} from './session-send-arguments';
const argsFor=(kind:string)=>({target_ref:kind+':'+'a'.repeat(64),operation_key:'session-continue-'+'b'.repeat(64),instruction:'原文\n  preserved\t\r',stop_condition:'One exact return.\n'});
it.each(['fabric_attempt','hermes_secretary','hermes_meta'])('closed native %s send preserves the exact four original fields without conferring any capability',kind=>{
 const args=argsFor(kind);expect(sessionSendArguments(args)).toEqual(args);
 for(const k of Object.keys(args)){const v={...args} as Record<string,unknown>;delete v[k];expect(sessionSendArguments(v)).toBeNull();for(const bad of [null,1,[],{}])expect(sessionSendArguments({...args,[k]:bad})).toBeNull();}
 for(const k of ['principal_scope','url','permission','work_ref','root_job_id'])expect(sessionSendArguments({...args,[k]:'foreign'})).toBeNull();
});
it.each(['fabric_attempt','hermes_secretary','hermes_meta'])('native %s send rejects implicit/foreign/newline references and Unicode bounds without rewriting text',kind=>{
 const args=argsFor(kind);
 for(const key of ['target_ref','operation_key'] as const){for(const value of [args[key]+'\n',args[key].toUpperCase(),args[key].slice(0,-1),'latest','foreign:'+args[key]])expect(sessionSendArguments({...args,[key]:value})).toBeNull();}
 for(const prefix of ['codex:','hermes_secretary','HERMES_SECRETARY:','hermes_secretary::'])expect(sessionSendArguments({...args,target_ref:prefix+'a'.repeat(64)})).toBeNull();
 for(const key of ['instruction','stop_condition']){expect(sessionSendArguments({...args,[key]:'🦀'.repeat(700)})).not.toBeNull();for(const value of ['🦀'.repeat(701),'',' \n\r\t'])expect(sessionSendArguments({...args,[key]:value})).toBeNull();}
});

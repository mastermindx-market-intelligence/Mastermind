import {expect,it} from 'vitest';
import {workConnectionPresentation as present} from './work-connection-presentation';
import type {MissionDiagnosticSnapshot} from './diagnostic-state';
import {decodeNativeExecutiveObservation} from './native-executive-observation';
const snapshot:MissionDiagnosticSnapshot={hostKind:'native',launchConfigured:false,frontendResourceConfigured:false,nativeResourceConfigured:null,acquisitionAvailable:true,contentAvailable:true,executiveAvailable:false,executiveContextPhase:'auth_unavailable',executiveTransportPhase:'auth_unavailable'};
const local=(reason:string,available=false)=>decodeNativeExecutiveObservation({schema:'mastermind.native_executive_status.v1',configured:true,available,reason,generation:9,programs_read:{phase:'TIMEOUT',http_status:null}})!;
it.each(['en','zh-CN'])('uses reported status without inventing refusal or backend success: %s',locale=>{
 expect(present(snapshot,undefined,locale)?.title).toBe(locale==='en'?'Work connection unavailable':'工作连接不可用');
 expect(present(snapshot,local('AUTHORIZATION_REFUSED'),locale)?.title).toBe(locale==='en'?'Work authorization was not granted':'工作授权未获批准');
 expect(present(snapshot,local('AVAILABLE',true),locale)?.title).toBe(locale==='en'?'Work connection not confirmed':'工作连接尚未确认');
});
it.each(['AUTHORIZING','EXCHANGING','AUTH_TRANSACTION_EXPIRED','EXPIRED','NOT_ESTABLISHED','TOKEN_EXCHANGE_FAILED','TOKEN_RESPONSE_INVALID','AUTH_BROWSER_UNAVAILABLE'])('does not relabel %s as refusal',reason=>{
 expect(present(snapshot,local(reason),'en')?.title).not.toBe('Work authorization was not granted');
});
it.each([null,{...snapshot,hostKind:'web' as const},{...snapshot,acquisitionAvailable:false},{...snapshot,contentAvailable:false},{...snapshot,acquisitionAvailable:null},{...snapshot,contentAvailable:null}])('withholds account/content presentation without affirmative native facts',value=>{
 expect(present(value,local('AUTHORIZATION_REFUSED'),'en')).toBeNull();
});
it('keeps unknown and legacy distinct from refused and hides extra copy on healthy flow',()=>{
 const unknown={...snapshot,executiveAvailable:null,executiveContextPhase:'unknown' as const,executiveTransportPhase:'unknown' as const};
 expect(present(unknown,undefined,'en')?.title).toBe('Work connection not confirmed');
 expect(present(snapshot,decodeNativeExecutiveObservation({generation:9,available:false})!,'en')?.title).toBe('Work connection unavailable');
 expect(present({...snapshot,executiveAvailable:true,executiveContextPhase:'ready'},local('AUTHORIZATION_REFUSED'),'en')).toBeNull();
});

import {expect,it} from 'vitest';
import {workStatusPresentation} from './work-status-presentation';
it.each(['en','zh-CN'] as const)('keeps review approval and a return separate from absent acceptance in %s',locale=>{
 const input={dispatch:'RETURNED',review:'approve',acceptance:'NOT_PROJECTED',read:'CURRENT'} as const;
 const before=JSON.stringify(input),text=workStatusPresentation(input,locale);
 expect(text.acceptance).toBe(locale==='en'?'Acceptance not supplied':'未提供验收信息');
 expect(text.review).toBe(locale==='en'?'Review approved':'审阅通过');expect(text.readCaveat).toBeNull();expect(JSON.stringify(input)).toBe(before);
});
it('keeps uncertain dispatch and partial or historical source warnings explicit',()=>{
 const base={review:'NOT_YET',acceptance:'NOT_PROJECTED'} as const;
 expect(workStatusPresentation({...base,dispatch:'UNKNOWN',read:'PARTIAL'},'en')).toMatchObject({dispatch:'Dispatch not confirmed',readCaveat:'Some source information is missing or may be out of date.'});
 expect(workStatusPresentation({...base,dispatch:'EFFECT_UNKNOWN',read:'HISTORICAL'},'en')).toMatchObject({dispatch:'Outcome unknown',readCaveat:'This is historical source information; it does not confirm current status.'});
 expect(workStatusPresentation({...base,dispatch:'UNKNOWN',read:'UNAVAILABLE'},'zh-CN').readCaveat).toBe('来源信息不可用，无法确认当前状态。');
});

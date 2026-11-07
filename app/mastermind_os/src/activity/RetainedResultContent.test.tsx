// @vitest-environment jsdom
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {RetainedResultContent} from './RetainedResultContent';
afterEach(cleanup);
it.each(['en','zh-CN'] as const)('puts exact summary before closed structured record in %s',locale=>{
 const summary='Original reply\nsecond line',roleResult={source:'a'.repeat(64),nested:{exact:true}};
 const {container}=render(<RetainedResultContent locale={locale} summary={summary} roleResult={roleResult} nextActions={['Actual next step']}/>);
 const paragraph=container.querySelector('.mm-result-reading__summary')!,details=container.querySelector('details')!;
 expect(paragraph.textContent).toBe(summary);expect(details.open).toBe(false);
 expect(Boolean(paragraph.compareDocumentPosition(details)&Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
 expect(details.querySelector('pre')!.textContent).toBe(JSON.stringify(roleResult,null,2));
 expect(screen.getByRole('heading',{name:locale==='en'?'Summary':'摘要'})).toBeTruthy();
 expect(screen.getByText('Actual next step')).toBeTruthy();
});
it('does not invent a next action for an empty source array',()=>{
 render(<RetainedResultContent locale="en" summary="Exact return" roleResult={{}} nextActions={[]}/>);
 expect(screen.queryByRole('heading',{name:'Suggested next actions'})).toBeNull();
});

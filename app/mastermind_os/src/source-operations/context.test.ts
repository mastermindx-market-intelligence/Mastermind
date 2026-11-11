import { describe, expect, it } from 'vitest';
import { decodeSourceOperationContext, validSourceOperationContextSelection } from './context';
const selected = {action:'ADOPT_PLAN' as const,workRef:'WS:TEST'};
const body = () => ({schema:'mastermind.workspace_source_operation_context.v1',
  selection:{action:'ADOPT_PLAN',work_ref:'WS:TEST'},owner_context:{principal_scope:'a'.repeat(64)},can_inspect:true});
describe('qualified source operation context', () => {
  it('decodes only the exact selected action/scope and detaches the result', () => {
    const raw = body(); const value = decodeSourceOperationContext(raw,selected);
    raw.owner_context.principal_scope='b'.repeat(64);
    expect(value.owner_context.principal_scope).toBe('a'.repeat(64));
    expect(value.can_inspect).toBe(true);
    expect('can_adopt' in value).toBe(false);
  });
  it.each(['WS:TEST\n','WS:lower','WS:A','WS:../TEST','WS:TEST--BAD'])('refuses noncanonical work %s', workRef => {
    expect(validSourceOperationContextSelection({...selected,workRef})).toBe(false);
  });
  it('permits a rootless global CREATE context without inventing project identity', () => {
    expect(validSourceOperationContextSelection({action:'publish_project_proposal',workRef:null})).toBe(true);
    expect(validSourceOperationContextSelection({action:'ADOPT_PLAN',workRef:null})).toBe(false);
  });
  it('refuses public auth labels, foreign selection, extra fields and wrong scope', () => {
    for (const raw of [{signed_in:true}, {...body(),can_adopt:true},
      {...body(),selection:{action:'ACCEPT_DIRECTION',work_ref:'WS:TEST'}},
      {...body(),owner_context:{principal_scope:'label'}},
      {...body(),owner_context:{principal_scope:'a'.repeat(64)+'\n'}}]) {
      expect(() => decodeSourceOperationContext(raw,selected)).toThrow('SOURCE_OPERATION_CONTEXT_INVALID');
    }
  });
  it('does not invoke nested accessors or leak reflective errors', () => {
    let invoked=0;
    const raw=body(); Object.defineProperty(raw.owner_context,'principal_scope',{get(){invoked++;return 'a'.repeat(64);}});
    expect(() => decodeSourceOperationContext(raw,selected)).toThrow('SOURCE_OPERATION_CONTEXT_INVALID');
    expect(invoked).toBe(0);
    const proxy=new Proxy({}, {getPrototypeOf(){throw Error('private diagnostic');}});
    expect(() => decodeSourceOperationContext(proxy,selected)).toThrow(/^SOURCE_OPERATION_CONTEXT_INVALID$/);
  });
});

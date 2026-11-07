// @vitest-environment jsdom
import {expect,it,vi} from 'vitest';
import {MAX_FILE_BYTES,readStagedProjectFile} from './project-knowledge-requests';

function file(raw: Uint8Array | string,name='notes.md',type='text/markdown') {
  const bytes=typeof raw==='string'?new TextEncoder().encode(raw):raw.slice();
  const value=new File([bytes as BlobPart],name,{type});
  // Named jsdom-only byte-reader seam; actual File internal brand is retained.
  const read=vi.fn(async()=>bytes.slice().buffer as ArrayBuffer);
  Object.defineProperty(value,'arrayBuffer',{value:read,configurable:true});
  return {value,read};
}
it('stages exact bounded text once with no project or request authority',async()=>{
  const original='\ufeffResearch 中文\r\nLiteral \\u4e2d';const f=file(original);
  const staged=await readStagedProjectFile(f.value);
  expect(staged).toEqual({display_name:'notes.md',media_type:'text/markdown',content_utf8:original});
  expect(Object.isFrozen(staged)).toBe(true);expect(f.read).toHaveBeenCalledTimes(1);
  expect(Object.keys(staged).sort()).toEqual(['content_utf8','display_name','media_type']);
});
it.each([
  ['oversize','x'.repeat(MAX_FILE_BYTES+1),'notes.md','text/markdown','FILE_TOO_LARGE'],
  ['empty','','notes.md','text/markdown','INVALID_FILE'],
  ['extension','x','notes.exe','','UNSUPPORTED_FILE_TYPE'],
  ['mime','x','notes.md','application/octet-stream','UNSUPPORTED_FILE_TYPE'],
  ['path','x','../notes.md','text/markdown','INVALID_FILE'],
] as const)('refuses %s before reading',async(_name,raw,name,type,code)=>{
  const f=file(raw,name,type);await expect(readStagedProjectFile(f.value)).rejects.toMatchObject({code});
  expect(f.read).not.toHaveBeenCalled();
});
it('refuses a forged File and a directory-selected File',async()=>{
  await expect(readStagedProjectFile({name:'notes.md'} as File)).rejects.toMatchObject({code:'INVALID_FILE'});
  const f=file('text');Object.defineProperty(f.value,'webkitRelativePath',{value:'directory/notes.md'});
  await expect(readStagedProjectFile(f.value)).rejects.toMatchObject({code:'INVALID_FILE'});
  expect(f.read).not.toHaveBeenCalled();
});
it('refuses invalid UTF8 and a read whose byte size changed',async()=>{
  await expect(readStagedProjectFile(file(new Uint8Array([0xff])).value)).rejects.toMatchObject({code:'INVALID_TEXT'});
  const f=file('text');Object.defineProperty(f.value,'arrayBuffer',{value:async()=>new ArrayBuffer(1)});
  await expect(readStagedProjectFile(f.value)).rejects.toMatchObject({code:'READ_FAILED'});
});
it('honors cancellation before and after the single read',async()=>{
  const f=file('text');const before=new AbortController();before.abort();
  await expect(readStagedProjectFile(f.value,before.signal)).rejects.toMatchObject({code:'CANCELLED'});
  expect(f.read).not.toHaveBeenCalled();
  let deliver!:(value:ArrayBuffer)=>void;const pending=new Promise<ArrayBuffer>(resolve=>{deliver=resolve;});
  Object.defineProperty(f.value,'arrayBuffer',{value:()=>pending});
  const after=new AbortController();const staged=readStagedProjectFile(f.value,after.signal);
  const refused=expect(staged).rejects.toMatchObject({code:'CANCELLED'});after.abort();
  deliver(new TextEncoder().encode('text').buffer);await refused;
});

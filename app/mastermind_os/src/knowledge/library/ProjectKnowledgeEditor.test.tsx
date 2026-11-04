// @vitest-environment jsdom
/**
 * Focused React/Vitest + jsdom checks for ProjectKnowledgeEditor.
 *
 * The request builders from ./project-knowledge-requests are used as readonly
 * production dependencies — this suite never re-implements, patches or wraps
 * them. All fixtures are synthetic; nothing here performs live auth, upload,
 * grants or network work, and no test claims a real save happened.
 *
 * Environment global File: if the jsdom File lacks `arrayBuffer`, Node's real
 * File is installed as the test-environment global so fixtures carry the
 * actual native brand getters the builder checks. The production builder is
 * never modified.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ProjectKnowledgeEditor } from './ProjectKnowledgeEditor';
import type {
  ProjectKnowledgeEditorFileProps,
  ProjectKnowledgeEditorPreferenceProps,
} from './ProjectKnowledgeEditor';
import type {
  ProjectFileAddRequest,
  ProjectKnowledgeSourceContext,
  ProjectPreferenceSetRequest,
  ProjectSourceCurrentFn,
} from './project-knowledge-requests';

/** Actual jsdom File brand; only its absent byte-read method is a local fixture. */
function fixtureFile(bytes:Uint8Array,name:string,type:string):File {
 const owned=bytes.slice();const file=new File([owned as BlobPart],name,{type});
 if(typeof file.arrayBuffer!=='function') Object.defineProperty(file,'arrayBuffer',{configurable:true,value:()=>Promise.resolve(owned.buffer as ArrayBuffer)});
 return file;
}

const WORK_REF = 'WS:KNOWLEDGE-EDITOR-SCRATCH';
const SOURCE_COMMIT = '0123456789abcdef0123456789abcdef01234567';
const BASE_REVISION = 'f'.repeat(64);
const FILE_REQUEST_ID = `mmos-project-file-add-${'a1b2c3d4e5'.repeat(4)}`; // 40 hex
const PREF_REQUEST_ID = `mmos-project-preference-set-${'5e6d7c8b9a'.repeat(4)}`; // 40 hex
const PREF_REVISION = 'a'.repeat(64);
const OTHER_REVISION = 'b'.repeat(64);

const makeContext = (): ProjectKnowledgeSourceContext => ({
  workRef: WORK_REF,
  sourceCommit: SOURCE_COMMIT,
  baseRevision: BASE_REVISION,
});

/** Actual currency callback: same three fields back, nothing granted. */
const currentSame: ProjectSourceCurrentFn = (snapshot) => ({
  workRef: snapshot.workRef,
  sourceCommit: snapshot.sourceCommit,
  baseRevision: snapshot.baseRevision,
});

/** Currency callback that proves the source moved. */
const currentChanged: ProjectSourceCurrentFn = () => {
  throw new Error('synthetic drift');
};

const makeTextFile = (name: string, content: string, type = ''): File => {
  const bytes = new TextEncoder().encode(content);
  return fixtureFile(bytes,name,type);
};

const makeBytesFile = (name: string, bytes: number[], type = ''): File =>
  fixtureFile(new Uint8Array(bytes),name,type);

/** Points the native chooser at one synthetic file; explicit selection only. */
const selectFile = (input: HTMLElement, file: File): void => {
  Object.defineProperty(input, 'files', {
    value: {
      0: file,
      length: 1,
      item: (index: number) => (index === 0 ? file : null),
    },
    configurable: true,
  });
  fireEvent.change(input);
};

const renderFileEditor = (overrides: Partial<ProjectKnowledgeEditorFileProps> = {}) => {
  const props: ProjectKnowledgeEditorFileProps = {
    mode: 'file',
    sourceContext: makeContext(),
    requestId: FILE_REQUEST_ID,
    authGeneration: 1,
    hostGeneration: 'host-1',
    locale: 'en',
    current: currentSame,
    phase: 'idle',
    onSubmitFile: vi.fn(),
    ...overrides,
  };
  const utils = render(React.createElement(ProjectKnowledgeEditor, props));
  return { props, onSubmitFile: props.onSubmitFile as ReturnType<typeof vi.fn>, ...utils };
};

const renderPreferenceEditor = (
  overrides: Partial<ProjectKnowledgeEditorPreferenceProps> = {},
) => {
  const props: ProjectKnowledgeEditorPreferenceProps = {
    mode: 'preference',
    sourceContext: makeContext(),
    requestId: PREF_REQUEST_ID,
    authGeneration: 1,
    hostGeneration: 'host-1',
    locale: 'en',
    current: currentSame,
    phase: 'idle',
    initialValue: '',
    expectedPreferenceRevision: PREF_REVISION,
    onSubmitPreference: vi.fn(),
    ...overrides,
  };
  const utils = render(React.createElement(ProjectKnowledgeEditor, props));
  return { props, onSubmitPreference: props.onSubmitPreference as ReturnType<typeof vi.fn>, ...utils };
};

const textarea = () => screen.getByRole('textbox') as HTMLTextAreaElement;
const buttonNamed = (name: string) =>
  screen.getByRole('button', { name }) as HTMLButtonElement;

afterEach(() => {
  cleanup();
});

describe('file mode', () => {
  it('labels the native chooser, restricts accept, and disables Add without a selection', () => {
    renderFileEditor();
    const input = screen.getByLabelText('Choose a file') as HTMLInputElement;
    expect(input.type).toBe('file');
    expect(input.getAttribute('accept')).toBe('.md,.txt,text/markdown,text/plain');
    expect(buttonNamed('Add file').disabled).toBe(true);
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByText('Source details')).not.toBeNull();
  });

  it('shows a selected file by name and bytes without ever claiming it saved', () => {
    renderFileEditor();
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('notes.md', 'hello'));
    expect(screen.getByText('notes.md')).not.toBeNull();
    expect(screen.getByText('5 bytes')).not.toBeNull();
    expect(screen.getByText('Selected — not saved yet.')).not.toBeNull();
    expect(screen.queryByText('Saved to this project.')).toBeNull();
    const onSubmitFile = screen.getByRole('button', { name: 'Add file' }) as HTMLButtonElement;
    expect(onSubmitFile.disabled).toBe(false);
  });

  it('keeps the prior selection when a chooser change carries no file', () => {
    renderFileEditor();
    const input = screen.getByLabelText('Choose a file');
    selectFile(input, makeTextFile('notes.md', 'hello'));
    const noFiles = { length: 0, item: () => null };
    Object.defineProperty(input, 'files', { value: noFiles, configurable: true });
    fireEvent.change(input);
    expect(screen.getByText('notes.md')).not.toBeNull();
  });

  it('hands the exact closed frozen request to the owner once (CJK, CRLF, emoji intact)', async () => {
    const content = '中文标题\r\n第二行 😀\nend';
    const { onSubmitFile } = renderFileEditor();
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('notes.md', content));
    await actClick('Add file');
    await waitFor(() => expect(onSubmitFile).toHaveBeenCalledTimes(1));
    const request = onSubmitFile.mock.calls[0][0] as ProjectFileAddRequest;
    expect(request.schema).toBe('mastermind.project_file_add_request.v1');
    expect(request.request_id).toBe(FILE_REQUEST_ID);
    expect(request.work_ref).toBe(WORK_REF);
    expect(request.source_commit).toBe(SOURCE_COMMIT);
    expect(request.base_revision).toBe(BASE_REVISION);
    expect(request.file.display_name).toBe('notes.md');
    expect(request.file.media_type).toBe('text/markdown');
    expect(request.file.content_utf8).toBe(content);
    expect(Object.isFrozen(request)).toBe(true);
    expect(Object.isFrozen(request.file)).toBe(true);
  });

  it('cannot double-submit on a double click', async () => {
    const { onSubmitFile } = renderFileEditor();
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('notes.md', 'hello'));
    const button = buttonNamed('Add file');
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(onSubmitFile).toHaveBeenCalledTimes(1));
    await actOnly();
    expect(onSubmitFile).toHaveBeenCalledTimes(1);
  });

  it('refuses an unsupported extension with closed copy and no private error text', async () => {
    const { onSubmitFile } = renderFileEditor();
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('data.json', '{}'));
    await actClick('Add file');
    await waitFor(() => expect(screen.getByRole('status')).not.toBeNull());
    expect(screen.getByRole('status').textContent).toBe('The change was not saved.');
    expect(document.body.textContent).not.toContain('only .md');
    expect(onSubmitFile).not.toHaveBeenCalled();
    expect(screen.getByText('data.json')).not.toBeNull();
  });

  it('refuses an oversize file before any submit', async () => {
    const { onSubmitFile } = renderFileEditor();
    selectFile(
      screen.getByLabelText('Choose a file'),
      makeBytesFile('big.md', new Array<number>(40000).fill(0x61)),
    );
    await actClick('Add file');
    await waitFor(() => expect(screen.getByRole('status')).not.toBeNull());
    expect(screen.getByRole('status').textContent).toBe('The change was not saved.');
    expect(onSubmitFile).not.toHaveBeenCalled();
  });

  it('refuses invalid UTF-8 content', async () => {
    const { onSubmitFile } = renderFileEditor();
    selectFile(
      screen.getByLabelText('Choose a file'),
      makeBytesFile('broken.md', [0x23, 0xff, 0xfe, 0x2e]),
    );
    await actClick('Add file');
    await waitFor(() => expect(screen.getByRole('status')).not.toBeNull());
    expect(screen.getByRole('status').textContent).toBe('The change was not saved.');
    expect(onSubmitFile).not.toHaveBeenCalled();
  });

  it('source drift during the build shows stale, keeps the selection, and never submits', async () => {
    const { onSubmitFile } = renderFileEditor({ current: currentChanged });
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('notes.md', 'hello'));
    await actClick('Add file');
    await waitFor(() => expect(screen.getByRole('status')).not.toBeNull());
    expect(screen.getByRole('status').textContent).toBe('This project changed. Your draft is kept.');
    expect(onSubmitFile).not.toHaveBeenCalled();
    expect(screen.getByText('notes.md')).not.toBeNull();
  });

  it('a parent id with the wrong paired prefix is refused and never retargeted', async () => {
    const { onSubmitFile } = renderFileEditor({ requestId: PREF_REQUEST_ID });
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('notes.md', 'hello'));
    await actClick('Add file');
    await waitFor(() => expect(screen.getByRole('status')).not.toBeNull());
    expect(screen.getByRole('status').textContent).toBe('The change was not saved.');
    expect(onSubmitFile).not.toHaveBeenCalled();
  });

  it('a missing owner disables Add and says saving is unavailable', () => {
    renderFileEditor({ onSubmitFile: undefined });
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('notes.md', 'hello'));
    expect(buttonNamed('Add file').disabled).toBe(true);
    expect(screen.getByText('Saving is unavailable.')).not.toBeNull();
  });
});

describe('preference mode', () => {
  it('hands the literal draft through exactly (CJK, CRLF, emoji, edge spaces)', async () => {
    const { onSubmitPreference } = renderPreferenceEditor();
    fireEvent.change(textarea(), { target: { value: '  中文偏好 😀 ' } });
    await actClick('Save preference');
    await waitFor(() => expect(onSubmitPreference).toHaveBeenCalledTimes(1));
    const request = onSubmitPreference.mock.calls[0][0] as ProjectPreferenceSetRequest;
    expect(request.schema).toBe('mastermind.project_preference_set_request.v1');
    expect(request.request_id).toBe(PREF_REQUEST_ID);
    expect(request.work_ref).toBe(WORK_REF);
    expect(request.source_commit).toBe(SOURCE_COMMIT);
    expect(request.base_revision).toBe(BASE_REVISION);
    expect(request.expected_preference_revision).toBe(PREF_REVISION);
    expect(request.value).toBe('  中文偏好 😀 ');
    expect(Object.isFrozen(request)).toBe(true);
  });

  it('preserves the initial literal value including CRLF from the parent', async () => {
    const literal = '第一行\r\n第二行';
    const { onSubmitPreference } = renderPreferenceEditor({ initialValue: literal });
    // The literal lives in component state, never re-read from the DOM, so the
    // DOM's value display cannot renormalize what is handed to the builder.
    expect(textarea().value.length).toBeGreaterThan(0);
    await actClick('Save preference');
    await waitFor(() => expect(onSubmitPreference).toHaveBeenCalledTimes(1));
    expect((onSubmitPreference.mock.calls[0][0] as ProjectPreferenceSetRequest).value).toBe(literal);
  });

  it('hands a null expected revision through as null', async () => {
    const { onSubmitPreference } = renderPreferenceEditor({ expectedPreferenceRevision: null });
    fireEvent.change(textarea(), { target: { value: 'plain' } });
    await actClick('Save preference');
    await waitFor(() => expect(onSubmitPreference).toHaveBeenCalledTimes(1));
    expect(
      (onSubmitPreference.mock.calls[0][0] as ProjectPreferenceSetRequest)
        .expected_preference_revision,
    ).toBeNull();
  });

  it('refuses a blank draft and never submits', async () => {
    const { onSubmitPreference } = renderPreferenceEditor();
    await actClick('Save preference');
    await waitFor(() => expect(screen.getByRole('status')).not.toBeNull());
    expect(screen.getByRole('status').textContent).toBe('The change was not saved.');
    expect(onSubmitPreference).not.toHaveBeenCalled();
  });

  it('refuses a draft over 2000 UTF-8 bytes', async () => {
    const { onSubmitPreference } = renderPreferenceEditor();
    fireEvent.change(textarea(), { target: { value: '中'.repeat(1200) } });
    await actClick('Save preference');
    await waitFor(() => expect(screen.getByRole('status')).not.toBeNull());
    expect(screen.getByRole('status').textContent).toBe('The change was not saved.');
    expect(onSubmitPreference).not.toHaveBeenCalled();
  });

  it('revision drift shows stale, preserves the draft, and never submits', () => {
    const { props, rerender } = renderPreferenceEditor();
    fireEvent.change(textarea(), { target: { value: '保留草稿' } });
    rerender(
      React.createElement(ProjectKnowledgeEditor, {
        ...props,
        expectedPreferenceRevision: OTHER_REVISION,
      }),
    );
    expect(screen.getByRole('status').textContent).toBe('This project changed. Your draft is kept.');
    expect(textarea().value).toBe('保留草稿');
    expect(buttonNamed('Save preference').disabled).toBe(true);
    fireEvent.click(buttonNamed('Save preference'));
    expect((props.onSubmitPreference as ReturnType<typeof vi.fn>).mock.calls.length).toBe(0);
  });

  it('a missing owner disables Save and says saving is unavailable', () => {
    renderPreferenceEditor({ onSubmitPreference: undefined });
    expect(buttonNamed('Save preference').disabled).toBe(true);
    expect(screen.getByText('Saving is unavailable.')).not.toBeNull();
  });
});

describe('identity and lifecycle', () => {
  it('an auth generation change clears the private draft before passive effects', () => {
    const { props, rerender } = renderPreferenceEditor();
    fireEvent.change(textarea(), { target: { value: '私有草稿' } });
    rerender(React.createElement(ProjectKnowledgeEditor, { ...props, authGeneration: 2 }));
    expect(textarea().value).toBe('');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('a typed host identity change clears the draft; the same text host does not', () => {
    const { props, rerender } = renderPreferenceEditor({ hostGeneration: '1' });
    fireEvent.change(textarea(), { target: { value: '草稿' } });
    // Same text identity: draft kept.
    rerender(React.createElement(ProjectKnowledgeEditor, { ...props, hostGeneration: '1' }));
    expect(textarea().value).toBe('草稿');
    // Number 1 is a different identity than string '1': body cleared.
    rerender(React.createElement(ProjectKnowledgeEditor, { ...props, hostGeneration: 1 }));
    expect(textarea().value).toBe('');
  });

  it('a work identity change clears the selected file and the draft', () => {
    const fileProps = renderFileEditor();
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('notes.md', 'hello'));
    fileProps.unmount();
    const { props, rerender } = renderPreferenceEditor();
    fireEvent.change(textarea(), { target: { value: '私有草稿' } });
    rerender(
      React.createElement(ProjectKnowledgeEditor, {
        ...props,
        sourceContext: { ...makeContext(), workRef: 'WS:OTHER' },
      }),
    );
    expect(textarea().value).toBe('');
  });

  it('parent phase props alone drive the public copy, and the draft survives each', () => {
    const cases: Array<[ProjectKnowledgeEditorPreferenceProps['phase'], string]> = [
      ['pending', 'Saving…'],
      ['proposal-published', 'Submitted for review. It is not saved to this project yet.'],
      ['source-published', 'Saved to this project.'],
      ['unknown', 'The outcome is not confirmed. Check the original operation.'],
      ['refused', 'The change was not saved.'],
      ['stale', 'This project changed. Your draft is kept.'],
    ];
    const { props, rerender } = renderPreferenceEditor({ initialValue: '起点' });
    for (const [phase, copy] of cases) {
      rerender(React.createElement(ProjectKnowledgeEditor, { ...props, phase }));
      expect(screen.getByRole('status').textContent).toBe(copy);
      expect(textarea().value).toBe('起点');
    }
  });

  it('every non-idle phase disables Save', () => {
    const phases: ProjectKnowledgeEditorPreferenceProps['phase'][] = [
      'pending',
      'unknown',
      'proposal-published',
      'source-published',
      'refused',
      'stale',
    ];
    const { props, rerender } = renderPreferenceEditor({ initialValue: 'x' });
    for (const phase of phases) {
      rerender(React.createElement(ProjectKnowledgeEditor, { ...props, phase }));
      expect(buttonNamed('Save preference').disabled).toBe(true);
    }
  });

  it('a resolved callback is only a handoff: local pending until the parent reports', async () => {
    const { onSubmitPreference, props, rerender } = renderPreferenceEditor({
      onSubmitPreference: vi.fn(async () => {}),
    });
    fireEvent.change(textarea(), { target: { value: '偏好' } });
    await actClick('Save preference');
    await waitFor(() => expect(onSubmitPreference).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('status').textContent).toBe('Saving…');
    expect(screen.queryByText('Saved to this project.')).toBeNull();
    rerender(React.createElement(ProjectKnowledgeEditor, { ...props, phase: 'source-published' }));
    expect(screen.getByRole('status').textContent).toBe('Saved to this project.');
  });

  it('a throw after the handoff means unknown: no retry, Check is explicit only', async () => {
    const { onSubmitPreference, props, rerender } = renderPreferenceEditor({
      onSubmitPreference: vi.fn(async () => {
        throw new Error('boom');
      }),
    });
    fireEvent.change(textarea(), { target: { value: '偏好' } });
    await actClick('Save preference');
    await waitFor(() => expect(screen.getByRole('status')).not.toBeNull());
    expect(screen.getByRole('status').textContent).toBe(
      'The outcome is not confirmed. Check the original operation.',
    );
    expect(buttonNamed('Save preference').disabled).toBe(true);
    expect(screen.queryByRole('button', { name: 'Check original operation' })).toBeNull();
    expect(document.body.textContent).not.toContain('boom');
    // The check affordance appears only with the actual callback, and is explicit.
    const onCheckOriginal=vi.fn();
    rerender(React.createElement(ProjectKnowledgeEditor, { ...props, onCheckOriginal }));
    const check = buttonNamed('Check original operation');
    fireEvent.click(check);
    await waitFor(() =>
      expect(onCheckOriginal).toHaveBeenCalledTimes(1),
    );
    expect(onCheckOriginal).toHaveBeenCalledWith();
    expect(buttonNamed('Save preference').disabled).toBe(true);
    expect(onSubmitPreference).toHaveBeenCalledTimes(1);
  });

  it('Cancel calls onClose once and clears nothing by itself', () => {
    const onClose = vi.fn();
    const { onSubmitPreference } = renderPreferenceEditor({ onClose });
    fireEvent.change(textarea(), { target: { value: '保留草稿' } });
    fireEvent.click(buttonNamed('Cancel'));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(textarea().value).toBe('保留草稿');
    expect(onSubmitPreference).not.toHaveBeenCalled();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('IME composition and Enter never submit; only the explicit button does', async () => {
    const { onSubmitPreference } = renderPreferenceEditor();
    const field = textarea();
    fireEvent.compositionStart(field);
    fireEvent.change(field, { target: { value: 'beam' } });
    fireEvent.keyDown(field, { key: 'Enter' });
    fireEvent.compositionEnd(field);
    fireEvent.keyDown(field, { key: 'Enter', keyCode: 13 });
    expect(onSubmitPreference).not.toHaveBeenCalled();
    expect(screen.queryByRole('status')).toBeNull();
    fireEvent.change(field, { target: { value: 'beam 好了' } });
    await actClick('Save preference');
    await waitFor(() => expect(onSubmitPreference).toHaveBeenCalledTimes(1));
  });

  it('a handoff resolving after unmount submits once and stays quiet', async () => {
    let resolveHandoff: (() => void) = ()=>{};
    const onSubmitFile = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveHandoff = resolve;
        }),
    );
    const { unmount } = renderFileEditor({ onSubmitFile });
    selectFile(screen.getByLabelText('Choose a file'), makeTextFile('notes.md', 'hello'));
    fireEvent.click(buttonNamed('Add file'));
    await waitFor(() => expect(onSubmitFile).toHaveBeenCalledTimes(1));
    unmount();
    resolveHandoff?.();
    await actOnly();
    expect(onSubmitFile).toHaveBeenCalledTimes(1);
  });

  it('an unmount during the file read leaves no submit and no rejection', async () => {
    const file = makeTextFile('slow.md', 'hello');
    const realRead = file.arrayBuffer.bind(file);
    let finish: (() => void) = ()=>{};
    Object.defineProperty(file, 'arrayBuffer', {
      value: () =>
        new Promise<ArrayBuffer>((resolve) => {
          finish = () => resolve(realRead());
        }),
      configurable: true,
    });
    const { onSubmitFile, unmount } = renderFileEditor();
    selectFile(screen.getByLabelText('Choose a file'), file);
    fireEvent.click(buttonNamed('Add file'));
    await actOnly();
    unmount();
    await actOnly();
    finish?.();
    await actOnly();
    expect(onSubmitFile).not.toHaveBeenCalled();
  });
});

describe('actual parent binding repairs',()=>{
 it.each(['sourceCommit','baseRevision','requestId','current','onSubmitPreference'] as const)('preserves the literal draft and prevents retarget after %s changes',field=>{
  const {props,rerender,onSubmitPreference}=renderPreferenceEditor({initialValue:'Original preference'});
  fireEvent.change(textarea(),{target:{value:'Keep my exact draft 中文'}});
  const changed={...props};
  if(field==='sourceCommit'||field==='baseRevision')changed.sourceContext={...props.sourceContext,[field]:field==='sourceCommit'?'e'.repeat(40):'e'.repeat(64)};
  else if(field==='requestId')changed.requestId='mmos-project-preference-set-'+'e'.repeat(40);
  else if(field==='current')changed.current=()=>makeContext();
  else changed.onSubmitPreference=vi.fn();
  rerender(React.createElement(ProjectKnowledgeEditor,changed));
  expect(textarea().value).toBe('Keep my exact draft 中文');expect(buttonNamed('Save preference').disabled).toBe(true);
  expect(screen.getByRole('status').textContent).toBe('This project changed. Your draft is kept.');expect(onSubmitPreference).not.toHaveBeenCalled();
 });
 it('re-proves preference source currency before handoff and preserves the draft on stale return',()=>{
  const {onSubmitPreference}=renderPreferenceEditor({current:()=>({...makeContext(),sourceCommit:'e'.repeat(40)})});
  fireEvent.change(textarea(),{target:{value:'Draft before stale source'}});fireEvent.click(buttonNamed('Save preference'));
  expect(onSubmitPreference).not.toHaveBeenCalled();expect(textarea().value).toBe('Draft before stale source');
  expect(screen.getByRole('status').textContent).toBe('This project changed. Your draft is kept.');
 });
 it('clears a previous principal preference even when the parent still supplies the old initialValue',()=>{
  const {props,rerender}=renderPreferenceEditor({initialValue:'Previous principal private preference'});
  rerender(React.createElement(ProjectKnowledgeEditor,{...props,authGeneration:99}));
  expect(textarea().value).toBe('');expect(document.body.textContent).not.toContain('Previous principal private preference');
 });
});

describe('owner-state presentation copy',()=>{
 it.each(['pending','unknown'] as const)('names closing the editor without cancelling %s original request',phase=>{
  const onClose=vi.fn();const {container}=renderPreferenceEditor({phase,onClose});
  expect(container.querySelector('section')!.lang).toBe('en');
  expect(screen.getByText('Closing does not cancel the original request.')).toBeTruthy();
  fireEvent.click(buttonNamed('Close editor'));expect(onClose).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button',{name:'Cancel'})).toBeNull();
 });
 it('shows prospective preservation and file bounds before saving',()=>{
  const pref=renderPreferenceEditor();expect(screen.getByText('Your text and line breaks will be preserved.')).toBeTruthy();pref.unmount();
  renderFileEditor();expect(screen.getByText('.md or .txt, up to 32 KiB. Choosing a file does not save it.')).toBeTruthy();
 });
 it('marks Chinese language and gives the same pending close semantics',()=>{
  const {container}=renderPreferenceEditor({locale:'zh-CN',phase:'unknown',onClose:vi.fn()});
  expect(container.querySelector('section')!.lang).toBe('zh-CN');expect(buttonNamed('关闭编辑器')).toBeTruthy();
  expect(screen.getByText('关闭编辑器不会取消原请求。')).toBeTruthy();
 });
});

describe('locale and styling contract', () => {
  it('renders the zh-CN labels and plain copy', () => {
    renderPreferenceEditor({
      locale: 'zh-CN',
      onClose: () => {},
      initialValue: '草稿',
    });
    expect(screen.getByLabelText('沟通偏好')).not.toBeNull();
    expect(buttonNamed('保存偏好')).not.toBeNull();
    expect(buttonNamed('取消')).not.toBeNull();
    expect(screen.getByText('来源详情')).not.toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });


});

/** Clicks a button by accessible name and flushes the synchronous state. */
async function actClick(name: string): Promise<void> {
  const button = buttonNamed(name);
  fireEvent.click(button);
  await actOnly();
}

/** A few settled microtask turns so builder reads and handoffs resolve. */
async function actOnly(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}


it.each(['en','zh-CN'] as const)('keeps literal draft when server preparation is unavailable without claiming a pending publication %s',locale=>{
 const context=makeContext();
 const props:ProjectKnowledgeEditorPreferenceProps={mode:'preference',sourceContext:context,requestId:PREF_REQUEST_ID,
  authGeneration:1,hostGeneration:1,current:currentSame,phase:'idle',initialValue:'Exact original\n中文',
  expectedPreferenceRevision:null,onSubmitPreference:vi.fn(),locale};
 const view=render(<ProjectKnowledgeEditor {...props}/>);
 const field=screen.getByRole('textbox');fireEvent.change(field,{target:{value:'Changed literal\n保留'}});
 view.rerender(<ProjectKnowledgeEditor {...props} phase="prepare-unavailable"/>);
 expect((field as HTMLTextAreaElement).value).toBe('Changed literal\n保留');
 expect(screen.getByRole('status').textContent).toContain(locale==='en'?'Nothing was submitted for publication':'尚未提交发布');
 expect(screen.queryByRole('button',{name:locale==='en'?'Check original operation':'检查原操作'})).toBeNull();
 expect(screen.getByRole('button',{name:locale==='en'?'Save preference':'保存偏好'}).hasAttribute('disabled')).toBe(true);
});

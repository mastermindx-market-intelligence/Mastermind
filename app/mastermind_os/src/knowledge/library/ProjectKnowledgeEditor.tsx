/**
 * ProjectKnowledgeEditor — the action-required editor surface over the project
 * knowledge write path.
 *
 * Two discriminated modes share one neutral panel:
 *   - mode 'file':        one explicitly user-selected browser File, added
 *                         through `buildProjectFileRequest`.
 *   - mode 'preference':  one literal communication preference value, saved
 *                         through `buildProjectPreferenceRequest`.
 *
 * Hard boundary: this component is presentation plus request construction
 * only. It owns no controller, store, transport, identifier minting or receipt
 * issuing. The parent owns the actual distinct grants, the existing v5
 * controller, the common events/publisher/currentness plumbing and the App
 * integration. The `requestId` is the parent's original paired-prefix
 * identifier and is never minted, randomized or retried here.
 *
 * Callback presence is NOT authority: the parent mounts this editor only when
 * the actual owner grant and port exist. A missing callback simply disables
 * Save and says so in plain copy. A resolved callback means the request was
 * handed to the owner — it is never proof of a save. A published phase
 * ('proposal-published' / 'source-published') only ever arrives through the
 * parent `phase` prop from outside this component; the chooser and the
 * resolved callback never fabricate an uploaded/saved result.
 *
 * Identity: the source context, the expected preference revision, the request
 * id and the method identities (`current` and the submit callback) are bound
 * when the editor opens and are never retargeted. An auth/host/work/mode
 * identity change re-keys the core render, which clears the private editor
 * body before any passive effect runs. Typed identity is respected: host `1`
 * and host `'1'` are different identities.
 *
 * This component imports its scoped stylesheet; the shell owns outer layout.
 */

import { useEffect, useId, useRef, useState } from 'react';
import './knowledge-editor.css';
import type { ChangeEvent } from 'react';

import {
  buildProjectFileRequest,
  buildProjectPreferenceRequest,
  KnowledgeInputError,
} from './project-knowledge-requests';
import type {
  KnowledgeInputErrorCode,
  ProjectFileAddRequest,
  ProjectKnowledgeSourceContext,
  ProjectPreferenceSetRequest,
  ProjectSourceCurrentFn,
} from './project-knowledge-requests';

/** Parent-owned edit lifecycle phase, as reported from outside this component. */
export type KnowledgeEditPhase =
  | 'idle'
  | 'pending'
  | 'prepared'
  | 'prepare-unavailable'
  | 'publication-held'
  | 'unknown'
  | 'proposal-published'
  | 'source-published'
  | 'refused'
  | 'stale';

/** Supported editor locales. */
export type KnowledgeEditorLocale = 'en' | 'zh-CN';

/** Props shared by both editor modes. */
export interface ProjectKnowledgeEditorBaseProps {
  /** Exact three-field source context, bound at editor open; never retargeted. */
  sourceContext: ProjectKnowledgeSourceContext;
  /** The parent's original request id with the exact paired prefix; never minted. */
  requestId: string;
  /** Owner auth generation; a change clears the private editor body. */
  authGeneration: number;
  /** Owner host generation, typed; `1` and `'1'` are different identities. */
  hostGeneration: string | number | null;
  /** Interface locale; defaults to English. */
  locale?: KnowledgeEditorLocale;
  /** Actual source-currency callback handed to the request builders. */
  current: ProjectSourceCurrentFn;
  /** Parent-owned lifecycle phase; the only source of published outcomes. */
  phase: KnowledgeEditPhase;
  /** Cancels edit presentation only; never clears the original pending operation. */
  onClose?: () => void;
  /** Explicit unknown-outcome check; presence gates the check button. */
  onCheckOriginal?: () => void;
}

/** File-mode props: one explicitly selected browser File. */
export interface ProjectKnowledgeEditorFileProps extends ProjectKnowledgeEditorBaseProps {
  mode: 'file';
  onSubmitFile?: (request: ProjectFileAddRequest) => Promise<void> | void;
}

/** Preference-mode props: one literal communication preference value. */
export interface ProjectKnowledgeEditorPreferenceProps extends ProjectKnowledgeEditorBaseProps {
  mode: 'preference';
  initialValue: string;
  expectedPreferenceRevision: string | null;
  onSubmitPreference?: (request: ProjectPreferenceSetRequest) => Promise<void> | void;
}

/** Discriminated editor props. */
export type ProjectKnowledgeEditorProps =
  | ProjectKnowledgeEditorFileProps
  | ProjectKnowledgeEditorPreferenceProps;

/** Field separator for the composite identity key; never appears in the fields. */
const IDENTITY_SEPARATOR = '\u001f';

/** Typed host identity part: the type tag keeps `1` and `'1'` distinct. */
function hostIdentityPart(hostGeneration: string | number | null): string {
  if (hostGeneration === null) return 'null:';
  return `${typeof hostGeneration}:${String(hostGeneration)}`;
}

/**
 * Composite identity of one editor binding. Any change re-keys the core
 * render, clearing the private editor body during that keyed render — before
 * any passive effect of the previous core can run.
 */
function buildIdentityKey(props: ProjectKnowledgeEditorProps): string {
  return [
    String(props.authGeneration),
    hostIdentityPart(props.hostGeneration),
    props.mode,
    props.sourceContext.workRef,
  ].join(IDENTITY_SEPARATOR);
}

/** Normalized core props; the discriminated union collapses to these. */
interface EditorCoreProps {
  mode: 'file' | 'preference';
  sourceContext: ProjectKnowledgeSourceContext;
  requestId: string;
  authGeneration: number;
  hostGeneration: string | number | null;
  locale: KnowledgeEditorLocale;
  current: ProjectSourceCurrentFn;
  phase: KnowledgeEditPhase;
  onClose?: () => void;
  onCheckOriginal?: () => void;
  submitFile?: (request: ProjectFileAddRequest) => Promise<void> | void;
  submitPreference?: (request: ProjectPreferenceSetRequest) => Promise<void> | void;
  /** Preference draft bound at open; the exact parent value, never normalized. */
  initialPreferenceValue: string;
  /** Expected preference revision bound at open; `null` in file mode. */
  boundPreferenceRevision: string | null;
}

/** Snapshot of the owner identities a submit depends on, captured before any await. */
interface SubmitWitness {
  authGeneration: number;
  hostGeneration: string | number | null;
  workRef: string;
  sourceCommit: string;
  baseRevision: string;
  requestId: string;
  boundRevision: string | null;
  current: ProjectSourceCurrentFn;
  submitFile: EditorCoreProps['submitFile'];
  submitPreference: EditorCoreProps['submitPreference'];
}

function EditorCore(props: EditorCoreProps) {
  const {
    mode,
    locale,
    phase,
    sourceContext,
    requestId,
    authGeneration,
    hostGeneration,
    current,
    onClose,
    onCheckOriginal,
    submitFile,
    submitPreference,
    initialPreferenceValue,
    boundPreferenceRevision,
  } = props;
  const zh = locale === 'zh-CN';
  const fieldId = useId();

  // --- Binding at editor open -------------------------------------------
  // The wrapper re-keys this component when the auth/host/work/mode identity
  // changes, so mount state below IS the open binding. It is never retargeted.

  // The literal preference draft: never trimmed, normalized or re-read from
  // props after open; it survives every outcome and rerender.
  const [preferenceDraft, setPreferenceDraft] = useState(initialPreferenceValue);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [building, setBuilding] = useState(false);
  const [handedOff, setHandedOff] = useState(false);
  const [handoffThrew, setHandoffThrew] = useState(false);
  const [sourceDrifted, setSourceDrifted] = useState(false);
  const [refusalCode, setRefusalCode] = useState<KnowledgeInputErrorCode | null>(null);
  const [boundRevision] = useState(boundPreferenceRevision);
  const [bindingAtOpen]=useState(()=>({sourceCommit:sourceContext.sourceCommit,baseRevision:sourceContext.baseRevision,
    requestId,current,submitFile,submitPreference}));
  const bindingDrift=sourceContext.sourceCommit!==bindingAtOpen.sourceCommit || sourceContext.baseRevision!==bindingAtOpen.baseRevision ||
    requestId!==bindingAtOpen.requestId || current!==bindingAtOpen.current || submitFile!==bindingAtOpen.submitFile || submitPreference!==bindingAtOpen.submitPreference;

  // Owner generation / method identities as of the latest render.
  const latestRef = useRef({
    authGeneration,
    hostGeneration,
    workRef: sourceContext.workRef,
    sourceCommit: sourceContext.sourceCommit,
    baseRevision: sourceContext.baseRevision,
    requestId,
    boundRevision,
    current,
    submitFile,
    submitPreference,
  });
  latestRef.current = {
    authGeneration,
    hostGeneration,
    workRef: sourceContext.workRef,
    sourceCommit: sourceContext.sourceCommit,
    baseRevision: sourceContext.baseRevision,
    requestId,
    boundRevision,
    current,
    submitFile,
    submitPreference,
  };

  // Unmount abort. `mountedRef` also gates every continuation after an await.
  const mountedRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const attemptRef = useRef(false);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  // Revision drift is derived, not state: the expected preference revision is
  // bound at open, and a different prop makes the binding stale while the
  // literal draft is preserved. The submit stays disabled; no retargeting.
  const revisionDrift =
    mode === 'preference' && boundPreferenceRevision !== boundRevision;

  // Owner-authoritative phase first; local overlays only fill the gap while
  // the parent still reports idle. A resolved callback is a handoff, not a
  // save; a callback that throws after the handoff leaves the outcome UNKNOWN.
  const owner = mode === 'file' ? submitFile : submitPreference;
  const effectivePhase: KnowledgeEditPhase =
    phase !== 'idle'
      ? phase
      : handoffThrew
        ? 'unknown'
        : handedOff || building
          ? 'pending'
          : revisionDrift || sourceDrifted || bindingDrift
            ? 'stale'
            : refusalCode !== null
              ? 'refused'
              : 'idle';

  const canSubmit = effectivePhase === 'idle' && owner !== undefined && !building && !bindingDrift && !revisionDrift;

  /** Captures the submit witness before any await. */
  const captureWitness = (): SubmitWitness => ({
    authGeneration: latestRef.current.authGeneration,
    hostGeneration: latestRef.current.hostGeneration,
    workRef: latestRef.current.workRef,
    sourceCommit: latestRef.current.sourceCommit,
    baseRevision: latestRef.current.baseRevision,
    requestId: latestRef.current.requestId,
    boundRevision: latestRef.current.boundRevision,
    current: latestRef.current.current,
    submitFile: latestRef.current.submitFile,
    submitPreference: latestRef.current.submitPreference,
  });

  /** True only if the owner generations, binding and method identities all hold. */
  const witnessHolds = (witness: SubmitWitness): boolean => {
    const now = latestRef.current;
    return (
      mountedRef.current &&
      Object.is(now.authGeneration, witness.authGeneration) &&
      Object.is(now.hostGeneration, witness.hostGeneration) &&
      now.requestId === witness.requestId &&
      now.workRef === witness.workRef &&
      now.sourceCommit === witness.sourceCommit &&
      now.baseRevision === witness.baseRevision &&
      Object.is(now.boundRevision, witness.boundRevision) &&
      now.current === witness.current &&
      now.submitFile === witness.submitFile &&
      now.submitPreference === witness.submitPreference
    );
  };

  /** Detached, frozen copy of the bound context handed to the builders. */
  const witnessContext = (witness: SubmitWitness): ProjectKnowledgeSourceContext =>
    Object.freeze({
      workRef: witness.workRef,
      sourceCommit: witness.sourceCommit,
      baseRevision: witness.baseRevision,
    });

  /** Maps a failed build onto closed public copy only; never input or error text. */
  const noteBuildError = (error: unknown): void => {
    if (error instanceof KnowledgeInputError) {
      if (error.code === 'CANCELLED') return; // aborted: draft kept, nothing claimed
      if (error.code === 'SOURCE_CHANGED') {
        setSourceDrifted(true);
        return;
      }
      setRefusalCode(error.code);
      return;
    }
    setRefusalCode('READ_FAILED');
  };

  /** File mode: explicit Add file — build, witness-check, then one handoff. */
  const handleAddFile = (): void => {
    if (attemptRef.current || !canSubmit) return;
    const witness = captureWitness();
    const submit = witness.submitFile;
    if (submit === undefined || selectedFile === null) return;
    const file = selectedFile;
    const controller = new AbortController();
    abortRef.current = controller;
    attemptRef.current = true;
    setBuilding(true);
    setRefusalCode(null);
    setSourceDrifted(false);
    const boundContext = witnessContext(witness);
    void (async () => {
      let request: ProjectFileAddRequest;
      try {
        // The builder re-proves currency before and after the one read and
        // fences on the owned abort signal; this component adds nothing.
        request = await buildProjectFileRequest(
          boundContext,
          witness.requestId,
          file,
          controller.signal,
          witness.current,
        );
      } catch (error: unknown) {
        if (!witnessHolds(witness)) { if(mountedRef.current){attemptRef.current=false;setBuilding(false);setSourceDrifted(true);} return; }
        attemptRef.current = false;
        abortRef.current = null;
        setBuilding(false);
        noteBuildError(error);
        return;
      }
      // Same captured witness, re-proven after the await and before the handoff.
      if (!witnessHolds(witness)) { if(mountedRef.current){attemptRef.current=false;setBuilding(false);setSourceDrifted(true);} return; }
      attemptRef.current = false;
      abortRef.current = null;
      setBuilding(false);
      setHandedOff(true); // parent may still report idle: pending is shown locally
      try {
        await submit(request);
      } catch {
        // A throw after the handoff means the outcome is UNKNOWN, not no-effect.
        if (!witnessHolds(witness)) return;
        setHandoffThrew(true);
      }
    })();
  };

  /** Preference mode: explicit Save preference — build, witness-check, handoff. */
  const handleSavePreference = (): void => {
    if (attemptRef.current || !canSubmit) return;
    const witness = captureWitness();
    const submit = witness.submitPreference;
    if (submit === undefined) return;
    const boundContext = witnessContext(witness);
    let request: ProjectPreferenceSetRequest;
    try {
      // The exact literal draft is handed to the builder: no trimming,
      // normalization or extraction happens anywhere in this component.
      request = buildProjectPreferenceRequest(
        boundContext,
        witness.requestId,
        witness.boundRevision,
        preferenceDraft,
      );
    } catch (error: unknown) {
      noteBuildError(error);
      return;
    }
    // Preference construction is synchronous; unlike the File builder it has
    // no built-in current-source callback. Re-prove it at this handoff.
    try {
      const now=witness.current(boundContext);
      const descriptors=Object.getOwnPropertyDescriptors(now);
      if(Object.keys(descriptors).sort().join('|')!=='baseRevision|sourceCommit|workRef' ||
        (Object.getPrototypeOf(now)!==Object.prototype && Object.getPrototypeOf(now)!==null) || Object.getOwnPropertySymbols(now).length!==0 ||
        Object.values(descriptors).some(d=>!('value' in d)||!d.enumerable) ||
        descriptors.workRef.value!==boundContext.workRef || descriptors.sourceCommit.value!==boundContext.sourceCommit ||
        descriptors.baseRevision.value!==boundContext.baseRevision || !witnessHolds(witness)) {
        setSourceDrifted(true); return;
      }
    } catch { setSourceDrifted(true); return; }
    setHandedOff(true); // parent may still report idle: pending is shown locally
    void (async () => {
      try {
        await submit(request);
      } catch {
        if (!witnessHolds(witness)) return;
        setHandoffThrew(true);
      }
    })();
  };

  /** Explicit user selection only: a chooser event with no file keeps the prior pick. */
  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const files = event.target.files;
    if (files === null || files.length === 0) return;
    let next: File | null = null;
    try {
      next = files.item(0);
    } catch {
      next = null;
    }
    if (next === null) {
      const first: unknown = files[0];
      next = typeof first === 'object' && first !== null ? (first as File) : null;
    }
    if (next === null) return;
    setSelectedFile(next); // the File handle only; the body is read by the builder
  };

  // Safe closed read of the selected file's display metadata.
  let selectedName = '';
  let selectedBytes = 0;
  if (selectedFile !== null) {
    try {
      const name: unknown = selectedFile.name;
      const size: unknown = selectedFile.size;
      selectedName = typeof name === 'string' ? name : '';
      selectedBytes = typeof size === 'number' && Number.isSafeInteger(size) ? size : 0;
    } catch {
      selectedName = '';
      selectedBytes = 0;
    }
  }

  // --- Closed public copy ------------------------------------------------
  const statusCopy = (() => {
    switch (effectivePhase) {
      case 'prepared':
        return zh ? '更改已准备好供你检查，尚未发布。' : 'Your changes are prepared for review. Nothing has been published.';
      case 'publication-held':
        return zh ? '之前的项目操作尚未确定。请先使用它的原始控件检查；这些更改尚未提交发布。' : 'A previous project action is unresolved. Use its original controls first; these changes have not been submitted for publication.';
      case 'prepare-unavailable':
        return zh ? '暂时无法准备更改。尚未提交发布，你的草稿已保留。' : 'Your changes could not be prepared. Nothing was submitted for publication. Your draft is kept.';
      case 'pending':
        return zh ? '正在保存…' : 'Saving…';
      case 'proposal-published':
        return zh
          ? '已提交评审。尚未保存到此项目。'
          : 'Submitted for review. It is not saved to this project yet.';
      case 'source-published':
        return zh ? '已保存到此项目。' : 'Saved to this project.';
      case 'unknown':
        return zh ? '结果未确认。请检查原操作。' : 'The outcome is not confirmed. Check the original operation.';
      case 'refused':
        return zh ? '更改未保存。' : 'The change was not saved.';
      case 'stale':
        return zh ? '此项目已更改。您的草稿已保留。' : 'This project changed. Your draft is kept.';
      default:
        return null;
    }
  })();

  const heading = mode === 'file' ? (zh ? '添加文件' : 'Add file') : zh ? '沟通偏好' : 'Communication preference';
  const chooseLabel = zh ? '选择文件' : 'Choose a file';
  const preferenceLabel = zh ? '沟通偏好' : 'Communication preference';
  const primaryLabel = mode === 'file' ? (zh ? '添加文件' : 'Add file') : zh ? '保存偏好' : 'Save preference';
  const checkLabel = zh ? '检查原操作' : 'Check original operation';
  const originalInFlight = effectivePhase==='pending' || effectivePhase==='unknown' || effectivePhase==='proposal-published';
  const cancelLabel = originalInFlight || effectivePhase==='source-published' ? (zh ? '关闭编辑器' : 'Close editor') : (zh ? '取消' : 'Cancel');
  const unavailableCopy = zh ? '保存功能不可用。' : 'Saving is unavailable.';
  const noSelectionCopy = zh ? '尚未选择文件。' : 'No file is selected yet.';
  const selectedNoteCopy = zh ? '已选择，尚未保存。' : 'Selected — not saved yet.';
  const bytesUnit = zh ? '字节' : 'bytes';
  const preferenceHintCopy = zh ? '将保留你的文字和换行。' : 'Your text and line breaks will be preserved.';
  const detailsSummary = zh ? '来源详情' : 'Source details';

  const rootClassName = zh ? 'knowledge-editor knowledge-editor--zh' : 'knowledge-editor';
  const canClickPrimary = canSubmit && (mode === 'preference' || selectedFile !== null);

  return (
    <section
      className={rootClassName}
      lang={zh ? 'zh-CN' : 'en'}
      data-knowledge-editor-mode={mode}
      data-knowledge-editor-phase={effectivePhase}
    >
      <h2 className="knowledge-editor-heading">{heading}</h2>

      {mode === 'file' ? (
        <div className="knowledge-editor-field">
          <label className="knowledge-editor-label" htmlFor={`${fieldId}-file`}>
            {chooseLabel}
          </label>
          {/* Native chooser, single selection; no drag, no bulk, no remote URL,
              no filesystem path. The accept list mirrors the builder's trusted
              extension mapping. Enter on the chooser never submits anything. */}
          <input
            id={`${fieldId}-file`}
            className="knowledge-editor-file"
            type="file"
            accept=".md,.txt,text/markdown,text/plain"
            onChange={handleFileInputChange}
          />
          <p className="knowledge-editor-hint">{zh ? 'Markdown 或纯文本（.md/.txt），不超过32KiB；选择文件不会保存。' : '.md or .txt, up to 32 KiB. Choosing a file does not save it.'}</p>
          {selectedFile === null ? (
            <p className="knowledge-editor-hint">{noSelectionCopy}</p>
          ) : (
            <div className="knowledge-editor-selected">
              <span className="knowledge-editor-selected-name">{selectedName}</span>
              <span className="knowledge-editor-selected-meta">
                {selectedBytes} {bytesUnit}
              </span>
              <span className="knowledge-editor-selected-note">{selectedNoteCopy}</span>
            </div>
          )}
        </div>
      ) : (
        <div className="knowledge-editor-field">
          <label className="knowledge-editor-label" htmlFor={`${fieldId}-value`}>
            {preferenceLabel}
          </label>
          {/* The literal draft. No Enter handler exists, so IME Enter and any
              other Enter are just text; submission is the explicit button only. */}
          <textarea
            id={`${fieldId}-value`}
            className="knowledge-editor-textarea"
            value={preferenceDraft}
            onChange={(event) => setPreferenceDraft(event.target.value)}
            rows={6}
          />
          <p className="knowledge-editor-hint">{preferenceHintCopy}</p>
        </div>
      )}

      {owner === undefined ? (
        <p className="knowledge-editor-unavailable">{unavailableCopy}</p>
      ) : null}

      {statusCopy !== null ? (
        <p className="knowledge-editor-status" role="status" aria-live="polite">
          {statusCopy}
        </p>
      ) : null}

      <div className="knowledge-editor-actions">
        <button
          type="button"
          className="knowledge-editor-button knowledge-editor-button--primary"
          disabled={!canClickPrimary}
          onClick={mode === 'file' ? handleAddFile : handleSavePreference}
        >
          {primaryLabel}
        </button>
        {effectivePhase === 'unknown' && onCheckOriginal !== undefined ? (
          <button
            type="button"
            className="knowledge-editor-button"
            onClick={() => {
              onCheckOriginal();
            }}
          >
            {checkLabel}
          </button>
        ) : null}
        {onClose !== undefined ? (
          <button
            type="button"
            className="knowledge-editor-button"
            onClick={() => {
              // Cancel discards edit presentation only, through the parent's
              // own callback. It never clears the original pending operation
              // and never cancels an effect.
              onClose();
            }}
          >
            {cancelLabel}
          </button>
        ) : null}
      </div>

      {originalInFlight && onClose ? <p className="knowledge-editor-hint">{zh ? '关闭编辑器不会取消原请求。' : 'Closing does not cancel the original request.'}</p> : null}

      <details className="knowledge-editor-details">
        <summary>{detailsSummary}</summary>
        <pre>
          {`workRef ${sourceContext.workRef}
sourceCommit ${sourceContext.sourceCommit}
baseRevision ${sourceContext.baseRevision}`}
          {mode === 'preference' ? `\nexpectedPreferenceRevision ${boundRevision ?? 'null'}` : ''}
          {refusalCode !== null ? `\ncode ${refusalCode}` : ''}
        </pre>
      </details>
    </section>
  );
}

/**
 * The exported editor. The composite identity re-keys the core: an
 * auth/host/work/mode identity change mounts a fresh core, which clears the
 * private editor body during that keyed render — before any passive effect of
 * the previous core runs.
 */
export function ProjectKnowledgeEditor(props: ProjectKnowledgeEditorProps) {
  const identityKey = buildIdentityKey(props);
  const previousIdentity=useRef(identityKey);
  const changedIdentity=previousIdentity.current!==identityKey;
  previousIdentity.current=identityKey;
  if (props.mode === 'file') {
    return (
      <EditorCore
        key={identityKey}
        mode="file"
        sourceContext={props.sourceContext}
        requestId={props.requestId}
        authGeneration={props.authGeneration}
        hostGeneration={props.hostGeneration}
        locale={props.locale ?? 'en'}
        current={props.current}
        phase={props.phase}
        onClose={props.onClose}
        onCheckOriginal={props.onCheckOriginal}
        submitFile={props.onSubmitFile}
        initialPreferenceValue=""
        boundPreferenceRevision={null}
      />
    );
  }
  return (
    <EditorCore
      key={identityKey}
      mode="preference"
      sourceContext={props.sourceContext}
      requestId={props.requestId}
      authGeneration={props.authGeneration}
      hostGeneration={props.hostGeneration}
      locale={props.locale ?? 'en'}
      current={props.current}
      phase={props.phase}
      onClose={props.onClose}
      onCheckOriginal={props.onCheckOriginal}
      submitPreference={props.onSubmitPreference}
      initialPreferenceValue={changedIdentity ? "" : props.initialValue}
      boundPreferenceRevision={props.expectedPreferenceRevision}
    />
  );
}

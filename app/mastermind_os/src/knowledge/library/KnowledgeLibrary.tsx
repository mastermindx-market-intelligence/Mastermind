/**
 * Knowledge Library — bounded read consumer for project Files / Memory /
 * records, with typed parent action handoffs.
 *
 * This leaf owns no upload, publication, auth, storage or lifecycle
 * authority. Reads only run through the owner-supplied ports; Add files and
 * Edit preference only forward explicit typed callbacks. A missing or
 * out-of-scope port renders a local typed unavailable state — it never
 * invents an owner denial, sample data or a saved result.
 *
 * Identity (auth generation, host generation, work ref, wired read methods,
 * refresh key) keys the whole private body: a replacement clears the private
 * DOM before effects and paint, aborts in-flight reads and retires tickets.
 * Locale and theme are not identity — the user's view and query survive them.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ComponentType, MouseEvent as ReactMouseEvent, ReactNode } from 'react';
import './knowledge-library.css';
import {captureProjectSourceDraftRead, completeProjectSourceDraftRead, type ProjectSourceDraftProof} from './project-source-draft';
import {ProjectSourceDraftCompanion} from './ProjectSourceDraftCompanion';
import {sameKnowledgeCodeContext,type ProjectKnowledgeReadMetadata} from './project-data-observation';
import {readProjectFileMatchSource} from '../../discovery/project-file-open';
import {
  KnowledgeContractError,
  knowledgeLibraryCopy,
  reasonPublicCopy,
  sha256Hex,
  unavailableActions,
  unavailableCatalogue,
  unavailableMemory,
  unavailableSource,
  validate_actions,
  validate_catalogue,
  validate_memory,
  validate_source,
} from './knowledge-library-contract';
import type {
  KnowledgeActionsResult,
  KnowledgeCatalogue,
  KnowledgeCatalogueResult,
  KnowledgeCatalogueFileRow,
  KnowledgeCatalogueRecordRow,
  KnowledgeLibraryLocale,
  KnowledgeLibraryProps,
  KnowledgeLibrarySourceContext,
  KnowledgeLibraryTheme,
  KnowledgeMemoryResult,
  KnowledgeRecordKind,
  KnowledgeSourceResult,
  ProjectMemoryDocument,
} from './knowledge-library-contract';

function readMetadataLines(value:ProjectKnowledgeReadMetadata|null|undefined):string[]{
  if(!value)return [];
  return [value.codeContext?`code_context: ${JSON.stringify(value.codeContext)}`:null,
    value.dataObservation?`data_observation: ${JSON.stringify(value.dataObservation)}`:null].filter((line):line is string=>line!==null);
}

/* ------------------------------------------------------------------ */
/* Read-family state                                                   */
/* ------------------------------------------------------------------ */

type ReadPhase =
  | 'IDLE'
  | 'LOADING'
  | 'READY'
  | 'UNAVAILABLE'
  | 'EMPTY'
  | 'OWNER_UNAVAILABLE'
  | 'INVALID_PAYLOAD'
  | 'FAILED'
  | 'STALE'
  | 'TAMPER';

interface ReadState<T> {
  readonly phase: ReadPhase;
  readonly result: T | null;
  /** Closed local/backed diagnostic codes; rendered only inside details. */
  readonly detail: readonly string[];
}

function initialRead<T>(): ReadState<T> {
  return { phase: 'IDLE', result: null, detail: [] };
}

interface ReadHandle {
  seq: number;
  controller: AbortController;
}

/** One guarded-read lane per family: ticketed, abortable, StrictMode-safe. */
function useGuardedRead() {
  const seqRef = useRef(0);
  const activeRef = useRef<AbortController|null>(null);
  const cancel = useCallback(() => { seqRef.current++; activeRef.current?.abort(); activeRef.current=null; },[]);
  const begin = useCallback((): ReadHandle => {
    activeRef.current?.abort();
    const seq = ++seqRef.current, controller = new AbortController();
    activeRef.current=controller;
    return { seq, controller };
  }, []);
  const isCurrent = useCallback((handle: ReadHandle) => {
    return seqRef.current === handle.seq && !handle.controller.signal.aborted;
  }, []);
  useEffect(
    () => cancel,
    [cancel],
  );
  return useMemo(() => ({ begin, isCurrent, cancel }), [begin, isCurrent, cancel]);
}

/* ------------------------------------------------------------------ */
/* Identity and scope                                                  */
/* ------------------------------------------------------------------ */

const METHOD_IDS = new WeakMap<object, number>();
let METHOD_SEQ = 0;

function methodIdentity(fn: unknown): string {
  if ((typeof fn !== 'function' && typeof fn !== 'object') || fn === null) return 'absent';
  let id = METHOD_IDS.get(fn);
  if (id === undefined) {
    id = ++METHOD_SEQ;
    METHOD_IDS.set(fn, id);
  }
  return `fn:${id}`;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** Typed host/work scope gate: invalid scope renders local unavailable. */
function resolveScopeError(props: KnowledgeLibraryProps): string | null {
  if (!Number.isSafeInteger(props.authGeneration) || props.authGeneration < 0) return 'AUTH_GENERATION_INVALID';
  const host = props.hostGeneration;
  if (!((typeof host === 'string' && host.length > 0) ||
      (typeof host === 'number' && Number.isFinite(host)))) return 'HOST_GENERATION_INVALID';
  if (typeof props.workRef !== 'string' || !/^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/.test(props.workRef))
    return 'WORK_REF_INVALID';
  return null;
}

interface BodyProps {
  readonly onCurrentSourceOwner?: KnowledgeLibraryProps['onCurrentSourceOwner'];
  readonly draftPort?: KnowledgeLibraryProps['draftPort'];
  readonly requestedFile?: KnowledgeLibraryProps['requestedFile'];
  readonly fileSearchOwner?: KnowledgeLibraryProps['fileSearchOwner'];
  readonly onReturnToSearch?: KnowledgeLibraryProps['onReturnToSearch'];
  readonly identity: string;
  readonly workRef: string | null;
  readonly authGeneration: number;
  readonly hostGeneration: string|number|null;
  readonly locale: KnowledgeLibraryLocale;
  readonly theme: KnowledgeLibraryTheme;
  readonly scopeError: string | null;
  readonly readCatalogue?: KnowledgeLibraryProps['readCatalogue'];
  readonly readSource?: KnowledgeLibraryProps['readSource'];
  readonly readMemory?: KnowledgeLibraryProps['readMemory'];
  readonly readActions?: KnowledgeLibraryProps['readActions'];
  readonly onAddFiles?: KnowledgeLibraryProps['onAddFiles'];
  readonly onEditPreference?: KnowledgeLibraryProps['onEditPreference'];
  readonly renderSourceCompanion?: KnowledgeLibraryProps['renderSourceCompanion'];
}

/* ------------------------------------------------------------------ */
/* Optional existing markdown reader (lazy, failure falls back plain)   */
/* ------------------------------------------------------------------ */

type MarkdownComponent = ComponentType<{ source: string; locale?: KnowledgeLibraryLocale }>;
let sourceMarkdownModule: MarkdownComponent | null | undefined;

/**
 * Lazy import of the existing safe SourceMarkdown reader. Resolved at runtime
 * through an ignored specifier so a host without that module still renders
 * (plain, wrap-safe exact pre) instead of failing the slice.
 */
async function loadSourceMarkdown(): Promise<MarkdownComponent | null> {
  if (sourceMarkdownModule !== undefined) return sourceMarkdownModule;
  try {
    const mod = await import('../../conversations/SourceMarkdown');
    const candidate = mod.SourceMarkdown;
    sourceMarkdownModule = typeof candidate === 'function' ? (candidate as MarkdownComponent) : null;
  } catch {
    sourceMarkdownModule = null;
  }
  return sourceMarkdownModule;
}

/* ------------------------------------------------------------------ */
/* Presentation helpers (metadata only; no sample data)                 */
/* ------------------------------------------------------------------ */

const RECORD_KIND_LABELS: Record<KnowledgeRecordKind, Record<KnowledgeLibraryLocale, string>> = {
  WORKSTREAM: { en: 'Workstream', 'zh-CN': '工作流' },
  DECISION: { en: 'Decision', 'zh-CN': '决定' },
  DISCOVERY: { en: 'Discovery', 'zh-CN': '发现' },
  HANDOFF: { en: 'Handoff', 'zh-CN': '交接' },
  PROJECT_PREFERENCE: { en: 'Project preference', 'zh-CN': '项目偏好' },
};

function recordKindLabel(kind: KnowledgeRecordKind, locale: KnowledgeLibraryLocale): string {
  return RECORD_KIND_LABELS[kind][locale];
}

/** Upload provenance: only the actual owner's CURRENT_PRINCIPAL says "you". */
function fileProvenance(row: KnowledgeCatalogueFileRow, locale: KnowledgeLibraryLocale): string {
  const copy = knowledgeLibraryCopy(locale);
  if (row.origin.kind === 'PRINCIPAL_UPLOAD') {
    if (row.viewerRelation === 'CURRENT_PRINCIPAL') return copy.addedByYou;
    if (row.viewerRelation === 'OTHER_PRINCIPAL') return copy.addedByOther;
    return copy.uploadedFile;
  }
  return copy.declaredArtifact;
}

function isRowOpenable(
  row: KnowledgeCatalogueFileRow | KnowledgeCatalogueRecordRow,
  readSource: BodyProps['readSource'],
): boolean {
  return (!('state' in row) || row.state === 'READABLE') && row.revision !== null &&
    row.revision !== undefined && typeof readSource === 'function';
}

function rowExists(
  catalogue: KnowledgeCatalogue,
  sourceRef: string,
  expectedRevision: string,
): boolean {
  return (
    catalogue.files.some((row) => row.sourceRef === sourceRef && row.revision === expectedRevision) ||
    catalogue.records.some((row) => row.sourceRef === sourceRef && row.revision === expectedRevision)
  );
}

function matchFileQuery(row: KnowledgeCatalogueFileRow, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) return true;
  return row.displayName.toLowerCase().includes(needle);
}

function matchRecordQuery(row: KnowledgeCatalogueRecordRow, query: string, locale: KnowledgeLibraryLocale): boolean {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) return true;
  const haystack = [row.title, recordKindLabel(row.kind, locale), row.authoredAt ?? '']
    .join(' ')
    .toLowerCase();
  return haystack.includes(needle);
}

/* ------------------------------------------------------------------ */
/* Root component: scope gate + identity-keyed private body             */
/* ------------------------------------------------------------------ */

export function KnowledgeLibrary(props: KnowledgeLibraryProps) {
  const scopeError = resolveScopeError(props);
  const locale: KnowledgeLibraryLocale = props.locale === 'zh-CN' ? 'zh-CN' : 'en';
  const theme: KnowledgeLibraryTheme = props.theme === 'light' ? 'light' : 'dark';
  const identity = useMemo(
    () =>
      JSON.stringify([
        props.workRef,
        props.authGeneration,
        typeof props.hostGeneration, props.hostGeneration,
        props.refreshKey ?? null,
        methodIdentity(props.readCatalogue),
        methodIdentity(props.readSource),
        methodIdentity(props.readMemory),
        methodIdentity(props.readActions),
        methodIdentity(props.requestedFile),
        methodIdentity(props.fileSearchOwner),
      ]),
    [
      props.workRef,
      props.authGeneration,
      props.hostGeneration,
      props.refreshKey,
      props.readCatalogue,
      props.readSource,
      props.readMemory,
      props.readActions,
      props.requestedFile,
      props.fileSearchOwner,
    ],
  );

  const className = ['knowledge-library', locale === 'zh-CN' ? 'knowledge-library--zh' : ''].filter(Boolean).join(' ');

  return (
    <section
      className={className}
      data-knowledge-theme={theme}
      lang={locale === 'zh-CN' ? 'zh-CN' : undefined}
    >
      <KnowledgeLibraryBody
        key={identity}
        identity={identity}
        draftPort={props.draftPort}
        onCurrentSourceOwner={props.onCurrentSourceOwner}
        workRef={props.workRef}
        authGeneration={props.authGeneration}
        hostGeneration={props.hostGeneration}
        locale={locale}
        theme={theme}
        scopeError={scopeError}
        readCatalogue={props.readCatalogue}
        readSource={props.readSource}
        readMemory={props.readMemory}
        readActions={props.readActions}
        onAddFiles={props.onAddFiles}
        onEditPreference={props.onEditPreference}
        renderSourceCompanion={props.renderSourceCompanion}
        requestedFile={props.requestedFile}
        fileSearchOwner={props.fileSearchOwner}
        onReturnToSearch={props.onReturnToSearch}
      />
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Private body: all state lives here and dies with the identity key    */
/* ------------------------------------------------------------------ */

function KnowledgeLibraryBody(props: BodyProps) {
  const { identity, workRef, locale, theme, scopeError } = props;
  const copy = knowledgeLibraryCopy(locale);

  const [catalogueState, setCatalogueState] = useState<ReadState<KnowledgeCatalogueResult>>(() =>
    initialRead<KnowledgeCatalogueResult>(),
  );
  const [actionsState, setActionsState] = useState<{ result: KnowledgeActionsResult | null; detail: readonly string[] }>({
    result: null,
    detail: [],
  });
  const [memoryState, setMemoryState] = useState<ReadState<KnowledgeMemoryResult>>(() => initialRead<KnowledgeMemoryResult>());
  const [sourceState, setSourceState] = useState<ReadState<KnowledgeSourceResult>>(() => initialRead<KnowledgeSourceResult>());
  const [tab, setTab] = useState<'FILES' | 'MEMORY'>('FILES');
  const [view, setView] = useState<'LIST' | 'RECORDS' | 'READER'>('LIST');
  const [readerOrigin, setReaderOrigin] = useState<'LIST' | 'RECORDS'>('LIST');
  const [filesQuery, setFilesQuery] = useState('');
  const [recordsQuery, setRecordsQuery] = useState('');
  const [markdown, setMarkdown] = useState<MarkdownComponent | null>(null);
  const [openRow, setOpenRow] = useState<{ sourceRef: string; expectedRevision: string } | null>(null);

  const [draftProof,setDraftProof]=useState<ProjectSourceDraftProof|null>(null);
  const liveProps=useRef(props); liveProps.current=props;
  const bodyLive=useRef(false);
  const catalogueWitness=useRef<{catalogue:KnowledgeCatalogue;current:()=>boolean}|null>(null);
  useLayoutEffect(()=>{bodyLive.current=true;return()=>{bodyLive.current=false;catalogueWitness.current=null;};},[]);
  // This fixed host owner supplies current signed scope independently of the
  // destination draft. Missing owner remains a read-only presentation.
  function captureSourceGuard(handle:ReadHandle,isCurrent=sourceRead.isCurrent) {
    const owner=props.fileSearchOwner;
    if(!owner)return ()=>false;
    try {
      const methods=[owner.context,owner.authGeneration,owner.readCatalogue,owner.readSource] as const;
      const context=owner.context(),auth=owner.authGeneration();
      if(!context?.generation || !Number.isSafeInteger(auth))return ()=>false;
      return ()=>{
        if(!bodyLive.current||!isCurrent(handle)||liveProps.current.fileSearchOwner!==owner)return false;
        const now=owner.context();
        return !!now&&now.generation===context.generation&&owner.authGeneration()===auth&&
          owner.context===methods[0]&&owner.authGeneration===methods[1]&&owner.readCatalogue===methods[2]&&owner.readSource===methods[3];
      };
    }catch{return ()=>false;}
  }
  const memoryRequestedRef = useRef(false);
  const focusRestoreRef = useRef<HTMLElement | null>(null);
  const restoreFocusRef = useRef(false);
  useLayoutEffect(() => {
    if (view !== 'READER' && restoreFocusRef.current) {
      restoreFocusRef.current=false; focusRestoreRef.current?.focus();
    }
  },[view]);

  const catalogueRead = useGuardedRead();
  const actionsRead = useGuardedRead();
  const memoryRead = useGuardedRead();
  const sourceRead = useGuardedRead();

  const catalogue = catalogueState.phase === 'READY' ? catalogueState.result?.catalogue ?? null : null;
  useLayoutEffect(()=>{
    const witness=catalogueWitness.current;
    const registration=props.onCurrentSourceOwner;
    if(!registration)return;
    if(!catalogue||witness?.catalogue!==catalogue){registration(null);return;}
    const bound=Object.freeze({workRef:catalogue.workRef,sourceCommit:catalogue.sourceCommit,baseRevision:catalogue.workstreamSha256});
    const current=()=>bodyLive.current&&catalogueWitness.current===witness&&witness.current();
    registration(Object.freeze({codeContext(){
      try{return current()?catalogueState.result?.codeContext??null:null;}catch{return null;}
    },current(snapshot:KnowledgeLibrarySourceContext){
      try {
        if(!bodyLive.current||catalogueWitness.current!==witness||!witness.current()||
          snapshot.workRef!==bound.workRef||snapshot.sourceCommit!==bound.sourceCommit||snapshot.baseRevision!==bound.baseRevision)throw Error();
        return {...bound};
      }catch{throw new Error('SOURCE_CHANGED');}
    }}));
    return()=>registration(null);
  },[catalogue,props.onCurrentSourceOwner]);

  const actions = actionsState.result;
  const sourceContext: KnowledgeLibrarySourceContext | null = catalogue
    ? { workRef: catalogue.workRef, sourceCommit: catalogue.sourceCommit, baseRevision: catalogue.workstreamSha256 }
    : null;

  /* --- Catalogue: exactly one read per identity / explicit refresh ----- */

  const runCatalogue = useCallback(() => {
    catalogueWitness.current=null;
    if (!workRef || scopeError) {
      setCatalogueState({ phase: 'OWNER_UNAVAILABLE', result: unavailableCatalogue(['SOURCE_UNAVAILABLE']), detail: scopeError ? [scopeError] : [] });
      return;
    }
    if (typeof props.readCatalogue !== 'function') {
      setCatalogueState({ phase: 'OWNER_UNAVAILABLE', result: unavailableCatalogue(['SOURCE_UNAVAILABLE']), detail: ['READ_CATALOGUE_ABSENT'] });
      return;
    }
    actionsRead.cancel(); memoryRead.cancel(); sourceRead.cancel();
    memoryRequestedRef.current=false;
    setActionsState({result:null,detail:[]}); setMemoryState(initialRead()); setSourceState(initialRead());
    const read = props.readCatalogue;
    const handle = catalogueRead.begin();
    const ownerCurrent=captureSourceGuard(handle,catalogueRead.isCurrent);
    setCatalogueState({ phase: 'LOADING', result: null, detail: [] });
    void (async () => {
      try {
        const raw = await read({ workRef, signal: handle.controller.signal });
        if (!catalogueRead.isCurrent(handle)) return;
        const validated = validate_catalogue(raw, workRef);
        if (!catalogueRead.isCurrent(handle)) return;
        if(validated.availability==='AVAILABLE'&&validated.catalogue&&ownerCurrent())
          catalogueWitness.current={catalogue:validated.catalogue,current:ownerCurrent};
        setCatalogueState(
          validated.availability === 'AVAILABLE'
            ? { phase: 'READY', result: validated, detail: [] }
            : { phase: 'UNAVAILABLE', result: validated, detail: validated.reasonCodes },
        );
      } catch (error) {
        if (handle.controller.signal.aborted) return;
        if (error instanceof KnowledgeContractError) {
          setCatalogueState({ phase: 'INVALID_PAYLOAD', result: unavailableCatalogue(['SOURCE_UNAVAILABLE']), detail: [error.code] });
        } else {
          setCatalogueState({ phase: 'FAILED', result: unavailableCatalogue(['SOURCE_UNAVAILABLE']), detail: [] });
        }
      }
    })();
    return () => handle.controller.abort();
  }, [workRef, scopeError, props.readCatalogue, props.fileSearchOwner, catalogueRead, actionsRead, memoryRead, sourceRead]);

  useEffect(() => {
    const cleanup = runCatalogue();
    return () => {
      if (typeof cleanup === 'function') cleanup();
    };
  }, [runCatalogue, identity]);

  /* --- Actions: only after an available catalogue + exact snapshot ------ */

  useEffect(() => {
    if (catalogueState.phase !== 'READY' || !catalogue) return;
    if (typeof props.readActions !== 'function') {
      setActionsState({ result: unavailableActions(), detail: ['READ_ACTIONS_ABSENT'] });
      return;
    }
    const read = props.readActions;
    const handle = actionsRead.begin();
    void (async () => {
      try {
        const raw = await read({
          workRef: catalogue.workRef,
          sourceCommit: catalogue.sourceCommit,
          baseRevision: catalogue.workstreamSha256,
          signal: handle.controller.signal,
        });
        if (!actionsRead.isCurrent(handle)) return;
        const validated = validate_actions(raw, catalogue.workRef, catalogue.sourceCommit, catalogue.workstreamSha256);
        if (!actionsRead.isCurrent(handle)) return;
        setActionsState({ result: validated, detail: [] });
      } catch (error) {
        if (handle.controller.signal.aborted) return;
        setActionsState({
          result: unavailableActions(),
          detail: error instanceof KnowledgeContractError ? [error.code] : ['ACTIONS_READ_FAILED'],
        });
      }
    })();
    return () => handle.controller.abort();
  }, [catalogueState.phase, catalogue, props.readActions, actionsRead, identity]);

  /* --- Memory: only on explicit Memory tab activation ------------------- */

  const runMemoryRead = useCallback(() => {
    if (!workRef || scopeError || !catalogue || memoryRequestedRef.current) return;
    memoryRequestedRef.current = true;
    if (typeof props.readMemory !== 'function') {
      setMemoryState({ phase: 'OWNER_UNAVAILABLE', result: unavailableMemory(['SOURCE_UNAVAILABLE']), detail: ['READ_MEMORY_ABSENT'] });
      return;
    }
    const read = props.readMemory;
    const handle = memoryRead.begin();
    setMemoryState({ phase: 'LOADING', result: null, detail: [] });
    void (async () => {
      try {
        const raw = await read({ workRef, signal: handle.controller.signal });
        if (!memoryRead.isCurrent(handle)) return;
        const validated = validate_memory(raw, workRef);
        if(!sameKnowledgeCodeContext(catalogueState.result?.codeContext,validated.codeContext)||
          (validated.dataObservation&&validated.dataObservation.canonical_data_commit!==catalogue.sourceCommit)){
          setMemoryState({phase:'STALE',result:null,detail:['SOURCE_CHANGED']});return;
        }
        if (!memoryRead.isCurrent(handle)) return;
        if (validated.availability === 'AVAILABLE') {
          const record=catalogue.records.find(row => row.sourceRef === catalogue.memory.sourceRef);
          if (catalogue.memory.state !== 'AVAILABLE' || !validated.source || !record ||
              validated.source.commit !== catalogue.sourceCommit || validated.source.path !== record.path ||
              validated.source.revision !== catalogue.memory.revision) {
            setMemoryState({phase:'STALE',result:null,detail:['SOURCE_CHANGED']}); return;
          }
          setMemoryState({ phase: 'READY', result: validated, detail: [] });
        } else if (validated.availability === 'EMPTY') {
          if (catalogue.memory.state !== 'EMPTY' || validated.source !== null) {
            setMemoryState({phase:'STALE',result:null,detail:['SOURCE_CHANGED']}); return;
          }
          setMemoryState({ phase: 'EMPTY', result: validated, detail: [] });
        } else {
          setMemoryState({ phase: 'UNAVAILABLE', result: validated, detail: validated.reasonCodes });
        }
      } catch (error) {
        if (handle.controller.signal.aborted) return;
        if (error instanceof KnowledgeContractError) {
          setMemoryState({ phase: 'INVALID_PAYLOAD', result: unavailableMemory(['SOURCE_UNAVAILABLE']), detail: [error.code] });
        } else {
          setMemoryState({ phase: 'FAILED', result: unavailableMemory(['SOURCE_UNAVAILABLE']), detail: [] });
        }
      }
    })();
  }, [workRef, scopeError, props.readMemory, memoryRead, catalogue]);

  const activateMemoryTab = useCallback(() => {
    setTab('MEMORY');
    if (!memoryRequestedRef.current) runMemoryRead();
  }, [runMemoryRead]);

  /* --- Source: only explicit Open on a current, readable row ------------ */

  const runSourceRead = useCallback(
    (sourceRef: string, expectedRevision: string) => {
      if (!workRef || typeof props.readSource !== 'function' || !catalogue) return;
      const candidate=[...catalogue.files,...catalogue.records].find(row =>
        row.sourceRef === sourceRef && row.revision === expectedRevision);
      if (!candidate || !isRowOpenable(candidate,props.readSource)) {
        setSourceState({phase:'STALE',result:null,detail:['SOURCE_CHANGED']}); return;
      }
      const read = props.readSource;
      const handle = sourceRead.begin();
      const sourceIsCurrent=captureSourceGuard(handle);
      const destination=liveProps.current.draftPort;
      const ticket=destination?captureProjectSourceDraftRead(destination,workRef,sourceIsCurrent):null;
      setDraftProof(null);
      setSourceState({ phase: 'LOADING', result: null, detail: [] });
      void (async () => {
        try {
          const raw = await read({ workRef, sourceRef, expectedRevision, signal: handle.controller.signal });
          if (!sourceRead.isCurrent(handle)) return;
          const validated = validate_source(raw, workRef, sourceRef);
          if (!sourceRead.isCurrent(handle)) return;
          if (validated.availability !== 'AVAILABLE' || !validated.document || !validated.source) {
            setSourceState({ phase: 'UNAVAILABLE', result: validated, detail: validated.reasonCodes });
            return;
          }
          if(!sameKnowledgeCodeContext(catalogueState.result?.codeContext,validated.codeContext)){
            setSourceState({phase:'STALE',result:null,detail:['CODE_CONTEXT_CHANGED']});return;
          }
          const digest = await sha256Hex(validated.document.contentUtf8);
          if (!sourceRead.isCurrent(handle)) return;
          if (digest !== validated.document.contentSha256) {
            setSourceState({ phase: 'TAMPER', result: validated, detail: ['SOURCE_INVALID'] });
            return;
          }
          if (validated.source.commit !== catalogue.sourceCommit || validated.source.path !== candidate.path ||
              validated.source.revision !== expectedRevision ||
              validated.document.mediaType !== ('mediaType' in candidate ? candidate.mediaType : 'text/markdown') ||
              ('contentSha256' in candidate && candidate.contentSha256 !== null && candidate.contentSha256 !== digest) ||
              !rowExists(catalogue, sourceRef, expectedRevision)) {
            setSourceState({ phase: 'STALE', result: validated, detail: ['SOURCE_CHANGED'] });
            return;
          }
          const proof=ticket&&liveProps.current.draftPort?await completeProjectSourceDraftRead(ticket,
            {kind:'mediaType' in candidate?'PROJECT_FILE':'PROJECT_RECORD',sourceRef,result:validated},liveProps.current.draftPort):null;
          if(!sourceRead.isCurrent(handle))return;
          if(ticket&&!sourceIsCurrent()){setSourceState({phase:'STALE',result:null,detail:['SOURCE_CONTEXT_CHANGED']});return;}
          setDraftProof(proof);
          setSourceState({ phase: 'READY', result: validated, detail: [] });
        } catch (error) {
          if (handle.controller.signal.aborted) return;
          if (error instanceof KnowledgeContractError) {
            setSourceState({ phase: 'INVALID_PAYLOAD', result: unavailableSource(['SOURCE_INVALID']), detail: [error.code] });
          } else {
            setSourceState({ phase: 'FAILED', result: unavailableSource(['SOURCE_UNAVAILABLE']), detail: [] });
          }
        }
      })();
    },
    [props.readSource, workRef, catalogue, catalogueState.result, sourceRead, props.fileSearchOwner],
  );

  const openSourceRow = useCallback(
    (row: KnowledgeCatalogueFileRow | KnowledgeCatalogueRecordRow, origin: 'LIST' | 'RECORDS', event: ReactMouseEvent<HTMLButtonElement>) => {
      if (!isRowOpenable(row, props.readSource) || !catalogue) return;
      focusRestoreRef.current = event.currentTarget;
      setOpenRow({ sourceRef: row.sourceRef, expectedRevision: row.revision as string });
      setReaderOrigin(origin);
      setView('READER');
      runSourceRead(row.sourceRef, row.revision as string);
    },
    [props.readSource, catalogue, runSourceRead],
  );

  // A Search Open is an explicit navigation, never a cached preview body. The
  // helper proves fresh membership, original tuple, SHA and owner currentness.
  useEffect(() => {
    if (!props.requestedFile || !catalogue || !workRef || scopeError) return;
    const handle=sourceRead.begin();
    const sourceIsCurrent=captureSourceGuard(handle);
    const ticket=props.draftPort?captureProjectSourceDraftRead(props.draftPort,workRef,sourceIsCurrent):null;
    setDraftProof(null);
    setView('READER'); setOpenRow(null);
    setSourceState({phase:'LOADING',result:null,detail:[]});
    if (props.requestedFile.workRef!==workRef || props.requestedFile.authGeneration!==props.authGeneration ||
        typeof props.requestedFile.hostGeneration!==typeof props.hostGeneration || props.requestedFile.hostGeneration!==props.hostGeneration) {
      setSourceState({phase:'STALE',result:null,detail:['SOURCE_CONTEXT_CHANGED']});
      return () => handle.controller.abort();
    }
    if (!props.fileSearchOwner) {
      setSourceState({phase:'OWNER_UNAVAILABLE',result:null,detail:['FILE_SEARCH_OWNER_ABSENT']});
      return () => handle.controller.abort();
    }
    void readProjectFileMatchSource({workRef,match:props.requestedFile.match,signal:handle.controller.signal},props.fileSearchOwner).then(async opened=>{
      if (!sourceRead.isCurrent(handle)) return;
      const result=opened.document, reference=opened.reference;
      if (opened.state !== 'AVAILABLE' || !reference || !result?.source || !result.document) {
        setSourceState({phase:'STALE',result:null,detail:[opened.reason ?? 'SOURCE_UNAVAILABLE']}); return;
      }
      const candidates=catalogue.files.filter(row=>row.sourceRef===reference.sourceRef && row.revision===reference.expectedRevision &&
        row.path===result.source!.path && isRowOpenable(row,props.readSource));
      if (candidates.length!==1 || catalogue.sourceCommit!==result.source.commit ||
          !sameKnowledgeCodeContext(catalogueState.result?.codeContext,result.codeContext)) {
        setSourceState({phase:'STALE',result:null,detail:['SOURCE_CHANGED']}); return;
      }
      const proof=ticket&&liveProps.current.draftPort?await completeProjectSourceDraftRead(ticket,
        {kind:'PROJECT_FILE',sourceRef:reference.sourceRef,result},liveProps.current.draftPort):null;
      if(!sourceRead.isCurrent(handle))return;
      if(ticket&&!sourceIsCurrent()){setSourceState({phase:'STALE',result:null,detail:['SOURCE_CONTEXT_CHANGED']});return;}
      setDraftProof(proof);
      setOpenRow({sourceRef:reference.sourceRef,expectedRevision:reference.expectedRevision});
      setSourceState({phase:'READY',result,detail:[]});
    }).catch(()=>{
      if (sourceRead.isCurrent(handle)) setSourceState({phase:'FAILED',result:null,detail:['SOURCE_UNAVAILABLE']});
    });
    return () => handle.controller.abort();
  },[catalogue,workRef,scopeError,props.requestedFile,props.fileSearchOwner,props.readSource,props.authGeneration,props.hostGeneration,sourceRead]);

  const closeReader = useCallback(() => {
    restoreFocusRef.current=true;
    sourceRead.cancel();
    setDraftProof(null);
    setSourceState(initialRead()); setOpenRow(null);
    if (props.requestedFile && props.onReturnToSearch) { props.onReturnToSearch(); return; }
    setView(readerOrigin);
  }, [readerOrigin, sourceRead, props.requestedFile, props.onReturnToSearch]);

  useEffect(() => {
    if (view !== 'READER') return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeReader();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [view, closeReader]);

  /* --- Optional markdown reader: loaded once per body -------------------- */

  useEffect(() => {
    let disposed = false;
    void loadSourceMarkdown().then((component) => {
      if (!disposed) setMarkdown(() => component);
    });
    return () => {
      disposed = true;
    };
  }, []);

  /* --- Derived availability ------------------------------------------------ */

  const addFilesEnabled = Boolean(
    sourceContext && actions && actions.addFiles === 'AVAILABLE' && typeof props.onAddFiles === 'function',
  );
  const memoryDocument: ProjectMemoryDocument | null =
    catalogue && memoryState.phase === 'READY' && memoryState.result?.memory && catalogue.memory.sourceRef
      ? {
          source: memoryState.result.source!,
          sourceRef: catalogue.memory.sourceRef,
          revision: catalogue.memory.revision,
          value: memoryState.result.memory.value,
          origin: memoryState.result.memory.origin,
          lastEdit: memoryState.result.memory.lastEdit,
        }
      : null;
  const memoryCurrent =
    memoryDocument !== null && memoryState.result?.source != null && memoryState.result.source.commit === catalogue?.sourceCommit;
  const editPreferenceEnabled = Boolean(
    sourceContext && actions && actions.editPreference === 'AVAILABLE' && typeof props.onEditPreference === 'function' &&
    (memoryCurrent || (memoryState.phase === 'EMPTY' && catalogue?.memory.state === 'EMPTY')),
  );

  const handleAddFiles = useCallback(() => {
    if (!addFilesEnabled || !sourceContext) return;
    props.onAddFiles?.(sourceContext);
  }, [addFilesEnabled, sourceContext, props.onAddFiles]);

  const handleEditPreference = useCallback(() => {
    if (!editPreferenceEnabled || !sourceContext) return;
    props.onEditPreference?.(sourceContext, memoryDocument);
  }, [editPreferenceEnabled, sourceContext, memoryDocument, props.onEditPreference]);

  const title = catalogue ? catalogue.title : copy.fallbackTitle;

  const closedDetails = useCallback(
    (lines: readonly string[], label: string) =>
      lines.length === 0 ? null : (
        <details className="knowledge-library-details">
          <summary>{label}</summary>
          <pre>{lines.join('\n')}</pre>
        </details>
      ),
    [],
  );

  const renderFileRow = (row: KnowledgeCatalogueFileRow) => {
    const openable = isRowOpenable(row, props.readSource);
    return (
      <div key={row.sourceRef} className="knowledge-library-row">
        <div className="knowledge-library-row-main">
          <h3 className="knowledge-library-row-title">{row.displayName}</h3>
          <p className="knowledge-library-row-meta">{fileProvenance(row, locale)}</p>
        </div>
        <button
          type="button"
          className="knowledge-library-open"
          disabled={!openable}
          onClick={(event) => openSourceRow(row, 'LIST', event)}
        >
          {openable ? copy.open : copy.openUnavailable}
        </button>
      </div>
    );
  };

  const renderRecordRow = (row: KnowledgeCatalogueRecordRow) => {
    const openable = isRowOpenable(row, props.readSource);
    const dateMeta = row.authoredAt === null ? '' : ` · ${row.authoredAt}`;
    return (
      <div key={row.sourceRef} className="knowledge-library-row">
        <div className="knowledge-library-row-main">
          <h3 className="knowledge-library-row-title">{row.title}</h3>
          <p className="knowledge-library-row-meta">
            <span className="knowledge-library-row-kind">{recordKindLabel(row.kind, locale)}</span>
            {dateMeta}
          </p>
        </div>
        <button
          type="button"
          className="knowledge-library-open"
          disabled={!openable}
          onClick={(event) => openSourceRow(row, 'RECORDS', event)}
        >
          {openable ? copy.open : copy.openUnavailable}
        </button>
      </div>
    );
  };

  const renderCatalogueNotice = () => {
    if (catalogueState.phase === 'LOADING') {
      return (
        <p className="knowledge-library-note" aria-live="polite">
          {copy.loading}
        </p>
      );
    }
    if (catalogueState.phase === 'OWNER_UNAVAILABLE') {
      return <><p className="knowledge-library-empty">{workRef?copy.scopeUnavailable:copy.chooseProject}</p>{closedDetails(catalogueState.detail,copy.diagnostics)}</>;
    }
    if (catalogueState.phase === 'INVALID_PAYLOAD') {
      return (
        <div>
          <p className="knowledge-library-empty">{copy.invalidPayload}</p>
          {closedDetails(catalogueState.detail, copy.diagnostics)}
        </div>
      );
    }
    if (catalogueState.phase === 'FAILED') {
      return <p className="knowledge-library-empty">{copy.readFailed}</p>;
    }
    if (catalogueState.phase === 'UNAVAILABLE' && catalogueState.result) {
      return (
        <div>
          <p className="knowledge-library-empty">{copy.catalogueUnavailable}</p>
          {closedDetails(
            catalogueState.result.reasonCodes.map((code) => `${code} — ${reasonPublicCopy(code, locale)}`),
            copy.diagnostics,
          )}
        </div>
      );
    }
    return null;
  };

  const renderFiles = () => {
    if (!catalogue) return null;
    const coverage = catalogue.fileCoverage;
    const visible = catalogue.files.filter((row) => matchFileQuery(row, filesQuery));
    const unreadable = catalogue.files.filter((row) => row.state !== 'READABLE');
    return (
      <section id="knowledge-library-panel-files" role="tabpanel" aria-labelledby="knowledge-library-tab-files">
        <div className="knowledge-library-panel">
          <div className="knowledge-library-query">
            <label htmlFor="knowledge-library-files-query">{copy.queryLabel}</label>
            <input
              id="knowledge-library-files-query"
              value={filesQuery}
              placeholder={copy.queryFilesPlaceholder}
              onChange={(event) => setFilesQuery(event.target.value)}
            />
            <p className="knowledge-library-note knowledge-library-note--quiet">{copy.filterScopeNote}</p>
          </div>
          {catalogue.files.length === 0 ? (
            <p className="knowledge-library-empty">{copy.emptyFiles}</p>
          ) : visible.length === 0 ? (
            <p className="knowledge-library-empty">{copy.emptyQuery}</p>
          ) : (
            visible.map(renderFileRow)
          )}
        </div>
        {coverage.state === 'PARTIAL' && (
          <p className="knowledge-library-note">
            {copy.partialNotice} {copy.partialFilesDetail(coverage.declared, coverage.listed)}
          </p>
        )}
        {unreadable.length > 0 &&
          closedDetails(
            unreadable.map((row) => `state: ${row.state}\nsource_ref: ${row.sourceRef}`),
            copy.diagnostics,
          )}
        <div className="knowledge-library-actions-after">
          <button type="button" className="knowledge-library-button" onClick={() => setView('RECORDS')}>
            {copy.browseAllRecords}
          </button>
        </div>
      </section>
    );
  };

  const renderRecords = () => {
    if (!catalogue) return null;
    const visible = catalogue.records.filter((row) => matchRecordQuery(row, recordsQuery, locale));
    return (
      <section id="knowledge-library-panel-records" role="tabpanel" aria-labelledby="knowledge-library-tab-files">
        <div className="knowledge-library-records-head">
          <h2>{copy.recordsTitle}</h2>
          <button type="button" className="knowledge-library-button" onClick={() => setView('LIST')}>
            {copy.backToLibrary}
          </button>
        </div>
        <div className="knowledge-library-panel">
          <div className="knowledge-library-query">
            <label htmlFor="knowledge-library-records-query">{copy.queryLabel}</label>
            <input
              id="knowledge-library-records-query"
              value={recordsQuery}
              placeholder={copy.queryRecordsPlaceholder}
              onChange={(event) => setRecordsQuery(event.target.value)}
            />
            <p className="knowledge-library-note knowledge-library-note--quiet">{copy.filterScopeNote}</p>
          </div>
          {catalogue.records.length === 0 ? (
            <p className="knowledge-library-empty">{copy.emptyRecords}</p>
          ) : visible.length === 0 ? (
            <p className="knowledge-library-empty">{copy.emptyQuery}</p>
          ) : (
            visible.map(renderRecordRow)
          )}
        </div>
        <p className="knowledge-library-note">
          {copy.boundedRecordsNote(catalogue.recordCoverage.matched, catalogue.recordCoverage.scanned)}
        </p>
      </section>
    );
  };

  const renderMemory = () => (
    <section id="knowledge-library-panel-memory" role="tabpanel" aria-labelledby="knowledge-library-tab-memory">
      {memoryState.phase === 'LOADING' && (
        <p className="knowledge-library-note" aria-live="polite">
          {copy.loading}
        </p>
      )}
      {memoryState.phase === 'OWNER_UNAVAILABLE' && <p className="knowledge-library-empty">{copy.scopeUnavailable}</p>}
      {memoryState.phase === 'FAILED' && <p className="knowledge-library-empty">{copy.readFailed}</p>}
      {memoryState.phase === 'INVALID_PAYLOAD' && (
        <div>
          <p className="knowledge-library-empty">{copy.invalidPayload}</p>
          {closedDetails(memoryState.detail, copy.diagnostics)}
        </div>
      )}
      {memoryState.phase === 'UNAVAILABLE' && (
        <div>
          <p className="knowledge-library-empty">{copy.memoryUnavailable}</p>
          {closedDetails(
            (memoryState.result?.reasonCodes ?? []).map((code) => `${code} — ${reasonPublicCopy(code, locale)}`),
            copy.diagnostics,
          )}
        </div>
      )}
      {memoryState.phase === 'EMPTY' && (
        <div className="knowledge-library-panel">
          <p className="knowledge-library-empty">{copy.memoryEmpty}</p>
          {editPreferenceEnabled && (
            <div className="knowledge-library-row">
              <div className="knowledge-library-row-main">
                <h3 className="knowledge-library-row-title">{copy.memoryTitle}</h3>
              </div>
              <button type="button" className="knowledge-library-open" onClick={handleEditPreference}>
                {copy.addPreference}
              </button>
            </div>
          )}
        </div>
      )}
      {memoryState.phase === 'IDLE' && <button type="button" className="knowledge-library-button" onClick={runMemoryRead}>
        {locale === 'zh-CN' ? '读取项目记忆' : 'Read project memory'}</button>}
      {memoryState.phase === 'STALE' && <p className="knowledge-library-note">{copy.refreshPrompt}</p>}
      {memoryState.phase === 'READY' && memoryDocument && (
        <div className="knowledge-library-panel">
          <div className="knowledge-library-row">
            <div className="knowledge-library-row-main">
              <h3 className="knowledge-library-row-title">{copy.memoryTitle}</h3>
              <p className="knowledge-library-row-meta">
                {memoryDocument.origin.kind === 'CONVERSATION' ? copy.originConversation : copy.originUserEdit}
              </p>
            </div>
            {editPreferenceEnabled && (
              <button type="button" className="knowledge-library-open" onClick={handleEditPreference}>
                {copy.editPreference}
              </button>
            )}
          </div>
          <p className="knowledge-library-memory-value">{memoryDocument.value}</p>
          {readMetadataLines(memoryState.result).length?closedDetails(readMetadataLines(memoryState.result),copy.sourceDetails):null}
        </div>
      )}
      {memoryDocument !== null && !memoryCurrent && (
        <p className="knowledge-library-note">{copy.refreshPrompt}</p>
      )}
      <div className="knowledge-library-actions-after">
        <button type="button" className="knowledge-library-button" onClick={() => setTab('FILES')}>
          {copy.backToFiles}
        </button>
      </div>
    </section>
  );

  const renderReader = () => {
    if (sourceState.phase === 'LOADING') {
      return (
        <div className="knowledge-library-reader">
          <article className="knowledge-library-document">
            <button type="button" className="knowledge-library-button" onClick={closeReader}>
              {copy.back}
            </button>
            <p aria-live="polite">{copy.loading}</p>
          </article>
        </div>
      );
    }
    const result = sourceState.result;
    if (sourceState.phase === 'READY' && result?.document && result.source && openRow) {
      const document_ = result.document;
      const sourceDocument = {
        workRef: catalogue ? catalogue.workRef : workRef ?? '',
        sourceRef: openRow.sourceRef,
        title: document_.title,
        mediaType: document_.mediaType,
        contentUtf8: document_.contentUtf8,
        contentSha256: document_.contentSha256,
        source: result.source,
      };
      const MarkdownReader = markdown;
      return (
        <div className="knowledge-library-reader">
          <article className="knowledge-library-document">
            <button type="button" className="knowledge-library-button" onClick={closeReader}>
              {copy.back}
            </button>
            <h1>{document_.title}</h1>
            {document_.mediaType === 'text/markdown' && MarkdownReader ? (
              <MarkdownReader source={document_.contentUtf8} locale={locale} />
            ) : (
              <pre className="knowledge-library-plaintext">{document_.contentUtf8}</pre>
            )}
          </article>
          <aside className="knowledge-library-aside">
            {props.draftPort?<ProjectSourceDraftCompanion proof={draftProof} port={props.draftPort} locale={locale}/>:null}
            {props.renderSourceCompanion ? props.renderSourceCompanion(sourceDocument) : null}
            <div className="knowledge-library-aside-panel">
              <h2>{copy.provenance}</h2>
              <p>{document_.mediaType === 'text/markdown' ? copy.markdownLabel : copy.plainLabel}</p>
              {closedDetails(
                [
                  `source_ref: ${openRow.sourceRef}`,
                  `repository: ${result.source.repository}`,
                  `commit: ${result.source.commit}`,
                  `path: ${result.source.path}`,
                  `revision: ${result.source.revision}`,
                  `content_sha256: ${result.source.contentSha256}`,
                  `committed_at: ${result.source.committedAt ?? 'null'}`,
                  `media_type: ${document_.mediaType}`,
                  ...readMetadataLines(result),
                ],
                copy.sourceDetails,
              )}
            </div>
          </aside>
        </div>
      );
    }
    const headline =
      sourceState.phase === 'STALE' || sourceState.phase === 'TAMPER'
        ? copy.sourceChanged
        : sourceState.phase === 'INVALID_PAYLOAD'
          ? copy.invalidPayload
          : sourceState.phase === 'OWNER_UNAVAILABLE'
            ? copy.scopeUnavailable
            : copy.sourceUnavailable;
    return (
      <div className="knowledge-library-reader">
        <article className="knowledge-library-document">
          <button type="button" className="knowledge-library-button" onClick={closeReader}>
            {copy.back}
          </button>
          <h1>{headline}</h1>
          {sourceState.phase === 'STALE' && <p>{copy.refreshPrompt}</p>}
          {closedDetails(sourceState.detail, copy.diagnostics)}
        </article>
      </div>
    );
  };

  return (
    <div aria-busy={catalogueState.phase === 'LOADING'}>
      <div hidden={view === 'READER'} aria-hidden={view === 'READER'}>
          <header className="knowledge-library-heading">
            <p className="knowledge-library-eyebrow">{copy.productLabel}</p>
            <h1 className="knowledge-library-title">{title}</h1>
            {readMetadataLines(catalogueState.result).length?closedDetails(readMetadataLines(catalogueState.result),copy.sourceDetails):null}
          </header>
          <div className="knowledge-library-toolbar" role="tablist" aria-label={title}>
            <button
              type="button"
              role="tab"
              id="knowledge-library-tab-files"
              aria-selected={tab === 'FILES'}
              aria-controls="knowledge-library-panel-files"
              className="knowledge-library-tab"
              onClick={() => {
                setTab('FILES');
                setView('LIST');
              }}
            >
              {copy.filesTab}
            </button>
            <button
              type="button"
              role="tab"
              id="knowledge-library-tab-memory"
              aria-selected={tab === 'MEMORY'}
              aria-controls="knowledge-library-panel-memory"
              className="knowledge-library-tab"
              onClick={activateMemoryTab}
              disabled={!catalogue}
            >
              {copy.memoryTab}
            </button>
            <span className="knowledge-library-toolbar-spacer" />
            <button
              type="button"
              className="knowledge-library-button knowledge-library-button--primary"
              onClick={handleAddFiles}
              disabled={!addFilesEnabled}
            >
              {copy.addFiles}
            </button>
            <button type="button" className="knowledge-library-button" disabled={!props.readCatalogue || catalogueState.phase === 'LOADING'}
              onClick={() => {runCatalogue();}}>{locale === 'zh-CN' ? '刷新来源' : 'Refresh sources'}</button>
          </div>
          {renderCatalogueNotice()}
          {catalogue && tab === 'FILES' && (view === 'LIST' || (view === 'READER' && readerOrigin === 'LIST')) && renderFiles()}
          {catalogue && tab === 'FILES' && (view === 'RECORDS' || (view === 'READER' && readerOrigin === 'RECORDS')) && renderRecords()}
          {catalogue && tab === 'MEMORY' && renderMemory()}
      </div>
      {view === 'READER' && renderReader()}
    </div>
  );
}

export default KnowledgeLibrary;

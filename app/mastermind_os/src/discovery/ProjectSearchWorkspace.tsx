/**
 * ProjectSearchWorkspace — project-scoped Files / Saved conversations search UI.
 *
 * Read-only consumer of the supplied bounded read composers
 * (`searchSavedConversations`, `searchProjectFiles`) and of the parent-supplied
 * Open handoffs. This component never re-reads sources, never decodes raw
 * source payloads, never opens network/store/invoke channels and never invents
 * owner, coverage, freshness or provenance data.
 *
 * Parent-owned responsibilities (not implemented here): strict owner host
 * ports, the exact-match/source validator before any real reader or draft, the
 * App integration and the associated draft. Presence of a callback or a
 * composer here is not a new grant.
 *
 * Scratch limitation recorded for the parent reviewer: the sibling composer
 * modules are delivered separately under their frozen contracts; this file
 * only imports them.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { searchSavedConversations } from './saved-conversations';
import type {
  SavedConversationMatch,
  SavedConversationSearchOwner,
  SavedConversationSearchResult,
} from './saved-conversations';
import { searchProjectFiles } from './project-file-search';
import type {
  ProjectFileMatch,
  ProjectFileSearchOwner,
  ProjectFileSearchResult,
} from './project-file-search';
import './project-search.css';
import type {createProjectConversationHistoryOwner} from '../conversations/project-conversation-history-owner';

export type ProjectSearchLocale = 'en' | 'zh-CN';
export type ProjectSearchTheme = 'dark' | 'light';
export type ProjectSearchSourceFilter = 'files' | 'saved';
export interface SavedSourcePageWitness { readonly pageCursor?: string; readonly expectedHighWater: number; }

export interface ProjectSearchWorkspaceProps {
  workRef: string | null;
  authGeneration: number;
  hostGeneration: string | number | null;
  locale?: ProjectSearchLocale;
  theme?: ProjectSearchTheme;
  sessionHistory?: SavedConversationSearchOwner;
  /** Actual target-independent project READ owner; refresh is explicit only. */
  savedHistory?: ReturnType<typeof createProjectConversationHistoryOwner>;
  projectFiles?: ProjectFileSearchOwner;
  onOpenSaved?: (match: SavedConversationMatch, page: SavedSourcePageWitness) => void;
  onOpenFile?: (match: ProjectFileMatch) => void;
}

const QUERY_MIN_LENGTH = 2;
const QUERY_MAX_LENGTH = 128;
const MAX_VISIBLE_MATCHES = 8;

/* ---------------------------------------------------------------------------
 * Ephemeral UI identity. Owner slots are only a local comparison token for
 * method tuples; they are never a source clock or an authority of any kind.
 * ------------------------------------------------------------------------- */

const ownerSlots = new WeakMap<object, number>();
let nextOwnerSlot = 1;

function ownerSlot(owner: unknown): number {
  if (!owner || (typeof owner !== 'object' && typeof owner !== 'function')) {
    return 0;
  }
  const key = owner as object;
  let slot = ownerSlots.get(key);
  if (slot === undefined) {
    slot = nextOwnerSlot;
    nextOwnerSlot += 1;
    ownerSlots.set(key, slot);
  }
  return slot;
}

interface OwnerContextView {
  principalScope: string | null;
  generation: string;
  authGeneration: number;
}

function readOwnerContext(owner: unknown, requirePrincipal=true): OwnerContextView | null {
  if (!owner || (typeof owner !== 'object' && typeof owner !== 'function')) {
    return null;
  }
  const candidate = owner as SavedConversationSearchOwner;
  if (typeof candidate.context !== 'function' || typeof candidate.authGeneration !== 'function') {
    return null;
  }
  try {
    const context = candidate.context();
    if (!context) {
      return null;
    }
    if (
      (requirePrincipal && typeof context.principalScope !== 'string') ||
      typeof context.generation !== 'string' ||
      (requirePrincipal && context.principalScope.length === 0) ||
      context.generation.length === 0
    ) {
      return null;
    }
    const auth = candidate.authGeneration();
    if (typeof auth !== 'number' || !Number.isFinite(auth)) {
      return null;
    }
    return {
      principalScope: typeof context.principalScope==='string'?context.principalScope:null,
      generation: context.generation,
      authGeneration: auth,
    };
  } catch {
    return null;
  }
}

/** Typed token so `1` and `'1'` are distinct host identities. */
function hostToken(hostGeneration: string | number | null): string {
  if (hostGeneration === null) {
    return 'host:null';
  }
  if (typeof hostGeneration === 'number') {
    if (!Number.isFinite(hostGeneration)) {
      return 'host:nan';
    }
    return `host:number:${hostGeneration}`;
  }
  return `host:string:${hostGeneration}`;
}

/* ---------------------------------------------------------------------------
 * Query validation — literal query preserved; nothing is trimmed or rewritten.
 * ------------------------------------------------------------------------- */

type QueryCheck = { ok: true; query: string } | { ok: false };

function hasControlCharacter(value: string): boolean {
  // eslint-disable-next-line no-control-regex
  const controlPattern = /[\u0000-\u001F\u007F-\u009F]/;
  return controlPattern.test(value);
}

function hasLoneSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) {
        return true;
      }
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return true;
    }
  }
  return false;
}

function checkQuery(raw: string): QueryCheck {
  if (raw.length === 0) {
    return { ok: false };
  }
  if (hasControlCharacter(raw) || hasLoneSurrogate(raw)) {
    return { ok: false };
  }
  const codePoints = Array.from(raw).length;
  if (codePoints < QUERY_MIN_LENGTH || codePoints > QUERY_MAX_LENGTH) {
    return { ok: false };
  }
  return { ok: true, query: raw };
}

/* ---------------------------------------------------------------------------
 * Frozen-contract result views.
 * ------------------------------------------------------------------------- */

type SourceFilter = ProjectSearchSourceFilter;

type SavedPageRequest = { kind: 'saved'; cursor: string; highWater: number | null };
type FilesPageRequest = { kind: 'files'; pageStart: number; commit: string };
type PageRequest = SavedPageRequest | FilesPageRequest;

type LoadedSource =
  | { source: 'saved'; result: SavedConversationSearchResult; pageCursor?: string }
  | { source: 'files'; result: ProjectFileSearchResult };

interface DisplayRow {
  key: string;
  source: SourceFilter;
  saved: SavedConversationMatch | null;
  file: ProjectFileMatch | null;
  savedPage: SavedSourcePageWitness | null;
}

type NoticeCode =
  | 'invalid-query'
  | 'composer-failed'
  | 'owner-unavailable'
  | 'invalid-input'
  | 'source-changed'
  | 'invalid-source'
  | 'over-budget'
  | 'no-matches';

interface CoverageView {
  status: 'COMPLETE' | 'PARTIAL';
  scanned: number;
  matched: number;
  unavailable: number;
  declared: number | null;
  listed: number | null;
}

function coverageViewOf(loaded: LoadedSource): CoverageView {
  if (loaded.source === 'saved') {
    const coverage = loaded.result.coverage;
    return {
      status: coverage.status,
      scanned: coverage.scanned,
      matched: coverage.matched,
      unavailable: coverage.unavailable,
      declared: null,
      listed: null,
    };
  }
  const coverage = loaded.result.coverage;
  return {
    status: coverage.status,
    scanned: coverage.scanned,
    matched: coverage.matched,
    unavailable: coverage.unavailable,
    declared: coverage.declared,
    listed: coverage.listed,
  };
}

function rowsOf(loaded: LoadedSource, pageSlot: number): DisplayRow[] {
  const items = loaded.result.items;
  const rows: DisplayRow[] = [];
  const limit = Math.min(items.length, MAX_VISIBLE_MATCHES);
  for (let index = 0; index < limit; index += 1) {
    const item = items[index];
    rows.push(
      loaded.source === 'saved'
        ? { key: `saved:p${pageSlot}:i${index}`, source: 'saved', saved: item as SavedConversationMatch, file: null, savedPage: loaded.result.coverage.highWater===null?null:Object.freeze({expectedHighWater:loaded.result.coverage.highWater,...(loaded.pageCursor===undefined?{}:{pageCursor:loaded.pageCursor})}) }
        : { key: `files:p${pageSlot}:i${index}`, source: 'files', saved: null, file: item as ProjectFileMatch, savedPage:null },
    );
  }
  return rows;
}

/** Next page token derived only from the composer's own coverage. */
function nextPageRequestOf(loaded: LoadedSource): PageRequest | null {
  if (loaded.source === 'saved') {
    const coverage = loaded.result.coverage;
    if (coverage.nextCursor === null) {
      return null;
    }
    return { kind: 'saved', cursor: coverage.nextCursor, highWater: coverage.highWater };
  }
  const coverage = loaded.result.coverage;
  if (coverage.nextPageStart === null || loaded.result.sourceCommit === null) {
    return null;
  }
  return {
    kind: 'files',
    pageStart: coverage.nextPageStart,
    commit: loaded.result.sourceCommit,
  };
}

function reasonToNotice(reason: SavedConversationSearchResult['reason'] | ProjectFileSearchResult['reason']): NoticeCode {
  switch (reason) {
    case 'INVALID_INPUT':
      return 'invalid-input';
    case 'OWNER_UNAVAILABLE':
      return 'owner-unavailable';
    case 'SOURCE_CHANGED':
      return 'source-changed';
    case 'INVALID_SOURCE':
      return 'invalid-source';
    case 'OVER_BUDGET':
      return 'over-budget';
    default:
      return 'composer-failed';
  }
}

/* ---------------------------------------------------------------------------
 * Localized UI strings. Source excerpts, match titles and requested_at values
 * are rendered verbatim and are never localized.
 * ------------------------------------------------------------------------- */

interface Strings {
  title: string;
  queryLabel: string;
  queryPlaceholder: string;
  filterFiles: string;
  filterSaved: string;
  submit: string;
  searching: string;
  nextPage: string;
  inspect: string;
  closePreview:string;
  sourceDetails:string;
  requestTime:string;
  results:string;
  open: string;
  savedReplyTitle: string;
  selectedTitle: string;
  details: string;
  provenance: string;
  scopeNote: string;
  pageScope: string;
  scanned: string;
  matched: string;
  unavailable: string;
  declared: string;
  listed: string;
  partialNote: string;
  completeNote: string;
  noMatches: string;
  noMatchesPartial: string;
  noPreview: string;
  openDisabled: string;
  invalidQuery: string;
  composerFailed: string;
  ownerUnavailable: string;
  invalidInput: string;
  sourceChanged: string;
  invalidSource: string;
  overBudget: string;
  filesUnavailable: string;
  savedUnavailable: string;
  searchUnavailable: string;
}

const STRINGS: Record<ProjectSearchLocale, Strings> = {
  en: {
    title: 'Search',
    queryLabel: 'Search this project',
    queryPlaceholder: 'Search files or saved replies',
    filterFiles: 'Files',
    filterSaved: 'Saved conversations',
    submit: 'Search',
    searching: 'Searching…',
    nextPage: 'Next page',
    inspect: 'Inspect',
    closePreview:'Close preview',
    sourceDetails:'Source details',
    requestTime:'Request time',
    results:'Results',
    open: 'Open',
    savedReplyTitle: 'Saved reply',
    selectedTitle: 'Selected match',
    details: 'Details',
    provenance: 'Provenance',
    scopeNote: 'Covers this project only.',
    pageScope: 'This page',
    scanned: 'scanned',
    matched: 'matched',
    unavailable: 'unavailable',
    declared: 'declared',
    listed: 'listed',
    partialNote: 'Coverage is partial; further pages or entries may exist.',
    completeNote: 'No more results were reported for this search.',
    noMatches: 'No matches for this query.',
    noMatchesPartial: 'No matches in the pages checked.',
    noPreview: 'Select Inspect on a result to read it here.',
    openDisabled: 'Open is not available for this match.',
    invalidQuery: 'Enter 2–128 characters without control characters.',
    composerFailed: 'The search could not complete. Refresh to try again.',
    ownerUnavailable: 'Search is unavailable right now.',
    invalidInput: 'The search request was rejected as invalid.',
    sourceChanged: 'The source changed since this view loaded. Refresh to try again.',
    invalidSource: 'This source could not be verified. Search again to retry.',
    overBudget: 'The read budget for this view was reached.',
    filesUnavailable: 'File search is unavailable in this view.',
    savedUnavailable: 'Saved conversation search is unavailable in this view.',
    searchUnavailable: 'Search is unavailable in this view.',
  },
  'zh-CN': {
    title: '搜索',
    queryLabel: '搜索本项目',
    queryPlaceholder: '搜索文件或已保存的回复',
    filterFiles: '文件',
    filterSaved: '已保存的对话',
    submit: '搜索',
    searching: '正在搜索…',
    nextPage: '下一页',
    inspect: '查看',
    closePreview:'关闭预览',
    sourceDetails:'来源详情',
    requestTime:'请求时间',
    results:'搜索结果',
    open: '打开',
    savedReplyTitle: '已保存的回复',
    selectedTitle: '已选结果',
    details: '详情',
    provenance: '来源信息',
    scopeNote: '仅覆盖当前项目。',
    pageScope: '本页',
    scanned: '已扫描',
    matched: '命中',
    unavailable: '不可用',
    declared: '已声明',
    listed: '已列出',
    partialNote: '覆盖不完整；可能存在更多页面或条目。',
    completeNote: '本次搜索未返回更多结果。',
    noMatches: '没有匹配的结果。',
    noMatchesPartial: '已检查的页面中没有匹配结果。',
    noPreview: '在结果上选择“查看”后在此处阅读。',
    openDisabled: '此结果的打开操作不可用。',
    invalidQuery: '请输入 2–128 个字符，且不包含控制字符。',
    composerFailed: '搜索未能完成。刷新后可重试。',
    ownerUnavailable: '暂时无法搜索。',
    invalidInput: '搜索请求被判定为无效。',
    sourceChanged: '来源已发生变化，刷新后可重试。',
    invalidSource: '暂时无法验证此来源，请重新搜索。',
    overBudget: '当前视图的读取预算已用尽。',
    filesUnavailable: '文件搜索在当前视图不可用。',
    savedUnavailable: '已保存的对话搜索在当前视图不可用。',
    searchUnavailable: '搜索在当前视图不可用。',
  },
};

function noticeText(code: NoticeCode, strings: Strings): string {
  switch (code) {
    case 'invalid-query':
      return strings.invalidQuery;
    case 'composer-failed':
      return strings.composerFailed;
    case 'owner-unavailable':
      return strings.ownerUnavailable;
    case 'invalid-input':
      return strings.invalidInput;
    case 'source-changed':
      return strings.sourceChanged;
    case 'invalid-source':
      return strings.invalidSource;
    case 'over-budget':
      return strings.overBudget;
    case 'no-matches':
      return strings.noMatches;
    default:
      return strings.composerFailed;
  }
}

/* ---------------------------------------------------------------------------
 * Component.
 * ------------------------------------------------------------------------- */

export function ProjectSearchWorkspace(props: ProjectSearchWorkspaceProps) {
  const {
    workRef,
    authGeneration,
    hostGeneration,
    locale = 'en',
    theme = 'dark',
    sessionHistory: legacySessionHistory,
    savedHistory,
    projectFiles,
    onOpenSaved,
    onOpenFile,
  } = props;

  const strings = STRINGS[locale === 'zh-CN' ? 'zh-CN' : 'en'];

  const sessionHistory=savedHistory?.owner ?? legacySessionHistory;
  const [,sourceChanged]=useState(0);
  const [preparing,setPreparing]=useState(false);
  useEffect(()=>savedHistory?.subscribe(()=>sourceChanged(value=>value+1)),[savedHistory]);
  const savedContext = readOwnerContext(sessionHistory);
  const filesContext = readOwnerContext(projectFiles,false);

  /**
   * Render-derived body identity: work ref, prop auth generation, typed host
   * generation and each owner's slot plus its own principalScope / generation /
   * authGeneration context. Any change remounts the private body, clearing its
   * state during commit — before passive effects and before paint.
   */
  const bodyKey = useMemo(
    () =>
      [
        'psw',
        workRef === null ? 'work:null' : `work:${workRef}`,
        `auth:${authGeneration}`,
        hostToken(hostGeneration),
        `saved:${ownerSlot(sessionHistory)}:${
          savedContext
            ? `${savedContext.principalScope}@${savedContext.generation}@${savedContext.authGeneration}`
            : 'none'
        }`,
        `files:${ownerSlot(projectFiles)}:${
          filesContext
            ? `${filesContext.principalScope}@${filesContext.generation}@${filesContext.authGeneration}`
            : 'none'
        }`,
      ].join('|'),
    [workRef, authGeneration, hostGeneration, sessionHistory, savedContext, projectFiles, filesContext],
  );

  const identityReady = typeof workRef==='string' && /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.test(workRef)
    && !/[\r\n]/.test(workRef) && workRef.length>=5 && workRef.length<=67 && hostGeneration!==null
    && (typeof hostGeneration==='number'?Number.isFinite(hostGeneration):hostGeneration.length>0)
    && Number.isSafeInteger(authGeneration) && authGeneration>=0;
  const savedReady = identityReady && savedContext !== null;
  const filesReady = identityReady && filesContext !== null;

  return (
    <section
      className={`project-search project-search--${theme === 'light' ? 'light' : 'dark'} project-search--${locale === 'zh-CN' ? 'zh' : 'en'}`}
      aria-labelledby="project-search-heading"
      lang={locale === 'zh-CN' ? 'zh-CN' : 'en'}
    >
      <h1 className="project-search__title" id="project-search-heading">
        {strings.title}
      </h1>
      <p className="project-search__scope">{strings.scopeNote}</p>
      {savedHistory && <button type="button" disabled={!identityReady || preparing} onClick={()=>{
        if(!identityReady || preparing)return;
        setPreparing(true);
        void savedHistory.refresh().catch(()=>{}).finally(()=>setPreparing(false));
      }}>{preparing ? locale==='zh-CN'?'正在读取…':'Reading…' : locale==='zh-CN'?'读取已保存回复的搜索来源':'Read saved reply search source'}</button>}
      <ProjectSearchBody
        key={bodyKey}
        bodyKey={bodyKey}
        workRef={workRef}
        strings={strings}
        identityReady={identityReady}
        savedReady={savedReady}
        filesReady={filesReady}
        sessionHistory={sessionHistory}
        projectFiles={projectFiles}
        onOpenSaved={onOpenSaved}
        onOpenFile={onOpenFile}
      />
    </section>
  );
}

interface ProjectSearchBodyProps {
  bodyKey: string;
  workRef: string | null;
  strings: Strings;
  identityReady: boolean;
  savedReady: boolean;
  filesReady: boolean;
  sessionHistory?: SavedConversationSearchOwner;
  projectFiles?: ProjectFileSearchOwner;
  onOpenSaved?: (match: SavedConversationMatch, page: SavedSourcePageWitness) => void;
  onOpenFile?: (match: ProjectFileMatch) => void;
}

function ProjectSearchBody(props: ProjectSearchBodyProps) {
  const {
    bodyKey,
    workRef,
    strings,
    identityReady,
    savedReady,
    filesReady,
    sessionHistory,
    projectFiles,
    onOpenSaved,
    onOpenFile,
  } = props;

  const [filter, setFilter] = useState<SourceFilter>('files');
  const [queryDraft, setQueryDraft] = useState('');
  const [rows, setRows] = useState<DisplayRow[]>([]);
  const [coverage, setCoverage] = useState<CoverageView | null>(null);
  const [nextPage, setNextPage] = useState<PageRequest | null>(null);
  const [slateQuery, setSlateQuery] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [appending, setAppending] = useState(false);
  const [notice, setNotice] = useState<NoticeCode | null>(null);
  const [selectionKey, setSelectionKey] = useState<string | null>(null);
  const [openBlocked, setOpenBlocked] = useState(false);

  const composingRef = useRef(false);
  const requestSeqRef = useRef(0);
  const pageSlotRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  /** Current witness, refreshed on every commit before any event can run. */
  const witnessRef = useRef(bodyKey);
  useLayoutEffect(() => {
    witnessRef.current = bodyKey;
  });

  const sourceReady = filter === 'saved' ? savedReady : filesReady;
  const queryCheck = checkQuery(queryDraft);
  const queryValid = queryCheck.ok;
  const canSearch = sourceReady && queryValid && workRef !== null && !loading;
  const atVisibleCap = rows.length >= MAX_VISIBLE_MATCHES;
  const canRequestNextPage =
    sourceReady &&
    workRef !== null &&
    !loading &&
    !atVisibleCap &&
    nextPage !== null &&
    slateQuery !== null &&
    slateQuery === queryDraft;

  /** Unmount (identity change): abort any in-flight bounded read so no late
   * result can be published, whatever the composer does with the signal. */
  useLayoutEffect(
    () => () => {
      requestSeqRef.current += 1;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    },
    [],
  );

  function clearSlate() {
    setRows([]);
    setCoverage(null);
    setNextPage(null);
    setSlateQuery(null);
    setSelectionKey(null);
  }

  /** Query / tab actions abort the pending read and clear the slate content
   * synchronously, so no stale prefix survives into the next paint. */
  function cancelPending() {
    requestSeqRef.current += 1;
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }

  function changeQuery(next: string) {
    setQueryDraft(next);
    setNotice(null);
    setOpenBlocked(false);
    cancelPending();
    clearSlate();
    setLoading(false);
    setAppending(false);
  }

  function changeFilter(next: SourceFilter) {
    if (next === filter) {
      return;
    }
    setFilter(next);
    setNotice(null);
    setOpenBlocked(false);
    cancelPending();
    clearSlate();
    setLoading(false);
    setAppending(false);
  }

  function stillCurrent(seq: number, controller: AbortController, witnessAtSubmit: string): boolean {
    return (
      seq === requestSeqRef.current &&
      !controller.signal.aborted &&
      witnessRef.current === witnessAtSubmit
    );
  }

  const runSearch = useCallback(
    (options: { page: PageRequest | null }) => {
      const owner = filter === 'saved' ? sessionHistory : projectFiles;
      if (!sourceReady || workRef === null || !owner) {
        // No unsupported action is ever enabled; nothing is read here.
        return;
      }
      const check = checkQuery(queryDraft);
      if (!check.ok) {
        setNotice('invalid-query');
        return;
      }
      const query = check.query;
      const seq = requestSeqRef.current + 1;
      requestSeqRef.current = seq;
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;
      const witnessAtSubmit = witnessRef.current;

      setNotice(null);
      setOpenBlocked(false);
      setSelectionKey(null);
      if (!options.page) {
        clearSlate();
      }
      setLoading(true);
      setAppending(Boolean(options.page));

      const source = filter;
      const pageSlot = pageSlotRef.current + 1;
      pageSlotRef.current = pageSlot;
      void (async () => {
        let loaded: LoadedSource;
        try {
          if (source === 'saved') {
            const page = options.page && options.page.kind === 'saved' ? options.page : null;
            const result = await searchSavedConversations(
              {
                workRef,
                query,
                signal: controller.signal,
                // expectedHighWater is sent only when the composer reported one.
                ...(page
                  ? {
                      cursor: page.cursor,
                      ...(page.highWater === null ? {} : { expectedHighWater: page.highWater }),
                    }
                  : {}),
              },
              owner as SavedConversationSearchOwner,
            );
            loaded = { source: 'saved', result, ...(page?{pageCursor:page.cursor}:{}) };
          } else {
            const page = options.page && options.page.kind === 'files' ? options.page : null;
            const result = await searchProjectFiles(
              {
                workRef,
                query,
                signal: controller.signal,
                ...(page ? { pageStart: page.pageStart, expectedCommit: page.commit } : {}),
              },
              owner as ProjectFileSearchOwner,
            );
            loaded = { source: 'files', result };
          }
        } catch {
          if (!stillCurrent(seq, controller, witnessAtSubmit)) {
            return;
          }
          setLoading(false);
          setAppending(false);
          setNotice('composer-failed');
          return;
        }

        // Witness, read ticket and abort state are re-checked before any
        // private state is published.
        if (!stillCurrent(seq, controller, witnessAtSubmit)) {
          return;
        }
        if (loaded.result.state !== 'AVAILABLE' || loaded.result.workRef !== workRef || loaded.result.query !== query) {
          setLoading(false);
          setAppending(false);
          setNotice(
            loaded.result.state === 'AVAILABLE' || loaded.result.reason === null
              ? 'composer-failed'
              : reasonToNotice(loaded.result.reason),
          );
          return;
        }

        const freshRows = rowsOf(loaded, pageSlot);
        const mergedRows = options.page
          ? [...rowsRef.current, ...freshRows].slice(0, MAX_VISIBLE_MATCHES)
          : freshRows;
        setLoading(false);
        setAppending(false);
        setRows(mergedRows);
        setCoverage(coverageViewOf(loaded));
        setNextPage(nextPageRequestOf(loaded));
        setSlateQuery(query);
        if (mergedRows.length === 0) {
          setNotice('no-matches');
        }
      })();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filter, sourceReady, workRef, queryDraft, sessionHistory, projectFiles],
  );

  /** Latest committed rows, readable from the async continuation. */
  const rowsRef = useRef<DisplayRow[]>(rows);
  useLayoutEffect(() => {
    rowsRef.current = rows;
  }, [rows]);

  const previewHeading=useRef<HTMLHeadingElement|null>(null);
  const resultsHeading=useRef<HTMLHeadingElement|null>(null);
  const inspectTrigger=useRef<HTMLButtonElement|null>(null);
  const focusPreview=useRef(false);
  useLayoutEffect(()=>{
    if(focusPreview.current && selectionKey!==null){focusPreview.current=false;previewHeading.current?.focus();}
  },[selectionKey]);
  const closePreview=()=>{
    focusPreview.current=false;setSelectionKey(null);
    (inspectTrigger.current?.isConnected?inspectTrigger.current:resultsHeading.current)?.focus();
  };
  const selectedRow = selectionKey
    ? rows.find((row) => row.key === selectionKey) ?? null
    : null;

  function openRow(row: DisplayRow) {
    try {
      if (row.source === 'saved') {
        if (!onOpenSaved || !row.saved || !row.savedPage) {
          setOpenBlocked(true);
          return;
        }
        // Exact owned match object from the currently displayed result.
        onOpenSaved(row.saved,row.savedPage);
      } else {
        if (!onOpenFile || !row.file) {
          setOpenBlocked(true);
          return;
        }
        onOpenFile(row.file);
      }
      setOpenBlocked(false);
    } catch {
      // A failing handoff is a fixed local-unavailable, never an exception and
      // never a channel for source text.
      setOpenBlocked(true);
    }
  }

  const unavailableText = !identityReady
    ? strings.searchUnavailable
    : filter === 'saved'
      ? savedReady
        ? null
        : strings.savedUnavailable
      : filesReady
        ? null
        : strings.filesUnavailable;

  const statusParts: string[] = [];
  if (loading) {
    statusParts.push(appending ? strings.nextPage : strings.searching);
  } else if (coverage) {
    statusParts.push(
      `${strings.pageScope}: ${strings.scanned} ${coverage.scanned} · ${strings.matched} ${coverage.matched} · ${strings.unavailable} ${coverage.unavailable}`,
    );
    if (coverage.declared !== null) {
      statusParts.push(
        `${strings.declared} ${coverage.declared}${coverage.listed === null ? '' : ` · ${strings.listed} ${coverage.listed}`}`,
      );
    }
  }
  if (openBlocked) {
    statusParts.push(strings.openDisabled);
  } else if (notice) {
    statusParts.push(notice === 'no-matches' && coverage?.status === 'PARTIAL'
      ? strings.noMatchesPartial : noticeText(notice, strings));
  } else if (!loading && coverage && coverage.status === 'COMPLETE' && !nextPage) {
    statusParts.push(strings.completeNote);
  }
  if (!loading && !openBlocked && coverage?.status === 'PARTIAL' && (!notice || notice === 'no-matches')) {
    statusParts.push(strings.partialNote);
  }

  return (
    <div className="project-search__body">
      <form
        className="project-search__controls"
        onSubmit={(event) => {
          event.preventDefault();
          if (composingRef.current) {
            return;
          }
          runSearch({ page: null });
        }}
      >
        <div className="project-search__filters" role="group" aria-label={strings.title}>
          <button
            type="button"
            className="project-search__filter"
            aria-pressed={filter === 'files'}
            disabled={filter === 'files' && !filesReady}
            onClick={() => changeFilter('files')}
          >
            {strings.filterFiles}
          </button>
          <button
            type="button"
            className="project-search__filter"
            aria-pressed={filter === 'saved'}
            disabled={filter === 'saved' && !savedReady}
            onClick={() => changeFilter('saved')}
          >
            {strings.filterSaved}
          </button>
        </div>
        <div className="project-search__queryRow">
          <label className="project-search__queryLabel" htmlFor="project-search-query">
            {strings.queryLabel}
          </label>
          <div className="project-search__queryCluster">
            <input
              id="project-search-query"
              className="project-search__input"
              type="text"
              value={queryDraft}
              enterKeyHint="search"
              autoComplete="off"
              spellCheck={false}
              placeholder={strings.queryPlaceholder}
              disabled={!sourceReady}
              onChange={(event) => changeQuery(event.target.value)}
              onCompositionStart={() => {
                composingRef.current = true;
              }}
              onCompositionEnd={() => {
                composingRef.current = false;
              }}
            />
            <button
              type="submit"
              className="project-search__submit"
              disabled={!canSearch}
            >
              {strings.submit}
            </button>
          </div>
        </div>
        <p className="project-search__status" role="status" aria-live="polite">
          {statusParts.length > 0 ? statusParts.join(' — ') : ''}
        </p>
      </form>

      <div className="project-search__columns">
        <div className="project-search__results">
          <h2 className="project-search__resultsHeading" ref={resultsHeading} tabIndex={-1}>{strings.results}</h2>
          {unavailableText !== null ? (
            <p className="project-search__empty">{unavailableText}</p>
          ) : null}
          <ul className="project-search__list" aria-label={strings.title}>
            {rows.map((row) => {
              const selected = row.key === selectionKey;
              return (
                <li className="project-search__row" key={row.key}>
                  <div className="project-search__rowBody">
                    <p className="project-search__rowTitle">
                      {row.source === 'saved'
                        ? strings.savedReplyTitle
                        : row.file?.displayName ?? ''}
                    </p>
                    {row.source === 'saved' ? (
                      <p className="project-search__rowMeta">
                        {row.saved?.reference.requested_at ?? ''}
                      </p>
                    ) : null}
                    <p className="project-search__rowExcerpt">{row.source === 'saved' ? row.saved?.excerpt : row.file?.excerpt}</p>
                    {row.source === 'saved' && row.saved ? (
                      <details className="project-search__details">
                        <summary>{strings.details}</summary>
                        <dl className="project-search__provenance">
                          <div><dt>read_ref</dt><dd>{row.saved.reference.read_ref}</dd></div>
                          <div><dt>operation_key</dt><dd>{row.saved.reference.operation_key}</dd></div>
                          <div><dt>request_ref</dt><dd>{row.saved.reference.request_ref}</dd></div>
                          <div><dt>request_event_id</dt><dd>{row.saved.reference.request_event_id}</dd></div>
                          <div><dt>request_revision</dt><dd>{row.saved.reference.request_revision}</dd></div>
                          <div><dt>work_ref</dt><dd>{row.saved.reference.work_ref}</dd></div>
                          <div><dt>root_job_id</dt><dd>{row.saved.reference.root_job_id}</dd></div>
                          <div><dt>target_ref</dt><dd>{row.saved.reference.target_ref}</dd></div>
                          <div><dt>reference_only</dt><dd>{String(row.saved.reference.reference_only)}</dd></div>
                          <div><dt>sourceTextSha256</dt><dd>{row.saved.sourceTextSha256}</dd></div>
                        </dl>
                      </details>
                    ) : null}
                    {row.source === 'files' && row.file ? (
                      <details className="project-search__details">
                        <summary>{strings.details}</summary>
                        <dl className="project-search__provenance">
                          <div><dt>sourceRef</dt><dd>{row.file.sourceRef}</dd></div>
                          <div><dt>expectedRevision</dt><dd>{row.file.expectedRevision}</dd></div>
                          <div><dt>repository</dt><dd>{row.file.source.repository}</dd></div>
                          <div><dt>commit</dt><dd>{row.file.source.commit}</dd></div>
                          <div><dt>path</dt><dd>{row.file.source.path}</dd></div>
                          <div><dt>revision</dt><dd>{row.file.source.revision}</dd></div>
                          <div><dt>content_sha256</dt><dd>{row.file.source.content_sha256}</dd></div>
                          <div><dt>committed_at</dt><dd>{row.file.source.committed_at === null ? 'null' : row.file.source.committed_at}</dd></div>
                          <div><dt>sourceTextSha256</dt><dd>{row.file.sourceTextSha256}</dd></div>
                        </dl>
                      </details>
                    ) : null}
                  </div>
                  <div className="project-search__rowActions">
                    <button
                      type="button"
                      className="project-search__rowAction"
                      aria-pressed={selected}
                      onClick={event => {
                        inspectTrigger.current=event.currentTarget;
                        if(selected) closePreview();
                        else {focusPreview.current=true;setSelectionKey(row.key);}
                        setOpenBlocked(false);
                      }}
                    >
                      {strings.inspect}
                    </button>
                    <button
                      type="button"
                      className="project-search__rowAction project-search__rowAction--open"
                      disabled={
                        (row.source === 'saved'
                          ? !onOpenSaved || !row.saved || !row.savedPage
                          : !onOpenFile || !row.file)
                      }
                      onClick={() => openRow(row)}
                    >
                      {strings.open}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          {nextPage !== null && !atVisibleCap ? (
            <div className="project-search__pager">
              <button
                type="button"
                className="project-search__pagerButton"
                disabled={!canRequestNextPage}
                onClick={() => runSearch({ page: nextPage })}
              >
                {strings.nextPage}
              </button>
            </div>
          ) : null}
        </div>

        <aside className="project-search__preview" hidden={!selectedRow} onKeyDown={event=>{
          if(event.key==='Escape' && selectedRow){event.preventDefault();event.stopPropagation();closePreview();}
        }}>
          <h2 className="project-search__previewTitle" ref={previewHeading} tabIndex={-1}>{strings.selectedTitle}</h2>
          {selectedRow && <button type="button" className="project-search__rowAction" onClick={closePreview}>{strings.closePreview}</button>}
          {selectedRow ? (
            <div className="project-search__previewBody">
              <p className="project-search__previewHeading">
                {selectedRow.source === 'saved'
                  ? strings.savedReplyTitle
                  : selectedRow.file?.displayName ?? ''}
              </p>
              {selectedRow.source==='saved' && <p className="project-search__previewMeta">{strings.requestTime}: {selectedRow.saved?.reference.requested_at ?? ''}</p>}
              <p className="project-search__previewExcerpt">
                {selectedRow.source === 'saved' ? selectedRow.saved?.excerpt : selectedRow.file?.excerpt}
              </p>
              <details className="project-search__details"><summary>{strings.sourceDetails}</summary>
              {selectedRow.source === 'saved' && selectedRow.saved ? (
                <dl className="project-search__provenance">
                  <div><dt>root_job_id</dt><dd>{selectedRow.saved.reference.root_job_id}</dd></div>
                  <div><dt>requested_at</dt><dd>{selectedRow.saved.reference.requested_at}</dd></div>
                  <div><dt>read_ref</dt><dd>{selectedRow.saved.reference.read_ref}</dd></div>
                  <div><dt>sourceTextSha256</dt><dd>{selectedRow.saved.sourceTextSha256}</dd></div>
                </dl>
              ) : null}
              {selectedRow.source === 'files' && selectedRow.file ? (
                <dl className="project-search__provenance">
                  <div><dt>sourceRef</dt><dd>{selectedRow.file.sourceRef}</dd></div>
                  <div><dt>path</dt><dd>{selectedRow.file.source.path}</dd></div>
                  <div><dt>revision</dt><dd>{selectedRow.file.source.revision}</dd></div>
                  <div><dt>sourceTextSha256</dt><dd>{selectedRow.file.sourceTextSha256}</dd></div>
                </dl>
              ) : null}
              </details>
            </div>
          ) : (
            <p className="project-search__previewEmpty">{strings.noPreview}</p>
          )}
        </aside>
      </div>
    </div>
  );
}

export default ProjectSearchWorkspace;

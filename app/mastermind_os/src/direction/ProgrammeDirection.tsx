import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ProjectPlanRead, ProjectPlanSelection } from '../planning/project-plan';

export interface ProgrammeDirectionProps {
  selection: ProjectPlanSelection | null;
  read?: (request: ProjectPlanSelection & { signal: AbortSignal }) => Promise<ProjectPlanRead>;
  sourceGeneration?: () => number;
  canRead?: () => boolean;
  locale?: 'en' | 'zh-CN';
}

interface Acquisition {
  seq: number;
  reader: ProgrammeDirectionProps['read'];
  generationReader: ProgrammeDirectionProps['sourceGeneration'];
  permissionReader: ProgrammeDirectionProps['canRead'];
  workRef: string;
  generation: number;
  status: 'loading' | 'ok' | 'failed';
  result: ProjectPlanRead | null;
}

type Locale = NonNullable<ProgrammeDirectionProps['locale']>;

interface CopyTable {
  eyebrow: string;
  readButton: string;
  loading: string;
  noSelection: string;
  noReader: string;
  readFailed: string;
  unavailable: string;
  reasonCodesLabel: string;
  statusLabel: string;
  ownerLabel: string;
  nextActionLabel: string;
  adoptionLabel: string;
  adoptionRecorded: string;
  authoredMatches: string;
  authoredDiffers: string;
  notDeclared: string;
  wavesLabel: string;
  dependsOnLabel: string;
  prsLabel: string;
  sourceLabel: string;
  repositoryLabel: string;
  commitLabel: string;
  pathLabel: string;
  digestLabel: string;
  historyLabel: string;
  historyUnavailable: string;
  noRevisions: string;
  revisionCount: (count: number) => string;
  showAll: (count: number) => string;
  showFewer: string;
}

const COPY: Record<Locale, CopyTable> = {
  en: {
    eyebrow: 'Programme objective',
    readButton: 'Read programme objective',
    loading: 'Reading programme objective…',
    noSelection: 'No programme plan selection is active.',
    noReader: 'No reader is available in this context.',
    readFailed: 'The programme objective could not be read.',
    unavailable: 'The programme plan is unavailable for this selection.',
    reasonCodesLabel: 'Reason codes',
    statusLabel: 'Authored status',
    ownerLabel: 'Owner',
    nextActionLabel: 'Next action',
    adoptionLabel: 'Adoption declaration',
    adoptionRecorded: 'Adoption recorded by source',
    authoredMatches: 'The authored record matches the recorded adopted source.',
    authoredDiffers: 'The authored record differs from the recorded adopted source.',
    notDeclared: 'Not declared',
    wavesLabel: 'Waves',
    dependsOnLabel: 'Depends on',
    prsLabel: 'PRs',
    sourceLabel: 'Source',
    repositoryLabel: 'Repository',
    commitLabel: 'Commit',
    pathLabel: 'Path',
    digestLabel: 'Content digest',
    historyLabel: 'Source record revisions',
    historyUnavailable: 'Source record revisions are not available.',
    noRevisions: 'The declared source history records no revisions.',
    revisionCount: (count) => `${count} revisions`,
    showAll: (count) => `Show all ${count} revisions`,
    showFewer: 'Show fewer',
  },
  'zh-CN': {
    eyebrow: '项目目标',
    readButton: '读取项目目标',
    loading: '正在读取项目目标…',
    noSelection: '当前没有已激活的项目计划选择。',
    noReader: '当前上下文中没有可用的读取器。',
    readFailed: '无法读取项目目标。',
    unavailable: '该选择对应的项目计划不可用。',
    reasonCodesLabel: '原因代码',
    statusLabel: '原始状态',
    ownerLabel: '负责人',
    nextActionLabel: '下一步行动',
    adoptionLabel: '采纳声明',
    adoptionRecorded: '来源已记录采纳决定',
    authoredMatches: '编写记录与已记录的采纳来源一致。',
    authoredDiffers: '编写记录与已记录的采纳来源不同。',
    notDeclared: '未声明',
    wavesLabel: '工作波次',
    dependsOnLabel: '依赖',
    prsLabel: 'PR',
    sourceLabel: '来源',
    repositoryLabel: '仓库',
    commitLabel: '提交',
    pathLabel: '路径',
    digestLabel: '内容摘要',
    historyLabel: '来源记录修订',
    historyUnavailable: '来源记录修订不可用。',
    noRevisions: '声明的来源历史中没有记录修订。',
    revisionCount: (count) => `共 ${count} 条修订`,
    showAll: (count) => `显示全部 ${count} 条修订`,
    showFewer: '收起',
  },
};

const HISTORY_PREVIEW = 8;

export function ProgrammeDirection({
  selection,
  read,
  sourceGeneration,
  canRead,
  locale = 'en',
}: ProgrammeDirectionProps) {
  const copy = COPY[locale];

  const readRef = useRef(read);
  readRef.current = read;
  const generationRef = useRef(sourceGeneration);
  generationRef.current = sourceGeneration;
  const canReadRef = useRef(canRead);
  canReadRef.current = canRead;
  const selectionRef = useRef(selection);
  selectionRef.current = selection;

  const [acquisition, setAcquisition] = useState<Acquisition | null>(null);
  const acquisitionRef = useRef<Acquisition | null>(null);
  acquisitionRef.current = acquisition;
  const [showAllHistory, setShowAllHistory] = useState(false);
  const seqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(false);

  const generationNow = useCallback(() => {
    try { const value = generationRef.current?.(); return typeof value === 'number' &&
      Number.isSafeInteger(value) && value >= 0 ? value : NaN; } catch { return NaN; }
  }, []);
  const canReadNow = useCallback(() => {
    try { return typeof generationRef.current === 'function' &&
      typeof canReadRef.current === 'function' && canReadRef.current() === true &&
      Number.isFinite(generationNow()); } catch { return false; }
  }, [generationNow]);

  const snapshotCurrent = useCallback(
    (captured: Acquisition): boolean => {
      if (seqRef.current !== captured.seq) return false;
      const current = selectionRef.current;
      if (!current?.work_ref) return false;
      if (readRef.current !== captured.reader || generationRef.current !== captured.generationReader ||
        canReadRef.current !== captured.permissionReader) return false;
      if (current.work_ref !== captured.workRef) return false;
      if (generationNow() !== captured.generation) return false;
      if (!canReadNow()) return false;
      return true;
    },
    [generationNow, canReadNow],
  );

  const eraseAcquisition = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    acquisitionRef.current = null;
    setAcquisition(null);
  }, []);

  const performRead = useCallback(
    async (
      controller: AbortController,
      captured: Acquisition,
      request: ProjectPlanSelection,
    ): Promise<void> => {
      const reader = readRef.current;
      if (!reader) return;
      let result: ProjectPlanRead;
      try {
        result = await reader({ ...request, signal: controller.signal });
      } catch {
        if (controller.signal.aborted || seqRef.current !== captured.seq) return;
        if (!snapshotCurrent(captured)) {
          eraseAcquisition();
          return;
        }
        acquisitionRef.current = { ...captured, status: 'failed', result: null };
        setAcquisition(acquisitionRef.current);
        return;
      }
      if (controller.signal.aborted || seqRef.current !== captured.seq) return;
      if (!snapshotCurrent(captured)) {
        eraseAcquisition();
        return;
      }
      if (result.selection.work_ref !== captured.workRef) {
        acquisitionRef.current = { ...captured, status: 'failed', result: null };
        setAcquisition(acquisitionRef.current);
        return;
      }
      setShowAllHistory(false);
      acquisitionRef.current = { ...captured, status: 'ok', result };
      setAcquisition(acquisitionRef.current);
    },
    [snapshotCurrent, eraseAcquisition],
  );

  const startRead = useCallback(() => {
    const current = selectionRef.current;
    if (!current?.work_ref) return;
    if (!readRef.current) return;
    if (!canReadNow()) return;
    const pending = acquisitionRef.current;
    if (pending && pending.status === 'loading') return;
    abortRef.current?.abort();
    const seq = ++seqRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    const request: ProjectPlanSelection = { work_ref: current.work_ref };
    const captured: Acquisition = {
      seq, reader: readRef.current, generationReader: generationRef.current,
      permissionReader: canReadRef.current,
      workRef: current.work_ref,
      generation: generationNow(),
      status: 'loading',
      result: null,
    };
    acquisitionRef.current = captured;
    setAcquisition(captured);
    void performRead(controller, captured, request);
  }, [canReadNow, generationNow, performRead]);

  // Erase any retained acquisition the moment its snapshot stops matching the
  // live selection / generation / permission. This runs after every render so
  // a revoked permission cannot resurrect content on a later regrant: the
  // acquisition itself is destroyed, so a false→true flip with the same
  // generation still requires a fresh manual read.
  useLayoutEffect(() => {
    const current = acquisitionRef.current;
    if (!current) return;
    if (seqRef.current !== current.seq) return;
    const selected = selectionRef.current;
    const drifted =
      !selected ||
      !selected.work_ref ||
      readRef.current !== current.reader || generationRef.current !== current.generationReader ||
      canReadRef.current !== current.permissionReader ||
      selected.work_ref !== current.workRef ||
      generationNow() !== current.generation ||
      !canReadNow();
    if (!drifted) return;
    eraseAcquisition();
  });

  // Abort in-flight work when the reader, getters, permission callback or
  // selection identity changes; loading state is torn down with it so the
  // panel never shows a permanently stuck loading indicator.
  useLayoutEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    const current = acquisitionRef.current;
    if (!current || current.status !== 'loading') return;
    if (seqRef.current !== current.seq) return;
    eraseAcquisition();
  }, [read, sourceGeneration, canRead, selection?.work_ref, eraseAcquisition]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const selectionValid = typeof selection?.work_ref === "string" && selection.work_ref.length > 0;
  const permissionOk = canReadNow();
  const generation = generationNow();
  const snapshotMatches =
    selectionValid &&
    acquisition !== null &&
    selection !== null &&
    acquisition.workRef === selection.work_ref &&
    acquisition.generation === generation &&
    permissionOk && acquisition.reader === read &&
    acquisition.generationReader === sourceGeneration && acquisition.permissionReader === canRead;
  const loadingVisible = snapshotMatches && acquisition?.status === 'loading';
  const failedVisible = snapshotMatches && acquisition?.status === 'failed';
  const visibleAcquisition =
    snapshotMatches && acquisition?.status === 'ok' ? acquisition : null;

  const readDisabled =
    !selectionValid || read === undefined || !permissionOk || acquisition?.status === 'loading';

  const renderRead = (result: ProjectPlanRead) => {
    if (result.availability !== 'AVAILABLE' || !result.plan) {
      return (
        <div>
          <p className="office-muted">{copy.unavailable}</p>
          {result.reason_codes.length > 0 ? (
            <>
              <p className="office-section-label">{copy.reasonCodesLabel}</p>
              <ul>
                {result.reason_codes.map((code) => (
                  <li key={code} className="office-muted">
                    {code}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      );
    }
    const plan = result.plan;
    const source = result.source;
    const history = plan.version_history;
    return (
      <div>
        <h3 className="office-section-label">{plan.title}</h3>
        <p className="office-muted">{plan.objective}</p>
        <dl>
          <dt>{copy.statusLabel}</dt>
          <dd>{plan.status}</dd>
          <dt>{copy.ownerLabel}</dt>
          <dd>{plan.owner ?? copy.notDeclared}</dd>
          <dt>{copy.nextActionLabel}</dt>
          <dd>{plan.next_action ?? copy.notDeclared}</dd>
          <dt>{copy.adoptionLabel}</dt>
          <dd>
            {plan.adoption.state === 'AVAILABLE'
              ? <>{copy.adoptionRecorded} · {plan.adoption.decision_ref}
                  <p>{plan.adoption.matches_authored_record ? copy.authoredMatches : copy.authoredDiffers}</p></>
              : plan.adoption.reason === 'NOT_DECLARED'
                ? copy.notDeclared
                : `${plan.adoption.state} · ${plan.adoption.reason}`}
          </dd>
        </dl>
        <details><summary className="office-section-label">{copy.wavesLabel}</summary>
        {plan.waves.length > 0 ? (
          <ul>
            {plan.waves.map((wave) => (
              <li key={wave.id}>
                {wave.id} · {wave.title} · {wave.status}
                {wave.depends_on.length > 0
                  ? ` · ${copy.dependsOnLabel}: ${wave.depends_on.join(', ')}`
                  : ''}
                {wave.prs.length > 0 ? ` · ${copy.prsLabel}: ${wave.prs.join(', ')}` : ''}
                {wave.next_action ? ` · ${copy.nextActionLabel}: ${wave.next_action}` : ''}
              </li>
            ))}
          </ul>
        ) : null}
        </details>
        {source ? (
          <details>
            <summary className="office-section-label">{copy.sourceLabel}</summary>
            <dl>
              <dt>{copy.repositoryLabel}</dt>
              <dd>{source.repository}</dd>
              <dt>{copy.commitLabel}</dt>
              <dd>{source.commit}</dd>
              <dt>{copy.pathLabel}</dt>
              <dd>{source.path}</dd>
              <dt>{copy.digestLabel}</dt>
              <dd>{source.content_sha256}</dd>
            </dl>
          </details>
        ) : null}
        <details>
          <summary className="office-section-label">{copy.historyLabel}</summary>
          {history.state === 'AVAILABLE' ? (
            history.revisions.length === 0 ? (
              <p className="office-muted">{copy.noRevisions}</p>
            ) : (
              <>
                <p className="office-muted">{copy.revisionCount(history.revisions.length)}</p>
                <ul>
                  {(showAllHistory
                    ? history.revisions
                    : history.revisions.slice(0, HISTORY_PREVIEW)
                  ).map((revision, index) => (
                    <li key={`${revision.commit}-${index}`}>
                      {revision.commit} · {revision.committed_at} · {revision.content_sha256}
                    </li>
                  ))}
                </ul>
                {history.revisions.length > HISTORY_PREVIEW ? (
                  <button
                    type="button"
                    onClick={() => setShowAllHistory((value) => !value)}
                  >
                    {showAllHistory
                      ? copy.showFewer
                      : copy.showAll(history.revisions.length)}
                  </button>
                ) : null}
              </>
            )
          ) : (
            <p className="office-muted">
              {copy.historyUnavailable} {history.reason}
            </p>
          )}
        </details>
      </div>
    );
  };

  return (
    <section className="office-panel" aria-label={copy.eyebrow}>
      <p className="office-eyebrow">{copy.eyebrow}</p>
      {!selectionValid ? <p className="office-muted">{copy.noSelection}</p> : null}
      {selectionValid && (read === undefined || !permissionOk) ? (
        <p className="office-muted">{copy.noReader}</p>
      ) : null}
      <button type="button" onClick={startRead} disabled={readDisabled}>
        {copy.readButton}
      </button>
      {loadingVisible ? (
        <p className="office-muted" role="status">
          {copy.loading}
        </p>
      ) : null}
      {failedVisible ? (
        <p className="office-muted" role="alert">
          {copy.readFailed}
        </p>
      ) : null}
      {visibleAcquisition && visibleAcquisition.result
        ? renderRead(visibleAcquisition.result)
        : null}
    </section>
  );
}

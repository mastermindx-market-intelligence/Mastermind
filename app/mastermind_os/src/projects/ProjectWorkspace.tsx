import { useId, useLayoutEffect, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode, Ref } from 'react';
import './project-workspace.css';

/**
 * Bounded presentation composition for the visible project workspace paper.
 *
 * The component renders only owner-qualified slots. It performs no reads,
 * sends, pauses, creates or persistence, and derives no state, ids or rights:
 * every panel and string arrives already qualified by the app's owners.
 */

export type ProjectWorkspaceLocale = 'en' | 'zh-CN';

export interface ProjectWorkspaceProps {
  /**
   * Existing owner auth+project/session identity. Used only as a UI reset key
   * for disclosure state; it grants no authority on its own.
   */
  scopeKey: string;
  locale: ProjectWorkspaceLocale;
  title: string | null;
  headingLevel?: 1 | 2;
  headingRef?: Ref<HTMLHeadingElement>;
  goal: string | null;
  conversationPanel: ReactNode;
  composerPanel: ReactNode;
  statusPanel?: ReactNode;
  pauseControl?: ReactNode;
  filesPanel?: ReactNode;
  detailsPanel?: ReactNode;
  startWorkControl?: ReactNode;
  launchPanel?: ReactNode;
}

interface WorkspaceCopy {
  fallbackTitle: string;
  goalLabel: string;
  goalEmpty: string;
  filesLabel: string;
  detailsLabel: string;
  closeLabel: string;
  statusLabel: string;
  filesUnavailable: string;
  detailsUnavailable: string;
}

const COPY: Record<ProjectWorkspaceLocale, WorkspaceCopy> = {
  en: {
    fallbackTitle: 'Project workspace',
    goalLabel: 'Goal',
    goalEmpty: 'Project goal has not been supplied.',
    filesLabel: 'Files',
    detailsLabel: 'Project details',
    closeLabel: 'Close',
    statusLabel: 'Status',
    filesUnavailable: 'Files are not available for this project yet.',
    detailsUnavailable: 'Project details are not available for this project yet.',
  },
  'zh-CN': {
    fallbackTitle: '项目工作区',
    goalLabel: '目标',
    goalEmpty: '尚未提供项目目标。',
    filesLabel: '文件',
    detailsLabel: '项目详情',
    closeLabel: '关闭',
    statusLabel: '状态',
    filesUnavailable: '此项目暂无可用文件。',
    detailsUnavailable: '此项目暂无可用项目详情。',
  },
};

type DisclosureName = 'files' | 'details';

export function ProjectWorkspace(props: ProjectWorkspaceProps) {
  const {
    scopeKey,
    locale,
    title,
    goal,
    conversationPanel,
    composerPanel,
    statusPanel,
    pauseControl,
    filesPanel,
    detailsPanel,
    startWorkControl,
    launchPanel,
  } = props;
  const copy = COPY[locale];
  const Heading = props.headingLevel === 1 ? "h1" : "h2";

  const [disclosure, setDisclosure] = useState<DisclosureName | null>(null);
  const [disclosureScopeKey, setDisclosureScopeKey] = useState(scopeKey);
  const filesButtonRef = useRef<HTMLButtonElement | null>(null);
  const detailsButtonRef = useRef<HTMLButtonElement | null>(null);
  const filesRegionRef = useRef<HTMLElement | null>(null);
  const detailsRegionRef = useRef<HTMLElement | null>(null);

  // A new owner scope resets only the disclosure state, before paint. Owner
  // slots themselves are never re-keyed or remounted here.
  if (disclosureScopeKey !== scopeKey) {
    setDisclosureScopeKey(scopeKey);
    setDisclosure(null);
  }

  const filesRegionId = useId();
  const detailsRegionId = useId();

  // Opening a below-composer disclosure must bring its named content into
  // keyboard reach. Source/locale refreshes do not repeat this focus change.
  useLayoutEffect(() => {
    if (disclosure === 'files') filesRegionRef.current?.focus();
    if (disclosure === 'details') detailsRegionRef.current?.focus();
  }, [disclosure]);

  const hasStatus = statusPanel !== undefined && statusPanel !== null;
  const hasPause = pauseControl !== undefined && pauseControl !== null;
  const hasFiles = filesPanel !== undefined && filesPanel !== null;
  const hasDetails = detailsPanel !== undefined && detailsPanel !== null;

  const closeWithFocusReturn = (name: DisclosureName) => {
    setDisclosure((current) => (current === name ? null : current));
    const button = name === 'files' ? filesButtonRef.current : detailsButtonRef.current;
    button?.focus();
  };

  const handleDisclosureKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape' && disclosure !== null) {
      event.stopPropagation();
      closeWithFocusReturn(disclosure);
    }
  };

  const filesControl = (
    <span className="mm-project-workspace__control">
      <button
        type="button"
        ref={filesButtonRef}
        className="mm-project-workspace__control-button"
        onClick={() => setDisclosure((current) => (current === 'files' ? null : 'files'))}
        aria-expanded={disclosure === 'files'}
        aria-controls={hasFiles ? filesRegionId : undefined}
        disabled={!hasFiles}
        title={hasFiles ? undefined : copy.filesUnavailable}
      >
        {copy.filesLabel}
      </button>
      {hasFiles ? null : (
        <span className="mm-project-workspace__control-why mm-project-workspace__muted">
          {copy.filesUnavailable}
        </span>
      )}
    </span>
  );

  const detailsControl = (
    <span className="mm-project-workspace__control">
      <button
        type="button"
        ref={detailsButtonRef}
        className="mm-project-workspace__control-button"
        onClick={() => setDisclosure((current) => (current === 'details' ? null : 'details'))}
        aria-expanded={disclosure === 'details'}
        aria-controls={hasDetails ? detailsRegionId : undefined}
        disabled={!hasDetails}
        title={hasDetails ? undefined : copy.detailsUnavailable}
      >
        {copy.detailsLabel}
      </button>
      {hasDetails ? null : (
        <span className="mm-project-workspace__control-why mm-project-workspace__muted">
          {copy.detailsUnavailable}
        </span>
      )}
    </span>
  );

  return (
    <div className="mm-project-workspace" lang={locale} data-workspace-root="true">
      <header className="mm-project-workspace__header">
        <Heading ref={props.headingRef} tabIndex={props.headingRef ? -1 : undefined} className="mm-project-workspace__title">{title ?? copy.fallbackTitle}</Heading>
        <div className="mm-project-workspace__goal-block">
          <p className="mm-project-workspace__sr-only">{copy.goalLabel}</p>
          {goal === null ? (
            <p className="mm-project-workspace__goal-text mm-project-workspace__muted">
              {copy.goalEmpty}
            </p>
          ) : (
            <p className="mm-project-workspace__goal-text">{goal}</p>
          )}
        </div>
        <div className="mm-project-workspace__controls">
          {startWorkControl}
          {filesControl}
          {detailsControl}
        </div>
      </header>
      {hasStatus || hasPause ? (
        <div className="mm-project-workspace__status-strip" data-workspace-slot="status-strip">
          {hasStatus ? (
            <div className="mm-project-workspace__status-panel" data-workspace-slot="status">
              <span className="mm-project-workspace__sr-only">{copy.statusLabel}</span>
              {statusPanel}
            </div>
          ) : null}
          {hasPause ? (
            <div className="mm-project-workspace__pause-slot" data-workspace-slot="pause">
              {pauseControl}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="mm-project-workspace__launch" data-workspace-slot="launch">
        {launchPanel}
      </div>
      {/* Conversation first, then composer: unboxed owner content in stable
          slots. Toggling disclosures never moves or remounts these nodes. */}
      <div className="mm-project-workspace__conversation" data-workspace-slot="conversation">
        {conversationPanel}
      </div>
      <div className="mm-project-workspace__composer" data-workspace-slot="composer">
        {composerPanel}
      </div>
      {/* Named disclosures render after the composer so opening or closing
          them leaves the conversation and composer positions untouched. */}
      <div className="mm-project-workspace__disclosures">
        {disclosure === 'files' && hasFiles ? (
          <section
            ref={filesRegionRef}
            tabIndex={-1}
            id={filesRegionId}
            className="mm-project-workspace__disclosure"
            data-workspace-disclosure="files"
            aria-label={copy.filesLabel}
            onKeyDown={handleDisclosureKeyDown}
          >
            <div className="mm-project-workspace__disclosure-head">
              <p className="mm-project-workspace__section-title">{copy.filesLabel}</p>
              <button
                type="button"
                className="mm-project-workspace__close"
                onClick={() => closeWithFocusReturn('files')}
              >
                {copy.closeLabel}
              </button>
            </div>
            <div className="mm-project-workspace__disclosure-body" data-workspace-slot="files-panel">
              {filesPanel}
            </div>
          </section>
        ) : null}
        {disclosure === 'details' && hasDetails ? (
          <section
            ref={detailsRegionRef}
            tabIndex={-1}
            id={detailsRegionId}
            className="mm-project-workspace__disclosure"
            data-workspace-disclosure="details"
            aria-label={copy.detailsLabel}
            onKeyDown={handleDisclosureKeyDown}
          >
            <div className="mm-project-workspace__disclosure-head">
              <p className="mm-project-workspace__section-title">{copy.detailsLabel}</p>
              <button
                type="button"
                className="mm-project-workspace__close"
                onClick={() => closeWithFocusReturn('details')}
              >
                {copy.closeLabel}
              </button>
            </div>
            <div className="mm-project-workspace__disclosure-body" data-workspace-slot="details-panel">
              {detailsPanel}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}

export default ProjectWorkspace;

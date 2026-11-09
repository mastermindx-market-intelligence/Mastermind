// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ProjectWorkspaceProps } from './ProjectWorkspace';
import { ProjectWorkspace } from './ProjectWorkspace';

afterEach(cleanup);

/**
 * All fixture data below is strictly synthetic: it exists only to prove that
 * the owner-provided slots render exactly as supplied and that this frame
 * invents no status, goals, subtitles or assistant content of its own.
 */
function buildProps(overrides: Partial<ProjectWorkspaceProps> = {}): ProjectWorkspaceProps {
  return {
    scopeKey: 'scope-alpha',
    locale: 'en',
    title: 'Quarterly Report',
    goal: 'Summarize the quarter for the review board.',
    conversationPanel: (
      <ol aria-label="Conversation transcript">
        <li>Synthetic facilitator turn: confirm the reporting window.</li>
      </ol>
    ),
    composerPanel: (
      <form aria-label="Composer">
        <textarea aria-label="Message draft" defaultValue="" placeholder="Draft a message" />
      </form>
    ),
    ...overrides,
  };
}

describe('ProjectWorkspace', () => {
  it('opens a rootless project detail slot into keyboard reach without refocusing on refresh', () => {
    const props = buildProps({ scopeKey: 'synthetic-rootless-work', detailsPanel: <p>Supplied rootless plan and journal</p> });
    const view = render(<ProjectWorkspace {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Project details' }));
    const region = screen.getByRole('region', { name: 'Project details' });
    expect(document.activeElement).toBe(region);
    const draft = screen.getByRole('textbox', { name: 'Message draft' });
    draft.focus();
    view.rerender(<ProjectWorkspace {...props} title="Updated supplied title" />);
    expect(document.activeElement).toBe(draft);
    expect(screen.getByText('Supplied rootless plan and journal')).toBeTruthy();
  });

  it('renders owner conversation and composer nodes exactly, with no invented content (en)', () => {
    render(<ProjectWorkspace {...buildProps()} />);
    expect(screen.getByRole('list', { name: 'Conversation transcript' })).toBeTruthy();
    expect(
      screen.getByText('Synthetic facilitator turn: confirm the reporting window.'),
    ).toBeTruthy();
    expect(screen.getByRole('textbox', { name: 'Message draft' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Quarterly Report', level: 2 })).toBeTruthy();
    expect(screen.getByText('Summarize the quarter for the review board.')).toBeTruthy();
    // No invented status, subtitle or assistant sample anywhere in the frame.
    expect(screen.queryByText(/assistant/i)).toBeNull();
    expect(screen.queryByText(/working/i)).toBeNull();
    expect(screen.queryByText(/paused/i)).toBeNull();
    expect(screen.queryByText(/created/i)).toBeNull();
  });

  it('falls back honestly when title and goal are absent (en)', () => {
    render(<ProjectWorkspace {...buildProps({ title: null, goal: null })} />);
    expect(screen.getByRole('heading', { name: 'Project workspace', level: 2 })).toBeTruthy();
    expect(screen.getByText('Project goal has not been supplied.')).toBeTruthy();
    expect(screen.queryByText('Summarize the quarter for the review board.')).toBeNull();
  });

  it('falls back honestly when title and goal are absent (zh-CN)', () => {
    render(
      <ProjectWorkspace
        {...buildProps({ locale: 'zh-CN', title: null, goal: null })}
      />,
    );
    expect(screen.getByRole('heading', { name: '项目工作区', level: 2 })).toBeTruthy();
    expect(screen.getByText('尚未提供项目目标。')).toBeTruthy();
  });

  it('does not invent status or pause controls when the owner omits them', () => {
    render(<ProjectWorkspace {...buildProps()} />);
    expect(screen.queryByTestId('owner-status')).toBeNull();
    expect(screen.queryByText(/working/i)).toBeNull();
    expect(screen.queryByText(/paused/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /pause/i })).toBeNull();
  });

  it('renders provided status panel and pause control without alteration', () => {
    render(
      <ProjectWorkspace
        {...buildProps({
          statusPanel: <p data-testid="owner-status">Synthetic owner status text</p>,
          pauseControl: (
            <button type="button" data-testid="owner-pause">
              Pause project run
            </button>
          ),
        })}
      />,
    );
    expect(screen.getByTestId('owner-status').textContent).toBe('Synthetic owner status text');
    const pause = screen.getByTestId('owner-pause');
    expect(pause.textContent).toBe('Pause project run');
    expect(pause.getAttribute('type')).toBe('button');
    expect(screen.getByRole('button', { name: 'Pause project run' })).toBeTruthy();
  });

  it('opens the owner files panel, closes on Escape and returns focus to the Files control', () => {
    render(
      <ProjectWorkspace
        {...buildProps({ filesPanel: <div data-testid="owner-files">Synthetic files listing</div> })}
      />,
    );
    const filesButton = screen.getByRole('button', { name: 'Files' });
    expect(filesButton.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByTestId('owner-files')).toBeNull();
    fireEvent.click(filesButton);
    expect(screen.getByTestId('owner-files').textContent).toBe('Synthetic files listing');
    expect(filesButton.getAttribute('aria-expanded')).toBe('true');
    const region = screen
      .getByTestId('owner-files')
      .closest('[data-workspace-disclosure="files"]') as HTMLElement;
    fireEvent.keyDown(region, { key: 'Escape' });
    expect(screen.queryByTestId('owner-files')).toBeNull();
    expect(filesButton.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(filesButton);
  });

  it('opens the owner project details panel, closes via Close and returns focus', () => {
    render(
      <ProjectWorkspace
        {...buildProps({
          detailsPanel: (
            <dl data-testid="owner-details">
              <dt>Owner field</dt>
              <dd>Owner value</dd>
            </dl>
          ),
        })}
      />,
    );
    const detailsButton = screen.getByRole('button', { name: 'Project details' });
    fireEvent.click(detailsButton);
    expect(screen.getByTestId('owner-details').textContent).toContain('Owner value');
    expect(detailsButton.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByTestId('owner-details')).toBeNull();
    expect(detailsButton.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(detailsButton);
  });

  it('keeps the uncontrolled composer draft and node across locale, title, goal updates and disclosure toggles', () => {
    const { rerender } = render(
      <ProjectWorkspace
        {...buildProps({ filesPanel: <div data-testid="owner-files">Synthetic files listing</div> })}
      />,
    );
    const draft = screen.getByRole('textbox', { name: 'Message draft' }) as HTMLTextAreaElement;
    fireEvent.change(draft, { target: { value: 'Owner draft line retained locally' } });
    expect(draft.value).toBe('Owner draft line retained locally');
    fireEvent.click(screen.getByRole('button', { name: 'Files' }));
    expect(screen.getByTestId('owner-files')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByTestId('owner-files')).toBeNull();
    rerender(
      <ProjectWorkspace
        {...buildProps({
          locale: 'zh-CN',
          title: '季度报告',
          goal: '为评审会准备季度摘要。',
          filesPanel: <div data-testid="owner-files">Synthetic files listing</div>,
        })}
      />,
    );
    const draftAfter = screen.getByRole('textbox', { name: 'Message draft' }) as HTMLTextAreaElement;
    expect(draftAfter).toBe(draft);
    expect(draftAfter.value).toBe('Owner draft line retained locally');
  });

  it('closes an open disclosure when the owner scope key changes, without claiming new authority', () => {
    const { rerender } = render(
      <ProjectWorkspace
        {...buildProps({ filesPanel: <div data-testid="owner-files">Synthetic files listing</div> })}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Files' }));
    expect(screen.getByTestId('owner-files')).toBeTruthy();
    rerender(
      <ProjectWorkspace
        {...buildProps({
          scopeKey: 'scope-beta',
          filesPanel: <div data-testid="owner-files">Synthetic files listing</div>,
        })}
      />,
    );
    expect(screen.queryByTestId('owner-files')).toBeNull();
    expect(screen.getByRole('button', { name: 'Files' }).getAttribute('aria-expanded')).toBe(
      'false',
    );
  });

  it('disables Files and Project details with a plain reason when the owner omits those panels', () => {
    render(<ProjectWorkspace {...buildProps()} />);
    const filesButton = screen.getByRole('button', { name: 'Files' }) as HTMLButtonElement;
    const detailsButton = screen.getByRole('button', { name: 'Project details' }) as HTMLButtonElement;
    expect(filesButton.disabled).toBe(true);
    expect(detailsButton.disabled).toBe(true);
    expect(screen.getByText('Files are not available for this project yet.')).toBeTruthy();
    expect(screen.getByText('Project details are not available for this project yet.')).toBeTruthy();
    fireEvent.click(filesButton);
    expect(screen.queryByTestId('owner-files')).toBeNull();
  });

  it('renders complete zh-CN copy around owner slots without altering them', () => {
    render(
      <ProjectWorkspace
        {...buildProps({
          locale: 'zh-CN',
          title: '季度报告',
          goal: '为评审会准备季度摘要。',
          filesPanel: <div data-testid="owner-files">合成文件列表</div>,
          detailsPanel: (
            <dl data-testid="owner-details">
              <dt>负责人</dt>
              <dd>待定</dd>
            </dl>
          ),
        })}
      />,
    );
    expect(screen.getByRole('heading', { name: '季度报告', level: 2 })).toBeTruthy();
    expect(screen.getByText('目标')).toBeTruthy();
    expect(screen.getByText('为评审会准备季度摘要。')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '文件' }));
    expect(screen.getByTestId('owner-files').textContent).toBe('合成文件列表');
    expect(screen.getByRole('button', { name: '关闭' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    fireEvent.click(screen.getByRole('button', { name: '项目详情' }));
    expect(screen.getByTestId('owner-details').textContent).toContain('待定');
  });

  it('keeps exactly one h2 frame heading and never renders an h1 of its own', () => {
    render(
      <ProjectWorkspace
        {...buildProps({ filesPanel: <div data-testid="owner-files">Synthetic files listing</div> })}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Files' }));
    expect(document.querySelectorAll('h1')).toHaveLength(0);
    const headings = document.querySelectorAll('h2');
    expect(headings).toHaveLength(1);
    expect(headings[0]?.textContent).toBe('Quarterly Report');
  });
});

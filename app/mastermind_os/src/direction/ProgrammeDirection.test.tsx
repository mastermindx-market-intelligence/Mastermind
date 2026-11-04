// @vitest-environment jsdom
import { cloneElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ProgrammeDirection as ActualProgrammeDirection, type ProgrammeDirectionProps } from './ProgrammeDirection';
const DEFAULT_GENERATION = () => 0;
const DEFAULT_PERMISSION = () => true;
function ProgrammeDirection(props: ProgrammeDirectionProps) {
  return <ActualProgrammeDirection sourceGeneration={DEFAULT_GENERATION} canRead={DEFAULT_PERMISSION} {...props} />;
}
import {decodeProjectPlan, type ProjectPlanRead, type ProjectPlanSelection} from '../planning/project-plan';
import v2Fixture from '../fixtures/project-plan-v2-owner.json';

afterEach(cleanup);

type Revision = { commit: string; committed_at: string; content_sha256: string };
type Request = ProjectPlanSelection & { signal: AbortSignal };

function makeRevision(index: number): Revision {
  const ordinal = String(index).padStart(2, '0');
  return {
    commit: (index + 1).toString(16).padStart(40, '0'),
    committed_at: `2026-01-${String((index % 28) + 1).padStart(2, '0')}T00:00:00Z`,
    content_sha256: (index + 1).toString(16).padStart(64, '0'),
  };
}

function makeAvailable(
  options?: {
    workRef?: string;
    title?: string;
    history?: Extract<ProjectPlanRead, { availability: 'AVAILABLE' }>['plan']['version_history'];
  },
): ProjectPlanRead {
  const workRef = options?.workRef ?? 'WS:ALPHA';
  const history = options?.history ?? {
    state: 'AVAILABLE' as const,
    kind: 'GIT_RECORD_REVISIONS' as const,
    revisions: Array.from({ length: 10 }, (_, index) => makeRevision(index)),
  };
  return {
    schema: 'mastermind.workspace_project_plan.v1',
    selection: { work_ref: workRef },
    availability: 'AVAILABLE',
    source: {
      repository: 'mastermindx-market-intelligence/macro',
      commit: 'a'.repeat(40),
      path: 'agentos/workstreams/WS-ALPHA.md',
      content_sha256: 'b'.repeat(64),
    },
    plan: {
      title: options?.title ?? 'Office programme direction draft',
      objective: 'Stabilise the office objective pipeline.',
      status: 'DRAFT',
      owner: 'Office Steward',
      next_action: 'Confirm wave two scope.',
      waves: [
        {
          id: 'w1',
          title: 'Wave one',
          status: 'DONE',
          depends_on: [],
          next_action: null,
          prs: [101, 102],
        },
      ],
      adoption: { state: 'UNAVAILABLE', reason: 'NOT_DECLARED' },
      version_history: history,
    },
    reason_codes: [],
  };
}

function makeUnavailable(
  workRef = 'WS:ALPHA',
  reasonCodes: Extract<ProjectPlanRead, { availability: 'UNAVAILABLE' }>['reason_codes'] = ['RECORD_NOT_FOUND'],
): ProjectPlanRead {
  return {
    schema: 'mastermind.workspace_project_plan.v1',
    selection: { work_ref: workRef },
    availability: 'UNAVAILABLE',
    source: null,
    plan: null,
    reason_codes: reasonCodes,
  };
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
}

function makeDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function readerWithDeferreds() {
  const deferreds: Array<Deferred<ProjectPlanRead>> = [];
  const read = vi.fn((_request: Request) => {
    const deferred = makeDeferred<ProjectPlanRead>();
    deferreds.push(deferred);
    return deferred.promise;
  });
  return { read, deferreds };
}

const READ_BUTTON = 'Read programme objective';

async function clickRead(): Promise<HTMLButtonElement> {
  const button = screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement;
  fireEvent.click(button);
  return button;
}

function assertText(text: string | RegExp): void {
  if (screen.queryByText(text) === null) {
    throw new Error(`expected text to be present: ${text}`);
  }
}

describe('ProgrammeDirection', () => {
  it('requires both the current permission and generation owners before reading', () => {
    const read = vi.fn();
    const view = render(<ActualProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={read} />);
    expect((screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement).disabled).toBe(true);
    view.rerender(<ActualProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={read} canRead={DEFAULT_PERMISSION} />);
    expect((screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement).disabled).toBe(true);
    view.rerender(<ActualProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={read} sourceGeneration={DEFAULT_GENERATION} />);
    expect((screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement).disabled).toBe(true);
    expect(read).not.toHaveBeenCalled();
  });

  it('clears an acquisition when the reader changes at the same source generation', async () => {
    const first = readerWithDeferreds(), second = readerWithDeferreds();
    const view = render(<ProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={first.read} />);
    await clickRead();
    await act(async () => first.deferreds[0].resolve(makeAvailable({ title: 'Original reader content' })));
    assertText('Original reader content');
    view.rerender(<ProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={second.read} />);
    expect(screen.queryByText('Original reader content')).toBeNull();
    await clickRead();
    expect(second.read).toHaveBeenCalledTimes(1);
  });

  it('preserves a pending read across equivalent selection object churn', async () => {
    const { read, deferreds } = readerWithDeferreds();
    const view = render(<ProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={read} />);
    await clickRead();
    view.rerender(<ProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={read} />);
    expect(read.mock.calls[0][0].signal.aborted).toBe(false);
    await act(async () => deferreds[0].resolve(makeAvailable()));
    assertText('Stabilise the office objective pipeline.');
  });

  it('fails closed when the current source or permission getter throws', () => {
    const read = vi.fn();
    const view = render(<ProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={read}
      sourceGeneration={() => { throw new Error('PRIVATE_SOURCE_FAILURE'); }} />);
    expect((screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement).disabled).toBe(true);
    view.rerender(<ProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} read={read}
      canRead={() => { throw new Error('PRIVATE_PERMISSION_FAILURE'); }} />);
    expect((screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText(/PRIVATE_/)).toBeNull();
    expect(read).not.toHaveBeenCalled();
  });

  it('does not auto-read, reads on click, and expands source plus history', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    const { read, deferreds } = readerWithDeferreds();
    render(<ProgrammeDirection selection={selection} read={read} />);
    expect(read).not.toHaveBeenCalled();

    const button = await clickRead();
    expect(button.disabled).toBe(true);
    expect(read).toHaveBeenCalledTimes(1);
    expect(read.mock.calls[0][0].work_ref).toBe('WS:ALPHA');
    expect(read.mock.calls[0][0].signal.aborted).toBe(false);

    await act(async () => {
      deferreds[0].resolve(makeAvailable());
    });

    assertText('Office programme direction draft');
    assertText('Stabilise the office objective pipeline.');
    assertText('Authored status');
    assertText('DRAFT');
    assertText('Office Steward');
    assertText('Confirm wave two scope.');
    assertText(/Wave one/);
    assertText(/101, 102/);

    fireEvent.click(screen.getByText('Source'));
    assertText('mastermindx-market-intelligence/macro');
    assertText('a'.repeat(40));
    assertText('agentos/workstreams/WS-ALPHA.md');
    assertText('b'.repeat(64));

    fireEvent.click(screen.getByText('Source record revisions'));
    assertText('10 revisions');
    assertText(new RegExp(makeRevision(7).commit));
    expect(screen.queryByText(new RegExp(makeRevision(8).commit))).toBeNull();

    fireEvent.click(screen.getByText('Show all 10 revisions'));
    assertText(new RegExp(makeRevision(8).commit));
    assertText(new RegExp(makeRevision(9).commit));

    fireEvent.click(screen.getByText('Show fewer'));
    expect(screen.queryByText(new RegExp(makeRevision(8).commit))).toBeNull();
    assertText(new RegExp(makeRevision(7).commit));
  });

  it('renders an unavailable body with reason codes and no history claim', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    const { read, deferreds } = readerWithDeferreds();
    render(<ProgrammeDirection selection={selection} read={read} />);
    await clickRead();
    await act(async () => {
      deferreds[0].resolve(makeUnavailable());
    });

    assertText('The programme plan is unavailable for this selection.');
    assertText('Reason codes');
    assertText('RECORD_NOT_FOUND');
    expect(screen.queryByText('Source record revisions')).toBeNull();
    expect(screen.queryByText(/^0 revisions$/)).toBeNull();
  });

  it('renders unavailable history without claiming any revisions', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    const { read, deferreds } = readerWithDeferreds();
    render(<ProgrammeDirection selection={selection} read={read} />);
    await clickRead();
    await act(async () => {
      deferreds[0].resolve(
        makeAvailable({
          history: { state: 'UNAVAILABLE', reason: 'NOT_SUPPLIED_BY_OWNER' },
        }),
      );
    });

    assertText(/Source record revisions are not available/);
    assertText(/NOT_SUPPLIED_BY_OWNER/);
    expect(screen.queryByText(new RegExp(makeRevision(0).commit))).toBeNull();
    expect(screen.queryByText(/^0 revisions$/)).toBeNull();
    expect(screen.queryByText(/Show all/)).toBeNull();
  });

  it('shows fixed safe copy when the read rejects, never the raw error', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    const { read, deferreds } = readerWithDeferreds();
    render(<ProgrammeDirection selection={selection} read={read} />);
    await clickRead();
    await act(async () => {
      deferreds[0].reject(new Error('SENSITIVE_RAW_FAILURE_DETAILS'));
    });

    assertText('The programme objective could not be read.');
    expect(screen.queryByText(/SENSITIVE_RAW_FAILURE_DETAILS/)).toBeNull();
    const button = screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  it('shows the missing-selection state with a disabled button', () => {
    const { read } = readerWithDeferreds();
    render(<ProgrammeDirection selection={null} read={read} />);
    assertText('No programme plan selection is active.');
    const button = screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(read).not.toHaveBeenCalled();
  });

  it('shows the missing-reader state with a disabled button', () => {
    render(<ProgrammeDirection selection={{ work_ref: 'WS:ALPHA' }} />);
    assertText('No reader is available in this context.');
    const button = screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('hides an old response after a selection switch and reads the new selection', async () => {
    const selectionA: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    const selectionB: ProjectPlanSelection = { work_ref: 'WS:BETA' };
    const { read, deferreds } = readerWithDeferreds();
    const view = render(<ProgrammeDirection selection={selectionA} read={read} />);

    await clickRead();
    view.rerender(<ProgrammeDirection selection={selectionB} read={read} />);
    await act(async () => {
      deferreds[0].resolve(makeAvailable({ workRef: 'WS:ALPHA', title: 'Draft A' }));
    });

    expect(screen.queryByText('Draft A')).toBeNull();
    expect(screen.queryByText(/Reading programme objective/)).toBeNull();

    await clickRead();
    expect(read).toHaveBeenCalledTimes(2);
    expect(read.mock.calls[1][0].work_ref).toBe('WS:BETA');
    await act(async () => {
      deferreds[1].resolve(makeAvailable({ workRef: 'WS:BETA', title: 'Draft B' }));
    });
    assertText('Draft B');
    expect(screen.queryByText('Draft A')).toBeNull();
  });

  it('hides retained content on generation rotation and allows a manual reread', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    let generation = 1;
    const sourceGeneration = () => generation;
    const { read, deferreds } = readerWithDeferreds();
    const ui = (
      <ProgrammeDirection
        selection={selection}
        read={read}
        sourceGeneration={sourceGeneration}
      />
    );
    const view = render(ui);

    await clickRead();
    await act(async () => {
      deferreds[0].resolve(makeAvailable({ title: 'Draft Gen One' }));
    });
    assertText('Draft Gen One');

    generation = 2;
    view.rerender(cloneElement(ui));
    expect(screen.queryByText('Draft Gen One')).toBeNull();
    const button = screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);

    fireEvent.click(button);
    expect(read).toHaveBeenCalledTimes(2);
    await act(async () => {
      deferreds[1].resolve(makeAvailable({ title: 'Draft Gen Two' }));
    });
    assertText('Draft Gen Two');
    expect(screen.queryByText('Draft Gen One')).toBeNull();
  });

  it('erases content on revocation so a same-generation regrant needs a fresh read', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    let permitted = true;
    const canRead = () => permitted;
    const sourceGeneration = () => 7;
    const { read, deferreds } = readerWithDeferreds();
    const ui = (
      <ProgrammeDirection
        selection={selection}
        read={read}
        canRead={canRead}
        sourceGeneration={sourceGeneration}
      />
    );
    const view = render(ui);

    await clickRead();
    await act(async () => {
      deferreds[0].resolve(makeAvailable({ title: 'Draft Permitted' }));
    });
    assertText('Draft Permitted');

    permitted = false;
    view.rerender(cloneElement(ui));
    expect(screen.queryByText('Draft Permitted')).toBeNull();
    let button = screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);

    permitted = true;
    view.rerender(cloneElement(ui));
    expect(screen.queryByText('Draft Permitted')).toBeNull();
    button = screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    expect(read).toHaveBeenCalledTimes(1);

    fireEvent.click(button);
    expect(read).toHaveBeenCalledTimes(2);
    await act(async () => {
      deferreds[1].resolve(makeAvailable({ title: 'Draft Regranted' }));
    });
    assertText('Draft Regranted');
    expect(screen.queryByText('Draft Permitted')).toBeNull();
  });

  it('never shows a stale late resolution after generation rotation mid-read', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    let generation = 1;
    const sourceGeneration = () => generation;
    const { read, deferreds } = readerWithDeferreds();
    const ui = (
      <ProgrammeDirection
        selection={selection}
        read={read}
        sourceGeneration={sourceGeneration}
      />
    );
    const view = render(ui);

    await clickRead();
    expect(read).toHaveBeenCalledTimes(1);

    generation = 2;
    view.rerender(cloneElement(ui));
    expect(screen.queryByText(/Reading programme objective/)).toBeNull();
    const button = screen.getByRole('button', { name: READ_BUTTON }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);

    await act(async () => {
      deferreds[0].resolve(makeAvailable({ title: 'Draft Stale' }));
    });
    expect(screen.queryByText('Draft Stale')).toBeNull();

    fireEvent.click(button);
    expect(read).toHaveBeenCalledTimes(2);
    expect(read.mock.calls[1][0].work_ref).toBe('WS:ALPHA');
    await act(async () => {
      deferreds[1].resolve(makeAvailable({ title: 'Draft Fresh' }));
    });
    assertText('Draft Fresh');
    expect(screen.queryByText('Draft Stale')).toBeNull();
  });

  it('renders the zh-CN states and copy', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    const { read, deferreds } = readerWithDeferreds();
    const view = render(
      <ProgrammeDirection selection={null} read={read} locale="zh-CN" />,
    );
    assertText('当前没有已激活的项目计划选择。');
    let button = screen.getByRole('button', { name: '读取项目目标' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);

    view.rerender(<ProgrammeDirection selection={selection} read={read} locale="zh-CN" />);
    button = screen.getByRole('button', { name: '读取项目目标' }) as HTMLButtonElement;
    fireEvent.click(button);
    await act(async () => {
      deferreds[0].resolve(makeAvailable());
    });
    assertText('原始状态');
    assertText('Stabilise the office objective pipeline.');
    assertText('来源记录修订');
  });

  it('aborts the in-flight read on unmount', async () => {
    const selection: ProjectPlanSelection = { work_ref: 'WS:ALPHA' };
    const { read, deferreds } = readerWithDeferreds();
    const view = render(<ProgrammeDirection selection={selection} read={read} />);
    await clickRead();
    const signal = read.mock.calls[0][0].signal;
    expect(signal.aborted).toBe(false);
    view.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => {
      deferreds[0].resolve(makeAvailable());
    });
  });
});

it.each([['en','Adoption recorded by source','The authored record differs from the recorded adopted source.'],
  ['zh-CN','来源已记录采纳决定','编写记录与已记录的采纳来源不同。']] as const)(
  'shows actual decoded v2 source adoption separately from authored record in %s',async (locale,label,relation) => {
    const selection={work_ref:'WS:PLAN-TEST'};
    const body=decodeProjectPlan(v2Fixture.cases.available_pending,selection);
    const read=vi.fn(async()=>body);
    render(<ProgrammeDirection selection={selection} read={read} locale={locale}/>);
    fireEvent.click(screen.getByRole('button',{name:locale==='en'?'Read programme objective':'读取项目目标'}));
    expect(await screen.findByText(`${label} · DEC:PLAN-FIRST`,{exact:false})).toBeTruthy();
    expect(screen.getByText(relation)).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button',{name:/Adopt|采纳/})).toBeNull();
  });

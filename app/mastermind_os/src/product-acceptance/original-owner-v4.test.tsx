// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IDBFactory } from "fake-indexeddb";
import { createWebAuth } from "../web-auth";
import { composeMissionHost } from "../compose-mission-host";
import { App } from "../App";
import { ProductAcceptancePanel } from "./ProductAcceptancePanel";
import { ORIGIN } from "../public-config";
import fixture from "../fixtures/mission-v4-owner-accepted.json";
import programsFixture from "../fixtures/programs-available-workspace-service.json";
import { controlRoomFixture } from "../test-fixtures";
import type { MissionHost } from "../host";
const selected = { workRef: fixture.product_acceptance.selection.work_ref, rootJobId: fixture.product_acceptance.selection.root_job_id };
const flush = async () => { for (let n = 0; n < 30; n++) await Promise.resolve(); };
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
const disposals: Array<() => void> = [];
function setup() {
  let count = 0;
  const callbacks = new Set<(e: MessageEvent) => void>();
  const popup = { location: "", closed: false, close: vi.fn() };
  const room = controlRoomFixture(); room.work = [room.work[0]]; room.autonomy.responsibilities = [room.autonomy.responsibilities[0]];
  room.work[0].work_ref = selected.workRef; room.work[0].agent_os.workstream = "FIXTURE"; room.work[0].agent_os.title = "Acceptance project";
  Object.assign(room.autonomy.responsibilities[0], { responsibility_ref: selected.workRef, root_job_id: selected.rootJobId, root_job_candidates: [selected.rootJobId], root_job_ambiguous: false, runtime_root_state: "RESOLVED" });
  const payload = vi.fn(async (): Promise<Response> => response(structuredClone(fixture)));
  const fetcher = vi.fn<typeof fetch>(async url => {
    const path = new URL(String(url)).pathname;
    if (path.endsWith('/oauth/token')) return response({ token_type: "Bearer", access_token: "inert-fixture-token", expires_in: 3600, scope: new URL(popup.location).searchParams.get("scope") });
    if (path === '/workspace/mission/v4/current') return payload();
    if (path === '/workspace/programs/current') return response({ ...structuredClone(programsFixture), control_room: room });
    if (path === '/workspace/mission/v3/current') return response(fixture.mission);
    return response({}, 503);
  });
  const client = createWebAuth({ config: { webClientId: "inert-public-client" }, fetchFn: fetcher, openPopup: () => popup,
    crypto: { getRandomValues(a: Uint8Array) { a.fill(++count); return a; }, subtle: { digest: async () => new ArrayBuffer(32) } } as unknown as Crypto,
    addEventListener: ((_t: string, fn: (e: MessageEvent) => void) => callbacks.add(fn)) as typeof window.addEventListener,
    removeEventListener: ((_t: string, fn: (e: MessageEvent) => void) => callbacks.delete(fn)) as typeof window.removeEventListener });
  const callback = () => { for (const fn of [...callbacks]) fn({ source: popup, origin: ORIGIN, data: { type: "mastermind-auth-callback", state: new URL(popup.location).searchParams.get("state"), code: "inert-code" } } as unknown as MessageEvent); };
  const login = async () => { const p = client.signIn(); await flush(); callback(); await flush(); callback(); await p; };
  const composed = composeMissionHost(client, null, new IDBFactory()); disposals.push(composed.dispose);
  const calls = () => fetcher.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/workspace/mission/v4/current');
  return { client, host: composed.host, fetcher, payload, calls, login };
}
afterEach(() => { cleanup(); disposals.splice(0).forEach(fn => fn()); delete window.MastermindMissionHost; history.replaceState(null, '', '/os/'); vi.restoreAllMocks(); });
const request = () => ({ ...selected, signal: new AbortController().signal });
describe('mounted private Workspace original-owner acquisition', () => {
  it('consumes one full body through real web and host composition without a selector attachment', async () => {
    const e = setup(); await e.login(); expect(e.host.productAcceptanceOwner).toBeUndefined(); expect(e.host.readMissionV4).toBeUndefined();
    const result = await e.host.readOriginalMissionV4!(request()); expect(result).toEqual(fixture); expect(e.calls()).toHaveLength(1);
    const [url, options] = e.calls()[0]; const u = new URL(String(url));
    expect(u.origin).toBe(ORIGIN); expect([...u.searchParams]).toEqual([['work_ref', selected.workRef], ['root_job_id', selected.rootJobId], ['read_mode', 'original_owner']]);
    expect(options).toMatchObject({ method: 'GET', redirect: 'error', credentials: 'omit', cache: 'no-store' }); expect(options?.body).toBeUndefined();
    expect(JSON.stringify(e.client)).not.toContain('inert-fixture-token');
  });
  it('makes zero HTTP reads while signed out', async () => { const e = setup(); await expect(e.host.readOriginalMissionV4!(request())).rejects.toThrow(); expect(e.calls()).toHaveLength(0); });
  it.each(['requestMessageKey', 'read_mode', 'extra'])('refuses caller-added %s before HTTP', async extra => {
    const e = setup(); await e.login(); await expect(e.host.readOriginalMissionV4!({ ...request(), [extra]: 'forbidden' })).rejects.toThrow('SELECTION_INVALID'); expect(e.calls()).toHaveLength(0);
    await expect(e.client.readOriginalMissionV4!({ ...request(), [extra]: 'forbidden' })).rejects.toThrow('SELECTION_INVALID'); expect(e.calls()).toHaveLength(0);
  });
  it.each(['foreignWork', 'foreignRoot', 'missingKey', 'badKey', 'forgedResult', 'surplus', 'wrapper'])('rejects %s body without a second read', async defect => {
    const e = setup(); await e.login(); const body: any = structuredClone(fixture);
    if (defect === 'foreignWork') body.product_acceptance.selection.work_ref = 'WS:FOREIGN';
    if (defect === 'foreignRoot') body.product_acceptance.selection.root_job_id = 'JOB-999';
    if (defect === 'missingKey') delete body.product_acceptance.selection.request_message_key;
    if (defect === 'badKey') body.product_acceptance.selection.request_message_key = 'not-an-original-key';
    if (defect === 'forgedResult') body.product_acceptance.receipt.parent_result_envelope_digest = 'f'.repeat(64);
    if (defect === 'surplus') body.extra = true;
    e.payload.mockImplementation(async () => response(defect === 'wrapper' ? { ok: true, result: body } : body));
    await expect(e.host.readOriginalMissionV4!(request())).rejects.toThrow('MISSION_V4_RESPONSE_INVALID'); expect(e.calls()).toHaveLength(1);
  });
  it.each([401,403,404,503])('keeps HTTP %s unavailable without a key or fallback', async status => {
    const e = setup(); await e.login(); e.payload.mockImplementation(async () => response({}, status));
    await expect(e.host.readOriginalMissionV4!(request())).rejects.toThrow(); expect(e.calls()).toHaveLength(1);
  });
  it('propagates a qualified unavailable body through the unchanged decoder', async () => {
    const e = setup(); await e.login(); const body: any = structuredClone(fixture); body.product_acceptance = { ...body.product_acceptance, state: 'UNAVAILABLE', receipt: null, reason_codes: ['PARENT_CONSUMPTION_UNPROVEN'] };
    e.payload.mockImplementation(async () => response(body)); expect(await e.host.readOriginalMissionV4!(request())).toEqual(body); expect(e.calls()).toHaveLength(1);
  });
  it.each(['abort', 'authABA', 'clientMethodReplacement'])('withholds an abort-ignoring mounted read after %s', async event => {
    const e = setup(); await e.login(); let resolve!: (r: Response) => void; e.payload.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    const abort = new AbortController(); const pending = e.host.readOriginalMissionV4!({ ...selected, signal: abort.signal }); const assertion = expect(pending).rejects.toThrow(); await flush();
    if (event === 'abort') abort.abort();
    if (event === 'authABA') { await e.client.signOut(); await e.login(); }
    if (event === 'clientMethodReplacement') e.client.readOriginalMissionV4 = async () => structuredClone(fixture);
    resolve(response(fixture)); await assertion; expect(e.calls()).toHaveLength(1);
  });
  it.each(['selectionABA', 'hostReplacement', 'authWithdrawal', 'unmount'])('withholds a mounted-panel late response after %s', async event => {
    const e = setup(); await e.login(); let resolve!: (r: Response) => void;
    e.payload.mockImplementation(() => new Promise(() => {})).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    let generation = 1, currentHost: MissionHost | undefined = e.host;
    const props = { host: e.host, selection: selected, selectionGeneration: 1, currentSelectionGeneration: () => generation, currentHost: () => currentHost, authRevision: 1, enabled: true, locale: 'en' };
    const ui = render(<ProductAcceptancePanel {...props}/>); await waitFor(() => expect(e.calls()).toHaveLength(1));
    await act(async () => { if (event === 'selectionABA') generation += 2; if (event === 'hostReplacement') currentHost = { ...e.host }; if (event === 'authWithdrawal') await e.client.signOut(); if (event === 'unmount') ui.unmount(); });
    await act(async () => { resolve(response(fixture)); await flush(); }); expect(screen.queryByText('PRODUCT_ACCEPTED')).toBeNull();
  });
  it.each([200,503])('renders actual App Evidence from the mounted HTTP body, status=%s', async status => {
    const e = setup(); await e.login(); if (status !== 200) e.payload.mockImplementation(async () => response({}, status));
    window.MastermindMissionHost = e.host; history.replaceState(null, '', '/os/?request_message_key=asd-mcp-' + '0'.repeat(32));
    const ui = render(<App/>), user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Projects' }));
    await user.click(await screen.findByRole('button', { name: 'Open project Acceptance project' }));
    await user.click(await screen.findByRole('tab', { name: 'Evidence' }));
    const panel = await screen.findByRole('region', { name: 'Product acceptance receipt' });
    await within(panel).findByText(status === 200 ? 'PRODUCT_ACCEPTED' : 'UNAVAILABLE');
    await waitFor(() => expect(e.calls()).toHaveLength(1));
    expect(new URL(String(e.calls()[0][0])).searchParams.has('request_message_key')).toBe(false);
    expect(within(panel).queryAllByRole('button')).toHaveLength(0);
    ui.rerender(<App/>); await act(async () => { await flush(); }); expect(e.calls()).toHaveLength(1);
  });
});

describe('original-owner panel composition boundaries', () => {
  it('does not depend on or fall back to an uncomposed legacy selector attachment', async () => {
    const e = setup(); await e.login(); const legacy = vi.fn(async () => fixture);
    Object.defineProperty(e.host, 'productAcceptanceOwner', { value: { getSnapshot: () => null, subscribe: () => () => {} } });
    e.host.readMissionV4 = legacy;
    render(<ProductAcceptancePanel host={e.host} selection={selected} selectionGeneration={1} currentSelectionGeneration={() => 1} currentHost={() => e.host} authRevision={1} enabled locale="en"/>);
    await screen.findByText('PRODUCT_ACCEPTED'); expect(e.calls()).toHaveLength(1); expect(legacy).not.toHaveBeenCalled();
  });
  it('clears an already rendered original-owner receipt on authentication withdrawal', async () => {
    const e = setup(); await e.login();
    render(<ProductAcceptancePanel host={e.host} selection={selected} selectionGeneration={1} currentSelectionGeneration={() => 1} currentHost={() => e.host} authRevision={1} enabled locale="en"/>);
    await screen.findByText('PRODUCT_ACCEPTED'); await act(async () => { await e.client.signOut(); });
    expect(screen.queryByText('PRODUCT_ACCEPTED')).toBeNull(); expect(screen.getByText('UNAVAILABLE')).toBeTruthy(); expect(e.calls()).toHaveLength(1);
  });
  it('never uses a legacy read to mask an original-owner acquisition failure', async () => {
    const e = setup(); await e.login(); const legacy = vi.fn(async () => fixture); e.host.readMissionV4 = legacy;
    e.payload.mockImplementation(async () => response({}, 503));
    render(<ProductAcceptancePanel host={e.host} selection={selected} selectionGeneration={1} currentSelectionGeneration={() => 1} currentHost={() => e.host} authRevision={1} enabled locale="zh"/>);
    await screen.findByText('UNAVAILABLE'); await waitFor(() => expect(e.calls()).toHaveLength(1));
    expect(screen.queryByText('PRODUCT_ACCEPTED')).toBeNull(); expect(legacy).not.toHaveBeenCalled();
  });
});

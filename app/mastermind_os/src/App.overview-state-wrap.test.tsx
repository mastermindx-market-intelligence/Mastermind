// @vitest-environment jsdom
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import css from './styles.css?raw';
import postcss from 'postcss';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from './App';
import { decodeMission } from './mission';
import { decodeProgramsObservation } from './programs-observation';
import { controlRoomFixture, missionFixture, realMissionFixture } from './test-fixtures';
import programs from './fixtures/programs-available-workspace-service.json';

// Source/DOM proof only. jsdom has no layout: these tests never claim pixel fit.
// Removing the mobile wrap override must fail the 390px CSS contract below.
const selector = 'main .grid > .card > dl .state';
function cssAtWidth(width: number) {
  const sheet = postcss.parse(css);
  // Model only this stylesheet's max-width media conditions, not browser layout.
  sheet.walkAtRules('media', rule => {
    const match = rule.params.match(/^\(max-width:\s*(\d+)px\)$/);
    if (!match) throw new Error(`Unsupported media condition: ${rule.params}`);
    if (width <= Number(match[1])) rule.replaceWith(...rule.nodes!);
    else rule.remove();
  });
  return sheet.toString();
}
let container: HTMLDivElement, root: Root | null, style: HTMLStyleElement;
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const qualifiedPrograms = () => decodeProgramsObservation({ ...structuredClone(programs), control_room: controlRoomFixture() });
async function click(label: string) {
  const button = [...container.querySelectorAll<HTMLButtonElement>('button')].find(b => (b.getAttribute('aria-label') || b.textContent?.trim()) === label);
  expect(button, label).toBeTruthy();
  await act(async () => { button!.click(); });
}
async function openOverview(width: number, extendedStates = false) {
  style.textContent = cssAtWidth(width);
  const fixture = missionFixture('WS:BETA', 'JOB-B');
  if (extendedStates) {
    fixture.mission.submission_availability = 'UNAVAILABLE_NEW_SUBMISSION';
    fixture.posture.value = 'RETURN_EXECUTION_MISMATCH';
  }
  expect(decodeMission(fixture, { workRef: 'WS:BETA', rootJobId: 'JOB-B' })).not.toBeNull();
  const readProgramsObservation = vi.fn(async () => qualifiedPrograms());
  const readMission = vi.fn(async () => fixture);
  window.MastermindMissionHost = { readProgramsObservation, readMission };
  root = createRoot(container);
  await act(async () => { root!.render(<App />); });
  await click('Projects'); await click('Open project Beta program');
  expect(container.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toBe('Overview');
  return { readProgramsObservation, readMission };
}
beforeEach(() => {
  history.replaceState(null, '', '/os/'); delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
  container = document.createElement('div'); document.body.append(container);
  style = document.createElement('style'); document.head.append(style);
});
afterEach(async () => {
  if (root) await act(async () => root!.unmount()); root = null;
  style.remove(); container.remove(); delete window.MastermindMissionHost; vi.restoreAllMocks();
});

it('actual exact-head Overview admits and preserves the longer canonical state labels', async () => {
  const readers = await openOverview(390, true);
  const states = [...container.querySelectorAll(selector)];
  expect(states.some(s => s.textContent === 'UNAVAILABLE NEW SUBMISSION')).toBe(true);
  expect(states.some(s => s.textContent === 'RETURN EXECUTION MISMATCH')).toBe(true);
  expect(location.search).toBe('?work_ref=WS%3ABETA&root_job_id=JOB-B');
  expect(readers.readProgramsObservation).toHaveBeenCalledTimes(2);
  expect(readers.readMission).toHaveBeenCalledTimes(1);
});

it('the default fixture preserves and permits wrapping of the Chrome-identified CONSUMPTION UNKNOWN posture', async () => {
  // The existing source fixture supplies this state without a test override.
  // Chrome identified it on ff6f707; this assertion does not measure its rect.
  expect(realMissionFixture().posture.value).toBe('CONSUMPTION_UNKNOWN');
  await openOverview(390);
  const badge = container.querySelector(`${selector}.state-consumption_unknown`);
  expect(badge).toBeTruthy();
  expect(badge!.textContent).toBe('CONSUMPTION UNKNOWN');
  expect(badge!.parentElement?.tagName).toBe('DD');
  expect(badge!.parentElement?.previousElementSibling?.textContent).toBe('Posture');
  expect(badge!.closest('section')?.querySelector('h2')?.textContent).toBe('Review and acceptance');
  const style = getComputedStyle(badge!);
  expect(style.whiteSpace).toBe('normal');
  expect(style.display).toBe('inline-block');
  expect(style.maxWidth).toBe('100%');
});

it('existing state formatting adds word boundaries and both containing rules allow arbitrary wrapping', async () => {
  await openOverview(390);
  for (const badge of container.querySelectorAll(selector)) expect(badge.textContent).not.toContain('_');
  const sheet = postcss.parse(css);
  for (const selector of ['main', '.card']) {
    let permitsAnywhere = false;
    sheet.walkRules(rule => {
      if (rule.selectors.includes(selector)) rule.walkDecls('overflow-wrap', declaration => {
        if (declaration.value === 'anywhere') permitsAnywhere = true;
      });
    });
    expect(permitsAnywhere, selector).toBe(true);
  }
});

it.each([320, 390, 420, 640, 800])('%ipx Overview definition-list badges permit wrapping and remain bounded to their value track', async (width) => {
  await openOverview(width);
  const badges = [...container.querySelectorAll(selector)];
  expect(badges.length).toBe(7);
  for (const badge of badges) {
    const s = getComputedStyle(badge);
    expect(s.whiteSpace).toBe('normal');
    expect(s.display).toBe('inline-block');
    expect(s.maxWidth).toBe('100%');
  }
});

it.each([801, 960, 1440])('%ipx desktop and out-of-scope mobile badges retain their original whitespace policy', async (width) => {
  await openOverview(width);
  for (const badge of container.querySelectorAll(selector)) expect(getComputedStyle(badge).whiteSpace).toBe('nowrap');
  style.textContent = cssAtWidth(390);
  const outside = [...container.querySelectorAll('.state')].filter(s => !s.matches(selector));
  expect(outside.length).toBeGreaterThan(0);
  for (const badge of outside) expect(getComputedStyle(badge).whiteSpace).toBe('nowrap');
});

it('the selector matches only the seven shared Mission badges across actual App routes', async () => {
  const readers = await openOverview(390);
  const count = () => container.querySelectorAll(selector).length;
  expect(count()).toBe(7);
  for (const tab of ['Plan', 'Work', 'Evidence', 'More']) {
    const control = [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(button => button.textContent === tab);
    expect(control, tab).toBeTruthy();
    await act(async () => { control!.click(); });
    expect(count(), `Project ${tab}`).toBe(0);
  }
  await click('Overview'); expect(count()).toBe(7);
  await click('Today'); expect(count()).toBe(0);
  await click('Mission Workspace'); expect(count()).toBe(7);
  for (const route of ['Activity', 'Connections', 'Evidence', 'Conversation', 'Projects', 'Inbox', 'Conversations', 'Knowledge']) {
    await click(route); expect(count(), route).toBe(0);
  }
  for (const route of ['Work', 'Open Programs', 'Fleet & Capacity']) {
    await click('Today'); await click(route); expect(count(), route).toBe(0);
  }
  expect(location.search).toBe('?work_ref=WS%3ABETA&root_job_id=JOB-B');
  expect(readers.readProgramsObservation).toHaveBeenCalledTimes(2);
  expect(readers.readMission).toHaveBeenCalledTimes(1);
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { jsx } from 'react/jsx-runtime'
import { atom, host } from './sdk-fixture.js'
import plugin, { botWorkspaceKey, cleanRoutes, createLauncher, expectsHistory, installMetadata, MastermindPage, routeKey } from '../desktop/plugin.js'

const route = (profile = 'secretary', connectionId = 'm2', targetProfile = profile) => ({ connectionId, profile, targetProfile, mode: 'local' })
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const epoch = () => 1
const apiFor = (routes = [route()]) => ({
  state: { gateway: atom('open'), profile: atom('default') },
  profileRoutes: vi.fn(async () => routes),
  listPersistedSessions: vi.fn(async () => ({ sessions: [{ id: 's1', title: 'Delivery briefing', message_count: 4 }] })),
  requestProfile: vi.fn(async () => ({ sessions: [{ id: 'bot-root', resolved_id: 'bot-tip', root_title: 'Bot Chat', message_count: 6 }] })),
  openSession: vi.fn(async () => {}), newChat: vi.fn(), navigate: vi.fn()
})
const prepared = async (api = apiFor()) => { const model = createLauncher(api, epoch); await model.refresh(); await model.select(routeKey(model.state.get().routes[0])); return { api, model } }
const metadata = base => ({ schema: 'mastermind.mobile-metadata.v1', manifest: `${base}/api/plugins/mastermind-mobile/manifest.webmanifest`, icon: `${base}/api/plugins/mastermind-mobile/icon-192.png` })

beforeEach(() => { window.history.replaceState(null, '', '/'); document.head.querySelectorAll('[data-mastermind-mobile],link[rel="manifest"],meta[name^="apple-mobile"]').forEach(node => node.remove()) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); document.documentElement.removeAttribute('data-hermes-desktop-host') })

describe('existing route ownership', () => {
  it('preserves equal profile names on different connections and strips raw connection data', () => {
    const rows = cleanRoutes([route(), { ...route(), token: 'private', url: 'https://private' }, route('secretary', 'ubuntu'), {}, null])
    expect(rows).toHaveLength(2)
    expect(rows[0]).not.toHaveProperty('token')
    expect(rows[0]).not.toHaveProperty('url')
    expect(new Set(rows.map(routeKey)).size).toBe(2)
  })
  it('ranks leadership without inventing missing profiles', () => {
    expect(cleanRoutes([route('engineering'), route('secretary')]).map(row => row.profile)).toEqual(['secretary', 'engineering'])
    expect(cleanRoutes([])).toEqual([])
    expect(() => cleanRoutes({})).toThrow()
  })
  it('never chooses an ambiguous shortcut by name alone', async () => {
    const api = apiFor([route(), route('secretary', 'ubuntu')]), model = createLauncher(api, epoch)
    await model.refresh('secretary')
    expect(model.state.get().selected).toBeNull()
    expect(api.listPersistedSessions).not.toHaveBeenCalled()
    expect(model.state.get().historyError).toContain('multiple connections')
  })
  it('does not fall back to default when a shortcut names a missing agent', async () => {
    const model = createLauncher(apiFor([route('default')]), epoch)
    await model.refresh('secretary')
    expect(model.state.get().selected).toBeNull()
    expect(model.state.get().historyError).toContain('not available')
  })
  it('reads the selected route using its backend profile and leaves the custom page on a normal open', async () => {
    const api = apiFor([route('office', 'm2', 'secretary')]), { model } = await prepared(api)
    expect(api.listPersistedSessions).toHaveBeenCalledWith(route('office', 'm2', 'secretary'), { profile: 'secretary', limit: 12 })
    await model.open('s1')
    expect(api.openSession).toHaveBeenCalledWith('s1', expect.objectContaining({ route: route('office', 'm2', 'secretary'), profile: 'secretary', intent: 'in-place' }))
  })
  it('does not open unknown session ids or auto-send on navigation', async () => {
    const { api, model } = await prepared()
    await model.open('guessed')
    expect(api.openSession).not.toHaveBeenCalled()
    expect(api.requestProfile).not.toHaveBeenCalled()
    expect(api.newChat).not.toHaveBeenCalled()
  })
  it('opens a new separate draft only on explicit action, on the exact route', async () => {
    const { api, model } = await prepared()
    model.newChat()
    expect(api.newChat).toHaveBeenCalledExactlyOnceWith(route())
    expect(api.requestProfile).not.toHaveBeenCalled()
  })
  it('keeps hidden, archived, internal and wrong-profile records out of ordinary history', async () => {
    const api = apiFor()
    api.listPersistedSessions.mockResolvedValue({ sessions: [{ id: 'ok', title: 'Visible' }, { id: 'hidden', hidden: true }, { id: 'archived', archived: true }, { id: 'child', is_internal_child: true }, { id: 'wrong', profile: 'engineering' }] })
    const { model } = await prepared(api)
    expect(model.state.get().sessions.map(row => row.id)).toEqual(['ok'])
  })
  it('surfaces a partial read error rather than claiming there is no history', async () => {
    const api = apiFor()
    api.listPersistedSessions.mockResolvedValue({ sessions: [], errors: [{ profile: 'secretary', error: 'locked' }] })
    const { model } = await prepared(api)
    expect(model.state.get().historyError).toContain('could not be read')
  })
  it('uses live row count so a truly empty conversation can open', () => {
    expect(expectsHistory({ live_message_count: 0, message_count: 80 })).toBe(false)
    expect(expectsHistory({ message_count: 0 })).toBe(false)
    expect(expectsHistory({})).toBe(true)
  })
})

describe('stale work and navigation', () => {
  it('discards a history reply after another agent was selected', async () => {
    const first = deferred(), api = apiFor([route(), route('engineering')]), model = createLauncher(api, epoch)
    api.listPersistedSessions.mockImplementation(row => row.profile === 'secretary' ? first.promise : Promise.resolve({ sessions: [{ id: 'eng', title: 'Architecture' }] }))
    await model.refresh()
    const pending = model.select(routeKey(route()))
    await model.select(routeKey(route('engineering')))
    first.resolve({ sessions: [{ id: 'wrong' }] }); await pending
    expect(model.state.get().sessions[0].id).toBe('eng')
  })
  it('refuses navigation after an active-source change', async () => {
    let value = 1
    const api = apiFor(), model = createLauncher(api, () => value)
    await model.refresh(); await model.select(routeKey(route()))
    value = 2
    await model.open('s1'); model.newChat(); await model.openBot()
    expect(api.openSession).not.toHaveBeenCalled()
    expect(api.newChat).not.toHaveBeenCalled()
    expect(api.requestProfile).not.toHaveBeenCalled()
    expect(model.state.get().error).toContain('Connection changed')
  })
  it('discards inventory from a previous activation even when a name is unchanged', async () => {
    let value = 1
    const response = deferred(), api = apiFor(), model = createLauncher(api, () => value)
    api.profileRoutes.mockReturnValue(response.promise)
    const pending = model.refresh(); value = 2; response.resolve([route()]); await pending
    expect(model.state.get().routes).toEqual([])
  })
  it('has no late publications after unmount and can remount under React StrictMode', async () => {
    const response = deferred(), api = apiFor(), model = createLauncher(api, epoch)
    api.profileRoutes.mockReturnValueOnce(response.promise)
    const pending = model.refresh(); model.dispose(); response.resolve([route('wrong')]); await pending
    expect(model.state.get().routes).toEqual([])
    model.activate(); await model.refresh()
    expect(model.state.get().routes[0].profile).toBe('secretary')
  })
  it('does not display untrusted backend errors or tokens', async () => {
    const api = apiFor(), model = createLauncher(api, epoch)
    api.profileRoutes.mockRejectedValue(new Error('private-token-secret'))
    await model.refresh()
    expect(JSON.stringify(model.state.get())).not.toContain('private-token-secret')
  })
})

describe('canonical persistent Bot Chat', () => {
  it('resolves the existing canonical registry and navigates in-place to its current lineage tip', async () => {
    const { api, model } = await prepared()
    await model.openBot()
    expect(api.requestProfile).toHaveBeenCalledExactlyOnceWith(route(), 'session.list', { profile: 'secretary', title: 'Bot Chat', limit: 200, include_hidden: true }, undefined, { spawnPriority: 'foreground' })
    expect(api.openSession).toHaveBeenCalledExactlyOnceWith('bot-tip', expect.objectContaining({ route: route(), intent: 'in-place', workspaceMode: 'bots', workspaceOwnerKey: 'bot:m2::secretary', forceResume: true }))
    expect(api.newChat).not.toHaveBeenCalled()
  })
  it.each([
    { label: 'missing', rows: [] },
    { label: 'wrong title', rows: [{ id: 'other', title: 'Notes' }] },
    { label: 'ambiguous', rows: [{ id: 'a', title: 'Bot Chat' }, { id: 'b', title: 'Bot Chat' }] }
  ])('never creates a replacement on $label canonical history', async ({ rows }) => {
    const { api, model } = await prepared()
    api.requestProfile.mockResolvedValue({ sessions: rows })
    await model.openBot()
    expect(api.openSession).not.toHaveBeenCalled()
    expect(api.newChat).not.toHaveBeenCalled()
    expect(model.state.get().historyError).toContain('no replacement')
  })
  it('does not retry or submit after a canonical read fails', async () => {
    const { api, model } = await prepared()
    api.requestProfile.mockRejectedValue(new Error('offline'))
    await model.openBot()
    expect(api.requestProfile).toHaveBeenCalledTimes(1)
    expect(api.openSession).not.toHaveBeenCalled()
    expect(api.newChat).not.toHaveBeenCalled()
  })
  it('coalesces a double click while opening', async () => {
    const response = deferred(), { api, model } = await prepared()
    api.requestProfile.mockReturnValue(response.promise)
    const first = model.openBot(); await model.openBot()
    response.resolve({ sessions: [{ id: 'bot', title: 'Bot Chat', message_count: 0 }] }); await first
    expect(api.requestProfile).toHaveBeenCalledTimes(1)
    expect(api.openSession).toHaveBeenCalledTimes(1)
  })
  it('uses the established native Bot Mode presentation key', () => {
    expect(botWorkspaceKey(route('alias', 'm2', 'secretary'))).toBe('bot:m2::alias')
  })
})

describe('native mobile page and install metadata', () => {
  it('renders through StrictMode, exposes persistent and separate chat actions, and preserves history', async () => {
    const api = apiFor()
    render(jsx(StrictMode, { children: jsx(MastermindPage, { api, epoch, installState: atom('ready') }) }))
    fireEvent.click(await screen.findByRole('button', { name: /Secretary/ }))
    await screen.findByRole('button', { name: 'Delivery briefing' })
    fireEvent.click(screen.getByRole('button', { name: 'Open Bot Chat' }))
    await waitFor(() => expect(api.openSession).toHaveBeenCalledTimes(1))
    expect(api.newChat).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'New separate chat' })).toBeTruthy()
  })
  it('disables agent actions when disconnected without labelling agents idle', async () => {
    const api = apiFor(); api.state.gateway.set('closed')
    render(jsx(MastermindPage, { api, epoch, installState: atom('unavailable') }))
    expect((await screen.findByRole('button', { name: /Secretary/ })).disabled).toBe(true)
    expect(screen.getByRole('status').textContent).toContain('disconnected')
    expect(screen.queryByText(/agent.*idle/i)).toBeNull()
  })
  it('treats hostile conversation titles as text', async () => {
    const api = apiFor()
    api.listPersistedSessions.mockResolvedValue({ sessions: [{ id: 's', title: '<img src=x onerror=alert(1)>' }] })
    render(jsx(MastermindPage, { api, epoch, installState: atom('unavailable') }))
    fireEvent.click(await screen.findByRole('button', { name: /Secretary/ }))
    await screen.findByRole('button', { name: '<img src=x onerror=alert(1)>' })
    expect(document.querySelector('.mm-mobile img')).toBeNull()
  })
  it.each(['', '/hermes'])('adds same-origin credentialed metadata and removes only its own nodes for %s', base => {
    const own = document.createElement('meta'); own.name = 'unrelated'; document.head.append(own)
    const dispose = installMetadata(document, base, metadata(base))
    const manifest = document.querySelector('link[rel="manifest"]')
    expect(manifest.getAttribute('href')).toBe(metadata(base).manifest)
    expect(manifest.getAttribute('crossorigin')).toBe('use-credentials')
    dispose(); expect(document.querySelector('link[rel="manifest"]')).toBeNull(); expect(own.isConnected).toBe(true); own.remove()
  })
  it('rejects external metadata and preserves another application manifest', () => {
    expect(() => installMetadata(document, '', { ...metadata(''), manifest: 'https://other.test/app.json' })).toThrow()
    const existing = document.createElement('link'); existing.rel = 'manifest'; existing.href = '/existing.json'; document.head.append(existing)
    expect(() => installMetadata(document, '', metadata(''))).toThrow()
    expect(existing.getAttribute('href')).toBe('/existing.json')
  })
  it('registers native contributions but never restarts, opens or sends at registration', async () => {
    Object.assign(host, apiFor())
    const ctx = { onDispose: vi.fn(), registerMany: vi.fn(), rest: vi.fn() }
    plugin.register(ctx)
    expect(plugin.defaultEnabled).toBe(false)
    expect(ctx.registerMany.mock.calls[0][0].map(row => row.id)).toEqual(['home', 'navigation', 'open'])
    expect(host.openSession).not.toHaveBeenCalled(); expect(host.newChat).not.toHaveBeenCalled(); expect(host.requestProfile).not.toHaveBeenCalled()
    expect(ctx.rest).not.toHaveBeenCalled()
  })
})

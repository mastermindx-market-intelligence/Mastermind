// Original Mastermind integration. Hermes owns chat, streaming, tools, identity and storage.
import { atom, gatewayActivationEpoch, host, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, useValue } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

export const ID = 'mastermind-mobile'
const STAFF = [
  ['meta-ceo-uncensored', 'Meta-CEO', 'Direction and priorities'],
  ['secretary', 'Secretary', 'Briefings and follow-through'],
  ['chief-of-staff', 'Chief of Staff', 'Coordination and delivery']
]
const LABELS = new Map(STAFF.map(([name, title]) => [name, title]))
const PURPOSES = new Map(STAFF.map(([name, , purpose]) => [name, purpose]))
const text = value => typeof value === 'string' && value.trim().length > 0
export const routeKey = route => JSON.stringify([route.connectionId, route.profile, route.targetProfile])
export const labelFor = route => LABELS.get(route.targetProfile) || route.profile.replace(/[-_]+/g, ' ')
// Presentation key from the pinned Hermes Bot Mode contract, not a new bot identity.
export const botWorkspaceKey = route => `bot:${route.connectionId}::${route.profile}`
export const expectsHistory = row => Number.isFinite(row.live_message_count) ? row.live_message_count > 0 : Number.isFinite(row.message_count) ? row.message_count > 0 : true

export function cleanRoutes(value) {
  if (!Array.isArray(value)) throw new Error('Invalid route inventory')
  const unique = new Map()
  for (const row of value) {
    if (!row || !text(row.connectionId) || !text(row.profile) || !text(row.targetProfile) || !['local', 'remote'].includes(row.mode)) continue
    const route = { connectionId: row.connectionId, profile: row.profile, targetProfile: row.targetProfile, mode: row.mode }
    if (row.primary === true) route.primary = true
    unique.set(routeKey(route), Object.freeze(route))
  }
  const rank = route => { const i = STAFF.findIndex(([name]) => name === route.targetProfile); return i < 0 ? 10 : i }
  return [...unique.values()].sort((a, b) => rank(a) - rank(b) || labelFor(a).localeCompare(labelFor(b)) || routeKey(a).localeCompare(routeKey(b)))
}

// No request submits a turn or creates a canonical chat. Native route descriptors cross every seam.
export function createLauncher(api = host, epoch = gatewayActivationEpoch) {
  const state = atom({ routes: [], selected: null, sessions: [], loading: false, loadingChats: false, opening: false, error: '', historyError: '' })
  let inventory = 0, history = 0, disposed = false, sourceEpoch = epoch()
  const put = patch => { if (!disposed) state.set({ ...state.get(), ...patch }) }
  const current = stamp => !disposed && sourceEpoch === stamp && epoch() === stamp
  const stale = () => put({ routes: [], selected: null, sessions: [], loading: false, loadingChats: false, opening: false, error: 'Connection changed. Refresh your team before opening a chat.' })
  const model = {
    state,
    activate() { disposed = false },
    async refresh(preferred = '') {
      if (disposed) return
      const request = ++inventory, stamp = epoch()
      ++history
      sourceEpoch = stamp
      put({ routes: [], selected: null, sessions: [], loading: true, loadingChats: false, opening: false, error: '', historyError: '' })
      try {
        const routes = cleanRoutes(await api.profileRoutes())
        if (request !== inventory || disposed) return
        if (!current(stamp)) return stale()
        put({ routes, loading: false })
        const matches = routes.filter(route => route.targetProfile === preferred)
        if (preferred && matches.length === 1) await model.select(routeKey(matches[0]))
        else if (preferred) put({ historyError: matches.length ? 'This agent exists on multiple connections. Choose the intended connection.' : 'That agent is not available on this connection. Choose another agent below.' })
      } catch {
        if (request === inventory && !disposed) put({ loading: false, error: 'Your team could not be loaded. Reconnect to Hermes, then refresh.' })
      }
    },
    async select(key) {
      if (!current(sourceEpoch)) return stale()
      const route = state.get().routes.find(row => routeKey(row) === key)
      if (!route || state.get().opening) return
      const request = ++history, stamp = sourceEpoch
      put({ selected: route, sessions: [], loadingChats: true, historyError: '' })
      try {
        const result = await api.listPersistedSessions(route, { profile: route.targetProfile, limit: 12 })
        if (request !== history || disposed) return
        if (!current(stamp)) return stale()
        if (!result || !Array.isArray(result.sessions) || (result.errors || []).length) throw new Error('History unavailable')
        const rows = result.sessions.filter(row => row && text(row.id) && !row.hidden && !row.archived && !row.is_internal_child && (!row.profile || row.profile === route.targetProfile))
        put({ sessions: [...new Map(rows.map(row => [row.id, { id: row.id, title: text(row.title) ? row.title : 'Untitled conversation', expectHistory: expectsHistory(row) }])).values()], loadingChats: false })
      } catch {
        if (request === history && !disposed) put({ loadingChats: false, historyError: 'Conversation history could not be read. Nothing has been sent or moved.' })
      }
    },
    async open(id) {
      if (!current(sourceEpoch)) return stale()
      const snapshot = state.get(), row = snapshot.sessions.find(item => item.id === id)
      if (!snapshot.selected || snapshot.loadingChats || snapshot.opening || !row) return
      put({ opening: true, historyError: '' })
      try {
        // A normal tap must leave this full-page route. Native 'tab' intentionally
        // preserves main and can leave /mastermind being interpreted as a session.
        await api.openSession(id, { route: snapshot.selected, profile: snapshot.selected.targetProfile, intent: 'in-place', expectHistory: row.expectHistory, awaitHydration: true, forceResume: true })
      } catch {
        put({ historyError: 'Hermes could not open that conversation. Return to the native history list; do not resend an uncertain message.' })
      } finally { put({ opening: false }) }
    },
    async openBot() {
      if (!current(sourceEpoch)) return stale()
      const snapshot = state.get(), route = snapshot.selected, stamp = sourceEpoch, request = history
      if (!route || snapshot.opening || snapshot.loadingChats) return
      put({ opening: true, historyError: '' })
      try {
        const result = await api.requestProfile(route, 'session.list', { profile: route.targetProfile, title: 'Bot Chat', limit: 200, include_hidden: true }, undefined, { spawnPriority: 'foreground' })
        if (disposed || request !== history) return
        if (!current(stamp)) return stale()
        if (!result || !Array.isArray(result.sessions)) throw new Error('Invalid canonical read')
        const matches = result.sessions.filter(row => row && text(row.id) && !row.archived && !row.is_internal_child &&
          (String(row.root_title || '').trim() === 'Bot Chat' || (!row.root_title && String(row.title || '').trim() === 'Bot Chat')))
        if (matches.length !== 1) {
          put({ historyError: 'The existing Bot Chat could not be uniquely confirmed. Open this agent in native Bot Mode; no replacement was created.' })
          return
        }
        const row = matches[0], id = text(row.resolved_id) ? row.resolved_id : row.id
        await api.openSession(id, { route, profile: route.targetProfile, intent: 'in-place', expectHistory: expectsHistory(row), awaitHydration: true, forceResume: true, keepAllProfilesScope: true, workspaceMode: 'bots', workspaceOwnerKey: botWorkspaceKey(route), tabTitle: 'Bot Chat' })
      } catch {
        put({ historyError: 'The existing Bot Chat could not be opened. No new chat or message was created.' })
      } finally { put({ opening: false }) }
    },
    newChat() {
      if (!current(sourceEpoch)) return stale()
      const snapshot = state.get()
      if (!snapshot.selected || snapshot.opening || snapshot.loadingChats) return
      try { api.newChat(snapshot.selected) } catch { put({ historyError: 'A new draft could not be opened. Nothing was sent.' }) }
    },
    dispose() { disposed = true; ++inventory; ++history }
  }
  return model
}

const CSS = `
.mm-mobile{box-sizing:border-box;max-width:960px;margin:0 auto;padding:24px 20px max(24px,env(safe-area-inset-bottom));color:var(--ui-text-primary);font:inherit;overflow-wrap:anywhere}
.mm-mobile *{box-sizing:border-box}.mm-mobile h1{font-size:24px;line-height:1.2;font-weight:700;margin:0 0 8px}.mm-mobile h2{font-size:17px;font-weight:650;margin:0 0 12px}
.mm-mobile p{margin:0 0 14px;line-height:1.5}.mm-mobile .mm-muted{color:var(--ui-text-secondary);font-size:13px}
.mm-mobile .mm-top{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;margin-bottom:24px}
.mm-mobile .mm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px;margin:12px 0 24px}
.mm-mobile button,.mm-mobile summary{min-height:44px;font:inherit;cursor:pointer}.mm-mobile button{border:1px solid var(--ui-stroke-secondary);border-radius:10px;background:var(--ui-bg-editor);color:var(--ui-text-primary);padding:10px 14px;text-align:left;white-space:normal}
.mm-mobile button:hover{background:var(--ui-bg-secondary)}.mm-mobile button[aria-pressed=true]{background:var(--ui-bg-secondary);font-weight:650}
.mm-mobile button:focus-visible,.mm-mobile summary:focus-visible{outline:2px solid var(--ui-accent);outline-offset:3px}.mm-mobile button:disabled{opacity:.55;cursor:default}
.mm-mobile .mm-card{display:flex;flex-direction:column;gap:7px;min-height:112px;width:100%}.mm-mobile .mm-card strong{font-size:16px}.mm-mobile .mm-card small{font-weight:400;color:var(--ui-text-secondary);font-size:12px}
.mm-mobile .mm-history{border:1px solid var(--ui-stroke-secondary);border-radius:12px;padding:16px;margin-bottom:24px}.mm-mobile .mm-row{display:flex;flex-wrap:wrap;gap:10px;justify-content:space-between;align-items:center}.mm-mobile .mm-list{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:8px}.mm-mobile .mm-list button{width:100%}
.mm-mobile details{margin-top:18px}.mm-mobile summary{display:flex;align-items:center;font-weight:600}.mm-mobile a{color:var(--ui-accent);text-underline-offset:3px}
@media(max-width:480px){.mm-mobile{padding:20px 14px max(20px,env(safe-area-inset-bottom))}.mm-mobile .mm-grid{grid-template-columns:1fr}.mm-mobile .mm-card{min-height:96px}.mm-mobile .mm-history{padding:12px}}
`

export function MastermindPage({ api = host, epoch = gatewayActivationEpoch, installState }) {
  const model = useMemo(() => createLauncher(api, epoch), [api, epoch])
  const view = useValue(model.state), gateway = useValue(api.state.gateway), profile = useValue(api.state.profile), install = useValue(installState)
  const [showAll, setShowAll] = useState(false)
  useEffect(() => {
    model.activate()
    void model.refresh(new URLSearchParams(window.location.search).get('mastermind-agent') || '')
    return () => model.dispose()
  }, [model, gateway, profile])
  const staff = view.routes.filter(route => LABELS.has(route.targetProfile)), others = view.routes.filter(route => !LABELS.has(route.targetProfile))
  const selected = view.selected, connected = gateway === 'open'
  const cards = routes => routes.map(route => jsx('button', {
    type: 'button', className: 'mm-card', disabled: !connected || view.opening,
    'aria-pressed': !!selected && routeKey(selected) === routeKey(route), onClick: () => void model.select(routeKey(route)),
    children: jsxs('span', { children: [jsx('strong', { children: labelFor(route) }), jsx('p', { className: 'mm-muted', children: PURPOSES.get(route.targetProfile) || 'Specialist conversations' }), jsx('small', { children: `Connection: ${route.connectionId}` })] })
  }, routeKey(route)))
  return jsxs('main', { className: 'mm-mobile', 'aria-label': 'Mastermind', children: [
    jsx('style', { children: CSS }),
    jsxs('header', { className: 'mm-top', children: [jsxs('div', { children: [jsx('h1', { children: 'Your team' }), jsx('p', { className: 'mm-muted', children: 'Pick an agent. Continue the conversation.' })] }), jsx('button', { type: 'button', disabled: view.loading || view.opening, onClick: () => void model.refresh(), children: view.loading ? 'Loading team...' : 'Refresh team' })] }),
    jsx('p', { className: 'mm-muted', role: 'status', 'aria-live': 'polite', children: connected ? 'Connected to Hermes. Agent activity appears in each conversation.' : 'Hermes is disconnected. Reconnect before opening a chat.' }),
    view.error ? jsx('p', { role: 'alert', children: view.error }) : null,
    jsx('section', { 'aria-label': 'Leadership', className: 'mm-grid', children: cards(staff) }),
    !view.loading && !staff.length && !view.error ? jsx('p', { children: 'No leadership profiles are available on this connection.' }) : null,
    selected ? jsxs('section', { className: 'mm-history', 'aria-label': 'Saved conversations', children: [
      jsx('h2', { children: labelFor(selected) }),
      jsxs('div', { className: 'mm-row', children: [jsx('button', { type: 'button', disabled: !connected || view.opening || view.loadingChats, onClick: () => void model.openBot(), children: 'Open Bot Chat' }), jsx('button', { type: 'button', disabled: !connected || view.opening || view.loadingChats, onClick: () => model.newChat(), children: 'New separate chat' })] }),
      jsx('p', { className: 'mm-muted', children: 'Bot Chat is your persistent conversation. Separate chats keep their own history.' }),
      view.loadingChats ? jsx('p', { role: 'status', children: 'Reading conversations...' }) : null,
      view.opening ? jsx('p', { role: 'status', children: 'Opening in Hermes...' }) : null,
      !view.loadingChats && !view.sessions.length && !view.historyError ? jsx('p', { children: 'No recent separate conversations.' }) : null,
      jsx('ul', { className: 'mm-list', children: view.sessions.map(row => jsx('li', { children: jsx('button', { type: 'button', disabled: !connected || view.opening, onClick: () => void model.open(row.id), children: row.title }) }, row.id)) })
    ] }) : null,
    view.historyError ? jsx('p', { role: 'alert', children: view.historyError }) : null,
    others.length ? jsxs('section', { children: [jsx('button', { type: 'button', 'aria-expanded': showAll, onClick: () => setShowAll(!showAll), children: showAll ? 'Hide specialists' : `Show specialists (${others.length})` }), showAll ? jsx('div', { className: 'mm-grid', children: cards(others) }) : null] }) : null,
    jsxs('details', { children: [jsx('summary', { children: 'Use on your phone' }), jsx('p', { children: 'Connect to the approved private network and sign in with Nous. Your agents continue running on the M2.' }), jsx('p', { children: 'On iPhone, use Safari: Share, then Add to Home Screen. On supported Android browsers, choose Install app or Add to Home screen.' }), jsx('p', { className: 'mm-muted', children: install === 'ready' ? 'Home-screen metadata is ready. Install availability depends on your browser. Chats still require a connection.' : 'Home-screen metadata is unavailable. Browser chat still uses the native Hermes interface.' })] }),
    jsxs('details', { children: [jsx('summary', { children: 'Conversations stay native' }), jsx('p', { className: 'mm-muted', children: 'Messages, Markdown, code blocks, tool activity, stop and reconnect are rendered by Hermes itself. This page does not submit messages, copy transcripts, store credentials or queue offline actions.' })] })
  ] })
}

export function installMetadata(document, basePath, metadata) {
  if (!metadata || metadata.schema !== 'mastermind.mobile-metadata.v1') throw new Error('Unsupported metadata')
  const base = typeof basePath === 'string' ? basePath.replace(/\/$/, '') : ''
  if (base && !/^(\/[A-Za-z0-9_-]+)+$/.test(base)) throw new Error('Unsupported base path')
  const path = `${base}/api/plugins/${ID}`
  if (metadata.manifest !== `${path}/manifest.webmanifest` || metadata.icon !== `${path}/icon-192.png`) throw new Error('Unexpected metadata origin')
  const existing = document.querySelector('link[rel="manifest"]')
  if (existing && existing.getAttribute('href') !== metadata.manifest) throw new Error('Another application owns install metadata')
  const owned = []
  const add = (tag, attrs) => { const node = document.createElement(tag); Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value)); node.dataset.mastermindMobile = 'true'; document.head.append(node); owned.push(node) }
  if (!existing) add('link', { rel: 'manifest', href: metadata.manifest, crossorigin: 'use-credentials' })
  if (!document.querySelector('meta[name="apple-mobile-web-app-capable"]')) add('meta', { name: 'apple-mobile-web-app-capable', content: 'yes' })
  if (!document.querySelector('meta[name="apple-mobile-web-app-title"]')) add('meta', { name: 'apple-mobile-web-app-title', content: 'Mastermind' })
  return () => owned.forEach(node => node.remove())
}

export default {
  id: ID, name: 'Mastermind Mobile', defaultEnabled: false,
  register(ctx) {
    const installState = atom('unavailable')
    let disposed = false, cleanup = () => {}
    ctx.onDispose(() => { disposed = true; cleanup() })
    if (document.documentElement.dataset.hermesDesktopHost === 'browser') {
      ctx.rest('/metadata').then(metadata => {
        if (disposed) return
        cleanup = installMetadata(document, window.__HERMES_BASE_PATH__ || '', metadata)
        installState.set('ready')
      }).catch(() => { if (!disposed) installState.set('unavailable') })
    }
    ctx.registerMany([
      { id: 'home', area: ROUTES_AREA, data: { path: '/mastermind' }, render: () => jsx(MastermindPage, { installState }) },
      { id: 'navigation', area: SIDEBAR_NAV_AREA, data: { path: '/mastermind', label: 'Mastermind', codicon: 'organization' } },
      { id: 'open', area: PALETTE_AREA, data: { id: 'mastermind-mobile.open', label: 'Open Mastermind team', keywords: ['agents', 'secretary', 'meta-ceo'], run: () => host.navigate('/mastermind') } }
    ])
  }
}

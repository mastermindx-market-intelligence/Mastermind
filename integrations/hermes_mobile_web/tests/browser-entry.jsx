// Browser fixture only; never install this file as a plugin or copy production state here.
import { createRoot } from 'react-dom/client'
import { host, setEpoch } from './sdk-fixture.js'
import plugin from '../desktop/plugin.js'

const routes = ['meta-ceo-uncensored', 'secretary', 'chief-of-staff', 'engineering'].map(profile => ({ connectionId: 'm2-fixture', profile, targetProfile: profile, mode: 'local' }))
window.__proofCalls = []
window.__proofDisconnect = () => host.state.gateway.set('closed')
window.__proofSwap = () => { setEpoch(2); host.state.profile.set('other-connection') }
host.profileRoutes = async () => routes
host.listPersistedSessions = async (route, options) => {
  window.__proofCalls.push({ kind: 'history', route, options })
  return { sessions: [{ id: `${route.targetProfile}-saved`, title: 'Continue the launch readiness discussion', message_count: 8 }] }
}
host.requestProfile = async (route, method, params) => {
  window.__proofCalls.push({ kind: 'read', route, method, params })
  return { sessions: [{ id: `${route.targetProfile}-root`, resolved_id: `${route.targetProfile}-current`, root_title: 'Bot Chat', message_count: 8 }] }
}
host.openSession = async (id, options) => { window.__proofCalls.push({ kind: 'open', id, options }) }
host.newChat = route => { window.__proofCalls.push({ kind: 'draft', route }) }
const disposers = []
const context = {
  onDispose(fn) { disposers.push(fn) },
  rest: async path => {
    if (path !== '/metadata') throw new Error('Unexpected fixture request')
    return { schema: 'mastermind.mobile-metadata.v1', manifest: '/api/plugins/mastermind-mobile/manifest.webmanifest', icon: '/api/plugins/mastermind-mobile/icon-192.png' }
  },
  registerMany(rows) {
    const page = rows.find(row => row.id === 'home')
    createRoot(document.getElementById('root')).render(page.render())
  }
}
document.documentElement.dataset.hermesDesktopHost = 'browser'
plugin.register(context)
window.addEventListener('pagehide', () => disposers.forEach(fn => fn()), { once: true })

// Test/browser-proof fixture only. The shipping plugin imports Hermes's real SDK.
import { atom } from 'nanostores'
import { useStore } from '@nanostores/react'
export { atom }
export const useValue = useStore
export const PALETTE_AREA = 'commandPalette'
export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
let epoch = 0
export const gatewayActivationEpoch = () => epoch
export const setEpoch = value => { epoch = value }
export const host = {
  state: { gateway: atom('open'), profile: atom('default') },
  profileRoutes: async () => [],
  listPersistedSessions: async () => ({ sessions: [] }),
  requestProfile: async () => ({ sessions: [] }),
  openSession: async () => {},
  newChat: () => {},
  navigate: () => {}
}

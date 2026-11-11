// Copy this test into the pinned donor's apps/desktop/src/contrib/ for qualification.
// MOBILE_PLUGIN_SOURCE is the exact published plugin.js staged outside production.
// The only browser adaptation is the donor test suite's own Blob -> data URL shim.
import { readFileSync } from 'node:fs'
import { afterEach, expect, it, vi } from 'vitest'
import { PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { registry } from '@/contrib/registry'
import { $pluginDecisions, $pluginRecords, setPluginEnabled } from '@/contrib/plugins-store'
import { loadRuntimePlugin, unloadRuntimePlugin } from '@/contrib/runtime-loader'

const ID = 'mastermind-mobile'
const sourcePath = process.env.MOBILE_PLUGIN_SOURCE
if (!sourcePath) throw new Error('MOBILE_PLUGIN_SOURCE must identify the qualified source artifact')
const source = readFileSync(sourcePath, 'utf8')

const owned = (area: string) => registry.getArea(area).filter(item => item.id.startsWith(ID + ':'))

afterEach(() => {
  unloadRuntimePlugin(ID)
  const decisions = { ...$pluginDecisions.get() }; delete decisions[ID]; $pluginDecisions.set(decisions)
  const records = { ...$pluginRecords.get() }; delete records[ID]; $pluginRecords.set(records)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('loads unmodified ESM against the actual SDK, remains opt-in, then registers and disposes native contributions', async () => {
  const RealBlob = globalThis.Blob
  vi.stubGlobal('Blob', class {
    parts: string[]
    constructor(parts: string[]) { this.parts = parts }
  })
  vi.spyOn(URL, 'createObjectURL').mockImplementation(blob =>
    `data:text/javascript;base64,${Buffer.from((blob as unknown as { parts: string[] }).parts.join('')).toString('base64')}`)
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
  try {
    const id = await loadRuntimePlugin(source, 'mastermind-mobile-qualified', { file: sourcePath })
    expect(id).toBe(ID)
    expect($pluginRecords.get()[ID].status).toBe('disabled')
    expect(owned(ROUTES_AREA)).toHaveLength(0)
    setPluginEnabled(ID, true)
    expect($pluginRecords.get()[ID]).toMatchObject({ status: 'loaded', file: sourcePath })
    expect(owned(ROUTES_AREA)).toHaveLength(1)
    expect(owned(SIDEBAR_NAV_AREA)).toHaveLength(1)
    expect(owned(PALETTE_AREA)).toHaveLength(1)
    setPluginEnabled(ID, false)
    expect(owned(ROUTES_AREA)).toHaveLength(0)
    expect(owned(SIDEBAR_NAV_AREA)).toHaveLength(0)
    expect(owned(PALETTE_AREA)).toHaveLength(0)
    expect($pluginRecords.get()[ID].status).toBe('disabled')
  } finally { vi.stubGlobal('Blob', RealBlob) }
})

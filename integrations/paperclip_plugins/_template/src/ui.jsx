// Paperclip module UI. The host serves dist/ui/index.js and mounts the
// exports named by the manifest slots. Keep '@paperclipai/plugin-sdk/ui' and
// react EXTERNAL (the shared build_module.mjs does): the host rewrites those
// bare specifiers through its import map at load time.
//
// Plain inline styles are fine — SDK components (MetricCard, DataTable, ...)
// are available from '@paperclipai/plugin-sdk/ui' if you want them.
import { usePluginData } from '@paperclipai/plugin-sdk/ui'

export function ModulePage({ context }) {
  const { data, loading, error } = usePluginData('REPLACE-ME', {
    companyId: context && context.companyId,
  })
  return (
    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 900 }}>
      <h2 style={{ margin: 0 }}>REPLACE ME</h2>
      {loading ? <span>reading…</span> : null}
      {error ? <span>could not read worker bridge: {String(error.message || error)}</span> : null}
      {data ? <pre style={{ margin: 0 }}>{JSON.stringify(data, null, 2)}</pre> : null}
    </div>
  )
}

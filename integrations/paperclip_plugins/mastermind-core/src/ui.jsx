// Mastermind Core — UI bundle. The host serves dist/ui/index.js and mounts
// the exports named by the manifest slots. `@paperclipai/plugin-sdk/ui` and
// react stay external: the host rewrites those specifiers through its import
// map when it loads this bundle.
import { usePluginData } from '@paperclipai/plugin-sdk/ui'

const cardStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
  padding: '12px 14px',
  border: '1px solid rgba(127,127,127,0.35)',
  borderRadius: 10,
  minWidth: 150,
}
const labelStyle = {
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  opacity: 0.7,
}
const valueStyle = { fontSize: 26, fontWeight: 600, lineHeight: 1.1 }
const sourceStyle = { fontSize: 11, opacity: 0.6 }
const unreadStyle = { fontSize: 13, color: '#b45309', fontWeight: 500 }

const COUNTS = [
  { key: 'configuredRoles', label: 'Configured roles', source: 'agents' },
  { key: 'enrolledAgents', label: 'Enrolled agents', source: 'agents' },
  { key: 'reachableAgents', label: 'Reachable agents', source: 'agents.lastHeartbeatAt' },
  { key: 'agentsWithActiveWork', label: 'Agents with active work', source: 'agents' },
]

function CountCard({ label, value, source }) {
  return (
    <div style={cardStyle}>
      <span style={labelStyle}>{label}</span>
      {value === null || value === undefined ? (
        <span style={unreadStyle}>could not read {source}</span>
      ) : (
        <span style={valueStyle}>{value}</span>
      )}
      <span style={sourceStyle}>source: {source}</span>
    </div>
  )
}

export function RosterTruthWidget({ context }) {
  const { data, loading, error } = usePluginData('roster-truth', {
    companyId: context && context.companyId,
  })
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <strong>Roster truth</strong>
      {loading ? <span>reading…</span> : null}
      {error ? <span style={unreadStyle}>could not read worker bridge: {String(error.message || error)}</span> : null}
      {data && data.sources && data.sources.agents && !data.sources.agents.ok ? (
        <span style={unreadStyle}>could not read agents: {String(data.sources.agents.error)}</span>
      ) : null}
      {data ? (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {COUNTS.map((c) => (
            <CountCard key={c.key} label={c.label} value={data.counts ? data.counts[c.key] : null} source={c.source} />
          ))}
        </div>
      ) : null}
      {data && data.generatedAt ? (
        <span style={sourceStyle}>observed {data.generatedAt} — company {data.companyId || '?'}</span>
      ) : null}
    </div>
  )
}

export function MastermindPage({ context }) {
  const { data, loading, error } = usePluginData('roster-truth', {
    companyId: context && context.companyId,
  })
  return (
    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 900 }}>
      <h2 style={{ margin: 0 }}>Mastermind</h2>
      <p style={{ margin: 0, opacity: 0.8 }}>
        mastermind-core — the first Mastermind OS module. It displays and joins; it never admits,
        schedules, retries or accepts work.
      </p>
      {loading ? <span>reading…</span> : null}
      {error ? <span style={unreadStyle}>could not read worker bridge: {String(error.message || error)}</span> : null}
      {data ? (
        <>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {COUNTS.map((c) => (
              <CountCard key={c.key} label={c.label} value={data.counts ? data.counts[c.key] : null} source={c.source} />
            ))}
          </div>
          {data.roles && data.roles.length ? (
            <div>
              <span style={labelStyle}>roles observed</span>
              <div>{data.roles.join(', ')}</div>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

export function MastermindSidebar({ context }) {
  const { data } = usePluginData('roster-truth', {
    companyId: context && context.companyId,
  })
  const enrolled = data && data.counts ? data.counts.enrolledAgents : null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
      <strong>Mastermind</strong>
      {enrolled === null || enrolled === undefined ? (
        <span style={unreadStyle}>could not read agents</span>
      ) : (
        <span style={sourceStyle}>{enrolled} enrolled agents</span>
      )}
    </div>
  )
}

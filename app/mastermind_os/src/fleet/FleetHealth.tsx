import { useEffect, useState } from "react";
import { decodeFleetHealth, HISTORY_METRICS, type FleetHealthDocument, type FleetHost,
  type FleetRead, type FleetWindow, type HistoryMetric } from "../fleet";
import "./fleet.css";

const WINDOWS: FleetWindow[] = ["1h", "24h", "7d", "30d"];
const PLOTS: Record<HistoryMetric, {label: string; unit: string}> = {
  cpu_temp_c: {label: "CPU temperature", unit: "°C"}, cpu_busy_pct: {label: "CPU busy", unit: "%"},
  load1: {label: "Load average", unit: ""}, memory_used_pct: {label: "RAM used", unit: "%"},
  fabric_active_lanes: {label: "Fabric active lanes", unit: ""},
};
const pretty = (value: number | null, unit = "", digits = 1) => value === null ? "Unavailable" :
  `${value.toLocaleString(undefined, {maximumFractionDigits: digits})}${unit}`;
const gib = (value: number | null) => pretty(value === null ? null : value / 1024 ** 3, " GiB");
function time(stamp: number | null): string {
  if (stamp === null) return "No observation";
  const date = new Date(stamp * 1000);
  return Number.isFinite(date.valueOf()) ? date.toLocaleString(undefined, {month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "short"}) : "Observation time unavailable";
}
const coverageCopy: Record<string, string> = {
  SUBAGENT_COVERAGE_PARTIAL: "Observed Fabric lanes; not a complete subagent count. Nested and unmanaged agents are not enumerated by this source.",
  MEMORY_HISTORY_INCOMPLETE: "RAM history is incomplete: the existing collector has not recorded every RAM measurement.",
  MEMORY_TOTAL_UNAVAILABLE: "Measured total RAM is unavailable. A usage percentage is not inferred from declared capacity.",
  MAC_MEMORY_FREE_INACTIVE_ESTIMATE: "Mac memory is a free + inactive RAM estimate, not memory pressure or a precise used-RAM measurement.",
  CPU_TEMPERATURE_UNAVAILABLE: "A CPU temperature sensor is not available in this observation.",
  CPU_UTILIZATION_UNAVAILABLE: "CPU busy percentage is unavailable. Load average is a different measurement.",
  THERMAL_ADVISORY_UNAVAILABLE: "No operator thermal advisory limit is supplied for this machine.",
  SNAPSHOT_NOT_CURRENT: "The last machine observation is stale; current health and agent activity are not established.",
  SNAPSHOT_UNAVAILABLE: "The existing observer did not supply a successful machine observation.",
  OBSERVATION_TIME_INVALID: "The observer timestamp could not be validated.",
  HISTORY_INSUFFICIENT: "There are not enough recorded observations to establish a trend.",
  HISTORY_ORDER_INVALID: "History ordering is inconsistent; it was withheld rather than repaired by guessing.",
  REGISTRY_ALIASES_GROUPED: "Explicit registry aliases were grouped with the primary host; their activity was not added twice.",
  OCCUPANCY_CONFLICT: "The source's lane observations disagree. Current lane count is unavailable.",
  MEMORY_SOURCE_INCONSISTENT: "Memory source values disagree; the usage percentage is unavailable.",
};

function HistoryChart({host, metric}: {host: FleetHost; metric: HistoryMetric}) {
  const {label, unit} = PLOTS[metric];
  const points = host.history;
  const values = points.flatMap(p => p[metric] === null ? [] : [p[metric]!]);
  if (!values.length) return <article className="fleet-chart"><h4>{label}</h4><p className="fleet-muted">No recorded history for this metric.</p></article>;
  const first = points[0].timestamp, last = points.at(-1)!.timestamp;
  const high = unit === "%" ? 100 : Math.max(1, Math.ceil(Math.max(...values) * 1.1));
  const x = (stamp: number) => 8 + (stamp - first) / Math.max(1, last - first) * 384;
  const y = (value: number) => 90 - value / high * 78;
  let path = "", connected = false;
  for (const point of points) {
    const value = point[metric];
    if (value === null) { connected = false; continue; }
    if (point.gaps.includes(metric)) connected = false;
    path += `${connected ? "L" : "M"}${x(point.timestamp).toFixed(2)},${y(value).toFixed(2)} `;
    connected = true;
  }
  return <article className="fleet-chart">
    <div className="fleet-row"><h4>{label}</h4><span className="fleet-muted">Peak {pretty(Math.max(...values), unit)}</span></div>
    <svg viewBox="0 0 400 104" role="img" aria-label={`${label} history for ${host.label}`}>
      <title>{label}: {pretty(Math.min(...values), unit)} to {pretty(Math.max(...values), unit)}. Gaps are not interpolated.</title>
      <line className="fleet-chart-grid" x1="8" y1="90" x2="392" y2="90" />
      <line className="fleet-chart-grid" x1="8" y1="51" x2="392" y2="51" />
      <path data-series="true" d={path.trim()} fill="none" stroke="currentColor" strokeWidth="1.5" />
      {points.filter(p => p[metric] !== null).map(p => <circle key={p.timestamp} cx={x(p.timestamp)} cy={y(p[metric]!)} r={points.length > 80 ? 1 : 2} fill="currentColor"><title>{time(p.timestamp)} · {pretty(p[metric], unit)}</title></circle>)}
    </svg>
    <div className="fleet-row fleet-muted"><span>{pretty(0, unit)} – {pretty(high, unit)}</span><span>{values.length} recorded values</span></div>
  </article>;
}

interface Snapshot { document: FleetHealthDocument; generation: number; reader: FleetRead; received: number }
export function FleetHealth({read, generation = 0}: {read?: FleetRead; generation?: number}) {
  const [window, setWindow] = useState<FleetWindow>("24h");
  const [revision, setRevision] = useState(0);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    let attached = true, sequence = 0;
    let controller: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setPending(false); setFailed(false);
    const visible = () => document.visibilityState !== "hidden";
    const refresh = async () => {
      if (!read || !attached || !visible()) return;
      clearTimeout(timer); controller?.abort();
      controller = new AbortController(); const current = controller, started = ++sequence;
      setPending(true);
      try {
        const raw = await read({window, signal: current.signal});
        if (!attached || current.signal.aborted || sequence !== started) return;
        const decoded = decodeFleetHealth(raw, window);
        if (!decoded) throw Error("invalid Fleet response");
        setSnapshot({document: decoded, generation, reader: read, received: performance.now()});
        setFailed(false);
      } catch {
        if (attached && !current.signal.aborted && sequence === started) setFailed(true);
      } finally {
        if (attached && !current.signal.aborted && sequence === started) {
          setPending(false);
          if (document.visibilityState !== "hidden") timer = setTimeout(() => void refresh(), 60_000);
        }
      }
    };
    const visibility = () => {
      if (document.visibilityState === "hidden") { clearTimeout(timer); controller?.abort(); sequence++; setPending(false); }
      else void refresh();
    };
    document.addEventListener("visibilitychange", visibility);
    void refresh();
    return () => { attached = false; sequence++; clearTimeout(timer); controller?.abort(); document.removeEventListener("visibilitychange", visibility); };
  }, [read, generation, window, revision]);
  // Discard the prior principal's display synchronously, before effects run.
  const current = snapshot?.generation === generation && snapshot.reader === read && snapshot.document.window === window ? snapshot : null;
  const data = current?.document;
  const elapsed = current ? Math.max(0, (performance.now() - current.received) / 1000) : 0;
  const stateOf = (host: FleetHost) => failed ? "Last known" : host.state === "CURRENT" && host.observed_at !== null &&
    data && data.generated_at - host.observed_at + elapsed > 180 ? "Stale" : host.state.toLowerCase();
  const host = data?.hosts.find(h => h.id === selected) ?? data?.hosts[0];
  const currentCount = data?.hosts.filter(h => stateOf(h) === "current").length ?? 0;
  const findingsCount = data?.hosts.reduce((sum, h) => sum + h.findings.filter(f => f.severity !== "info").length, 0) ?? 0;
  return <section className="fleet-health" aria-label="Fleet hardware health">
    <header className="fleet-heading">
      <div><p className="fleet-eyebrow">Infrastructure · Observations</p><h2>Your machines, in view.</h2><p className="fleet-muted">Hardware pressure, thermal headroom and observed agent activity. No scheduling or host settings are changed here.</p></div>
      <button type="button" className="fleet-refresh" disabled={!read || pending} onClick={() => setRevision(v => v + 1)} aria-label="Refresh fleet">{pending ? "Refreshing…" : "Refresh"}</button>
    </header>
    <div className="fleet-toolbar">
      <div className="fleet-windows" role="group" aria-label="History window">{WINDOWS.map(value => <button type="button" key={value} aria-pressed={window === value} onClick={() => setWindow(value)}>{value}</button>)}</div>
      <span className="fleet-muted" role="status">{!read ? "Source not connected" : failed ? "Refresh failed · showing last observation" : pending ? "Reading the existing observer…" : data ? `Source observed ${time(data.generated_at)}` : "No observation received"}</span>
    </div>
    {!read && <div className="fleet-empty"><h3>Connect the existing Fleet source.</h3><p>The trusted workspace service has not supplied a Fleet reader. No computers, agent counts or sensor values are invented.</p></div>}
    {data?.availability === "UNAVAILABLE" && <div className="fleet-empty"><h3>Fleet source unavailable</h3><p>The existing observer is not readable through this workspace connection. This is not an empty or healthy fleet.</p></div>}
    {data && data.hosts.length > 0 && <>
      <div className="fleet-summary" aria-label="Fleet observation summary"><span><strong>{data.hosts.length}</strong> registered host records</span><span><strong>{currentCount}</strong> current observations</span><span><strong>{findingsCount}</strong> observed warnings</span><span className="fleet-muted">Sensor coverage varies by machine</span></div>
      <div className="fleet-machines">{data.hosts.map(h => <button type="button" key={h.id} className={`fleet-machine${host?.id === h.id ? " is-selected" : ""}`} aria-label={`Inspect ${h.label}`} aria-pressed={host?.id === h.id} onClick={() => setSelected(h.id)}>
        <span className="fleet-row"><strong>{h.label}</strong><span className={`fleet-state fleet-state-${stateOf(h).replace(" ", "-")}`}>{stateOf(h)}</span></span>
        <span className="fleet-machine-platform">{h.platform === "macos" ? "Mac" : h.platform === "linux" ? "Linux / Ubuntu" : "Platform unknown"} · {pretty(h.metrics.logical_cpus)} logical CPUs</span>
        <span className="fleet-metric-grid"><span><small>CPU busy</small><b>{pretty(h.metrics.cpu_busy_pct, "%")}</b></span><span><small>CPU temperature</small><b>{pretty(h.metrics.cpu_temp_c, "°C")}</b></span><span><small>{h.metrics.memory_used_pct !== null ? "RAM used" : h.coverage.includes("MAC_MEMORY_FREE_INACTIVE_ESTIMATE") ? "Free + inactive RAM (estimate)" : "Available RAM"}</small><b>{h.metrics.memory_used_pct !== null ? pretty(h.metrics.memory_used_pct, "%") : gib(h.metrics.memory_available_bytes)}</b></span><span><small>Fabric active lanes</small><b>{pretty(h.metrics.fabric_active_lanes)}</b></span></span>
        <span className="fleet-machine-foot">Last machine observation · {time(h.observed_at)}</span>
      </button>)}</div>
      {host && <section className="fleet-detail" aria-label={`${host.label} details`}>
        <div className="fleet-row"><div><p className="fleet-eyebrow">Machine detail</p><h3>{host.label}</h3></div><span className="fleet-muted">{stateOf(host)} · {time(host.observed_at)}</span></div>
        <dl className="fleet-extra"><div><dt>Load average · 1 / 5 min</dt><dd>{pretty(host.metrics.load1)} / {pretty(host.metrics.load5)}</dd></div><div><dt>Measured total RAM</dt><dd>{gib(host.metrics.memory_total_bytes)}</dd></div><div><dt>Swap used</dt><dd>{gib(host.metrics.swap_used_bytes)}</dd></div><div><dt>Storage free</dt><dd>{gib(host.metrics.disk_free_bytes)}</dd></div><div><dt>Storage temperature</dt><dd>{pretty(host.metrics.nvme_temp_c, "°C")}</dd></div><div><dt>CPU fan</dt><dd>{pretty(host.metrics.fan_rpm, " RPM", 0)}</dd></div></dl>
        <div className="fleet-findings"><h4>Health & sustained-use guidance</h4><p className="fleet-muted">High utilization or long uptime alone does not prove hardware damage. Sensor warnings and performance pressure are assessed separately.</p>
          {host.findings.length ? host.findings.map(f => <article key={f.code} className={`fleet-finding fleet-finding-${f.severity}`}><div className="fleet-row"><strong>{f.summary}</strong><span>{f.category} · {f.severity}</span></div><p>{f.detail}</p>{f.duration_seconds !== null && <small>Continuous observed duration: {pretty(f.duration_seconds / 60, " min")}</small>}</article>) : <p className="fleet-muted">No configured warning was found in the available evidence. This does not certify hardware health.</p>}
        </div>
        <div className="fleet-history-heading"><h4>Recorded history</h4><p className="fleet-muted">Recorded coverage: {host.history.length ? `${time(host.history[0].timestamp)} — ${time(host.history.at(-1)!.timestamp)}` : "No retained observations"}. Selected window: {window}; this does not guarantee full retention.</p></div>
        {data.history_truncated && <p className="fleet-coverage-note">History is bounded; older readings or finer detail may be unavailable. Retained peaks and source gaps are preserved.</p>}
        <div className="fleet-charts">{HISTORY_METRICS.map(metric => <HistoryChart key={metric} host={host} metric={metric} />)}</div>
        <div className="fleet-coverage"><h4>What this source can establish</h4>{host.coverage.map(code => <p key={code}>{coverageCopy[code] ?? code.replaceAll("_", " ").toLowerCase()}</p>)}{host.metrics.process_lane_candidates !== null && <p>Separately observed process candidates: {pretty(host.metrics.process_lane_candidates)}. They are not added to Fabric occupancy.</p>}</div>
      </section>}
    </>}
  </section>;
}

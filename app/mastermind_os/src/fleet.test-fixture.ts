// Deliberately synthetic test data. Never imported by a production consumer.
export const fleetFixture = () => ({
  schema: "mastermind.fleet_health.v1", availability: "AVAILABLE", generated_at: 1_791_890_400,
  window: "24h", history_truncated: false, admission_authoritative: false,
  source: "fabric_host_observer", reason_codes: [],
  hosts: [{
    id: "ubuntu2", label: "Ubuntu 2", platform: "linux", state: "CURRENT", observed_at: 1_791_890_400,
    metrics: { cpu_busy_pct: 0, load1: 2, load5: 3, logical_cpus: 32,
      memory_available_bytes: 16 * 1024 ** 3, memory_total_bytes: 32 * 1024 ** 3,
      memory_used_pct: 50, swap_used_bytes: 0, cpu_temp_c: 60, nvme_temp_c: 35,
      fan_rpm: null, disk_free_bytes: 100 * 1024 ** 3, fabric_active_lanes: 0,
      process_lane_candidates: 4, thermal_advisory_c: 85 },
    history: [{timestamp: 1_791_890_340, cpu_temp_c: 59, cpu_busy_pct: 0, load1: 1,
      memory_used_pct: null, fabric_active_lanes: 0, gaps: []},
      {timestamp: 1_791_890_400, cpu_temp_c: 60, cpu_busy_pct: 0, load1: 2,
      memory_used_pct: 50, fabric_active_lanes: 0, gaps: ["memory_used_pct"]}],
    findings: [], coverage: ["SUBAGENT_COVERAGE_PARTIAL", "MEMORY_HISTORY_INCOMPLETE"],
  }],
});

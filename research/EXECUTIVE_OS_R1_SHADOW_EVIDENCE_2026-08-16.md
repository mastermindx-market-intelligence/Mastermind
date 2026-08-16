# Executive OS R1 shadow evidence — 2026-08-16

Status: **accepted for Phase 1F-B entry**.

This evidence was produced by `scripts/executive_os_r1_shadow.py` against an
isolated Executive SQLite runtime. It is a deterministic fixture rollout: no
provider adapter, MCP server, live worker slot, launchd job, or write-capable
external integration was invoked.

## Scope and placement

| Case | Expected logical alias | Assigned fixture | Durable status |
|---|---|---|---|
| routine implementation | `fast.engineering` | `fixture-luna-r1` / `r1-fast-engineering` | `COMPLETED` |
| routine research | `fast.research` | `fixture-luna-r1` / `r1-fast-research` | `COMPLETED` |
| routine tests | `fast.engineering` | `fixture-luna-r1` / `r1-fast-engineering` | `COMPLETED` |
| routine review | `standard.review` | `fixture-terra-r1` / `r1-standard-review` | `COMPLETED` |

The registered fixture capacity is policy-derived from routing policy
`2026-08-16.stage1` and uses the logical model aliases `fast.engineering`,
`fast.research`, `standard.engineering`, `standard.research`, and
`standard.review`. The capacity metadata carries `fixture_only=true` and
`stage1_production_armed=false`.

## Metrics

The all-Sol values below are the previous reviewed reference fixture envelope.
They are not a provider billing or production token ledger; the evidence calls
that limitation out in the machine-readable result.

| Metric | Previous all-Sol reference | R1 shadow fixture | Delta (shadow − baseline) |
|---|---:|---:|---:|
| mean completion quality | 0.965 | 0.935 | -0.030 |
| validation pass rate | 100% | 100% | 0 pp |
| repair rate | 25% | 50% | +25 pp |
| repair rounds | 1 | 2 | +1 |
| mean latency | 1,250 ms | 1,600 ms | +350 ms |
| p95 fixture latency | 1,500 ms | 2,300 ms | +800 ms |
| frontier tokens | 5,100 | 1,770 | — |
| frontier-token savings | — | **3,330 / 65.294%** | — |

Latency is the reviewed deterministic fixture duration, not wall-clock model
latency. Quality, validation, repairs, and token values are likewise bounded
case inputs used to test the measurement and reporting path.

## Guard evidence

- Executive OS remains the lifecycle authority.
- Routing policy and fixture capacity remain `production_armed=false`.
- MCP write authority is false.
- Live worker-slot activation is false.
- Phase 1C-A hold/diagnostic state is preserved; no supervisor, canary, broker,
  or launchd artifact was modified by R1.
- Phase 1F-C was not started.
- No second control plane was introduced.

## Acceptance decision

R1 is accepted as a shadow-routing and measurement seam. It is sufficient to
begin Phase 1F-B durable parent/child runtime work, but it is not evidence to
activate live worker slots, grant MCP write authority, or claim production
provider quality/latency/token telemetry.

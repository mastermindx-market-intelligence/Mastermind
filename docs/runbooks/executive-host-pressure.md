# Executive host-pressure snapshot

## Status and boundary

`mastermind.host_pressure_snapshot/v1` is a read-only source capability. It
captures one bounded Darwin observation for an already-established opaque host
and boot/generation reference. It does not own host identity, process identity,
thresholds, admission, placement, lifecycle, persistence, retries, cleanup, or
service supervision.

The existing owners remain authoritative:

- Executive OS owns Job, Attempt, Worker, Event, process generation, cleanup,
  and absence proof.
- Capacity and `control_plane/executive_physical_resources.py` own physical
  reservation and begin admission.
- The existing SCF operations surface owns `host_fleet_health` and
  `disk_pressure` presentation.
- The worker broker owns dedicated-worker-UID containment.

HP0 neither edits nor arms `config/executive_physical_resources.json`. A source
snapshot is evidence, not a resource grant.

## Command

Run from an exact reviewed source checkout on Darwin:

```bash
python3 ops/executive_os/host_pressure_probe.py \
  --host-ref 'host-<64 lowercase hexadecimal characters>' \
  --boot-ref 'boot-<64 lowercase hexadecimal characters>'
```

The references must come from the existing authorized host/Runtime binding
owner. The probe never derives organizational identity from a hostname, serial,
process title, network address, or caller guess.

Success writes exactly one compact, sorted-key UTF-8 JSON document plus one
newline to standard output and exits 0. A refusal before output emission begins
writes one closed line to standard error, writes no snapshot to standard output,
and exits 65. Once the first output write is attempted, a write sequence that
cannot complete because a later write fails, returns an invalid/zero count, or
raises—or because flush fails—exits 74 with exactly `OUTPUT_EFFECT_UNKNOWN`;
every stdout byte from that invocation is then untrusted and must be discarded
even when it looks like complete canonical JSON. Recoverable short writes are
completed before flush and remain a normal exit-0 success.
Output uncertainty never authorizes a retry. The command performs no shell
invocation, network call, file write, retry, observed-process signal, browser or
provider action. On a timeout or output-cap violation it may terminate and reap
only the fixed `/bin/ps` child it created; it never signals a process reported by
that census.

## Snapshot contract

The exact keys are:

| Field | Type and unit | Meaning |
|---|---|---|
| `schema` | string | `mastermind.host_pressure_snapshot/v1` |
| `host_ref` | opaque string | Existing host-owner reference |
| `boot_ref` | opaque string | Existing boot/generation reference |
| `observed_at_ms` | integer, Unix ms | Observation wall time |
| `sample_window_ms` | integer ms | Bounded elapsed probe window |
| `logical_cpu_count` | integer count | Current logical CPU count |
| `load1_milli` | integer, load × 1,000 | One-minute load average |
| `load_ratio_milli` | integer, ratio × 1,000 | `load1_milli // logical_cpu_count` |
| `fseventsd_process_count` | integer count | Exact-basename rows observed |
| `fseventsd_cpu_milli_pct` | integer, percent × 1,000 or null | Aggregated `%CPU` |
| `fseventsd_rss_bytes` | integer bytes or null | Aggregated RSS converted from KiB |
| `telemetry_status` | enum | `COMPLETE` or `PARTIAL` |
| `unknown_fields` | sorted string list | Exact null optional fields |

All public numeric values are integers. Booleans do not satisfy integer fields.
Unknown, missing, duplicate, oversized, negative, nonfinite, overflowed, or
noncanonical values refuse. A successful complete process census that finds no
`fseventsd` row reports an observed zero. A failed or malformed census never
becomes zero.

HP0 currently emits `COMPLETE` only. The validator reserves `PARTIAL` for a
future accepted producer that explicitly pairs each optional null with the same
field in `unknown_fields`.

## Probe method

The production path is Darwin-only. It reads:

1. wall and monotonic clocks;
2. the logical CPU count;
3. the one-minute load average;
4. one bounded, headerless `/bin/ps -axo pid=,ppid=,%cpu=,rss=,comm=`
   projection.

The process table is capped before full capture: stdout is read incrementally
through a nonblocking pipe up to 4 MiB plus one discriminator byte, while stderr
is discarded rather than buffered. A three-second observation deadline starts
before launch and spans stdout read plus normal child exit; timeout or overflow
then receives at most one additional second of bounded TERM/KILL reaping. The
whole public sample remains capped at five seconds. The parser validates every
row, not only matching rows. PID, PPID, RSS,
and CPU tokens use one canonical unsigned decimal grammar before conversion. It
aggregates only rows whose executable basename is exactly `fseventsd`; similar
names are excluded.
Raw process rows, executable paths, PIDs, parent PIDs, arguments, environment,
stderr, account information, provider/session data, credentials, prompts, and
transcripts never enter the public snapshot or refusal.

The entire sample window must not exceed five seconds. Timeout, process launch
failure, non-zero status, empty output, malformed required fields, arithmetic
overflow, clock reversal, unsupported platform, or invalid core telemetry
refuses without retry.

## Closed refusal families

Output delivery uncertainty is separate from probe refusal. It emits exactly:

```text
host pressure probe output uncertain: OUTPUT_EFFECT_UNKNOWN
```

and exits 74. A caller accepts a snapshot only after exit 0 plus complete
canonical validation; every non-zero exit discards all stdout.

The emitted refusal is one of these closed codes:

- `ARGUMENTS_INVALID`
- `REFERENCE_INVALID`
- `PLATFORM_UNAVAILABLE`
- `UNSUPPORTED_PLATFORM`
- `WALL_CLOCK_INVALID`
- `MONOTONIC_CLOCK_INVALID`
- `CPU_COUNT_UNAVAILABLE`
- `LOAD_AVERAGE_INVALID`
- `PROCESS_CENSUS_TIMEOUT`
- `PROCESS_CENSUS_UNAVAILABLE`
- `PROCESS_CENSUS_NONZERO`
- `PROCESS_CENSUS_EMPTY`
- `PROCESS_CENSUS_TOO_LARGE`
- `PROCESS_CENSUS_MALFORMED`
- `PROCESS_CENSUS_OVERFLOW`
- `SAMPLE_WINDOW_EXCEEDED`
- `PROBE_INTERNAL_ERROR`
- `SNAPSHOT_CONTRACT_INVALID` at the CLI projection boundary

Unexpected exception text is collapsed to a closed code. Do not use a refusal
as proof that the host is idle or healthy.

## Test and real-canary procedure

Source proof:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -W error -m pytest -q -p no:cacheprovider \
  tests/test_executive_host_pressure.py \
  tests/test_executive_physical_resources.py \
  tests/test_executive_worker_broker.py
python3 -W error -m py_compile \
  control_plane/executive_host_pressure.py \
  ops/executive_os/host_pressure_probe.py \
  tests/test_executive_host_pressure.py
```

A real canary must use the currently authorized host and boot references, write
the snapshot to a separately owned evidence location, validate it again through
`validate_host_pressure_snapshot`, record exact source/head/tree identity, and
scan the artifact for prohibited raw fields. It must not install a daemon,
modify policy, kill a process, create a reservation, or claim an idle baseline.

## Continuation

HP0 stops at a reviewed Draft/Hold source and one read-only Mac canary. A later,
separately admitted HP1 may map accepted snapshot evidence into the existing
physical-resource observation and Capacity reservation owner, calibrate policy
from sustained measurements, and prove reserve/recheck behavior. HP0 itself
cannot authorize HP1 or production arming.

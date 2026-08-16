# Executive OS OHF-P0 — harness capability and recovery probe

**Status:** laboratory specification and first implementation (Codex App Server only)
**Date:** 2026-08-16
**Branch:** `codex/ohf-p0-harness-probes-20260816` off current `origin/master`
**Does not depend on:** Phase 1F-B, PR #74, or any change to `WorkerExecutionAdapter`

## 0. What P0 is

OHF-P0 is a production-inert laboratory that empirically measures what a native
harness can do **before** freezing `OperatorHarnessAdapter`.

It answers:

- what the harness can actually do
- what identity persists across restart
- what state can be recovered
- what tools/configuration were really loaded
- what Executive OS can reliably observe

It is not the Operator Fabric. It does not complete product work. It does not
extend Executive Jobs, Attempts, workers, capacity tables, or resource leases.

## 1. Architectural constraint

`control_plane.worker_adapter.WorkerExecutionAdapter` stays the sealed-worker
floor:

```text
start
collect_result
cancel
run_validation_argv
```

OHF-P0 must not modify that protocol. A richer future interface is allowed to
exist only after this probe has evidence for what the native harness actually
exposes.

## 2. Runtime migration prohibition

OHF-P0 evidence is ordinary files. The probe must not add:

- `harness_sessions` table
- capacity tables
- resource leases
- worker slots
- new Job state
- new Attempt state

CI pins this with `tests/test_ohf_probe_inertness.py`.

## 3. Schema

Canonical machine-readable evidence:

`mastermind.ohf_harness_probe/v1`

Written as `probe.json` plus a human `probe.md`. Markdown statuses are only:

- **VERIFIED**
- **NOT SUPPORTED**
- **NOT TESTED**
- **DEGRADED**
- **UNKNOWN**

No guessing. Usage/quota classification is `exact | provider_reported |
estimated | unknown`. A percentage is recorded only when the harness reported
it. The probe never infers one.

Untrusted streams reuse ``common.redaction.sanitize_external_text`` (the
sanitizer pinned by ``tests/test_secret_redaction.py``) plus
``control_plane.flags._SECRET_MARKERS`` for secret-named keys.  The finished
document uses a tighter credential-prefix scan so SHA-256 attestation digests
are not mistaken for API keys.  ``bridge.nw_feedback._redact_secrets`` is not
called: it publishes a governance event and would violate inertness.

## 4. Codex App Server commission

The first implementation talks JSON-RPC stdio to either:

- `--backend fake` — in-repo double (`scripts.ohf.fake_app_server`), default, CI
- `--backend live` / `--live` — real `codex app-server`

The commission, in order:

1. start App Server, `initialize`, `initialized`
2. create thread, bounded turn, record native thread identity
3. stop App Server, restart, resume same thread, bounded turn
4. fork; two divergent bounded continuations; parent ≠ fork
5. discover and invoke the inert `ohf-probe` skill
6. discover and invoke inert MCP `ohf_probe` / `ohf_probe_echo`
7. capture effective configuration digest vs expected bundle
8. capture provider-reported usage/quota when present
9. recovery battery:
   - kill App Server, resume (process died ≠ native session died)
   - SIGTERM, resume
   - malformed request, recover
   - missing native session reference, fail closed
   - workspace disappears, fail closed
   - effective configuration changes, detect drift
   - MCP disappears, report degraded capability
10. cleanup

The inert skill and MCP fixture are laboratory-owned. They are not operational
Mastermind skills or production MCP servers.

## 5. How to run

```bash
python -m scripts.ohf.run_probe --backend fake --out-dir /tmp/ohf-p0
python -m scripts.ohf.run_probe --live --out-dir research/evidence/ohf_p0/live
```

Live mode copies `auth.json` into an isolated `CODEX_HOME` without loading it
into evidence. It still must not write Executive SQLite, claim workers, change
routing config, register provider capacity, or arm live execution.

## 6. P0 acceptance

P0 passes when the laboratory can answer, with evidence:

| Question | Observation id |
|---|---|
| Can we launch the native harness? | `launch` |
| Can we create a durable session? | `durable_session` |
| Can we identify it? | `identify` |
| Can we restart the local process? | `process_restart` |
| Can we resume the session? | `resume` |
| Can we fork it? | `fork` |
| Can we attest skills? | `attest_skills` |
| Can we attest MCP? | `attest_mcp` |
| Can we observe usage/quota? | `usage_quota` |
| Can we detect configuration drift? | `config_drift` |
| Can we clean up? | `cleanup` |
| Can we do all that without touching Executive lifecycle state? | `inert` |

CI proves the fake commission. A live Codex run is an operator command, not a
merge gate, because it requires local auth and may spend quota.

Claude, Grok, Qwen, and Cursor are out of scope for this PR.

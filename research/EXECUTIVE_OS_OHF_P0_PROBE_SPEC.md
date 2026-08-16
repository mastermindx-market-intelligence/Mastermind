# Executive OS OHF-P0 — harness capability and recovery probe

**Status:** P0B protocol-fidelity laboratory (Codex App Server only)
**Date:** 2026-08-16
**Does not depend on changing Phase 1F-B semantics.**  Evidence remains ordinary
files.  This is still not the Operator Fabric.

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
floor. OHF-P0 must not modify that protocol.

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

`mastermind.ohf_harness_probe/v1.1`

Written as `probe.json` plus a human `probe.md`. Markdown statuses are only
derived from JSON. Essential acceptance evidence must not live only in notes.

Capability verdicts remain `pass | fail | unknown` and are an **initial**
snapshot. Recovery uses `VERIFIED | NOT_SUPPORTED | NOT_TESTED | DEGRADED |
UNKNOWN` and is a separate matrix. Losing MCP later must not rewrite the
initial `capabilities.mcp` snapshot.

Attestation is two manifests, not one mixed digest:

- `RequestedCapabilityManifest` → `requested_manifest_digest`
- `ObservedCapabilityManifest` → `observed_manifest_digest`

`config_attested=true` only when every load-bearing requirement matches.
Unobservable dimensions are `UNKNOWN`, never implicitly accepted.

Usage/quota classification is `exact | provider_reported | estimated |
unknown`. Provider windows are stored as reported (`used_percent`,
`window_duration_minutes`, `resets_at`, `rate_limit_reached_type`). The probe
never estimates remaining capacity.

## 4. Auth isolation

Live mode must not copy, symlink, or read `auth.json` bytes, and must not fall
back to `~/.codex`.

Prepare a dedicated home:

```bash
CODEX_HOME=/path/to/dedicated/home codex login
python -m scripts.ohf.run_probe \
  --live \
  --codex-home /path/to/dedicated/home \
  --out-dir /tmp/ohf-p0-live
```

`--live` without `--codex-home` is refused.

## 5. Codex App Server commission

The implementation talks JSON-RPC stdio to either:

- `--backend fake` — in-repo double (`scripts.ohf.fake_app_server`), default, CI
- `--backend live` / `--live --codex-home PATH` — real `codex app-server`

The fake must reproduce current App Server shapes, including grouped
`skills/list` and `skills/extraRoots/set` with `{extraRoots:[...]}`.  The client
parses `account/read` as `{account, requiresOpenaiAuth}` and records only
`auth_type`, `plan_type`, and `requires_openai_auth`.

The commission, in order:

1. start App Server, `initialize`, `initialized`
2. create thread, bounded turn, record native thread identity and PID
3. stop App Server, restart, resume same thread, bounded turn
4. fork; two divergent bounded continuations; prove isolation from `thread/read`
5. discover and invoke the inert `ohf-probe` skill; then a removal/drift case
6. discover and invoke inert MCP `ohf_probe` / `ohf_probe_echo`
7. compare requested vs observed capability manifests
8. capture provider-reported usage/quota windows when present
9. recovery battery with canonical fields:
   - `process_sigkill_resume`
   - `process_sigterm_resume`
   - `malformed_rpc_recovery`
   - `missing_session_fail_closed`
   - `config_drift_detected`
   - `mcp_disappearance_detected`
   - `workspace_missing_fail_closed`
   - `main_process_cleanup`
   - `transitive_orphan_cleanup`
10. cleanup: main-process exit is not proof that every descendant exited

## 6. How to run

```bash
python -m scripts.ohf.run_probe --backend fake --out-dir /tmp/ohf-p0
python -m scripts.ohf.run_probe \
  --live \
  --codex-home /path/to/dedicated/home \
  --out-dir /tmp/ohf-p0-live
```

## 7. P0B acceptance

CI proves the fake commission, protocol fidelity, auth isolation, and
attestation mutations. A live Codex canary is required before
`PASS_FOR_OPERATOR_ADAPTER_DESIGN`, but the laboratory remains
production-inert.

Claude, Grok, Qwen, and Cursor are out of scope.

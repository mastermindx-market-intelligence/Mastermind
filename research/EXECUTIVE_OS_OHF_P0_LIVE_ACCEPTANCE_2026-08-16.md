# OHF-P0 live Codex App Server acceptance

**Status:** sanitized durable memorandum of a production-inert live canary.
**Date:** 2026-08-16
**Verdict:** `PASS_FOR_OPERATOR_ADAPTER_DESIGN`
**Does not arm Operator Fabric, Phase 1F-C, or a production Codex adapter.**

This memo is derived from the raw live artifact. The raw JSON was not rewritten
to look prettier. Credentials are not reproduced here.

## Artifact identity

| Field | Value |
|---|---|
| Probe id | `ohf-p0-5cbe5e32673d` |
| Probe schema | `mastermind.ohf_harness_probe/v1.1` |
| Observed at | `2026-08-16T17:30:49Z` |
| Raw probe path (ephemeral) | `/tmp/ohf-p0-live/probe.json` |
| Derived markdown path (ephemeral) | `/tmp/ohf-p0-live/probe.md` |
| Raw probe SHA-256 | `aebc40b5bee6fab005439096a337e99d08b2c77d25b0fbe3289be29f7a30756e` |
| Derived markdown SHA-256 | `5e2da51d4c6ff552a1a86f52d12e306ff30af0ba5b2ba38e700c6f598974259c` |

The raw artifact is outside Git on purpose. Do not commit it.

## Source lineage at canary time

| Field | Value |
|---|---|
| Live-tested PR head | `5e3d14213ce86e063f9e30b0cce8af2d2c4c0595` |
| Master at canary time | `0ac57b2ad60f2a63369567084ca6481d050948b0` |
| PR | [#81](https://github.com/mastermindx-market-intelligence/Mastermind/pull/81) |
| Branch | `codex/ohf-p0b-protocol-fidelity-20260816` |
| Codex version | `codex-cli 0.147.0` |
| Harness kind | `codex-app-server` |
| Binary digest | `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477` |
| OS / architecture | macOS 26.5 (Darwin 25.5.0), arm64 |
| Host principal | `uid-501` |

After this memo, PR #81 was reconciled onto current master. The live-relevant
`scripts/ohf/**` and `tests/test_ohf_*.py` blobs remained byte-identical to
`5e3d142…`. That comparison is the reason this canary was not rerun.

## Auth isolation

Dedicated home: `/Users/chriswong/.codex-ohf-p0` (mode `0700`).

| Check | Result |
|---|---|
| Independently authenticated | YES (`chatgpt` / `pro`; `requires_openai_auth=true`) |
| `auth.json` copied | NO |
| `auth.json` symlinked | NO |
| Implicit `~/.codex` fallback | NO |
| Dedicated `auth.json` | present, not a symlink, mode `0600`, inode `1146460587` |
| Default `~/.codex/auth.json` | unchanged across login and probes (inode `909483118`, mtime `1786886116`, size 3864) |

Binding lesson: a production Codex slot must have an independent auth domain.
Do not design account pooling around copying `auth.json`.

## Thread / process continuity

| Generation | PID | Native thread |
|---|---|---|
| launch | `30646` | `01a00ba0-4f1f-7033-be8e-ef9796953d73` |
| graceful restart | `30816` | same thread resumed |
| SIGKILL replacement | `31381` | resume empty; active writer |
| SIGTERM replacement | `31389` | resume empty; writer still held |

Native thread survived graceful process replacement: **YES**.
Native thread survived immediate SIGKILL resume: **NO**.

Provider error (redacted thread id in the raw artifact):
`thread/resume -> thread <redacted> already has an active writer`.

## Fork

| Field | Value |
|---|---|
| Parent | `01a00ba0-4f1f-7033-be8e-ef9796953d73` |
| Fork | `01a00ba0-737b-7492-853b-e8c15c92655d` |
| Inherited earlier state | VERIFIED |
| Parent continuation isolated | VERIFIED |
| Fork continuation isolated | VERIFIED |
| Independent continuation proven | true |

A native fork is conversational state, not an Executive child Job.

## Capability observations

Requested digest:
`3bc674f57e95a38bf6d57bc32ddf20a2c465234bd99955afee46f498fc5355ec`

Observed digest:
`8e63688ec5b33ff7a54f983235668b226737e389046de2ce13e3d2e98764de94`

| Dimension | Observation |
|---|---|
| Model | requested and served `gpt-5.6-sol`; match true |
| Skill `ohf-probe` | discovered, invokable, invoked successfully; reloadable without restart VERIFIED |
| MCP `ohf_probe` / `ohf_probe_echo` | configured, visible, tool visible, callable |
| Structured MCP item events | not observed (`structured_event_visible=false`) |
| Approvals | `never` |
| Sandbox | `read-only` |
| Plugins | none unexpected |
| Structured turn events | pass |
| `config_attested` | **false** (honest). Required subset matched; 31 unexpected builtin skills and MCP `codex_apps` (134 unexpected tools) were present. |

Do not weaken `config_attested` to ignore ambient builtins. Requested-set equals
observed-set is not a viable production-only rule.

Initial capability snapshot: approvals/fork/mcp/persistent_session/quota_telemetry/resume/skills/structured_events/usage_telemetry = `pass`. checkpoint, human_attach, native_subagents = `unknown`.

## Rate-limit observation

Classification: `provider_reported` from `account/rateLimits/read`.
No remaining quota was derived.

| Window | Value |
|---|---|
| primary.used_percent | 57 |
| primary.window_duration_minutes | 10080 |
| primary.resets_at | 1787345508 |
| secondary | none observed |
| rate_limit_reached_type | none |
| token counts | redacted in the artifact as `<redacted>` |

## Recovery matrix

| Row | Status |
|---|---|
| process_sigkill_resume | NOT_SUPPORTED |
| process_sigterm_resume | VERIFIED |
| malformed_rpc_recovery | VERIFIED |
| missing_session_fail_closed | VERIFIED |
| workspace_missing_fail_closed | VERIFIED |
| config_drift_detected | VERIFIED |
| mcp_disappearance_detected | VERIFIED |
| main_process_cleanup | VERIFIED (`main_pid_exited=true`) |
| transitive_orphan_cleanup | UNKNOWN (`descendant_census=false`) |

## Security

| Check | Result |
|---|---|
| Credential exposure | false |
| Redaction failures | none |
| Unexpected skills | 31 builtins (`github:*`, `openai-templates:*`, `skill-creator`, `plugin-creator`, …) |
| Unexpected MCP | `codex_apps` |
| Unexpected plugins | none |
| Unexpected config | `manifest_mismatch` |

Raw probe.json was scanned for `access_token`, `refresh_token`, `id_token`, JWT, `sk-`, and email patterns: none present.

## Remaining UNKNOWNs

- Transitive orphan / descendant process cleanup (no census).
- Structured MCP item events as an adapter-required capability (not observed).
- Immediate SIGKILL resume (provider active-writer refusal; V1 must not invent writer-steal).
- Host reboot, controller restart, and App Server still-alive-while-controller-restarts (not in this canary).
- Checkpoint, human attach, and native subagent capabilities.

## Architectural implications (not production schema)

- OS process identity is not native harness session identity.
- ProcessGeneration is justified beneath a durable native session.
- V1 recovery must not blindly resume after unexpected process death.
- ExecutionProfile cannot be an exclusive exact skill/MCP set; it needs REQUIRED / ALLOWED_AMBIENT / FORBIDDEN, with unclassified fail-closed on write-capable profiles.
- App Server is a viable rich-operator substrate if graceful stop is used and builtins are attested honestly.

## Verdict

`PASS_FOR_OPERATOR_ADAPTER_DESIGN`

This memorandum does not self-accept Operator Fabric architecture. It closes
the P0 live-evidence gap so a later P1A constitution can be designed against
observed Codex App Server semantics rather than guesses.

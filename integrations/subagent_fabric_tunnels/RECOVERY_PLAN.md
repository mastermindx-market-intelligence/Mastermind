# Fabric tunnel recovery — 2026-10-30 implementation and proof plan

Status: **IN PROGRESS / NOT PRODUCTION-PROVEN**. Owner: current Chairman-assigned Fabric recovery lead, not an abandoned PR author. Repository: `mastermindx-market-intelligence/Mastermind`; source-law pin `bb85b429f2ffffd38408080ce4df7d6378c34100` (Skillpack 1.0.1). This plan is an implementation task tree, **not** a production selector or additional lifecycle authority.

## Outcome / DONE_WHEN

On m2studio, five existing Subagent Fabric tunnel-client user LaunchAgents (`c1`, `c2-business`, `c2-personal`, `c3`, `c4`) are managed by a repository-owned, reversible, secret-safe install; `RunAtLoad=true`, **unconditional** `KeepAlive=true` (tunnel-client may clean-exit on SIGTERM), and `ThrottleInterval>=10`. A bounded installed health loop detects absence of PID, >300-s stale first-party tunnel-client heartbeat, stale host-pull telemetry and an installed host-pull generation missing the approved stdin/ARG_MAX repair. Recovery uses only the incumbent owner/action and refuses unsafe repin; explicit alerts are required when repair cannot be safely qualified. The separate `com.mastermind.desktop-commander.remote` carrier must never be observed as a restart target or modified.

Proof requires source tests and independent non-authoring Fabric review against an immutable Draft PR head, then **after separate authorized source/host gates** M2 install/readback, all six job PIDs (five clients plus host-pull), one killed tunnel automatically recovered with changed PID and working heartbeat, fresh host telemetry and a native Fabric preview placing work. The upstream #1827 stdin fix is merged; a published generation is not automatically selected. Never merge or approve in this mission.

## Task tree

| ID | State | Dependency | Discriminating evidence |
| --- | --- | --- | --- |
| FTR-1 | DONE | Protected current source | Same-commit Skillpack verification, bounded collision census; `#708` is Executive-tunnel scope, `#1836`/`#1879` own evolving host-pull code, not our five Fabric tunnel labels |
| FTR-2 | IN PROGRESS | FTR-1 | New repo-owned source for precisely five existing user LaunchAgents; plist identity/argv validation, strict per-label allowlist, secure preimage backups and atomic CAS, no invented tokens/tunnel identities |
| FTR-3 | PENDING | FTR-2 | Read-only health classification and owner-preserving kickstart only for qualified jobs, rate limit, alert on unsafe/unknown heartbeat or stale telemetry/host-pull generation |
| FTR-4 | PENDING | FTR-2/3 | Hermetic tests: crash/exit0 restart policy, absent/stale heartbeat, missing/stale host telemetry, old selected versus pinned host-pull generation, symlink/ownership/manifest/argv rejects, idempotence/backup/failure rollback; existing launcher unchanged |
| FTR-5 | PENDING | FTR-4 | Draft PR; green relevant CI, fresh independent non-authoring paid-Fabric review with exact result. No self-approval/merge |
| FTR-6 | BLOCKED (host binding) | FTR-5; host route | Source/installed gen compare on m2: `CURRENT.json`, `com.mastermind.host-pull` pinned gen, `pick.py`, `fabric_task.py`, pool semantic diff. Only choose a fixed full generation through existing atomic publisher selection + expected-current CAS after proving compatibility; otherwise record HOLD |
| FTR-7 | BLOCKED (host binding) | FTR-5/6 | On m2, exact backups, installed jobs/PIDs, killed-client self recovery, heartbeat+telemetry+preview from real path; alert and preserve rollback if unqualified |

## Collision and safety fences

- Source writes limited to a *new, separate* `integrations/subagent_fabric_tunnels/` owner + corresponding narrow tests/runbook; **do not edit** any existing #1836/#1879 host-pull/candidate/publisher/native-generation paths or `integrations/studio_direct_mcp/`. The first implementation wave is source-only.
- GitHub protected source remains release authority; PR #1836 and stacked #1879 are still Draft and touch host-pull publisher. Do **not** override their writers, reuse their branch, repoint host-pull or select a generation just because #1827 merged.
- User-provided 2026-10-30 snapshot: host-pull was repointed to published `a08c824650f4200ab07b48b7842d7cad67bcc2d176b61bce63cafce460ba519e`; `CURRENT.json` reportedly still selects `854dd545…`. Exact current host facts require first-party readback; static snapshots are not authority for a new selector effect.
- This session's Studio Direct m2studio binding returned `FLEET_ROUTE_PREFLIGHT_REFUSED / NOT_APPLIED`. **Do not retry that action or use a second carrier to bypass the refusal.** Independently permitted source build/review can proceed. The separate Studio Direct fleet-status observation is not a health signal for the five Subagent Fabric tunnel clients.
- No sudo, reboot, security/SIP modification, Desktop Commander carrier touch, key/credential print, blind retries, worker duplicate, PR merge/approval, or active-launchd mutation before source/host qualification. Back up installed files before edit; preserve exact user/owner data in private backups, never GitHub or logs.

## Exact recovery frontier

Follow FTR-2 through FTR-5 on this branch, preserving sole source writer. Deployment lane remains separately blocked by the observed m2 host-binding preflight until an authorized host owner restores the **same** route; source/testing/review continues. Record progress and final state in #dotsandgroksecretary, with source links rather than implying this plan is live.

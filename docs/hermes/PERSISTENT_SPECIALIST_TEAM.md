# Hermes Persistent Specialist Team — local enrollment record

Status: **live and verified 2026-11-07** (commission: issue #2198). This document is the
durable repo-side record of the enrollment pattern and its verification evidence. The
enrollment itself lives on the operator workstation (`~/.hermes/profiles/`), not in this
repo; `integrations/hermes_leadership/charters.py` remains the charter canon.

## Pattern

Each specialist is a native Hermes **profile** (`hermes profile create --clone-from`)
with three durable components:

| Component | Location | Purpose |
|---|---|---|
| `SOUL.md` | `~/.hermes/profiles/<name>/SOUL.md` | System prompt: identity + mirror of the charter key |
| `memories/MEMORY.md` | `~/.hermes/profiles/<name>/memories/` | Persistent role memory (org, repos, intake, routing) |
| `config.yaml` | `~/.hermes/profiles/<name>/` | Model routing (glm-5.3 via provider `zai`) |

Work assignment and result return use the **shared kanban board** (durable SQLite,
cross-profile): any staff profile (Meta-CEO, Chief of Staff) runs
`hermes kanban create --body-file <f> --assignee <specialist> --created-by <staff>`,
then `hermes kanban dispatch --max 1`. The dispatched worker runs in an isolated
per-task workspace (`~/.hermes/kanban/workspaces/<task_id>/`), returns results as an
attributed task comment with exact revisions and evidence paths, and attaches artifacts.

Specialists are **idle by construction**: no resident process per profile — they consume
inference only when directly chatted (`HERMES_HOME=<profile> hermes chat -q …`) or when a
kanban dispatch spawns a bounded worker. Availability across restarts follows from
stateless profile directories plus the durable board.

## Installed identities (2026-11-07)

| Profile | Charter key (`charters.py`) | Title |
|---|---|---|
| `engineering` | `engineering` | Engineering and Architecture Lead |
| `delivery` | `delivery` | Delivery and Continuity Lead |
| `reliability` | `reliability` | Reliability, Capacity and FinOps Lead |
| `product` | `product` | Product and Workflow Lead |
| `intelligence` | `intelligence` | Intelligence and Data-Quality Lead |
| `assurance` | `assurance` | Assurance and Security Challenger |

Preserved staff profiles (untouched): `chief-of-staff`, `secretary`, `meta-ceo-uncensored`.

## Verification evidence (all disk-verified, not self-reported)

- **Engineering canary (p1)**: direct chat produced `~/hermes-specialists/engineering/PROBE.md`
  with exact marker `ENGINEERING-ALIVE-2026-11-07`; specialist-quoted sha256 matched an
  independent `shasum -a 256`. Kanban task `t_d12e11ef` (assign→dispatch→isolated
  workspace→completion comment + artifact) reported branch `hermes/mmrelay-roster-bridge`
  @ `508b4f2597ea3a7c5394f60f294da9cea818db6e` — byte-exact against independent
  `git rev-parse` in `~/Mastermind`.
- **Five remaining specialists (p2)**: parallel direct-chat probes each produced
  `~/hermes-specialists/<name>/ALIVE.md` with exact single-line markers
  (`DELIVERY-…`, `RELIABILITY-…`, `PRODUCT-…`, `INTELLIGENCE-…`, `ASSURANCE-ALIVE-2026-11-07`);
  byte counts verified (25/28/24/29/26 — exact, no trailing newline).
- **Meta-CEO wiring (p3)**: task `t_f4f1c79d` created **by** `meta-ceo-uncensored`,
  completed by `intelligence` in ~2 min; `~/hermes-specialists/intelligence/META_DISPATCH.md`
  byte-exact with a real UTC timestamp (`2026-11-07T07:48:54Z` = 00:48 MST, matching the
  run window); completion comment attributed, evidence path + as-of time per charter.
- **Restart recovery**: kanban run #7 crashed mid-dispatch during a gateway self-update
  (`update_paused` drain); the task auto-returned to `ready` and a redispatch completed
  cleanly (run #8) with byte-exact results. Attributed honestly by the worker.
- **Idle spend**: `ps` shows zero per-specialist resident processes; only the shared
  gateway, desktop app, and helper daemons.

## Operating protocol for staff (Meta-CEO / Chief of Staff)

1. `HERMES_HOME=~/.hermes/profiles/meta-ceo-uncensored hermes kanban create "<title>" --body-file <f> --assignee <specialist> --created-by meta-ceo-uncensored`
2. `hermes kanban dispatch --max 1` (any profile; board is shared)
3. Consume the completion comment; verify claimed revisions/artifacts independently
   (`git rev-parse`, `shasum`) before treating work as done.
4. Direct conversation: `HERMES_HOME=~/.hermes/profiles/<name> hermes chat -q "<msg>"`.

Constraints unchanged: paper-only; no live Slack sends (Chairman-gated); no push to
`master`; secrets never in transcripts or memory.

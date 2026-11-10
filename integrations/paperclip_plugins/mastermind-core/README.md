# mastermind-core

The first Mastermind OS module (lane L9). One page, one sidebar entry, one
dashboard widget, one agent tool, one health check.

- **Page** `/:companyPrefix/mastermind` — roster truth with observed roles.
- **Sidebar entry** — enrolled-agent count, or `could not read agents`.
- **Dashboard widget "Roster truth"** — four separate live counts:
  configured roles, enrolled agents, reachable agents, agents with active
  work. None are hard-coded. A count whose source could not be read shows
  `could not read <source>`, never 0.
- **Agent tool `roster-report`** — the same four counts in string form, with
  the source each came from.
- **Health check** — reports the last roster read's source status; before any
  read has completed it reports degraded, not ok.

## Module rules (binding, verbatim from the lane L9 ledger amendment)

1. A module displays and joins; it never admits, schedules, retries or
   accepts work.
2. Ids of work item, coding job/attempt, native run, conversation and output
   stay separate fields, joined explicitly.
3. A widget never says "nothing needs you" unless it observed every source it
   covers; otherwise it names the source it could not read.
4. Produced / delivered / reviewed / accepted are four states, never one
   "done".
5. No module registers a scheduled job that duplicates a routine defined
   elsewhere.

## Count sources

| Count | Source | Read |
| --- | --- | --- |
| configured roles | `agents` | distinct `role` values across the company's agents |
| enrolled agents | `agents` | `ctx.agents.list({companyId})` length |
| reachable agents | `agents.lastHeartbeatAt` | heartbeat within 2 minutes (server beats every 30s) |
| agents with active work | `agents` | agent `status` is `running` or `active` |

## Build

```
node ../build_module.mjs          # from this directory
```

esbuild and the plugin SDK come from the installed Paperclip CLI tree
(`PAPERCLIP_CLI_ROOT`, default `~/.paperclip/cli/current`). `dist/` is
committed so a local-path install works from a fresh checkout.

## Install into the isolated dev instance

```
tools/mmos_dev/paperclip_dev.sh install-module "$(pwd)"
tools/mmos_dev/paperclip_dev.sh reload-module "$(pwd)"   # after a source edit
tools/mmos_dev/paperclip_dev.sh logs plugin mastermind.core
```

Never install into the default instance (`127.0.0.1:3100`) except through the
runbook `integrations/mmos/L9_DEFAULT_INSTALL_RUNBOOK.md`.

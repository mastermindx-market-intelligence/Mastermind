# Paperclip module template

Copy this directory to `integrations/paperclip_plugins/<name>/`, replace
`REPLACE-ME` (plugin id in `src/manifest.js`, data key, tool name) and
`REPLACE ME` (display names), then edit `src/worker.js` and `src/ui.jsx`.
See `../mastermind-core/` for a complete worked example.

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

Honest data follows from rule 3: a count whose source could not be read is
`null` plus a named error, never a guessed value — and never a silent zero.

## Build

```
node ../build_module.mjs          # from this directory
```

esbuild and the plugin SDK come from the installed Paperclip CLI tree
(`PAPERCLIP_CLI_ROOT`, default `~/.paperclip/cli/current`) — no npm install
inside the module. Commit `dist/` so local-path installs work from a fresh
checkout.

## Hard-won contract facts (build 2026.1106.0)

- `src/manifest.js` is PURE DATA — no imports; the host loads it with a plain
  dynamic import.
- The worker MUST end with `runWorker(plugin, import.meta.url)`, else the
  process exits code 0 at load and activation fails.
- UI externals (`@paperclipai/plugin-sdk/ui`, `react`, `react-dom`,
  `react/jsx-runtime`) must stay BARE in `dist/ui/index.js` — the host
  rewrites them through its import map. Do not alias the SDK for the UI build
  (esbuild alias matches by path prefix and would remap the UI subpath too).
- `onHealth()` receives no arguments — capture `ctx` from `setup()` in a
  closure.
- Company-scoped reads need a company context: UI bridge calls get it from
  the host context automatically; bare HTTP calls must put `companyId` at the
  request top level.
- The host dev watcher attaches only to plugins that loaded successfully; an
  errored plugin recovers via DELETE + install (see install-module below),
  not by touching files.

## Install into the isolated dev instance

```
tools/mmos_dev/paperclip_dev.sh install-module "$(pwd)"
tools/mmos_dev/paperclip_dev.sh reload-module "$(pwd)"   # after a source edit
tools/mmos_dev/paperclip_dev.sh logs plugin <plugin-id>
```

Never install into the default instance (`127.0.0.1:3100`) except through
`integrations/mmos/L9_DEFAULT_INSTALL_RUNBOOK.md`.

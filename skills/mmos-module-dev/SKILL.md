---
name: mmos-module-dev
description: Build and run a Mastermind OS Paperclip module in the isolated dev instance (lane L9 test bed).
---

# MMOS module development

A Mastermind OS feature ships as a Paperclip plugin ("module") under
`integrations/paperclip_plugins/`. This skill builds, installs and proves one
against the isolated dev instance only — never the Chairman's default
instance at `127.0.0.1:3100`.

## What exists

- `integrations/paperclip_plugins/_template/` — copyable skeleton; its README
  carries the five module rules verbatim and the contract facts of build
  2026.1106.0 (manifest is pure data; `runWorker` is mandatory at the worker
  tail; UI externals stay bare; `onHealth()` gets no ctx; company-scoped
  reads need a company context; the dev watcher only watches plugins that
  were ready at server boot).
- `integrations/paperclip_plugins/mastermind-core/` — worked example: page,
  sidebar entry, roster-truth dashboard widget (four live counts with named
  sources), `roster-report` agent tool, health check.
- `integrations/paperclip_plugins/build_module.mjs` — one builder; esbuild
  and the SDK come from the installed CLI tree, no npm install.
- `tools/mmos_dev/paperclip_dev.sh` — isolated dev instance controller.

## Exact commands

```
cd integrations/paperclip_plugins/my-module
node ../build_module.mjs                                   # build (commit dist/)
tools/mmos_dev/paperclip_dev.sh up                         # dev instance on 127.0.0.1:3190
tools/mmos_dev/paperclip_dev.sh install-module "$(pwd)"    # install, waits for ready
# edit src, rebuild, then:
tools/mmos_dev/paperclip_dev.sh reload-module "$(pwd)"     # touch; falls back to reinstall
tools/mmos_dev/paperclip_dev.sh logs plugin mastermind.core
tools/mmos_dev/paperclip_dev.sh down
```

Rules and boundaries: `_template/README.md` and
`tools/mmos_dev/README.md` (next-lane test company/agent).

# Item 8 — exempt jobs that declare no repository (staged)

## Measured cost (lane HX, 2026-11-11)

- Mechanism (T3-launched threads, incl. delegated children):
  `~/.t3/userdata/settings.json` `defaultThreadEnvMode: "worktree"` — every
  new thread gets `git worktree add` under `~/.t3/worktrees/<project>/<id>`
  before its provider session starts (local git op, no network). On resume
  the checkout is reused; it is recreated only if missing
  (`ProviderTurnStartService.ts:636-676`, see item-10 evidence).
- Mechanism (CLI `--worktree` / fabric-side creations): user-level
  WorktreeCreate hook (`~/.claude/settings.json` →
  `~/.local/lib/mastermind/worktree-storage/worktree_create_hook.py` →
  `worktree_storage.py create`): `git fetch origin` + `git worktree add`
  into the SSD pools (`~/.config/mastermind/worktree-storage.json`), 600 s
  timeout, **no internal-disk fallback**; a failed fetch REFUSES the whole
  creation (hook log 2026-11-02T20:17:53Z and 20:18:12Z).
- Cost at Mastermind repo scale (424 MB .git, 223 MB checkout, local
  `--shared` clone, no network): `git worktree add` = **3.84 s / 4.42 s**
  (two runs). The T3 path adds nothing else; the hook path adds a full
  network `git fetch origin` on every creation (the dominant, failure-prone
  part).

## Smallest change (existing feature, no code)

T3 already has a **per-project** thread environment mode
(`default_thread_env_mode`, values `local` | `worktree`;
`apps/server/src/orchestration-v2/ProjectStore.ts:37`,
`serverSettings.ts:650-651,863`, settable in project settings
`ProjectCommands.ts:35,206-208`). Jobs that declare no repository should run
in a project whose mode is `local` — zero worktree cost, zero guard.

## Install (one-time, by principal)

1. Create a scratch project with no repository:
       t3 project add ~/scratch-no-repo
2. In the T3 app: Settings → that project → thread environment → **local**
   (writes the project's `default_thread_env_mode` row).
3. Delegate no-repo jobs into that project (delegated children inherit the
   project's env mode).

## Rollback

Set the project's thread environment back to **worktree** (or remove the
project: `t3 project remove ~/scratch-no-repo`). No files are replaced; the
change is one settings row per project.

## For the fabric CLI path (recommendation, not staged)

Creation cost and availability are dominated by `git fetch origin` per
creation. If worker-start latency there matters, have the parent (router)
warm the fetch immediately before start, or add a fetch-freshness window to
`worktree_storage.py create` — a code change to principal-owned
infrastructure, staged only as this recommendation.

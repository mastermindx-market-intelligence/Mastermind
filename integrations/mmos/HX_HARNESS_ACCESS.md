# Lane HX — harness access staged changes (2026-11-11)

Branch `t3/mmos-v4-hx`. Evidence: `~/.mastermind/mmos_evidence/hx-20261111/`.
Nothing here is installed; every item below is staged with install command,
target-file sha256, rollback, and tests. Full details per item in the
evidence files; summary:

## Item 9 — read-only Bash allow fragment (STAGED)

- Files: `harness/i9-readonly-allow-settings.json`,
  `harness/i9-test-readonly-allow.sh`.
- Install (merge into the provider home used by T3-launched sessions):

      F=~/.t3/providers/fabric-unified-router/settings.json
      cp "$F" "$F.bak-hx9"   # rollback: mv "$F.bak-hx9" "$F"
      jq -s '.[0] * {"permissions":{"allow":(.[0].permissions.allow // []) + .[1].permissions.allow}}' \
        "$F" harness/i9-readonly-allow-settings.json > "$F.new" && mv "$F.new" "$F"

- Replaced file (pre-install): `~/.t3/providers/fabric-unified-router/settings.json`,
  sha256 `0587c73761c8fcd7f1e07019ceadf77c060a2e8d08c69f390d6997d1a186a9ea`
  (has no `permissions` key today; the merge only adds one).
- Rollback: `mv "$F.bak-hx9" "$F"` (or delete the added `permissions.allow`
  entries).
- Tests: `bash harness/i9-test-readonly-allow.sh` — expects 11 RUN /
  24 REFUSED / 2 guard refusals + filesystem canaries, refusal
  classified by denial wording, not is_error. Proven live 2026-11-11 with
  glm-5.3 via the gateway (runs A–E + V/W under `~/.mastermind/mmos_dev/hx/i9/`).
- Adversarial result (deepseek child + HX reproduction): `Bash(git diff:*)`
  let `git diff --output=<any path> HEAD` write outside the working
  directories (canary verified, is_error=false). **git diff is therefore
  NOT allowlisted.** Repair 1 (run F) found the same hole in
  `Bash(git log:*)` (`git log -1 --format=%h --output=<path>` wrote an
  8-byte file outside the working dirs, is_error=false) — **git log is also
  NOT allowlisted**; the fragment is 8 prefixes. Without the rules the CLI's
  own analysis denies the `--output` forms (re-verified: "requires
  approval", no file written) while plain `git diff`/`git log` reads still
  run via built-in read-only handling. Remaining prefixes (ls, cat, head,
  tail, wc, echo, git status, git rev-parse) have no write-out flags;
  run F additionally proved cat/head/tail are blocked outside the working
  directories even with `Bash(cat:*)` allowlisted ("For security, Claude
  Code may only read the working directories") — key files under `~/.t3`,
  `~/.ssh` etc. stay unreadable without any deny rule; no deny-vs-allow
  precedence question remains open.
- Scope honestly stated: the worktree guard's own two refusal families
  (git-in-complex-form) are **not** bypassable by any permission rule, hook
  allow, or skip-permissions (proven live); the fragment restores prompt-free
  simple/compound read-only flows and turns the rest into precise denials.

## Item 8 — exempt no-repo jobs from worktree quarantine (STAGED)

- File: `harness/i8-exempt-no-repo-project.md` — measured cost (4 s local
  `git worktree add` at Mastermind scale; network fetch dominates the
  fabric-hook path) + smallest change: per-project
  `default_thread_env_mode = local` (existing T3 feature, no code), install
  steps and rollback inside. No host file is replaced; the change is one
  settings row per project.

## Item 8 repair 2 — Macro ship_loop_guard read-only remedy (STAGED, NOT installed)

The real quarantine for Macro-rooted sessions is the Macro project hook
`.claude/hooks/ship_loop_guard.py` (`_delivery_root_admission` :644-680 —
linked worktree + `claude/*` branch only; T3 `t3/*` branches always fail;
remedy text :594-634 always orders an SSD mint even for read-only tasks,
though read-only calls are allowed at :493-500/:542-555). Proven live:
deny+remedy reproduced end-to-end (runRB), and a read-only child completed
with **no mint** under the active hook using only the brief line (runRC) —
full table in `~/.mastermind/mmos_evidence/hx-20261111/item8-worktree-quarantine.md`.

- File: `harness/i8-ship-loop-readonly-remedy.patch` (one sentence added to
  the remedy text; zero behavior change — read-only calls already allowed).
- Install (owner decision; HX installed nothing):

      F="$HOME/Documents/Cluade/Macro Dashboard/.claude/hooks/ship_loop_guard.py"
      cp "$F" "$F.bak-hx8"   # rollback: mv "$F.bak-hx8" "$F"
      patch -p1 -d "$HOME/Documents/Cluade/Macro Dashboard" \
        < harness/i8-ship-loop-readonly-remedy.patch

- Replaced file (pre-install) sha256:
  `0cdca34217e01a524618e70c71be27347ad1d884eea98f72715669db7832207f`.
- Rollback: `mv "$F.bak-hx8" "$F"` (or `patch -R`).
- No-install alternative (proven): the usage-rule brief line — "If a
  SESSION ROOT QUARANTINE notice appears, do NOT mint a worktree, do NOT
  call EnterWorktree, do NOT perform any suggested remedy — plain single
  read-only commands and the Read/Grep tools are already allowed; finish
  the read-only task and return results." Plus, for any child: "Do not end
  your turn while a command of yours is still running; run it in the
  foreground and wait for it."

## Items closed without staged code

- Item 6 (fleet browsers): diagnosis only (one host healthy, two need
  one-time human Chrome loads) — `item6-fleet-browsers.md`.
- Item 10 (silent stops / failed resume): root causes + exact T3 source
  hook points; no T3 change requested — `item10-silent-stops.md`.
- Item 11 (one-way link): stale peer origin after the 05:25Z port move;
  fix = re-pair from peers — `item11-cross-machine-link.md`.
- Item 12 (MCP auth): one interactive `/mcp` sign-in under the provider
  CLAUDE_CONFIG_DIR — `item12-mcp-auth.md`.
- Item 5: moved to lane BCU (steer 2) — `item5-handoff.md`.

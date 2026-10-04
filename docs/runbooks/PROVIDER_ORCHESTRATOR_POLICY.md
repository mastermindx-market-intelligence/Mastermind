# Provider orchestrator policy deployment

This runbook installs the reviewed user-scope Mastermind CEO/orchestrator policy into local
Codex and Claude provider homes. It is configuration deployment only: it creates no lifecycle,
queue, retry, merge, watcher, source-custody, or permission authority.

Canonical source:

- `ops/executive_os/provider_orchestrator_policy.py`
- `ops/executive_os/provider_orchestrator_guard.py`

The deployer manages one marked policy block in `~/.codex/AGENTS.md` and
`~/.claude/CLAUDE.md`, one `PreToolUse` registration in each provider home, and identical
copies of the reviewed guard. Existing unrelated instructions, hooks, model settings, plugins,
permissions, worktree hooks, and credentials are preserved. Legacy
`mastermind-ceo-async-ci-v1`, `mastermind-ceo-context-discipline-v1`, and
`mastermind-ceo-forward-execution` blocks are migrated to the single v2 block rather than
stacked.

## Verify before apply

Run from a protected/reviewed Mastermind checkout:

```bash
python3 ops/executive_os/provider_orchestrator_policy.py verify --home "$HOME"
```

`READY` means the exact reviewed guard digest, policy content, and both provider hook
registrations match. `DRIFT` is read-only evidence; it does not authorize overwriting an
unrelated provider home. `REFUSED` means preflight found a malformed/unsafe target before
an apply could complete. `APPLY_INCOMPLETE_VERIFY_REQUIRED` is different: at least one
managed file changed before a later write failed. Keep the same host/carrier, inspect the
reported modified files, and run `verify` before any replay or alternate deployment path.

## Apply

After the source revision intended for the host is accepted:

```bash
python3 ops/executive_os/provider_orchestrator_policy.py apply --home "$HOME"
python3 ops/executive_os/provider_orchestrator_policy.py verify --home "$HOME"
```

The first mutation of an existing managed file creates a
`.mastermind-orchestrator-backup`; later idempotent applies do not replace that original
backup.

## Behavioral canary

Installation is not behavior proof. In a disposable Mastermind worktree/provider session,
verify all four observations separately:

1. A foreground `gh run watch <run> --interval 150` is denied with an asynchronous-wait
   explanation.
2. The same watcher launched with the provider's real background primitive is admitted and
   returns context instructing the principal to continue another independent lane.
3. A foreground CI status + `sleep` polling loop is denied even at a 150–300 second cadence.
4. A first bounded CI status read is admitted; an unchanged repeat inside five minutes is
   denied. A real watcher/event remains the next observation.

Do not launch a real workflow merely to prove the guard; use an already-existing run/PR or a
synthetic hook payload where possible. Never cancel/re-dispatch shared CI as part of this canary.

## Fleet acceptance

Track source review, host installation, provider hook visibility/trust, and behavioral canary as
four distinct states. A merged source file proves none of the latter three. A copied file proves
neither provider selection nor hook execution. For an offline host, leave it `NOT_INSTALLED`
rather than inferring convergence from another machine.

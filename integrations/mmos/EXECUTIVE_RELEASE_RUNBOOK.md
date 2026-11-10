# Executive Release Runbook — one window for the release owner

Transcribed from `integrations/mmos/L1_R6_DECISION_MEMO.md` §2–§5. Every command
below was verified against the usage/flag parsing of `ops/executive_os/install.sh`
and `ops/executive_os/service-control.sh` at the head of this branch — see the
flag note in §4 for the one memo/script discrepancy found.

## 1. Purpose

This is the **one-window release procedure for the Executive release owner (root)**
after a trunk PR merges to protected `master`. It stages the new release, flips the
Control and MCP components to the new generation, and leaves the production Worker
untouched. Nobody else runs these steps; no agent makes itself eligible.

## 2. Preconditions

- Hold **#1893** (`09b/call5913` + programme umbrella) is honored/cleared by its
  owner. Receipt reconciliation is one-way durable evidence (`DO_NOT_REDO`);
  the hold fence in `/Volumes/Mastermind/evidence/mmos-commission-01a15741/CURRENT.md`
  is owner-controlled. **This runbook never touches it.**
- `worker.codex` is **lawfully quiescent** at a real maintenance boundary. The
  guard `control_component_worker_live` (`ops/executive_os/autonomy_control.py:8846-8876`)
  admits only `LIVE` (control loaded+enabled, worker unloaded+disabled) or `OFFLINE`;
  a loaded-and-enabled Worker raises `control_component_worker_live`.

> **NO agent ever stops, disarms or restarts the production Worker to make this
> release eligible.** Only the root Executive release owner at a quiescent
> maintenance boundary (or a full `install.sh` cutover) may disable/bootout
> `worker.codex`. Manufacturing eligibility is prohibited.

## 3. Variables

- `T` — new trunk 40-hex SHA (merged to protected `master`, clean checkout at that SHA)
- `P` — current installed release: `dd45d1112cb437d8a033ef314e5bf5b8f97a65bc`
- `R` — releases dir: `/Library/Application Support/MastermindExecutive/releases`

## 4. Exact command sequence (memo §3, verified)

```bash
sudo /bin/bash ops/executive_os/install.sh --source-repo /path/to/clean-master \
  --expected-sha "$T" --operator-user <name> --stage-release-only
sudo /bin/bash "$R/$T/ops/executive_os/install.sh" --source-repo /path/to/clean-master \
  --expected-sha "$T" --operator-user <name> --stage-admin-checkout-only
sudo /bin/bash "$R/$T/ops/executive_os/service-control.sh" plan-control-component --expected-sha "$T"
sudo /bin/bash "$R/$T/ops/executive_os/service-control.sh" apply-control-component \
  --expected-sha "$T" --plan-sha256 <plan-64-hex>
sudo /bin/bash "$R/$T/ops/executive_os/service-control.sh" plan-mcp-component --expected-sha "$T"
sudo /bin/bash "$R/$T/ops/executive_os/service-control.sh" apply-mcp-component \
  --expected-sha "$T" --plan-sha256 <mcp-plan-64-hex>
```

**Flag note (memo vs script):** the memo's two `install.sh` invocations omit
`--operator-user NAME`. `install.sh` **requires** it (usage line 389; hard check
line 458; the account must exist and be a member of `_mastermind_ops`). The
runbook adds it above. All `service-control.sh` verbs and flags (`--expected-sha`,
`--plan-sha256`, `reconcile-*`) verify against its usage text.

Each `plan` step is read-only and prints the closed plan document **with its
digest** (`plan_sha256`); copy that 64-hex digest into the paired `apply` step.
`apply` recompiles the plan from live installed state and refuses on any digest
mismatch. Run each plan/apply pair in order before the next.

## 5. T3 enrollment extras — OWNER ACTS (memo §5 owner ask (b))

These are **owner acts on the live host**, not part of the scripted sequence above:

- Add `MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE` (path-only token file, root-readable)
  and `MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE` to the Control
  `com.mastermind.executive.control.plist` environment (both names verified in
  `control_plane/t3_native_composition.py:84,91`).
- Register the **`t3-native-01`** worker in the control DB
  (`/var/db/mastermind-executive/control/db`), per memo §5(b) — its provider
  home follows the installed `workers/codex-01/provider-home` pattern
  (install.sh `PROVIDER_HOME`). Separately, R5 landed the approved staged
  `t3` route row in `config/executive_worker_routes.json` with `enabled=false`;
  enabling that row is this owner step, after R6.

## 6. Rollback (memo §3)

The prior release dir `$R/$P` stays pinned: `com.mastermind.executive.{control,worker.codex,mcp}.plist`
(`ProgramArguments` + `WorkingDirectory`) and `config/control.json` (`proof_base_sha`)
all still name `$P`. Exact preimages are retained in
`config/control-component-update-v1.json` and
`installation-receipts/mcp-update-<plan12>.{config,plist}.before`.

- **Interrupted run**: use `reconcile-control-component --expected-sha "$T"` /
  `reconcile-mcp-component --expected-sha "$T"` — they prove one interrupted update
  to its exact retained postimages; they never republish, never re-dispatch a
  recorded bootout/bootstrap, never roll back.
- **Post-apply rollback**: re-run `plan/apply-control-component --expected-sha "$P"`
  against the prior SHA.

## 7. What stays untouched

- Hold **#1893** — owner-controlled; this runbook never clears it.
- The **production Worker** — agents never stop, disarm or restart it to create
  eligibility.
- **Port 8443** from the agent side.
- `~/.hermes` — read-only from here.
- **No Hermes gateway restart** (Hermes seat acts separately at its own boundary).

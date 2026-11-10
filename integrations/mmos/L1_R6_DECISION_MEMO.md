# L1 R6 Decision Memo — Trunk Executive Install vs Side-by-Side (2026-11-09)

## 1. Hold #1893 (`09b/call5913` & programme umbrella)
- **What created it**: Host commissioning `mmos-host-commission-b4a5a8925c6c-20261103-c4-v2` (root `01a15741-5e68-7803-8eb4-ccac74a6c04b`) phase `09b-maintenance-acceptance-after-service-stop` produced protected administrator-result `call5913` (`5913a5dd…`). Automated read was denied; `/Volumes/Mastermind/evidence/mmos-commission-01a15741/CURRENT.md` held dependent backend install/service/auth/canary actions.
- **Who/what lawfully clears it**: The assigned Root/Web owner consuming `/private/tmp/mmos-read-original-09b-completion-01a15741.py` (`1d6badf4…`) on the original carrier and reconciling `CURRENT.md`. On 2026-11-08/09 (`#1893` comments `6729078053`, `mastermidx4` 09:48Z), Root reconciled `09b` (`HOST_ACCEPTANCE_PASSED_SERVICES_STOPPED`, sha `b8b75c18…`) and upgraded Control/Worker/MCP to `dd45d1112cb437d8a033ef314e5bf5b8f97a65bc`, but kept `#1893` open for remaining A2/C1/provider-readiness/App `3652d89` holds.
- **Reversible?**: Receipt reconciliation is one-way durable evidence (`DO_NOT_REDO`); the administrative hold fence in `CURRENT.md` is owner-controlled. **Rule here: hold #1893 stays untouched.**

## 2. `control_component_worker_live` (`ops/executive_os/autonomy_control.py:8846-8876`)
- **The check**: `plan-control-component` / `apply-control-component` call `AutonomyController._component_mode()`, which probes `launchctl print system/com.mastermind.executive.worker.codex` and `launchctl print-disabled system`.
- **Eligibility**: Admits only `LIVE` (`control` loaded+enabled, `worker.codex` unloaded+disabled) or `OFFLINE` (both unloaded+disabled). Today `worker.codex` is loaded (PID 19597) and enabled, so `_component_mode()` raises `control_component_worker_live` (and `control_component_worker_not_disabled`).
- **Who flips it & what it protects**: Only the root Executive release owner at a quiescent maintenance boundary (or full `install.sh` cutover) may disable/bootout `worker.codex`. It prevents retargeting `com.mastermind.executive.worker.codex.plist` and restarting Control on a new generation while a live Worker daemon runs on the old generation (`dd45d111`) or can respawn mid-transaction.
- **Reversible?**: Yes at the launchd layer (`enable`/`bootstrap`), **but L1 MUST NEVER stop/disarm/restart production Control or Worker to manufacture eligibility.**

## 3. Lawful Normal-Release Install Route (`docs/executive_os/CONTROL_COMPONENT_UPDATE.md`, `ops/executive_os/mcp_component_update.py`)
- **Privileges**: `root` (`sudo`) by the Executive release owner, after trunk PR merges to protected `master` and `worker.codex` is lawfully quiescent under `#1893`.
- **Exact command sequence** (`T=<trunk-40-hex>`, `P=dd45d1112cb437d8a033ef314e5bf5b8f97a65bc`, `R="/Library/Application Support/MastermindExecutive/releases"`):
```bash
sudo /bin/bash ops/executive_os/install.sh --source-repo /path/to/clean-master --expected-sha "$T" --stage-release-only
sudo /bin/bash "$R/$T/ops/executive_os/install.sh" --source-repo /path/to/clean-master --expected-sha "$T" --stage-admin-checkout-only
sudo /bin/bash "$R/$T/ops/executive_os/service-control.sh" plan-control-component --expected-sha "$T"
sudo /bin/bash "$R/$T/ops/executive_os/service-control.sh" apply-control-component --expected-sha "$T" --plan-sha256 <plan-64-hex>
sudo /bin/bash "$R/$T/ops/executive_os/service-control.sh" plan-mcp-component --expected-sha "$T"
sudo /bin/bash "$R/$T/ops/executive_os/service-control.sh" apply-mcp-component --expected-sha "$T" --plan-sha256 <mcp-plan-64-hex>
```
- **Rollback**: Yes, prior release dir `$R/$P` is pinned explicitly in `com.mastermind.executive.{control,worker.codex,mcp}.plist` (`ProgramArguments` + `WorkingDirectory`) and `config/control.json` (`proof_base_sha`). Exact preimages are retained in `config/control-component-update-v1.json` and `installation-receipts/mcp-update-<plan12>.{config,plist}.before`. Interrupted runs use `reconcile-control-component` / `reconcile-mcp-component`; post-apply rollback re-runs `plan/apply-control-component --expected-sha "$P"`.

## 4. Side-by-Side Scratch Executive Evaluation (`~/.cache/mmos-l1-r6-executive`)
- **Topology**: Production is a 3-process root stack (`scripts/executive_os_phase1c.py serve` UID 450, `scripts/executive_os_phase1c_worker.py serve` UID 451, `ops/executive_os/executive_mcp_entry.py` UID 458). However:
  1. `executive_mcp_entry.py:69-76,884-889` hard-requires `os.geteuid() == 458`, root-owned `0755` sealed ancestors (`require_sealed_path`), `/var/run/mastermind-executive/ceo-ingress.sock`, and `/var/log/mastermind-executive/mcp-auth`; it also does not wire `build_hermes_host_mcp_app` (`hermes_host.py`).
  2. `scripts/executive_os_phase1c.py` does not call `install_execution_return_seam` (only wired in `t3_admitted_canary.py` and tests).
  3. Commit `61a89955a` explicitly deleted `scripts/dev_hermes_child_request_mcp.py` (`drop dev Executive launcher (identity guard; would be a parallel listener)`).
  4. For R9, `SecretaryNativeSendTransport` (`integrations/session_bridge/hermes_native_return.py:227-297`) uses `HermesNativeSession.request` over the installed root-sealed `FabricBindingSource` (`hermes_native.py:249`), not HTTP; without root-sealed Secretary session bindings, delivery returns `NATIVE_SESSION_UNAVAILABLE` (already proven in R3).
- **What it WOULD prove**: Daemon-level `ExecutiveControlService` + `MixedExecutionOwnerSupervisor` (`compose_t3_native_owners_for_service`) `kill -9` + `service.reconcile()` over `~/.cache/mmos-l1-r6-executive`, plus ASGI/loopback `build_hermes_host_mcp_app(create_coo_app(...))` `POST /mcp/hermes-host` (`child_request_admit`).
- **What it would STILL NOT prove**: (a) Production R6 (`dd45d111` stays on `:8443` and `/var/run/mastermind-executive/*.sock`); (b) `executive_mcp_entry.py` root/UID-458 gate; (c) R7 production plist/DB enrollment (`t3-native` row in `/var/db/.../executive.sqlite3`); (d) R8 live Hermes gateway (`mmx-executive` points to `:8443`, and `61a89955a` forbids a parallel TCP listener); (e) R9 live `DELIVERED` receipt into Hermes (`HermesNativeSession` requires the installed root `FabricBindingSource` and live Secretary session).
- **Build / launch / verify / teardown commands (in-process ASGI/service harness, no parallel TCP listener per `61a89955a`)**:
```bash
export S="$HOME/.cache/mmos-l1-r6-executive" T="/Users/chriswong/.t3/worktrees/Mastermind/t3-5fa4ea09"
mkdir -p "$S/run" "$S/db" && chmod 700 "$S"
PYTHONPATH="$T:$T/tests" /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -B \
  "$T/integrations/t3/live_proof/t3_admitted_canary.py" --scratch-root "$S"
PYTHONPATH="$T" /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -B -m pytest \
  "$T/tests/test_hermes_child_request_host_forwarding.py" "$T/tests/test_t3_native_composition.py" -q
rm -rf "$S"
```

## 5. Ranked Recommendations & Exact Owner Asks
1. **Option 1 (RECOMMENDED) — Keep R1–R4 scratch canary + unit/ASGI proofs as pre-R6 evidence; land G1–G3 + two missing production seams (`install_execution_return_seam` in `scripts/executive_os_phase1c.py` and `hermes_host` mount in `ops/executive_os/executive_mcp_entry.py`); defer R6/R7/R8/R9 live cutover to one coherent root release after `#1893`.**
   - *Owner ask*: **(a) L1**: wire `install_execution_return_seam` + `hermes_host` mount on `t3/mmos-v2-l1-gaps` and merge to `master`; **(b) Executive Release Owner (root, after `#1893` & Worker quiescence)**: run §3 stage + `plan/apply-control-component` + `plan/apply-mcp-component`, add `MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE` + `MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE` to Control plist, and register `t3-native-01` in `/var/db/mastermind-executive/control/db`; **(c) Hermes Seat**: run `/tmp/l1_owner_acts_20261109.md` §A (`hermes plugins enable mmx-mastermind` + config set + gateway reload at Hermes maintenance boundary).
2. **Option 2 — Run a one-shot supervisor `kill -9` + `reconcile_restart` extension inside `t3_admitted_canary.py` on `~/.cache/mmos-l1-r6-executive` (no TCP listener, honoring `61a89955a`).**
   - *Owner ask*: **L1 lead** approval for 1 extra T3 canary thread budget to prove `ExecutiveSupervisor.reconcile_restart` across child `kill -9` on scratch SQLite; still requires Option 1 owner asks for production R6–R9.
3. **Option 3 (DO NOT SELECT) — Stand up a side-by-side TCP Executive MCP daemon on a second port.**
   - *Owner ask*: None — explicitly rejected by commit `61a89955a` (identity guard against parallel Executive listeners) and cannot satisfy `executive_mcp_entry.py` UID 458 / root-seal invariants or `HermesNativeSession` R9 delivery.

# Claude fabric pre-onboarding integration checkpoint

FINALIZATION_CLASSIFICATION: CHECKPOINTED_CONTINUATION
MISSION_COMPLETE: false
CAPABILITY_STATE: BUILT_NOT_PROVEN / PRODUCTION_DISARMED

## Assignment and custody

Chairman requested continued native Claude integration into the existing subagent
fabric, with no account login now. Complete source wiring and offline verification
before account-by-account onboarding.

- Repository: `mastermindx-market-intelligence/Mastermind`.
- Operation: `claude-fabric-preonboarding-integration-20260926-sol-001`.
- Original source pin: `0d12bb45c4429a7441614fac8eff4830db5e7c0d`.
- Current protected procedure/recovery pin: `763ec8f920177fdf48b18df1b8e37b61ab482ef0`.
- Current-pin COLD_START, ACTIVE_EXECUTION, WEB_CEO_DELEGATION and CLOSEOUT
  were reloaded and verified byte-identical to the previously fully read versions.
  Protected movement changes only status.sh and its tests; adapter paths are unchanged.
- Published first slice: PR #999 at `517a4b8e6c68d4c60163989a06fabb47dc24ee95`.
  The containing commit of this updated file identifies the recovery-fix successor.
- Skillpack: mastermind.sol_skillpack.v1, version 1.0.1, bootstrap major 1.
- Loaded at that pin: INDEX, COLD_START, ACTIVE_EXECUTION,
  WEB_CEO_DELEGATION, CLOSEOUT, DELIVERY_WORKFLOW and repository instructions.
- Canonical `mmx-workspace acquire`, lane `web`.
- Branch: `sol/web-claude-fabric-preonboarding-integration-20260926-sol-001`.
- Workspace: `/Volumes/Mastermind/agent-workspaces/web/claude-fabric-preonboarding-integration-20260926-sol-001`.
- Direct implementation: LOWER_TOTAL_OVERHEAD for one bounded factory repair.

This is a source artifact, not an Agent OS registry, lease, admission or wake.
Its containing immutable Git revision identifies the candidate. Publication and
remote readback must be verified independently before claiming publication.

## Capability delta

Before: the remote fleet's default factory always constructed the Codex facade,
and fixed endpoints had no adapter identity despite an existing Claude facade.

After: frozen `RemoteWorkerBrokerEndpoint` accepts exactly `codex-cli` or
`claude-code`; legacy callers retain Codex. The existing fleet constructs the
corresponding existing facade. No provider selector enters request data.
Unknown/noncanonical identities refuse before transport. The existing trusted
factory-injection seam is unchanged; no provider/plugin registry was added.

Provider-free tests use production fleet/facade classes against synthetic broker
wire receipts. They prove mixed endpoint construction, exact-worker launch,
immutable identity, wrong-provider response refusal, and retention of the same
worker binding after response loss rather than fallback to another worker.

Code: `control_plane/executive_worker_broker.py`.
Tests: `tests/test_native_claude_remote_fleet.py`.
Native descriptor remains `implemented=false`; provider/route activation is
unchanged. Transport composition is not admission or production proof.

## Verification

RED before implementation reproduced missing endpoint adapter_id and the missing
legacy default; exit 1. Focused GREEN: seven new plus fifteen existing fleet
tests, exit 0. Final combined regression: **359 passed, 11 subtests passed**, exit
0, 63.90 seconds. Python 3.14.7. Syntax compilation and `git diff --check` passed.

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p anyio.pytest_plugin \
  tests/test_native_claude_remote_fleet.py \
  tests/test_remote_worker_broker_fleet.py \
  tests/test_executive_worker_broker.py \
  tests/test_remote_worker_broker_client.py \
  tests/test_executive_claude_worker.py \
  tests/test_claude_worker_preflight.py \
  tests/test_worker_adapter.py \
  tests/test_executive_worker_broker_turnkey_binding.py \
  -q --tb=short -o addopts='' \
  --junitxml=.pytest_cache/claude-fabric-regression.xml
```

An initial broad run failed async remote-client tests because AnyIO was disabled;
the corrected invocation above passed. No application change disguised that
runner failure. A historical plan named a nonexistent
`test_worker_adapter_broker_contract.py`; current test owners above replace that
obsolete command, not the underlying acceptance requirement.

Full-repository pytest with AnyIO and `-x` stopped during collection at
`tests/mastermind_window_reader/test_mission_association.py`:
`ModuleNotFoundError: No module named 'jwt'` (2 skipped, 1 error).
Full-project validation is NOT green in this environment. No global packages
were installed. Exact-head hosted CI and independent review remain release gates.

## Next existing-owner integration unit

**Next action: reconcile and extend #992's post-claim transport binding, not login.**

Observed #992 head: `223664d01c21499791ca891d52d13e43ca8f3e20`.
`RemoteWorkerHostBinding.endpoint_for()` does not propagate adapter identity.
`build_attempt_bound_worker_fleet()` explicitly refuses non-Codex providers.
Reuse its canonical Runtime/Capacity rechecks, attempt-bound client and recovery
operation sets. Do not create a second dispatcher or copy its lifecycle.

After current source-writer/effect reconciliation:
1. Carry closed immutable adapter identity from trusted host binding to endpoint,
   never from launch payload, account name, or provider inference.
2. Check canonical claimed provider against that binding before remote I/O.
   #919's native alias uses `anthropic` with `claude-code`; preserve
   `codex` with `codex-cli`, and refuse unknown/mismatched pairs.
3. Prove claim-to-Claude-fleet composition and negative cases: state movement,
   wrong host, missing binding, provider/adapter mismatch, response loss and
   restart recovery without new start/fallback authority.
4. Reconcile #919's native capability/router/supervisor/service path, then wire
   the existing worker-local native constructor with a genuinely trusted managed
   policy observer and common validation adapter. The scoped protected source
   search found no native production constructor outside the adapter module;
   do not claim this wiring already exists.
5. Complete integrated offline acceptance and source/release review before
   separate account onboarding and a harmless real-account canary.

Observed #919 head: `3a8a753a8ef31bcdf1c32f783627e14504d0a0cf`, Draft/Hold.
Do not silently take over that source writer or create competing admission.
#955 remains the distinct Claude COO/client edge and its role-correct non-CEO
admission dependencies; its Auth0 ceremony is outside this turn. #660 remains
sustained Operator Harness proxy work. #455 is a held fake CLI falsifier, not
native production integration. #589 is closed/superseded; do not revive it.

Native descriptor activation, trusted worker-local composition, exact CLI/model/
managed-policy qualification and account canaries are NOT proven by this slice.
**Account onboarding is not the only remaining task.**

## Collision, effects and continuation

The open-PR census found shared broker-file work in #994 and #590. Their inspected
hunks are imports/constructor/dispatch/status, disjoint from this endpoint/fleet
change. Older large #124 also lists the file; its whole diff exceeded GitHub's
limit, so no complete conflict-free merge census is claimed. Refresh material
source/custody before integration. No incumbent branch/worktree was changed.

Two source-read/verification tool calls were refused before dispatch and were
not retried or rerouted: those actions are EFFECT_NONE, not a platform-wide
outage. Independent edits/tests proceeded from already-inspected source. The
source diff/status/compilation had already passed before the final documentation
write; a subsequent combined status/hash command was refused and its digest
outputs are not claimed. No unresolved modifying effect was observed.

No Claude login, credential read/change, provider inference, production Job or
Attempt, account enrollment, service restart/install, runtime arming, merge or
deployment. Test-local fixtures are not production receipts. No worker/watcher
was dispatched; no background continuation or automatic wake is claimed.

Boundary: the independently owned endpoint/facade unit is implemented and tested;
the next unit crosses existing #992/#919 source owners and requires fresh exact-
head/custody reconciliation. Resume in assigned attended Sol execution from this
checkpoint and the exact published candidate, not unrelated historical handoffs.
The parent mission remains incomplete until the pre-onboarding source vertical
is actually wired and accepted.

## Current recovery-identity unit and expanded Chairman assignment

The Chairman extended the mission: rich native COO environments must expose the
relevant complete skills/plugin catalog, direct access to Mastermind, macro and
mastermind-terminal through existing source custody, and Executive OS / Agent OS /
Mastermind OS / GitHub / Slack integration. Prepare bounded Web CEO handoffs while
retaining this adapter lane. No Claude account login is requested now.

Separate a rich COO principal profile from the sealed child-worker profile. Do not
remove the latter's no-extension/no-MCP fences to simulate COO parity. Reuse #676
(parity), #962/#955 (plugin/auth carrier), and existing workspace/Craft/communication
owners. Cross-session organizational continuity belongs to WS:EXECUTIVE-CAPACITY-FABRIC
in macro/agentos, not a new registry in this repository. Prepared packets are not
worker assignment, PICKUP_ACK, START, or background execution.

New concrete defect found and repaired: the remote facade checked adapter identity
on start but ignored the broker's existing adapter_id in both asynchronous status
and synchronous reattach responses. A Claude facade accepted absent, null, boolean,
empty, Codex, wrong-case and whitespace-drift identities. Two checks now refuse
these replies before accepting status or registering the recovered process. The
same fleet run binding remains retained after refusal; no new start is authorized.
The common wire/schema and provider selector are unchanged. Codex's positive
recovery fixture now mirrors the real broker's existing adapter_id field.

RED: 14 expected failing subcases, 12 tests passed, 11 earlier subtests passed;
exit 1, 1.62 seconds. GREEN after the repair and schema-correct Codex fixture:
**364 passed, 25 subtests passed**, exit 0, 65.39 seconds. The command above was
reused with output `.pytest_cache/claude-recovery-regression.xml`. Five new tests
also cover exact-process native recovery, idempotent reattachment without start,
process-generation drift and lost-recovery-response/no-restart behavior.

The new changed test path is `tests/test_executive_worker_broker.py` (one fixture
field plus comment); its positive assertions remain intact. No account/provider
process was used by the new native recovery tests.

Hosted CI for the prior 517a4b8 candidate is now terminal FAILURE, not pending:
run 36234343299, job 108383295498, synthetic merge
f7769334436d1203ff8b69687e2cea04bf854031. The 754-module gate had one failure in
`test_ohf_real_chain_publishes_visible_items_while_controller_nonterminal`:
first snapshot contained only `LC1 real partial`, but the test prematurely
expected both partial and final. Existing PR #984 owns this exact ordered-prefix
repair. Additional evidence was posted there as comment 5845514532; do not
reimplement its test fix or manually rerun unchanged CI. A current passing native
suite is not full-repository acceptance. The current changed production candidate
requires fresh exact-head CI/review and the normal release gate.

Current effect state: acknowledged source edits and test results only; no unknown
modifying effect. One compound source-discovery request in this continuation was
refused before dispatch and was not repeated; permitted native reads and independent
source/testing actions remained available. No package install, credential action,
provider inference, runtime activation, source-custody transfer or deployment.

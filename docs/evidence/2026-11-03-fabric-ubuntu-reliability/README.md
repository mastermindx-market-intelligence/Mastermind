# Ubuntu maintenance repair and Fabric qualification checkpoint

**Status: maintenance configured on Ubuntu0–4; two bounded Ubuntu0 worker routes verified; source fixes tested and technically reviewed but unreleased; fleet qualification remains incomplete.**

This is a bounded maintenance and recovery slice of the existing
WS:EXECUTIVE-CAPACITY-FABRIC program, integration root
`agent-fabric-end-to-end-fable-integration-20260913-sol-001`,
[PR #600](https://github.com/mastermindx-market-intelligence/Mastermind/pull/600)
P4/P5, alongside the existing
[fleet maintenance owner #1632](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1632).
It does not create a replacement queue, scheduler, watcher, or source-release owner.

## Authority and exact source

The current user requested repair of Subagent Fabric and all Ubuntu hosts.
The operation is `fabric-ubuntu-reliability-20261103-c4`, in its own managed Web
workspace and branch. The protected source base is
`e39a617b6771cb6b07323a533b4cf9db7e78900a`.
The selected native Fabric generation remains
`28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce` (seq24).
No native release selection or provider qualification policy was changed.

The deployed hygiene script SHA256 is
`3f676c0075478029e5857f0a95cd4ba9ae0dba9221eab312b034f88bca2502e3`.
Service and timer hashes, exact host identities, receipt paths, observed byte
counts and service states are retained in [maintenance-receipts.json](maintenance-receipts.json).

## Verified repair

Ubuntu4's existing timer was active, but every service run failed because the
local reserve configuration was absent. The installed script already matched
protected source. Creating the missing
`~/.config/mastermind/fabric-storage-reserve.json` with
`{"internal_floor_gib":75}\n` restored a successful service run:
`Result=success`, `ExecMainStatus=0`, `mode=CALM`, `degraded=false`.
A subsequent canonical heartbeat also remained successful.

Ubuntu0–3 had no hygiene script, service, timer or local reserve config.
All four reported `Linger=yes` and had a same-user, owner-verified existing
D-Bus socket. The exact protected script and units were installed only after
absent-file and unit/drop-in checks. Files were created exclusively, without
following symlinks, with hashes and permissions read back. The first report-only
run succeeded on each host before timer activation; the loaded ExecStart and
FragmentPath were verified before one controlled service execution.

All five timers are enabled and active. The configured 75 GiB is the existing
host registry requirement of 60 GiB plus a 15 GiB checkout reserve. It is an
observation binding, not a new or reduced admission threshold.

| Host | Change | Service exit | Pressure mode | Available GiB at receipt | Cleanup disposition |
| --- | --- | ---: | --- | ---: | --- |
| ubuntu0 | Installed missing protected toolkit and reserve | 1 | CRITICAL | 94.24 | HELD_UNBOUND_CACHE_TARGET |
| ubuntu1 | Installed missing protected toolkit and reserve | 0 | CRITICAL | 98.10 | SKIPPED_UNTRUSTED_CACHE_PATH, SKIPPED_UNAVAILABLE, SKIPPED_UNTRUSTED_CACHE_PATH |
| ubuntu2 | Installed missing protected toolkit and reserve | 0 | CALM | 287.71 | NO_PRESSURE |
| ubuntu3 | Installed missing protected toolkit and reserve | 1 | CRITICAL | 127.49 | SKIPPED_UNTRUSTED_CACHE_PATH, HELD_UNBOUND_CACHE_TARGET |
| ubuntu4 | Added missing reserve to existing install | 0 | CALM | 866.96 | NO_PRESSURE |

A oneshot service's `inactive/dead` state after exit 0 is expected. Ubuntu0 and
Ubuntu3's nonzero service exits are the deliberate current cleanup hold, not
a successful storage repair. Ubuntu1's exit 0 does not clear its CRITICAL
pressure classification or its separate CI disk gate.

The source explicitly returns false from `manager_effect_target_bound()`;
scheduled runs cannot invoke a destructive package-manager purge. It performs
only shallow worktree observations. No Git workspace, worker lease, unknown
effect marker, cache, archive, model or user file was deleted. Attributable
reclaimed bytes are **zero**. Disk availability increased during this session,
but those changes are not attributed to this operation.

## Installation-documentation defect

`LINUX_HOURLY.md` called the configured floor optional and omitted its setup
from the installation sequence, while the implementation requires a configured
floor for a non-degraded receipt. The proposed documentation change explicitly
requires that binding before activation, explains the exact observed failure,
preserves pre-existing configuration, and distinguishes maintenance observation
from worker admission and CI requirements. No executable hygiene behavior
changes in this branch. A separate native executor repair in this same branch
adds local-commit preflight and suppresses a specific Git informational advisory;
see [source-fix.md](source-fix.md) and its exact validation hashes.

## Fabric execution proof and remaining failures

The distinct bounded arithmetic task `fabric-fleet-byte-validation-20261103-c4`
completed on Ubuntu0 through GLM with rc0. Every returned value was recomputed
and verified, and the exact 224-byte response was accepted by the assigning
parent. The owned-process receipt reports normal completion, verified process
identity/census and zero residuals; the local worker marker is absent. Its
usage receipt was missing, so no usage or spend is claimed. This establishes
one bounded worker path, not full host qualification. The text response wrapped
its correct JSON in Markdown; raw JSON formatting compliance is not claimed.

The distinct Qwen documentation review on Ubuntu3 returned
`QWEN_FINAL_RESPONSE_UNCONFIRMED`, rc1 and no accepted review. Its wrapper's
429 label is local inference, not verified provider HTTP status. Full bounded
runtime projections are in [runtime-validation.json](runtime-validation.json).

The bounded source audit `fabric-ubuntu-reliability-20261103-c4-source-audit`
was admitted on Ubuntu1 through GLM / `glm-5.3-flash` with an 18-turn ceiling.
The controller retained terminal rc1 and a `turn_limit` provider outcome.
Its 366-byte response has SHA256
`ab876265c363be23a6ea83bf7ba14f0c040210027e72a8c7b7b1ce52c3fd1dbc`.
No useful audit was delivered; it is not accepted and `retry_allowed=false`.
The `unrecognized_model` warning alone is not a cause diagnosis. Existing
[PR #1894](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1894)
expressly distinguishes this warning from request failure. This run was not
replayed or represented as successful worker work.

Ubuntu2 remains held by four original `sparse_workspace_effect_unknown` runs:

- `news-w4-v91-v1-review-r1`
- `news-w4-v91-v4-review-r1`
- `news-w4-v91-v6-review-r1`
- `news-w4-v91-v7-review-r2`

Their original owner reports `EFFECT_UNKNOWN`; no result, parent acceptance or
safe release proof is established. Original ledger rows bind them to root
`e3d62d36-ba30-4fed-a723-f6ce79ba4f99` and parent
`orch-v91-seat-direct-20261102`. The exact provider lease rows now report
released, while the four local reconciliation holds remain. Maintenance installation does not reconcile
them. Age, a missing process or excess disk cannot release these holds.

Ubuntu4 retains its qualification-only provider modes. Ample capacity and a
successful maintenance receipt do not qualify a worker. Each intended host
still needs admissible useful work, an actual worker start, a valid retained
terminal result, parent consumption, and verified slot release before the whole
fleet can be called fully working.

## Validation and continuation

Live proof covers source and config readback, effective user units, persistent
timer activation, report-only validation and canonical service receipts.
The native executor source changes passed 79 focused tests with no failures or
skips, including the full existing composition suite and new preflight cases.
The rebuilt 102-member inventory changes only the executor. These are source
candidate checks; the live generation has not changed.
Review the source diff, [source-fix.md](source-fix.md), and machine-readable receipts, then continue
through the original Fabric reconciliation, source-release and fleet retention
owners. Preserve currently held or conflicting source carriers (#1836, #1877,
#1951, #1894 and #1902). This branch does not adopt their held executable
candidates. Shared release metadata must be rebuilt against any separately
merged native changes before release; it is not permission to select a held candidate.


## Final observed checkpoint

The fresh read-only host snapshot at approximately **09:03:54 UTC** is in
[closing-validation.json](closing-validation.json). All hosts were reachable,
all installed hashes still matched, and all five timers were enabled and active
after their next scheduled executions. Ubuntu1/2/4 returned service exit 0;
Ubuntu0/3 still returned the existing unbound-cache-target hold. Available disk
was 110.096, 145.848, 287.707, 108.483 and 866.958 GiB respectively. This is a
new observation, not storage reclaimed by this operation. Subsequent telemetry
reported NORMAL thermal risk on all five hosts.

Ubuntu1's four `pc-ci` services remained `activating/start-pre`; `df` showed
89% used. Its separate CI disk condition remains unresolved. Ubuntu2's four
original hold hashes still exactly matched. Ubuntu4's current registry still
lists every allowed provider mode as qualification-only. The installed Fabric
request schema has no host/qualification-host field; the Studio host-command
tool is not an agent-handoff surface. No alternate submission route was used.

The independent source review `fabric-sparse-source-review-20261103-c4`
ran through the Grok pool on Ubuntu0 and completed with rc0. Its exact 6,204-byte
result (SHA256 `7f9062a1c449fe08c4b3c89d0b89c77712e743df17303f3879e35dcd45eab5b8`)
was independently rehashed, adjudicated and accepted. The process receipt proves
normal completion and zero residuals; the local marker is absent and the exact
provider lease reads released. The requested model was `grok-4.7`; the usage
receipt does not independently prove the served model.

The verdict is **NO_BLOCKING_FINDING_WITHIN_SCOPE**, for the exact two-hunk
patch and supplied functions at `bb0266fc54124255e5373ec20607ba410674cecd`.
The reviewer did not execute tests or inspect the whole repository. The full
unchanged response, runtime receipts, limits and parent adjudication are in
[review-result.json](review-result.json). This technical review is not a formal
GitHub approval.

Two additional regression checks passed in 1.479 seconds: the real sparse-index
observation preserved index/configuration bytes, and exit-zero/valid stdout
with unrelated stderr still refused. Together with the earlier 79-test run,
the evidence covers **81 distinct passing tests**, not a single 81-test run.
The executable candidate hash remains unchanged.

The original selected native generation was not replaced. GitHub formal review
submissions and combined status contexts were empty at readback. The connector
reported `mergeable=false`, although the observed upstream commit changed
unrelated paths and a read-only merge-tree calculation found no conflict.
No approval, green CI, mergeability, installation or whole-fleet readiness is
inferred from those observations. The next release action remains with the
existing non-author review and protected native publication owners, followed
by real worker qualification and original-incident reconciliation.

## CI repair and protected-source composition (2026-11-03 continuation)

The original PR-head CI failed in three shards because four tests retained an old CURRENT manifest pin and the historical B11 fixture lacked the exact predecessor executor. The minimal reproducer recorded three assertion failures and one fixture setup error before repair.

The current source composes protected master `9f65957e29eba92245d78609f032aaea523b7cb4` with the existing sparse-commit fix. Regeneration produces 102 members, manifest `dbf5371bd7e346d8abd4c52d65731b52a0eb388cc45c41ce28fe143f295700b8`, and inventory `2b02de89d0fac9a72930e7aa1fbd302f710d3b2c36661245620e48b984e0c934`. Only `ext/remote_sub_exec.py` differs from that protected native manifest; all four upstream diagnostic member changes survive relative to the prior PR head.

The original catalog and diagnostic fixtures, original transition manifest, and historical transformation-chain pins remain unchanged. A supplemental byte-qualified fixture restores only the old executor during disposable historical reconstruction. Current-stage verification still precedes restoration, and all historical members are verified afterward.

Focused regressions: **182 passed, 6 Linux-only skips**, plus **88 passed** for the affected upstream diagnostic paths. The current-manifest failures and all 32 historical successor tests now pass. These local results do not stand in for Linux CI, independent integration review, protected merge, or installation. Exact hashes and receipts are in `ci-repair-validation.json`.

The bounded integration-review request `fabric-ubuntu-ci-fixture-review-20261103-c4` was refused with `MANUAL_ROUTE_UNAVAILABLE`; same-ID status is `NOT_FOUND`, with execution absence unproven and retry disallowed. The operation is preserved without rerouting or replay. The earlier accepted executor review retains only its original scope.

Ubuntu1 diagnosis now identifies its four CI runners’ startup refusal: disk use is 88.86%, above the installed guard’s 85% threshold. The guard also requires 100 GiB free. No CPU or memory refusal was observed. No disk threshold was lowered and no data was deleted. A bounded storage ownership read found the root-owned isolated runner directories unreadable as `longr`; the home census is partial.

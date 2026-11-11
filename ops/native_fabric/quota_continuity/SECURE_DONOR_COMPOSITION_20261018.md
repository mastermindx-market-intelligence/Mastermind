# Secure donor and quota-continuity composition

## Why this additional source change is required

Ubuntu Fabric #1404 and quota-continuity #1592 independently changed the same
sealed executor preimage. The #1404 source carrier repairs donor qualification;
#1592 adds the provider outcome-path binding and publishes a complete immutable
native generation. Installing either standalone executor over the other would
lose accepted behavior. This composition retains both transformations.

#1404 merged through the native protected queue at 2026-10-18 10:58:30 UTC as
`00d64feaaa8394f904682e22eb1fc8e70e9ce096`. Its reviewed source head remained
`115a50a52a1e212a24b739945c033ac1a90f74e9`; all 51 source-carrier blobs survived
in the queued merge tree. All three shards and the required `test` gate passed
in merge-group workflow `39119189720`. This composition is a subsequent source
change and needs its own immutable-head review and protected checks.

Only `candidate/remote_sub_exec.py` changes among the 81 native runtime files.
The native manifest and source inventory are regenerated from the existing
explicit builder. The other 80 entries, the historical preimages, publisher,
installer, continuation policy, support helpers, and state bindings remain intact.

| Source identity | SHA-256 |
| --- | --- |
| Shared sealed preimage | `a29798abb84294b1d8a67c53ef2b45137db4517f960598e51c8da21796d6cf61` |
| #1404 repaired executor, reviewed at `115a50a52a1e212a24b739945c033ac1a90f74e9` | `131f56a4c26915d9e6a5fc6501f930b3aeeb5e4c4501eb730b080e0c6dde5772` |
| #1592 executor, protected in `89cf2399c47da20c0c23826266e52984f88c27e7` | `f5ec893143e5bf43c37cc1d98ff1b67c0b36d9cc8674d4bf0b12ab6da0f7a29c` |
| Composed executor, 47,180 bytes | `8fc268d94c66227dac66c259343c137da8256d7b4545b4f77591ebc4eb66c43d` |
| Regenerated 81-file native manifest | `58b8bb063324ec67b1720c15488ac06e1091e8383c661cb0a6005f0f8f21907f` |
| Regenerated source inventory | `a4075a4a36873a65c01df7a93c703f4de049780e78e5ae40fc850e8a6e131fd5` |

The composed file before `def _execute` is byte-identical to the #1404 repaired
executor. Its `_execute` and complete subsequent tail are byte-identical to
#1592. Relative to the repaired #1404 executor, the sole addition is #1592's
existing assignment of `POOL_OUTCOME_FILE` to this run's immutable support
executor `lanes/<key>.provider.json` path, immediately after `POOL_USAGE_RUN_ID`.
This preserves the original remote stable-state owner through its fixed link.

## Security behavior retained

Data-only, bounded, stable no-follow qualification of donor ancestry and common
and worktree Git configuration precedes donor Git. Command-bearing, include,
redirection and unknown configuration refuses. Observations use fixed Git,
bounded process/output handling, scrubbed Git/loader settings, disabled hooks
and fsmonitor, and denied transports.

Helper and policy bytes require independent HEAD, unflagged stage-zero index,
and stable working-file agreement. Lowercase index tags, including the combined
assume-unchanged form, refuse. Observed Gitlinks refuse before status can enter
a separately configured repository. Uppercase skip-worktree entries are allowed
only outside the independently approved cone with proven absence; required or
materialized paths and uncertain absence refuse. This constrained sparse rule
was explicitly accepted in the independent review of the repaired source.

The actual workspace controller retains final donor requalification, reachable
drift handling with cause and effect uncertainty, refusal to reuse effect
carriers, isolated Python helper invocation, and typed uncertain cleanup. The
controller does not remove or reuse a checkout on failure. The pinned Macro
helper's own failure cleanup remains its separate existing behavior.

Python `-I` limits module-search exposure; it is not an operating-system sandbox.
The trusted system Git/interpreter, interpreter-wide initialization and an
adversarial concurrent same-UID writer remain explicit assumptions. Immutable
publication does not remove a real donor ownership or writer/effect hold.

The original paid review remains `CHANGES_REQUIRED` on its original `ba3938`
source. Its retained result and original lineage are preserved; this composition
does not restart that worker or turn its historical verdict into a PASS.

## Verification of the actual combination

`tests/test_fabric_native_security_composition_20261018.py` adds 67 cases. It
retains the original standalone #1404 patch-application suite and reuses its 66
unchanged inert donor assertions against functions compiled from the actual
composed candidate. Before fixture pin overrides, the test verifies the original
patch/preimage, both independently known postimage hashes, security-prefix and
quota-tail equality, and the complete generated native inventory.

The additional publication test uses a fresh subprocess and real artifact owners:

1. Build and verify all 81 staged native files, publish and select them in a
   disposable native kit, read the selection once and retain the verified real
   generation path.
2. Execute that selected generation's actual `support-meta` helper. Require its
   publisher's 36-file closure to match the selected controller's declaration.
   Read the fixture policy through its original `orch` owner; no `pools.yaml`
   file is added to native `ext`.
3. Transfer exactly those code bytes and the inert policy, then use the actual
   transferred publisher. Verify the support digest, sealed file/directory modes,
   reuse and fixed remote state links.
4. Import the actual executor and runtime modules from the published support
   directory, with no source/candidate fallback on that import path.
5. Invoke the actual `_execute` with a fixture-only lease and a benign committed
   helper. The controller's actual `_new_macro_workspace` and real owned-process
   runner mint a disposable linked sparse worktree. `HOME` remains unchanged;
   the fixture helper derives its destination from its explicit donor CWD.
6. Stop at an explicit fixture sentinel before the provider runner. Assert the
   corrected outcome path despite a deliberately wrong input value, unchanged
   root/parent/run/lease/account identities, verified workspace and branch, minted
   process receipt with proven cleanup, and workspace-ready CWD/environment.
   No provider outcome or ordinary worker process receipt exists. The fixture
   lease records the expected missing-worker-receipt hold.

This is an offline composition proof. The helper is deliberately a benign
fixture with fixture Git-object pins. It does not prove execution of the genuine
production Macro helper, physical admission, a paid provider, or a real worker.
The wrapper/outcome and quota-recovery suites separately exercise actual wrapper
receipts against inert loopback provider fixtures using this candidate executor.

Prepublication verification passed 67 composition cases and all 75 existing
quota/recovery cases. The existing rollout suite passed 16 cases in scratch;
its one real DirectoryChain case passed separately on M2 using a newly created
owned fixture parent under the trusted home ancestry. That final invocation ran
the unchanged protected test, publisher and six verified runtime dependencies:
one case passed, zero skipped, in 0.315 seconds. It exercised only disposable
fixture state and made no production selection, service or provider change.
Together these runs cover all 17 existing rollout cases without weakening the
directory-custody guard or changing `HOME`.

Run the affected suites from the repository root:

```sh
python3 -m pytest -q tests/test_fabric_native_security_composition_20261018.py
python3 -m unittest discover -s ops/native_fabric/quota_continuity/tests -p 'test_*.py'
python3 -m unittest discover -s ops/native_fabric/quota_continuity/rollout -p 'test_*.py'
```

The owned-process seam needs normal local process-table visibility. A restricted
executor that denies the process census correctly produces unproven cleanup;
do not mock that result into success. Loopback wrapper tests also require a
local socket. The existing directory-custody integration test still requires
the documented trusted native fixture root. No guard is weakened for scratch.

## Existing installation and the next release boundary

The #1613 owner reported that #1592 native phase one and the existing collector
rebind were complete. A continuation readback independently found this selection
on the original M2 kit:

- Native generation `d8533f8cfac86410c41fa15c2b3d24c6473f08633fe39aeb8c8115a3cb2dc74c`.
- Selection sequence 1, previous generation null; pointer SHA-256
  `32e377263ac32b7ee142336a715b54f176fbbceb253bbba29038de33cd62373f`.
- All 81 installed code hashes matched protected #1592, with sealed file modes
  and descriptor-matching state links. The selected executor was `f5ec8931...`;
  the retained flat executor was still `a29798ab...`.

That is a historical readback, not an install lock. Reconcile the current
selection, source writer, original lease/producer identities and active release
operations immediately before any new publication or selection. Do not repeat
native bootstrap, phase one or collector rebind. Use the existing publisher and
selector CAS for the new generation, preserving running controllers' pinned
paths and all old generations. Do not overwrite flat helpers.

For the original M2 stable-ext binding, this exact manifest predicts native
generation `bb55b27481ee1fb21ce604bbd358920fe653f40ce4d7ac59f3d57b4afb037612`.
This value is a deterministic descriptor calculation, not a publication receipt.
It must be independently verified against the actual protected merged source
and original owner binding during deployment.

The current publication units are **81 native code files and 36 remote support
files**. This supersedes the earlier #1404 private 31-file support frontier for
the combined release. Earlier support digests, fixture-helper receipts and
review results retain their original byte identities and proof limits.

#1613 retains its active C3 backend/service release owner, including the corrected
sealed-profile and stdout-capture work. #1457 keeps its separate Web MCP owner;
Macro GC #9430 keeps its cleanup owner. Source publication does not grant a new
Session Bridge, authorize a service restart through another owner, or supply a
missing worker-dispatch capability.

## Operational acceptance still required

Before claiming a host operational, qualify its actual donor ownership and
metadata, selected native source, remote immutable support digest and invocation
binding. Earlier donor holds were observed on all four hosts; source approval
does not clear those observations. Keep dirty original donors, original leases
and uncertain effects intact. Do not repeat Ubuntu1's blocked staging operation
or the earlier rc78 review.

Capacities remain **12/18/12/12**, with U2/U3 **80 degrees C** new-job admission,
disk/load/PSI protections and provider quotas. NEW Macro workspaces, CPU-scoped,
fixed-pool/model, artifact, native-return and operator requests remain ineligible
for automatic quota continuation under the preserved #1592 policy.

The combined source still requires independent semantic review on its new
immutable head, protected head and merge-group checks, protected merge readback,
immutable deployment and host binding, then real original-carrier admitted
worker START, result and explicit acceptance. Sustained heavy-load and any
attended thermal/cooling qualification remain separate physical evidence.

MISSION_COMPLETE: false.

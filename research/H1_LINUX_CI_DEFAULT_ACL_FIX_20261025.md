# H1 Linux test-platform qualification — exact #1847 source-only repair

**Status:** CI fixture correction, not host/provider/initializer approval. Current protected
source prerequisite `master@bb85b429f2ffffd38408080ce4df7d6378c34100`;
original #1847 repair base `bdcad338796111b7c0c6d670b4d7a4fd217d52d0`.

## Observed falsifier

Hosted `ubuntu-latest` job 121181466977, CI 40197393494, failed the real
`test_actual_nested_initializer_private_package_context_and_wire` at the
compiled child. The allowlisted v2 diagnostic says `InitializerCommitmentRefused`,
`BOOTSTRAP`, `HOME_ANCESTOR`, `DEFAULT`, at `run_bootstrap->pin->no_acl->refuse`.
This is an intended strict refusal: a POSIX default ACL on an ancestor of the
hosted account HOME is not an eligible execution environment. No private path,
token or ACL value needs to be displayed to establish the failure.

Read-only physical Linux metadata checks on ubuntu0, ubuntu1 and ubuntu2 found
ABSENT access/default ACLs at account HOME, its ancestor and `/`; a qualified
Linux account can exist. No existing account, ACL, credential or lane was changed.

## Source-only correction

1. The hosted test's **read-only real HOME ancestry** classifier determines
   fixture eligibility *before* the first observer, because an ACL-bearing
   fixture can be refused by that earlier observer (not necessarily the final
   compiled child). Any present ACL means the hosted fixture is an explicit
   `SKIP`, **not a positive runtime receipt**. Unsupported metadata errors
   remain hard failures. If the host is ACL-free, the entire original real
   observer/compiled-child journey remains mandatory, and any nonzero return
   is a hard failure. The required isolated step below cannot be skipped.
2. A **new required job step in the same pytest shard 2**, not optional,
   runs the original positive Linux real process/observer path in a disposable
   container with a fresh non-root account and no HOME-ancestor default ACL.
   The container has read-only source, no network, all caps dropped, no new
   privileges, read-only root filesystem, and only isolated HOME and `/tmp`
   tmpfs write targets. Its Python distribution remains an actual, root-owned
   CPython 3.12 image, not a monkeypatched observer or ACL check.
3. Ubuntu's Python package adds two administrative startup *symlinks* that
   the strict normal-profile initializer independently rejects. The disposable
   test image materializes their exact targets as root-owned **regular files**,
   checks SHA equality, then runs under its non-root account. This modifies
   test-image bytes only, never host `/usr`, private data or production guard.
   No `setfacl`, source runtime patch, fake `pwd`, fake Python status or stubbed
   credential/observer is used.
4. The existing workflow contract test now requires this step before the
   full shard, forbids `continue-on-error`, and checks source/profile isolation.

## Bounded real OS experiment (not CI acceptance)

On authorized Ubuntu0, a disposable `ubuntu:24.04` Python3.12/pytest image
with the two root-owned startup files materialized and a `uid=1555` non-root
fixture was exercised with all capabilities dropped, no network and read-only
source. The **unmodified pre-repair #1847 test source** completed its real
Linux private-package/initializer/getpath/observer process and output
`1 passed in 0.86s` with an `ASSERTIONS_COMPLETED` notice; no provider worker,
real credential, production launch or remote worker effect. The initial
unqualified image correctly refused two Python startup symlinks at
`_require_startup_entry` and was repaired inside the disposable image.

An adversarial negative-only disposable image with an actual POSIX DEFAULT
ACL on its private `/home` tmpfs demonstrated an earlier
`FINAL_OBSERVER_REFUSAL` before the final compiled child; an exit78-only
classifier at the final child would miss this legitimate path. The source
branch now rejects that ineligible test substrate *before* the observer,
without altering production ACL checks. Only the isolated real positive
step is accepted as a CI positive.

The actual GitHub Actions result on this PR's *new exact head* and separate
nonauthor source review are still owed. A compliant disposable positive is
**not** an actual paid-Fabric H1 remote-host acceptance/worker START.

## Do-not-merge boundaries

`candidate/paid_initializer.py` `no_acl` and its Root/file/FD/identity
requirements are unchanged. #1847 stays Draft and unreleased until hosted
current-head checks, independent review, and accepted H1 release gates.
The #1836 97-member host-pull source and already-selected M2 native seq23
are separate owners; this change does not publish, select, restart, merge,
qualify providers, retry a refused run or change an ACL on any live host.

## Current-head D8 identity-literal guard repair

Hosted #1847 run 40269860803 on eb835d47 passed shards 0 and 2,
including the mandatory no-ACL positive CI step, but failed shard 1 only:
`test_d8_template_topology_and_protected_defaults` reported `['700']`.
The D8 identity guard correctly treats an unqualified decimal 700 token
inside a CI source/identity-bearing diff as suspicious; the source was the
new Docker `--tmpfs ...mode=700` permission operand next to `uid/gid`.
Use the explicit **octal** `mode=0700`, not an identity literal.
The original guard is unchanged, its narrow scanner rejects mode=700 and
accepts mode=0700 on the exact YAML diff. Docker on authorized Ubuntu0
independently showed `--tmpfs ...mode=0700` creates a nonroot-owned home
with actual `stat.S_IMODE=0o700`. Keep this exact permission pinned in the
workflow source contract test. No default ACLs, user identities, services
or credentials are modified on any actual host.

## October 31 integration: require a positive result, not just a green step

The prior accepted 102-member H1 union and four-path fixture repair were
composed on original PR #1847 at manifest
`66205e3fcbea978b195d147db932c2bf33c3e806d7d00f7666665863470c90eb`.
That identity is historical component evidence after the sealed-YAML gap below;
it does not qualify the changed production closure. The historical 95-member
fixture and paired installer checks remain intact.

Independent changed-risk review found that a mandatory Docker step alone
does not prove the positive: pytest returns zero when its selected node is
skipped. Earlier successful step status is therefore not sufficient evidence
of one passed journey. The fixture now writes JUnit to writable `/tmp` and
requires the exact selected node once, with zero skips, failures and errors.
Malformed, missing, duplicate and wrong-node reports must refuse. This is a
test-result gate, not a change to the production ACL or execution predicates.

The read-only `/repo` mount is a tracked `git archive HEAD` snapshot from the
actual CI checkout. It excludes `.git` and untracked account/credential files;
the report stays on the separate writable tmpfs. The helper is tracked in the
same source head as the selected test. No host credential or live initializer
read is needed to establish this isolation.

The source union also adds a sixth fast-preflight module,
`tests/test_paid_provider_entry_linux.py`. Its fixed public case/function
selectors join the existing failure annotation allowlist. The annotation
schema remains module, case, function, phase, bounded line and safe errno;
exception text, parameters and temporary paths are never emitted. The
original failed CI job and its raw-log escape-rendering refusal remain held.
New annotations are generated by the new test execution; they do not recover
or re-encode refused raw log bytes. Exact new-head Linux CI remains owed.

## Controlled provider module coverage

Head `26091439` produced a safe failure annotation in the actual compiled
provider journey's final fixture-settlement check. That is not evidence of
the earlier HOME ACL cause: the primary predicate remains unknown and the
failed hosted namespace retains its unproven settlement. The model receipt,
process-identity and cleanup guards are unchanged.

Only the five compiled integration cases now require an explicit controlled
Linux/Python3.12 test request before source staging, HOME namespace creation
or executor launch. The other eighteen unit cases remain runnable on generic
hosts. This test selector grants no host or execution authority. The same
isolated container runs the complete existing provider module, whose nine
functions collect **23 exact parameterized cases**, including adverse cases.
Its separate bounded report gate requires that complete finite identity set
with no duplicate, missing or unexpected case and zero skips/errors/failures.
The original one-node initializer gate is unchanged. The full module report
may retain only the two inert testcase properties already emitted by the
fixture; property values are never proof or diagnostic output.

Fixed CI notices appear only after each fail-closed gate succeeds under the
existing `sh -eu` owner. They qualify disposable test mechanics, not a paid
provider request, approved initializer commitment or production H1 admission.


## P1.T3.S1: close the actual executor's held YAML dependency

The real `-I -S -B` executor reaches routing-policy validation from lane
admission. The policy parser imports `yaml`, while the former held flat-module
closure supplied none. Native payload membership alone did not make the
already-reviewed PyYAML archive available to that executor. An exact-source
no-site discriminator reproduced this missing dependency; the earlier hosted
failure's masked primary cause remains unclaimed.

A separate `held_yaml` context in the existing `paid_yaml_runtime.py` now
validates the exact reviewed archive and provenance, their 19-member inventory
and 17 Python modules, and serves the pure package from memory. It never reopens
an archive path, changes `sys.path`, uses site packages, or falls back to a
binary extension. It rejects pre-existing YAML namespaces, checks the real held
source owner before member execution, after import and at exit, and removes
only its exact module and finder objects. Foreign replacements remain visible
and cause refusal, including `None` sentinels, equal-comparing foreign finders,
and duplicate references to an owned finder. Failed imports and interrupted
owner checks receive the same exact cleanup. The original Root-only `_read`
and `load_yaml` functions and their custody/cache behavior remain unchanged.

The three existing YAML assets join the held support and descriptor bindings:
47 support members, 48 with the existing optional artifact delivery member,
and nine source bindings. The three executable entry modules and three
initializer modules remain separate sets. Earlier 44/45 support generations
remain recognized by the publisher. Fixed whitespace-separated support
literals preserve the exact source sets while retaining the unchanged 100000
byte command ceiling; no dependency or binding is omitted.

The rebuilt native payload has 102 members and manifest
`0be933110a192f3855359eb72bfdfddb38e6dd581ed1d495d0caf7ea8a7a6aec`.
Only the initializer's actual entry pin, provider entry, model owner, support
publisher and YAML loader payloads change from the prior accepted union.
The native inventory, successor installer target and finite test pins derive
from those actual bytes. Historical paired-transition targets stay unchanged.

The private Linux fixture now provisions the same finite valid policy in its
snapshot and stable path and calls the real publisher in a fresh no-site
process using the actual held-source owner. It does not adopt pytest's ambient
YAML namespace or replace publication/admission validation. The canonical
model branch uses its explicit private gateway database and needs no invented
broker accounts or ledger activation files.

Fresh fixture failures emit a bounded PRIMARY annotation before final cleanup
can mask the original predicate. Only fixed public source selectors, typed
return/timeout/receipt states and a finite known refusal-prefix enum can leave
the fixture. Unknown, canary-bearing or terminal-control output maps to UNKNOWN;
raw output, messages, suffixes, paths, config and argv are never emitted. These
are newly generated facts from a new execution, not retrieval or reconstruction
of held historical raw logs. Settlement guards are unchanged.

Local no-site library/policy positives and adversarial refusals qualify the
source composition only. Exact new-head controlled Linux evidence must still
prove the original initializer once and all 23 provider-module cases, each
with zero skips/errors/failures, followed by all required checks and normal
independent protected delivery. No installed generation or runtime is changed
by this source repair.


## Fresh pre-model discriminator after 22e96341 CI

Run41231679937 at22e96341 passed the original controlled initializer gate,
but the provider module reported return78, no timeout and an absent model
receipt before final settlement refused. That fixed fact does not identify
an ACL or another root cause. Shard0 and exact-head CodeQL passed; shard1
also failed with no structured testcase detail or JUnit artifact. Preloading
ordinary YAML locally reproduces a separate new unit-test order defect:
the Root custody refusal correctly preserves an existing namespace, while
the test incorrectly required emptiness. The corrected test compares all
YAML keys and exact module objects immediately around the real refusal.
It neither removes nor adopts an ambient module. Its hosted-cause status
remains UNKNOWN until new qualified CI.

The positive provider case now first runs a separate test-only diagnostic
child with the original no-site flags and exact compiled bootstrap wrapped
by a finite trace. It intercepts the exact held `_run_executor` call before
its body and checks only request correlations, the real capture-owner
source contract and real model-command compilation. It does not enter lane
admission, create capture outputs, execute a model or consume provider
intent. The original paid command is then executed separately without a
prefix or source patch; the original1-node and complete23-node report gates
remain unchanged. The diagnostic never qualifies either positive proof.

Only an exact private stop after all checks and successful context unwind
can report READY. A missing canonical mode, None/non-tuple/wrong compiler
result, wrong-filename executor, early or wrong stop, suppressed/replaced
stop and cleanup failure refuse. Bounded allowlisted exception facts retain
a swallowed bootstrap failure without rendering its text. The strict parser
also rejects semantically inconsistent READY records. Shape validation is
not source authentication or a Python sandbox: the caller supplies the
ordinary fixed compiler output over the held source.

The existing bounded child owner limits acquisition, suppresses stderr and
reaps its own child. A malformed result becomes the fixed CHILD_REFUSED fact;
argv, source text, capability contents and acquisition exceptions are never
rendered. The two already-existing preflight/artifact refusal prefixes join
the finite enum, and the exact new Root-loader test has a static metadata
selector. No wildcard, dynamic path, parameter or namespace value is emitted.
The new source-only discriminator and its local surrogate-interpreter proof
do not recover historical raw logs or qualify the declared Linux selector.
Production payload/installer bytes and the100000 cap remain unchanged.

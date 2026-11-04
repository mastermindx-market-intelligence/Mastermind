# Ubuntu Grok account-to-host custody fence — source candidate

Status: BUILT_NOT_PROVEN. Operation: fabric-ubuntu-reliability-20261103-c4.
Original source owner: Mastermind PR #2007. No protected merge, native release
selection, host enrollment or paid worker has occurred.

## Purpose, design and refusal boundary

The incumbent broker labels Grok POOL_ACCOUNT=default even though each eligible
host reads its own ~/.grok/auth.json. A model list, broker alias or host
eligibility check does not prove the subscription for an unpinned worker.
The current connected fabric_request has no typed host selector.

The new fail-closed guard in candidate/native_remote.py reuses the existing
per-run hosts.json support-bundle registry, not a second identity directory,
scheduler, lease ledger, or control plane. Grok scope and Grok environment
both require an enrolled grok_account_binding matching the original selected
host, broker account, nonempty subscription_scope and the host owner's local
credential-file metadata. Missing/malformed binding, host/account change,
replaced credential, changed metadata, symlink or unsafe file mode refuses
before native provider execution. The environment path checks once before
creating ephemeral per-run configuration, then checks again before passing
the existing auth path to the provider.

A fixture-only registry member is:

  grok_account_binding:
    schema: mastermind.grok_host_account_binding.v1
    host: ubuntu0
    account: default
    subscription_scope: chris-main-grok
    auth_identity:
      uid: 1000
      dev: 1
      ino: 42
      size: 10
      mtime_ns: 123
      ctime_ns: 123

These numbers are fake test data, not host enrollment or a live credential.
No source task read, copied or transmitted the live OAuth credential.

## Explicit limitations

File metadata is NOT cryptographic OAuth account attestation. A trusted human
must first verify the intended subscriber in the original attended native login.
Only the original host-registry owner can bind the corresponding observed
local auth-file metadata and provide the independent subscriber/custody proof.
Token refresh or account replacement changes metadata and intentionally
requires requalification. No enrollment tooling is installed by this patch.

The bound host check occurs BEFORE Grok provider execution, but not necessarily
before the original broker acquires a lease. The native broker and typed Fabric
request still need a real host-to-subscriber admission check, not a host
preference invented inside a work packet. Until that exists, first paid-worker
and cross-host subscription-isolation proofs remain blocked. This candidate
must not be installed on unenrolled hosts because it will refuse Grok calls.

## Source/preservation and test receipts

- Forward runtime native_remote.py SHA256:
  8ea3fed6a49a54b83b161b2a1341bbd3d5ade34111f7a2b1735d3a8f32d4495b
- Accepted original Grok overlay untouched SHA256:
  388c412ee5803ac54356275323eba5fb0ee57519a8810490f81fe13977459f9e
- Separate historical predecessor fixture SHA256:
  a37bd58d7c972cabbeb0f247811a001d3fccb4d4e6b626417f06f4fb5e4962b0
- Existing builder produced 102 native members. Pre-integration manifest SHA256 (superseded by later composition):
  6e1b8022edd501af52daef9dc3a40913923cb1a26160eee2a571a8210081a3ea
- Pre-integration source inventory SHA256 (superseded):
  dc752d57ad2fc7efa1004ae1a1a1e35937767c8d2087fa37238143c71d4da2b9
- Offline current-source tests: 225 pass / 6 skips /
  0 failures / 0 errors, across 231 actual test cases.
  JUnit SHA256: 2def12e353bc98db2edd6694e1afe97fd01e9221c480fa78980cb4c02b4b6898
- Original immutable 95/102-member historical manifests and predecessor fixtures
  remain unchanged. The new separate fixture restores native_remote.py
  for the disposable historical test only.

## Remaining source integration and original runtime gates

A read-only merge-tree against newer protected source
1548ad095387838ff1a22133879d37b40fb180d8 found material
overlaps in builder and current-pin tests. This draft is on the original
owned source branch and must be recomposed with the latest accepted
picker, task, native manifest and source tests before remote publication,
current-head CI, independent review or native release. Do not repin
historical evidence to make tests pass.

Keep PR #2007 and PR #2008 unmerged, the latter Draft, and preserve
#1632 RELEASE storage restrictions, original Ubuntu2 EFFECT_UNKNOWN
holds, Ubuntu0/3 cache binding holds, Ubuntu4 qualification and
the original refused worker identities. Next source action: integrate
the accepted protected native movements in this same managed branch,
rebuild and retest, then use the normal protected PR source/review gates.
A true first Grok 4.7 worker still requires the typed broker host/account
fence and an independently verified subscriber identity.

## Protected integration (source-only)

A local two-parent integration with protected SHA 1548ad095387838ff1a22133879d37b40fb180d8 retains protected picker 747a55a50f..., sparse executor 7c7b94a974..., and Grok account guard 8ea3fed6a49.... The combined current manifest SHA256 is 44579551a1c01a25712d8e59441e88258780ef2fea082d17e7b2d2b501453587. The original historical test targets and immutable source fixtures remain unchanged. This is a local source composition, not a merge of PR #2007 into protected main, a runtime installation or a review receipt.


Integrated offline regression evidence: 225 passed, 6 expected Linux-only skips,
zero failures/errors across 231 distinct testcase records. The retained local
JUnit digest is 1c084a06ffb88518686d6fc4a1f7289af44ceb2d2d58cd6f2329d8703ba2baca.
Final combined manifest hash: 44579551a1c01a25712d8e59441e88258780ef2fea082d17e7b2d2b501453587.
Final combined inventory hash: 6a181c3866cf402965b05d36d6471f9b066985fb0f18b1f828ac486bf5840484.
Only native_remote.py, remote_sub_exec.py and pick.py use the exact
expected qualified forward hashes; other protected source is inherited.
No host registry binding has been enrolled, so the live Grok preflight
remains unchanged on the currently selected native generation.


## Broker and automatic-host prelease continuation (2026-11-04T05:36:50+00:00)

**BUILT_NOT_PROVEN; MISSION_COMPLETE=false.** This source-only continuation
extends the earlier provider-side credential guard through the *incumbent*
host picker and lease broker, not a new account directory, scheduler or
lease/identity plane.

- The original host picker now stages from candidate/host_pick.py and adds
  a Grok-only, fail-closed account-binding gate using the shared strict
  schema validator in native_remote.py. An unbound host is not eligible
  for automatic Grok placement; Cursor, GLM, Qwen and other modes keep
  their existing gates.
- The original lease_broker.py adds a remote-grok-only check *before new
  lease or waiter creation*. It compares the candidate host's existing
  trusted hosts.json binding with the original YAML account catalog
  subscription_scope. Mismatched, missing, stale, malformed or
  qualification-only hosts return host_account_unavailable. No cross-pool
  fallback or model substitution is introduced.
- The remote host still compares exact UID/device/inode/size/mtime/ctime
  against the enrolled metadata before CLI execution. Registry data
  and filesystem custody are **not** proof of an OAuth principal or
  actual model served; the Chairman's Chris Grok, Cursor, Grok Bot and
  Secretary2 capacity scopes remain distinct.

Current exact forward code SHA256:
  native_remote.py = da3a0ebd46357036b770aff40f2aab7ee4aa377e9aaebfb0a53d537d5962fa21
  lease_broker.py = ede49e98ef4df55bb561716c734aa79a3637b5257c79a6f757645791a870c846
  host_pick.py = 025ca9fea8ba96c4a66c26ad7be8c1e8b317e81101e67b5f6dc42c606a10fa6a

Source package retains **102 members**. Manifest SHA256 = f3c1157c94756eb67f72ca50200f6b4d489c5e418ca145ea8fe9eed6620474f3;
inventory SHA256 = 8d2ea87a750aedb2eb1f6a42f8cd89ba452735c4e8b7bc3003cacc16d13975f9. Previous accepted source and immutable
historical95/102 manifest targets remain untouched. A separate fixture
tests/fixtures/native-grok-prelease-predecessors-74efbfd1.json
SHA256 728d67e580b2598c609cbc28a23d53505f3d65b4680d7a0625c1b1eb16cc75a5 retains only the exact two public predecessor
code files from PR-head 74efbfd1; no secrets or provider credentials.

Offline integrated packaging/historical suite: 236
passed, 6 expected Linux-only skips, 0 failures,
0 errors across 242 actual testcase records; JUnit SHA256
1965d2183857f3d95fe518716b2715d0f1a36725354c2dbfaf3a3689a167f881.
Separate broker/host account-adjacent suite: 115
passed, 0 skipped, 0 failures/errors across
115 records; JUnit SHA256 ac94ea9026295268385b2b387d7527cf06347d1aa64ccf85d3ef2b44021d900b.
The JUnit files under /tmp are local evidence only, not published attachments
or live production receipts.

**Original runtime configuration gate observed read-only:** active M2 pool
status identified selected native generation
8cefc4b27b2036f86bcec1d626e864f45f792e2c290ab8de56fbde89f78ac94a.
Its existing Grok account catalog has one account but **zero populated
subscription_scope fields**; Ubuntu0-4's existing hosts.json entries have
**zero Grok account bindings**. No live config/credential bytes were edited.
The new fail-closed source would refuse all Grok remote workers until the
original provider-account and host-registry owners enroll and independently
attest the correct Chris subscription. Do not select/publish that generation
before gated enrollment, non-author review and real-path qualification.

**Next action:** publish this same existing PR #2007 source revision through
normal non-merge source gates and inspect its exact-head CI. Then obtain
original-account-scope and per-host registry enrollment through the existing
configuration owners with a retained human-verified account identity, and
prove one real Grok 4.7 worker/return through the admitted native route.
The PR #2008 independent Ubuntu4 writer, original four Ubuntu2 effect-unknown
markers, Ubuntu0/3 cache effect hold, and #1632 RELEASE storage restrictions
are unchanged.


## Grok task-class and broker-host bypass hardening

**Source-only correction after the previously green e142 head.** The first
prelease implementation limited the broker fence to task_class=remote-grok.
A later hardening candidate limited it to remote-grok or host differing
from this_host. Both were insufficient: isolated original-configuration
tests proved an **unbound Ubuntu1** account could obtain a disposable
Grok lease by presenting task_class=audit; a caller-controlled broker
host identity of ubuntu1 could also make that unbound host look local.
No production leases or workers were created in these falsifying tests.

The final guard is therefore **unconditional for every pool=grok
lease**, regardless of task class, provider model or asserted broker host.
Only an original-host-registry binding matching the incumbent account
catalog subscription scope may grant a Grok lease. This deliberately
blocks unbound local/M2 Grok usage until that distinct local principal
and host are enrolled; it never substitutes a Secretary2 token or
silently changes a paid provider. Cursor/GLM/Qwen/other pools remain
under their existing unchanged admission policies.

Added permanent tests for caller-controlled alternate task classes,
claimed local broker host, and invalid remote host. Real original M2
configuration was also exercised against eight pairs of requested
host/task class/broker identity using only disposable fixture SQLite:
all qualified Ubuntu0 cases admitted, all unbound Ubuntu1 cases
refused host_account_unavailable; no production lease, provider
inference or host credential bytes were accessed.

Exact revised native source SHA256 lease_broker.py:
  a83a2fd667b1b6055d8aa07bb0a9f9f438baf6d6ca610c11256eb6faf7c27b3e

Combined 102-member source package SHA256:
  manifest be7b70d73ef45640777b1677f3ab4dae8caed6d3ece0292aa9c1c6e07615f8fe
  source inventory b31fc69a205d3f4554539f29f0164149a9ae674e2c26afa36d18ba4df466d638

The former e142 hashes and green CI belong to the **previous**
candidate and are retained above as historical provenance. They do
not qualify this revised broker source. Historical95/102 predecessor
fixtures and manifest hashes remain unchanged. Current source tests,
hosted CI, non-author review, protected merge and native publication
are separate gates. No live generation or stored credential was changed
by this source repair. The original M2 policy has already enrolled
Chris Grok Ubuntu0 only, and Ubuntu1-4 remain held from Grok AUTO.


Final offline regression receipt for unconditional Grok grant fence:
355 passed, 6 expected Linux-only skipped, zero failures/errors among 361
actual testcase records. JUnit SHA256:
f6fb8f18a61c0a637c3289822e73659614a5e560e957dd7d71e1d6ad21d711a4
Local original M2 test file /tmp/mmx-grok-all-lease-fence.xml only (not a
public attachment). The historical source/manifest fixtures were preserved.
Adversarial original M2 account/registry tests across task classes
remote-grok and audit and broker-host identities m2studio/ubuntu1 separately
verified eight temporary-DB cases: qualified Ubuntu0 accepts, unbound
Ubuntu1 denies across all combinations. No production lease or provider
worker was run by those tests.
This change requires NEW current-head hosted CI and independent review;
prior green CI on e142376f does not qualify the successor candidate.

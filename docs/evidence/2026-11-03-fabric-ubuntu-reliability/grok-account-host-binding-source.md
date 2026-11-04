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
- Existing builder produced 102 native members. Provisional current manifest SHA256:
  6e1b8022edd501af52daef9dc3a40913923cb1a26160eee2a571a8210081a3ea
- Provisional source inventory SHA256:
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

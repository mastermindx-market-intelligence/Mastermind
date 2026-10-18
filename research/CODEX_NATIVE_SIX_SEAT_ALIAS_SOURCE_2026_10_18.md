# Native Codex six-seat selector alias integration — source-only

Mission: Chairman's four personal Pro seats (C1-C4) and two independently
governed Business seats (B1/B2) are candidates for native Codex frontier
planning/orchestration. The current installed M2 Fabric kit recognizes only
C1-C4. This is a finite extension of the existing advisory account selector
and native profile, NOT a new scheduler/identity/admission/control plane.

## Source and custody

- Original existing selector PR: #1365, exact predecessor
  4c27a8d3a4dab635b5301e3f8fda84576b711b9f.
- Existing M2 installed non-git kit, files:
  codex_pool_policy.py, codex_native_profile.py,
  tests/test_codex_pool_policy.py, tests/test_codex_native_profile.py.
- Exact source preimages and postimages are sealed in
  ops/native_fabric/patches/codex_six_seat_alias_20261018.manifest.json.
- Existing advisory policy and installed model/host/broker selection
  have NOT been modified or installed.
- A source-only patch adds B1/B2 as recognized candidate aliases,
  and updates the old empty-directory test for six private homes.
  The profile continues to return NOT_ENROLLED without auth; any verified
  binding still returns dispatch_ready=false until native relay proof.
- Source verifier only reads the installed preimage, tests the patch
  in a disposable directory, and demands exact unchanged source readback.
  No tokens, account IDs, device auth, host installs, lease, model requests
  or provider traffic are permitted.

## Tests

- RED before change: 4 failing, 2 passing targeted tests because B1/B2
  were unrecognized and the alias count was four.
- GREEN after change: 26/26 combined existing selector/profile and
  new six-seat tests passed on M2, provider free.
- Exact patch apply, expected postimage hashes, no original source mutation,
  Python compileall, git diff --check all passed.
- Verify independently:
  python3 ops/native_fabric/verify_codex_six_seat_source.py
  --source-root <EXACT_TRUSTED_M2_FABRIC_KIT_PATH>

## Native observed seat status

C1's managed ChatGPT account ID digest matched the existing private
Switcher ChatGPT1 account_id. Native display email differed; do not use
display email as the authorization authority. With that same identity,
M2 Codex CLI 0.159.3 native model/list returned gpt-6-astra and
gpt-6.1-sol among seven visible models. An earlier native rate-limit
read reported Pro, primary 100% / seven-day window, secondary explicitly
NOT_APPLICABLE. Exact identity and model metadata were verified without
printing emails, identifiers, hashes or credentials; private App Server
process-group cleanup succeeded. No model turn or reservation exists.

C2-C4 remain unenrolled and B1/B2 are not authenticated or registered
in the installed kit. These six labels are candidates, not six usable
workers. Business plan entitlements and model availability must be
observed independently on each authorized seat, with a separate quota
window and original owner.

## Release and acceptance

1. Reconcile existing source/installer owner against the exact preimage;
   do not blindly apply to a changed installed kit.
2. Independently review exact PR head, run hosted CI, and install through
   the existing source owner under accepted authority.
3. Enroll remaining seats via their own official native OAuth and prove
   each subject/plan/model/quota; never move credentials between homes.
4. Integrate qualified per-seat observations at the *existing* broker
   atomic claim/START check. Advisory choice is NOT a lease or permission.
5. Prove one original-parent worker job, retained result, review and
   acceptance; then expand concurrency based on observed sustained limits.
6. Preserve C1 home and existing affected/unknown effects; no duplicate
   retry, controller, identity ledger, queue or account switcher.

Status: SOURCE_CANDIDATE_ONLY / NOT_INSTALLED / NOT_SIX_SEAT_READY.


## October 18 successor: provider-free Business member inclusion gate

The preceding B1/B2 unenrolled status in this source note is now superseded.
All six private M2 native homes were authenticated by the Chairman. C1-C4
native account subjects matched their intended Switcher labels and listed both
Astra and Sol 6.1. For B1/B2, the local OpenAI ID-token claims establish
two DISTINCT users in the SAME Business workspace (chatgpt_user_id differs,
chatgpt_account_id matches); B2's user ID also matches C2 Personal, while
its Business workspace/account ID differs from C2 Personal. Native
account/read email is not a reliable per-user discriminator in this case.
No raw names, emails, account IDs, hashes, tokens, or credentials are in
this repository.

An actual provider Business plan/seat-type response has NOT yet proven the
Premium-vs-Standard included entitlement for either member. Native quota
observations reported each Business home as 100% remaining for a seven-day
primary window, but do not prove that shared workspace credits are independent.
Existing quota comparator PR #1585 added separate member ID matching for
same-workspace comparisons; that source change is not installed.

The originally published four-plus-two alias-only patch is now extended in
the SAME source candidate. It adds model- and quota-context-dependent advisory
eligibility to codex_pool_policy.AccountObservation with optional hashed
workspace and member IDs, an explicitly owner-qualified entitlement class,
and visible model identifiers. A Business seat is advisory-selectable only
with a business_premium_included entitlement, well-formed separate workspace
and member hashes, a fresh future quota horizon, active subscription headroom,
an explicitly requested model present in its qualified model set, and an
available broker slot. An unknown Standard tier, missing member ID, missing
model list, or business_workspace_shared_credits class cannot qualify.
Two aliases with an IDENTICAL (workspace, user, entitlement class) tuple are
both excluded, without starving an unrelated eligible account. DIFFERENT
members of the SAME Business workspace are deliberately eligible separately
when their exact seat allowance was independently qualified. One user in
Personal vs Business scopes stays a different quota context.

RED-first proof: 32 parametrized new Business/model/duplicate cases failed
against the alias-only predecessor (construction lacked identity fields).
GREEN after correction: 58/58 combined existing selector/profile and new
Business scope tests, plus the existing source bundle tests independently.
The digest-sealed replay helper adds the new Business cases, requires
byte-exact installed preimages, verifies the resulting source/postimage
hashes and checks that installed source remained unchanged. This remains
SOURCE ONLY. No current upstream Runtime or native provider grants emerge
from fabricated synthetic metadata, and no broker/runner/launcher is changed.

CRITICAL PATH STILL OPEN: the currently installed legacy remote
native_remote.scope() expects codex-native/default and refuses
M2-local host placement, while enrolled Ubuntu hosts lack an allowed
codex-native execution mode. Thus there is currently no lawful path from
the six M2 account homes to those legacy remote runners. Do not add six
broker slots or copy credentials onto Ubuntu. Integration must use the
incumbent Executive worker broker's isolated per-worker on-host process
realm and capability/admission checks, with exact seat identity and
original-parent acceptance. Existing Executive worker slot catalog currently
defines only codex-pro-01/02/03 plus the distinct company slot; it is not
six installed subscription processes. A future source owner must reconcile
the actual runtime's reviewed OS UIDs, model entitlement, issuer quota scope,
release/merge readiness, and the previously accepted platform gate.


## October 18 bounded native observation to selector bridge

The incumbent installed Fabric kit previously had only a pure ranking function
with hypothetical AccountObservation rows; the separate accepted #1585 native
Codex observer returned sanitized quota/account metadata in a different shape,
and there was no direct consumer projection. The same original source candidate
now adds project_native_account_observation as a PURE translation helper inside
codex_pool_policy (not a new state, identity, quota or scheduling owner).

Source contract:
- Takes only a sanitized successful native observer result, a qualified
  account-binding boolean and model list, owner-qualified entitlement class,
  and current existing broker active-leases/cap. No credential reads or model
  queries are performed in this module.
- Requires NATIVE_READS_COMPLETED, api_fallback=false, a proven empty private
  App Server process group, native managed ChatGPT, available capacity, exact
  codex limit identifier, proper account ID (and Business member ID), expected
  personal or Business plan, <=10-minute observation age, coherent used and
  remaining percentages, and future reset horizon.
- Explicitly requires exactly ONE observed quota window and its sibling
  explicitly NOT_APPLICABLE. It refuses missing/unknown/contradictory or
  multiple windows rather than silently discarding a binding rate limit.
- Passes reset_credits=None regardless of observed credit inventory. No
  paid provider reset or promotional refill is requested, inferred or minted.
- Business included-seat premium validation and model-list issuer binding
  MUST be produced by the authorized existing owner. A field supplied to
  a pure function is not an administrative entitlement or runtime proof.
- No account is ever granted without the incumbent broker's actual atomic
  provider+seat+model+host claim and the separate START/return acceptance path.

RED-first: 14 cases failed while this translator was absent; GREEN after
source change: 73/73 combined old selector, six-seat aliases, business
identity safeguards and new native-result projection cases. The digest-sealed
offline verifier copies the exact installed preimages, applies the patch
only in a disposable directory, verifies postimage/test digests, executes
all tests, and proves the installed M2 kit remains byte-for-byte unchanged.

The upstream source status is only DRAFT/SOURCE_CANDIDATE. Legacy M2 broker
still uses codex-native/default cap 1 and its Ubuntu lane launcher remains
ineligible for M2 account homes. The actual Executive worker slot catalog
has codex-01 and three personal Pro definitions; its read-only status
reported every reviewed slot NOT_READY with missing provider homes, and
the Executive reader replied backend_unavailable. A valid model list and
this pure bridge do not cure those host/realm/acceptance gates.


## October 18 same-private-session native model binding

After the original #1585 native observation owner added a bounded optional
model/list read inside its existing App Server process, the original #1365
pure project_native_account_observation is hardened to require the exact
sanitized model_visibility shape: OBSERVED, model/list source,
admission_granted=false, and no unknown, duplicate or malformed identifiers.
Only the two approved Astra/Sol identifiers may survive projection. A caller
may specify a strict subset to narrow execution but cannot add a model that
the native App Server did not return. A missing/failed native model read
makes this projective sample ineligible; the native owner separately retains
any already observed quota evidence for refresh analysis.

RED-first: 9 model-catalog provenance/negative cases failed against the
predecessor projective source. GREEN: 82/82 combined selector, profile,
Business identity/entitlement and native-quota/model projection tests pass.
Exact installed-source replay and hosted CI need independent confirmation.

Real provider metadata probe via C1's private native App Server:
NATIVE_READS_COMPLETED=true; model visibility OBSERVED=true; separate
model identifiers Astra/Sol 6.1 both present; provider-home private process
group cleanup true. The identical sanitized sample passed into current
project_native_account_observation without separate caller-provided model
set. It returned only the observed two-model set. Broker seat cap=0, and
select_account(requested_model=gpt-6-astra) returned None, as required.
No paid model turn, account rotation, work dispatch, quota debit, reset
credit, local credential extraction, broker mutation or capacity enrollment.

This remains a source-only proof of a model/subject eligibility observation.
The incumbent Executive worker source config/OS principal and launch path
remain NOT_READY; exact START-bound account/host/model enrollment and a real
parent-accepted worker result are outstanding.


## October 18: subscriber-collision guard after real six-seat native identity read

A live read-only same-private-App-Server metadata pass on all six authenticated
M2 homes confirmed four native Personal Pro plan responses (C1/C2/C3/C4),
two native Business plan responses (B1/B2), Astra and Sol 6.1 visible on all,
quota AVAILABLE_OBSERVED on all and process cleanup proved for all. The
sanitized relationship test (no account IDs or credentials emitted) showed:
B1/B2 use the SAME Business workspace but DIFFERENT member identities;
C2 Personal/B2 Business are the SAME user with DIFFERENT workspace IDs.
Those observations are not signed Premium seat-type entitlements, root OS
principal enrollments, leases, or proof of authorized model turns.

A security gap surfaced in the source-only ranker: Personal Pro aliases
carrying the same underlying subscription workspace could be independently
ranked when a missing/different user ID or entitlement_class prevented the
old workspace+user+tier collision test from joining them. The existing pure
selector now uses a Personal workspace-level collision key, and a Business
workspace+member key. Untrusted category strings never split one included
subscription into multiple quota balances. A shared workspace with two real
Business members remains two candidates only after each member's independent
Premium entitlement and exact broker admission are proven.

RED-first four candidate tests failed on original source; GREEN 88/88
combined native account/projection/six-alias/collision tests. Byte-exact
installed-source patch, manifest, source + test digests and regression guard
must pass at committed head; hosted CI/review remain independent gates.

DO_NOT_REDO: original #1585 native observer and #1615 inert C4 worker and
#1618 bounded-worker message isolation remain separate accepted candidate
work. No change to installed Macro Fabric broker, profiles, processes,
credentials, root-controlled home or application/OS version.

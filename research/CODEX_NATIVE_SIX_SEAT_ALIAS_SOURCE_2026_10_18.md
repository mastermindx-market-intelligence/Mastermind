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

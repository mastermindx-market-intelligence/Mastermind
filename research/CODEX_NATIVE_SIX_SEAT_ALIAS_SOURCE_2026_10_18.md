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

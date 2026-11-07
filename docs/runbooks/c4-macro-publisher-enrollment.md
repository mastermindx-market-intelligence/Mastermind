# C4 Macro publisher enrollment and merge capability

## Owner, scope and acceptance

Chairman assignment: restore a Macro-enabled, merge-capable Studio Direct publishing connection for the blocked international-country cockpit session and prevent the same late publication discovery in future sessions. This is a bounded dependency under Mastermind #917, not a new service, publisher, runtime, permission store or workstream. The current session owns this C4 repair; it does not acquire the original website's writing surface or C2's held source.

Operation: `c4-macro-publisher-enrollment-20261103`. Procedure pin: `b4a5a8925c6c1412dac67ba296cf65ee81c4d4c8`, skillpack 1.0.1/bootstrap 1. Existing parent task tree: `docs/superpowers/plans/2026-11-02-delivery-turnaround-execution.md` on #1957. Preserve that owner's live edits and #1979's original source carrier.

DONE_WHEN: the exact C4 installed owner supports explicitly enrolled Macro plus the reviewed two-parent commit contract; its actual ChatGPT catalog advertises `repository` and nested `merge`; the original Macro operation is readable through its original publishing route without replaying its rejected publication; and the website delivery owner can continue current-head review, normal release, data refresh and public-route proof. Website deployment is not claimed by installing a publisher.

## Verified diagnosis, 2026-11-03 UTC

C4 is running from `/Users/chriswong/.local/share/studio-direct-mcp/private/chatgpt4`, label `com.mastermind.studio-direct-private.chatgpt4`, port 45024. Its eleven-module fleet v0.1.10 generation lacks `workspace-access.mjs`. Its configuration enrolls only Mastermind. Its current ChatGPT publisher tool definitions expose neither repository selection nor the two-parent merge input.

The installed `mmx-workspace` launcher already binds Mastermind, Macro and Terminal. Reinstalling that allocator would not repair the missing gateway grant and would duplicate work.

C4 has a completed original `state/native-pool-pin` transaction. Result `APPLIED`; plan SHA256 `4732de6c370ca3385d17749e411f634d149b7701971219baea65707d6c069818`; manifest postimage `168bb25afd7d710799fb86f8912389d49c86371c107ee9544d65fdc2b9d390e2`; config postimage `f02e385e234f7f88619058485b61f17834d3cfc33896ce3f5606bd64fcecce21`; selected pool bridge `bc0b3559392a07f3d4f7109455765c14dbc4dc946f6cb5a788e547ae179dbf0f`. All seven original transaction files must remain immutable. Generic restaging is deliberately refused after this pin.

C2 PR #1979 head `b742aa06ffb9d2c7541f7aa5dbfd2df0d3eb21bf` is a distinct, held two-module successor for an already enrolled seat. Its subsequent target-generation-freeze test edit was explicitly safety-denied in its original workspace. This C4 change neither repairs nor replays that denied C2 edit, does not touch that workspace, and does not depend on #1979 being accepted. Its published architecture informed the same-owner design; the C4 implementation reuses protected master's native-pin primitives directly.

## Source implementation

`private_service_pin_enrollment.py` is an adjunct to the existing private-service/native-pin owner, exposed as `private_service.py native-pool-pin-enrollment`. It is not another installer service. It supports read-only `preview`/`status` and explicit exact-plan `apply`/`reconcile`, for C4 only.

The fixed generation replaces `gateway.mjs` and `git-publish.mjs`, adds `workspace-access.mjs`, and preserves the other nine modules. It changes only `gitPublish` and adds `repositoryWorkspaces` for the existing canonical `mastermind`, `macro`, `terminal` aliases. Fleet, Paper, authentication, tunnel, concurrency, backend, Node, dependencies, plist and the original native-pin evidence remain unchanged. No lifecycle, Git, network fetch or app-permission action is part of the transaction.

The implementation authenticates the completed original native pin with the native selection owner; uses the existing lifecycle and native-publication locks; proves the service is stopped before writes; durably records intent; commits modules, configuration, then manifest; and writes the completion result last. Only the exact ordered prefix of this transaction can be reconciled. Foreign bytes, modes, symlinks, source changes, unknown accounts and source generations are refused. Incomplete or missing completion evidence blocks startup. Preparation interruptions retain their original transaction and refuse automatic replay; incomplete preparation requires owner reconciliation rather than deleting evidence. Any failure after a write is reported as `EFFECT_UNKNOWN`, including context-exit failures. The fixed target and configuration transformation do not depend on future generic upgrade constants.

Frozen target SHA256 values:

| File | SHA256 |
|---|---|
| gateway.mjs | `17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30` |
| git-publish.mjs | `f67119198a0e63c34ae148633402a7ec3ab351ecf7f40a24bdc355b9890f8a2c` |
| workspace-access.mjs | `e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5` |

## Verification receipts

Observed at 2026-11-03 06:11 UTC, before source publication. These are source/preview receipts, NOT installation or consumer acceptance.

- **336/336 installer tests PASS**: `python3 -m unittest discover -s . -p 'private_service*test.py'`. This includes **41 new C4 enrollment tests**. The earlier 333-test run found the expected CLI-command-set regression; the explicit command-set test was updated, then the entire suite reran successfully. No failed run is presented as a pass.
- Test log SHA256: `8f58dd0aeab2fbede4b780bf07403907ea58279d1245d55428f115ead4d5dcf9`, original `/tmp/c4-enrollment-all-tests-r2-20261103.log`; retain with this operation's host evidence.
- Actual C4 read-only enrollment preview: **NOT_APPLIED / PREVIEW / zero installation writes**, plan `53d8fc7982d9dab6b42e1c2ed7687e65137b4ad4ac2bf204d7de1f11a7652029`. It authenticated the actual original native owner, installed configuration and runtime seal while C4 remained running.
- Exact target-module catalog assertions PASS: closed repository enum includes all three canonical aliases; commit input has the two required merge fences `expected_protected_base_sha` and `expected_tree_sha`; undeclared properties are refused; repository discovery is read-only. No publication tool was invoked.
- Actual twelve-module compatibility fixture PASS: nine unchanged C4 code modules plus the three fixed targets, using C4's unchanged dependency tree. The v0.1.10 gateway successfully resolved the proposed three-repository configuration. No gateway listener, backend, worker or service was started by this fixture; no auth material was copied.
- `git diff --check` PASS. Code identity at the tested source: private_service.py `ddc8e7b2a0d2267e5f7f076eead85bd1394c8b6a50aa62c20d565dcc0a2691f4`; new owner `63e62b54dd8d4f2e5a5f5b7e6958164a5a6dc746eca53ecfc46540862b7ad694`; enrollment tests `1a99300a4d22c61041a557756ec6296387e1b7716822b6f17ebd1e1660a44380`; existing CLI test file `a9d4bdb4bd02cd91f09f7323dd81a3a4a4cc4934c02f1c6741df8242a6070fe1`.

Source-only payload: `/Users/chriswong/.local/share/mastermind/evidence/c4-enrollment-20261103/r1-payload`. Compatibility fixture is a sibling `r1-compatibility-fixture`. Neither is a selected runtime or a release authorization. The gateway payload matches the exact already-reviewed C2 compatibility code digest; only implementation bytes were copied, never another account's configuration, authentication or credentials. The publisher and adapter match protected master at the procedure pin.

## R3 command-budget correction and publication recovery

The original source commit attempt returned `TYPED_GIT_PRECHECK_REFUSED / NOT_APPLIED`; native HEAD remained `d858990aa24d11979303e46eb0f51b03569bbdef`, with exactly the six intended dirty/new files. The subsequent typed read-only status also refused. A bounded read-only call to the original `mmx-workspace status` succeeded with correct original binding in **24.256 seconds**, exceeding the installed publisher's **15,000 ms** per-command limit. This is direct deadline-mismatch evidence, not an observed authorization denial or proof of the gateway's swallowed exception.

R3 therefore preserves the exact 15-second original preimage but sets the enrolled `gitPublish.commandTimeoutMs` to **45,000**, matching protected source's existing bounded C2 timeout policy. Push remains **60,000 ms**; no retry, permission, destination or credential policy is relaxed. This fixed C4 generation does not depend on the moving C2 constant.

The updated source passes **336/336 tests** again (95.620 seconds), log `c4-enrollment-all-tests-r3.log` in the retained evidence directory, SHA256 `ef932ce7b54bc46a188200ed860e2c1ccc15a6b5e5fa9403cfa25315a10bec1e`. Current owner SHA256 is `636e81bfb93e879e1ac52989424b8934f1bd7ba12a871f3c1a521c0da91203f9`; current enrollment-test SHA256 is `43243bb2350a21af2a099ea3df2dab173ea6da292bd96326f122acb1df4b0de8`. Other source-code hashes above are unchanged. The actual read-only C4 preview passed again with zero installation writes and **current plan `ed70c31ad3942a1d803dd3584ed09e8b9b3c9799793a67346e90ef7cbd843a6f`**. It supersedes the earlier 15-second target plan; do not apply the old plan.

A subsequent read-only diagnostic invoked the **same installed publisher code, same installed configuration, same 15-second deadlines, original operation and exact same source binding**, instrumenting only subprocess durations. It completed successfully: native workspace status 4,368 ms, Git checks 52-361 ms, exact remote readback 1,301 ms. Local and remote HEAD were both the original `d858990aa24d11979303e46eb0f51b03569bbdef`. This proves technical recovery without changing the gateway, permissions or carrier, and allows one reconciled attempt through the original typed publisher. It is not a claim that intermittent latency is permanently fixed before R3 is installed.

Independent same-app UI readiness was requested from Grok Secretary in the authorized channel, thread `1793687003.507719`. Only exact account/app binding and supported refresh control were requested before installation; no app recreation, permission loosening, alternate source publication or service mutation was delegated. A sent message is not pickup/start evidence.

## Task tree / release frontier

| ID | Scope | Status / exact next action |
|---|---|---|
| C4.1 | Verify installed enrollment, source generation, original native pin and client schema | Proven diagnosis; do not redo without drift |
| C4.2 | Implement the existing owner's C4 enrollment successor | Implemented and locally tested; actual installation preview qualified; independent review not yet accepted |
| C4.3 | Independent exact-head review, hosted CI, protected release, one-seat installation | Review this source, resolve findings, and use the normal non-author protected release. Do not self-approve/merge or modify held PRs |
| C4.4 | Verify installed catalog and refresh the same ChatGPT app's action snapshot | After C4.3, refresh through the exact app's supported account/admin controls and read back actual exposed repository/merge schemas |
| C4.5 | Return capability to the original website owner | Read-only status for the original Macro operation through the now-enrolled native tool; preserve its branch, work, review and unknown-effect history |
| C4.6 | Prevent late capability discovery | README now requires repository and merge capability checks before substantial work and separates installed enrollment, implementation and client-snapshot gaps |

## Installation and app-refresh handoff

Do not install from an unreviewed worktree. After exact-head independent review, CI and protected release, retain that accepted source revision and its adjunct owner module together. Recheck only drift-sensitive installed facts and active writer/effect state. The expected preview plan above is not authority to ignore changed installed state.

Use a verified independent maintenance carrier that survives stopping C4. Remote Desktop Commander currently exposes online `m2studio`, device `3f5ce987-e3eb-40a3-af9f-4b0ae54919cc`; a targeted read of C4's manifest succeeded through it. This proves read access, not an untested stop/apply/start action. Do not stop the gateway serving a mutating call without an independent return path.

Through the existing private-service owner: obtain the exact read-only preview; stop only C4 after active effects are reconciled; apply the exact preview plan and source hashes once; read the same transaction's status; start C4 through the original owner; verify health, preserved fleet/Paper capabilities and the actual live tool catalog. An uncertain return must be reconciled at this same transaction, never restaged through a different account. Generic-restage refusal stays intact.

OpenAI's current custom-MCP documentation permits existing-app tool-list refresh for Business/Enterprise/Edu administrators; it no longer mandates recreating a Business app. Personal-account controls still need direct verification. The README records official source links. Preserve the same app identity, account, connection, audience and unrelated actions. A gateway restart, OAuth reconnect or fresh chat alone is not proof of snapshot refresh. No app recreation or permission-mode loosening is authorized by this change.

The Browser connector currently reports that the originating extension/browser context is missing. Its exposed surface is read-only; Plugin Creator/Management do not expose an MCP tool-snapshot refresh action. This is a precise remaining UI/control-path gap, not evidence that C4 must be recreated. The authorized app administrator or an already-authorized UI operator must use the exact account's supported refresh/review control after the server update, then read back the native catalog.

## Effect and safety continuity

Original website operation `intl-country-cockpit-20261018` and branch `sol/web-intl-country-cockpit-20261018` remain untouched. Its earlier pre-effect publication refusal has not been retried. No website commit, push, merge, data refresh or deployment is claimed.

A shell-based source-location diagnostic earlier in this repair session was explicitly safety-blocked before execution. That exact request was held, not retried or delegated. Distinct native configuration reads, managed source acquisition, source editing, tests and Mastermind publication succeeded; they do not reauthorize the denied action.

Fabric source request `c4-publisher-source-20261103-01`, root `c4-macro-publisher-enrollment-20261103`, was ultimately recorded `REQUEST_REFUSED_BEFORE_LAUNCH`, with execution absence proven by the native status and `same_run_replay_allowed=false`. Controller 37602 exited with adapter code 75; no worker START or source result occurred. No replacement implementation worker was launched. The parent performed permitted direct source work, which still requires an independent non-author review. The earlier optional-turn-preflight observation was reconciled separately before the one same-run request; it is not permission to replay this later refusal.

No installed C4 files, original native-pin files, app grants, sibling gateways, credential stores or original website effects were changed in this source phase. Delivery, source qualification, review, merge, installation, client adoption and website acceptance remain distinct.


## Native selection moved forward after the original C4 preview (2026-11-03)

The accepted R3 preview remains the *same C4 source/manifest target*, but a
subsequent independent M2 release preflight returned
`NATIVE_PIN_ENROLLMENT_OWNER_REFUSED` / underlying
`NATIVE_POOL_PIN_SUCCESSOR_REFUSED` **before any installed write**. The
canonical native-code selection was already at sequence **26** while the
original immutable C4 pin was selected at sequence **24**. Installed C4 stayed
running with original 11-file manifest `168bb25a...`, config `f02e385e...`,
and no enrollment transaction. This is a real upstream native pointer change,
not a source authorization to restage, stop or apply a stale plan.

A *distinct source candidate* under the same `private_service._pin_native_context`
owner now admits forward selected generations **only** for the exact C4
historical successor digest
`77c2c136852a783a1e2572c145af7536ee6cd0d7f443daa4c09795c333fd3dc7`,
the frozen generation `28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce`,
and original selected sequence **24**. A later current selection must have
higher sequence, a distinct prior generation, two genuinely verifiable current
and predecessor published native generations, and unchanged original bridged
launcher ingresses. It retains the original native pin transaction and all
bytes, source/manifest expectations, native publication lock and selected
generation **readback** across the existing two proof calls. An existing
`PREVIOUS` or exactly `SELECTED` state retains its original behavior.

**Scope honesty:** the native owner's `CURRENT.json` exposes only its
immediate previous pointer, not a verifiable full chronological chain back to
the old C4 selected generation. This candidate therefore verifies the actual
native owner's *current published selection*, its immediately previous
published generation, and the intact original historical pin/bridge; it does
**not** claim an archival proof of every intermediate native generation.
The distinct authenticated selected-generation owner remains authoritative.
Any unknown account, mismatched original successor, rollback, invalid
generation, foreign bridge, or selection that moves between the two proofs
refuses closed. No generic native pool selector, retry mechanism, publisher,
application privilege or installed runtime was introduced.

The source-only candidate ran the same installed C4 read-only
`native-pool-pin-enrollment --operation preview` after this change and
returned `PREVIEW / NOT_APPLIED`, zero writes, **the same exact planned hash**
`ed70c31ad3942a1d803dd3584ed09e8b9b3c9799793a67346e90ef7cbd843a6f`
against the now-current sequence 26 selection. Hermetic subprocess
negative-case tests cover account, digest/target, rollback, unverified
current/previous, self-pointer, foreign bridge and pointer changes; the
full `private_service*test.py` suite passed **369/369**. These are qualification
facts, **not approval to install the new source candidate**.

**Release order remains mandatory:** independent nonauthor review on the
actual source commit, hosted CI, normal protected merge, accepted owner source
readback, fresh live C4 preview and current native pointer proof, exclusive
C4 idle/stopped-service maintenance, single original transaction CAS apply,
same-transaction reconciliation, start, installed tool catalog and actual
ChatGPT4 app snapshot refresh. Re-run the preview at installation time; do
not blindly reuse the earlier plan, relax pin policy or replay any denied
legacy Macro/C2 publication.


## C4 publisher recovery pair — 2026-11-07

Persistent Sector Leadership ([Mastermind #1202](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1202#issuecomment-6695716256)) needs the incumbent publisher's guarded reconciliation contract. The installed C4 publisher lacks it, and its workspace adapter rejects the corresponding arguments. The new source successor extends this same enrollment owner; it introduces no account, lifecycle, Git publication, retry or queue owner.

Current operation: `persistent-sector-leadership-publisher-20261107-c4`, source base `5f8c13da926011fb5fdc8cea21287b532ac968db`. The original paid C4 source run ended in a root-verified provider error without an accepted source result; the assigned parent completed this bounded recovery. The returned paid adapter leaf is `psl-publisher-adapter-20261107-c4`, commit `e5446e3a2d8a274d3a4d94bc63f2c100678e9075`. Qualification evidence belongs to this source generation; prior installer runs above do not qualify these changes.

The successor requires the completed original native pin, enrollment, Paper-v20 and fleet-status transactions. Its exact predecessor manifest is `c440f2ba4c0bdfbba3aff86303a483e3ab42a1093f330ba9e3fd6c6f923783b4`; config remains `f06dc822015fc11f34d7e1142bdf1b016cb985af701ba929f33b313ff3a570df`.

| Module | Preserved predecessor SHA256 | New C4 SHA256 |
|---|---|---|
| git-publish.mjs | `f67119198a0e63c34ae148633402a7ec3ab351ecf7f40a24bdc355b9890f8a2c` | `a8ce5f25f4fc606e294f58de5748a73a36de5178d8e30b27132c3660e161d58e` |
| workspace-access.mjs | `e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5` | `290cf5e961db2fa30e37c32da473595518df0ded80fc850a84cf5bdae1a1ec3c` |

Generation `c4-publisher-recovery-20261107-v4` uses the existing `native-pool-pin-enrollment` CLI and a distinct retained `native-pool-pin-enrollment-publisher` transaction. The two source modules are required together. The only legal write prefixes are `OLD → PUBLISHER_ONLY → MODULES → COMMITTED`: publisher first, adapter second, manifest third, result last. Both modules' exact modes and before/after bytes are plan-bound. A prior publisher-only prototype intent is not a compatible transaction and must never be silently migrated.

The adapter forwards `status.action_ref` and `push.recovery` to the existing publisher unchanged, removing only the repository selector after its closed binding. The existing publisher owns validation, journal and recovery. Commission status keeps its original closed contract. Commit admits the publisher-owned, mutually exclusive `index_recovery` selector; ordinary message/merge inputs remain closed and unchanged. The adapter forwards this object without interpreting it.

Original enrollment `TARGET_FILES` and generic fleet installation maps remain immutable. The generic compatibility test uses the actual historical publisher and adapter bytes in `fixtures/git-publish.fleet-v10-merge.mjs` (`abc3b4…`) and `fixtures/workspace-access.fleet-v10-merge.mjs` (`e4f74c…`). The C4 source test checks the actual current pair. These fixtures are not runtime bundle members or new admitted installation generations.

### Source and actual-carrier qualification

The initial two-module focused run passed 47 tests, including the C4 filesystem transactions and generic compatibility class. The returned adapter passed all 67 tests on M2. The final full installer run passed **590/590**, including the exhaustive eight-state prefix proof; control-bundle closure passed **53/53**; composition with the actual held C2 patch passed **45/45**. [Exact source hashes, commands and retained logs](../evidence/persistent-sector-leadership-2026-11-07/c4-publisher-pair/README.md) accompany this source. These qualify source, not installation.

A harmless fixture using the **actual configured C4 `/usr/bin/git`**, version **2.50.1 (Apple Git-155)**, proved the publisher's repeated-`-c` URL-clearing projection resolves exactly one pinned URL. The adapter worker's optional test-binary discovery is not relied on as proof for installed C4, and C4's configured binary is unchanged.

### Exact v4 settlement qualification

The same publisher now owns the explicit index-lock recovery variant. Its preview is read-only; apply uses exact HEAD/tree/index and lock identity fences plus declared maintenance custody, and makes at most one unique same-filesystem quarantine move. It never rewrites the real index, creates a commit, deletes a replacement lock or grants retry. Historical origin remains unknown; writer exclusion is caller-declared.

Retained actions are admitted before current-index preparation. Receipt reads and terminal writes require owner-controlled, non-symlink ancestry and a bound action generation. All routes to a new applied settlement establish source and quarantine-ancestor directory durability. Unreadable owner state, uncertain moves and unavailable durability remain structured unknown outcomes. These checks are not atomic inode CAS and do not replace maintenance custody.

Paid candidates `8d2eec…` and `641a37…` remained unaccepted after concrete defects were found. The next two-file corrective request was retained but refused before launch with unclassified code75; it was not retried or rehomed. The assigned parent completed the correction directly in this original source workspace under the authorized blocked-Fabric fallback.

On actual M2, all **11 focused regression cases failed before and passed after**. Four demonstrate formerly missed canonical-path fault injection; seven cover retained receipt ancestry, replacement-time drift, repeat-apply truth and directory durability. The complete final publisher/adapter suite passed **206/206**, zero skips. The final v4 installer suite passed **590/590** with `TMPDIR=/private/tmp`; production HOME and path guards were unchanged. Earlier three canonical-path fixture errors and their separate three-case pass remain distinct historical evidence. Current source evidence is [the v4 receipt](../evidence/persistent-sector-leadership-2026-11-07/c4-publisher-pair/index-recovery-v4.json).

This source qualification does not install the pair, settle any original Macro action, retire its actual lock, establish CI green or prove product acceptance. The inherited Brain composition CI dependency remains with original APPLICATION #2175/#2194 and its existing package-effect fences.

### Completed-parent proof correction after protected adoption

The protected v4 control bundle was installed coherently, but the first installed
publisher-pair apply refused before creating its child transaction. Same-target
readback found all original module, manifest and config bytes unchanged, and the
existing owner restored C4 to healthy service with its original pair. The
[source-linked maintenance receipt](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2203#issuecomment-6706612328)
records the exact plan, control-bundle digest, absence proof and restoration.

The child had passed its modifying verb to native installation admission solely
to obtain the publication lock. That strict reader requires the original
historical bootstrap artifact, which has been pruned. The completed native
parent remains verifiable through the existing retained status reader. The
closed C4 publisher continuation now separates those two responsibilities:

1. Authenticate the completed parent with the unchanged native status context
   and retain a copy of its complete binding, including the selected pointer.
2. Acquire the existing canonical native publication lock on the store from
   that verified binding, inside the existing C4 lifecycle mutex.
3. Authenticate the same binding again under the lock and require full equality.
4. Keep that lock through the original pin/result/bridge checks, parent receipts,
   child publication and final original-pin fingerprint check.

Generic native apply/reconcile and every other enrollment caller retain their
strict admission path. C4 preview/status remain read-only. The native proof
owner, native lock implementation, pair payloads, v4 transaction generation,
parent receipts, account/configuration and installation guards are unchanged.
The continuation does not reconstruct a bootstrap artifact or select native
code. As before, locks exclude conforming owners; they do not create atomic
filesystem CAS against a hostile process with the same UID.

The focused integration cases use the real native proof subprocess, canonical
publication lock and C4 filesystem transactions with isolated release fixtures.
They cover the reproduced failure, live lock contention during writes and the
final fingerprint, selected-pointer drift, corrupt retained evidence, exceptional
lock release, same-child reconcile, committed reconcile without replay, and
unchanged strict native admission. The separate real retained-reader suite
continues to verify receipt/artifact integrity. Exact commands, source hashes,
failure-before and passing-after receipts are retained in
[parent-proof qualification](../evidence/persistent-sector-leadership-2026-11-07/c4-publisher-pair/parent-proof-correction.json).

A new protected source release and complete control-bundle adoption are required
before another installed preview. The failed pre-preparation apply is not
blindly retried. Confirm the original target still has no child transaction,
retain that evidence, and use a fresh preview under the corrected installed owner. A successful source test
does not establish pair installation, Macro action recovery or product acceptance.

### Protected adoption and recovery order

The current Chairman's ChatGPT Web review waiver supersedes this runbook's historical blanket separate-review wording. Perform self-check, meaningful tests and required CI; obtain non-author GitHub approval only where the actual protected rules require it. No self-approval, self-merge, rule bypass or release-hold bypass is permitted.

1. Complete exact-source qualification and normal protected release.
2. Through an independent maintenance carrier, freshly verify the existing sealed **13-member control bundle**, then CAS-install that complete qualified bundle with its actual expected digest. Do not copy a single owner into the installed closure, move the installer under a different HOME, or relax path guards. The installed control context supplies the unchanged frozen Paper reader through its existing verified mechanism.
3. Stage only the exact two qualified module payloads in the allowed HOME-owned source directory. Obtain a fresh C4 preview through the installed private-service owner.
4. Establish quiescence of C4's own active commands and unread returns, stop only C4 through its owner, and apply the exact preview plan once. The separate Fabric service and its workers are not a C4 drain prerequisite.
5. Read the same transaction, reconcile an uncertain return there, start through the existing owner, then verify health and the actual installed/live tool catalog. Refresh the same ChatGPT app's supported action snapshot if needed and read back `action_ref`/`recovery` capability.
6. Only then use the publisher's guarded `LEGACY_FORWARD_ONLY` path for the original Macro operation and its actual current heads. Preserve the historical unknown push action; the new forward action does not retroactively settle or retry it.

A source preview from the candidate `/Volumes` checkout already refused before installation because the frozen private reader's HOME ancestry guard applies there. Preserve that refusal. The existing control-bundle owner is the legitimate installed-source adoption path; there is no alternate installer invocation or guard exception.

No installed action or consumer acceptance is implied by this source procedure. C2's held source, credentials, profiles, grants, config, Node, backend, dependencies, plist and all retained parent transactions remain bound to their existing owners.

### Exact committed-v4 inventory successor

The first original-workspace recovery preview under installed v4 refused with
`INDEX_RECOVERY_STATE_UNAVAILABLE` before any recovery effect. The bounded
diagnostic isolated `ERR_CHILD_PROCESS_STDIO_MAXBUFFER`: both exact `ls-files`
inventories exceeded the ordinary 1 MiB command-output buffer. HEAD, tree,
real index and lock identities remained readable and unchanged.

The corrected publisher hashes all stdout bytes of the four fixed, read-only
recovery inventories as binary streams. It preserves their NUL delimiters and
existing receipt fingerprints, enforces a separate 64 MiB ceiling per inventory,
retains the configured command deadline and 1 MiB stderr ceiling, and refuses
on limit, timeout, stream/process error or nonzero exit. An abort requests
`SIGKILL` and allows at most one further second for confirmed child closure.
If closure cannot be confirmed, cleanup uncertainty settles as an unavailable
observation without claiming the reader exited. No partial digest is admitted.
Ordinary command-output limits and every index/lock/HEAD/tree/custody fence stay
unchanged. The tests include an actual Git index exceeding both old buffers,
all four binary inventories, tail sensitivity, the exact ceiling and failures.

This publisher is one exact child within the existing
`native-pool-pin-enrollment` owner. It preserves the committed v4 transaction:

- Parent plan: `7d0112d29668a3bb4ef26790387d1010fedd638895088cd08a34d9d893a12301`.
- Parent manifest: `8af46ae3e2ffea1ed0af23c78f9ed11dedb3411f05118937679fb535c5048d76`.
- Parent publisher: `a8ce5f25f4fc606e294f58de5748a73a36de5178d8e30b27132c3660e161d58e`.
- Corrected publisher: `6b50521c6d94c83a2f68a700f6f658c4d52ec91cd7fc29bedb00a9d4f6647f05`.
- Unchanged adapter: `290cf5e961db2fa30e37c32da473595518df0ded80fc850a84cf5bdae1a1ec3c`.
- Unchanged config: `f06dc822015fc11f34d7e1142bdf1b016cb985af701ba929f33b313ff3a570df`.

The child journal is
`native-pool-pin-enrollment-publisher-inventory`, generation
`c4-publisher-inventory-20261107-v1`. Its plan binds the full nine-file v4
fingerprint, all earlier parent proofs and the retained v4 modes. Only the
publisher and projected manifest change, in the order
`OLD -> PUBLISHER_ONLY -> COMMITTED`; the adapter is an invariant. The manifest
projection changes only `files["git-publish.mjs"]`. A committed byte state without
the durable child result remains `EFFECT_UNKNOWN`. Once a child exists,
incomplete or foreign child evidence blocks startup without v4 fallback.

After this source is qualified and protected, install the complete control
bundle through its existing CAS owner. Stage the exact corrected publisher
under the permitted HOME-owned source directory, and use the same enrollment
command with the **parent manifest** above. Fresh preview binds the new child
plan; quiesce and stop only C4, apply once, retain/read back that child, and start
through the incumbent owner. Preserve v4 and earlier receipts byte-for-byte.
Reconciliation always uses the same child and original plan, with no replay of
completed module writes. The real native proof context and publication lock
remain held through writes, result settlement and the final parent fingerprint.

Only actual installed-source/client proof permits a new original-Macro recovery
preview. The previous pre-effect refusal is retained as evidence; this source
repair does not itself move its lock, commit source, publish a branch, deploy a
consumer or establish Sector acceptance.

Qualification: the final publisher suite passed 142 tests; the enrollment and
real native-parent suites passed 110, control/closure/source identity passed 63,
and retained native-reader coverage passed 12. The final publisher digest was
then rechecked against the source-fixed enrollment target. Earlier runs overlap;
they are not additive. Initial fixture-only failures and the bounded-cleanup
review correction remain in the
[source receipt](../evidence/persistent-sector-leadership-2026-11-07/c4-publisher-pair/inventory-streaming-correction.json).

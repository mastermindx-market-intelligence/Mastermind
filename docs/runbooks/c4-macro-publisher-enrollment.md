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

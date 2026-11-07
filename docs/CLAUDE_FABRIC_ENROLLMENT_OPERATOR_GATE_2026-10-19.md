# Claude Fabric enrollment - first-account operator gate

Status: PRE-LOGIN PREPARATION. No Claude native worker realm is claimed active by this document.
Source authority: protected docs/sol_skills/INDEX.md at fd1159695b0491a1b2c8d3042dce1232ad8365b4; approved provider-auth compatibility amendment and OCR-1 V3 plan.

## Scope and retained identities

- Enrollment target: one Claude Code **native subscription** worker realm, not an already-open Parallels Claude.app profile.
- Preserve existing Claude 3/5/6/8 applications and their support directories. Never launch, quit, move, log out or relink these apps for this task.
- Do not repurpose standalone `/Users/chriswong/.local/bin/claude` as evidence for an embedded Parallels account.
- Preserve `claude` (principal seat; aliases fable/claude-fable) versus `claude-native` (operator/reviewer) as separate routes.
- No tokens, Keychain payloads, provider-account emails, raw `auth status` output or account UUIDs enter repository, Slack, Executive events, notes or model context.
- Never substitute `CLAUDE_CONFIG_DIR` for native macOS OS-principal/Keychain isolation. No `claude setup-token`, `CLAUDE_CODE_OAUTH_TOKEN`, API key or unreviewed provider gateway.

## Safe preparation (operator-owned, before asking Chairman to authenticate)

1. Verify the installed Claude binary version/path and installed source release with non-credential metadata. Do not modify the default Claude application or invoke a model turn.
2. Resolve existing host_ref, dedicated native worker OS principal, provider-binary attestation and worker execution environment from their canonical owners. If missing, report the exact unfulfilled identity seam and prepare it through those owners; do not invent hashes or refs.
3. Use the canonical `ops/executive_os/claude-worker-preflight.py` and `ops/executive_os/claude-realm-set-verify.py`, not a new login/preflight command. CLI probing is limited to allowlisted `--version` and `auth status` in the **same reviewed worker environment** used later by the worker.
4. Validate the worker context refuses higher-precedence keys, cloud/gateway/provider profile selection, mismatched user or non-native auth; the preflight must fail closed if unable to demonstrate the actual worker context.
5. Determine first selected realm label, exact host and OS principal, verified path/binary, and native login command in that principal. Prepare a restricted authenticated human interactive shell for login; do not open GUI Claude.app.
6. Before asking the Chairman to log in, show a **single explicit manual command** for the already-isolated worker principal, identify which intended paid subscription to select, and state that the interactive provider sign-in must be completed by the human. Never paste secrets or raw auth metadata into chat.

## Required Family-B sequencing before Chairman attended login

Protected Family-B implementation architecture requires B1 source registry/export acceptance, B2 native realm enrollment, B3 existing canonical preflight composition, B4 native observation and capacity readiness, and B5 owner-qualified source acquisition/CF2 claim integration **before** B6's first real native subscription login. A provisioned OS principal and passing identity-owner diagnostic are only B2 evidence; an unaccepted/absent Claude native-capacity source blocks B4/B5. The first real login is not a substitute for production source enrollment.

Current concrete B1 owner is Macro PR #7583, whose original issued opaque Claude capability identity must be preserved across reconciliation with accepted MiniMax registration #9482 on Macro main. The registered Claude source row must be accepted, exported from an actual protected release and bound by the existing root Capacity/Control owners; do not fabricate a registration or rewrite the MiniMax row. Once the B1–B5 consumer path is source-qualified, the operator presents one supervised B6 login step under the reviewed OS principal. The canonical auth verifier, capacity qualification, and B7 original-parent canary remain independent proofs; do not bypass source, execution or production gates.

## Chairman attended gate - ONLY after B1-B5 are source-qualified and steps 1-6 pass

A. In the verified dedicated native worker-principal terminal, execute `claude auth login` using its reviewed binary. Complete the native subscription browser sign-in yourself. Do not use `setup-token`, API keys or a Parallels app profile.
B. Tell the operator only **"login completed"** (or describe a failure) and which opaque subscription slot you intended; never provide the credential, account email, login URL or Keychain item.
C. Operator runs the single canonical non-secret worker-context preflight and checks the closed receipt: `WORKER_CONTEXT_AUTH_READY`, `claudeai`, `first_party`, matching accepted host/principal, execution-context Worker Broker, binary and intended slot. Stop and diagnose any failure without switching auth method.
D. Only after the fresh preflight and distinct-realm-set verifier, qualify the source-owned provider capacity, native broker enrollment, approved host placement and one bounded original-parent model canary. Read back capacity selection and retained result; this is not granted by login success alone.
E. Repeat A-D one realm at a time. Confirm distinct OS-principal/credential realms and quota ownership before counting pooled concurrency. Never infer five or four usable subscriptions from GUI app count.
F. Follow the existing protected merge/release and attestation path before labeling any route production-ready. Do not edit a sealed live Fabric release in place.

## Exact-model optional delegation

- Keep auto selection the default. An explicit model request is an **exact allowed-model constraint**, not permission to bypass role, subscription, quota, capacity, host, plan provenance or review independence.
- Existing draft PR #1365 is the active selector source carrier. Reconcile that candidate's owner, head and release with existing installed Fabric before promotion; do not ship a parallel selector or copy a patch into a live immutable release.
- Principal-level Astra/Fable auditors are not interchangeable with leaf workers. First establish a supported principal/reviewer route and independent-review constraints; if unavailable, refuse the pinned model rather than silently substituting a different one.
- Model selection and account selection are separate: account is authorized by the provider realm/capacity owner, never raw `--model` or a user's host hint.

## Proof and closeout

Source tests: `python3 -m pytest tests/test_claude_worker_preflight.py tests/test_claude_realm_set_verify.py -q`. Passing tests prove the closed preflight contract, not enrolled accounts.
Live acceptance: a fresh worker-context auth receipt + realm-set distinctness + broker-enabled provider + admitted bounded original-parent worker result + accepted release/protected checks. Absent any one, report BUILT_NOT_PROVEN.

## Live Oct 19/20 M2 checkpoint — retained first-realm evidence

Protected procedure pin checked after resume: Mastermind master `a7553e0a18339c910eef9687c730b06605dd710e`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1. No credential read, login initiation, provider inference, Worker start, Capacity publication, admission or user GUI action occurred.

**Native identity — diagnostic accepted, not ready:** Root-owned `worker-claude8-native-01.json` is a v6 broker configuration with `native_provider=claude`, `native_realm_enrollment=enrolled` at generation 2, and a dedicated private OS-principal realm. The exact currently bound binary is reviewed Claude Code **2.1.275**; its actual SHA-256 matched `native_realm_enrollment.provider_binary_sha256`. The installed native realm identity owner, evaluated under that dedicated worker OS principal and private working directory, returned **ACCEPTED**. An earlier diagnostic's inherited inaccessible CWD was corrected; it never established provider readiness.

**Auth — independently classified:** The reviewed provider binary's native metadata-only auth status under the dedicated principal returned **loggedIn=false**. A later staged diagnostic using the installed canonical `claude-worker-preflight.py` allowed version observation `2.1.275` and normalized auth to **LOGIN_REQUIRED**. One earlier combined preflight attempt returned `PROVIDER_COMMAND_FAILED`; the subsequent separated version/auth observations succeeded, but the cause of the earlier failure was not established. No raw provider auth output/PII was retained.

**Capacity — absent:** The current worker configuration has **no native_capacity_enrollment or capacity_capability_id** and no observed Claude worker process/service. The installed native Fabric picker still says `NONE reason=native subscription enrollment pending` for Claude audit. Installed root capacity-source v2 export currently includes one registered MiniMax domain and **no registered Claude domain**. These are independent gates; login success will not itself enable Fabric.

**Existing Claude source registration custody:** Macro `main` at `13e098071ab2799c41a170d21ad522f751dfb15a` has only the MiniMax row in the canonical `config/provider_native_capabilities.v1.json`. Existing *draft/held* **Macro PR #7583** already contains the original opaque native-Claude registration identity. It must be reconciled through that original source carrier: never issue a second Claude capability ID or blindly merge its older registry snapshot over the newer MiniMax registration. At that earlier inspection, the old operation's source workspace was not found at its former mount path. The exact original locked worktree was subsequently recovered on the mounted `/Volumes/Mastermind 2` volume (see latest B1 frontier below); the temporary path miss did not constitute writer release. Macro #9482 accepted the MiniMax registry registration only; it did not admit Claude.

**Selector owner:** Mastermind draft **PR #1365** remains open at `b785a595baaf4e004d3a82c8e0fecf4678950e0f` with its own ongoing exact-model selector/seat proof and writer. Preserve it and do not add a competing selector implementation.

**Next safe actions in governing Family-B order:** (1) Reconcile original Macro B1 PR #7583 source custody and merge its *existing* Claude capability identity with accepted MiniMax registration #9482/current main, preserving the single canonical Provider Control registry. Obtain accepted-source B1 release/export rather than synthetic data. (2) Complete B2–B5 source-owned realm/capacity observation, registration acquisition and existing CF2/Executive integration and required qualification. (3) Only after these actual gates pass, request the Chairman-attended B6 native Claude subscription `auth login --claudeai` in the exact dedicated OS principal and root-approved binary/private environment; never invoke a generic user shell or Parallels Claude.app. (4) Verify canonical `claudeai/first_party` and worker-context readiness with no raw auth metadata, and prove B7 one admitted original-parent result before broader realms. Do not claim login alone enables Fabric capacity.

**Proof vocabulary:** `IDENTITY_ACCEPTED_DIAGNOSTIC`; `AUTH_LOGIN_REQUIRED`; `CLAUDE_NATIVE_CAPACITY_NOT_ENROLLED`; `WORKER_NOT_STARTED`; `PRODUCTION_PROOF_MISSING`. All remain nonterminal.


## 2026-10-20 source and reviewer frontier (latest checked)

The original Macro Family-B B1 registration operation `family-b-b1-provider-native-capability-registration-20260917-sol-001` was recovered **on its original locked worktree** at `/Volumes/Mastermind 2/agent-workspaces/macro/sol/family-b-b1-provider-native-capability-registration-20260917-sol-001`. Its pending merge was reconciled and committed on the same PR #7583 as `0aeb5a3f7cb78b16b94522429e11ee0480f94fa3`; the original MiniMax capability row and original source-issued Claude capability row both survive. The independent-review non-ordinal-ID finding was repaired with deterministic native issuance/validation, regression tests and an ordinary fast-forward push at **`8e043896fafd835581902f7390ff5e5c517a7098`**. Tests passed on Python 3.12/3.14 (76 + 4 subtests each) and the adjacent Provider Control owner suite (233). The accepted-release source compiler, on that committed candidate, produced two registered rows with current and predecessor source identity; the installed Control source validator accepted a **synthetic, non-authoritative** Claude consumer fixture, never a live enrollment.

Hosted GitHub semantic `ci-gate`, `contract-delta` and all twelve CI packs completed successfully at this exact head. A separate inactive merge-queue pilot context returned `inactive_base_context` and is not a provider validator regression. The existing independent `CHANGES_REQUESTED` review is **not yet cleared**: PR #7583 is now ready for review with `hold-for-sol` explicitly retained, and its original reviewer `mastermindx-3` has been formally re-requested. No protected Macro merge/registration publication has occurred.

The reviewer is expected to adjudicate the repaired same-carrier source and normal protected queue delivery. **No independent approval, protected release, host-auth readiness or provider capacity follows from CI-green or from the synthetic consumer check.** Until the source is actually accepted and the existing owner wires B2-B5, the first native Claude login remains held. Last observed M2 Claude worker configuration still has `native_realm_enrollment=enrolled` / native auth `LOGIN_REQUIRED`, with `native_capacity_enrollment` absent. The GUI Parallels Claude applications remain outside this worker's custody.

The separate optional exact-model selector stays on original Mastermind PR #1365 (later observed candidate `e53e0285c925b11887bd034a78bc2570ad3600c5`), source-only and not installed. Its Codex Astra candidate path is not proof of an available, independent Fable principal audit route. No separate selector, release, credential or account process should be created.

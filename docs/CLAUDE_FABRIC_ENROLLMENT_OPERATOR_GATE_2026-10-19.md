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

## Chairman attended gate - do only when steps 1-6 pass

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

**Existing Claude source registration custody:** Macro `main` at `13e098071ab2799c41a170d21ad522f751dfb15a` has only the MiniMax row in the canonical `config/provider_native_capabilities.v1.json`. Existing *draft/held* **Macro PR #7583** already contains the original opaque native-Claude registration identity. It must be reconciled through that original source carrier: never issue a second Claude capability ID or blindly merge its older registry snapshot over the newer MiniMax registration. The old operation's former on-disk workspace was not found on the mounted volume, and its canonical workspace status is unregistered. This does not constitute a source-writer release or permission to duplicate its identity. Macro #9482 accepted the MiniMax registry registration only; it did not admit Claude.

**Selector owner:** Mastermind draft **PR #1365** remains open at `b785a595baaf4e004d3a82c8e0fecf4678950e0f` with its own ongoing exact-model selector/seat proof and writer. Preserve it and do not add a competing selector implementation.

**Next safe actions:** (1) Complete one Chairman-attended native Claude subscription `auth login --claudeai` in the *existing exact dedicated OS principal*, using the root-approved binary and private provider environment; never invoke a generic user shell or Parallels Claude.app. (2) Verify `claudeai/first_party` via the installed canonical preflight under the same realm, without printing raw account metadata. (3) Reconcile Macro #7583 with #9482/current source so an accepted current-source Claude registration can be exported, without duplicate capability identity. (4) Bind the provider-capability export through existing source/Control owners into `native_capacity_enrollment` and broker slot, qualify positive Worker-context auth, and run one admitted retained original-parent result. Do not claim step (4) from merely having step (1).

**Proof vocabulary:** `IDENTITY_ACCEPTED_DIAGNOSTIC`; `AUTH_LOGIN_REQUIRED`; `CLAUDE_NATIVE_CAPACITY_NOT_ENROLLED`; `WORKER_NOT_STARTED`; `PRODUCTION_PROOF_MISSING`. All remain nonterminal.

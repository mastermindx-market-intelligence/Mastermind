# Claude browser access across the Mastermind fleet

Date: 2026-09-15 America/New_York. Host receipts use UTC and therefore show September 16.

Operation: `claude-browser-fleet-client-20260915-sol-001`.
Protected source consumed: `4709b9483182c20153868dac164e1f621aac505c`.
Source-custody workspace: installed `mmx-workspace`, lane `web`.
Branch: `sol/web-claude-browser-fleet-client-20260915-sol-001`.

**Disposition: implementation candidate plus attended synthetic browser evidence; not production-enabled and not an end-to-end completed program.**

## 1. Outcome and decision

Every admitted Claude CLI, native Claude application session and fabric child should be able to request an appropriate browser without sharing one Claude extension login. The browser may run on a different computer from the model client. Approved web identities should retain their login state, while password use and password saving happen through a credential-owning helper rather than through plaintext model messages.

Adopt the existing official Playwright MCP engine and extend existing Mastermind resource and capability owners. Do not build another automation engine, credential vault, browser-session registry, scheduler or organizational control plane. A thin client package can simplify installation; a new Chrome extension is not required for dedicated automation profiles. Existing attended Claude-in-Chrome and Web Sol extensions retain their own supported purposes and authority boundaries.

### Ownership chain

`Claude client -> existing capability grant / SCF exposure -> Executive Attempt and existing Fleet placement -> Operator Harness resource on the selected host -> guarded Playwright browser -> owner-specific credential actuator when necessary`.

Executive remains the owner of admission, lifecycle, leases, reconciliation and effect truth. Capacity/Fleet remains the owner of host selection and physical reservations. Operator Harness remains the owner of attempt-local process and browser resources. SCF remains the model-facing capability projection. Credential ownership remains with the existing credential program; its R2 readiness is not a vault engine or proof of usable credentials.

## 2. What already exists and what is actually missing

`control_plane/worker_browser_b1.py` is a substantial bounded browser resource, not a missing implementation: exact runtime attestation, loopback enforcement, MCP tool guard, devserver ownership, screenshots and process-generation reconciliation already exist. It is deliberately isolated and limited to local review. Its protections must not be relaxed to turn it into an authenticated web browser.

The reviewed B1 runtime package is `@playwright/mcp@0.0.79`, with Playwright/Playwright Core `1.63.0-alpha-2026-08-05`. The dependency closure requires Node 20 or newer, even though the top-level MCP package advertises Node 18. The current installer is Mac/external-volume-specific. A desktop installation, production enrollment and cross-platform adapter are not established merely by this package existing in git.

The current `ClaudeSubscriptionWorkerAdapter` is a sealed, Claude-compatible subscription canary worker, not proof of every native Anthropic account's launcher. It denies `mcp__*`, supplies an empty strict MCP configuration and adds `--no-chrome`. Installing an extension cannot give that profile a tool it explicitly refuses. Do not remove those restrictions globally. A separately admitted Claude browser profile must compose the existing resource owner and a complete requested-versus-observed capability check.

The current browser capability fixture is `operator.browser.local-review.v1`, whose execution surface is `codex-app-server`. Translating its MCP configuration into Claude syntax does not admit the profile on Claude. The new R1 module explicitly preserves this distinction.

Native Claude Chrome integration is useful for attended tasks, but current official documentation requires interactive `/login` and a direct Anthropic plan; API-key and long-lived setup-token sessions cannot use that extension path. Multiple connected browsers can be selected through `/chrome`; this is not the same thing as an independent multi-account fleet resource.

## 3. Browser types and identity

Keep four concepts distinct: the model subscription account, the browser process, the web account signed into a profile, and the physical host. Four Claude accounts do not necessarily require four permanent copies of every website login.

Use these resource modes through existing owners:

| Mode | Intended use | Login state | Boundary |
|---|---|---|---|
| Existing B1 local review | Inspect a job's local devserver | Fresh/isolated | Existing loopback-only rules remain unchanged |
| Public temporary browser | Approved research and public-site workflows | Disposable | New explicit egress/tool policy, not an implicit B1 widening |
| Persistent authenticated browser | Approved service/account workflows | Retained on its home host | One controller, origin/account-scoped credential capability |
| Existing human/Web Sol seat | Observe or act on a specifically assigned existing surface | Existing state | Existing managed-seat and semantic action law; no generic attachment bypass |

A persistent profile belongs to a web identity, trust boundary, OS principal and home host. Ephemeral browser slots belong to an admitted attempt or child. A new stdio MCP connection is not by itself proof of a new browser profile or lease.

For the same persistent profile, allow one active mutating controller. Use the existing physical-resource reservation and execution lease; Chrome's own profile lock is a last-resort check, not the company authority owner. Do not introduce a second Redis/SQLite lock database. Helpers either receive independent profiles/resources or use an explicitly serialized parent-mediated operation.

After a dispatched click, submit or account change has an ambiguous result, preserve the exact target and effect identity for reconciliation. Do not blindly repeat the operation on another browser, account or host. Receiving a screenshot is not proof that a submission succeeded.

## 4. Client integration

### Claude CLI

At the admitted launch boundary, consume a validated MCP grant and construct explicit `--strict-mcp-config` configuration with exact tool names. Preserve server identity, version, tool-schema digest, resource generation and the existing guard. Global user/project MCP settings must not silently expand a sealed worker's privileges. Native `--chrome` is optional for an attended alternative; it is not a dependency of the shared browser service.

R1 implements the pure configuration translation in `control_plane/claude_mcp_client_projection.py`. It returns separate configuration shapes for CLI, Python Agent SDK, local Desktop and eligible inline subagents. It starts nothing and changes no global settings. `--allowedTools` is an auto-approval list, not a substitute for server-side enforcement. Its argv is a fragment; the caller must preserve option boundaries when constructing the complete command.

### Claude Desktop / Mac application

Use a local stdio bridge to the same admitted capabilities. Package that bridge as a desktop extension only after its installed executable and release are attested. A local MCP JSON entry does not enable cloud-hosted Cowork or web sessions. Do not assume changing one macOS app configuration enables every separately signed-in application instance.

A Desktop application may reuse its MCP connection across conversations. Do not infer a per-conversation identity from one stdio connection or trust a model-selected account label as authority. The existing Executive/runtime owner must bind each admitted browser handle to a real client/operation identity; otherwise parallel Desktop activation remains unsupported. Verify this explicitly with two conversations before claiming app-wide concurrency.

Remote custom connectors are an alternative, but current Anthropic documentation says the requests originate from Anthropic's cloud. A Tailscale-only URL does not automatically work. A reviewed authenticated ingress would be required, and must expose the scoped capability API, not unauthenticated CDP or raw Playwright on a public port. R1 therefore refuses to translate an HTTP grant into a local Desktop stdio entry without an admitted bridge; it does not silently drop required servers.

### Native subagents and fabric children

Current Claude documentation supports inline subagent MCP definitions, which establish scoped connections, while string references reuse an existing parent connection. Plugin-provided subagent `mcpServers` fields are ignored. Consequently, a plugin alone cannot be the browser provisioning mechanism.

The fabric launcher must bind each child to the allowed capability subset and owned resource generation. A child does not inherit unlimited host, credential or recursive-spawn permission. A profile with native helpers disabled remains disabled. Tool availability, actual tool invocation, browser independence, artifact consumption and cleanup need separate evidence. Do not report a parent tool listing as child browser proof.

## 5. Multi-host operation and persistent logins

The preferred persistence design is to keep a logged-in profile on a stable home host and route authorized callers to it. This avoids copying browser secrets just because the model process moved. Additional local profiles on other hosts may be enrolled separately when locality or capacity actually requires them. Host readiness must include runtime revision, OS/browser compatibility, free resources, profile availability, user-unlock state and network reachability.

Remote evidence also needs transport: a snapshot filename on the browser host is not a readable local file on a different client. Return bounded, authenticated artifact content through the existing artifact owner and bind it to the browser operation. The Studio pilot consumed files locally and therefore does not prove remote artifact delivery.

A permanently managed host installation must use the existing host enrollment and signed/pinned release path, appropriate macOS launch service or Windows service/task ownership, private storage permissions and closed transport. Do not deploy directly from an arbitrary worktree, expose debugging ports to the internet or use a shared cloud folder for live browser data.

Password sync, browser session persistence and browser profile replication are different features. A password manager can make approved credentials available on multiple machines without making their cookies identical. Persistent local profiles can reduce login prompts without keeping every session valid forever. Website expiry, revocation, MFA, passkeys/device binding, CAPTCHA and OS unlock still exist.

Do not copy the user's default Chrome profile, live cookie databases or entire Application Support folder. Chrome restricts debugging of the default data directory, and a dedicated automation directory is the supported isolation pattern. Storage-state export is sensitive credential material, not a harmless JSON fixture. If a specific approved service genuinely needs portable state, its owner must prove support and keep the transfer encrypted, scoped, short-lived and outside model-visible artifacts.

For host outages, a browser resource becoming reachable on another host is not permission to replay a possibly completed action. The existing effect owner decides whether a fresh profile/session may be enrolled after reconciliation.

## 6. Password storage, use and save

A current narrow email search found an existing 1Password welcome message dated September 12 in America/New_York. This is evidence of a signup, not proof that the desktop app, CLI, SDK, vault permissions or automation enrollment is ready. No vault contents or secret values were read.

Target that existing 1Password setup, subject to the credential owner's integration and available account permissions. Preserve existing macOS Keychain coordinates for host-native secrets. Do not create a competing vault or migrate the user's existing secrets implicitly.

For unattended automation, prefer a dedicated automation vault containing only explicitly approved service credentials and a scoped service account where the actual plan and account permissions support it. 1Password service accounts cannot access built-in Personal/Private/Employee vaults or the default Shared vault. Local desktop SDK authorization is a different human-approved mode and expires after inactivity or locking; it is not a permanently unattended route.

The credential-owning helper needs separate use and save capabilities. These are proposed contracts, not tools installed by this change:

- **Use an approved login:** resolve a prebound credential reference, validate account/profile generation and exact destination origin, fill the approved login form within the helper, verify a non-secret signed-in observation, return only a bounded receipt.
- **Save an approved credential:** accept a human enrollment or generate a password inside the credential owner, write it to the bound automation vault entry, reconcile success, and return the non-secret reference. Password rotation or a website account change requires separate explicit authority.
- **Report readiness:** expose enrolled, locked, expired, revoked, stale-generation, MFA-required and unavailable states through existing SCF readiness composition. Do not make the model infer readiness by visiting password-manager settings.

A general-purpose browser agent must not inspect the vault UI or secret-bearing DOM, use arbitrary JavaScript to read password fields, capture login screenshots with revealed secrets, or read intercepted authentication bodies. Avoid a generic `get_secret` tool and do not hand the vault token to every child process. The trusted actuator necessarily handles the secret transiently, but the model receives an outcome, not the password. Domain binding, navigation races, credential-saving confirmation, revocation and log/artifact leakage require adversarial tests before activation.

Initial vault enrollment, account unlock and provider MFA may require the Chairman. Never ask for an account password, recovery kit, vault token or OTP to be pasted into this chat.

## Operator experience within existing Control Room surfaces

Expose browser availability, home host, mode, scoped web identity, current owner and login readiness in the existing Control Room rather than creating a second console. A worker should report a actionable state such as available, capacity-exhausted, profile-in-use, host-offline, login-required or human-MFA-required. The user must be able to locate the browser, request an attended login, release an owned session and inspect its returned evidence without locating a hidden terminal or guessing which account is attached.

Use a visible browser for first-login ceremonies and an explicit mode switch for attended intervention. Normal automated work may stay headless. Credential entries are selected by non-secret labels/references; no reveal-password feature is needed for the model. The account-wide permission, destructive web action, purchase, posting and external communication boundaries are not waived by browser availability. These UI and human-intervention paths are required work, not implemented by R1.

## 7. Reconcile active owners; do not race them

| Existing carrier | Current observed boundary | This program's relationship |
|---|---|---|
| Mastermind PR #634 | Credential architecture; records-only | Reuse SCF/credential ownership and no-raw-secret model boundary |
| PR #663 | Secret-free credential readiness composer candidate | Consume after acceptance; not a vault actuator |
| PR #644 | Fleet placement architecture candidate | Reuse placement/reservation/MH1; no second host scheduler |
| PR #473 | Browser actuation source-custody HOLD, changes requested | Do not modify its four source paths or adopt its unknown incumbent effects |
| PR #633 | Existing Astra OAuth/effect reconciliation | No retry, account substitution or enrollment effect from this program |

The current Mastermind Executive connector returned HTTP 401 with manual reauthentication required. No Executive Job was submitted, queued, claimed or dispatched by this turn. Host probes used the separately qualified attended Remote Desktop Commander route and are not fabric dispatch evidence. The failed authenticated route was not bypassed to claim production admission.

## 8. Implementation waves and acceptance

### R1 — client translation and browser feasibility (this candidate)

Deliver the pure serializer and exact source-linked tests without changing current worker permissions or runtime configuration. Prove real browser feasibility with synthetic state on fresh profiles. No real account enrollment, vault use, global Claude settings, service installation or protected-source deployment follows from this candidate.

### R2 — one admitted Claude browser vertical

Reconcile current Claude operator/source custody and the existing capability registry. Add a distinct Claude execution-surface profile through the existing owner, not by rebranding the Codex fixture. Compose BrowserGenerationResource, the exact guarded MCP bridge, child environment and requested/observed capability checks. Start one admitted Claude session on a synthetic local app. It must navigate, act, consume its real snapshot/screenshot and return canonical evidence; cancellation must settle the browser resource. Obtain independent review and current-base proof before enabling any production profile.

Repeat with four separately authenticated, admitted Claude accounts. The observed launch record must prove four distinct native sessions; the earlier four-browser experiment is not sufficient. Verify no settings, tab, cookie or account cross-talk.

### R3 — persistent authenticated profile plus credential use/save

After credential readiness and ownership reconcile, enroll one approved non-critical web account in a dedicated home-host profile and automation vault. Prove use without raw-secret output, wrong-origin refusal, stale-generation refusal, save confirmation, lock/MFA reporting and restart persistence. Do not claim indefinite session validity. Test revocation and cold boot independently. Retain B1's original isolation.

### R4 — admitted fleet transport and resource placement

After Fleet/Capacity prerequisites clear, add the browser readiness facts and cross-platform runtime qualification to the existing host resource path. Prove a Claude client on one host actually drives a browser on another through the authenticated transport. Test offline host, sleep/wake, capacity exhaustion, single-profile contention and effect-unknown recovery. A remote shell launching a local test is host feasibility, not this acceptance.

### R5 — Desktop and child integration

Install the reviewed local bridge for one real Claude Desktop session without overwriting unrelated settings. Prove an actual tool action and returned page evidence. Enroll other app/account instances with explicit principal identity. Separately prove a native inline subagent and a fabric child using their own admitted resource; prove that a plugin field ignored by Claude is not relied upon. Cloud remote-connector delivery is optional and needs its own ingress/authentication proof.

### R6 — end-to-end production acceptance

Run a real user workflow across CLI, Desktop and fabric child with exact release identity. Demonstrate four concurrent independent workers, one serialized shared web identity, second-host routing, retained login after browser restart, expected human-unlock/MFA behavior, secret-free receipts, cancellation/cleanup and revocation. Record actual native client/session, host and resource identities. Source merge, HTTP health, configuration generation and synthetic tests each remain lower evidence levels, not substitutes for this workflow.

## 9. Evidence already produced

Baseline capability tests: 30 passed. New projection tests were first run before implementation and failed with the intended missing-projection assertion. The initial implementation then passed 29 new tests plus the 30 existing tests. Final focused validation passed 61 tests (31 projection tests plus 30 existing capability tests), including a Python-version-compatible refusal assertion for relabelling candidate metadata as production-armed. At final source comparison, protected master was `7642aea155d2817219135b24246b55c1d7611c66`, one commit ahead of the consumed base, with two changed files and no overlap with this candidate or its directly consumed capability/browser contracts. This is not a fresh-base integration test or merge receipt. Exact candidate head and independent review status belong on the draft carrier.

Studio experiment: `@playwright/mcp@0.0.79`, actual installed Chrome, four concurrent fresh profiles, synthetic cookie and local-storage isolation, active-profile duplicate refusal, four successful restart-persistence checks, nine actual MCP tool catalogs consumed and sixteen returned snapshot files consumed. All nine owned MCP processes exited and their process groups were proven absent. This is not a sealed-worker UID sweep or a proof about unrelated detached browser processes.

Artifact root: `/Volumes/Mastermind/agent-evidence/claude-browser-fleet-client-20260915-sol-001`.
Final Studio receipt: `browser-fixture-receipt.json`.
Probe source SHA-256: `51be6989e584d059d51991fd28b452d801b452fa45c414fc8d6d359c5d4d633b`.

Three live integration lessons were captured with preserved failed receipts before correction: a 137-character socket directory prevented startup; a private short socket directory fixed the experiment. Navigation returned a snapshot artifact link rather than inline DOM; the verifier needed to consume the exact bounded artifact. The actual click schema required `target`, not a remembered `ref`; tools/list established the current contract. These changes are in the attended probe, not claimed as production B1 repairs.

Mac mini and MacBook probes separately launched real sandbox-requested Chrome through the same pinned Playwright Core version, rendered a local fixture, and proved synthetic cookie/local-storage persistence across browser restart. Both contexts and fixture servers closed successfully; temporary downloaded dependencies were removed. Those are browser-host/library tests, not MCP client or fabric routing tests.

No real credentials, personal profiles, password-manager settings, existing managed-browser seats or production website actions were used in these proofs.

## 10. Primary references checked September 15, 2026

- Claude Chrome prerequisites and multi-browser selection: https://code.claude.com/docs/en/chrome
- Claude MCP client configuration: https://code.claude.com/docs/en/mcp
- Native subagent inline connections versus plugin limitations: https://code.claude.com/docs/en/subagents
- Desktop/local versus cloud-originated remote connector behavior: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp
- Playwright profile persistence and exclusivity: https://playwright.dev/mcp/configuration/user-profile
- Sensitive authentication state: https://playwright.dev/docs/auth
- Chrome default-profile debugging restrictions: https://developer.chrome.com/blog/remote-debugging-port
- 1Password authentication modes: https://www.1password.dev/sdks/concepts
- 1Password service account requirements and exclusions: https://www.1password.dev/service-accounts/get-started

These references describe current upstream behavior. Deployment must still attest the exact installed versions; the pinned MCP runtime's observed tool schema already differed from a remembered example.


## 11. Native permission repair checkpoint

Same source operation resumed under protected procedure `f590c068880dbb848bda90b80b73dbcb6688d6fc`. Exact readback proved the prior blocked fixture patch had not changed source; the original fixture digest remained `307f2e1891f7f413428e6f804317fe0d44f2abeb7ad72c179841dc127df33a23`. The unfinished child-denial cases were repaired rather than removed.

A stronger real native test then falsified reliance on an inline child's tools list: a broader parent auto-approval allowed the omitted tool to execute. An explicit child deny stopped it. The compiler now derives exact denies from a complete, schema-matched tool catalog and refuses inline generation without that evidence. The fixed native consumer uses the generated configuration unchanged; it does not manually patch in the expected deny.

Permitted direct CLI, Python SDK and native-child paths returned actual page snapshots/images and preserved the synthetic 936-character Unicode input. Their observed browser tool set reduced from 24 raw definitions to the seven granted tools. Denied cases exposed six browser tools and performed no form submission; the child result was consumed by its original parent. Exact final source hashes and run receipts live in `research/evidence/claude_browser_client_native_2026-09-16.json`; the R1 plan's replay amendment defines their scope.

These are installed-client/browser protocol proofs driven by a local deterministic responder. They are not native Anthropic account authentication, model cognition, visual judgment, real Executive admission, production B1 activation, Desktop installation or fleet deployment. A complete source and evidence candidate may be submitted for review; the parent program remains PARTIAL.

The source correction is confined to the client projection, its tests, the native test consumer, this program/plan and captured non-secret evidence. No existing sealed subscription worker was loosened. No service, global Claude setting, vault, account, browser seat or production website was changed.

Exact next delivery dependency: publish this same candidate for independent exact-head review; then integrate its catalog/deny contract through the incumbent native Anthropic PF1 and browser-resource owners after their admission/source gates clear. The current source acceptance ceiling remains BUILT_NOT_PROVEN as a production capability. Do not repeat the already-completed four-host synthetic feasibility tests or mistake this native test child for a real fabric Job.

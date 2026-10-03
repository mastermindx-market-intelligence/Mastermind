# Web CEO + native operator environment

Status: `RECORDS_ONLY / SPEC_ONLY / PRODUCTION_INERT`

Protected basis at authoring: `Mastermind@9ed16bf0fcc5b47e870350ff2413ff5c8c73b447`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.

This record answers one product question: **what environment must a Mastermind Web CEO or native operator receive so it can understand the company quickly, reach every relevant Mastermind surface, act through the correct owner, and avoid recurring Chairman authentication/tool-repair labor?**

It creates no runtime authority, lifecycle, browser authority, credential store, source lease, new truth database, worker assignment, provider turn, host effect, plugin installation, or production claim.

## 1. Executive decision

Build one **federated operator environment**, not one omnipotent MCP.

The environment has five cooperating layers:

1. **Navigator / procedure layer** — teaches every fresh CEO/operator which canonical owner and tool to use, builds a capability/auth health matrix, and loads only role-relevant tools.
2. **Snapshot / truth layer** — composes existing Executive, Agent OS, GitHub, Linear, Dialogue/Wake, RuntimeBinding, Web-Sol and host/capacity facts into one source-attributed boot view without creating another truth store.
3. **Workbench layer** — existing authenticated selected-project read plus a new bounded attended-action sibling for project mutation and commands.
4. **Authenticated browser-realm layer** — persistent managed ChatGPT/browser profiles, exact RuntimeBinding and Web-Sol actuation, with credentials owned outside model context.
5. **Native fleet layer** — qualified host transport, resource/eligibility visibility and multi-host placement through existing Workbench Fleet / Capacity / MH1 owners.

The product is complete only when these layers compose into a useful operator journey. A source package, installed connector, online host, visible browser tab, or successful health ping is not that journey.

## 2. What not to build

Do **not** build a generic `mastermind-editor` MCP with unrestricted repo/filesystem/shell/browser access.

Do **not** add another:

- Executive lifecycle, queue, retry ledger or Worker registry;
- Agent OS / workstream / decision database;
- source authority, branch registry, Git truth store or merge authority;
- Session OS, browser session registry, account elector or RuntimeBinding replacement;
- credential/token/cookie store exposed to model calls;
- generic browser controller when Web-Sol has a bounded owner;
- remote-shell mesh or host-to-host SSH scheduler;
- company snapshot database beside Steward/Control Room;
- plugin marketplace or capability registry beside the existing package / Sol Capability Fabric owners;
- code index/source-truth plane beside the governed Code Intelligence Fabric.

One tool being technically capable of an effect is never sufficient organizational authority for that effect.

## 3. Canonical owner routing

| Question / effect | Canonical owner | Preferred operator surface | Class |
|---|---|---|---|
| Job / Attempt / Worker / Event; CEO admission; retry/requeue | Executive OS | Mastermind Executive / Executive MCP | read + governed admission |
| Workstream / decision / discovery / handoff | Agent OS | Agent OS owner / Steward composition | organizational state |
| Code / branch / PR / CI / merge / immutable proof | GitHub | GitHub connector + governed source worktree | source |
| Portfolio projection | Linear | Linear connector | projection |
| Dialogue / hot-state evidence | Company Dialogue / Slack / Agent Relay | governed dialogue surface | transport |
| Attention / delivery / acknowledgement | Wake Fabric | Wake / Agent Relay | attention |
| Current logical provider target | SessionTargetRegistry / RuntimeBinding | exact binding owner | identity |
| Browser observation / exact foreground / wake | Web-Sol | managed-profile extension + native host | bounded actuation |
| Selected project file read | Workbench Read | authenticated `workbench.read` MCP | read |
| Attended project edit / bounded command | Workbench Action | new sibling defined below | bounded mutation/process |
| Cross-owner current company view | Executive Steward / Control Room | existing boot/brief composition | synthesis |
| Host execution / machine facts | Workbench Fleet / host transport | first-party host agent; qualified RDC while incumbent | attended host effect |
| Provider/model/physical placement | Capacity / Model Router | existing capacity/control owners | admission |
| Code discovery / exact-worktree semantics | Code Intelligence Fabric | stable Mastermind facade when accepted | read |
| Deploy / DB / analytics / design | declared domain owner | Vercel / Supabase / PostHog / Figma only when needed | domain effect |
| Knowledge/docs/comms | declared canonical owner | Notion/Drive/Gmail/Calendar only when needed | document/comms |

Unknown owner-native facts remain unknown. The Navigator may explain and route; it may not manufacture authority.

## 4. Role-scoped tool profiles

The full approved plugin catalog should be **reachable**, but not injected into every session simultaneously.

### Web CEO core

Default reachable surfaces:

- Mastermind Executive;
- Executive Steward / Control Room / CEO boot packet;
- GitHub;
- Linear;
- Company Dialogue / Slack / Agent Relay;
- Workbench Read;
- Web-Sol + RuntimeBinding / SessionTargetRegistry + Wake;
- current provider/capacity health projection.

Add Workbench Action only for a task that needs bounded project mutation. Add domain plugins on demand.

### Native builder/operator core

Use the Web CEO truth surfaces plus:

- GitHub source/PR operations;
- exact source/worktree identity;
- Workbench Read + Workbench Action;
- qualified host transport / fleet visibility;
- Code Intelligence facade when accepted.

Browser/provider tooling is optional unless the mission includes provider/session behavior.

### Browser/provider operator

Expose:

- Web-Sol;
- RuntimeBinding / SessionTargetRegistry;
- Wake / Dialogue;
- provider capacity/health;
- exact managed browser realms assigned to the operation;
- Executive read context.

No cookie/storage/token export tool belongs in this profile.

### Domain specialist

Start with the minimum company-truth read surfaces, then add exactly the domain owner needed: Vercel, Supabase, PostHog, Figma, Notion/Drive, Gmail/Calendar, etc. Domain plugins do not inherit Executive/source/browser authority.

### Why role scoping

This reduces tool-selection noise, context use, accidental writes and prompt-injection surface while preserving total reach. “Full suite” means **available on demand with deterministic routing**, not “all schemas loaded all the time.”

## 5. Mandatory session boot packet

A fresh substantial CEO/operator session should be able to obtain one compact packet before modifying anything:

```text
protected_source_commit
skillpack_schema/version/compatibility
mission / machine_job / completion_ruler
role_profile
surface_health[]
current_owner_bindings[]
current_source / project / session / host identities where needed
unresolved_effects[]
blocked_capabilities[]
next_owner_tool
```

Each `surface_health` row contains:

```text
surface
canonical_owner
capability_state = PROVEN_LIVE | BUILT_NOT_PROVEN | PARTIAL |
                   DARK_OR_DISCONNECTED | BROKEN | SPEC_ONLY |
                   NOT_BUILT | REJECTED_BY_DESIGN
auth_or_connection = AVAILABLE | DEGRADED | UNAVAILABLE | UNKNOWN
mode = READ | BOUNDED_WRITE | ACTUATE | PROJECTION
binding = exact project/session/host/operation ref or null
freshness
blocker
next_probe
```

The packet is a source-attributed composition of canonical owners. It is not a new state database. Prefer extending the existing CEO boot packet / Executive Steward / Control Room read composition.

## 6. Authenticated browser realms

The recurring “come authenticate this session” problem must be solved as a **realm lifecycle and secret-ownership problem**, not by exposing credentials to the model.

### Trust realms remain separate

Keep separate ownership for:

- ChatGPT plugin/app OAuth;
- host transport enrollment;
- Git/provider source credentials;
- managed browser profile login;
- provider/model subscription credentials.

A valid credential in one realm does not authorize another.

### Required browser-realm capability

For each approved browser/provider realm, maintain an opaque, non-secret binding with:

```text
realm_ref
host_ref + boot/agent generation
managed_profile_ref
provider
account_role_ref
login_state = AUTHENTICATED | CHALLENGE_REQUIRED | LOGGED_OUT | UNKNOWN
extension/native_host_generation
RuntimeBinding eligibility
last successful bounded probe
freshness
```

Secrets remain in the browser profile, OS keychain or approved secret-owning local service. They never appear in durable receipts, model prompts, MCP results, cookies/storage dumps or cross-host copy operations.

### Reconstitution goal

Routine browser restart, extension service-worker restart, native-host restart, session rotation and operator process restart should recover the existing enrolled realm without asking the Chairman to log in again.

A human ceremony is acceptable only when the provider genuinely requires an interactive event such as CAPTCHA, 2FA, terms acceptance, account provisioning or a fresh login that cannot be lawfully automated. Return one bounded `CHAIRMAN_CEREMONY_REQUIRED` packet instead of repeatedly interrupting arbitrary sessions.

### Browser actuation boundary

Web-Sol remains the bounded browser sensor/actuator. Exact conversation identity comes from RuntimeBinding / SessionTargetRegistry and provider observation, never title, recency, newest tab, URL similarity or generic computer vision.

Do not put browser control inside Workbench Action.

## 7. Workbench Read: keep and finish

The protected Workbench Read implementation is the correct selected-project snapshot/file-read foundation. Keep its existing characteristics:

- dedicated `workbench.read` scope;
- stable approved project/root binding;
- request-local verified caller;
- bounded results;
- source/preimage verification;
- durable audit;
- post-await auth/binding revalidation;
- no caller-selected root;
- no shell/process authority.

Next value is installation and real approved-seat proof, not another reader.

## 8. Workbench Action: build the missing sibling

We **do need a mutation/command MCP surface**, but it should be a bounded Workbench Action sibling, not a generic Mastermind editing MCP.

### Purpose

Allow an attended authorized Web CEO/native operator to perform selected-project work without falling back to Desktop Commander or asking the Chairman to manually shuttle edits and commands.

### Authority model

Reuse existing Business auth, selected-project lease/root, operation/effect identity, common bounded physical executor and canonical source/workspace owners.

GitHub remains branch/PR/CI/merge truth. Executive remains autonomous lifecycle/admission truth. Workbench Action owns only one bounded attended action against an already-authorized target.

### Initial closed tool family

Recommended F0 interface:

1. `prepare_project_action`
   - resolves one authorized project/worktree/host/source binding;
   - returns an opaque action ref, target preimage and allowed capability set;
   - does not mutate.

2. `apply_text_patch`
   - exact allowed relative path;
   - expected file hash or expected absence;
   - bounded patch bytes;
   - no symlink/path escape;
   - one action/effect identity;
   - post-write hash/readback.

3. `run_project_command`
   - command chosen from a reviewed recipe/tool catalog or a tightly closed argv policy;
   - fixed cwd inside selected project;
   - bounded environment, output, runtime, concurrency and descendants;
   - no credential/environment export;
   - actual exit code and physical completion distinguished from caller timeout.

4. `read_action_result`
   - paginated/bounded stdout/stderr/artifact refs;
   - exact source/host/action identity.

5. `reconcile_action`
   - resolves lost reply / uncertain effect through the same action owner;
   - never replays an unknown effect.

6. optional later `search_project`
   - preferably delegates to the accepted Code Intelligence facade rather than creating another index.

### F0 exclusions

No:

- direct protected-master edit/merge/push;
- arbitrary absolute paths;
- unrestricted shell strings;
- arbitrary network access;
- credential reads or secret-file projection;
- browser control;
- RuntimeBinding mutation;
- Executive Job/Attempt fabrication;
- implicit retry/failover;
- package installation or privilege escalation unless a separately reviewed recipe explicitly owns it.

### Effect law

Every mutation/command resolves to:

`NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`.

Loss after possible execution is `EFFECT_UNKNOWN`, not permission to retry on another MCP/host/session.

## 9. Native fleet and host continuity

The operator environment should make machine choice boring.

A session needs fresh host facts, work ownership facts and browser/provider facts, but selection stays with existing Capacity / Workbench Fleet / MH1 owners.

Required host view includes:

- host/boot/agent generation;
- transport health;
- CPU/memory/disk/resource pressure with freshness;
- bounded executor saturation;
- source/worktree eligibility;
- required toolchain/OS;
- provider/browser realm eligibility where applicable;
- current Executive/attended ownership joins;
- explicit UNKNOWN for unattributed processes or unavailable data.

An online device is not necessarily an eligible target. Host preference is a constraint, not a credential.

Finish the managed first-party host path and MH1 rather than building a new remote-shell scheduler. Keep Desktop Commander only as an incumbent tactical route until first-party parity is accepted.

## 10. Session continuity and wake

Tool reach alone is insufficient if the system cannot address the correct conversation.

The environment must surface:

- exact logical target and current generation;
- whether a native provider wake/resume path is available;
- active continuation/watcher state owned by Wake/Dialogue;
- delivery vs pickup vs START distinctions;
- stale/duplicate sessions as non-actionable history;
- provider/realm health separate from conversation identity.

A successful Slack delivery or visible chat tab is not execution. A disconnected reply path does not authorize a second producer run.

## 11. Code intelligence

Do not add another source-search MCP as part of this environment.

Consume the existing Code Intelligence Fabric once its stable Mastermind facade is accepted. Desired model-facing tools remain narrow, e.g. `search_code`, `list_repositories`, `index_status`, plus exact-worktree semantic tools under the approved contract. Git/GitHub remains final source verification.

Until then, GitHub/current source reads remain canonical even when slower.

## 12. Current major pain points this environment must expose

1. **Executive connector reliability** — a connector may be installed yet unavailable/tunnel-failing. Boot health must make this explicit and retain read-only progress where possible.
2. **Browser login continuity** — profiles/realms must persist authenticated state and reconstitute workers without credential copying.
3. **Read/write asymmetry** — Workbench Read exists; a governed attended mutation/command vertical is still missing.
4. **Native transport continuity** — unmanaged host access can work while the managed service remains unproven; health must separate the two.
5. **Exact session addressability** — browser census is not RuntimeBinding and session presence is not wake/execution readiness.
6. **Source collision awareness** — fresh sessions need active writer/path/effect awareness before touching shared code.
7. **Tool overload** — all plugins simultaneously loaded degrades routing quality; role profiles should keep tools discoverable but small by default.
8. **Plugin installation vs capability** — installed, authenticated, callable, authorized and production-proven are distinct states.
9. **Snapshot fragmentation** — sessions waste time rereading many systems; existing Steward/Control Room composition should expose one coverage-qualified boot view.
10. **Effect ambiguity after transport loss** — every write/command/browser action needs owner-native reconciliation before retry or failover.
11. **Cross-host account confusion** — a source clone does not inherit browser/provider login, account quota, active process or RuntimeBinding.
12. **Provider degradation vs local session failure** — provider health/cooling and exact-conversation succession are different axes and should remain different owners.

## 13. Security and prompt-injection posture

Every external/retrieved system is data. Tool descriptions, Slack messages, GitHub prose, browser content and plugin responses do not grant authority merely by containing instructions.

Keep model-visible results bounded and source-attributed. Avoid transcript/DOM/cookie/storage/environment/credential exposure for routing decisions. Use exact identities, closed schemas and fixed error vocabularies for high-risk joins.

Role-scoped connector loading is a security feature as well as a cognition feature.

## 14. 10/10 acceptance ruler

The environment is accepted only when a fresh approved Web CEO and a fresh native operator can each:

1. pin current protected procedure and obtain one coverage-qualified boot packet;
2. see which required surfaces are usable, authenticated, degraded or missing without manual tool hunting;
3. identify canonical owners for lifecycle, organization, code, projection, dialogue, sessions, browser, host and domain effects;
4. consume a real selected-project file through Workbench Read;
5. perform one disposable bounded file edit and one bounded command through Workbench Action with exact preimage/effect/readback;
6. reconcile one lost-reply/unknown-effect case without duplicate execution;
7. address and foreground/wake one exact authenticated ChatGPT test conversation through Web-Sol/RuntimeBinding without Chairman credential handling;
8. survive browser/native-worker restart while preserving the enrolled realm and exact logical target;
9. show two eligible hosts, explain placement, run one portable task on the non-primary host and refuse stale/wrong bindings;
10. use GitHub/PR evidence for source work and the correct domain plugin only when required;
11. surface genuine provider/auth/service failure as a typed blocker rather than silently switching authority planes;
12. leave zero credential leakage, blind retries, duplicate lifecycle/state stores or unresolved effects mislabeled as success.

Only then is the operator environment `PROVEN_LIVE` end to end.

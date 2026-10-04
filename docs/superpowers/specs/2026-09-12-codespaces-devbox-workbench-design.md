# Codespaces DevBox Workbench — Design

**Date:** 2026-09-12
**Owner:** Sol
**Chairman direction:** build the approved Codespaces-backed DevBox path end-to-end while preserving current ChatGPT product truth: Personal Pro is an observation carrier, and modifying traversal requires a supported full-MCP Business or Enterprise/Edu workspace.
**Protected pickup:** `mastermindx-market-intelligence/Mastermind@9e180aadd0b8930867d304ad62ea27a2f12375cc`
**Skillpack:** `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1 from the same protected commit
**Capability at pickup:** `NOT_BUILT` for Codespaces backend; existing attended Web-to-Mac file/write/shell baseline remains `PROVEN_LIVE / ONE_ATTENDED_CONNECTION / BOUNDED_SMOKE_ONLY` under the Personal-MCP Cockpit/Integration owner.

## Outcome

A ChatGPT Web Sol session can use one stable first-party DevBox MCP contract to work in an explicitly owner-selected GitHub Codespace: inspect and edit repository files, run shell/git/worktree/test commands, observe long-running command output after the initiating model call returns, cancel an owned command, and obtain exact terminal/effect evidence. The Codespace is an execution resource, never a second Executive lifecycle, scheduler, queue, identity system, memory, retry plane, or source authority.

The useful first production vertical is:

```text
current attended Web-Sol authority
-> authenticated DevBox MCP
-> exact owner-issued Codespace/workspace binding
-> one prepared command identity
-> start at most once
-> independent stdout/stderr observation by process_ref + cursor
-> terminal exit/cancel truth
-> working-tree/git evidence
-> same-action reconciliation after response loss
```

The command may outlive a ChatGPT reasoning/tool request. Deterministic provider-local execution receipts survive the model turn. Executive Job/Attempt/Worker state, when present, stays owned by Executive OS.

The same source and authority plane supports two deployment-owned profiles. `OBSERVE_ONLY` uses exact scope `workbench.observe` and exposes only `devbox_status` plus `read_devbox_process`; this is the live Personal Pro carrier. `EXECUTE` uses exact scope `workbench.execute` and exposes all four tools; this is the modifying carrier for a currently supported full-MCP ChatGPT plan. The model never selects, combines or widens the profile.

ChatGPT's reviewed app snapshot is a provider projection, not a second Mastermind authority plane. Each eligible ChatGPT workspace must review the exact tool set it will invoke. OpenAI's current product contract freezes the approved tool snapshot; Business currently requires recreating and republishing the ChatGPT-side app record when that snapshot changes, while Enterprise/Edu provides action-refresh controls. Any provider-side registration must still point to the same reviewed MCP URL and reuse the existing Auth0 tenant, OAuth application/client and endpoint resource server. It does not authorize another backend, target registry, process store, credential, audit or lifecycle plane. Product source revalidated 2026-09-16: [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt).

## Existing owners reused

| Concern | Owner |
|---|---|
| Job/Attempt/Worker/Event lifecycle | Executive OS |
| durable organizational decisions/handoffs | Agent OS |
| exact repository/branch/commit/PR/CI | GitHub |
| authenticated MCP bearer verification/audit | `integrations.business_mcp_auth` |
| selected-project read semantics | existing Workbench descriptor/observer stack |
| Workbench product contract | governed Workbench architecture / this bounded implementation |
| Codespace creation/start/stop/repository binding | GitHub Codespaces API/CLI; not an MCP lifecycle database |
| command process + stdout/stderr on one bound Codespace | Codespaces DevBox provider implementation |
| source publication/merge | existing GitHub owner/release path, never generic shell credentials |

No model-visible tool accepts a host name, SSH endpoint, arbitrary filesystem root, token, GitHub credential, or Codespace account. Target selection is deployment/owner configuration and is represented to the model only by opaque references.

## Architecture

The source package is split into three narrow layers.

1. `integrations/devbox_mcp/contracts.py` contains the closed model-facing request/result vocabulary and exact effect states `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`. It performs no I/O.
2. `integrations/devbox_mcp/port.py` defines the injected attended DevBox port. The MCP app depends on this interface rather than on Codespaces, `subprocess`, SSH, GitHub, or a local path.
3. `integrations/devbox_mcp/codespace_runtime.py` implements the port for a process already running inside an admitted Codespace. It owns only provider-local execution receipts for commands it starts. The deployment owner supplies the exact repository root and an immutable opaque target/binding generation; callers cannot retarget them.

The first remote deployment runs the DevBox service *inside* the Codespace. That means filesystem and command operations are local to the cloud workspace and do not transit the Chairman Mac. GitHub remains responsible for starting/stopping the Codespace. A later stable external controller may automate GitHub Codespace lifecycle, but it must call the same DevBox contract and may not create another process/lifecycle plane.

## Tool surface

V1 defines four tools in source, selected through one exact singleton OAuth scope. `OBSERVE_ONLY` lists exactly `devbox_status` and `read_devbox_process`; `EXECUTE` lists all four. Empty, unknown or multiple scope tuples fail closed. The MCP edge and the bound DevBox port independently enforce the selected tuple.

- `devbox_status` — read-only identity/capability/working-tree observation for the currently bound target.
- `start_devbox_command` — attended modifying action. Input is `operation_key`, bounded `command_text`, and optional timeout/output ceilings. It never accepts cwd, environment, host, account, shell binary, repository, branch, or credentials.
- `read_devbox_process` — read-only process observation using an opaque `process_ref` plus independent stdout/stderr byte cursors. It never consumes another observer's output.
- `cancel_devbox_process` — modifying action scoped to one exact `process_ref`; it verifies the stored process identity before signaling the owned process group.

File edits, git operations, worktree management and tests are commands in the bound repository. Source publication remains outside V1: the Codespace runtime strips ambient `GH_TOKEN`, `GITHUB_TOKEN`, SSH-agent and Git credential helper variables/config from child commands. The default command environment has no authority to push or merge.

## Process identity and durable receipts

A process reference is derived from an owner namespace plus the `operation_key` and request digest. Provider-local records live under a deployment-owned private state directory outside the repository working tree. They are execution evidence, not Executive lifecycle state.

Runtime admission also persists one exact source-baseline receipt outside the checkout. Production admission requires a clean Git working tree by default. A known `NOT_APPLIED` start refusal does not consume that clean-baseline gate; the source must remain equal to the admitted baseline until an owned effect is durably observed. An unresolved pre-effect receipt remains `EFFECT_UNKNOWN` and blocks a different new command rather than being treated as an owned edit. Once an owned effect exists, later commands may inspect and test that command's working-tree changes. Reopening the same generation preserves the original admission baseline rather than redefining a dirty post-effect tree as clean.

`start_devbox_command` is prepare-and-start in one attended tool call but has at-most-once semantics by `operation_key`:

- no prior receipt + successful durable pre-effect record -> attempt start;
- same operation + identical request -> return/reconcile the same process;
- same operation + different request -> conflict before effect;
- uncertain spawn/write boundary -> persist/return `EFFECT_UNKNOWN`; never start a second process;
- known pre-effect refusal -> `NOT_APPLIED`.

The detached supervisor records PID, PGID/session, Linux boot ID when available, `/proc/<pid>/stat` start identity, exact command digest, workspace identity, start time, terminal time, exit code, cancellation facts, and output file identities. It writes identity-bound `STARTED` and terminal sidecars before replacing the mutable projection, so a lost primary receipt replacement can be reconciled without spawning process two. A malformed or identity-mismatched sidecar fails closed. Client-visible results contain only bounded secret-free projections.

The supervisor itself is launched from the private state home with Python safe-path mode (`-P`, `PYTHONSAFEPATH=1`, `PYTHONNOUSERSITE=1`) and an exact reviewed-source `PYTHONPATH`. The attended checkout is therefore the child command's cwd and mutation target, never the authority that selects the receipt-writing supervisor module.

Before constructing auth, runtime or the listener, the long-lived service launcher performs one sanitizing re-exec with `-P`. It replaces ambient `PYTHONPATH` with the launcher's exact reviewed-source root, sets `PYTHONSAFEPATH=1` and `PYTHONNOUSERSITE=1`, and carries only the closed Codespace service allowlist. A marker is never accepted as proof by itself: every post-exec entry reconstructs the exact expected environment and refuses unless the complete process environment is byte-for-byte equal to that projection. A forged marker, extra credential, cwd-selected module or ambient import path therefore cannot reach service construction.

A durable `cancel.json` receipt is the canonical fact that cancellation was requested. Live reads project it immediately, and normal, terminal-race, and output-uncertain terminal paths all fold the same fact into their result. A terminal process and a requested cancellation remain separate facts; neither is inferred from the other.

Each stdout/stderr projection includes `accounting_complete`. While it is `false`, `total_bytes`, `retained_bytes`, `dropped_bytes`, and `gap_ranges` are monotonic facts for bytes already consumed by the pump; more bytes may still arrive. Retained bytes are written before the corresponding progress projection is published, so a reported retained range is already readable. `accounting_complete=true` is emitted only from an exact `TERMINAL` + `APPLIED` receipt, when the byte accounting is final.

## Command confinement

This is `ATTENDED_ONLY`, not an autonomous sandbox claim. The deployment owner fixes:

- exact repository root;
- realpath/device/inode identity at startup and revalidation before every start;
- dedicated private state root;
- executable shell (`/bin/bash` on qualified Linux Codespaces V1);
- sanitized environment and PATH;
- timeout/output ceilings;
- process-group ownership;
- no inherited GitHub token, SSH agent, credential helper, cloud token, browser state, or Chairman home;
- no model-supplied cwd, env, executable, network policy, target, account, or credential.

A repository-root boundary does not claim strong filesystem confinement against arbitrary shell. V1 therefore requires the disposable/isolated Codespace execution realm. Unattended or multi-tenant promotion requires a stronger container/user/network boundary and a separate acceptance wave.

## MCP/auth boundary

The MCP app reuses `integrations.business_mcp_auth` for OAuth/JWT verification and audit. Policy and lease must contain exactly one supported scope: `workbench.observe` for `OBSERVE_ONLY`, or `workbench.execute` for `EXECUTE`. The exact singleton scope is a deployment-owned selector; a token, model request or tool argument cannot choose, combine or widen it. The server owns no token store and never receives GitHub credentials. The deployment owner supplies the authenticated port and exact allowed host/origin policy. `lease.expected_client_ref` is derived only through the public canonical `client_ref_digest(issuer, client_id)` helper from the exact accepted OAuth client identity; it is never copied from an unverified token or invented independently. A token without a usable `client_id`/`azp` cannot satisfy the DevBox lease.

OpenAI product documentation revalidated on 2026-09-16 limits Pro custom MCP connections to read/fetch permissions. Full MCP, including write/modify actions, is currently available to Business and Enterprise/Edu. Therefore Personal Pro may prove only the `OBSERVE_ONLY` slice. It cannot promote the four-tool parent capability. Every modifying call must traverse an eligible full-MCP ChatGPT workspace and still satisfy the current authenticated subject, exact `workbench.execute` policy/lease, bound target generation and attended authority.

## Codespace lifecycle

GitHub Codespaces lifecycle is deliberately separate from the MCP action contract. Initial canary uses one explicit disposable Codespace created from the implementation branch, smallest suitable machine, aggressive idle timeout, and one repo. The current Mac `gh` credential lacks the `codespace` OAuth scope; that is an action-time canary gate, not an architecture limitation.

After the execution vertical is proven, a controller may automate `list/create/start/stop` through GitHub under existing resource/capacity owners. It must return opaque target options and never expose GitHub tokens or let the model pick an arbitrary repository/host.

## Failure/correction behavior

- malformed/oversized input: refuse before effect;
- target/root/generation drift: refuse before new effect;
- dirty or changed source before the first durably owned effect: `SOURCE_DIRTY`, refuse before effect;
- operation-key conflict: refuse before effect;
- response loss after a possible spawn: `EFFECT_UNKNOWN`, same-action reconciliation only;
- exact empty owner-private operation directory with no durable PREPARED receipt: `PRE_EFFECT_RECEIPT_UNAVAILABLE`; stop the service and use the bounded operator recovery procedure, never infer a spawned process or auto-delete an ambiguous directory;
- missing, malformed, or identity-drifted durable receipt: typed `RECEIPT_UNAVAILABLE`, never generic success/refusal and never a new effect;
- durable PREPARED / START_RECEIPT_UNAVAILABLE state after a possible supervisor start: preserve `EFFECT_UNKNOWN`, reconcile the same operation only, and never apply the exact-empty deletion rule;
- missing/rotated process identity: unknown/refused, never signal a PID by number alone;
- output gap/truncation: explicit retained range/gap/truncation metadata plus `accounting_complete`;
- timeout: owned supervisor terminates the exact process group and records terminal truth; inability to prove termination is not rewritten as cancellation success;
- Codespace stop/disconnect: process becomes unavailable/unknown until same target is observed again; never auto-fail over to a Mac or second Codespace;
- Git working-tree changes are evidence, not publication or acceptance.

## First production proof

One retained disposable Codespace must prove two sequential slices through the same canonical source branch, resource server, target/process authority and public MCP URL. A profile change is an explicit policy/lease rebind of the same service plane, never a second server, CLI mode, target registry or auth plane.

### `OBSERVE_ONLY` through Personal Pro

1. the reviewed app snapshot lists exactly `devbox_status` and `read_devbox_process`;
2. authenticated `devbox_status` names only opaque target/binding/source facts;
3. when an authorized pre-existing process reference is intentionally available, `read_devbox_process` returns its bounded observation truth;
4. `start_devbox_command` and `cancel_devbox_process` are absent from discovery, and direct RPC attempts return `TOOL_NOT_AVAILABLE` before both MCP-port dispatch and runtime dispatch.

This establishes only the Personal Pro observation slice. It does not establish modifying capability and does not promote the four-tool parent beyond `BUILT_NOT_PROVEN`.

### `EXECUTE` through a supported full-MCP plan

1. the reviewed app snapshot lists exactly all four DevBox tools;
2. authenticated `devbox_status` names only opaque target/binding/source facts;
3. an exit-0 command runs in the Codespace with separate stdout/stderr observation;
4. an intentional exit-7 command records exit 7 rather than generic failure;
5. a command changes a disposable file and later read/git evidence observes the exact postimage;
6. a command can continue after the initiating tool call and be observed later by `process_ref`;
7. duplicate same-operation start reconciles without process two;
8. changed-payload reuse of that operation key refuses before effect;
9. timeout/cancel terminates only the exact owned process generation;
10. ambient GitHub credential variables are absent in child execution;
11. Codespace stop leaves no claim of success or automatic backend failover.

The four-tool parent becomes `PROVEN_LIVE` only after this exact `EXECUTE` traversal succeeds through a currently supported full-MCP ChatGPT plan and its results are read back. Source tests, a Codespace-local direct call, public port reachability, app review, OAuth success, Personal Pro observation and supported-plan modifying traversal are distinct gates.

## No-rebuild boundary

Do not add a second Executive lifecycle, durable work queue, target registry, permission database, account elector, retry service, transcript store, Git source writer, evidence database or model-session identity plane. Codespaces is a resource provider. DevBox MCP is a bounded facade. Existing owners retain their authority.

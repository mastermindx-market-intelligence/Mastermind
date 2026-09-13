# Codespaces DevBox Workbench — Design

**Date:** 2026-09-12
**Owner:** Sol
**Chairman direction:** build the approved Codespaces-backed DevBox path end-to-end and treat Personal Pro custom-MCP read/write as a proven account capability.
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

V1 exposes four tools only:

- `devbox_status` — read-only identity/capability/working-tree observation for the currently bound target.
- `start_devbox_command` — attended modifying action. Input is `operation_key`, bounded `command_text`, and optional timeout/output ceilings. It never accepts cwd, environment, host, account, shell binary, repository, branch, or credentials.
- `read_devbox_process` — read-only process observation using an opaque `process_ref` plus independent stdout/stderr byte cursors. It never consumes another observer's output.
- `cancel_devbox_process` — modifying action scoped to one exact `process_ref`; it verifies the stored process identity before signaling the owned process group.

File edits, git operations, worktree management and tests are commands in the bound repository. Source publication remains outside V1: the Codespace runtime strips ambient `GH_TOKEN`, `GITHUB_TOKEN`, SSH-agent and Git credential helper variables/config from child commands. The default command environment has no authority to push or merge.

## Process identity and durable receipts

A process reference is derived from an owner namespace plus the `operation_key` and request digest. Provider-local records live under a deployment-owned private state directory outside the repository working tree. They are execution evidence, not Executive lifecycle state.

`start_devbox_command` is prepare-and-start in one attended tool call but has at-most-once semantics by `operation_key`:

- no prior receipt + successful durable pre-effect record -> attempt start;
- same operation + identical request -> return/reconcile the same process;
- same operation + different request -> conflict before effect;
- uncertain spawn/write boundary -> persist/return `EFFECT_UNKNOWN`; never start a second process;
- known pre-effect refusal -> `NOT_APPLIED`.

The detached supervisor records PID, PGID/session, Linux boot ID when available, `/proc/<pid>/stat` start identity, exact command digest, workspace identity, start time, terminal time, exit code, cancellation facts, and output file identities. Client-visible results contain only bounded secret-free projections.

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

The MCP app reuses `integrations.business_mcp_auth` for OAuth/JWT verification and audit. A dedicated policy/resource scope `workbench.execute` is required. The server owns no token store and never receives GitHub credentials. The deployment owner supplies the authenticated port and exact allowed host/origin policy.

Personal Pro write capability is an observed account/platform fact for this Chairman seat and is no longer treated as absent. Account capability does not replace Mastermind authorization: every modifying call still needs the current authenticated subject, bound target generation and attended authority.

## Codespace lifecycle

GitHub Codespaces lifecycle is deliberately separate from the MCP action contract. Initial canary uses one explicit disposable Codespace created from the implementation branch, smallest suitable machine, aggressive idle timeout, and one repo. The current Mac `gh` credential lacks the `codespace` OAuth scope; that is an action-time canary gate, not an architecture limitation.

After the execution vertical is proven, a controller may automate `list/create/start/stop` through GitHub under existing resource/capacity owners. It must return opaque target options and never expose GitHub tokens or let the model pick an arbitrary repository/host.

## Failure/correction behavior

- malformed/oversized input: refuse before effect;
- target/root/generation drift: refuse before new effect;
- operation-key conflict: refuse before effect;
- response loss after a possible spawn: `EFFECT_UNKNOWN`, same-action reconciliation only;
- missing/rotated process identity: unknown/refused, never signal a PID by number alone;
- output gap/truncation: explicit retained range/gap/truncation metadata;
- timeout: owned supervisor terminates the exact process group and records terminal truth; inability to prove termination is not rewritten as cancellation success;
- Codespace stop/disconnect: process becomes unavailable/unknown until same target is observed again; never auto-fail over to a Mac or second Codespace;
- Git working-tree changes are evidence, not publication or acceptance.

## First production proof

One disposable Codespace must prove through the real code path:

1. authenticated `devbox_status` names only opaque target/binding/source facts;
2. an exit-0 command runs in the Codespace with separate stdout/stderr observation;
3. an intentional exit-7 command records exit 7 rather than generic failure;
4. a command changes a disposable file and later read/git evidence observes the exact postimage;
5. a command can continue after the initiating tool call and be observed later by `process_ref`;
6. duplicate same-operation start reconciles without process two;
7. changed-payload reuse of that operation key refuses before effect;
8. timeout/cancel terminates only the exact owned process generation;
9. ambient GitHub credential variables are absent in child execution;
10. Codespace stop leaves no claim of success or automatic backend failover.

The final product claim is `PROVEN_LIVE` only after the actual Personal Pro custom-MCP connection invokes the deployed DevBox app and the results above are read back. Source tests, a Codespace-local direct call, public port reachability, app connection, and successful OAuth are distinct gates.

## No-rebuild boundary

Do not add a second Executive lifecycle, durable work queue, target registry, permission database, account elector, retry service, transcript store, Git source writer, evidence database or model-session identity plane. Codespaces is a resource provider. DevBox MCP is a bounded facade. Existing owners retain their authority.
